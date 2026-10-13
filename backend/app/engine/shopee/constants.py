"""
Constantes extraídas literalmente da planilha CALCULO_MKTPLACE_SP.xlsx,
aba "SHOPEE OPERACAO SP". Nenhum valor aqui foi inventado — cada um tem
a célula de origem anotada ao lado.

ATUALIZAÇÃO: os valores "de negócio" (comissão, taxa fixa, mentoria,
custo logístico, perda, custo da caixa de papelão) agora vêm de um
JSONConfigStore (backend/data/campos_ajustaveis_shopee.json), editável
via GET/PUT /api/config sem precisar mexer em código nem reiniciar o
servidor. Os defaults abaixo são os mesmos valores originais da planilha
— só passam a ser o ponto de partida, não mais fixos.

As alíquotas de imposto (ICMS, PIS/COFINS, IR/CSLL) continuam hardcoded:
não são "campo ajustável" no sentido pedido (comissão de plataforma),
são regime tributário do produto — mudar isso é uma decisão fiscal, não
uma taxa que a Shopee resolve mudar unilateralmente.
"""
from pathlib import Path

from app.core.config_store import JSONConfigStore

_DATA_DIR = Path(__file__).resolve().parent.parent.parent.parent / "data"

_DEFAULTS = {
    "perc_mentoria": 0.01,                  # C15
    "perc_custo_logistico": 0.035,          # C16
    "perc_perda": 0.01,                     # C17
    "custo_caixa_papelao_padrao": 2.79,     # D21 — só produtos específicos (latas de tinta, frigideiras Wok)
    "comissao_limiar": 79.99,               # C19 — limiar de preço que muda a faixa de comissão
    "comissao_pct_ate_limiar": 0.20,        # C19 — comissão até o limiar
    "comissao_pct_acima_limiar": 0.14,      # C19 — comissão acima do limiar
    "taxa_fixa_faixas": [                   # D20 — faixas de preço da taxa fixa Shopee
        {"ate": 79.99, "valor": 4.50},
        {"ate": 99.99, "valor": 16.00},
        {"ate": 199.99, "valor": 20.00},
        {"ate": None, "valor": 26.00},       # None = "acima de", última faixa (catch-all)
    ],
    "taxa_premio_fixo": 1.07,               # D20 — prêmio fixo somado em toda faixa
}

_store = JSONConfigStore(_DATA_DIR / "campos_ajustaveis_shopee.json", _DEFAULTS)


def _sync_module_attrs() -> None:
    """
    Mantém os nomes de módulo (PERC_MENTORIA etc.) sincronizados com o
    store. custos_base.py e nacional_sem_st.py leem `constants.PERC_X`
    como atributo de módulo a cada chamada — não fazem cache — então
    atualizar esses nomes aqui é suficiente pra refletir no cálculo sem
    precisar mexer nesses arquivos (já validados contra a planilha).
    """
    global PERC_MENTORIA, PERC_CUSTO_LOGISTICO, PERC_PERDA, CUSTO_CAIXA_PAPELAO_PADRAO
    cfg = _store.obter()
    PERC_MENTORIA = cfg["perc_mentoria"]
    PERC_CUSTO_LOGISTICO = cfg["perc_custo_logistico"]
    PERC_PERDA = cfg["perc_perda"]
    CUSTO_CAIXA_PAPELAO_PADRAO = cfg["custo_caixa_papelao_padrao"]


PERC_MENTORIA = _DEFAULTS["perc_mentoria"]
PERC_CUSTO_LOGISTICO = _DEFAULTS["perc_custo_logistico"]
PERC_PERDA = _DEFAULTS["perc_perda"]
CUSTO_CAIXA_PAPELAO_PADRAO = _DEFAULTS["custo_caixa_papelao_padrao"]
_sync_module_attrs()


def config_atual() -> dict:
    """GET /api/config lê daqui — devolve os campos ajustáveis atuais da Shopee."""
    return _store.obter()


def aplicar_config(novos: dict) -> dict:
    """PUT /api/config grava aqui — mescla, persiste em disco e já reflete no cálculo."""
    resultado = _store.atualizar(novos)
    _sync_module_attrs()
    return resultado


# --- Alíquotas do bloco de impostos — cenários SEM ST (colunas G:J / L:O / Q:T, linhas 3-14) ---

NACIONAL_SEM_ST = {
    "credito_presumido": 0.0,        # H3
    "icms_frete_ml_credito": 0.12,   # H4
    "icms_entrada_credito": 0.18,    # H5
    "icms_saida": 0.20,              # H6
    "pis_cofins_credito": 0.0925,    # H7
    "pis_cofins_debito": 0.0925,     # H8
    "ir_cs_credito": 0.34,           # H9
    "ir_cs_debito": 0.34,            # H10
}

BASE_REDUZIDA_SEM_ST = {
    "credito_presumido": 0.0,        # M3
    "icms_frete_ml_credito": 0.12,   # M4
    "icms_entrada_credito": 0.088,   # M5
    "icms_saida": 0.088,             # M6
    "pis_cofins_credito": 0.0925,    # M7
    "pis_cofins_debito": 0.0925,     # M8
    "ir_cs_credito": 0.34,           # M9
    "ir_cs_debito": 0.34,            # M10
}

# Regra de negócio (2026-09, confirmada com o usuário): no cenário Base
# Reduzida — tanto SEM ST quanto COM ST — o ICMS ENTRADA CRÉDITO pode ser
# 8,80% (origem nacional, valor padrão acima) ou 4,00% (origem importado).
# NENHUM outro campo muda (ICMS saída continua 8,80%, PIS/COFINS e IR/CSLL
# continuam os mesmos) — só o ICMS entrada crédito. Isto é uma
# classificação interna do produto "Base Reduzida" e não tem NENHUMA
# relação com o cenário separado "Produto Importado" (Q:T na planilha,
# sempre 4% fixo, sem essa opção) — esse não é tocado por esta regra.
BASE_REDUZIDA_SEM_ST_IMPORTADO = {
    **BASE_REDUZIDA_SEM_ST,
    "icms_entrada_credito": 0.04,
}

IMPORTADO_SEM_ST = {
    "credito_presumido": 0.0,        # R3
    "icms_frete_ml_credito": 0.12,   # R4
    "icms_entrada_credito": 0.04,    # R5
    "icms_saida": 0.20,              # R6
    "pis_cofins_credito": 0.0925,    # R7
    "pis_cofins_debito": 0.0925,     # R8
    "ir_cs_credito": 0.34,           # R9
    "ir_cs_debito": 0.34,            # R10
}

# --- Alíquotas dos cenários COM ST ---
# A planilha calcula "com ST" como média ponderada de dois sub-blocos:
#   "venda p/ SP" (peso 45%) e "venda p/ fora de SP" (peso 55%).
# O sub-bloco "venda p/ SP" usa as MESMAS alíquotas nos 3 tipos de produto
# (H38/H39=0, M38/M39=0, R38/R39=0 na planilha) — por isso é um único dicionário.
# O sub-bloco "venda p/ fora de SP" usa as MESMAS alíquotas de ICMS entrada/saída
# do cenário SEM ST equivalente (H54=H5, M54=M5, R54=R5 etc na planilha) — por
# isso reaproveitamos os dicionários *_SEM_ST acima em vez de duplicar valores.

PESO_VENDA_SP = 0.45     # linhas 36-48 (I19, N19, S19 ...)
PESO_VENDA_FORA_SP = 0.55  # linhas 52-64 (I19, N19, S19 ...)

VENDA_SP_COM_ST = {
    "credito_presumido": 0.0,        # H36 / M36 / R36 (=H36)
    "icms_frete_ml_credito": 0.12,   # H37 / M37 / R37
    "icms_entrada_credito": 0.0,     # H38 / M38 / R38
    "icms_saida": 0.0,               # H39 / M39 / R39
    "pis_cofins_credito": 0.0925,    # H40 / M40 / R40
    "pis_cofins_debito": 0.0925,     # H41 / M41 / R41
    "ir_cs_credito": 0.34,           # H42 / M42 / R42
    "ir_cs_debito": 0.34,            # H43 / M43 / R43
}

# venda_fora_sp usa as alíquotas de icms_entrada_credito/icms_saida do cenário
# SEM ST da mesma categoria (H54=0.18 igual H5; M54=0.088 igual M5; R54=0.04
# igual R5 — e o mesmo para icms_saida). credito_presumido/frete/pis-cofins/ir-cs
# também batem com o bloco sem ST da mesma categoria.
NACIONAL_VENDA_FORA_SP_COM_ST = NACIONAL_SEM_ST
BASE_REDUZIDA_VENDA_FORA_SP_COM_ST = BASE_REDUZIDA_SEM_ST
IMPORTADO_VENDA_FORA_SP_COM_ST = IMPORTADO_SEM_ST

# --- Regra de negócio COM ST (2026-09, confirmada com o usuário): mesma
# opção 8,80%/4,00% do bloco SEM ST acima (ver BASE_REDUZIDA_SEM_ST_IMPORTADO),
# só que aplicada ao sub-bloco "venda p/ fora de SP" do cenário com ST.
BASE_REDUZIDA_VENDA_FORA_SP_COM_ST_IMPORTADO = {
    **BASE_REDUZIDA_SEM_ST,
    "icms_entrada_credito": 0.04,
}


def custo_shopee_pct(preco_venda: float) -> float:
    """C19: comissão por faixa de preço — valores lidos do config store."""
    cfg = _store.obter()
    if preco_venda <= cfg["comissao_limiar"]:
        return cfg["comissao_pct_ate_limiar"]
    return cfg["comissao_pct_acima_limiar"]


def taxa_shp_premio(preco_venda: float) -> float:
    """D20: faixas de preço + prêmio fixo — valores lidos do config store."""
    cfg = _store.obter()
    faixas = cfg["taxa_fixa_faixas"]
    for faixa in faixas:
        if faixa["ate"] is None or preco_venda <= faixa["ate"]:
            return faixa["valor"] + cfg["taxa_premio_fixo"]
    # Segurança: se por algum motivo nenhuma faixa bateu (config editada sem
    # catch-all None), usa a última faixa cadastrada.
    return faixas[-1]["valor"] + cfg["taxa_premio_fixo"]
