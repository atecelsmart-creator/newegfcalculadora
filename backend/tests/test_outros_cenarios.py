"""
Testes de validação dos 5 cenários restantes (Base Reduzida sem/com ST,
Importado sem/com ST, Nacional com ST).

Mesmo método da Etapa 6 (test_nacional_sem_st.py): CASOS TÉCNICOS
CONTROLADOS, preenchidos numa cópia da própria planilha
(CALCULO_MKTPLACE_SP.xlsx, aba "SHOPEE OPERACAO SP"), recalculados no
LibreOffice, com os valores de saída de cada célula copiados aqui como
gabarito. Nenhum valor foi inventado no Python.

Caso técnico SEM ST (mesmo da Etapa 6): D9=200 (preço venda), D10=100
(custo sem IPI), C11=5% (IPI), D18=15 (custo frete), D21=2 (custo caixa),
C13=0 (ST).

Caso técnico COM ST: idênticos, exceto C13=7% (ST) — usado só para validar
os cenários "com ST", que precisam de um perc_st != 0 pra exercitar a
fórmula.
"""
import pytest

from app.engine.shopee.nacional_sem_st import EntradasNacionalSemST
from app.engine.shopee.nacional_sem_st import calcular as calcular_nacional_sem_st
from app.engine.shopee.outros_cenarios import (
    EntradasComST,
    EntradasSemST,
    calcular_base_reduzida_com_st,
    calcular_base_reduzida_sem_st,
    calcular_importado_com_st,
    calcular_importado_sem_st,
    calcular_nacional_com_st,
)
from app.engine.shopee.solver import resolver_generico

PRECO_VENDA = 200.0

ENTRADAS_SEM_ST = EntradasSemST(
    custo_sem_ipi=100.0,
    perc_ipi=0.05,
    custo_frete=15.0,
    custo_caixa_papelao=2.0,
)

ENTRADAS_COM_ST = EntradasComST(
    custo_sem_ipi=100.0,
    perc_ipi=0.05,
    perc_st=0.07,
    custo_frete=15.0,
    custo_caixa_papelao=2.0,
)


# --- Cenários SEM ST (bloco N e S, linhas 3-14 da planilha recalculada) ---

def test_base_reduzida_sem_st_bate_com_a_planilha_recalculada():
    r = calcular_base_reduzida_sem_st(PRECO_VENDA, ENTRADAS_SEM_ST)
    assert r.custo_total_impostos == pytest.approx(10.3464765, abs=1e-6)   # N12
    assert r.lucro_real == pytest.approx(2.5335235, abs=1e-6)             # N14
    assert r.margem_real == pytest.approx(0.0126676175, abs=1e-6)         # O14


def test_importado_sem_st_bate_com_a_planilha_recalculada():
    r = calcular_importado_sem_st(PRECO_VENDA, ENTRADAS_SEM_ST)
    assert r.custo_total_impostos == pytest.approx(32.695025, abs=1e-6)   # S12
    assert r.lucro_real == pytest.approx(-19.815025, abs=1e-6)           # S14
    assert r.margem_real == pytest.approx(-0.099075125, abs=1e-6)        # T14


def test_base_reduzida_sem_st_origem_importado_troca_so_o_icms_entrada():
    """
    Regra de negócio (confirmada com o usuário, 2026-09): o campo origem
    também tem efeito no cenário Base Reduzida - sem ST, não só no com ST
    (correição de um bug em que o campo era aceito pelo schema mas nunca
    chegava a este cálculo). origem="importado" troca o ICMS entrada
    crédito de 8,80% pra 4,00% — e só isso (ICMS saída, PIS/COFINS, IR/CSLL
    continuam os mesmos do Base Reduzida).

    Gabarito calculado replicando fielmente custos_base.py +
    formulas_comuns.py fora do motor (mesmo método das demais validações
    deste arquivo), com o mesmo caso técnico SEM ST (PRECO_VENDA=200,
    custo=100, IPI=5%, frete=15, caixa=2) só trocando a alíquota de ICMS
    entrada pra 4,00%.
    """
    entradas_importado = EntradasSemST(
        custo_sem_ipi=100.0,
        perc_ipi=0.05,
        custo_frete=15.0,
        custo_caixa_papelao=2.0,
        origem="importado",
    )
    r = calcular_base_reduzida_sem_st(PRECO_VENDA, entradas_importado)
    assert r.custo_total_impostos == pytest.approx(13.2214365, abs=1e-6)
    assert r.lucro_real == pytest.approx(-0.3414365, abs=1e-6)
    assert r.margem_real == pytest.approx(-0.0017071825, abs=1e-6)


def test_base_reduzida_sem_st_origem_nao_afeta_nacional_nem_importado_puros():
    """O campo origem existe em EntradasNacionalSemST (compartilhada pelos 3
    cenários sem ST) por conveniência de schema — Nacional sem ST e
    Importado sem ST devem ignorá-lo completamente, mesmo padrão do campo
    origem em EntradasComST."""
    entradas_default = ENTRADAS_SEM_ST  # origem="nacional" (default)
    entradas_explicita_importado = EntradasSemST(
        custo_sem_ipi=100.0, perc_ipi=0.05, custo_frete=15.0,
        custo_caixa_papelao=2.0, origem="importado",
    )
    r_nacional_default = calcular_nacional_sem_st(PRECO_VENDA, entradas_default)
    r_nacional_com_origem_importado = calcular_nacional_sem_st(PRECO_VENDA, entradas_explicita_importado)
    assert r_nacional_default.lucro_real == pytest.approx(r_nacional_com_origem_importado.lucro_real, abs=1e-9)

    r_importado_default = calcular_importado_sem_st(PRECO_VENDA, entradas_default)
    r_importado_com_origem_importado = calcular_importado_sem_st(PRECO_VENDA, entradas_explicita_importado)
    assert r_importado_default.lucro_real == pytest.approx(r_importado_com_origem_importado.lucro_real, abs=1e-9)


# --- Cenários COM ST (média ponderada 45/55, linhas 18-30/36-48/52-64) ---

def test_nacional_com_st_bate_com_a_planilha_recalculada():
    r = calcular_nacional_com_st(PRECO_VENDA, ENTRADAS_COM_ST)
    assert r.custo_produto_total == pytest.approx(112.0, abs=1e-6)         # D14 (inclui ST=7)
    assert r.custo_total_impostos == pytest.approx(8.325928675, abs=1e-6)  # I27
    assert r.lucro_real == pytest.approx(-2.515928675, abs=1e-6)          # I29
    assert r.margem_real == pytest.approx(-0.012579643375, abs=1e-6)      # J29


def test_base_reduzida_com_st_bate_com_a_planilha_recalculada():
    # origem default = "nacional" -> ICMS entrada 8,80% no sub-bloco "fora de SP"
    r = calcular_base_reduzida_com_st(PRECO_VENDA, ENTRADAS_COM_ST)
    assert r.custo_total_impostos == pytest.approx(3.218327, abs=1e-6)     # N27
    assert r.lucro_real == pytest.approx(2.591673, abs=1e-6)              # N29
    assert r.margem_real == pytest.approx(0.012958365, abs=1e-6)          # O29


def test_base_reduzida_com_st_origem_importado_nao_afeta_o_resultado():
    """
    CORRIGIDO (2026-09, achado reportado pelo usuário comparando print da
    planilha x ferramenta em produção — caso real: preço R$187,11, custo
    sem IPI R$100, IPI 5,20%, ST 9,54%): ao contrário do que este teste
    afirmava antes, origem="importado" NÃO troca o ICMS entrada crédito do
    sub-bloco "venda p/ fora de SP" no cenário Base Reduzida - com ST. A
    planilha recalculada mantém 8,80% nesse sub-bloco independente da
    origem selecionada — o toggle só tem efeito real no Base Reduzida SEM
    ST (ver test_base_reduzida_sem_st_origem_importado_troca_so_o_icms_entrada
    acima). O bug antigo fazia a ferramenta divergir da planilha exatamente
    nesse caso (Base Reduzida - com ST + origem importado), com preço
    necessário ~R$191 em vez de ~R$187,11 pra margem de 5%.

    Gabarito: com origem sem efeito, o resultado com "importado" deve ser
    IDÊNTICO ao resultado default ("nacional") — mesmo princípio do teste
    de Nacional/Importado puros logo abaixo.
    """
    entradas_importado = EntradasComST(
        custo_sem_ipi=100.0,
        perc_ipi=0.05,
        perc_st=0.07,
        custo_frete=15.0,
        custo_caixa_papelao=2.0,
        origem="importado",
    )
    r_importado = calcular_base_reduzida_com_st(PRECO_VENDA, entradas_importado)
    r_nacional = calcular_base_reduzida_com_st(PRECO_VENDA, ENTRADAS_COM_ST)
    assert r_importado.custo_total_impostos == pytest.approx(r_nacional.custo_total_impostos, abs=1e-9)
    assert r_importado.lucro_real == pytest.approx(r_nacional.lucro_real, abs=1e-9)
    # Mesmo gabarito de test_base_reduzida_com_st_bate_com_a_planilha_recalculada (N27/N29/O29)
    assert r_importado.custo_total_impostos == pytest.approx(3.218327, abs=1e-6)
    assert r_importado.lucro_real == pytest.approx(2.591673, abs=1e-6)
    assert r_importado.margem_real == pytest.approx(0.012958365, abs=1e-6)


def test_base_reduzida_com_st_origem_nao_afeta_nacional_nem_importado_puros():
    """O campo origem só existe em EntradasComST por conveniência de schema —
    Nacional com ST e Importado com ST devem ignorá-lo completamente."""
    entradas_default = ENTRADAS_COM_ST  # origem="nacional" (default)
    entradas_explicita_importado = EntradasComST(
        custo_sem_ipi=100.0, perc_ipi=0.05, perc_st=0.07,
        custo_frete=15.0, custo_caixa_papelao=2.0, origem="importado",
    )
    r_nacional_default = calcular_nacional_com_st(PRECO_VENDA, entradas_default)
    r_nacional_com_origem_importado = calcular_nacional_com_st(PRECO_VENDA, entradas_explicita_importado)
    assert r_nacional_default.lucro_real == pytest.approx(r_nacional_com_origem_importado.lucro_real, abs=1e-9)

    r_importado_default = calcular_importado_com_st(PRECO_VENDA, entradas_default)
    r_importado_com_origem_importado = calcular_importado_com_st(PRECO_VENDA, entradas_explicita_importado)
    assert r_importado_default.lucro_real == pytest.approx(r_importado_com_origem_importado.lucro_real, abs=1e-9)


def test_importado_com_st_bate_com_a_planilha_recalculada():
    r = calcular_importado_com_st(PRECO_VENDA, ENTRADAS_COM_ST)
    assert r.custo_total_impostos == pytest.approx(15.313678675, abs=1e-6)  # S27
    assert r.lucro_real == pytest.approx(-9.503678675, abs=1e-6)           # S29
    assert r.margem_real == pytest.approx(-0.047518393375, abs=1e-6)       # T29


# --- Solver genérico (auto-consistência, mesmo princípio da Etapa 6) ---

def test_solver_generico_funciona_para_base_reduzida_sem_st():
    margem_desejada = 0.20
    resultado = resolver_generico(calcular_base_reduzida_sem_st, ENTRADAS_SEM_ST, margem_desejada)
    assert resultado.margem_real == pytest.approx(margem_desejada, abs=1e-4)


def test_solver_generico_funciona_para_importado_com_st():
    margem_desejada = 0.15
    resultado = resolver_generico(calcular_importado_com_st, ENTRADAS_COM_ST, margem_desejada)
    assert resultado.margem_real == pytest.approx(margem_desejada, abs=1e-4)


# --- CORRIGIDO (2026-09): ST agora reflete no custo do produto mesmo nos ---
# --- cenários "sem ST" — outros_cenarios.py estava hardcodando perc_st=0 ---
# --- e routes.py não repassava dados.perc_st pra EntradasNacionalSemST.  ---
def test_sem_st_agora_reflete_perc_st_no_custo_do_produto():
    """
    Antes da correção, _calcular_sem_st() ignorava entradas.perc_st e
    passava sempre 0.0 pra calcular_custos_base — então o ST digitado pelo
    usuário nunca entrava no custo do produto em Base Reduzida sem ST e
    Importado sem ST (só funcionava em Nacional sem ST). Este teste
    garante que os dois cenários agora somam o valor do ST no custo total,
    igual ao Nacional sem ST já fazia.
    """
    entradas_com_st_no_sem_st = EntradasSemST(
        custo_sem_ipi=100.0, perc_ipi=0.05, perc_st=0.07,
        custo_frete=15.0, custo_caixa_papelao=2.0,
    )
    r_com = calcular_base_reduzida_sem_st(PRECO_VENDA, entradas_com_st_no_sem_st)
    r_sem = calcular_base_reduzida_sem_st(PRECO_VENDA, ENTRADAS_SEM_ST)
    # 0.07 * custo_sem_ipi(100) = 7.00 a mais no custo do produto
    assert r_com.custo_produto_total == pytest.approx(r_sem.custo_produto_total + 7.0, abs=1e-6)
    assert r_com.custo_produto_total != r_sem.custo_produto_total
