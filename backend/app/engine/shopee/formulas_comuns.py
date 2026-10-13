"""
Bloco de impostos (I3:I12 / N3:N12 / S3:S12 na planilha) — fórmula única,
reaproveitada com alíquotas diferentes para cada um dos 6 cenários.

A única diferença estrutural dentro desse bloco é a fórmula do ICMS ENTRADA
CRÉDITO (I5 / I38 / I54 na planilha):
  - variante "padrão" (usada no bloco SEM ST e no sub-bloco "venda p/ SP"
    do COM ST): icms_entrada_credito = aliquota * custo_sem_ipi
    (planilha: =H5*$D$10 + $D$12*0.18 — D12 é sempre 0, fora de escopo)
  - variante "venda p/ fora de SP" (só existe nos cenários COM ST):
    icms_entrada_credito = valor_st + aliquota * custo_sem_ipi
    (planilha: =$D$13 + ($D$10+$D$12)*H54)
Todo o resto do bloco (I3, I4, I6, I7, I8, I9, I10, I11, I12) segue a MESMA
fórmula nas duas variantes.
"""
from dataclasses import dataclass


@dataclass
class BlocoImpostos:
    credito_presumido: float          # I3
    icms_frete_ml_credito: float      # I4
    icms_entrada_credito: float       # I5
    icms_saida: float                 # I6
    pis_cofins_credito: float         # I7
    pis_cofins_debito: float          # I8
    ir_cs_credito: float              # I9
    ir_cs_debito: float               # I10
    ir_cs: float                      # I11
    custo_total_impostos: float       # I12


def calcular_bloco_impostos(
    *,
    preco_venda: float,
    custo_sem_ipi: float,
    custo_frete: float,
    custo_produto_total: float,
    mentoria: float,
    custo_logistico: float,
    custo_shopee: float,
    taxa_shp_premio: float,
    valor_st: float,
    aliquotas: dict,
    incluir_st_no_icms_entrada: bool = False,
    perda: float = 0.0,
    incluir_perda_no_ir_cs_credito: bool = False,
    frete_compra: float = 0.0,
) -> BlocoImpostos:
    """
    Reproduz literalmente I3:I12 (ou o sub-bloco equivalente N/S, 36:45, 52:61)
    da aba "SHOPEE OPERACAO SP", para um preco_venda candidato.

    incluir_st_no_icms_entrada=True reproduz a fórmula do sub-bloco
    "venda p/ fora de SP" dos cenários COM ST (única variante que soma o
    valor do ST ao ICMS entrada crédito).
    """
    credito_presumido = aliquotas["credito_presumido"] * preco_venda        # I3 = H3*D9
    icms_frete_ml_credito = aliquotas["icms_frete_ml_credito"] * custo_frete  # I4 = H4*D18

    if incluir_st_no_icms_entrada:
        icms_entrada_credito = (                                            # I54 = D13+(D10+D12)*H54
            valor_st + aliquotas["icms_entrada_credito"] * (custo_sem_ipi + frete_compra)
        )
    else:
        # frete_compra = D14 da planilha (FRETE % sobre custo+IPI). Default 0.0 =
        # comportamento antigo (Shopee/TikTok não passam esse valor).
        icms_entrada_credito = aliquotas["icms_entrada_credito"] * custo_sem_ipi + frete_compra * 0.18  # I5 = H5*D10 + D14*0.18

    icms_saida = aliquotas["icms_saida"] * preco_venda                      # I6 = H6*D9

    pis_cofins_credito = (                                                  # I7
        custo_produto_total - icms_entrada_credito + custo_frete
        - icms_frete_ml_credito + custo_logistico + custo_shopee + taxa_shp_premio
    ) * aliquotas["pis_cofins_credito"]

    pis_cofins_debito = (preco_venda - icms_saida) * aliquotas["pis_cofins_debito"]  # I8

    ir_cs_credito = (                                                       # I9
        custo_produto_total + mentoria + custo_logistico + custo_frete
        + custo_shopee + taxa_shp_premio + icms_saida + pis_cofins_debito
        + (perda if incluir_perda_no_ir_cs_credito else 0.0)
        # Quirk da planilha: N9 (Base Reduzida) e S9 (Importado) somam D17
        # (perda) aqui; I9 (Nacional) não soma. Preservado tal como está na
        # planilha, não é uma escolha de engenharia.
    ) * aliquotas["ir_cs_credito"]

    ir_cs_debito = (                                                        # I10
        preco_venda + credito_presumido + icms_frete_ml_credito
        + icms_entrada_credito + pis_cofins_credito
    ) * aliquotas["ir_cs_debito"]

    ir_cs = max(0.0, ir_cs_debito - ir_cs_credito)                          # I11

    custo_total_impostos = (                                                # I12
        (icms_saida + pis_cofins_debito + ir_cs)
        - (icms_frete_ml_credito + icms_entrada_credito + pis_cofins_credito + credito_presumido)
    )

    return BlocoImpostos(
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
    )
