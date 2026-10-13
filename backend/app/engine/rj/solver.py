"""
Solver do RJ. Igual ao de SP (bisseção sobre a margem), com um ajuste: no
Magalu o frete some em preço <= R$79 e aparece acima disso (salto na
curva de margem), então a busca roda em dois trechos — primeiro até R$79,
depois acima — para nunca convergir em cima do salto.
"""
from app.engine.rj.frete import LIMITE_FRETE_MAGALU
from app.engine.shopee.solver import ResultadoCompleto


def _bisseccao(fn, ent, margem, lo, hi, tol=1e-6, max_iter=200):
    if fn(lo, ent).margem_real >= margem:
        return fn(lo, ent)
    if fn(hi, ent).margem_real < margem:
        return None
    r = fn((lo + hi) / 2, ent)
    for _ in range(max_iter):
        mid = (lo + hi) / 2
        r = fn(mid, ent)
        if abs(r.margem_real - margem) < tol:
            return r
        if r.margem_real < margem:
            lo = mid
        else:
            hi = mid
    return r


def resolver_rj(calcular_fn, ent, margem_desejada: float, desconto_promocional: float = 0.0) -> ResultadoCompleto:
    lo, hi = ent.custo_sem_ipi * 1.001, ent.custo_sem_ipi * 1000
    promo = None
    if ent.marketplace == "magalu":
        if lo < LIMITE_FRETE_MAGALU:
            promo = _bisseccao(calcular_fn, ent, margem_desejada, lo, LIMITE_FRETE_MAGALU)
        if promo is None:
            promo = _bisseccao(calcular_fn, ent, margem_desejada, max(lo, LIMITE_FRETE_MAGALU + 0.01), hi)
    else:
        promo = _bisseccao(calcular_fn, ent, margem_desejada, lo, hi)
    if promo is None:
        raise ValueError("Margem desejada não é atingível nem com preço 1000x o custo — revise os parâmetros de entrada.")

    fator = 1 - desconto_promocional
    preco_cheio = promo.preco_venda / fator if fator > 0 else promo.preco_venda
    cheio = calcular_fn(preco_cheio, ent)
    return ResultadoCompleto(
        preco_necessario=promo.preco_venda,
        preco_cheio=preco_cheio,
        preco_promocional=promo.preco_venda,
        lucro_real=cheio.lucro_real,
        margem_real=cheio.margem_real,
        lucro_promocional=promo.lucro_real,
        margem_promocional=promo.margem_real,
        custo_produto_total=promo.custo_produto_total,
        custo_total_impostos=promo.custo_total_impostos,
    )
