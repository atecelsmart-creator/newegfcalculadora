"""
Testes do termômetro de confiança (app/qualidade/confianca.py).

ATENÇÃO: aqui NÃO há dados reais da planilha. O módulo de qualidade não calcula
preço — só lê entradas/resultado do motor. Por isso os testes usam um motor
FALSO e simples (apenas técnico, valores controlados), só para provar que cada
critério acende a cor certa. A validação dos preços em si continua nos testes
do motor contra a planilha.
"""
from dataclasses import dataclass
from types import SimpleNamespace

from app.qualidade.confianca import avaliar_confianca


@dataclass
class EntFalsa:
    custo_sem_ipi: float
    perc_frete: float = 0.0
    custo_frete: float = 0.0
    comissao_pct: float | None = 0.10


def motor_falso(preco, e):
    """Lucro = preço - custo*(1+frete%) - frete R$ - comissão*preço. Só técnico."""
    lucro = preco - e.custo_sem_ipi * (1 + e.perc_frete) - e.custo_frete - (e.comissao_pct or 0) * preco
    return SimpleNamespace(margem_real=lucro / preco)


def avaliar(ent, preco, margem, **kw):
    kw.setdefault("perc_frete", ent.perc_frete)
    return avaliar_confianca(
        calcular_fn=motor_falso, entradas=ent, preco_promocional=preco, margem_desejada=margem, **kw
    )


def niveis(r):
    return {m["criterio"]: m["nivel"] for m in r["motivos"]}


def test_verde_quando_tudo_coerente_e_margem_folgada():
    ent = EntFalsa(custo_sem_ipi=60, perc_frete=0.03)  # margem do motor falso: (100-61,8-10)/100 = 28,2%
    r = avaliar(ent, 100.0, 0.28)
    assert r["nivel"] == "verde"
    assert r["score"] >= 80
    assert r["margem_estressada"] > 0.28 * 0.5


def test_vermelho_quando_estresse_zera_margem():
    ent = EntFalsa(custo_sem_ipi=85, perc_frete=0.03)  # margem do motor falso: 2,45%; sob estresse fica negativa
    r = avaliar(ent, 100.0, 0.0245)
    assert r["nivel"] == "vermelho"
    assert niveis(r)["estresse"] == "risco"
    assert r["score"] <= 39


def test_amarelo_quando_pouca_folga():
    ent = EntFalsa(custo_sem_ipi=80, perc_frete=0.03)  # margem 7,6%; estressada ~2% (< 50% de 7,6%)
    r = avaliar(ent, 100.0, 0.076)
    assert niveis(r)["estresse"] == "atencao"
    assert r["nivel"] == "amarelo"
    assert r["score"] <= 79


def test_frete_digitado_x_tabela():
    ent = EntFalsa(custo_sem_ipi=60, perc_frete=0.03, custo_frete=20)
    ok = avaliar(ent, 200.0, 0.2, frete_digitado=20, frete_tabela=20)
    assert niveis(ok)["frete_tabela"] == "ok"
    amarelo = avaliar(ent, 200.0, 0.2, frete_digitado=22, frete_tabela=20)  # +10%
    assert niveis(amarelo)["frete_tabela"] == "atencao"
    vermelho = avaliar(ent, 200.0, 0.2, frete_digitado=26, frete_tabela=20)  # +30%
    assert niveis(vermelho)["frete_tabela"] == "risco"
    assert vermelho["nivel"] == "vermelho"
    sem_ref = avaliar(ent, 200.0, 0.2, frete_digitado=20, frete_tabela=None)
    assert niveis(sem_ref)["frete_tabela"] == "atencao"


def test_frete_compra_zerado_e_st_zerado():
    ent = EntFalsa(custo_sem_ipi=60, perc_frete=0.0)
    r = avaliar(ent, 100.0, 0.2, requer_st=True, perc_st=0.0)
    n = niveis(r)
    assert n["frete_compra"] == "atencao"
    assert n["st"] == "atencao"
    assert "st" not in niveis(avaliar(ent, 100.0, 0.2, requer_st=False))


def test_lucro_em_reais_no_promocional():
    ent = EntFalsa(custo_sem_ipi=60, perc_frete=0.03)
    assert niveis(avaliar(ent, 100.0, 0.28, lucro_promocional=51.51))["lucro"] == "ok"
    assert niveis(avaliar(ent, 100.0, 0.28, lucro_promocional=3.0))["lucro"] == "atencao"
    assert niveis(avaliar(ent, 100.0, 0.28, lucro_promocional=1.0))["lucro"] == "risco"
    r = avaliar(ent, 100.0, 0.28, lucro_promocional=-2.0)
    assert niveis(r)["lucro"] == "risco"
    assert r["nivel"] == "vermelho"


def test_faixas_de_margem_no_promocional():
    ent = EntFalsa(custo_sem_ipi=60, perc_frete=0.03)
    assert niveis(avaliar(ent, 100.0, 0.28, margem_promocional=0.20))["margem"] == "ok"
    assert niveis(avaliar(ent, 100.0, 0.28, margem_promocional=0.149999))["margem"] == "ok"  # 15% com folga do solver
    assert niveis(avaliar(ent, 100.0, 0.28, margem_promocional=0.10))["margem"] == "atencao"
    r = avaliar(ent, 100.0, 0.28, margem_promocional=0.05)
    assert niveis(r)["margem"] == "risco"
    assert r["nivel"] == "vermelho"


def test_peso_do_frete_e_margem_alta():
    ent = EntFalsa(custo_sem_ipi=20, perc_frete=0.03, custo_frete=45)
    r = avaliar(ent, 100.0, 0.5, frete_aplicado=45)
    n = niveis(r)
    assert n["frete_peso"] == "risco"
    assert n["margem_alvo"] == "atencao"


def test_nunca_levanta_excecao():
    def motor_quebrado(preco, e):
        raise RuntimeError("falha técnica simulada")

    ent = EntFalsa(custo_sem_ipi=60, perc_frete=0.03)
    r = avaliar_confianca(
        calcular_fn=motor_quebrado, entradas=ent, preco_promocional=100.0, margem_desejada=0.2, perc_frete=0.03
    )
    # o critério de estresse falha, os demais seguem
    assert r is not None
    assert "estresse" not in niveis(r)
