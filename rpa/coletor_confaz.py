"""
Coletor do Confaz (Convênio ICMS 52/91): lê a página SALVA em disco (rpa/confaz.html),
sem acessar o site, e diz se um NCM está nos Anexos I ou II (redação em vigor).

Como a página é montada:
  - Há 6 tabelas. Só valem as que vêm depois de "Nova redação dada ao Anexo I/II" e têm a coluna
    "NCM/SH" (Anexo I e Anexo II atuais). As de "Redação anterior"/"Redação original" são ignoradas.
  - Dentro das tabelas atuais ainda existem linhas antigas, logo após uma nota "Redação anterior ..."
    ou "Redação original ...". Elas são puladas, e os itens "Revogado(s)" também.

Resultado (modelos.ResultadoConfaz), no mesmo formato que o resto do robô já usa:
  BASE_REDUZIDA  NCM em um único item, sem condição aparente na descrição (o detalhe diz qual item conferir)
  CONDICIONAL    NCM em mais de um item/anexo, coberto só por posição/subposição, ou com condição na
                 descrição (capacidade, exceto, "Outros"...). O robô não assume: vai para REVISAR
  FORA_DA_LISTA  NCM não consta nos Anexos
  FALHOU         arquivo ausente/ilegível, lista com tamanho suspeito ou NCM inválido
                 (falha NUNCA vira FORA_DA_LISTA)

Uso na linha de comando (na raiz do projeto):
  python -m rpa.coletor_confaz 84198999 84151011
  python -m rpa.coletor_confaz --html "C:\\outro\\confaz.html" 84138100
"""
import re
import sys
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path

from rpa import config
from rpa import modelos as m

# Abaixo disso a lista lida é suspeita (página mudou de layout?) e o coletor falha em vez de dizer "fora da lista".
MINIMO_ITENS = 100

_CODIGO = re.compile(r"\b\d{4}\.\d{2}(?:\.\d{2})?(?!\d)")
_ANEXO = re.compile(r"\bANEXO (II|I)\b")
_CONDICAO = re.compile(
    r"capacidade|superior|inferior|exceto|somente|apenas|desde que|destinad|"
    r"para (?:uso|transporte|utiliza)|pot[eê]ncia|\baté\b|acima|abaixo|\bnão\b|^outr[oa]s?\b",
    re.IGNORECASE,
)


def _limpa(txt: str) -> str:
    return re.sub(r"\s+", " ", (txt or "").replace("\xa0", " ")).strip()


class _LeitorTabelas(HTMLParser):
    """Guarda cada tabela com o texto que vem antes dela (títulos e notas) e suas linhas."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tabelas: list[dict] = []
        self._nivel = 0
        self._ignorar = 0
        self._fora: list[str] = []
        self._atual: dict | None = None
        self._linha: list[str] | None = None
        self._celula: list[str] | None = None

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self._ignorar += 1
        elif tag == "table":
            self._nivel += 1
            if self._nivel == 1:
                self._atual = {"antes": _limpa(" ".join(self._fora)), "linhas": []}
                self._fora = []
        elif self._nivel == 1 and tag == "tr":
            self._linha = []
        elif self._nivel == 1 and tag in ("td", "th") and self._linha is not None:
            self._celula = []
        elif tag == "br" and self._celula is not None:
            self._celula.append(" ")

    def handle_endtag(self, tag):
        if tag in ("script", "style"):
            self._ignorar = max(0, self._ignorar - 1)
        elif self._nivel == 1 and tag in ("td", "th") and self._celula is not None and self._linha is not None:
            self._linha.append(_limpa("".join(self._celula)))
            self._celula = None
        elif self._nivel == 1 and tag == "tr" and self._linha is not None:
            if self._atual is not None:
                self._atual["linhas"].append(self._linha)
            self._linha = None
        elif tag == "table" and self._nivel > 0:
            self._nivel -= 1
            if self._nivel == 0 and self._atual is not None:
                self.tabelas.append(self._atual)
                self._atual = None

    def handle_data(self, data):
        if self._ignorar:
            return
        if self._celula is not None:
            self._celula.append(data)
        elif self._nivel == 0:
            self._fora.append(data)


@dataclass(frozen=True)
class Item:
    anexo: str            # "I" ou "II"
    item: str             # número do item/subitem no Convênio (ex.: "13.7")
    descricao: str
    codigos: tuple[str, ...]   # NCMs só com dígitos: 8 (exato) ou 4/6 (posição/subposição inteira)


def _tabela_em_vigor(tab: dict) -> str | None:
    """Devolve "I" ou "II" se a tabela é um Anexo em vigor; senão None."""
    if not tab["linhas"]:
        return None
    cab = " ".join(tab["linhas"][0]).upper()
    if "NCM/SH" not in cab or "NBM" in cab:
        return None
    antes = tab["antes"].upper()
    nova = antes.rfind("NOVA REDAÇÃO DADA AO ANEXO")
    velha = max(antes.rfind("REDAÇÃO ANTERIOR DADA AO ANEXO"), antes.rfind("REDAÇÃO ORIGINAL"))
    if nova < 0 or nova < velha:
        return None
    anexos = _ANEXO.findall(antes)
    return anexos[-1] if anexos else None


def _ids_da_nota(nota: str) -> list[str]:
    """'Revogados os subitens 39.1, 39.2 e 39.3 do Anexo I pelo Conv...' -> ['39.1','39.2','39.3'].
    Só olha o trecho entre 'item/subitem' e 'do Anexo' (datas e números de convênio ficam de fora)."""
    achou = re.search(r"(?:sub\w*|itens?)\s+(.+?)\s+do Anexo", nota, re.IGNORECASE)
    return re.findall(r"\d+(?:\.\d+)*", achou.group(1)) if achou else []


def _itens_da_tabela(tab: dict, anexo: str) -> list[Item]:
    linhas = tab["linhas"][1:]
    revogados: set[str] = set()
    for cel in linhas:
        if len(cel) < 3 and cel and cel[0].lower().startswith("revogad"):
            revogados.update(_ids_da_nota(cel[0]))

    itens: list[Item] = []
    ultimo_id = None
    pular_ids: set[str] = set()
    for cel in linhas:
        if len(cel) < 3:                       # linha de nota (uma célula só)
            nota = cel[0] if cel else ""
            baixa = nota.lower()
            if baixa.startswith(("redação anterior", "redação original")):
                pular_ids = set(_ids_da_nota(nota)) or ({ultimo_id} if ultimo_id else set())
            else:
                pular_ids = set()
            continue
        item, desc, ncms = cel[0], cel[1], cel[2]
        if pular_ids:
            if item in pular_ids:              # versão antiga do mesmo item
                continue
            pular_ids = set()
        if item in revogados:
            continue
        codigos = tuple(c.replace(".", "") for c in _CODIGO.findall(ncms))
        ultimo_id = item
        if codigos:
            itens.append(Item(anexo=anexo, item=item, descricao=desc, codigos=codigos))
    return itens


def ler_itens(caminho) -> list[Item]:
    """Lê o HTML salvo e devolve os itens em vigor dos Anexos I e II."""
    bruto = Path(caminho).read_bytes()
    try:
        html = bruto.decode("utf-8")
    except UnicodeDecodeError:
        html = bruto.decode("cp1252", errors="replace")
    leitor = _LeitorTabelas()
    leitor.feed(html)
    leitor.close()
    itens: list[Item] = []
    for tab in leitor.tabelas:
        anexo = _tabela_em_vigor(tab)
        if anexo:
            itens.extend(_itens_da_tabela(tab, anexo))
    return itens


class ColetorConfaz:
    """Consulta de NCM no Convênio 52/91 a partir do HTML salvo. Nunca lança erro: devolve FALHOU com o motivo."""

    def __init__(self, caminho=None, minimo_itens: int = MINIMO_ITENS):
        self.caminho = Path(caminho) if caminho else Path(config.CONFAZ_HTML)
        self.erro: str | None = None
        self.itens: list[Item] = []
        self._exatos: dict[str, list[Item]] = {}
        self._prefixos: list[tuple[str, Item]] = []
        try:
            self.itens = ler_itens(self.caminho)
        except FileNotFoundError:
            self.erro = f"Arquivo do Confaz não encontrado: {self.caminho}"
        except Exception as e:  # leitura/parse nunca derruba o robô
            self.erro = f"Não consegui ler o HTML do Confaz ({type(e).__name__}: {e})"
        if self.erro is None and len(self.itens) < minimo_itens:
            self.erro = (f"Só achei {len(self.itens)} itens nos Anexos I e II (esperado ao menos {minimo_itens}); "
                         "a página salva pode estar incompleta ou ter mudado de layout")
            self.itens = []
        for it in self.itens:
            for cod in it.codigos:
                if len(cod) == 8:
                    self._exatos.setdefault(cod, []).append(it)
                else:
                    self._prefixos.append((cod, it))

    def consultar(self, ncm) -> m.ResultadoConfaz:
        if self.erro:
            return m.ResultadoConfaz(status=m.CONFAZ_FALHOU, detalhe=self.erro)
        d = re.sub(r"\D", "", str(ncm or ""))
        if len(d) != 8:
            return m.ResultadoConfaz(status=m.CONFAZ_FALHOU, detalhe=f"NCM inválido: {ncm!r} (esperado 8 dígitos)")

        exatos = self._exatos.get(d, [])
        cobertos = [(p, it) for p, it in self._prefixos if d.startswith(p)]
        if not exatos and not cobertos:
            return m.ResultadoConfaz(status=m.FORA_DA_LISTA,
                                     detalhe=f"NCM {d} não consta nos Anexos I e II do Convênio 52/91 (redação em vigor)")

        def rotulo(it: Item) -> str:
            return f"Anexo {it.anexo}, item {it.item}: {it.descricao[:90]}"

        motivos = []
        todos = list(exatos) + [it for _, it in cobertos]
        if len(todos) > 1:
            motivos.append(f"aparece em {len(todos)} itens")
        if cobertos:
            motivos.append("coberto só por posição/subposição (" + ", ".join(sorted({p for p, _ in cobertos})) + ")")
        if any(_CONDICAO.search(it.descricao) for it in todos):
            motivos.append("descrição com condição ou genérica")
        itens_txt = " | ".join(rotulo(it) for it in todos[:4])
        if motivos:
            return m.ResultadoConfaz(status=m.CONDICIONAL,
                                     detalhe=f"NCM {d}: {'; '.join(motivos)}. {itens_txt}")
        return m.ResultadoConfaz(status=m.BASE_REDUZIDA, detalhe=f"NCM {d}: {itens_txt}")


def _main(argv: list[str]) -> int:
    caminho = None
    ncms = []
    i = 0
    while i < len(argv):
        if argv[i] == "--html" and i + 1 < len(argv):
            caminho = argv[i + 1]
            i += 2
        else:
            ncms.append(argv[i])
            i += 1
    coletor = ColetorConfaz(caminho)
    if coletor.erro:
        print("FALHOU:", coletor.erro)
        return 1
    print(f"{len(coletor.itens)} itens em vigor lidos de {coletor.caminho}")
    for n in ncms:
        r = coletor.consultar(n)
        print(f"{n}: {r.status} - {r.detalhe}")
    return 0


if __name__ == "__main__":
    sys.exit(_main(sys.argv[1:]))
