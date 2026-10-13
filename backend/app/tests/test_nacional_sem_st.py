"""
Testes de validação do motor Nacional sem ST.

IMPORTANTE — sobre a origem dos números:
A planilha recebida (CALCULO_MKTPLACE_SP.xlsx) veio com os campos de entrada
(preço de venda, custo, IPI, frete, caixa) em branco. Não existe, portanto,
um caso real e completo pronto na planilha para copiar.

Os valores usados abaixo são CASOS TÉCNICOS CONTROLADOS, não dados reais de
operação: preço de venda R$200, custo R$100, IPI 5%, frete R$15, caixa R$2.
Não foram inventados no motor em Python — foram preenchidos numa cópia da
própria planilha (SHOPEE OPERACAO SP), recalculados pelo LibreOffice, e os
resultados de cada célula (I3:I14) foram copiados aqui como valor esperado.
Ou seja: o "gabarito" é a planilha, não o meu código.

Quando você tiver um caso real completo (preço, custo, IPI, frete, margem
alvo) para comparar, me passe que eu adiciono como teste adicional — sem
tirar este, que continua útil como regressão técnica do motor.
"""
import pytest

from app.engine.shopee.nacional_sem_st import EntradasNacionalSemST, calcular
from app.engine.shopee.solver import resolver_nacional_sem_st


# Caso técnico A — planilha SHOPEE OPERACAO SP com:
#   D9=200 (preço venda) D10=100 (custo) C11=5% (IPI) D18=15 (frete) D21=2 (caixa)
# Resultados lidos da planilha após recálculo no LibreOffice (bloco G3:J15):
ENTRADAS_CASO_A = EntradasNacionalSemST(
    custo_sem_ipi=100.0,
    perc_ipi=0.05,
    custo_frete=15.0,
    custo_caixa_papelao=2.0,
)
PRECO_VENDA_CASO_A = 200.0

ESPERADO_CASO_A = {
    "ipi": 5.0,                      # D11
    "custo_produto_total": 105.0,    # D14
    "mentoria": 2.0,                 # D15
    "custo_logistico": 7.0,          # D16
    "perda": 1.05,                   # D17
    "custo_shopee_perc": 0.14,       # C19 (200 > 79.99 -> 14%)
    "custo_shopee": 28.0,            # D19
    "taxa_shp_premio": 27.07,        # D20 (faixa 199.99< -> 26 + 1.07)
    "credito_presumido": 0.0,        # I3
    "icms_frete_ml_credito": 1.8,    # I4
    "icms_entrada_credito": 18.0,    # I5
    "icms_saida": 40.0,              # I6
    "pis_cofins_credito": 15.009975,  # I7
    "pis_cofins_debito": 14.8,       # I8
    "ir_cs_credito": 81.2158,        # I9
    "ir_cs_debito": 79.8353915,      # I10
    "ir_cs": 0.0,                    # I11
    "custo_total_impostos": 19.990025,  # I12
    "lucro_real": -7.11002499999999,    # I14
    "margem_real": -0.035550125,        # J14
}


def test_caso_tecnico_a_bate_com_a_planilha_recalculada():
    resultado = calcular(PRECO_VENDA_CASO_A, ENTRADAS_CASO_A)

    for campo, esperado in ESPERADO_CASO_A.items():
        obtido = getattr(resultado, campo)
        assert obtido == pytest.approx(esperado, abs=1e-6), (
            f"{campo}: esperado {esperado}, obtido {obtido}"
        )


def test_solver_encontra_preco_cuja_margem_bate_com_a_desejada():
    """
    Teste técnico de auto-consistência do solver (não vem da planilha, que
    não tem solver — o gabarito aqui é o próprio motor: se `calcular()` já
    foi validado no teste acima, o solver está correto se o preço que ele
    encontra, jogado de volta em `calcular()`, reproduz a margem pedida.
    """
    margem_desejada = 0.20
    resultado = resolver_nacional_sem_st(ENTRADAS_CASO_A, margem_desejada)

    assert resultado.margem_real == pytest.approx(margem_desejada, abs=1e-4)

    conferencia = calcular(resultado.preco_cheio, ENTRADAS_CASO_A)
    assert conferencia.margem_real == pytest.approx(margem_desejada, abs=1e-4)


def test_preco_promocional_recalcula_margem_e_lucro_apos_desconto():
    margem_desejada = 0.20
    desconto = 0.10

    resultado = resolver_nacional_sem_st(ENTRADAS_CASO_A, margem_desejada, desconto)

    assert resultado.preco_promocional == pytest.approx(
        resultado.preco_cheio * (1 - desconto)
    )
    # margem no promocional é MENOR que a margem desejada (mesmo custo, preço menor)
    assert resultado.margem_promocional < resultado.margem_real


def test_st_fica_travado_em_zero_no_cenario_sem_st():
    """EntradasNacionalSemST nem aceita perc_st — não existe como parâmetro."""
    import dataclasses

    campos = {f.name for f in dataclasses.fields(EntradasNacionalSemST)}
    assert "perc_st" not in campos
