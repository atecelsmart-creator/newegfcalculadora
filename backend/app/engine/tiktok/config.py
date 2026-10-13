"""
Campos ajustáveis do TikTok Shop — extraídos da planilha
CALCULO_MKTPLACE_SP.xlsx, aba "TIK TOK OPERACAO SP".

IMPORTANTE: este módulo AINDA NÃO é usado por nenhum motor de cálculo —
o Módulo 1 só implementa o motor da Shopee até este ponto (ver
app/engine/shopee/). Ele existe pra deixar a aba "Campos Ajustáveis" do
frontend funcional e os valores já persistidos, prontos pro dia em que o
motor TikTok for implementado (mesma arquitetura de scenarios.py da Shopee).
"""
from pathlib import Path

from app.core.config_store import JSONConfigStore

_DATA_DIR = Path(__file__).resolve().parent.parent.parent.parent / "data"

_DEFAULTS = {
    "comissao_limiar": 50.0,                # C19 — limiar de preço da comissão
    "comissao_pct_abaixo_limiar": 0.16,     # C19 — comissão abaixo do limiar
    "comissao_pct_acima_limiar": 0.12,      # C19 — comissão a partir do limiar
    "taxa_fixa_abaixo_limiar": 4.00,        # D20 — taxa fixa abaixo do limiar
    "taxa_fixa_acima_limiar": 6.00,         # D20 — taxa fixa a partir do limiar
    "taxa_premio_fixo": 1.07,               # D20 — prêmio fixo somado em toda faixa
    "comissao_afiliados_pct": 0.06,         # C21 'COMISSÃO AFILIADOS'
    "perc_mentoria": 0.01,                  # C15
    "perc_custo_logistico": 0.035,          # C16
    "perc_perda": 0.01,                     # C17
}

_store = JSONConfigStore(_DATA_DIR / "campos_ajustaveis_tiktok.json", _DEFAULTS)


def obter() -> dict:
    return _store.obter()


def atualizar(novos: dict) -> dict:
    return _store.atualizar(novos)
