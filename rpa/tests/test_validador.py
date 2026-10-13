import pytest

from rpa import modelos as m
from rpa import validador
from rpa.tests.fabrica import dados


def test_produto_valido_nao_tem_motivos():
    assert validador.validar(dados()) == []


def test_ipi_zero_e_valido_mas_vazio_nao():
    assert validador.validar(dados(perc_ipi=0.0)) == []
    assert validador.validar(dados(perc_ipi=None))


@pytest.mark.parametrize("campo, valor", [
    ("codigo_fabricante", None),
    ("codigo_fabricante", "  "),
    ("aliq_icms", None),
    ("aliq_icms", 7),
    ("ncm", None),
    ("ncm", "1234567"),
    ("ncm", "851762779"),
    ("ncm", "abcdefgh"),
    ("unitario", None),
    ("unitario", 0),
    ("unitario", -5),
    ("perc_frete", None),
    ("perc_frete", 3),        # 3 em vez de 0.03: erro de unidade
    ("perc_ipi", 5),          # 5 em vez de 0.05
])
def test_campo_invalido_gera_motivo(campo, valor):
    assert validador.validar(dados(**{campo: valor}))


@pytest.mark.parametrize("ncm", ["85176277", "8517.62.77", "8517 6277"])
def test_ncm_com_8_digitos_aceita_pontos(ncm):
    assert validador.ncm_limpo(ncm) == "85176277"
    assert validador.validar(dados(ncm=ncm)) == []


def test_com_st_exige_mva():
    assert validador.validar(dados(st=m.ResultadoST(m.COM_ST, mva=0.5))) == []
    assert validador.validar(dados(st=m.ResultadoST(m.COM_ST, mva=None)))
    assert validador.validar(dados(st=m.ResultadoST(m.COM_ST, mva=0)))


def test_varios_problemas_aparecem_juntos():
    motivos = validador.validar(dados(unitario=None, ncm=None, aliq_icms=7))
    assert len(motivos) == 3
