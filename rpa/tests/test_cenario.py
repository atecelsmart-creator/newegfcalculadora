import pytest

from rpa import cenario
from rpa import modelos as m
from rpa.tests.fabrica import dados

SEM = m.ResultadoST(m.SEM_ST)
COM = m.ResultadoST(m.COM_ST, mva=0.5)
FORA = m.ResultadoConfaz(m.FORA_DA_LISTA)
BASE = m.ResultadoConfaz(m.BASE_REDUZIDA)


@pytest.mark.parametrize("aliq, st, confaz, esperado, origem", [
    # Nacional / Importado / Base Reduzida x sem ST / com ST
    (12, SEM, FORA, "nacional_sem_st", "nacional"),
    (16, COM, FORA, "nacional_com_st", "nacional"),
    (18, SEM, FORA, "nacional_sem_st", "nacional"),
    (20, COM, FORA, "nacional_com_st", "nacional"),
    (4, SEM, FORA, "importado_sem_st", "importado"),
    (4, COM, FORA, "importado_com_st", "importado"),
    # Base Reduzida: a origem vem da Aliq ICMS
    (12, SEM, BASE, "base_reduzida_sem_st", "nacional"),
    (20, COM, BASE, "base_reduzida_com_st", "nacional"),
    (4, SEM, BASE, "base_reduzida_sem_st", "importado"),
    (4, COM, BASE, "base_reduzida_com_st", "importado"),
])
def test_matriz_de_cenarios(aliq, st, confaz, esperado, origem):
    d = cenario.definir_cenario(dados(aliq_icms=aliq, st=st, confaz=confaz))
    assert d.ok
    assert d.cenario == esperado
    assert d.cenario in cenario.CENARIOS_VALIDOS
    assert d.origem_base_reduzida == origem


def test_os_6_cenarios_sao_alcancaveis():
    achados = set()
    for aliq in (4, 12):
        for st in (SEM, COM):
            for confaz in (FORA, BASE):
                achados.add(cenario.definir_cenario(dados(aliq_icms=aliq, st=st, confaz=confaz)).cenario)
    assert achados == cenario.CENARIOS_VALIDOS


@pytest.mark.parametrize("aliq", [None, 0, 7, 17, 25, 0.12])
def test_aliq_invalida_vira_revisar(aliq):
    assert not cenario.definir_cenario(dados(aliq_icms=aliq)).ok


@pytest.mark.parametrize("status", [m.ST_FALHOU, m.ST_AMBIGUO, m.ST_NAO_CONSULTADO, "qualquer coisa"])
def test_st_com_falha_ou_duvida_nunca_vira_sem_st(status):
    d = cenario.definir_cenario(dados(st=m.ResultadoST(status)))
    assert not d.ok
    assert d.cenario is None


@pytest.mark.parametrize("status", [m.CONDICIONAL, m.CONFAZ_FALHOU, m.CONFAZ_NAO_CONSULTADO])
def test_confaz_com_duvida_nunca_assume_base_reduzida(status):
    d = cenario.definir_cenario(dados(confaz=m.ResultadoConfaz(status)))
    assert not d.ok


def test_estado_desconhecido_nao_e_suportado():
    assert not cenario.definir_cenario(dados(), estado="MG").ok


@pytest.mark.parametrize("aliq, confaz, esperado, origem", [
    (12, FORA, "nacional_sem_st", "nacional"),
    (18, FORA, "nacional_sem_st", "nacional"),
    (4, FORA, "importado_sem_st", "importado"),
    (12, BASE, "base_reduzida_sem_st", "nacional"),
    (4, BASE, "base_reduzida_sem_st", "importado"),
])
def test_rj_so_tem_cenarios_sem_st(aliq, confaz, esperado, origem):
    d = cenario.definir_cenario(dados(aliq_icms=aliq, confaz=confaz), estado="RJ")
    assert d.ok
    assert d.cenario == esperado
    assert d.cenario in cenario.CENARIOS_VALIDOS_RJ
    assert not d.com_st
    assert d.origem_base_reduzida == origem


@pytest.mark.parametrize("st", [SEM, COM, m.ResultadoST(m.ST_FALHOU), m.ResultadoST(m.ST_AMBIGUO), m.ResultadoST(m.ST_NAO_CONSULTADO)])
def test_rj_ignora_o_econet(st):
    """No RJ não existe ST: com ST, falha ou dúvida no Econet o cenário continua sendo o "sem ST"."""
    d = cenario.definir_cenario(dados(st=st), estado="RJ")
    assert d.ok
    assert d.cenario == "nacional_sem_st"


@pytest.mark.parametrize("aliq", [None, 0, 7, 25])
def test_rj_aliq_invalida_vira_revisar(aliq):
    assert not cenario.definir_cenario(dados(aliq_icms=aliq), estado="RJ").ok


@pytest.mark.parametrize("status", [m.CONDICIONAL, m.CONFAZ_FALHOU, m.CONFAZ_NAO_CONSULTADO])
def test_rj_confaz_com_duvida_nunca_assume_base_reduzida(status):
    assert not cenario.definir_cenario(dados(confaz=m.ResultadoConfaz(status)), estado="RJ").ok
