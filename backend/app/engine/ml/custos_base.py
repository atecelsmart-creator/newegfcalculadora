"""
Custos base (D13, D15-D22) — Mercado Livre, aba "ML OPERACAO SP".

Mesma decisão registrada do motor do TikTok (ver tiktok/custos_base.py):
o bloco de impostos e as alíquotas são idênticos nas 3 abas (regime
tributário do vendedor, não regra de plataforma) — reaproveitados de
app.engine.shopee em vez de duplicados (ver scenarios.py). Validado com
teste manual célula a célula (preço 150 / custo 50 / IPI 5% / ST 3% /
custo frete R$8, recalculado no LibreOffice): bate com I3:I14 da aba ML,
inclusive I14=23.58698205 e a divergência já confirmada da célula H54
(0,12, não 0,18 — ver constants do motor, aliquotas COM ST fora de SP).

Duas decisões em aberto, sinalizadas aqui e não resolvidas por conta
própria (ver aviso no fim da resposta que acompanha este código):
  - CUSTO FRETE (D20 na planilha) é um VLOOKUP numa tabela peso x faixa de
    valor (aba "BASE FRETE MELI") — já registrado como fora de escopo em
    ml/config.py. Aqui vira parâmetro de entrada (custo_frete), informado
    manualmente, igual ao equivalente da Shopee.
  - CUSTO MERCADO LIVRE (D21 = C21*D11 - E21): a planilha subtrai um termo
    E21 que está em branco no arquivo de referência e não tem nome nem
    aparece em nenhum outro lugar da aba. Tratado aqui como 0 (mesmo valor
    que o arquivo de referência tem hoje) — não inventado, mas também não
    confirmado o que E21 representa.
"""
from dataclasses import dataclass

from app.engine.ml import config as ml_config

# D22 "TAXA CITEL + PRÊMIO": hardcoded na planilha como valor fixo (não
# vem de nenhuma célula C de entrada, ao contrário da comissão/mentoria/
# logística/perda) — por isso não está em ml/config.py, fica aqui como
# constante de módulo, igual ao valor literal da planilha.
TAXA_CITEL_PREMIO = 1.07


@dataclass
class CustosBase:
    ipi: float                  # D13
    valor_st: float               # D15
    custo_produto_total: float     # D16
    mentoria: float                  # D17
    custo_logistico: float             # D18
    perda: float                         # D19
    custo_ml_perc: float                   # C21
    custo_ml: float                          # D21
    taxa_citel_premio: float                   # D22
    frete_compra: float = 0.0                    # D14 (FRETE % sobre custo+IPI)


def calcular_custos_base(
    preco_venda: float,
    custo_sem_ipi: float,
    perc_ipi: float,
    perc_st: float = 0.0,
    perc_frete: float = 0.0,
    comissao_pct: float | None = None,
) -> CustosBase:
    """
    Reproduz D13, D14, D15, D16, D17, D18, D19, D21, D22 da planilha.

    D14 (FRETE de compra, percentual sobre custo+IPI) é o campo `perc_frete`
    (C14); default 0.0 = mesmo comportamento de antes. Entra no D16 e, por
    consequência, na PERDA (D19 = C19*D16). O efeito no ICMS entrada crédito
    (I5/I38/I54) é feito no bloco de impostos via `frete_compra`.
    """
    cfg = ml_config.obter()

    ipi = perc_ipi * custo_sem_ipi                                  # D13
    frete_compra = perc_frete * (custo_sem_ipi + ipi)               # D14 = C14*(D12+D13)
    valor_st = perc_st * custo_sem_ipi                              # D15
    custo_produto_total = frete_compra + ipi + custo_sem_ipi + valor_st  # D16 = D14+D13+D12+D15

    mentoria = preco_venda * cfg["perc_mentoria"]                   # D17
    custo_logistico = preco_venda * cfg["perc_custo_logistico"]     # D18
    perda = cfg["perc_perda"] * custo_produto_total                 # D19

    custo_ml_perc = comissao_pct if comissao_pct is not None else cfg["comissao_pct"]  # C21 (informada na tela; senão, o valor salvo)
    custo_ml = custo_ml_perc * preco_venda                          # D21 (E21 tratado como 0 — ver docstring)

    return CustosBase(
        ipi=ipi,
        valor_st=valor_st,
        custo_produto_total=custo_produto_total,
        mentoria=mentoria,
        custo_logistico=custo_logistico,
        perda=perda,
        custo_ml_perc=custo_ml_perc,
        custo_ml=custo_ml,
        taxa_citel_premio=TAXA_CITEL_PREMIO,
        frete_compra=frete_compra,
    )
