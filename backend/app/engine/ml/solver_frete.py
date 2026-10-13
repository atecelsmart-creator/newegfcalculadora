"""
Solver do Mercado Livre com FRETE DEPENDENTE DO PREÇO (faixa de valor
automática).

Por que não reaproveitar a bisseção de app.engine.shopee.solver direto:
na tabela "BASE FRETE MELI" o frete SALTA ao cruzar o limite de uma faixa
(ex.: 0,3-0,5 kg: R$ 8,25 até R$ 78,99 e R$ 13,85 a partir de R$ 79,00).
Com isso a margem em função do preço deixa de ser monotônica — sobe dentro
de cada faixa, mas cai de repente na fronteira — e uma bisseção sobre a
curva inteira pode convergir pro lugar errado.

Solução: dentro de UMA faixa o frete é fixo, a curva volta a ser monotônica
e o solver existente resolve sem alteração. Então resolvemos faixa por
faixa, da mais barata pra mais cara, e ficamos com o MENOR preço válido:
  - solução dentro da faixa      -> é ela;
  - solução ABAIXO do limite inf. -> o próprio limite inferior já tem margem
    >= a desejada (a margem cresce com o preço dentro da faixa), então o
    preço é o limite inferior;
  - solução ACIMA do limite sup.  -> essa faixa não fecha, tenta a próxima.

Nada aqui mexe no motor da Shopee/TikTok: só importa o solver genérico.
"""
from dataclasses import replace

from app.engine.ml import frete as ml_frete
from app.engine.shopee.solver import (
    ResultadoCompleto,
    encontrar_preco_generico,
)


def resolver_com_faixa_automatica(
    calculator,
    entradas,
    peso: str,
    margem_desejada: float,
    desconto_promocional: float = 0.0,
) -> tuple[ResultadoCompleto, str, float]:
    """
    Devolve (resultado, faixa_aplicada, frete_aplicado) — faixa e frete
    valem pro PREÇO PROMOCIONAL (o preço realmente cobrado do cliente).
    `entradas.custo_frete` é ignorado (sobrescrito pelo lookup por preço).
    """
    def calcular_por_preco(preco: float, ent):
        return calculator.calcular(
            preco, replace(ent, custo_frete=ml_frete.obter_frete_por_preco(peso, preco))
        )

    n = len(ml_frete.FAIXAS_VALOR)
    resultado_promocional = None
    for k in range(n):
        lo = ml_frete.LIMITES_INFERIORES[k]
        hi = ml_frete.LIMITES_INFERIORES[k + 1] if k + 1 < n else float("inf")
        ent_k = replace(entradas, custo_frete=ml_frete.obter_frete(peso, ml_frete.FAIXAS_VALOR[k]))
        try:
            achado = encontrar_preco_generico(
                calculator.calcular, ent_k, margem_desejada, entradas.custo_sem_ipi
            )
        except ValueError:
            continue  # margem inalcançável com o frete dessa faixa
        p = achado.preco_venda
        if p >= hi:
            continue
        if p < lo:
            # margem já >= desejada no limite inferior da faixa
            resultado_promocional = calcular_por_preco(lo, entradas)
        else:
            resultado_promocional = calcular_por_preco(p, entradas)
        break

    if resultado_promocional is None:
        raise ValueError(
            "Margem desejada não é atingível em nenhuma faixa de valor do frete — "
            "revise os parâmetros de entrada."
        )

    preco_promocional = resultado_promocional.preco_venda
    fator = 1 - desconto_promocional
    preco_cheio = preco_promocional / fator if fator > 0 else preco_promocional
    # Informativo (como na Shopee): o que aconteceria SE a venda fosse pelo
    # preço cheio — inclusive com a faixa/frete que esse preço teria.
    resultado_cheio = calcular_por_preco(preco_cheio, entradas)

    resultado = ResultadoCompleto(
        preco_necessario=preco_promocional,
        preco_cheio=preco_cheio,
        preco_promocional=preco_promocional,
        lucro_real=resultado_cheio.lucro_real,
        margem_real=resultado_cheio.margem_real,
        lucro_promocional=resultado_promocional.lucro_real,
        margem_promocional=resultado_promocional.margem_real,
        custo_produto_total=resultado_promocional.custo_produto_total,
        custo_total_impostos=resultado_promocional.custo_total_impostos,
    )
    return (
        resultado,
        ml_frete.faixa_por_preco(preco_promocional),
        ml_frete.obter_frete_por_preco(peso, preco_promocional),
    )
