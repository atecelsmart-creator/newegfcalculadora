"""
Definidor de cenário (matriz de 6 cenários, São Paulo).

Duas decisões independentes escolhem o cenário:
  - sem ST / com ST  -> resultado do Econet
  - tipo             -> Aliq ICMS do Citel (4% = importado; 12/16/18/20% = nacional)
  - Base Reduzida    -> Confaz 52/91 (a origem passa a vir da Aliq ICMS)

Qualquer dúvida devolve ok=False com o motivo (vira REVISAR). O robô nunca assume
"sem ST" por falha de pesquisa e nunca assume Base Reduzida sozinho.
"""
from dataclasses import dataclass

from rpa import modelos as m

ICMS_IMPORTADO = {4}
ICMS_NACIONAL = {12, 16, 18, 20}

CENARIOS_VALIDOS = {
    "nacional_sem_st", "nacional_com_st",
    "importado_sem_st", "importado_com_st",
    "base_reduzida_sem_st", "base_reduzida_com_st",
}


@dataclass(frozen=True)
class Decisao:
    ok: bool
    cenario: str | None = None
    origem_base_reduzida: str = "nacional"   # só tem efeito nos cenários base_reduzida_*
    tipo: str | None = None                  # "nacional" | "importado"
    com_st: bool = False
    base_reduzida: bool = False
    motivo: str = ""


def tipo_produto(aliq_icms: float | None) -> str | None:
    """4 -> importado; 12/16/18/20 -> nacional; qualquer outro valor (ou ausente) -> None."""
    if aliq_icms is None:
        return None
    a = round(float(aliq_icms), 4)
    if a in ICMS_IMPORTADO:
        return "importado"
    if a in ICMS_NACIONAL:
        return "nacional"
    return None


def _revisar(motivo: str) -> Decisao:
    return Decisao(ok=False, motivo=motivo)


def definir_cenario(dados: m.DadosProduto, estado: str = "SP") -> Decisao:
    if estado != "SP":
        return _revisar(f"Estado {estado} ainda não suportado pelo robô (esta etapa é só SP)")

    tipo = tipo_produto(dados.aliq_icms)
    if tipo is None:
        return _revisar(f"Aliq ICMS {dados.aliq_icms} fora de 4, 12, 16, 18, 20")

    st = dados.st.status
    if st == m.COM_ST:
        com_st = True
    elif st == m.SEM_ST:
        com_st = False
    elif st == m.ST_AMBIGUO:
        return _revisar("Econet devolveu mais de um MVA para o NCM")
    elif st == m.ST_FALHOU:
        return _revisar("Pesquisa no Econet falhou (falha nunca é tratada como sem ST)")
    else:
        return _revisar("ST não consultado no Econet")

    conf = dados.confaz.status
    if conf == m.BASE_REDUZIDA:
        base = True
    elif conf == m.FORA_DA_LISTA:
        base = False
    elif conf == m.CONDICIONAL:
        return _revisar("Item do Convênio 52/91 com condição além do NCM (o robô não assume Base Reduzida)")
    else:
        return _revisar("Confaz não consultado ou a consulta falhou")

    sufixo = "com_st" if com_st else "sem_st"
    prefixo = "base_reduzida" if base else tipo
    cenario = f"{prefixo}_{sufixo}"
    # Em Base Reduzida a origem vem da Aliq ICMS: 4% = importado (entrada 4,00%); 12/16/18/20% = nacional (entrada 8,80%).
    return Decisao(ok=True, cenario=cenario, origem_base_reduzida=tipo, tipo=tipo, com_st=com_st, base_reduzida=base)
