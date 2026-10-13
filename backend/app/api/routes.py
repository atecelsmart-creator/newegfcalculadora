"""
Endpoints HTTP. Responsabilidade única: validar formato de entrada (via
schemas), montar as entradas certas e chamar o ScenarioCalculator do
cenário escolhido (app/engine/shopee/scenarios.py), devolver o resultado.
Nenhuma regra de cálculo (aliquota, fórmula, flag de perda etc.) mora
aqui — só em scenarios.py e nos módulos que ele encapsula.
"""
from fastapi import APIRouter, File, HTTPException, UploadFile

from app.engine.ml import config as ml_config
from app.engine.ml import frete as ml_frete
from app.engine.ml import scenarios as ml_scenarios
from app.engine.ml.solver_frete import resolver_com_faixa_automatica
from app.engine.rj import config as rj_config
from app.engine.rj import frete as rj_frete
from app.engine.rj import motor as rj_motor
from app.engine.rj.solver import resolver_rj
from app.engine.shopee import constants
from app.engine.shopee.nacional_sem_st import EntradasNacionalSemST
from app.engine.shopee.outros_cenarios import EntradasComST as ShopeeEntradasComST
from app.engine.shopee.scenarios import obter_calculator as obter_calculator_shopee
from app.engine.shopee.solver import resolver_generico
from app.engine.tiktok import config as tiktok_config
from app.engine.tiktok import scenarios as tiktok_scenarios
from app.pma import store as pma_store
from app.schemas.calculo import CalculoInput, CalculoOutput, ConfigUpdateInput, Estado, Marketplace, PmaOutput

router = APIRouter()


def _montar_entradas(dados: CalculoInput, requer_st: bool):
    """
    Monta o dataclass de entradas certo pro marketplace + cenário. Os 3
    motores (shopee/scenarios.py, ml/scenarios.py, tiktok/scenarios.py) têm
    dataclasses EntradasSemST/EntradasComST próprios (nomes iguais, campos
    quase iguais) — só o TikTok não tem custo_caixa_papelao (não existe
    essa célula na fórmula dele, ver tiktok/scenarios.py).
    """
    if dados.marketplace == Marketplace.SHOPEE:
        if requer_st:
            return ShopeeEntradasComST(
                perc_frete=dados.perc_frete,
                custo_sem_ipi=dados.custo_sem_ipi,
                perc_ipi=dados.perc_ipi,
                perc_st=dados.perc_st,
                custo_frete=dados.custo_frete,
                custo_caixa_papelao=dados.custo_caixa_papelao,
                origem=dados.origem_base_reduzida.value,
            )
        return EntradasNacionalSemST(
            perc_frete=dados.perc_frete,
            custo_sem_ipi=dados.custo_sem_ipi,
            perc_ipi=dados.perc_ipi,
            perc_st=dados.perc_st,
            custo_frete=dados.custo_frete,
            custo_caixa_papelao=dados.custo_caixa_papelao,
            origem=dados.origem_base_reduzida.value,
        )

    if dados.marketplace == Marketplace.MERCADO_LIVRE:
        if requer_st:
            return ml_scenarios.EntradasComST(
                custo_sem_ipi=dados.custo_sem_ipi,
                perc_ipi=dados.perc_ipi,
                perc_st=dados.perc_st,
                custo_frete=dados.custo_frete,
                custo_caixa_papelao=dados.custo_caixa_papelao,
                origem=dados.origem_base_reduzida.value,
                perc_frete=dados.perc_frete,
                comissao_pct=dados.ml_comissao_pct,
            )
        return ml_scenarios.EntradasSemST(
            custo_sem_ipi=dados.custo_sem_ipi,
            perc_ipi=dados.perc_ipi,
            perc_st=dados.perc_st,
            custo_frete=dados.custo_frete,
            custo_caixa_papelao=dados.custo_caixa_papelao,
            origem=dados.origem_base_reduzida.value,
            perc_frete=dados.perc_frete,
            comissao_pct=dados.ml_comissao_pct,
        )

    # TikTok — sem campo custo_caixa_papelao (não existe na fórmula dele).
    if requer_st:
        return tiktok_scenarios.EntradasComST(
            perc_frete=dados.perc_frete,
            custo_sem_ipi=dados.custo_sem_ipi,
            perc_ipi=dados.perc_ipi,
            perc_st=dados.perc_st,
            custo_frete=dados.custo_frete,
            origem=dados.origem_base_reduzida.value,
        )
    return tiktok_scenarios.EntradasSemST(
        perc_frete=dados.perc_frete,
        custo_sem_ipi=dados.custo_sem_ipi,
        perc_ipi=dados.perc_ipi,
        perc_st=dados.perc_st,
        custo_frete=dados.custo_frete,
        origem=dados.origem_base_reduzida.value,
    )


_OBTER_CALCULATOR = {
    Marketplace.SHOPEE: obter_calculator_shopee,
    Marketplace.MERCADO_LIVRE: ml_scenarios.obter_calculator,
    Marketplace.TIKTOK: tiktok_scenarios.obter_calculator,
}


@router.post("/calcular", response_model=CalculoOutput)
def calcular(dados: CalculoInput) -> CalculoOutput:
    resultado = _calcular_base(dados)
    # Tabela PMA: se veio um código, compara o preço promocional com a REVENDA da planilha.
    pma = pma_store.avaliar(dados.codigo_pma, resultado.preco_promocional)
    return resultado.model_copy(update={"pma": PmaOutput(**pma)}) if pma else resultado


def _calcular_base(dados: CalculoInput) -> CalculoOutput:
    if dados.estado == Estado.SP and dados.marketplace in (Marketplace.MAGALU, Marketplace.AMAZON_DBA):
        raise HTTPException(status_code=422, detail="Magalu e Amazon DBA existem só no Rio de Janeiro.")
    ml_auto = False
    ml_faixa_aplicada = None
    ml_frete_aplicado = None
    if dados.marketplace == Marketplace.MERCADO_LIVRE and dados.custo_frete > 0:
        # Frete já conhecido (valor da plataforma do ML): equivale a digitar direto na
        # célula D20 da planilha — dispensa peso e faixa de valor.
        ml_faixa_aplicada = "Informado manualmente"
        ml_frete_aplicado = dados.custo_frete
    elif dados.marketplace == Marketplace.MERCADO_LIVRE:
        # Frete do ML vem da tabela peso x faixa de valor (D20), não é digitado.
        # Só modo MANUAL, igual à planilha (C8 peso, C9 faixa). O modo automático
        # (faixa deduzida do preço) foi desativado: sem fonte oficial confirmada.
        if not dados.ml_peso:
            raise HTTPException(status_code=422, detail="Selecione o peso do frete do Mercado Livre.")
        if not dados.ml_faixa_valor or dados.ml_faixa_valor == ml_frete.FAIXA_AUTO:
            raise HTTPException(status_code=422, detail="Selecione a faixa de valor do frete do Mercado Livre.")
        else:
            try:
                frete = ml_frete.obter_frete(dados.ml_peso, dados.ml_faixa_valor)
            except ValueError as e:
                raise HTTPException(status_code=422, detail=str(e))
            dados = dados.model_copy(update={"custo_frete": frete})
            ml_faixa_aplicada = dados.ml_faixa_valor
            ml_frete_aplicado = frete

    if dados.marketplace != Marketplace.MERCADO_LIVRE and not (
        dados.estado == Estado.RJ and dados.marketplace in (Marketplace.MAGALU, Marketplace.AMAZON_DBA)
    ):
        # Shopee/TikTok: o frete é % (C12 da planilha, entra em D12/D14). D18 (frete em R$) fica vazio.
        dados = dados.model_copy(update={"custo_frete": 0.0})

    if dados.estado == Estado.RJ:
        return _calcular_rj(dados, ml_faixa_aplicada, ml_frete_aplicado)

    calculator = _OBTER_CALCULATOR[dados.marketplace](dados.cenario)
    entradas = _montar_entradas(dados, calculator.requer_st)

    try:
        if ml_auto:
            resultado, ml_faixa_aplicada, ml_frete_aplicado = resolver_com_faixa_automatica(
                calculator, entradas, dados.ml_peso, dados.margem_desejada, dados.desconto_promocional
            )
        else:
            resultado = resolver_generico(
                calculator.calcular, entradas, dados.margem_desejada, dados.desconto_promocional
            )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    return CalculoOutput(
        cenario=dados.cenario,
        marketplace=dados.marketplace,
        preco_necessario=resultado.preco_necessario,
        preco_cheio=resultado.preco_cheio,
        preco_promocional=resultado.preco_promocional,
        lucro_real=resultado.lucro_real,
        margem_real=resultado.margem_real,
        lucro_promocional=resultado.lucro_promocional,
        margem_promocional=resultado.margem_promocional,
        custo_produto_total=resultado.custo_produto_total,
        custo_total_impostos=resultado.custo_total_impostos,
        ml_faixa_valor_aplicada=ml_faixa_aplicada,
        ml_frete_aplicado=ml_frete_aplicado,
    )


def _calcular_rj(dados: CalculoInput, ml_faixa, ml_frete) -> CalculoOutput:
    """Motor do Rio (app/engine/rj) — regras da planilha CALCULO_MKTPLACE_RJ.xlsx, sem ST."""
    tipo = rj_motor.TIPO_POR_CENARIO.get(dados.cenario.value)
    if tipo is None:
        raise HTTPException(status_code=422, detail="O Rio de Janeiro não tem cenários com ST.")
    mk = dados.marketplace
    custo_frete = dados.custo_frete
    faixa_txt = ml_faixa
    magalu_peso = magalu_nivel = None
    frete_adicional = 0.0  # Amazon DBA: kg adicional (H5)
    frete_manual = dados.custo_frete > 0  # D13 digitado direto (Magalu/Amazon): dispensa a tabela
    if mk == Marketplace.AMAZON_DBA:
        if frete_manual:
            faixa_txt = "Informado manualmente"
        else:
            if not dados.amz_peso or not dados.amz_faixa_valor:
                raise HTTPException(status_code=422, detail="Selecione o peso e o valor (faixa) do frete da Amazon DBA.")
            try:
                custo_frete = rj_frete.frete_amazon(dados.amz_peso, dados.amz_faixa_valor)
            except ValueError as e:
                raise HTTPException(status_code=422, detail=str(e))
            faixa_txt = dados.amz_faixa_valor
        try:  # KG ADICIONAL (H5): opcional — sem faixa ou sem kg vale 0, como na planilha
            frete_adicional = rj_frete.frete_adicional_amazon(dados.amz_kg_faixa, dados.amz_qtd_kg)
        except ValueError as e:
            raise HTTPException(status_code=422, detail=str(e))
    elif mk == Marketplace.MAGALU:
        if frete_manual:
            faixa_txt = "Informado manualmente"
        else:
            if not dados.magalu_peso or not dados.magalu_nivel:
                raise HTTPException(status_code=422, detail="Selecione o nível de serviço e o peso do frete da Magalu.")
            magalu_peso, magalu_nivel = dados.magalu_peso, dados.magalu_nivel
            faixa_txt = f"{magalu_nivel} · {magalu_peso}"
    entradas = rj_motor.EntradasRJ(
        marketplace=mk.value,
        tipo=tipo,
        custo_sem_ipi=dados.custo_sem_ipi,
        perc_ipi=dados.perc_ipi,
        perc_frete=dados.perc_frete,
        custo_frete=custo_frete,
        custo_caixa_papelao=dados.custo_caixa_papelao,
        magalu_peso=magalu_peso,
        magalu_nivel=magalu_nivel,
        comissao_pct=dados.ml_comissao_pct if mk in (Marketplace.MERCADO_LIVRE, Marketplace.MAGALU, Marketplace.AMAZON_DBA) else None,
        origem=dados.origem_base_reduzida.value,
        icms_pct=dados.icms_rj_pct,
        frete_adicional=frete_adicional,
    )
    try:
        r = resolver_rj(rj_motor.calcular, entradas, dados.margem_desejada, dados.desconto_promocional)
        frete_aplicado = rj_motor.calcular(r.preco_promocional, entradas).frete_aplicado
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return CalculoOutput(
        estado=Estado.RJ,
        cenario=dados.cenario,
        marketplace=mk,
        preco_necessario=r.preco_necessario,
        preco_cheio=r.preco_cheio,
        preco_promocional=r.preco_promocional,
        lucro_real=r.lucro_real,
        margem_real=r.margem_real,
        lucro_promocional=r.lucro_promocional,
        margem_promocional=r.margem_promocional,
        custo_produto_total=r.custo_produto_total,
        custo_total_impostos=r.custo_total_impostos,
        ml_faixa_valor_aplicada=faixa_txt,
        ml_frete_aplicado=frete_aplicado if mk in (Marketplace.MERCADO_LIVRE, Marketplace.MAGALU, Marketplace.AMAZON_DBA) else None,
        amz_frete_adicional=frete_adicional if mk == Marketplace.AMAZON_DBA else None,
    )


@router.get("/pma/status")
def pma_status():
    """Qual planilha PMA está carregada (arquivo, data, quantidade de itens)."""
    return pma_store.status()


@router.post("/pma/upload")
async def pma_upload(arquivo: UploadFile = File(...)):
    """Recebe a planilha do PMA (.xlsx/.xlsb/.xlsm/.xls) e substitui a tabela atual."""
    conteudo = await arquivo.read()
    if len(conteudo) > 30 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Arquivo muito grande (limite de 30 MB).")
    try:
        return pma_store.carregar_planilha(arquivo.filename or "", conteudo)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.get("/pma/buscar")
def pma_buscar(codigo: str):
    """Consulta um código na tabela PMA (a tela usa pra mostrar o produto e a REVENDA ao digitar)."""
    item = pma_store.buscar(codigo)
    if item is None:
        return {"encontrado": False, "sugestoes": pma_store.sugerir(codigo), "tabela_carregada": pma_store.status()["carregada"]}
    return {"encontrado": True, "codigo": item["codigo"], "descricao": item["descricao"], "revenda": item["revenda"], "aba": item.get("aba")}


@router.get("/cenarios")
def listar_cenarios():
    """
    Permite ao frontend descobrir os cenários e se cada um exige ST, sem
    hardcodar essa lista no HTML/JS — fonte única continua sendo
    scenarios.SCENARIO_CALCULATORS.
    """
    from app.engine.shopee.scenarios import SCENARIO_CALCULATORS

    return [
        {"valor": cenario.value, "nome": calc.nome, "requer_st": calc.requer_st}
        for cenario, calc in SCENARIO_CALCULATORS.items()
    ]


@router.get("/ml/frete-opcoes")
def ml_frete_opcoes():
    """Opções dos seletores PESO e VALOR do Mercado Livre (fonte única: ml/frete.py)."""
    return {"pesos": ml_frete.PESOS, "faixas_valor": ml_frete.FAIXAS_VALOR}


@router.get("/ml/frete")
def ml_frete_valor(peso: str, faixa_valor: str):
    """Frete (D20) pra um par Peso x Valor — a tela usa pra preencher o campo sozinha."""
    try:
        return {"valor": ml_frete.obter_frete(peso, faixa_valor)}
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.get("/rj/frete-magalu")
def rj_frete_magalu(peso: str, nivel: str):
    """Frete da tabela Magalu (nivel x peso), sem a regra de preço <= R$79 — a tela preenche o campo com isso."""
    try:
        return {"valor": rj_frete.tabela_magalu(peso, nivel)}
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.get("/rj/frete-amazon")
def rj_frete_amazon(peso: str, faixa_valor: str):
    """Frete da tabela Amazon DBA (peso x faixa de valor) — a tela preenche o campo com isso."""
    try:
        return {"valor": rj_frete.frete_amazon(peso, faixa_valor)}
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.get("/rj/frete-opcoes")
def rj_frete_opcoes():
    """Opções dos seletores de frete da Magalu e da Amazon DBA (RJ)."""
    return {
        "magalu": {"niveis": rj_frete.NIVEIS_MAGALU, "pesos": rj_frete.PESOS_MAGALU},
        "amazon_dba": {
            "faixas_valor": rj_frete.FAIXAS_AMZ,
            "pesos": rj_frete.PESOS_AMZ,
            "kg_adicional": rj_frete.KG_ADICIONAL_AMZ,  # faixa de preço -> valor por kg extra (H2/H3 da planilha)
        },
    }


@router.get("/custo-caixa-padrao")
def custo_caixa_padrao():
    """Valor de referência (R$2,79) pro frontend sugerir quando o produto usa a caixa."""
    return {"valor": constants.CUSTO_CAIXA_PAPELAO_PADRAO}


@router.get("/config")
def obter_config():
    """
    Devolve os campos ajustáveis dos 3 marketplaces pra aba "Campos
    Ajustáveis" do frontend. Os 3 já alimentam o /calcular (Shopee, ML e
    TikTok todos com motor implementado).
    """
    return {
        "shopee": constants.config_atual(),
        "mercado_livre": ml_config.obter(),
        "tiktok": tiktok_config.obter(),
        "rj": rj_config.obter_todos(),
    }


@router.put("/config")
def atualizar_config(dados: ConfigUpdateInput):
    """
    Atualiza e persiste os campos ajustáveis. Manda só o(s) marketplace(s)
    que o usuário editou — os outros ficam como estavam. A resposta trás
    de volta o estado final salvo de cada marketplace enviado (útil pro
    frontend confirmar o que realmente foi gravado).
    """
    resposta = {}
    if dados.shopee is not None:
        resposta["shopee"] = constants.aplicar_config(dados.shopee)
    if dados.mercado_livre is not None:
        resposta["mercado_livre"] = ml_config.atualizar(dados.mercado_livre)
    if dados.tiktok is not None:
        resposta["tiktok"] = tiktok_config.atualizar(dados.tiktok)
    if dados.rj is not None:
        invalidos = [k for k in dados.rj if k not in rj_config.MARKETPLACES]
        if invalidos:
            raise HTTPException(status_code=422, detail=f"Marketplace inválido no RJ: {invalidos}")
        resposta["rj"] = {mk: rj_config.atualizar(mk, valores) for mk, valores in dados.rj.items()}
    return resposta
