"""
Tipos compartilhados entre os coletores (CSV de teste hoje; Citel, Econet e Confaz depois),
o definidor de cenário e o validador.

Convenção de unidades (a mesma que a calculadora usa):
  - perc_frete, perc_ipi e mva: FRAÇÃO (5% = 0.05)
  - aliq_icms: número em % (12% = 12)
"""
from dataclasses import dataclass, field

# Resultado da consulta ao Econet
COM_ST = "COM_ST"                      # apareceu MVA
SEM_ST = "SEM_ST"                      # pesquisa confirmada, sem resultado
ST_FALHOU = "FALHOU"                   # sessão expirada, página não carregou, erro (NUNCA vira sem ST)
ST_AMBIGUO = "AMBIGUO"                 # mais de um MVA para o mesmo NCM
ST_NAO_CONSULTADO = "NAO_CONSULTADO"

# Resultado da consulta ao Confaz (Convênio 52/91)
BASE_REDUZIDA = "BASE_REDUZIDA"        # NCM na lista e informações batem
FORA_DA_LISTA = "FORA_DA_LISTA"
CONDICIONAL = "CONDICIONAL"            # item com condição além do NCM (o robô não assume sozinho)
CONFAZ_FALHOU = "FALHOU"
CONFAZ_NAO_CONSULTADO = "NAO_CONSULTADO"


@dataclass
class ResultadoST:
    status: str = ST_NAO_CONSULTADO
    mva: float | None = None
    detalhe: str = ""


@dataclass
class ResultadoConfaz:
    status: str = CONFAZ_NAO_CONSULTADO
    detalhe: str = ""


@dataclass
class DadosProduto:
    sku: str
    codigo_fabricante: str | None = None
    unitario: float | None = None
    aliq_icms: float | None = None
    ncm: str | None = None
    perc_frete: float | None = None
    perc_ipi: float | None = None
    st: ResultadoST = field(default_factory=ResultadoST)
    confaz: ResultadoConfaz = field(default_factory=ResultadoConfaz)
