"""
Testes do despacho por cenário (app/engine/shopee/scenarios.py).

Não repetem a validação numérica contra a planilha — isso já está em
test_nacional_sem_st.py e test_outros_cenarios.py. Aqui o objetivo é
garantir que:
  1. Os 6 cenários do schema (Cenario) têm um calculator registrado.
  2. requer_st está certo nos 6 (só os 3 "com ST" = True).
  3. Cada calculator.calcular() devolve exatamente o mesmo resultado da
     função "pura" equivalente (nenhuma regra foi alterada ao virar
     classe — é só um wrapper).
"""
import pytest

from app.engine.shopee import outros_cenarios as outros
from app.engine.shopee.nacional_sem_st import EntradasNacionalSemST
from app.engine.shopee.nacional_sem_st import calcular as calcular_nacional_sem_st
from app.engine.shopee.outros_cenarios import EntradasComST
from app.engine.shopee.scenarios import SCENARIO_CALCULATORS, obter_calculator
from app.schemas.calculo import Cenario

PRECO_VENDA = 200.0

ENTRADAS_SEM_ST = EntradasNacionalSemST(
    custo_sem_ipi=100.0, perc_ipi=0.05, custo_frete=15.0, custo_caixa_papelao=2.0
)
ENTRADAS_COM_ST = EntradasComST(
    custo_sem_ipi=100.0, perc_ipi=0.05, perc_st=0.07, custo_frete=15.0, custo_caixa_papelao=2.0
)

CENARIOS_SEM_ST = {Cenario.NACIONAL_SEM_ST, Cenario.BASE_REDUZIDA_SEM_ST, Cenario.IMPORTADO_SEM_ST}
CENARIOS_COM_ST = {Cenario.NACIONAL_COM_ST, Cenario.BASE_REDUZIDA_COM_ST, Cenario.IMPORTADO_COM_ST}


def test_todos_os_6_cenarios_do_schema_tem_calculator_registrado():
    assert set(SCENARIO_CALCULATORS.keys()) == set(Cenario)


@pytest.mark.parametrize("cenario", sorted(CENARIOS_SEM_ST, key=lambda c: c.value))
def test_requer_st_e_falso_nos_3_cenarios_sem_st(cenario):
    assert obter_calculator(cenario).requer_st is False


@pytest.mark.parametrize("cenario", sorted(CENARIOS_COM_ST, key=lambda c: c.value))
def test_requer_st_e_verdadeiro_nos_3_cenarios_com_st(cenario):
    assert obter_calculator(cenario).requer_st is True


def test_nacional_sem_st_via_registro_bate_com_funcao_direta():
    via_registro = obter_calculator(Cenario.NACIONAL_SEM_ST).calcular(PRECO_VENDA, ENTRADAS_SEM_ST)
    direto = calcular_nacional_sem_st(PRECO_VENDA, ENTRADAS_SEM_ST)
    assert via_registro == direto


@pytest.mark.parametrize(
    "cenario,funcao_direta",
    [
        (Cenario.BASE_REDUZIDA_SEM_ST, outros.calcular_base_reduzida_sem_st),
        (Cenario.IMPORTADO_SEM_ST, outros.calcular_importado_sem_st),
    ],
)
def test_cenarios_sem_st_via_registro_batem_com_funcao_direta(cenario, funcao_direta):
    via_registro = obter_calculator(cenario).calcular(PRECO_VENDA, ENTRADAS_SEM_ST)
    direto = funcao_direta(PRECO_VENDA, ENTRADAS_SEM_ST)
    assert via_registro == direto


@pytest.mark.parametrize(
    "cenario,funcao_direta",
    [
        (Cenario.NACIONAL_COM_ST, outros.calcular_nacional_com_st),
        (Cenario.BASE_REDUZIDA_COM_ST, outros.calcular_base_reduzida_com_st),
        (Cenario.IMPORTADO_COM_ST, outros.calcular_importado_com_st),
    ],
)
def test_cenarios_com_st_via_registro_batem_com_funcao_direta(cenario, funcao_direta):
    via_registro = obter_calculator(cenario).calcular(PRECO_VENDA, ENTRADAS_COM_ST)
    direto = funcao_direta(PRECO_VENDA, ENTRADAS_COM_ST)
    assert via_registro == direto
