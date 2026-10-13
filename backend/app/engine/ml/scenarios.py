"""
Motor de cálculo — Mercado Livre, os 6 cenários da aba "ML OPERACAO SP"
(mesma estrutura G2:T64 da Shopee/TikTok: Nacional/Base Reduzida/Importado
x sem ST/com ST, com a média ponderada 45%/55% "venda p/ SP" x "venda p/
fora de SP" nos 3 cenários com ST).

Reaproveita do motor da Shopee (ver ml/custos_base.py pro porquê):
  - app.engine.shopee.constants — a maior parte das alíquotas e os pesos
    PESO_VENDA_SP/FORA_SP (idênticos aqui);
  - app.engine.shopee.formulas_comuns.calcular_bloco_impostos — bloco
    I3:I12 idêntico, só troca "custo_shopee"/"taxa_shp_premio" por
    custo_ml/taxa_citel_premio;
  - app.engine.shopee.solver — genérico, sem necessidade de versão própria.

EXCEÇÃO CONFIRMADA (a divergência já validada com o usuário antes desta
implementação): H54 (ICMS ENTRADA CRÉDITO, sub-bloco "venda p/ fora de
SP" do cenário Nacional — com ST) vale 0,12 na aba do ML, e NÃO 0,18 como
no equivalente da Shopee/TikTok (onde H54=H5=0,18, os dois cenários têm
essa igualdade). Só esse valor diverge — credito_presumido, icms_frete_ml
_credito, icms_saida, pis_cofins e ir_cs do mesmo sub-bloco continuam
idênticos aos da Shopee. Por isso NACIONAL_VENDA_FORA_SP_COM_ST_ML abaixo
não pode reaproveitar constants.NACIONAL_VENDA_FORA_SP_COM_ST da Shopee
(que é só um alias de NACIONAL_SEM_ST, icms_entrada_credito=0,18) — é o
único ponto de todo o motor do ML que não é um "reaproveita direto".
Base Reduzida (M54=0,088) e Importado (R54=0,04) NÃO têm essa divergência:
batem com o sem-ST equivalente, igual à Shopee — validado com teste manual
célula a célula (preço 150, custo 50, IPI 5%, ST 3%, frete R$8) contra
CALCULO_MKTPLACE_SP.xlsx recalculado no LibreOffice: os 6 cenários bateram
(I14=24.113178 no Nacional sem ST; I29=29.27912175 no Nacional com ST,
só fechou depois de aplicar esta correção do H54).

Diferença real em relação à Shopee/TikTok (o bloco de impostos em si é
idêntico, exceto a exceção do H54 acima): "CUSTO CAIXA PAPELÃO" (D23) É
subtraído no lucro real aqui (diferente do TikTok, que não tem essa
célula na fórmula) — exposto como campo de entrada `custo_caixa_papelao`,
igual ao equivalente da Shopee, default 0.0.
"""
from dataclasses import dataclass
from typing import Protocol

from app.engine.ml.custos_base import calcular_custos_base
from app.engine.shopee import constants
from app.engine.shopee.formulas_comuns import calcular_bloco_impostos
from app.schemas.calculo import Cenario

# Ver exceção do H54 no docstring do módulo — só o ICMS entrada crédito
# muda (0,12 em vez dos 0,18 de constants.NACIONAL_SEM_ST); todo o resto
# do sub-bloco "venda p/ fora de SP" do Nacional continua igual.
NACIONAL_VENDA_FORA_SP_COM_ST_ML = {
    **constants.NACIONAL_SEM_ST,
    "icms_entrada_credito": 0.12,  # H54 na planilha — confirmado, não 0.18
}


@dataclass
class EntradasSemST:
    custo_sem_ipi: float
    perc_ipi: float
    custo_frete: float
    custo_caixa_papelao: float = 0.0
    perc_st: float = 0.0
    # Só tem efeito no cenário Base Reduzida - sem ST (mesma regra da
    # Shopee: "nacional" -> ICMS entrada 8,80%; "importado" -> 4,00%).
    origem: str = "nacional"
    perc_frete: float = 0.0   # C14: FRETE de compra, % sobre custo+IPI (ex.: 0.03 = 3%)
    comissao_pct: float | None = None   # C21: comissão ML informada na tela (None = valor salvo nos ajustáveis)


@dataclass
class EntradasComST:
    custo_sem_ipi: float
    perc_ipi: float
    perc_st: float
    custo_frete: float
    custo_caixa_papelao: float = 0.0
    # Mantido por paridade de schema — sem efeito nos cenários com ST.
    origem: str = "nacional"
    perc_frete: float = 0.0   # C14: FRETE de compra, % sobre custo+IPI (ex.: 0.03 = 3%)
    comissao_pct: float | None = None   # C21: comissão ML informada na tela (None = valor salvo nos ajustáveis)


@dataclass
class ResultadoCenario:
    preco_venda: float
    custo_produto_total: float   # D16
    mentoria: float                # D17
    custo_logistico: float           # D18
    perda: float                       # D19
    custo_ml: float                      # D21
    taxa_citel_premio: float               # D22
    custo_total_impostos: float              # I12 (sem ST) ou I27 (com ST)
    lucro_real: float                          # I14 (sem ST) ou I29 (com ST)
    margem_real: float                           # J14 (sem ST) ou J29 (com ST)


def _calcular_sem_st(
    preco_venda: float,
    entradas: EntradasSemST,
    aliquotas: dict,
    incluir_perda_no_ir_cs_credito: bool = False,
) -> ResultadoCenario:
    custos = calcular_custos_base(
        preco_venda, entradas.custo_sem_ipi, entradas.perc_ipi,
        perc_st=entradas.perc_st, perc_frete=entradas.perc_frete, comissao_pct=entradas.comissao_pct,
    )
    bloco = calcular_bloco_impostos(
        preco_venda=preco_venda,
        custo_sem_ipi=entradas.custo_sem_ipi,
        custo_frete=entradas.custo_frete,
        custo_produto_total=custos.custo_produto_total,
        mentoria=custos.mentoria,
        custo_logistico=custos.custo_logistico,
        custo_shopee=custos.custo_ml,
        taxa_shp_premio=custos.taxa_citel_premio,
        valor_st=custos.valor_st,
        aliquotas=aliquotas,
        incluir_st_no_icms_entrada=False,
        perda=custos.perda,
        incluir_perda_no_ir_cs_credito=incluir_perda_no_ir_cs_credito,
        frete_compra=custos.frete_compra,
    )
    lucro_real = (                                                     # I14
        preco_venda - custos.custo_produto_total - custos.mentoria - custos.custo_logistico
        - custos.perda - entradas.custo_frete - custos.custo_ml
        - bloco.custo_total_impostos - custos.taxa_citel_premio - entradas.custo_caixa_papelao
    )
    margem_real = lucro_real / preco_venda if preco_venda else 0.0
    return ResultadoCenario(
        preco_venda=preco_venda,
        custo_produto_total=custos.custo_produto_total,
        mentoria=custos.mentoria,
        custo_logistico=custos.custo_logistico,
        perda=custos.perda,
        custo_ml=custos.custo_ml,
        taxa_citel_premio=custos.taxa_citel_premio,
        custo_total_impostos=bloco.custo_total_impostos,
        lucro_real=lucro_real,
        margem_real=margem_real,
    )


def _calcular_com_st(preco_venda: float, entradas: EntradasComST, aliquotas_fora_sp: dict) -> ResultadoCenario:
    custos = calcular_custos_base(
        preco_venda, entradas.custo_sem_ipi, entradas.perc_ipi,
        perc_st=entradas.perc_st, perc_frete=entradas.perc_frete, comissao_pct=entradas.comissao_pct,
    )
    bloco_sp = calcular_bloco_impostos(
        preco_venda=preco_venda,
        custo_sem_ipi=entradas.custo_sem_ipi,
        custo_frete=entradas.custo_frete,
        custo_produto_total=custos.custo_produto_total,
        mentoria=custos.mentoria,
        custo_logistico=custos.custo_logistico,
        custo_shopee=custos.custo_ml,
        taxa_shp_premio=custos.taxa_citel_premio,
        valor_st=custos.valor_st,
        aliquotas=constants.VENDA_SP_COM_ST,
        incluir_st_no_icms_entrada=False,
        frete_compra=custos.frete_compra,
    )
    bloco_fora_sp = calcular_bloco_impostos(
        preco_venda=preco_venda,
        custo_sem_ipi=entradas.custo_sem_ipi,
        custo_frete=entradas.custo_frete,
        custo_produto_total=custos.custo_produto_total,
        mentoria=custos.mentoria,
        custo_logistico=custos.custo_logistico,
        custo_shopee=custos.custo_ml,
        taxa_shp_premio=custos.taxa_citel_premio,
        valor_st=custos.valor_st,
        aliquotas=aliquotas_fora_sp,
        incluir_st_no_icms_entrada=True,
        frete_compra=custos.frete_compra,
    )
    custo_total_impostos = (                                           # I27
        constants.PESO_VENDA_SP * bloco_sp.custo_total_impostos
        + constants.PESO_VENDA_FORA_SP * bloco_fora_sp.custo_total_impostos
    )
    lucro_real = (                                                     # I29
        preco_venda - custos.custo_produto_total - custos.mentoria - entradas.custo_frete
        - custos.custo_ml - custos.taxa_citel_premio - custo_total_impostos
        - custos.perda - custos.custo_logistico - entradas.custo_caixa_papelao
    )
    margem_real = lucro_real / preco_venda if preco_venda else 0.0
    return ResultadoCenario(
        preco_venda=preco_venda,
        custo_produto_total=custos.custo_produto_total,
        mentoria=custos.mentoria,
        custo_logistico=custos.custo_logistico,
        perda=custos.perda,
        custo_ml=custos.custo_ml,
        taxa_citel_premio=custos.taxa_citel_premio,
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
    # Exceção do H54 — ver NACIONAL_VENDA_FORA_SP_COM_ST_ML no topo deste
    # módulo. NÃO usar constants.NACIONAL_VENDA_FORA_SP_COM_ST da Shopee
    # aqui (ficaria com icms_entrada_credito=0,18, errado pro ML).
    return _calcular_com_st(preco_venda, entradas, NACIONAL_VENDA_FORA_SP_COM_ST_ML)


def calcular_base_reduzida_com_st(preco_venda: float, entradas: EntradasComST) -> ResultadoCenario:
    return _calcular_com_st(preco_venda, entradas, constants.BASE_REDUZIDA_VENDA_FORA_SP_COM_ST)


def calcular_importado_com_st(preco_venda: float, entradas: EntradasComST) -> ResultadoCenario:
    return _calcular_com_st(preco_venda, entradas, constants.IMPORTADO_VENDA_FORA_SP_COM_ST)


class ScenarioCalculator(Protocol):
    """Contrato comum aos 6 cenários — mesmo Protocol da Shopee/TikTok."""

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


# Registro único — mesma convenção da Shopee/TikTok.
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
