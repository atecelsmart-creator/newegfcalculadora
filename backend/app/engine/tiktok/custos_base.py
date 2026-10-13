"""
Custos base (D11, D13-D21) — TikTok Shop, aba "TIK TOK OPERACAO SP".

Decisão registrada (2026-09, validada com teste manual célula a célula —
preço 150 / custo 50 / IPI 5% / ST 3% / custo frete R$8, recalculado no
LibreOffice: bate com I3:I14 da planilha, inclusive I14=11.48828205): as
alíquotas de ICMS/PIS-COFINS/IR-CSLL e a fórmula do bloco de impostos
(H3:H10, H36:H43, H52:H59 e I3:I12 / I36:I45 / I52:I61) são IDÊNTICAS,
valor por valor, nas abas Shopee, TikTok e ML — é o regime tributário do
vendedor, não uma regra da plataforma. Por isso este módulo NÃO duplica
esse bloco: reaproveita app.engine.shopee.constants (alíquotas) e
app.engine.shopee.formulas_comuns.calcular_bloco_impostos (já validados
em tests/test_nacional_sem_st.py e tests/test_outros_cenarios.py) — ver
scenarios.py. Aqui só fica o que é de fato específico do TikTok: comissão
por faixa de preço, taxa fixa + prêmio, e comissão de afiliados.
"""
from dataclasses import dataclass

from app.engine.tiktok import config as tiktok_config


@dataclass
class CustosBase:
    ipi: float                    # D11
    valor_st: float                 # D13
    custo_produto_total: float       # D14
    mentoria: float                    # D15
    custo_logistico: float               # D16
    perda: float                           # D17
    custo_tiktok_perc: float                 # C19
    custo_tiktok: float                        # D19
    taxa_tiktok_premio: float                    # D20
    comissao_afiliados: float                      # D21
    frete_compra: float = 0.0                        # D12 (FRETE % sobre custo+IPI)


def calcular_custos_base(
    preco_venda: float,
    custo_sem_ipi: float,
    perc_ipi: float,
    perc_st: float = 0.0,
    perc_frete: float = 0.0,
) -> CustosBase:
    """
    Reproduz D11, D13, D14, D15, D16, D17, D19, D20, D21 da planilha.

    D12 (frete percentual sobre custo+IPI) fica fora de escopo — mesma
    decisão já registrada no motor da Shopee (custos_base.py de lá):
    travado em 0.0 aqui (confirmado no teste manual: com C12=0.02 a
    planilha ainda bate com D12 travado em 0 do lado do Python, porque a
    planilha soma o termo pra dentro de D14 e I5 — replicar isso exigiria
    expor um campo que a Shopee decidiu não expor; mantendo consistência).
    """
    cfg = tiktok_config.obter()

    ipi = perc_ipi * custo_sem_ipi                                  # D11
    frete_compra = perc_frete * (custo_sem_ipi + ipi)               # D12 = C12*(D10+D11) (FRETE em %)
    valor_st = perc_st * custo_sem_ipi                              # D13
    custo_produto_total = frete_compra + custo_sem_ipi + ipi + valor_st  # D14 = D12+D11+D10+D13

    mentoria = preco_venda * cfg["perc_mentoria"]                   # D15
    custo_logistico = preco_venda * cfg["perc_custo_logistico"]     # D16
    perda = cfg["perc_perda"] * custo_produto_total                 # D17

    # C19 = IF(D9<limiar, pct_abaixo, pct_acima)
    abaixo_limiar = preco_venda < cfg["comissao_limiar"]
    custo_tiktok_perc = (
        cfg["comissao_pct_abaixo_limiar"] if abaixo_limiar else cfg["comissao_pct_acima_limiar"]
    )
    custo_tiktok = custo_tiktok_perc * preco_venda                   # D19

    # D20 = IF(D9<limiar, taxa_abaixo, taxa_acima) + premio_fixo
    taxa_fixa = (
        cfg["taxa_fixa_abaixo_limiar"] if abaixo_limiar else cfg["taxa_fixa_acima_limiar"]
    )
    taxa_tiktok_premio = taxa_fixa + cfg["taxa_premio_fixo"]

    comissao_afiliados = cfg["comissao_afiliados_pct"] * preco_venda  # D21

    return CustosBase(
        ipi=ipi,
        valor_st=valor_st,
        custo_produto_total=custo_produto_total,
        mentoria=mentoria,
        custo_logistico=custo_logistico,
        perda=perda,
        custo_tiktok_perc=custo_tiktok_perc,
        custo_tiktok=custo_tiktok,
        taxa_tiktok_premio=taxa_tiktok_premio,
        comissao_afiliados=comissao_afiliados,
        frete_compra=frete_compra,
    )
