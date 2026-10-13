"""
Motor de cálculo — TikTok Shop, os 6 cenários da aba "TIK TOK OPERACAO SP"
(mesma estrutura G2:T64 da aba da Shopee: Nacional/Base Reduzida/Importado
x sem ST/com ST, com a média ponderada 45%/55% "venda p/ SP" x "venda p/
fora de SP" nos 3 cenários com ST).

Reaproveita do motor da Shopee (ver custos_base.py pro porquê):
  - app.engine.shopee.constants — alíquotas (NACIONAL_SEM_ST,
    BASE_REDUZIDA_SEM_ST, IMPORTADO_SEM_ST, VENDA_SP_COM_ST e as 3
    variantes *_VENDA_FORA_SP_COM_ST) e os pesos PESO_VENDA_SP/FORA_SP;
  - app.engine.shopee.formulas_comuns.calcular_bloco_impostos — fórmula
    do bloco I3:I12 (idêntica nas 3 abas, só troca o que entra como
    "custo_shopee"/"taxa_shp_premio", que aqui são custo_tiktok e
    taxa_tiktok_premio);
  - app.engine.shopee.solver — encontrar_preco_generico/resolver_generico
    já são genéricos (só dependem de calcular_fn(preco, entradas) ->
    resultado com .margem_real/.preco_venda), não precisam de versão
    própria pro TikTok.

Validado com teste manual célula a célula (preço 150, custo 50, IPI 5%,
ST 3%, frete R$8) contra CALCULO_MKTPLACE_SP.xlsx recalculado no
LibreOffice — bloco Nacional sem ST bateu em todas as 12 células
(I3:I14), incluindo I14=11.48828205.

Diferenças reais em relação à Shopee (só na montagem final — o bloco de
impostos em si é idêntico):
  - "COMISSÃO AFILIADOS" (D21, comissao_afiliados) é um custo A MAIS que
    não existe na Shopee: entra no lucro_real de TODOS os 6 cenários mas
    NÃO entra em nenhuma fórmula do bloco de impostos (nenhuma célula de
    I3:I12/I36:I45/I52:I61 referencia D21 na planilha) — por isso só
    aparece nas linhas de lucro_real abaixo, nunca como argumento de
    calcular_bloco_impostos.
  - Não existe custo de caixa de papelão como campo separado aqui: a aba
    do TikTok tem o mesmo texto informativo (B23:B25) da Shopee, mas
    NENHUMA célula D correspondente é subtraída no lucro real (conferido:
    a fórmula de I14 não tem esse termo). Decisão: não expor esse campo
    nas entradas do TikTok — se o produto usa caixa de papelão, o custo
    deve ser somado direto em custo_sem_ipi pelo usuário.
"""
from dataclasses import dataclass
from typing import Protocol

from app.engine.shopee import constants
from app.engine.shopee.formulas_comuns import calcular_bloco_impostos
from app.engine.tiktok.custos_base import calcular_custos_base
from app.schemas.calculo import Cenario


@dataclass
class EntradasSemST:
    custo_sem_ipi: float
    perc_ipi: float
    custo_frete: float
    perc_st: float = 0.0
    perc_frete: float = 0.0   # FRETE % sobre custo+IPI (C12 da planilha)
    # Só tem efeito no cenário Base Reduzida - sem ST (mesma regra da
    # Shopee: "nacional" -> ICMS entrada 8,80%; "importado" -> 4,00%).
    origem: str = "nacional"


@dataclass
class EntradasComST:
    custo_sem_ipi: float
    perc_ipi: float
    perc_st: float
    custo_frete: float
    perc_frete: float = 0.0   # FRETE % sobre custo+IPI (C12 da planilha)
    # Mantido por paridade de schema com EntradasSemST — sem efeito nos
    # cenários com ST (mesma regra confirmada na Shopee: o campo "origem"
    # não muda nada no sub-bloco "venda p/ fora de SP").
    origem: str = "nacional"


@dataclass
class ResultadoCenario:
    preco_venda: float
    custo_produto_total: float   # D14
    mentoria: float                # D15
    custo_logistico: float           # D16
    perda: float                       # D17
    custo_tiktok: float                  # D19
    taxa_tiktok_premio: float               # D20
    comissao_afiliados: float                 # D21
    custo_total_impostos: float                 # I12 (sem ST) ou I27 (com ST)
    lucro_real: float                             # I14 (sem ST) ou I29 (com ST)
    margem_real: float                              # J14 (sem ST) ou J29 (com ST)


def _calcular_sem_st(
    preco_venda: float,
    entradas: EntradasSemST,
    aliquotas: dict,
    incluir_perda_no_ir_cs_credito: bool = False,
) -> ResultadoCenario:
    custos = calcular_custos_base(preco_venda, entradas.custo_sem_ipi, entradas.perc_ipi, perc_st=entradas.perc_st, perc_frete=entradas.perc_frete)
    bloco = calcular_bloco_impostos(
        preco_venda=preco_venda,
        custo_sem_ipi=entradas.custo_sem_ipi,
        custo_frete=entradas.custo_frete,
        custo_produto_total=custos.custo_produto_total,
        mentoria=custos.mentoria,
        custo_logistico=custos.custo_logistico,
        custo_shopee=custos.custo_tiktok,
        taxa_shp_premio=custos.taxa_tiktok_premio,
        valor_st=custos.valor_st,
        aliquotas=aliquotas,
        incluir_st_no_icms_entrada=False,
        perda=custos.perda,
        incluir_perda_no_ir_cs_credito=incluir_perda_no_ir_cs_credito,
        frete_compra=custos.frete_compra,
    )
    lucro_real = (                                                     # I14
        preco_venda - custos.custo_produto_total - custos.mentoria - custos.custo_logistico
        - custos.perda - entradas.custo_frete - custos.custo_tiktok
        - bloco.custo_total_impostos - custos.taxa_tiktok_premio - custos.comissao_afiliados
    )
    margem_real = lucro_real / preco_venda if preco_venda else 0.0
    return ResultadoCenario(
        preco_venda=preco_venda,
        custo_produto_total=custos.custo_produto_total,
        mentoria=custos.mentoria,
        custo_logistico=custos.custo_logistico,
        perda=custos.perda,
        custo_tiktok=custos.custo_tiktok,
        taxa_tiktok_premio=custos.taxa_tiktok_premio,
        comissao_afiliados=custos.comissao_afiliados,
        custo_total_impostos=bloco.custo_total_impostos,
        lucro_real=lucro_real,
        margem_real=margem_real,
    )


def _calcular_com_st(preco_venda: float, entradas: EntradasComST, aliquotas_fora_sp: dict) -> ResultadoCenario:
    custos = calcular_custos_base(preco_venda, entradas.custo_sem_ipi, entradas.perc_ipi, perc_st=entradas.perc_st, perc_frete=entradas.perc_frete)
    bloco_sp = calcular_bloco_impostos(
        preco_venda=preco_venda,
        custo_sem_ipi=entradas.custo_sem_ipi,
        custo_frete=entradas.custo_frete,
        custo_produto_total=custos.custo_produto_total,
        mentoria=custos.mentoria,
        custo_logistico=custos.custo_logistico,
        custo_shopee=custos.custo_tiktok,
        taxa_shp_premio=custos.taxa_tiktok_premio,
        valor_st=custos.valor_st,
        aliquotas=constants.VENDA_SP_COM_ST,
        frete_compra=custos.frete_compra,
        incluir_st_no_icms_entrada=False,
    )
    bloco_fora_sp = calcular_bloco_impostos(
        preco_venda=preco_venda,
        custo_sem_ipi=entradas.custo_sem_ipi,
        custo_frete=entradas.custo_frete,
        custo_produto_total=custos.custo_produto_total,
        mentoria=custos.mentoria,
        custo_logistico=custos.custo_logistico,
        custo_shopee=custos.custo_tiktok,
        taxa_shp_premio=custos.taxa_tiktok_premio,
        valor_st=custos.valor_st,
        aliquotas=aliquotas_fora_sp,
        frete_compra=custos.frete_compra,
        incluir_st_no_icms_entrada=True,
    )
    custo_total_impostos = (                                           # I27
        constants.PESO_VENDA_SP * bloco_sp.custo_total_impostos
        + constants.PESO_VENDA_FORA_SP * bloco_fora_sp.custo_total_impostos
    )
    lucro_real = (                                                     # I29
        preco_venda - custos.custo_produto_total - custos.mentoria - entradas.custo_frete
        - custos.custo_tiktok - custos.taxa_tiktok_premio - custo_total_impostos
        - custos.perda - custos.custo_logistico - custos.comissao_afiliados
    )
    margem_real = lucro_real / preco_venda if preco_venda else 0.0
    return ResultadoCenario(
        preco_venda=preco_venda,
        custo_produto_total=custos.custo_produto_total,
        mentoria=custos.mentoria,
        custo_logistico=custos.custo_logistico,
        perda=custos.perda,
        custo_tiktok=custos.custo_tiktok,
        taxa_tiktok_premio=custos.taxa_tiktok_premio,
        comissao_afiliados=custos.comissao_afiliados,
        custo_total_impostos=custo_total_impostos,
        lucro_real=lucro_real,
        margem_real=margem_real,
    )


def calcular_nacional_sem_st(preco_venda: float, entradas: EntradasSemST) -> ResultadoCenario:
    return _calcular_sem_st(preco_venda, entradas, constants.NACIONAL_SEM_ST, incluir_perda_no_ir_cs_credito=False)


def calcular_base_reduzida_sem_st(preco_venda: float, entradas: EntradasSemST) -> ResultadoCenario:
    aliquotas = (
        constants.BASE_REDUZIDA_SEM_ST_IMPORTADO
        if entradas.origem == "importado"
        else constants.BASE_REDUZIDA_SEM_ST
    )
    return _calcular_sem_st(preco_venda, entradas, aliquotas, incluir_perda_no_ir_cs_credito=True)


def calcular_importado_sem_st(preco_venda: float, entradas: EntradasSemST) -> ResultadoCenario:
    return _calcular_sem_st(preco_venda, entradas, constants.IMPORTADO_SEM_ST, incluir_perda_no_ir_cs_credito=True)


def calcular_nacional_com_st(preco_venda: float, entradas: EntradasComST) -> ResultadoCenario:
    return _calcular_com_st(preco_venda, entradas, constants.NACIONAL_VENDA_FORA_SP_COM_ST)


def calcular_base_reduzida_com_st(preco_venda: float, entradas: EntradasComST) -> ResultadoCenario:
    return _calcular_com_st(preco_venda, entradas, constants.BASE_REDUZIDA_VENDA_FORA_SP_COM_ST)


def calcular_importado_com_st(preco_venda: float, entradas: EntradasComST) -> ResultadoCenario:
    return _calcular_com_st(preco_venda, entradas, constants.IMPORTADO_VENDA_FORA_SP_COM_ST)


class ScenarioCalculator(Protocol):
    """Contrato comum aos 6 cenários — mesmo Protocol da Shopee (scenarios.py de lá)."""

    nome: str
    requer_st: bool

    def calcular(self, preco_venda: float, entradas) -> ResultadoCenario: ...


@dataclass(frozen=True)
class NacionalSemSTCalculator:
    nome: str = "Produto Nacional — sem ST"
    requer_st: bool = False

    def calcular(self, preco_venda: float, entradas: EntradasSemST) -> ResultadoCenario:
        return calcular_nacional_sem_st(preco_venda, entradas)


@dataclass(frozen=True)
class NacionalComSTCalculator:
    nome: str = "Produto Nacional — com ST"
    requer_st: bool = True

    def calcular(self, preco_venda: float, entradas: EntradasComST) -> ResultadoCenario:
        return calcular_nacional_com_st(preco_venda, entradas)


@dataclass(frozen=True)
class BaseReduzidaSemSTCalculator:
    nome: str = "Produto com Base Reduzida — sem ST"
    requer_st: bool = False

    def calcular(self, preco_venda: float, entradas: EntradasSemST) -> ResultadoCenario:
        return calcular_base_reduzida_sem_st(preco_venda, entradas)


@dataclass(frozen=True)
class BaseReduzidaComSTCalculator:
    nome: str = "Produto com Base Reduzida — com ST"
    requer_st: bool = True

    def calcular(self, preco_venda: float, entradas: EntradasComST) -> ResultadoCenario:
        return calcular_base_reduzida_com_st(preco_venda, entradas)


@dataclass(frozen=True)
class ImportadoSemSTCalculator:
    nome: str = "Produto Importado — sem ST"
    requer_st: bool = False

    def calcular(self, preco_venda: float, entradas: EntradasSemST) -> ResultadoCenario:
        return calcular_importado_sem_st(preco_venda, entradas)


@dataclass(frozen=True)
class ImportadoComSTCalculator:
    nome: str = "Produto Importado — com ST"
    requer_st: bool = True

    def calcular(self, preco_venda: float, entradas: EntradasComST) -> ResultadoCenario:
        return calcular_importado_com_st(preco_venda, entradas)


# Registro único — mesma convenção da Shopee: adicionar/alterar um cenário
# no futuro significa mexer só aqui + criar a classe correspondente.
SCENARIO_CALCULATORS: dict[Cenario, ScenarioCalculator] = {
    Cenario.NACIONAL_SEM_ST: NacionalSemSTCalculator(),
    Cenario.NACIONAL_COM_ST: NacionalComSTCalculator(),
    Cenario.BASE_REDUZIDA_SEM_ST: BaseReduzidaSemSTCalculator(),
    Cenario.BASE_REDUZIDA_COM_ST: BaseReduzidaComSTCalculator(),
    Cenario.IMPORTADO_SEM_ST: ImportadoSemSTCalculator(),
    Cenario.IMPORTADO_COM_ST: ImportadoComSTCalculator(),
}


def obter_calculator(cenario: Cenario) -> ScenarioCalculator:
    return SCENARIO_CALCULATORS[cenario]
