"""
Validação do motor do RJ contra CALCULO_MKTPLACE_RJ.xlsx.

Os valores esperados (lucro real e custo total de impostos) foram obtidos
recalculando a própria planilha no LibreOffice com as entradas de cada caso
(versão de 2026-10: mentoria de 1,5% também no ML/Magalu/Amazon; Amazon com
kg adicional e faixas abaixo de R$79 / acima de R$200).
As entradas são CASOS TÉCNICOS CONTROLADOS (não são dados reais de produto).
Tupla: (marketplace, tipo, preço, custo s/ IPI, IPI%, frete%, frete R$ ML,
caixa R$, lucro esperado, impostos esperados).
"""
import pytest

from app.engine.rj import config as rj_config
from app.engine.rj import frete as rj_frete
from app.engine.rj import motor
from app.engine.rj.solver import resolver_rj
from app.engine.shopee.solver import resolver_generico

CASOS = [
    ("tiktok", "nacional", 30, 40, 0.05, 0.03, 0.0, 0, -24.129736, -1.530264),
    ("tiktok", "base_reduzida", 30, 40, 0.05, 0.03, 0.0, 0, -21.697636, -3.962364),
    ("tiktok", "importado", 30, 40, 0.05, 0.03, 0.0, 0, -23.440036, -2.219964),
    ("shopee", "nacional", 60, 40, 0.05, 0.03, 0.0, 2.79, -10.234236, 5.434236),
    ("shopee", "base_reduzida", 60, 40, 0.05, 0.03, 0.0, 2.79, -4.208436, -0.591564),
    ("shopee", "importado", 60, 40, 0.05, 0.03, 0.0, 2.79, -5.950836, 1.150836),
    ("tiktok", "nacional", 60, 40, 0.05, 0.03, 0.0, 0, -7.744236, 5.434236),
    ("tiktok", "base_reduzida", 60, 40, 0.05, 0.03, 0.0, 0, -1.718436, -0.591564),
    ("tiktok", "importado", 60, 40, 0.05, 0.03, 0.0, 0, -3.460836, 1.150836),
    ("shopee", "nacional", 79.99, 40, 0.05, 0.03, 0.0, 2.79, 0.8172355, 10.0749145),
    ("shopee", "base_reduzida", 79.99, 40, 0.05, 0.03, 0.0, 2.79, 7.323968816, 3.568181184),
    ("shopee", "importado", 79.99, 40, 0.05, 0.03, 0.0, 2.79, 6.173984816, 4.718165184),
    ("shopee", "nacional", 150, 40, 0.05, 0.03, 0.0, 2.79, 24.92609424, 34.42390576),
    ("shopee", "base_reduzida", 150, 40, 0.05, 0.03, 0.0, 2.79, 36.01864824, 23.33135176),
    ("shopee", "importado", 150, 40, 0.05, 0.03, 0.0, 2.79, 34.86866424, 24.48133576),
    ("tiktok", "nacional", 250, 40, 0.05, 0.03, 0.0, 0, 68.42419424, 82.21580576),
    ("tiktok", "base_reduzida", 250, 40, 0.05, 0.03, 0.0, 0, 87.42288824, 63.21711176),
    ("tiktok", "importado", 250, 40, 0.05, 0.03, 0.0, 0, 86.27290424, 64.36709576),
    ("mercado_livre", "nacional", 110, 40, 0.05, 0.03, 16.85, 2.79, 13.42962364, 17.47037636),
    ("mercado_livre", "base_reduzida", 110, 40, 0.05, 0.03, 16.85, 2.79, 21.35972164, 9.54027836),
    ("mercado_livre", "importado", 110, 40, 0.05, 0.03, 16.85, 2.79, 20.20973764, 10.69026236),
    ("mercado_livre", "nacional", 35, 10, 0.0, 0.0, 6.85, 0, 5.7986044, 6.2763956),
    ("mercado_livre", "base_reduzida", 35, 10, 0.0, 0.0, 6.85, 0, 8.3740894, 3.7009106),
    ("mercado_livre", "importado", 35, 10, 0.0, 0.0, 6.85, 0, 8.0865934, 3.9884066),
]


@pytest.fixture(autouse=True)
def config_padrao(monkeypatch):
    """Usa os defaults da planilha, ignorando o que estiver salvo em data/*.json."""
    monkeypatch.setattr(rj_config, "obter", lambda mk: rj_config._DEFAULTS[mk])


@pytest.mark.parametrize("mk,tipo,preco,custo,ipi,frete,frete_r,caixa,lucro,impostos", CASOS)
def test_bate_com_planilha_rj(mk, tipo, preco, custo, ipi, frete, frete_r, caixa, lucro, impostos):
    r = motor.calcular(preco, motor.EntradasRJ(mk, tipo, custo, ipi, frete, frete_r, caixa))
    assert r.lucro_real == pytest.approx(lucro, abs=1e-6)
    assert r.custo_total_impostos == pytest.approx(impostos, abs=1e-6)


@pytest.mark.parametrize("mk", ["shopee", "mercado_livre", "tiktok"])
def test_solver_atinge_margem_desejada(mk):
    ent = motor.EntradasRJ(mk, "nacional", 40, 0.05, 0.03, 6.85 if mk == "mercado_livre" else 0.0)
    r = resolver_generico(motor.calcular, ent, 0.15, 0.0)
    assert r.margem_promocional == pytest.approx(0.15, abs=1e-4)


# ---- Magalu e Amazon DBA ----
# Casos reais de MAGALU e AMAZON DBA: lucro e impostos recalculados na própria planilha (LibreOffice).
# Entradas: custo 40, IPI 5%, frete 3%, caixa R$2,79; Magalu ">97%" + "Até 500gr"; Amazon "500 g a 1 kg" + "R$ 100 a 119,99".
# Fonte: CALCULO_MKTPLACE_RJ.xlsx, abas MAGALU e AMAZON DBA.

# Tupla: (marketplace, tipo, preço, frete R$ da Amazon, lucro esperado, impostos esperados).
CASOS_MAGALU_AMAZON = [
    ("magalu", "nacional", 60, 0, -9.534236, 5.434236),
    ("magalu", "base_reduzida", 60, 0, -3.508436, -0.591564),
    ("magalu", "importado", 60, 0, -5.250836, 1.150836),
    ("magalu", "nacional", 99.99, 0, -0.9608345, 11.1027845),
    ("magalu", "base_reduzida", 99.99, 0, 8.275670616, 1.866279384),
    ("magalu", "importado", 99.99, 0, 7.125686616, 3.016263384),
    ("magalu", "nacional", 150, 0, 21.40508004, 28.99491996),
    ("magalu", "base_reduzida", 150, 0, 32.49763404, 17.90236596),
    ("magalu", "importado", 150, 0, 31.34765004, 19.05234996),
    ("amazon_dba", "nacional", 60, 15.7, -21.122256, 2.272256),
    ("amazon_dba", "base_reduzida", 60, 15.7, -15.096456, -3.753544),
    ("amazon_dba", "importado", 60, 15.7, -16.838856, -2.011144),
    ("amazon_dba", "nacional", 99.99, 15.7, 3.5855655, 11.5559345),
    ("amazon_dba", "base_reduzida", 99.99, 15.7, 11.276294616, 3.865205384),
    ("amazon_dba", "importado", 99.99, 15.7, 10.126310616, 5.015189384),
    ("amazon_dba", "nacional", 150, 15.7, 25.89100104, 31.75899896),
    ("amazon_dba", "base_reduzida", 150, 15.7, 36.98355504, 20.66644496),
    ("amazon_dba", "importado", 150, 15.7, 35.83357104, 21.81642896),
]


@pytest.mark.parametrize("mk,tipo,preco,frete_r,lucro,impostos", CASOS_MAGALU_AMAZON)
def test_bate_com_planilha_rj_magalu_amazon(mk, tipo, preco, frete_r, lucro, impostos):
    ent = motor.EntradasRJ(mk, tipo, 40, 0.05, 0.03, frete_r, 2.79, magalu_peso="Até 500gr", magalu_nivel=">97%")
    r = motor.calcular(preco, ent)
    assert r.lucro_real == pytest.approx(lucro, abs=1e-6)
    assert r.custo_total_impostos == pytest.approx(impostos, abs=1e-6)


def test_frete_magalu_zero_ate_79_e_tabela_acima():
    assert rj_frete.frete_magalu(79.0, "Até 500gr", ">97%") == 0.0
    assert rj_frete.frete_magalu(79.01, "Até 500gr", ">97%") == pytest.approx(17.95)
    assert rj_frete.frete_magalu(120, "De 1kg a 2kg", "<92%") == pytest.approx(42.9)


def test_frete_amazon_tabela_e_sem_frete():
    assert rj_frete.frete_amazon("500 g a 1 kg", "R$ 100 a 119,99") == pytest.approx(15.7)
    assert rj_frete.frete_amazon("1 a 2 kg", rj_frete.SEM_FRETE_AMZ) == 0.0


def test_taxa_amazon_por_faixa_de_preco():
    cfg = rj_config._DEFAULTS["amazon_dba"]
    ent = motor.EntradasRJ("amazon_dba", "nacional", 40)
    assert motor._taxas_marketplace("amazon_dba", 20, cfg, ent)[1] == pytest.approx(4.5 + 1.35)
    assert motor._taxas_marketplace("amazon_dba", 40, cfg, ent)[1] == pytest.approx(6.5 + 1.35)
    assert motor._taxas_marketplace("amazon_dba", 90, cfg, ent)[1] == pytest.approx(6.75 + 1.35)


def test_solver_magalu_atinge_margem_desejada():
    ent = motor.EntradasRJ("magalu", "nacional", 40, 0.05, 0.03, 0.0, 0.0, magalu_peso="Até 500gr", magalu_nivel=">97%")
    r = resolver_rj(motor.calcular, ent, 0.15, 0.0)
    assert r.margem_promocional == pytest.approx(0.15, abs=1e-4)


def test_solver_amazon_atinge_margem_desejada():
    frete = rj_frete.frete_amazon("500 g a 1 kg", "R$ 100 a 119,99")
    ent = motor.EntradasRJ("amazon_dba", "nacional", 40, 0.05, 0.03, frete, 0.0)
    r = resolver_rj(motor.calcular, ent, 0.15, 0.0)
    assert r.margem_promocional == pytest.approx(0.15, abs=1e-4)


# ---- Amazon DBA: KG ADICIONAL (H2 faixa, H3 valor/kg, H4 qtd kg, H5 = H3*H4; D15 = C15 + H5) ----
# Entradas: custo 40, IPI 5%, frete 3%, caixa R$2,79 (mesmas dos casos acima). Valores da própria planilha.
# Tupla: (tipo, preço, frete base R$, faixa do kg adicional, qtd kg, lucro esperado, impostos esperados).
CASOS_AMAZON_KG_ADICIONAL = [
    ("nacional", 60, 15.7, "R$ 100 a 119,99", 2, -27.222256, 2.272256),
    ("base_reduzida", 60, 15.7, "R$ 100 a 119,99", 2, -21.196456, -3.753544),
    ("importado", 60, 15.7, "R$ 100 a 119,99", 2, -22.938856, -2.011144),
    ("nacional", 99.99, 15.7, "R$ 100 a 119,99", 2, -2.5144345, 11.5559345),
    ("base_reduzida", 99.99, 15.7, "R$ 100 a 119,99", 2, 5.176294616, 3.865205384),
    ("importado", 99.99, 15.7, "R$ 100 a 119,99", 2, 4.026310616, 5.015189384),
    ("nacional", 150, 15.7, "R$ 100 a 119,99", 2, 19.79100104, 31.75899896),
    ("base_reduzida", 150, 15.7, "R$ 100 a 119,99", 2, 30.88355504, 20.66644496),
    ("importado", 150, 15.7, "R$ 100 a 119,99", 2, 29.73357104, 21.81642896),
    ("nacional", 250, 27.95, "Acima R$200", 3, 50.93242004, 67.46757996),
    ("base_reduzida", 250, 27.95, "Acima R$200", 3, 69.93111404, 48.46888596),
    ("importado", 250, 27.95, "Acima R$200", 3, 68.78113004, 49.61886996),
]


@pytest.mark.parametrize("tipo,preco,frete_r,faixa,kg,lucro,impostos", CASOS_AMAZON_KG_ADICIONAL)
def test_bate_com_planilha_amazon_kg_adicional(tipo, preco, frete_r, faixa, kg, lucro, impostos):
    ent = motor.EntradasRJ("amazon_dba", tipo, 40, 0.05, 0.03, frete_r, 2.79,
                           frete_adicional=rj_frete.frete_adicional_amazon(faixa, kg))
    r = motor.calcular(preco, ent)
    assert r.lucro_real == pytest.approx(lucro, abs=1e-6)
    assert r.custo_total_impostos == pytest.approx(impostos, abs=1e-6)


def test_kg_adicional_so_desconta_do_lucro_e_nao_mexe_nos_impostos():
    base = motor.EntradasRJ("amazon_dba", "nacional", 40, 0.05, 0.03, 15.7, 2.79)
    com = motor.EntradasRJ("amazon_dba", "nacional", 40, 0.05, 0.03, 15.7, 2.79, frete_adicional=6.10)
    r0, r1 = motor.calcular(99.99, base), motor.calcular(99.99, com)
    assert r1.custo_total_impostos == pytest.approx(r0.custo_total_impostos, abs=1e-9)   # créditos usam só o frete base (C15)
    assert r1.lucro_real == pytest.approx(r0.lucro_real - 6.10, abs=1e-9)                # D15 = C15 + H5
    assert r1.frete_aplicado == pytest.approx(15.7) and r1.frete_adicional == pytest.approx(6.10)


def test_kg_adicional_e_ignorado_fora_da_amazon():
    base = motor.EntradasRJ("shopee", "nacional", 40, 0.05, 0.03, 0.0, 2.79)
    com = motor.EntradasRJ("shopee", "nacional", 40, 0.05, 0.03, 0.0, 2.79, frete_adicional=9.99)
    assert motor.calcular(80, com).lucro_real == pytest.approx(motor.calcular(80, base).lucro_real)


def test_frete_adicional_amazon_regras_da_planilha():
    assert rj_frete.frete_adicional_amazon("R$ 100 a 119,99", 2) == pytest.approx(6.10)      # 3,05 x 2
    assert rj_frete.frete_adicional_amazon("R$ 150 a 199,99", 2.5) == pytest.approx(8.75)    # 3,50 x 2,5
    assert rj_frete.frete_adicional_amazon("Acima R$200", 3) == pytest.approx(12.0)          # 4,00 x 3
    assert rj_frete.frete_adicional_amazon(None, 3) == 0.0       # H3 = "" -> H5 = 0
    assert rj_frete.frete_adicional_amazon("", 3) == 0.0
    assert rj_frete.frete_adicional_amazon("R$ 150 a 199,99", 0) == 0.0
    with pytest.raises(ValueError):
        rj_frete.frete_adicional_amazon("R$ 10 a 20", 1)


def test_frete_amazon_novas_faixas_da_planilha():
    assert rj_frete.frete_amazon("0 a 250 g", "R$ 0 a 29,99") == pytest.approx(4.5)
    assert rj_frete.frete_amazon("0 a 250 g", "R$ 50 a 78,99") == pytest.approx(6.75)
    assert rj_frete.frete_amazon("1 a 2 kg", "R$ 0 a 29,99") == 0.0          # célula vazia na planilha -> VLOOKUP devolve 0
    assert rj_frete.frete_amazon("500 g a 1 kg", "Acima R$200") == pytest.approx(21.95)
    assert rj_frete.frete_amazon("5 a 6 kg", "Acima R$200") == pytest.approx(36.95)
    assert "Kg adicional" not in rj_frete.PESOS_AMZ                          # não é opção do dropdown de peso (C2 = A2:A13)


def test_solver_amazon_com_kg_adicional_atinge_margem_desejada():
    frete = rj_frete.frete_amazon("500 g a 1 kg", "R$ 100 a 119,99")
    ent = motor.EntradasRJ("amazon_dba", "nacional", 40, 0.05, 0.03, frete, 0.0,
                           frete_adicional=rj_frete.frete_adicional_amazon("R$ 100 a 119,99", 2))
    r = resolver_rj(motor.calcular, ent, 0.15, 0.0)
    assert r.margem_promocional == pytest.approx(0.15, abs=1e-4)
