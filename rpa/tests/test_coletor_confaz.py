"""Testes do coletor do Confaz com um HTML pequeno montado no mesmo formato da página salva."""
from rpa import modelos as m
from rpa.coletor_confaz import ColetorConfaz

CAB = "<tr><th>ITEM</th><th>DESCRIÇÃO</th><th>NCM/SH</th></tr>"


def _html(corpo_anexo1: str, extra: str = "") -> str:
    return f"""<html><body><script>var x = "<table>";</script>
    <p>ANEXO I</p><p>Nova redação dada ao Anexo I pelo Conv. ICMS 89/09, efeitos a partir de 15.10.09.</p>
    <table>{CAB}{corpo_anexo1}</table>
    <p>ANEXO II</p><p>Redação anterior dada ao Anexo II pelo Conv. ICMS 112/08, efeitos de 20.10.08 a 14.10.09.</p>
    <table><tr><th>ITEM / SUBITEM / DISCRIMINAÇÃO</th><th>NCM/SH</th></tr>
      <tr><td>Bombas antigas</td><td>9999.99.99</td></tr></table>{extra}</body></html>"""


def _coletor(tmp_path, corpo, extra="", minimo=1):
    arq = tmp_path / "confaz.html"
    arq.write_text(_html(corpo, extra), encoding="utf-8")
    return ColetorConfaz(arq, minimo_itens=minimo)


def _linha(item, desc, ncm):
    return f"<tr><td>{item}</td><td>{desc}</td><td>{ncm}</td></tr>"


def test_item_unico_sem_condicao_e_base_reduzida(tmp_path):
    c = _coletor(tmp_path, _linha("1", "Brocas", "8207.19.00"))
    r = c.consultar("8207.19.00")
    assert r.status == m.BASE_REDUZIDA
    assert "Anexo I, item 1" in r.detalhe
    assert c.consultar("82071900").status == m.BASE_REDUZIDA   # com ou sem pontos


def test_ncm_fora_da_lista(tmp_path):
    c = _coletor(tmp_path, _linha("1", "Brocas", "8207.19.00"))
    assert c.consultar("84151011").status == m.FORA_DA_LISTA


def test_tabela_de_redacao_anterior_e_ignorada(tmp_path):
    c = _coletor(tmp_path, _linha("1", "Brocas", "8207.19.00"))
    assert c.consultar("99999999").status == m.FORA_DA_LISTA


def test_ncm_em_dois_itens_e_condicional(tmp_path):
    corpo = _linha("9.07", "Aquecedores", "8419.89.99") + _linha("9.12", "Resfriadores", "8419.89.99")
    assert _coletor(tmp_path, corpo).consultar("84198999").status == m.CONDICIONAL


def test_descricao_com_condicao_ou_generica_e_condicional(tmp_path):
    corpo = _linha("1", "Silos de capacidade superior a 10 t", "7309.00.10") + _linha("2", "Outros fornos", "8417.80.90")
    c = _coletor(tmp_path, corpo)
    assert c.consultar("73090010").status == m.CONDICIONAL
    assert c.consultar("84178090").status == m.CONDICIONAL


def test_varios_ncms_na_mesma_celula(tmp_path):
    c = _coletor(tmp_path, _linha("1.3", "Reservatórios de aço", "7310.10.90, 7310.29.10 e 7310.29.90"))
    for n in ("73101090", "73102910", "73102990"):
        assert c.consultar(n).status == m.BASE_REDUZIDA


def test_posicao_inteira_e_condicional(tmp_path):
    c = _coletor(tmp_path, _linha("56.5", "Partes de máquinas", "8467.29"))
    assert c.consultar("84672911").status == m.CONDICIONAL


def test_linha_de_redacao_anterior_dentro_da_tabela_e_pulada(tmp_path):
    corpo = (
        "<tr><td colspan='3'>Nova redação dada ao subitem 13.7 do Anexo I pelo Conv. ICMS 27/12, efeitos a partir de 01.06.12.</td></tr>"
        + _linha("13.7", "Fornos industriais", "8417.80.90")
        + "<tr><td colspan='3'>Redação anterior dada ao subitem 13.7 do Anexo I pelo Conv. ICMS 89/09, efeitos de 15.10.09 a 31.05.12.</td></tr>"
        + _linha("13.7", "Fornos para carbonização", "8417.80.11")
        + _linha("14", "Máquinas para frio", "8418.99.00")
    )
    c = _coletor(tmp_path, corpo)
    assert c.consultar("84178090").status == m.BASE_REDUZIDA
    assert c.consultar("84178011").status == m.FORA_DA_LISTA
    assert c.consultar("84189900").status == m.BASE_REDUZIDA


def test_item_revogado_e_ignorado(tmp_path):
    corpo = (
        _linha("40.1", "Lavar a seco", "8451.10.00")
        + "<tr><td colspan='3'>Revogado o subitem 40.2 do Anexo I pelo Conv. ICMS 154/15, efeitos a partir de 30.12.15.</td></tr>"
        + "<tr><td colspan='3'>Redação anterior dada ao subite 40.2 do Anexo I pelo Conv. ICMS 89/09.</td></tr>"
        + _linha("40.2", "Secar", "8451.21.00")
        + _linha("40.3", "Outras de secar", "8451.29.10")
    )
    c = _coletor(tmp_path, corpo)
    assert c.consultar("84512100").status == m.FORA_DA_LISTA
    assert c.consultar("84512910").status == m.CONDICIONAL    # "Outras" -> genérico, vai para revisão


def test_falhas_nunca_viram_fora_da_lista(tmp_path):
    c = _coletor(tmp_path, _linha("1", "Brocas", "8207.19.00"))
    assert c.consultar("123").status == m.CONFAZ_FALHOU
    assert c.consultar(None).status == m.CONFAZ_FALHOU
    assert ColetorConfaz(tmp_path / "nao_existe.html").consultar("82071900").status == m.CONFAZ_FALHOU


def test_lista_pequena_demais_falha(tmp_path):
    arq = tmp_path / "confaz.html"
    arq.write_text(_html(_linha("1", "Brocas", "8207.19.00")), encoding="utf-8")
    r = ColetorConfaz(arq).consultar("82071900")        # minimo padrão = 100 itens
    assert r.status == m.CONFAZ_FALHOU and "Só achei 1 itens" in r.detalhe
