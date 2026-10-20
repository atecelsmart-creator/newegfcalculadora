"""
Busca do preço de venda que atinge a margem desejada.

Como as faixas da taxa Shopee (C19) e da Taxa SHP+Prêmio (D20) dependem do
próprio preço de venda, não existe fórmula fechada — o preço precisa ser
encontrado por busca numérica (ex: bisseção) sobre a função de cálculo do
cenário escolhido.

Decisão registrada (CORRIGIDA em 2026-09 — a versão anterior deste
comentário estava com a regra invertida, veja resolver_generico abaixo):
a margem_desejada vale sobre o PREÇO PROMOCIONAL — é esse o valor que
realmente entra no caixa na venda (é o que a aba "SHOPEE OPERACAO SP" da
planilha resolve em D9/J14). O preço cheio é só o valor inflado mostrado
riscado no "de/por" da Shopee — nunca é cobrado de verdade — e é obtido
DIVIDINDO o preço promocional pelo fator de desconto (não multiplicando).

`encontrar_preco_generico` funciona para qualquer um dos 6 cenários (recebe
a função `calcular` do cenário como parâmetro); `resolver_nacional_sem_st`
é mantido por compatibilidade com os testes já existentes da Etapa 6.
"""
from dataclasses import dataclass
from typing import Callable, TypeVar

from app.engine.shopee.nacional_sem_st import EntradasNacionalSemST, ResultadoCalculo, calcular

R = TypeVar("R")  # qualquer dataclass de resultado que tenha .margem_real e .preco_venda


def encontrar_preco_generico(
    calcular_fn: Callable[..., R],
    entradas,
    margem_desejada: float,
    custo_sem_ipi: float,
    tolerancia: float = 1e-6,
    max_iter: int = 200,
) -> R:
    """
    Busca por bisseção o preco_venda cuja margem_real bate com margem_desejada,
    para qualquer cenário — calcular_fn(preco_venda, entradas) -> resultado
    (resultado precisa ter atributo `margem_real`).

    Premissa (não vem da planilha, é decisão de implementação do solver):
    margem_real cresce de forma monotônica com preco_venda — custos fixos
    diluem e as faixas de taxa da Shopee só diminuem conforme o preço sobe.
    Se essa premissa se mostrar falsa em algum caso real, a bisseção pode
    convergir errado — sinalizar se acontecer.
    """
    lo = custo_sem_ipi * 1.001
    hi = custo_sem_ipi * 1000

    margem_lo = calcular_fn(lo, entradas).margem_real
    margem_hi = calcular_fn(hi, entradas).margem_real

    if margem_lo >= margem_desejada:
        return calcular_fn(lo, entradas)
    if margem_hi < margem_desejada:
        raise ValueError(
            "Margem desejada não é atingível nem com preço 1000x o custo — "
            "revise os parâmetros de entrada."
        )

    resultado = calcular_fn((lo + hi) / 2, entradas)
    for _ in range(max_iter):
        mid = (lo + hi) / 2
        resultado = calcular_fn(mid, entradas)
        if abs(resultado.margem_real - margem_desejada) < tolerancia:
            return resultado
        if resultado.margem_real < margem_desejada:
            lo = mid
        else:
            hi = mid
    return resultado


def encontrar_preco_necessario(
    entradas: EntradasNacionalSemST,
    margem_desejada: float,
    tolerancia: float = 1e-6,
    max_iter: int = 200,
) -> ResultadoCalculo:
    """Mantido por compatibilidade — equivalente a encontrar_preco_generico(calcular, ...)."""
    return encontrar_preco_generico(
        calcular, entradas, margem_desejada, entradas.custo_sem_ipi, tolerancia, max_iter
    )


@dataclass
class ResultadoCompleto:
    preco_necessario: float
    preco_cheio: float
    preco_promocional: float
    lucro_real: float
    margem_real: float
    lucro_promocional: float
    margem_promocional: float
    custo_produto_total: float
    custo_total_impostos: float


def resolver_generico(
    calcular_fn: Callable[..., R],
    entradas,
    margem_desejada: float,
    desconto_promocional: float = 0.0,
) -> ResultadoCompleto:
    """
    Versão genérica de resolver_nacional_sem_st, reaproveitável pelos 6
    cenários. Regra de negócio real (confirmada com a planilha e com o
    fluxo da empresa na Shopee):
      - margem_desejada vale sobre o PREÇO PROMOCIONAL (o preço que o
        cliente realmente paga — é o valor que entra no caixa, então é
        nele que a margem precisa ser garantida). É o solver que encontra
        esse preço, igual a planilha faz em D9 pra bater J14.
      - preco_cheio = preco_promocional / (1 - desconto_promocional) — é
        só o valor inflado exibido riscado no "de/por" da Shopee; nunca é
        efetivamente cobrado, por isso não passa por um segundo solver,
        só pela divisão.
      - lucro/margem do preço cheio são recalculados a partir desse preço
        maior (custo_shopee e taxa_shp_premio podem mudar de faixa se o
        preço cruzar um limite — por isso é um `calcular_fn()` novo, não
        só uma conta em cima do lucro do promocional). Esses números são
        só informativos (mostram o que aconteceria SE a venda fosse feita
        pelo preço cheio, o que não ocorre na prática).
    """
    resultado_promocional = encontrar_preco_generico(
        calcular_fn, entradas, margem_desejada, entradas.custo_sem_ipi
    )
    preco_promocional = resultado_promocional.preco_venda
    fator_desconto = 1 - desconto_promocional
    preco_cheio = preco_promocional / fator_desconto if fator_desconto > 0 else preco_promocional
    resultado_cheio = calcular_fn(preco_cheio, entradas)

    return ResultadoCompleto(
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


def resolver_nacional_sem_st(
    entradas: EntradasNacionalSemST,
    margem_desejada: float,
    desconto_promocional: float = 0.0,
) -> ResultadoCompleto:
    """Mantido por compatibilidade — equivalente a resolver_generico(calcular, ...)."""
    return resolver_generico(calcular, entradas, margem_desejada, desconto_promocional)
