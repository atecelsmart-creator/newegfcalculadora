"""
Motor de cálculo — Shopee, Produto Nacional sem ST.

ETAPA 5 (estrutura): assinatura e mapeamento de células definidos aqui.
ETAPA 6 (implementação): corpo das funções será preenchido e validado
contra a planilha antes de seguir para os outros cenários.

Mapeamento de células (aba "SHOPEE OPERACAO SP", bloco G3:J15):
  I3  crédito presumido        I7  PIS/COFINS crédito
  I4  ICMS frete ML crédito    I8  PIS/COFINS débito
  I5  ICMS entrada crédito     I9  IR/CSLL crédito
  I6  ICMS saída               I10 IR/CSLL débito
                                I11 IR/CSLL (a pagar)
                                I12 custo total de impostos
  I14 lucro real (=D9-D14-D15-D16-D17-D18-D19-I12-D20-D21)
"""
from dataclasses import dataclass

from app.engine.shopee import constants


@dataclass
class EntradasNacionalSemST:
    custo_sem_ipi: float
    perc_ipi: float
    custo_frete: float
    custo_caixa_papelao: float
    # CORRIGIDO (2026-09): o ST NAO fica travado em 0 nos cenários "sem ST"
    # — decisão anterior estava errada. Confirmado contra a planilha real
    # (recalculada no LibreOffice, valores batendo ao centavo): o valor do
    # ST sempre entra no CUSTO DO PRODUTO (D14 = D10+D12+D13), em QUALQUER
    # cenário. A única diferença real entre "sem ST" e "com ST" é que a
    # fórmula do ICMS ENTRADA CRÉDITO não soma o valor do ST aqui (soma só
    # no sub-bloco "venda p/ fora de SP" dos cenários com ST — ver
    # formulas_comuns.incluir_st_no_icms_entrada). Default 0.0 mantém
    # compatibilidade com os testes já validados (que usavam ST=0).
    perc_st: float = 0.0
    # FRETE em % sobre custo+IPI (C12 da planilha). D12 = C12*(D10+D11), soma no D14 e no ICMS entrada (+D12*0,18).
    perc_frete: float = 0.0
    # origem: só tem efeito real no cenário Base Reduzida - sem ST (ver
    # outros_cenarios.calcular_base_reduzida_sem_st e constants.py,
    # BASE_REDUZIDA_SEM_ST_IMPORTADO). "nacional" (padrão) usa ICMS entrada
    # 8,80%; "importado" usa 4,00%. Ignorado por este cálculo (Nacional sem
    # ST) e por Importado sem ST, que já são fixos, sem essa distinção —
    # mesmo padrão do campo origem em EntradasComST (outros_cenarios.py).
    origem: str = "nacional"


@dataclass
class ResultadoCalculo:
    preco_venda: float
    # custos (D11, D14-D21)
    ipi: float
    custo_produto_total: float          # D14
    mentoria: float                     # D15
    custo_logistico: float              # D16
    perda: float                        # D17
    custo_shopee_perc: float            # C19
    custo_shopee: float                 # D19
    taxa_shp_premio: float              # D20
    # bloco de impostos (I3:I12)
    credito_presumido: float            # I3
    icms_frete_ml_credito: float        # I4
    icms_entrada_credito: float         # I5
    icms_saida: float                   # I6
    pis_cofins_credito: float           # I7
    pis_cofins_debito: float            # I8
    ir_cs_credito: float                # I9
    ir_cs_debito: float                 # I10
    ir_cs: float                        # I11
    custo_total_impostos: float         # I12
    # resultado (I14, J14)
    lucro_real: float
    margem_real: float


def calcular(preco_venda: float, entradas: EntradasNacionalSemST) -> ResultadoCalculo:
    """
    Reproduz literalmente o bloco G3:J15 da planilha (aba "SHOPEE OPERACAO SP")
    para um preco_venda candidato. Validado em tests/test_nacional_sem_st.py
    contra a própria planilha recalculada (ver comentário no arquivo de teste).
    """
    c = constants.NACIONAL_SEM_ST

    # D11, D13, D14
    ipi = entradas.perc_ipi * entradas.custo_sem_ipi                       # D11
    frete_compra = entradas.perc_frete * (entradas.custo_sem_ipi + ipi)   # D12 = C12*(D10+D11)
    st = entradas.perc_st * entradas.custo_sem_ipi                         # D13 (CORRIGIDO: não é mais travado em 0)
    custo_produto_total = frete_compra + entradas.custo_sem_ipi + ipi + st                # D14 (D12=0, fora de escopo)

    # D15, D16, D17
    mentoria = preco_venda * constants.PERC_MENTORIA                       # D15
    custo_logistico = preco_venda * constants.PERC_CUSTO_LOGISTICO         # D16
    perda = constants.PERC_PERDA * custo_produto_total                     # D17

    # D19 (C19), D20
    custo_shopee_perc = constants.custo_shopee_pct(preco_venda)            # C19
    custo_shopee = custo_shopee_perc * preco_venda                         # D19
    taxa_shp_premio = constants.taxa_shp_premio(preco_venda)               # D20

    # Bloco de impostos, na ordem de dependência da planilha (I3 -> I12)
    credito_presumido = c["credito_presumido"] * preco_venda               # I3 = H3*D9
    icms_frete_ml_credito = c["icms_frete_ml_credito"] * entradas.custo_frete  # I4 = H4*D18
    icms_entrada_credito = c["icms_entrada_credito"] * entradas.custo_sem_ipi + frete_compra * 0.18  # I5 = H5*D10 (+D12*0.18, D12=0)
    icms_saida = c["icms_saida"] * preco_venda                              # I6 = H6*D9

    pis_cofins_credito = (                                                  # I7
        custo_produto_total - icms_entrada_credito + entradas.custo_frete
        - icms_frete_ml_credito + custo_logistico + custo_shopee + taxa_shp_premio
    ) * c["pis_cofins_credito"]

    pis_cofins_debito = (preco_venda - icms_saida) * c["pis_cofins_debito"]  # I8

    ir_cs_credito = (                                                       # I9
        custo_produto_total + mentoria + custo_logistico + entradas.custo_frete
        + custo_shopee + taxa_shp_premio + icms_saida + pis_cofins_debito
    ) * c["ir_cs_credito"]

    ir_cs_debito = (                                                        # I10
        preco_venda + credito_presumido + icms_frete_ml_credito
        + icms_entrada_credito + pis_cofins_credito
    ) * c["ir_cs_debito"]

    ir_cs = max(0.0, ir_cs_debito - ir_cs_credito)                          # I11 = IF((I10-I9)<0,0,I10-I9)

    custo_total_impostos = (                                                # I12
        (icms_saida + pis_cofins_debito + ir_cs)
        - (icms_frete_ml_credito + icms_entrada_credito + pis_cofins_credito + credito_presumido)
    )

    lucro_real = (                                                          # I14
        preco_venda - custo_produto_total - mentoria - custo_logistico - perda
        - entradas.custo_frete - custo_shopee - custo_total_impostos
        - taxa_shp_premio - entradas.custo_caixa_papelao
    )
    margem_real = lucro_real / preco_venda if preco_venda else 0.0          # J14

    return ResultadoCalculo(
        preco_venda=preco_venda,
        ipi=ipi,
        custo_produto_total=custo_produto_total,
        mentoria=mentoria,
        custo_logistico=custo_logistico,
        perda=perda,
        custo_shopee_perc=custo_shopee_perc,
        custo_shopee=custo_shopee,
        taxa_shp_premio=taxa_shp_premio,
        credito_presumido=credito_presumido,
        icms_frete_ml_credito=icms_frete_ml_credito,
        icms_entrada_credito=icms_entrada_credito,
        icms_saida=icms_saida,
        pis_cofins_credito=pis_cofins_credito,
        pis_cofins_debito=pis_cofins_debito,
        ir_cs_credito=ir_cs_credito,
        ir_cs_debito=ir_cs_debito,
        ir_cs=ir_cs,
        custo_total_impostos=custo_total_impostos,
        lucro_real=lucro_real,
        margem_real=margem_real,
    )
