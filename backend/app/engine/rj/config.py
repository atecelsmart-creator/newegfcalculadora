"""
Campos ajustáveis do Rio de Janeiro — um JSON por marketplace em
backend/data/campos_ajustaveis_rj_<marketplace>.json, separados dos de SP
(alterar um estado nunca altera o outro). Defaults = valores da planilha
CALCULO_MKTPLACE_RJ.xlsx (células anotadas ao lado).

Diferenças em relação a SP: existe "custo fixo" (5%) no lugar de "perda", o
prêmio é R$1,35 e a mentoria é 1,5% em todos os marketplaces.
"""
from pathlib import Path

from app.core.config_store import JSONConfigStore

_DATA_DIR = Path(__file__).resolve().parent.parent.parent.parent / "data"

MARKETPLACES = ("shopee", "mercado_livre", "tiktok", "magalu", "amazon_dba")

_DEFAULTS = {
    "shopee": {                                  # aba SHOPEE RJ
        "comissao_limiar": 79.99,                # C11
        "comissao_pct_ate_limiar": 0.20,         # C11
        "comissao_pct_acima_limiar": 0.14,       # C11
        "taxa_fixa_faixas": [                    # D12
            {"ate": 79.99, "valor": 4.50},
            {"ate": 99.99, "valor": 16.00},
            {"ate": 199.99, "valor": 20.00},
            {"ate": None, "valor": 26.00},
        ],
        "taxa_premio_fixo": 1.35,                # D12 (+1.35)
        "perc_mentoria": 0.015,                  # C7
        "perc_custo_logistico": 0.03,            # C8
        "perc_custo_fixo": 0.05,                 # C9
        "custo_caixa_papelao_padrao": 2.79,      # nota B18
    },
    "mercado_livre": {                           # aba MELI RJ
        "comissao_pct": 0.12,                    # C14
        "taxa_premio_fixo": 1.35,                # D15 (=1+0.35)
        "perc_mentoria": 0.015,                  # C10
        "perc_custo_logistico": 0.03,            # C11
        "perc_custo_fixo": 0.05,                 # C12
    },
    "tiktok": {                                  # aba TIK TOP SHOP
        "comissao_limiar": 50.0,                 # C11 (<50)
        "comissao_pct_abaixo_limiar": 0.16,      # C11
        "comissao_pct_acima_limiar": 0.12,       # C11
        "taxa_fixa_abaixo_limiar": 4.00,         # D12
        "taxa_fixa_acima_limiar": 6.00,          # D12
        "taxa_premio_fixo": 1.35,                # D12 (+1.35)
        "comissao_afiliados_pct": 0.06,          # C13
        "perc_mentoria": 0.015,                  # C7
        "perc_custo_logistico": 0.03,            # C8
        "perc_custo_fixo": 0.05,                 # C9
    },
    "magalu": {                                  # aba MAGALU
        "comissao_pct": 0.18,                    # C14
        "taxa_fixa": 5.0,                        # D15 (=5+1.35)
        "taxa_premio_fixo": 1.35,                # D15
        "perc_mentoria": 0.015,                  # C10
        "perc_custo_logistico": 0.03,            # C11
        "perc_custo_fixo": 0.05,                 # C12
    },
    "amazon_dba": {                              # aba AMAZON DBA
        "comissao_pct": 0.135,                   # C16 (=12%+1.5%)
        "taxa_limiar_1": 30.0,                   # D17: preco < 30
        "taxa_fixa_1": 4.5,                      # D17
        "taxa_limiar_2": 50.0,                   # D17: preco < 50
        "taxa_fixa_2": 6.5,                      # D17
        "taxa_fixa_3": 6.75,                     # D17: demais
        "taxa_premio_fixo": 1.35,                # D17
        "perc_mentoria": 0.015,                  # C12
        "perc_custo_logistico": 0.03,            # C13
        "perc_custo_fixo": 0.05,                 # C14
    },
}

_stores = {
    mk: JSONConfigStore(_DATA_DIR / f"campos_ajustaveis_rj_{mk}.json", defaults)
    for mk, defaults in _DEFAULTS.items()
}


def obter(marketplace: str) -> dict:
    return _stores[marketplace].obter()


def atualizar(marketplace: str, novos: dict) -> dict:
    return _stores[marketplace].atualizar(novos)


def obter_todos() -> dict:
    return {mk: obter(mk) for mk in MARKETPLACES}
