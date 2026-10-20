"""Robô no Mercado Livre: dados extras (comissão e frete), validação, payload, conferência da faixa de frete e relatório."""
import pytest

from rpa import cenario, cliente_api, config, main, ml_frete, relatorio, validador
from rpa import modelos as m
from rpa.fonte_csv import FonteCSV
from rpa.tests.fabrica import dados


def ml(**kw) -> m.DadosProduto:
    """Produto válido do Mercado Livre (frete já conhecido em R$). Sobrescreva o que o teste precisar."""
    base = dict(ml_comissao=0.12, frete_ml=8.15)
    base.update(kw)
    return dados(**base)


@pytest.fixture
def mercado_livre(monkeypatch):
    monkeypatch.setattr(config, "MARKETPLACE", "mercado_livre")
    monkeypatch.setattr(config, "ESTADO", "SP")


# ---------------------------------------------------------------- tabela de frete (conversão de rótulos)
@pytest.mark.parametrize("texto, esperado", [
    ("De 0,5 a 1 kg", "De 0,5 a 1 kg"),
    ("0,5 a 1 kg", "De 0,5 a 1 kg"),
    ("de 0,5 a 1 KG", "De 0,5 a 1 kg"),
    ("Até 0,3 kg", "Até 0,3 kg"),
    ("ate 0,3 kg", "Até 0,3 kg"),
    ("Mais de 150 kg", "Mais de 150 kg"),
])
def test_peso_aceita_variacoes_e_devolve_o_rotulo_da_tabela(texto, esperado):
    assert ml_frete.canonico_peso(texto) == esperado


@pytest.mark.parametrize("texto, esperado", [
    ("49 a R$ 78,99", "49 a R$ 78,99"),
    ("49 a 78,99", "49 a R$ 78,99"),
    ("0 a 18,99", "0 a R$ 18,99**"),
    ("A partir de 200", "A partir de 200"),
])
def test_faixa_aceita_variacoes_e_devolve_o_rotulo_da_tabela(texto, esperado):
    assert ml_frete.canonico_faixa(texto) == esperado


@pytest.mark.parametrize("texto", [None, "", "  ", "De 0,4 a 1 kg", "50 a 60", "auto"])
def test_rotulo_que_nao_existe_vira_none(texto):
    assert ml_frete.canonico_peso(texto) is None
    assert ml_frete.canonico_faixa(texto) is None


@pytest.mark.parametrize("preco, faixa", [
    (0.0, "0 a R$ 18,99**"), (18.99, "0 a R$ 18,99**"), (19.0, "19 a R$ 48,99"), (48.99, "19 a R$ 48,99"),
    (49.0, "49 a R$ 78,99"), (79.0, "79 a R$ 99,99"), (119.99, "100 a R$ 119,99"), (200.0, "A partir de 200"), (999.0, "A partir de 200"),
])
def test_faixa_do_preco(preco, faixa):
    assert ml_frete.faixa_do_preco(preco) == faixa


# ---------------------------------------------------------------- validador
def test_ml_valido_com_frete_em_reais():
    assert validador.validar(ml(), "SP", "mercado_livre") == []


def test_ml_valido_com_peso_e_faixa():
    d = ml(frete_ml=None, ml_peso="0,5 a 1 kg", ml_faixa_valor="49 a 78,99")
    assert validador.validar(d, "SP", "mercado_livre") == []
    assert validador.validar(d, "RJ", "mercado_livre") == []


def test_outros_marketplaces_nao_exigem_dados_do_ml():
    assert validador.validar(dados(), "SP", "shopee") == []
    assert validador.validar(dados(), "SP", "tiktok") == []
    assert validador.validar(dados(), "SP") == []


@pytest.mark.parametrize("campo, valor", [
    ("ml_comissao", None),
    ("ml_comissao", 0),
    ("ml_comissao", 12),        # 12 em vez de 0.12: erro de unidade
])
def test_comissao_invalida_gera_motivo(campo, valor):
    assert validador.validar(ml(**{campo: valor}), "SP", "mercado_livre")


def test_sem_frete_nenhum_gera_motivo():
    motivos = validador.validar(ml(frete_ml=None), "SP", "mercado_livre")
    assert any("Frete do Mercado Livre ausente" in x for x in motivos)


def test_frete_negativo_gera_motivo():
    assert validador.validar(ml(frete_ml=-1), "SP", "mercado_livre")


@pytest.mark.parametrize("peso, faixa", [
    ("0,5 a 1 kg", None),               # falta a faixa
    (None, "49 a 78,99"),               # falta o peso
    ("De 0,4 a 1 kg", "49 a 78,99"),    # peso fora da tabela
    ("0,5 a 1 kg", "50 a 60"),          # faixa fora da tabela
])
def test_peso_e_faixa_incompletos_ou_invalidos(peso, faixa):
    assert validador.validar(ml(frete_ml=None, ml_peso=peso, ml_faixa_valor=faixa), "SP", "mercado_livre")


def test_frete_em_reais_dispensa_peso_e_faixa_invalidos():
    assert validador.validar(ml(ml_peso="lixo", ml_faixa_valor="lixo"), "SP", "mercado_livre") == []


# ---------------------------------------------------------------- fonte de dados (CSV)
def test_fonte_le_as_colunas_do_ml(tmp_path):
    arq = tmp_path / "d.csv"
    arq.write_text(
        "sku;codigo_fabricante;unitario;aliq_icms;ncm;frete;ipi;st_status;mva;ml_comissao;frete_ml;ml_peso;ml_faixa_valor\n"
        "A1;C1;100,00;12;85176277;0,03;0,05;SEM_ST;;0,14;;0,5 a 1 kg;49 a 78,99\n"
        "A2;C2;100,00;12;85176277;0,03;0,05;SEM_ST;;0,12;8,15;;\n",
        encoding="utf-8")
    fonte = FonteCSV(arq, usar_confaz=False)
    a1, a2 = fonte.obter("A1"), fonte.obter("A2")
    assert (a1.ml_comissao, a1.ml_peso, a1.ml_faixa_valor, a1.frete_ml) == (0.14, "0,5 a 1 kg", "49 a 78,99", None)
    assert (a2.ml_comissao, a2.frete_ml, a2.ml_peso, a2.ml_faixa_valor) == (0.12, 8.15, None, None)


def test_fonte_sem_colunas_do_ml_deixa_vazio(tmp_path):
    arq = tmp_path / "d.csv"
    arq.write_text("sku;codigo_fabricante;unitario;aliq_icms;ncm;frete;ipi\nA1;C1;100;12;85176277;0,03;0,05\n", encoding="utf-8")
    d = FonteCSV(arq, usar_confaz=False).obter("A1")
    assert (d.ml_comissao, d.ml_peso, d.ml_faixa_valor, d.frete_ml) == (None, None, None, None)


# ---------------------------------------------------------------- payload da calculadora
def _payload(d):
    return cliente_api.montar_payload(d, cenario.definir_cenario(d, config.ESTADO), 0.15, 0.10)


def test_payload_ml_com_frete_em_reais(mercado_livre):
    p = _payload(ml(frete_ml=8.15, ml_comissao=0.14))
    assert p["marketplace"] == "mercado_livre"
    assert p["ml_comissao_pct"] == 0.14
    assert p["custo_frete"] == 8.15
    assert "ml_peso" not in p and "ml_faixa_valor" not in p


def test_payload_ml_com_peso_e_faixa_usa_os_rotulos_da_tabela(mercado_livre):
    p = _payload(ml(frete_ml=None, ml_peso="0,5 a 1 kg", ml_faixa_valor="49 a 78,99"))
    assert p["ml_peso"] == "De 0,5 a 1 kg"
    assert p["ml_faixa_valor"] == "49 a R$ 78,99"
    assert "custo_frete" not in p


def test_payload_dos_outros_marketplaces_nao_leva_campos_do_ml(monkeypatch):
    monkeypatch.setattr(config, "MARKETPLACE", "shopee")
    p = _payload(dados())
    assert not any(k.startswith("ml_") for k in p) and "custo_frete" not in p


# ---------------------------------------------------------------- conferência da faixa do frete
def test_faixa_certa_passa(mercado_livre):
    d = ml(frete_ml=None, ml_peso="0,5 a 1 kg", ml_faixa_valor="100 a 119,99")
    assert main._conferir_faixa_frete_ml(d, {"preco_promocional": 110.0}) == ""


def test_faixa_errada_vira_motivo_com_a_faixa_certa(mercado_livre):
    d = ml(frete_ml=None, ml_peso="0,5 a 1 kg", ml_faixa_valor="49 a 78,99")
    motivo = main._conferir_faixa_frete_ml(d, {"preco_promocional": 110.0})
    assert "100 a R$ 119,99" in motivo and "49 a R$ 78,99" in motivo


def test_frete_em_reais_dispensa_a_conferencia_de_faixa(mercado_livre):
    assert main._conferir_faixa_frete_ml(ml(frete_ml=8.15), {"preco_promocional": 110.0}) == ""


# ---------------------------------------------------------------- fluxo completo de um SKU (calculadora simulada)
class _Fonte:
    def __init__(self, d):
        self._d = d

    def obter(self, sku):
        return self._d


def _resultado(promo=110.0, **extra):
    r = {"preco_cheio": promo / 0.9, "preco_promocional": promo, "margem_promocional": 0.15, "pma": None,
         "ml_frete_aplicado": 8.15, "ml_faixa_valor_aplicada": "100 a R$ 119,99"}
    r.update(extra)
    return r


def test_sku_ml_ok_guarda_dados_e_frete_aplicado(mercado_livre, monkeypatch):
    monkeypatch.setattr(cliente_api, "calcular", lambda payload: _resultado())
    linha = main.processar_sku("X1", _Fonte(ml()), "", 0.15, 0.10, False)
    assert linha["status"] == "OK", linha["motivo"]
    assert linha["ml_comissao"] == 0.12 and linha["frete_ml_aplicado"] == 8.15
    assert linha["faixa_frete_aplicada"] == "100 a R$ 119,99"


def test_sku_ml_sem_comissao_vai_para_revisar_sem_calcular(mercado_livre, monkeypatch):
    chamou = []
    monkeypatch.setattr(cliente_api, "calcular", lambda payload: chamou.append(payload) or _resultado())
    linha = main.processar_sku("X1", _Fonte(ml(ml_comissao=None)), "", 0.15, 0.10, False)
    assert linha["status"] == "REVISAR" and "Comissão do Mercado Livre ausente" in linha["motivo"]
    assert not chamou


def test_sku_ml_com_faixa_errada_vira_revisar_e_nao_grava(mercado_livre, monkeypatch):
    monkeypatch.setattr(cliente_api, "calcular", lambda payload: _resultado(promo=110.0))
    gravou = []
    d = ml(frete_ml=None, ml_peso="0,5 a 1 kg", ml_faixa_valor="49 a 78,99")
    linha = main.processar_sku("X1", _Fonte(d), "", 0.15, 0.10, True, gravador=lambda *a: gravou.append(a) or {"conferencia_ok": True})
    assert linha["status"] == "REVISAR" and "Faixa de frete do ML" in linha["motivo"]
    assert not gravou and not linha["gravado"]


def test_sku_ml_ok_grava_cheio_e_promocional(mercado_livre, monkeypatch):
    monkeypatch.setattr(cliente_api, "calcular", lambda payload: _resultado(promo=110.0))
    gravou = []
    linha = main.processar_sku("X1", _Fonte(ml()), "", 0.15, 0.10, True,
                               gravador=lambda sku, cheio, promo: gravou.append((sku, cheio, promo)) or {"conferencia_ok": True})
    assert linha["status"] == "OK" and linha["gravado"]
    assert gravou == [("X1", pytest.approx(110.0 / 0.9), 110.0)]


# ---------------------------------------------------------------- relatório
def test_relatorio_so_tem_colunas_do_ml_quando_o_lote_e_do_ml(tmp_path):
    base = {"sku": "A", "status": "OK", "motivo": "", "gravado": False}
    sem = relatorio.gerar([base], tmp_path / "a", "shopee_sp")
    com = relatorio.gerar([{**base, "ml_comissao": 0.12, "frete_ml_aplicado": 8.15}], tmp_path / "b", "mercado_livre_sp")
    cab_sem = sem.with_suffix(".csv").read_text(encoding="utf-8-sig").splitlines()[0]
    cab_com = com.with_suffix(".csv").read_text(encoding="utf-8-sig").splitlines()[0]
    assert "Comissão ML" not in cab_sem
    assert "Comissão ML" in cab_com and "Frete ML aplicado (R$)" in cab_com


# ---------------------------------------------------------------- detalhes (popup da linha)
def _itens(d, res, estado):
    pytest.importorskip("pydantic")   # os detalhes leem as constantes do motor do backend
    from rpa import detalhes
    dec = cenario.definir_cenario(d, estado)
    return detalhes.montar(d, dec, res, 0.15, 0.10)["itens"]


@pytest.mark.parametrize("estado", ["SP", "RJ"])
def test_detalhes_ml_mostram_comissao_frete_e_conferem_a_faixa(mercado_livre, monkeypatch, estado):
    monkeypatch.setattr(config, "ESTADO", estado)
    d = ml(frete_ml=None, ml_peso="0,5 a 1 kg", ml_faixa_valor="100 a 119,99", ml_comissao=0.14)
    itens = _itens(d, _resultado(promo=110.0), estado)
    por = {(i["g"], i["r"]): i for i in itens}
    assert por[("Taxas Mercado Livre", "Comissão")]["v"] == "14,00%"
    assert por[("Taxas Mercado Livre", "Frete do ML")]["v"] == "R$ 8,15"
    faixa = por[("Taxas Mercado Livre", "Faixa de valor (frete ML)")]
    assert faixa["ok"] is True


def test_detalhes_ml_faixa_que_nao_confere_pede_atencao(mercado_livre):
    d = ml(frete_ml=None, ml_peso="0,5 a 1 kg", ml_faixa_valor="49 a 78,99")
    itens = _itens(d, _resultado(promo=110.0, ml_faixa_valor_aplicada="49 a R$ 78,99"), "SP")
    faixa = next(i for i in itens if i["r"] == "Faixa de valor (frete ML)")
    assert faixa["ok"] is False and "100 a R$ 119,99" in faixa["n"]
