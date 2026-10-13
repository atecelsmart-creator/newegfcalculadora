"""
Motor de cálculo dos 5 cenários restantes do seletor (Etapa 8 do PDF-guia):
  - Nacional com ST            (bloco G17:J30, planilha "SHOPEE OPERACAO SP")
  - Base Reduzida sem ST        (bloco L3:O15)
  - Base Reduzida com ST         (bloco L17:O30)
  - Importado sem ST              (bloco Q3:T15)
  - Importado com ST               (bloco Q17:T30)

Todos os 6 cenários compartilham os custos base (custos_base.py) e o mesmo
formato de bloco de impostos (formulas_comuns.py); só mudam as alíquotas
(constants.py) e, nos cenários "com ST", a média ponderada 45/55 dos
sub-blocos "venda p/ SP" e "venda p/ fora de SP".

Validado contra CALCULO_MKTPLACE_SP.xlsx recalculado no LibreOffice, mesmos
casos técnicos controlados do Nacional sem ST (ver tests/test_outros_cenarios.py).
"""
from dataclasses import dataclass

from app.engine.shopee import constants
from app.engine.shopee.custos_base import calcular_custos_base
from app.engine.shopee.formulas_comuns import calcular_bloco_impostos
from app.engine.shopee.nacional_sem_st import EntradasNacionalSemST

# As entradas dos cenários "sem ST" têm exatamente o mesmo formato do
# Nacional sem ST (custo_sem_ipi, perc_ipi, custo_frete, custo_caixa_papelao,
# perc_st) — reaproveitamos a classe em vez de duplicar.
EntradasSemST = EntradasNacionalSemST


@dataclass
class EntradasComST:
    custo_sem_ipi: float
    perc_ipi: float
    perc_st: float
    custo_frete: float
    custo_caixa_papelao: float
    # CORRIGIDO (2026-09): este campo não tem mais efeito em NENHUM cenário
    # "com ST" — inclusive Base Reduzida (ver calcular_base_reduzida_com_st
    # acima, validado contra a planilha: o sub-bloco "venda p/ fora de SP"
    # sempre usa 8,80%, mesmo com "importado" selecionado). Só continua
    # tendo efeito real em EntradasSemST/calcular_base_reduzida_sem_st.
    # Mantido aqui por compatibilidade de schema (a API sempre manda esse
    # campo, mesmo pros cenários "com ST"), mas é ignorado por todos eles.
    origem: str = "nacional"
    perc_frete: float = 0.0   # FRETE % sobre custo+IPI (C12 da planilha)


@dataclass
class ResultadoCenario:
    preco_venda: float
    custo_produto_total: float   # D14
    mentoria: float               # D15
    custo_logistico: float        # D16
    perda: float                   # D17
    custo_shopee: float              # D19
    taxa_shp_premio: float             # D20
    custo_total_impostos: float          # I12 (sem ST) ou I27 (com ST)
    lucro_real: float                     # I14 (sem ST) ou I29 (com ST)
    margem_real: float                     # J14 (sem ST) ou J29 (com ST)


def _calcular_sem_st(
    preco_venda: float,
    entradas: EntradasSemST,
    aliquotas: dict,
    incluir_perda_no_ir_cs_credito: bool = False,
) -> ResultadoCenario:
    """
    Fórmula comum aos 3 cenários SEM ST — só troca o dicionário de alíquotas
    e a flag incluir_perda_no_ir_cs_credito (quirk da planilha: N9/S9 somam
    a perda no IR/CSLL crédito, I9 do Nacional não soma).

    CORRIGIDO (2026-09): esta função hardcodava perc_st=0.0 aqui dentro,
    ignorando entradas.perc_st mesmo depois da correção feita em
    nacional_sem_st.py — por isso Base Reduzida sem ST e Importado sem ST
    nunca refletiam o valor de ST digitado pelo usuário, mesmo depois do
    campo estar liberado na tela. Agora usa entradas.perc_st igual ao
    Nacional sem ST: o ST entra no custo do produto (D14) mas não entra na
    fórmula do ICMS entrada crédito neste bloco (isso só acontece no
    sub-bloco "venda p/ fora de SP" dos cenários COM ST — ver
    incluir_st_no_icms_entrada em formulas_comuns.py).
    """
    custos = calcular_custos_base(
        preco_venda, entradas.custo_sem_ipi, entradas.perc_ipi, perc_st=entradas.perc_st,
        perc_frete=entradas.perc_frete,
    )
    bloco = calcular_bloco_impostos(
        preco_venda=preco_venda,
        custo_sem_ipi=entradas.custo_sem_ipi,
        custo_frete=entradas.custo_frete,
        custo_produto_total=custos.custo_produto_total,
        mentoria=custos.mentoria,
        custo_logistico=custos.custo_logistico,
        custo_shopee=custos.custo_shopee,
        taxa_shp_premio=custos.taxa_shp_premio,
        valor_st=custos.valor_st,
        aliquotas=aliquotas,
        incluir_st_no_icms_entrada=False,
        perda=custos.perda,
        incluir_perda_no_ir_cs_credito=incluir_perda_no_ir_cs_credito,
        frete_compra=custos.frete_compra,
    )
    lucro_real = (                                                          # I14
        preco_venda - custos.custo_produto_total - custos.mentoria - custos.custo_logistico
        - custos.perda - entradas.custo_frete - custos.custo_shopee
        - bloco.custo_total_impostos - custos.taxa_shp_premio - entradas.custo_caixa_papelao
    )
    margem_real = lucro_real / preco_venda if preco_venda else 0.0
    return ResultadoCenario(
        preco_venda=preco_venda,
        custo_produto_total=custos.custo_produto_total,
        mentoria=custos.mentoria,
        custo_logistico=custos.custo_logistico,
        perda=custos.perda,
        custo_shopee=custos.custo_shopee,
        taxa_shp_premio=custos.taxa_shp_premio,
        custo_total_impostos=bloco.custo_total_impostos,
        lucro_real=lucro_real,
        margem_real=margem_real,
    )


def _calcular_com_st(preco_venda: float, entradas: EntradasComST, aliquotas_fora_sp: dict) -> ResultadoCenario:
    """
    Fórmula comum aos 3 cenários COM ST: média ponderada 45%/55% entre o
    sub-bloco "venda p/ SP" (alíquotas fixas, iguais nos 3 tipos de produto)
    e "venda p/ fora de SP" (alíquotas iguais ao cenário SEM ST equivalente).
    """
    custos = calcular_custos_base(
        preco_venda, entradas.custo_sem_ipi, entradas.perc_ipi, perc_st=entradas.perc_st,
        perc_frete=entradas.perc_frete,
    )
    bloco_sp = calcular_bloco_impostos(
        preco_venda=preco_venda,
        custo_sem_ipi=entradas.custo_sem_ipi,
        custo_frete=entradas.custo_frete,
        custo_produto_total=custos.custo_produto_total,
        mentoria=custos.mentoria,
        custo_logistico=custos.custo_logistico,
        custo_shopee=custos.custo_shopee,
        taxa_shp_premio=custos.taxa_shp_premio,
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
        custo_shopee=custos.custo_shopee,
        taxa_shp_premio=custos.taxa_shp_premio,
        valor_st=custos.valor_st,
        aliquotas=aliquotas_fora_sp,
        frete_compra=custos.frete_compra,
        incluir_st_no_icms_entrada=True,
    )
    custo_total_impostos = (                                                # I27
        constants.PESO_VENDA_SP * bloco_sp.custo_total_impostos
        + constants.PESO_VENDA_FORA_SP * bloco_fora_sp.custo_total_impostos
    )
    lucro_real = (                                                          # I29
        preco_venda - custos.custo_produto_total - custos.mentoria - entradas.custo_frete
        - custos.custo_shopee - custos.taxa_shp_premio - custo_total_impostos
        - custos.perda - custos.custo_logistico - entradas.custo_caixa_papelao
    )
    margem_real = lucro_real / preco_venda if preco_venda else 0.0
    return ResultadoCenario(
        preco_venda=preco_venda,
        custo_produto_total=custos.custo_produto_total,
        mentoria=custos.mentoria,
        custo_logistico=custos.custo_logistico,
        perda=custos.perda,
        custo_shopee=custos.custo_shopee,
        taxa_shp_premio=custos.taxa_shp_premio,
        custo_total_impostos=custo_total_impostos,
        lucro_real=lucro_real,
        margem_real=margem_real,
    )


def calcular_base_reduzida_sem_st(preco_venda: float, entradas: EntradasSemST) -> ResultadoCenario:
    # Planilha: N9 inclui D17 (perda) no IR/CSLL crédito — diferente do Nacional (I9), que não inclui.
    # Regra de negócio (2026-09): origem "importado" troca só o ICMS entrada
    # crédito de 8,80% pra 4,00% — mesma regra do Base Reduzida com ST,
    # agora também aplicada aqui no sem ST (ver constants.py,
    # BASE_REDUZIDA_SEM_ST_IMPORTADO). Tudo o mais (ICMS saída, PIS/COFINS,
    # IR/CSLL) permanece igual nos dois casos.
    aliquotas = (
        constants.BASE_REDUZIDA_SEM_ST_IMPORTADO
        if entradas.origem == "importado"
        else constants.BASE_REDUZIDA_SEM_ST
    )
    return _calcular_sem_st(
        preco_venda, entradas, aliquotas, incluir_perda_no_ir_cs_credito=True
    )


def calcular_importado_sem_st(preco_venda: float, entradas: EntradasSemST) -> ResultadoCenario:
    # Planilha: S9 inclui D17 (perda) no IR/CSLL crédito — mesma diferença do Base Reduzida.
    return _calcular_sem_st(
        preco_venda, entradas, constants.IMPORTADO_SEM_ST, incluir_perda_no_ir_cs_credito=True
    )


def calcular_nacional_com_st(preco_venda: float, entradas: EntradasComST) -> ResultadoCenario:
    return _calcular_com_st(preco_venda, entradas, constants.NACIONAL_VENDA_FORA_SP_COM_ST)


def calcular_base_reduzida_com_st(preco_venda: float, entradas: EntradasComST) -> ResultadoCenario:
    # CORRIGIDO (2026-09, validado célula a célula contra a planilha —
    # CALCULO_MKTPLACE_SP.xlsx, bloco L17:O30): ao contrário da regra de
    # negócio anterior (abaixo, comentário antigo removido), o toggle
    # "origem" (nacional/importado) NÃO tem efeito neste cenário. O
    # sub-bloco "venda p/ fora de SP" usa ICMS entrada crédito 8,80%
    # sempre, mesmo com "importado" (4,00%) selecionado na tela — só o
    # Base Reduzida SEM ST (calcular_base_reduzida_sem_st, acima) responde
    # a esse campo. BASE_REDUZIDA_VENDA_FORA_SP_COM_ST_IMPORTADO deixou de
    # ser usado (mantido em constants.py só por rastreabilidade/histórico).
    return _calcular_com_st(preco_venda, entradas, constants.BASE_REDUZIDA_VENDA_FORA_SP_COM_ST)


def calcular_importado_com_st(preco_venda: float, entradas: EntradasComST) -> ResultadoCenario:
    return _calcular_com_st(preco_venda, entradas, constants.IMPORTADO_VENDA_FORA_SP_COM_ST)
