"""
Camada de despacho por cenário (Etapa 8 do PDF-guia, arquitetura pedida
explicitamente: "ScenarioCalculator -> NacionalSemSTCalculator / ...").

Este módulo NÃO reimplementa nenhuma fórmula. Cada classe abaixo é um
wrapper fino em torno das funções já validadas contra a planilha em
nacional_sem_st.py / outros_cenarios.py (ver tests/test_nacional_sem_st.py
e tests/test_outros_cenarios.py — comparação célula a célula com a
planilha recalculada no LibreOffice). O objetivo aqui é só isto: garantir
que trocar o cenário troca o CONJUNTO CORRETO de regras (aliquotas, flag
de perda no IR/CSLL crédito, presença ou não da média ponderada 45/55),
sem depender de "if cenario == ..." espalhado pela API ou pelo frontend.

Resumo do que muda entre os 6 cenários (documentado na matriz aprovada
antes desta implementação):
  - Nacional / Base Reduzida / Importado: mudam as aliquotas de ICMS
    entrada crédito e ICMS saída, e (só nos cenários SEM ST) se a perda
    (D17) entra ou não no IR/CSLL crédito — Nacional não inclui,
    Base Reduzida e Importado incluem.
  - sem ST / com ST: SEM ST usa o bloco de fórmulas direto (I3:I14 /
    N3:N14 / S3:S14); COM ST vira uma média ponderada 45%/55% entre dois
    sub-blocos ("venda p/ SP" e "venda p/ fora de SP"), o ICMS entrada
    crédito passa a somar o valor do ST, e a flag de perda no IR/CSLL
    crédito fica sempre desligada (mesmo para Base Reduzida/Importado).
  - Base Reduzida tem uma regra extra, só dela — vale tanto pro sem ST
    quanto pro com ST: o campo `origem` ("nacional", padrão, ou
    "importado") escolhe se o ICMS entrada crédito é 8,80% ou 4,00% (no
    com ST, isso se aplica ao sub-bloco "venda p/ fora de SP") — nada mais
    muda (ICMS saída continua 8,80% nos dois casos). Isso NÃO tem relação
    com os cenários "Produto Importado" (que continuam fixos em 4%, sem
    essa opção) — é só uma classificação de origem dentro do próprio Base
    Reduzida. Nacional (sem/com ST) e Importado (sem/com ST) ignoram esse
    campo. Ver constants.py (BASE_REDUZIDA_SEM_ST_IMPORTADO,
    BASE_REDUZIDA_VENDA_FORA_SP_COM_ST_IMPORTADO) e
    outros_cenarios.calcular_base_reduzida_sem_st /
    calcular_base_reduzida_com_st.
  - Frete (D12/D18), IPI, taxas e faixas da Shopee, ICMS frete ML
    crédito (12%), PIS/COFINS (9,25%) e IR/CSLL (34%): idênticos nos 6.
"""
from dataclasses import dataclass
from typing import Protocol, Union

from app.engine.shopee import outros_cenarios as _outros
from app.engine.shopee.nacional_sem_st import (
    EntradasNacionalSemST,
    ResultadoCalculo,
)
from app.engine.shopee.nacional_sem_st import calcular as _calcular_nacional_sem_st
from app.engine.shopee.outros_cenarios import EntradasComST, EntradasSemST, ResultadoCenario
from app.schemas.calculo import Cenario

Entradas = Union[EntradasSemST, EntradasComST]
Resultado = Union[ResultadoCalculo, ResultadoCenario]


class ScenarioCalculator(Protocol):
    """Contrato comum aos 6 cenários — usado pelo solver e pela API."""

    #: nome de exibição (só informativo, não entra em regra de cálculo)
    nome: str
    #: True para os 3 cenários "com ST" — API monta EntradasComST; False
    #: para os 3 "sem ST" — API monta EntradasSemST (sem perc_st, travado
    #: em 0 por decisão registrada).
    requer_st: bool

    def calcular(self, preco_venda: float, entradas: Entradas) -> Resultado:
        ...


@dataclass(frozen=True)
class NacionalSemSTCalculator:
    nome: str = "Produto Nacional — sem ST"
    requer_st: bool = False

    def calcular(self, preco_venda: float, entradas: EntradasNacionalSemST) -> ResultadoCalculo:
        return _calcular_nacional_sem_st(preco_venda, entradas)


@dataclass(frozen=True)
class NacionalComSTCalculator:
    nome: str = "Produto Nacional — com ST"
    requer_st: bool = True

    def calcular(self, preco_venda: float, entradas: EntradasComST) -> ResultadoCenario:
        return _outros.calcular_nacional_com_st(preco_venda, entradas)


@dataclass(frozen=True)
class BaseReduzidaSemSTCalculator:
    nome: str = "Produto com Base Reduzida — sem ST"
    requer_st: bool = False

    def calcular(self, preco_venda: float, entradas: EntradasSemST) -> ResultadoCenario:
        return _outros.calcular_base_reduzida_sem_st(preco_venda, entradas)


@dataclass(frozen=True)
class BaseReduzidaComSTCalculator:
    nome: str = "Produto com Base Reduzida — com ST"
    requer_st: bool = True

    def calcular(self, preco_venda: float, entradas: EntradasComST) -> ResultadoCenario:
        return _outros.calcular_base_reduzida_com_st(preco_venda, entradas)


@dataclass(frozen=True)
class ImportadoSemSTCalculator:
    nome: str = "Produto Importado — sem ST"
    requer_st: bool = False

    def calcular(self, preco_venda: float, entradas: EntradasSemST) -> ResultadoCenario:
        return _outros.calcular_importado_sem_st(preco_venda, entradas)


@dataclass(frozen=True)
class ImportadoComSTCalculator:
    nome: str = "Produto Importado — com ST"
    requer_st: bool = True

    def calcular(self, preco_venda: float, entradas: EntradasComST) -> ResultadoCenario:
        return _outros.calcular_importado_com_st(preco_venda, entradas)


# Registro único — é a ÚNICA fonte de dispatch por cenário no motor inteiro.
# Adicionar/alterar um cenário no futuro (ex: um 7º cenário) significa mexer
# só aqui + criar a classe correspondente, nunca em routes.py ou no frontend.
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
