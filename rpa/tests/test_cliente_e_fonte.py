from rpa import cenario, cliente_api, config
from rpa import modelos as m
from rpa.fonte_csv import FonteCSV
from rpa.tests.fabrica import dados


def _payload(d, margem=0.15, desconto=0.10):
    return cliente_api.montar_payload(d, cenario.definir_cenario(d), margem, desconto)


def test_payload_sem_st_usa_perc_st_da_config(monkeypatch):
    monkeypatch.setattr(config, "PERC_ST_SEM_ST", 0.0)
    p = _payload(dados())
    assert p["cenario"] == "nacional_sem_st"
    assert p["marketplace"] == "shopee" and p["estado"] == "SP"
    assert p["perc_st"] == 0.0
    assert p["custo_sem_ipi"] == 100.0 and p["perc_ipi"] == 0.05 and p["perc_frete"] == 0.03
    assert p["margem_desejada"] == 0.15 and p["desconto_promocional"] == 0.10


def test_payload_com_st_usa_o_mva_do_econet():
    p = _payload(dados(st=m.ResultadoST(m.COM_ST, mva=0.5)))
    assert p["cenario"] == "nacional_com_st"
    assert p["perc_st"] == 0.5


def test_payload_base_reduzida_importada():
    p = _payload(dados(aliq_icms=4, confaz=m.ResultadoConfaz(m.BASE_REDUZIDA)))
    assert p["cenario"] == "base_reduzida_sem_st"
    assert p["origem_base_reduzida"] == "importado"


def test_codigo_pma_vem_do_fabricante_ou_do_sku(monkeypatch):
    monkeypatch.setattr(config, "PMA_CODIGO_DE", "fabricante")
    assert _payload(dados())["codigo_pma"] == "ABC123"
    monkeypatch.setattr(config, "PMA_CODIGO_DE", "sku")
    assert _payload(dados())["codigo_pma"] == "X1"


def test_fonte_csv_le_decimais_e_status(tmp_path):
    arq = tmp_path / "d.csv"
    arq.write_text(
        "sku;codigo_fabricante;unitario;aliq_icms;ncm;frete;ipi;st_status;mva;confaz_status\n"
        "A1;F1;123,45;12;85176277;0,03;0,05;COM_ST;0,5;BASE_REDUZIDA\n"
        "A2;F2;10;4;85176277;3%;0;sem_st;;fora_da_lista\n"
        "A3;F3;10;4;85176277;0.03;0;;;\n",
        encoding="utf-8",
    )
    f = FonteCSV(arq, usar_confaz=False)   # aqui testa a leitura da coluna confaz_status; o coletor tem teste próprio abaixo
    a1 = f.obter("a1")
    assert a1.unitario == 123.45 and a1.perc_frete == 0.03 and a1.st.status == m.COM_ST and a1.st.mva == 0.5
    assert a1.confaz.status == m.BASE_REDUZIDA
    a2 = f.obter("A2")
    assert a2.perc_frete is None            # "3%" é ilegível de propósito
    assert a2.perc_ipi == 0.0 and a2.st.status == m.SEM_ST
    a3 = f.obter("A3")
    assert a3.st.status == m.ST_NAO_CONSULTADO and a3.confaz.status == m.CONFAZ_NAO_CONSULTADO
    assert f.obter("NAO_EXISTE") is None


def test_fonte_consulta_o_ncm_no_confaz_e_ignora_a_coluna(tmp_path):
    """Com o coletor ligado, o NCM manda: a coluna confaz_status do arquivo só vale para linha sem NCM."""
    arq = tmp_path / "d.csv"
    arq.write_text(
        "sku;codigo_fabricante;unitario;aliq_icms;ncm;frete;ipi;st_status;mva;confaz_status\n"
        "B1;F1;10;12;84248990;0,03;0;SEM_ST;;FORA_DA_LISTA\n"      # coluna diz FORA, mas o NCM está no Anexo I
        "B2;F2;10;12;73239900;0,03;0;SEM_ST;;BASE_REDUZIDA\n"      # coluna diz BASE, mas o NCM não está na lista
        "B3;F3;10;12;84672999;0,03;0;SEM_ST;;\n"                    # NCM só coberto por subposição -> CONDICIONAL
        "B4;F4;10;12;;0,03;0;SEM_ST;;BASE_REDUZIDA\n",              # sem NCM: vale a coluna
        encoding="utf-8",
    )
    f = FonteCSV(arq, usar_confaz=True)
    assert f.obter("B1").confaz.status == m.BASE_REDUZIDA and "Anexo I" in f.obter("B1").confaz.detalhe
    assert f.obter("B2").confaz.status == m.FORA_DA_LISTA
    assert f.obter("B3").confaz.status == m.CONDICIONAL
    assert f.obter("B4").confaz.status == m.BASE_REDUZIDA


def test_fonte_confaz_ausente_vira_falhou_e_nao_volta_para_a_coluna(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "CONFAZ_HTML", tmp_path / "nao_existe.html")
    arq = tmp_path / "d.csv"
    arq.write_text(
        "sku;codigo_fabricante;unitario;aliq_icms;ncm;frete;ipi;st_status;mva;confaz_status\n"
        "C1;F1;10;12;84248990;0,03;0;SEM_ST;;FORA_DA_LISTA\n",
        encoding="utf-8",
    )
    c1 = FonteCSV(arq, usar_confaz=True).obter("C1")
    assert c1.confaz.status == m.CONFAZ_FALHOU and "não encontrado" in c1.confaz.detalhe
