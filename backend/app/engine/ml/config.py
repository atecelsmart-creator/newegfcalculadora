"""
Campos ajustáveis do Mercado Livre — extraídos da planilha
CALCULO_MKTPLACE_SP.xlsx, aba "ML OPERACAO SP".

IMPORTANTE: este módulo AINDA NÃO é usado por nenhum motor de cálculo —
o Módulo 1 só implementa o motor da Shopee até este ponto (ver
app/engine/shopee/). Ele existe pra deixar a aba "Campos Ajustáveis" do
frontend funcional e os valores já persistidos, prontos pro dia em que o
motor ML for implementado (mesma arquitetura de scenarios.py da Shopee).

Frete do ML (D20 na planilha) não entra aqui: na planilha ele vem de um
VLOOKUP numa tabela de peso x faixa de valor (aba "BASE FRETE MELI"), não
é uma taxa fixa simples — decisão registrada: fora de escopo por enquanto.
"""
from pathlib import Path

from app.core.config_store import JSONConfigStore

_DATA_DIR = Path(__file__).resolve().parent.parent.parent.parent / "data"

_DEFAULTS = {
    "comissao_pct": 0.12,           # C21 'CUSTO MERCADO LIVRE'
    "perc_mentoria": 0.015,         # C17
    "perc_custo_logistico": 0.035,  # C18
    "perc_perda": 0.01,             # C19
}

_store = JSONConfigStore(_DATA_DIR / "campos_ajustaveis_mercado_livre.json", _DEFAULTS)


def obter() -> dict:
    return _store.obter()


def atualizar(novos: dict) -> dict:
    return _store.atualizar(novos)
