"""
Termômetro de CONFIANÇA DO PREÇO.

Responde: "posso publicar esse preço sem medo de perder dinheiro?". Roda DEPOIS
do cálculo e NÃO altera nenhum número do motor — só lê entradas e resultado.
Se qualquer coisa aqui falhar, devolve None e o cálculo segue normal (o front
simplesmente não mostra o termômetro).

Critérios (cada um vira "ok", "atencao" ou "risco"):
  1. Frete digitado x tabela Peso x Valor (ML, Magalu e Amazon).
  2. Frete de compra (%) zerado.
  3. Cenário com ST, mas ST (%) zerado.
  4. Teste de estresse: margem no preço promocional se custo, frete e
     comissão piorarem um pouco. É o critério que mostra se o preço é frágil.
  5. Peso do frete (R$) no preço promocional.
  6. Margem desejada alta demais (provável erro de digitação).
  7. Lucro por unidade no preço promocional (R$): prejuízo ou lucro baixo demais.
  8. Margem no preço promocional: faixas de margem boa / razoável / ruim.

Cor final = pior nível entre os critérios (algum "risco" -> vermelho; algum
"atencao" -> amarelo; senão verde). Todos os limites estão em LIMITES, aqui
embaixo — é o único lugar para ajustar.
"""
from __future__ import annotations

import dataclasses
import logging

log = logging.getLogger(__name__)

LIMITES = {
    # Frete digitado x tabela: diferença relativa
    "frete_diverg_atencao": 0.05,   # acima disso: amarelo
    "frete_diverg_risco": 0.20,     # acima disso: vermelho
    # Teste de estresse (piora relativa aplicada sobre as entradas)
    "estresse_custo": 0.05,         # custo do produto +5%
    "estresse_frete": 0.20,         # frete (% de compra e R$) +20%
    "estresse_comissao": 0.10,      # comissão +10% (quando informada na tela)
    "folga_atencao": 0.50,          # margem sob estresse < 50% da desejada: amarelo
                                    # margem sob estresse <= 0: vermelho
    # Peso do frete (R$) sobre o preço promocional
    "frete_peso_atencao": 0.25,
    "frete_peso_risco": 0.40,
    # Margem desejada suspeita de erro de digitação
    "margem_alta_atencao": 0.40,
    # Qualidade do resultado: margem no preço promocional
    "margem_boa": 0.15,             # a partir daqui: verde
    "margem_minima": 0.08,          # entre minima e boa: amarelo; abaixo: vermelho
    # Qualidade do resultado: lucro por unidade no promocional (R$)
    "lucro_atencao": 5.00,          # abaixo disso: amarelo
    "lucro_risco": 2.00,            # abaixo disso (ou prejuízo): vermelho
    # Pontuação (só para a barra; a COR vem do pior critério)
    "penalidade_atencao": 15,
    "penalidade_risco": 40,
}

OK, ATENCAO, RISCO = "ok", "atencao", "risco"
_ORDEM = {OK: 0, ATENCAO: 1, RISCO: 2}
_NIVEL_COR = ["verde", "amarelo", "vermelho"]


def _pct(v: float) -> str:
    return f"{v * 100:.1f}".replace(".", ",") + "%"


def _brl(v: float) -> str:
    return "R$ " + f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _item(criterio: str, nivel: str, mensagem: str) -> dict:
    return {"criterio": criterio, "nivel": nivel, "mensagem": mensagem}


# ---------------------------------------------------------------- critérios

def _c_frete_digitado(frete_digitado, frete_tabela):
    if frete_digitado is None or frete_digitado <= 0:
        return None
    if frete_tabela is None or frete_tabela <= 0:
        return _item(
            "frete_tabela", ATENCAO,
            f"Frete digitado direto ({_brl(frete_digitado)}), sem peso/valor selecionados para conferir com a tabela.",
        )
    diff = (frete_digitado - frete_tabela) / frete_tabela
    abs_diff = abs(diff)
    if abs_diff <= LIMITES["frete_diverg_atencao"]:
        return _item("frete_tabela", OK, f"Frete digitado ({_brl(frete_digitado)}) confere com a tabela ({_brl(frete_tabela)}).")
    sentido = "acima" if diff > 0 else "abaixo"
    msg = f"Frete digitado ({_brl(frete_digitado)}) está {_pct(abs_diff)} {sentido} da tabela ({_brl(frete_tabela)})."
    nivel = RISCO if abs_diff > LIMITES["frete_diverg_risco"] else ATENCAO
    return _item("frete_tabela", nivel, msg)


def _c_frete_compra(perc_frete):
    if perc_frete <= 0:
        return _item("frete_compra", ATENCAO, "Frete de compra (%) zerado: confirme se o custo já inclui o frete.")
    return _item("frete_compra", OK, f"Frete de compra informado ({_pct(perc_frete)}).")


def _c_st(requer_st, perc_st):
    if not requer_st:
        return None
    if perc_st <= 0:
        return _item("st", ATENCAO, "Cenário com ST, mas o ST (%) está zerado: o custo pode estar subestimado.")
    return _item("st", OK, f"ST informado ({_pct(perc_st)}).")


def _estressar(entradas):
    """Cópia das entradas com custo, frete e comissão um pouco piores."""
    campos = {f.name for f in dataclasses.fields(entradas)}
    upd = {}
    if "custo_sem_ipi" in campos:
        upd["custo_sem_ipi"] = entradas.custo_sem_ipi * (1 + LIMITES["estresse_custo"])
    for nome in ("perc_frete", "custo_frete"):
        if nome in campos and getattr(entradas, nome):
            upd[nome] = getattr(entradas, nome) * (1 + LIMITES["estresse_frete"])
    if "comissao_pct" in campos and getattr(entradas, "comissao_pct", None):
        upd["comissao_pct"] = entradas.comissao_pct * (1 + LIMITES["estresse_comissao"])
    return dataclasses.replace(entradas, **upd)


def _c_estresse(calcular_fn, entradas, preco, margem_desejada):
    margem = calcular_fn(preco, _estressar(entradas)).margem_real
    desc = (
        f"custo +{LIMITES['estresse_custo'] * 100:.0f}%, "
        f"frete +{LIMITES['estresse_frete'] * 100:.0f}%, "
        f"comissão +{LIMITES['estresse_comissao'] * 100:.0f}%"
    )
    if margem <= 0:
        item = _item("estresse", RISCO, f"Sob estresse ({desc}) a margem vai a {_pct(margem)}: o preço não aguenta uma pequena piora de custos.")
    elif margem < margem_desejada * LIMITES["folga_atencao"]:
        item = _item("estresse", ATENCAO, f"Sob estresse ({desc}) a margem cai de {_pct(margem_desejada)} para {_pct(margem)}: pouca folga.")
    else:
        item = _item("estresse", OK, f"Margem aguenta o teste de estresse ({desc}): {_pct(margem)} contra {_pct(margem_desejada)} desejada.")
    return item, margem


def _c_peso_frete(frete_aplicado, preco):
    if not frete_aplicado or frete_aplicado <= 0 or preco <= 0:
        return None
    ratio = frete_aplicado / preco
    if ratio >= LIMITES["frete_peso_risco"]:
        return _item("frete_peso", RISCO, f"O frete ({_brl(frete_aplicado)}) consome {_pct(ratio)} do preço promocional.")
    if ratio >= LIMITES["frete_peso_atencao"]:
        return _item("frete_peso", ATENCAO, f"O frete ({_brl(frete_aplicado)}) pesa {_pct(ratio)} do preço promocional.")
    return _item("frete_peso", OK, f"Frete aplicado pesa {_pct(ratio)} do preço promocional.")


def _c_margem_alvo(margem_desejada):
    if margem_desejada > LIMITES["margem_alta_atencao"]:
        return _item("margem_alvo", ATENCAO, f"Margem desejada de {_pct(margem_desejada)} é alta: confira se não é erro de digitação.")
    return None


def _c_lucro(lucro_promocional):
    if lucro_promocional is None:
        return None
    if lucro_promocional <= 0:
        return _item("lucro", RISCO, f"O preço promocional não dá lucro ({_brl(lucro_promocional)} por unidade).")
    if lucro_promocional < LIMITES["lucro_risco"]:
        return _item("lucro", RISCO, f"Lucro de {_brl(lucro_promocional)} por unidade é baixo demais para compensar a venda.")
    if lucro_promocional < LIMITES["lucro_atencao"]:
        return _item("lucro", ATENCAO, f"Lucro de {_brl(lucro_promocional)} por unidade é baixo.")
    return _item("lucro", OK, f"Lucro de {_brl(lucro_promocional)} por unidade no promocional.")


def _c_margem_boa(margem_promocional):
    if margem_promocional is None:
        return None
    tol = 1e-4  # o solver converge com folga de ~1e-6; evita 14,99999% virar amarelo
    if margem_promocional + tol < LIMITES["margem_minima"]:
        return _item("margem", RISCO, f"Margem de {_pct(margem_promocional)} no promocional está abaixo do mínimo ({_pct(LIMITES['margem_minima'])}).")
    if margem_promocional + tol < LIMITES["margem_boa"]:
        return _item("margem", ATENCAO, f"Margem de {_pct(margem_promocional)} no promocional é apertada (boa a partir de {_pct(LIMITES['margem_boa'])}).")
    return _item("margem", OK, f"Margem de {_pct(margem_promocional)} no promocional.")


# ---------------------------------------------------------------- avaliação

def avaliar_confianca(
    *,
    calcular_fn,
    entradas,
    preco_promocional: float,
    margem_desejada: float,
    requer_st: bool = False,
    perc_st: float = 0.0,
    perc_frete: float = 0.0,
    frete_aplicado: float | None = None,
    frete_digitado: float | None = None,
    frete_tabela: float | None = None,
    lucro_promocional: float | None = None,
    margem_promocional: float | None = None,
) -> dict | None:
    """
    Devolve {"nivel": "verde|amarelo|vermelho", "score": 0-100, "titulo": str,
    "margem_estressada": float|None, "motivos": [{criterio, nivel, mensagem}]}
    ou None se não conseguiu avaliar. Nunca levanta exceção.
    """
    try:
        itens: list[dict] = []
        margem_estressada = None

        def seguro(fn, *args):
            try:
                return fn(*args)
            except Exception:  # um critério quebrado não derruba os outros
                log.exception("Falha no critério de confiança %s", getattr(fn, "__name__", fn))
                return None

        for res in (
            seguro(_c_frete_digitado, frete_digitado, frete_tabela),
            seguro(_c_frete_compra, perc_frete),
            seguro(_c_st, requer_st, perc_st),
        ):
            if res:
                itens.append(res)

        for res in (
            seguro(_c_lucro, lucro_promocional),
            seguro(_c_margem_boa, margem_promocional),
        ):
            if res:
                itens.append(res)

        est = seguro(_c_estresse, calcular_fn, entradas, preco_promocional, margem_desejada)
        if est:
            itens.append(est[0])
            margem_estressada = est[1]

        for res in (
            seguro(_c_peso_frete, frete_aplicado, preco_promocional),
            seguro(_c_margem_alvo, margem_desejada),
        ):
            if res:
                itens.append(res)

        if not itens:
            return None

        pior = max(_ORDEM[i["nivel"]] for i in itens)
        penal = sum(
            LIMITES["penalidade_risco"] if i["nivel"] == RISCO else LIMITES["penalidade_atencao"] if i["nivel"] == ATENCAO else 0
            for i in itens
        )
        score = max(0, 100 - penal)
        if pior == 2:
            score = min(score, 39)
        elif pior == 1:
            score = min(score, 79)

        if pior == 2:
            primeiro = next(i for i in itens if i["nivel"] == RISCO)
            titulo = "Revise antes de publicar: " + primeiro["mensagem"]
        elif pior == 1:
            primeiro = next(i for i in itens if i["nivel"] == ATENCAO)
            titulo = "Confira antes de publicar: " + primeiro["mensagem"]
        else:
            titulo = "Lucro, margem e dados em ordem; o preço aguenta o teste de estresse."

        # pontos problemáticos primeiro na lista
        itens.sort(key=lambda i: -_ORDEM[i["nivel"]])
        return {
            "nivel": _NIVEL_COR[pior],
            "score": int(score),
            "titulo": titulo,
            "margem_estressada": margem_estressada,
            "motivos": itens,
        }
    except Exception:
        log.exception("Falha ao avaliar a confiança do preço")
        return None
