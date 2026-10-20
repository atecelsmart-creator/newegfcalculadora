"""
Edita a planilha de preços de um marketplace (Mercado Livre ou Shopee).

Localiza um anúncio pelo SKU ou pelo código do anúncio e grava, na MESMA linha:
  - Mercado Livre: Preço cheio -> PRICE ("Preço") e Preço promocional -> SALE_PRICE ("Preço em promoção")
  - Shopee: só o Preço (a planilha de atualização em massa da Shopee não tem preço promocional)

O que muda de um marketplace para o outro está no Perfil (nome da aba, nomes das colunas, formato do código do anúncio).
A regra de gravação é a mesma. Nenhuma fórmula de preço mora aqui: os valores já vêm calculados pela calculadora.
"""
from __future__ import annotations

import hashlib
import html
import io
import math
import posixpath
import re
import threading
import unicodedata
import zipfile
from dataclasses import dataclass, replace
from itertools import zip_longest
from xml.sax.saxutils import escape

from openpyxl import load_workbook
from openpyxl.utils import column_index_from_string, get_column_letter

ABA = "Anúncios"          # aba da planilha do Mercado Livre
LIMITE_BUSCA = 5          # quantas linhas mostrar quando a busca acha mais de uma


class PlanilhaInvalida(ValueError):
    """Arquivo que não é a planilha do marketplace. A mensagem já é para mostrar na tela."""


class BuscaInvalida(ValueError):
    """Busca vazia, sem resultado ou ambígua. A mensagem já é para mostrar na tela."""


def _norm(v) -> str:
    """'ID do Produto' / 'et_title_product_id' -> só letras e números, minúsculas, sem acento."""
    s = unicodedata.normalize("NFKD", str(v)).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]", "", s.lower())


@dataclass(frozen=True)
class Perfil:
    chave: str                 # "mercado_livre" | "shopee"
    nome: str                  # texto para mensagens
    aba: str | None            # aba fixa; None = procura a aba certa entre todas
    nomes: dict                # coluna -> nomes aceitos no cabeçalho (já normalizados)
    obrigatorias: tuple
    id_valido: re.Pattern      # o que é um código de anúncio de verdade (filtra linhas de ajuda/cabeçalho)
    usa_promocao: bool
    busca_sku_principal: bool  # a busca também olha a coluna de SKU principal
    linhas_cabecalho: int      # até onde procurar o cabeçalho (ML: só a linha 1)
    pedido: str                # "o SKU ou ..." (para as mensagens)
    dica_invalida: str
    sku_basta: bool = False    # linha vale com SKU mesmo sem ID de produto (planilha da Shopee com a coluna ID vazia)
    # Regras do marketplace para o envio em massa não dar erro (None = sem regra)
    preco_min: float | None = None
    preco_max: float | None = None
    razao_max: float | None = None   # preço da variação mais cara ÷ a mais barata do MESMO produto (Shopee: 5)
    rejeitar: frozenset = frozenset()   # cabeçalhos que só existem na planilha de OUTRO marketplace
    propria: bool = False    # planilha comum do usuário (SKU | Nome | Preço Cheio | Preço Promocional): SKU novo vira linha nova


ML = Perfil(
    chave="mercado_livre",
    nome="Mercado Livre",
    aba=ABA,
    nomes={
        "ITEM_ID": {"itemid"}, "VARIATION_ID": {"variationid"}, "SKU": {"sku"}, "TITLE": {"title"},
        "PRICE": {"price"}, "SALE_PRICE": {"saleprice"}, "STATUS": {"status"},
    },
    obrigatorias=("ITEM_ID", "VARIATION_ID", "SKU", "TITLE", "PRICE"),
    id_valido=re.compile(r"MLB\d+"),
    usa_promocao=True,
    busca_sku_principal=False,
    linhas_cabecalho=1,
    pedido="o SKU ou o código do anúncio (MLB...)",
    dica_invalida="Baixe de novo em 'Alterar preços em Excel'.",
)

# Planilha de atualização em massa da Shopee (aceita o nome técnico da coluna, ex.: et_title_product_id, e o nome em português)
SHOPEE = Perfil(
    chave="shopee",
    nome="Shopee",
    aba=None,
    nomes={
        # "id", "title" e "titulo": planilha da Shopee com cabeçalho curto (ID | SKU | TITLE) e o rótulo em português logo abaixo
        "ITEM_ID": {"ettitleproductid", "iddoproduto", "idproduto", "productid", "itemid", "id", "idanuncio", "iditem"},
        "VARIATION_ID": {"ettitlevariationid", "iddavariacao", "variationid"},
        "SKU": {"ettitlevariationsku", "skudavariacao", "skudereferenciadavariacao", "sku", "skudereferencia"},
        "PARENT_SKU": {"ettitleparentsku", "skuprincipal", "skudereferenciaprincipal", "skudoproduto", "parentsku"},
        "TITLE": {"ettitleproductname", "nomedoproduto", "productname", "nomedoanuncio", "title", "titulo"},
        "PRICE": {"ettitlevariationprice", "preco", "precooriginal", "precodavariacao", "price", "precocheio", "precoatual",
                  "precodevenda", "precodavenda", "precor", "valor", "valorr"},
        "SALE_PRICE": {"saleprice", "precoempromocao", "precopromocional", "precodepromocao", "precopromo"},
    },
    obrigatorias=("PRICE",),
    id_valido=re.compile(r"\d{5,}"),
    usa_promocao=True,
    busca_sku_principal=True,
    linhas_cabecalho=10,
    pedido="o SKU ou o ID do produto",
    dica_invalida="A planilha da Shopee precisa ter uma coluna de SKU (ou de ID do produto) e uma coluna de Preço.",
    sku_basta=True,
    preco_min=1.0,        # "Insira de 1.00 a 100000.00 para o preço do produto"
    preco_max=100000.0,
    razao_max=5.0,        # "O preço do sku mais caro dividido pelo do mais barato: 5.00"
    rejeitar=frozenset({"sellersku", "skuid"}),   # colunas da planilha do TikTok
)

# Planilha de edição em massa do TikTok Shop (aba "Template"): só Preço (sem preço promocional), SKU em "seller_sku"
TIKTOK = Perfil(
    chave="tiktok",
    nome="TikTok Shop",
    aba=None,
    nomes={
        "ITEM_ID": {"productid", "iddoproduto"},
        "VARIATION_ID": {"skuid", "iddosku"},
        "SKU": {"sellersku", "skudovendedor"},
        "TITLE": {"productname", "nomedoproduto"},
        "PRICE": {"price", "precodevarejomoedalocal", "precodevarejo"},
    },
    obrigatorias=("ITEM_ID", "SKU", "PRICE"),
    id_valido=re.compile(r"\d{10,}"),
    usa_promocao=False,
    busca_sku_principal=False,
    linhas_cabecalho=5,
    pedido="o SKU do vendedor ou o ID do produto",
    dica_invalida="Use a planilha de edição em massa baixada do TikTok Shop (aba Template, com product_id, seller_sku e price).",
)

# Planilha comum do usuário (controle interno da empresa): SKU | Descrição ou Título | Preço Cheio | Preço Promocional.
# Uma planilha por marketplace (o preço muda de um para o outro): a chave vira "propria_<marketplace>" (ver perfil_de).
PROPRIA = Perfil(
    chave="propria",
    nome="Minha planilha",
    aba=None,
    nomes={
        "SKU": {"sku", "codigo", "codigosku", "skudoproduto"},
        "TITLE": {"descricaoutitulo", "nomedoprodutooudescricao", "nomedoproduto", "descricao", "nome", "produto", "titulo"},
        "PRICE": {"precocheio", "preco", "precodevenda"},
        "SALE_PRICE": {"precopromocional", "precopromocao", "precopromo", "precodepromocao"},
    },
    obrigatorias=("SKU", "PRICE"),
    id_valido=re.compile(r"$^"),   # não tem ID de anúncio: a linha vale pelo SKU
    usa_promocao=True,
    busca_sku_principal=False,
    linhas_cabecalho=5,
    pedido="o SKU",
    dica_invalida="A planilha precisa ter as colunas SKU, Descrição ou Título, Preço Cheio e Preço Promocional.",
    sku_basta=True,
    propria=True,
)

PERFIS = {"mercado_livre": ML, "shopee": SHOPEE, "tiktok": TIKTOK}


NOMES_MK_PROPRIA = {**{k: v.nome for k, v in PERFIS.items()}, "magalu": "Magalu", "amazon_dba": "Amazon"}


def perfil_de(chave: str | None) -> Perfil:
    c = (chave or "").strip()
    if c.startswith("propria_") and c[len("propria_"):] in NOMES_MK_PROPRIA:   # planilha comum de um marketplace
        return replace(PROPRIA, chave=c, nome=f"Minha planilha ({NOMES_MK_PROPRIA[c[len('propria_'):]]})")
    return PERFIS.get(c, ML)


def _resultado_formula(ws, row: int, col: int, bruto):
    """Célula com FÓRMULA (ex.: o título das variações do ML, que é uma fórmula): devolve o resultado que o Excel guardou
    no arquivo (o que aparece na tela do Excel), não o texto da fórmula. Só vale para .xlsx/.xlsm; a segunda leitura
    (data_only) só é feita quando aparece a primeira fórmula. Se o arquivo não guardou o resultado, devolve None
    (a célula aparece vazia na calculadora; no arquivo a fórmula continua intacta)."""
    origem = getattr(ws, "_origem_xlsx", None)
    if origem is None:
        return bruto
    if origem["valores"] is None:
        try:
            origem["valores"] = _carregar_wb(origem["conteudo"], data_only=True)
        except Exception:
            origem["valores"] = False
    if not origem["valores"]:
        return None
    try:
        return origem["valores"][ws.title].cell(row, col).value
    except KeyError:
        return None


def _ler(ws, row: int, col: int):
    """Valor da célula para MOSTRAR/BUSCAR: fórmula vira o resultado dela. Para GRAVAR continua valendo ws.cell(...).value."""
    v = ws.cell(row, col).value
    if isinstance(v, str) and v[:1] == "=":
        return _resultado_formula(ws, row, col, v)
    return v


def _txt(v) -> str:
    if v is None:
        return ""
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v).strip()


_NUM_TXT = re.compile(r"^\d+(?:[.,]\d+)?$")


def _numero(v):
    """Preço da célula como número, ou None se estiver vazia / for '-' / texto qualquer.
    Shopee e TikTok guardam o preço como TEXTO ('1151.90'): isso conta como número."""
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, str) and _NUM_TXT.match(v.strip()):
        return float(v.strip().replace(",", "."))
    return None


def _gravar_preco(ws, row: int, col: int, valor: float) -> None:
    """Grava o preço respeitando o formato que a célula já tem: planilha que guarda o preço como texto
    (Shopee, TikTok) continua com texto ('123.45'); a do Mercado Livre continua com número."""
    atual = ws.cell(row, col).value
    if isinstance(atual, str) and _NUM_TXT.match(atual.strip()):
        ws.cell(row, col).value = f"{valor:.2f}"
    else:
        ws.cell(row, col).value = valor


def _colunas(ws, perfil: Perfil = ML) -> dict:
    """Mapeia coluna -> número, procurando o cabeçalho do perfil nas primeiras linhas.
    Guarda em '_LINHA' a linha em que o cabeçalho está (os anúncios começam na seguinte)."""
    pior = None
    rejeitado = False
    achados_pior: list = []
    for r in range(1, perfil.linhas_cabecalho + 1):
        try:
            linha = ws[r]
        except Exception:
            break
        cols: dict = {}
        nomes_linha: list = []
        for c in linha:
            if c.value is None or str(c.value).strip() == "":
                continue
            nomes_linha.append(str(c.value).strip())
            n = _norm(c.value)
            for canon, aceitos in perfil.nomes.items():
                if canon not in cols and n in aceitos:
                    cols[canon] = c.column
        if perfil.rejeitar and any(_norm(n) in perfil.rejeitar for n in nomes_linha):
            rejeitado = True   # cabeçalho de outro marketplace: não é a planilha deste
            continue
        falta = [n for n in perfil.obrigatorias if n not in cols]
        if perfil.sku_basta and "SKU" not in cols and "ITEM_ID" not in cols:
            falta.append("SKU_OU_ID")
        if not falta:
            cols["_LINHA"] = r
            return cols
        if pior is None or len(falta) < len(pior) or (len(falta) == len(pior) and len(nomes_linha) > len(achados_pior)):
            pior, achados_pior = falta, nomes_linha
    if rejeitado:
        raise PlanilhaInvalida(f"Este arquivo parece ser de outro marketplace, não do {perfil.nome}. "
                               f"Troque o campo Marketplace ou envie a planilha do {perfil.nome}.")
    falta = pior or list(perfil.obrigatorias)
    rotulo = {"ITEM_ID": "ID do produto", "PRICE": "Preço", "SKU": "SKU", "VARIATION_ID": "ID da variação",
              "TITLE": "Título", "SKU_OU_ID": "SKU ou ID do produto"}
    vistos = (" Colunas que encontrei: " + ", ".join(achados_pior[:14]) + ".") if achados_pior else ""
    raise PlanilhaInvalida(f"Esta planilha não parece ser a do {perfil.nome} (faltam as colunas "
                           f"{', '.join(rotulo.get(f, f) for f in falta)}).{vistos} {perfil.dica_invalida}")


def _sanear_xlsx(conteudo: bytes) -> bytes:
    """A planilha da Shopee grava o painel congelado como 'bottom_left' (o Excel aceita, o openpyxl não).
    Troca pelo nome certo ('bottomLeft') dentro das abas; o resto do arquivo fica igual."""
    try:
        zin = zipfile.ZipFile(io.BytesIO(conteudo))
    except zipfile.BadZipFile:
        return conteudo
    padrao = re.compile(rb'((?:activePane|pane)=")(top|bottom)_(left|right)(")')
    saida = io.BytesIO()
    with zin, zipfile.ZipFile(saida, "w", zipfile.ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            dados = zin.read(item.filename)
            if item.filename.startswith("xl/worksheets/") and item.filename.endswith(".xml"):
                dados = padrao.sub(lambda m: m.group(1) + m.group(2) + m.group(3).capitalize() + m.group(4), dados)
            zout.writestr(item, dados)
    return saida.getvalue()


def _carregar_wb(conteudo: bytes, **kw):
    try:
        return load_workbook(io.BytesIO(conteudo), **kw)
    except ValueError:   # ex.: painel congelado 'bottom_left' da Shopee
        return load_workbook(io.BytesIO(_sanear_xlsx(conteudo)), **kw)


def _abrir(conteudo: bytes, vba: bool = False, perfil: Perfil = ML):
    """Abre um .xlsx/.xlsm (vba=True preserva as macros do .xlsm) e acha a aba e as colunas do perfil."""
    try:
        wb = _carregar_wb(conteudo, keep_vba=vba)
    except Exception as e:
        raise PlanilhaInvalida(f"Não consegui abrir o arquivo. Use a planilha do {perfil.nome}.") from e
    origem = {"conteudo": conteudo, "valores": None}   # para ler o resultado das fórmulas sob demanda (_ler)
    for aba in wb.worksheets:
        aba._origem_xlsx = origem
    if perfil.aba:
        if perfil.aba not in wb.sheetnames:
            raise PlanilhaInvalida(f"O arquivo não tem a aba '{perfil.aba}'. Envie a planilha baixada do {perfil.nome} em "
                                   f"'Preços e automatização → Alterar preços em Excel'.")
        ws = wb[perfil.aba]
        return wb, ws, _colunas(ws, perfil)
    erro = None
    for ws in wb.worksheets:
        try:
            return wb, ws, _colunas(ws, perfil)
        except PlanilhaInvalida as e:
            erro = erro or e
    raise erro or PlanilhaInvalida(f"Não achei a planilha do {perfil.nome} neste arquivo.")


def _valor(ws, cols, row: int, nome: str):
    return _ler(ws, row, cols[nome]) if nome in cols else None


def _anuncios(ws, cols, perfil: Perfil = ML):
    """Linhas de anúncio de verdade (as de cabeçalho/ajuda não têm um código de anúncio válido).
    Shopee (sku_basta): também vale a linha com SKU e sem ID, desde que o SKU não seja o próprio rótulo da coluna."""
    rotulos_sku = perfil.nomes.get("SKU", set())
    for row in range(cols.get("_LINHA", 1) + 1, ws.max_row + 1):
        item = _txt(_ler(ws, row, cols["ITEM_ID"])) if "ITEM_ID" in cols else ""
        if perfil.id_valido.fullmatch(item):
            yield row, item
        elif perfil.sku_basta and "SKU" in cols:
            sku = _txt(_ler(ws, row, cols["SKU"]))
            if sku and _norm(sku) not in rotulos_sku:
                yield row, ""


def _info(ws, cols, row: int, item: str, perfil: Perfil = ML) -> dict:
    sale = _numero(_valor(ws, cols, row, "SALE_PRICE")) if perfil.usa_promocao else None
    return {
        "linha": row,
        "item_id": item,
        "variacao_id": _txt(_valor(ws, cols, row, "VARIATION_ID")),
        "sku": _txt(_valor(ws, cols, row, "SKU")) or _txt(_valor(ws, cols, row, "PARENT_SKU")),
        "titulo": _txt(_valor(ws, cols, row, "TITLE")),
        "preco_atual": _numero(_ler(ws, row, cols["PRICE"])),
        "promocao_atual": sale,
        "status": _txt(_valor(ws, cols, row, "STATUS")),
        "tem_coluna_promocao": perfil.usa_promocao and "SALE_PRICE" in cols,
    }


def _linhas_da_busca(ws, cols, busca: str, perfil: Perfil = ML) -> list:
    """Todas as linhas (linha, item_id) que a busca atinge: SKU igual, código do anúncio igual, ou (Shopee) SKU principal igual.
    SKU repetido / anúncio com variações = várias linhas, e todas entram. Na Shopee, o SKU principal vale para o produto
    inteiro: entram também as outras variações do mesmo ID de produto."""
    b = (busca or "").strip().upper()
    if not b:
        raise BuscaInvalida(f"Digite {perfil.pedido}.")
    todos = list(_anuncios(ws, cols, perfil))
    achados, produtos = [], set()
    for row, item in todos:
        sku = _txt(_valor(ws, cols, row, "SKU")).upper()
        principal = _txt(_valor(ws, cols, row, "PARENT_SKU")).upper() if perfil.busca_sku_principal else ""
        por_principal = bool(principal) and principal == b
        if por_principal and item:
            produtos.add(item)
        if sku == b or item.upper() == b or por_principal:
            achados.append((row, item))
    if produtos:
        ja = {r for r, _ in achados}
        achados += [(r, i) for r, i in todos if i in produtos and r not in ja]
        achados.sort()
    if not achados:
        raise BuscaInvalida(f"Não encontrei '{busca.strip()}' nesta planilha. Confira {perfil.pedido}.")
    return achados


def _linhas_por_numero(ws, cols, linhas, perfil: Perfil = ML) -> list:
    """Linhas (linha, item_id) escolhidas pelo número da linha na planilha (seleção em grupo da aba Tabela)."""
    pedidas = {int(x) for x in linhas}
    achados = [(row, item) for row, item in _anuncios(ws, cols, perfil) if row in pedidas]
    if not achados:
        raise BuscaInvalida("Não encontrei as linhas selecionadas nesta planilha. Atualize a tabela e selecione de novo.")
    return achados


def _achar(ws, cols, busca: str, perfil: Perfil = ML) -> dict:
    """Dados da primeira linha achada + quantas linhas a busca atinge (`total_linhas`) e quais são (`linhas`)."""
    achados = _linhas_da_busca(ws, cols, busca, perfil)
    row, item = achados[0]
    info = _info(ws, cols, row, item, perfil)
    info["total_linhas"] = len(achados)
    info["linhas"] = [r for r, _ in achados]
    return info


# ------------------------------------------------------------------ operações
def resumo(ws, cols, perfil: Perfil = ML) -> dict:
    """Diz quantos anúncios a planilha tem."""
    total = sum(1 for _ in _anuncios(ws, cols, perfil))
    outro = SHOPEE if perfil.chave == "mercado_livre" else ML
    ids = [_txt(_ler(ws, r, cols["ITEM_ID"])) for r in range(cols.get("_LINHA", 1) + 1, ws.max_row + 1)] \
        if "ITEM_ID" in cols else []
    if not any(perfil.id_valido.fullmatch(i) for i in ids) and any(outro.id_valido.fullmatch(i) for i in ids):
        raise PlanilhaInvalida(f"Este arquivo é a planilha do {outro.nome}, mas o marketplace escolhido é {perfil.nome}. "
                               f"Troque o campo Marketplace para {outro.nome} ou conecte a planilha correta do {perfil.nome}.")
    if not total and not perfil.propria:   # a planilha comum pode começar só com o cabeçalho
        raise PlanilhaInvalida("Não encontrei anúncios nesta planilha.")
    return {"total_anuncios": total, "tem_coluna_promocao": perfil.usa_promocao and "SALE_PRICE" in cols}


def _preco(v, nome: str) -> float:
    try:
        x = float(v)
    except (TypeError, ValueError):
        raise BuscaInvalida(f"{nome} inválido.")
    if not math.isfinite(x) or x <= 0:
        raise BuscaInvalida(f"{nome} precisa ser maior que zero.")
    return round(x, 2)


def _verificar(original: bytes, novo: bytes, esperados: set) -> list[str]:
    """Confere que a ÚNICA diferença entre os dois arquivos são as células de preço gravadas."""
    a = _carregar_wb(original)
    b = _carregar_wb(novo)
    if a.sheetnames != b.sheetnames:
        return ["as abas do arquivo pronto são diferentes das do original"]
    dif = []
    for wa in a.worksheets:
        wb_ = b[wa.title]
        for r, (ra, rb) in enumerate(zip_longest(wa.iter_rows(values_only=True), wb_.iter_rows(values_only=True),
                                                 fillvalue=()), start=1):
            if ra == rb:
                continue
            for c in range(max(len(ra), len(rb))):
                va = ra[c] if c < len(ra) else None
                vb = rb[c] if c < len(rb) else None
                if va == "":   # o Excel regrava texto vazio como célula vazia: não é mudança de verdade
                    va = None
                if vb == "":
                    vb = None
                if va != vb and (wa.title, r, c + 1) not in esperados:
                    dif.append(f"{wa.title}!{wa.cell(r, c + 1).coordinate}")
    return dif


_LINHA_COMPLETA = re.compile(rb'<row\b[^>]*?\sr="(\d+)"[^>]*?(?<!/)>.*?</row>', re.S)
_CELULA_XML = re.compile(rb'<c\b[^>]*?/>|<c\b[^>]*>.*?</c>', re.S)


def _verificar_rapido(original: bytes, novo: bytes, caminho: str, celulas: list) -> list[str]:
    """Mesma garantia de _verificar (só as células de preço gravadas mudaram), mas comparando os bytes do arquivo: tudo que
    não é a aba editada tem de ser idêntico, e na aba só podem mudar as células gravadas. Não abre a planilha de novo."""
    esperados = {}
    for l, c in celulas:
        esperados.setdefault(l, set()).add(f"{get_column_letter(c)}{l}".encode())
    za, zb = zipfile.ZipFile(io.BytesIO(original)), zipfile.ZipFile(io.BytesIO(novo))
    with za, zb:
        if za.namelist() != zb.namelist():
            return ["a estrutura do arquivo pronto é diferente da original"]
        for nome in za.namelist():
            if nome != caminho and za.read(nome) != zb.read(nome):
                return [f"o conteúdo de {nome} mudou"]
        xa, xb = za.read(caminho), zb.read(caminho)
    dif = []

    def separar(xml: bytes):
        """(xml sem as linhas gravadas, {n: bytes da linha}) numa única passada pelo XML da aba."""
        resto, achadas, pos = [], {}, 0
        for m in _LINHA_COMPLETA.finditer(xml):
            n = int(m.group(1))
            if n in esperados:
                resto.append(xml[pos:m.start()])
                achadas[n] = m.group(0)
                pos = m.end()
        resto.append(xml[pos:])
        return b"".join(resto), achadas

    xa, linhas_a = separar(xa)
    xb, linhas_b = separar(xb)
    for n in sorted(esperados):
        ra, rb = linhas_a.get(n), linhas_b.get(n)
        if ra is None or rb is None:
            return [f"linha {n} não encontrada"]
        if ra[:ra.index(b">") + 1] != rb[:rb.index(b">") + 1]:
            dif.append(f"linha {n}")
        ca = {re.search(rb'\sr="([A-Z]+\d+)"', c.split(b">", 1)[0]).group(1): c for c in _CELULA_XML.findall(ra)}
        cb = {re.search(rb'\sr="([A-Z]+\d+)"', c.split(b">", 1)[0]).group(1): c for c in _CELULA_XML.findall(rb)}
        for ref in set(ca) | set(cb):
            if ca.get(ref) != cb.get(ref) and ref not in esperados[n]:
                dif.append(ref.decode())
    if xa != xb:   # o resto da aba (outras linhas, formatação, painéis...) tem de ser byte a byte igual
        dif.append("outras partes da aba mudaram")
    return dif


def _reais(x: float) -> str:
    return "R$ " + f"{x:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _validar_regras(ws, cols, achados: list, cheio: float, perfil: Perfil) -> None:
    """Regras do marketplace para a planilha subir em massa sem erro. Confere ANTES de gravar qualquer célula."""
    if (perfil.preco_min is not None and cheio < perfil.preco_min) or (perfil.preco_max is not None and cheio > perfil.preco_max):
        raise BuscaInvalida(f"{perfil.nome} só aceita preço de {_reais(perfil.preco_min or 0)} a "
                            f"{_reais(perfil.preco_max or 0)}. O preço calculado ({_reais(cheio)}) faria o envio em massa dar erro.")
    if not perfil.razao_max:
        return
    mudam = {r for r, _ in achados}
    produtos = {i for _, i in achados if i}
    precos: dict = {p: [] for p in produtos}
    for row, item in _anuncios(ws, cols, perfil):
        if item in precos:
            p = cheio if row in mudam else _numero(_ler(ws, row, cols["PRICE"]))
            if p:
                precos[item].append(p)
    for prod, lista in precos.items():
        if len(lista) > 1 and max(lista) / min(lista) > perfil.razao_max:
            raise BuscaInvalida(f"Com esse preço, no produto {prod} a variação mais cara ({_reais(max(lista))}) ficaria mais de "
                                f"{perfil.razao_max:g}x o preço da mais barata ({_reais(min(lista))}). A {perfil.nome} recusa isso "
                                "no envio em massa. Grave o SKU do produto (todas as variações juntas) ou ajuste o preço.")


def _nova_linha(ws, cols, sku: str, nome: str, celulas: list) -> int:
    """Planilha comum: SKU que ainda não existe vira uma linha nova no fim (SKU e, se veio, o nome)."""
    r = ws.max_row
    while r > cols.get("_LINHA", 1) and not _txt(ws.cell(r, cols["SKU"]).value):
        r -= 1
    row = r + 1
    ws.cell(row, cols["SKU"]).value = sku.strip()
    celulas.append((row, cols["SKU"]))
    if (nome or "").strip() and "TITLE" in cols:
        ws.cell(row, cols["TITLE"]).value = nome.strip()
        celulas.append((row, cols["TITLE"]))
    return row


def aplicar(ws, cols, busca: str, preco_cheio, preco_promocional, perfil: Perfil = ML, nome: str = "", linhas=None) -> dict:
    """Grava o preço em TODAS as linhas que a busca atinge, em qualquer planilha que tenha cell(linha, coluna).value
    (openpyxl ou a Tabela do módulo arquivo). Mercado Livre grava também o promocional; Shopee e TikTok só o preço
    (se a planilha tiver a coluna de promoção, ela é preenchida)."""
    cheio = _preco(preco_cheio, "Preço cheio")
    promo = None if preco_promocional in (None, "") else _preco(preco_promocional, "Preço promocional")
    avisos, celulas = [], []
    if linhas:   # seleção em grupo: grava só nessas linhas (pelo número da linha), sem procurar por SKU/código
        achados = _linhas_por_numero(ws, cols, linhas, perfil)
    else:
        try:
            achados = _linhas_da_busca(ws, cols, busca, perfil)
        except BuscaInvalida:
            if not perfil.propria or not (busca or "").strip():
                raise
            achados = [(_nova_linha(ws, cols, busca, nome, celulas), "")]
            avisos.append("SKU novo: foi adicionada uma linha no fim da planilha.")
    _validar_regras(ws, cols, achados, cheio, perfil)
    antes_todas = [_info(ws, cols, r, i, perfil) for r, i in achados]
    antes = antes_todas[0]

    promo_valido = promo is not None and promo < cheio
    gravar_promo = perfil.usa_promocao and "SALE_PRICE" in cols and promo_valido
    limpar_promo = (perfil.chave == "mercado_livre" or perfil.propria) and "SALE_PRICE" in cols and not promo_valido
    vazio_promo = "-" if perfil.chave == "mercado_livre" else None   # ML usa "-"; planilha comum fica em branco
    if perfil.usa_promocao:
        if "SALE_PRICE" not in cols:
            if perfil.chave == "mercado_livre":
                avisos.append("Esta planilha não tem a coluna 'Preço em promoção': só o preço cheio foi gravado.")
        elif not promo_valido:
            avisos.append("O preço promocional não é menor que o cheio (desconto zerado): só o preço cheio foi gravado.")
    for row, _ in achados:
        _gravar_preco(ws, row, cols["PRICE"], cheio)
        celulas.append((row, cols["PRICE"]))
        if gravar_promo:
            _gravar_preco(ws, row, cols["SALE_PRICE"], promo)
            celulas.append((row, cols["SALE_PRICE"]))
        elif limpar_promo and _numero(_ler(ws, row, cols["SALE_PRICE"])) is not None:
            ws.cell(row, cols["SALE_PRICE"]).value = vazio_promo   # sem promo: volta ao vazio (não fica promo antiga valendo)
            celulas.append((row, cols["SALE_PRICE"]))
    if not gravar_promo and any(a["promocao_atual"] is not None and a["promocao_atual"] >= cheio for a in antes_todas):
        avisos.append("A promoção que já está na planilha não é menor que o novo preço cheio: confira antes de subir.")
    if len(achados) > 1 and not linhas:
        avisos.append(f"O SKU/código está em {len(achados)} linhas (variações ou SKU repetido): o mesmo preço foi gravado em todas.")
    depois = {**antes, "preco_atual": cheio, "promocao_atual": promo if gravar_promo else antes["promocao_atual"]}
    depois_todas = [_info(ws, cols, r, i, perfil) for r, i in achados]   # como as linhas ficaram (a Tabela online atualiza o cache com isto)
    return {"antes": antes, "antes_todas": antes_todas, "depois": depois, "depois_todas": depois_todas, "linhas_alteradas": len(achados),
            "gravou_promocional": gravar_promo, "avisos": avisos, "celulas": celulas}


class _SemPatch(Exception):
    """O arquivo tem uma estrutura que a gravação direta não cobre: usa o caminho antigo (openpyxl)."""


_LINHA_XML = re.compile(rb'<row\b[^>]*?\sr="(\d+)"[^>]*?(/?)>')


def _caminho_da_aba(zf: zipfile.ZipFile, titulo: str) -> str:
    wbxml = zf.read("xl/workbook.xml").decode("utf-8")
    rid = None
    for m in re.finditer(r"<(?:\w+:)?sheet\b[^>]*>", wbxml):
        nome = re.search(r'\bname="([^"]*)"', m.group(0))
        if nome and html.unescape(nome.group(1)) == titulo:
            r_ = re.search(r'\b\w+:id="([^"]*)"', m.group(0))
            rid = r_.group(1) if r_ else None
            break
    if not rid:
        raise _SemPatch()
    rels = zf.read("xl/_rels/workbook.xml.rels").decode("utf-8")
    for m in re.finditer(r"<Relationship\b[^>]*>", rels):
        if re.search(r'\bId="' + re.escape(rid) + r'"', m.group(0)):
            alvo = re.search(r'\bTarget="([^"]*)"', m.group(0))
            if not alvo:
                break
            t = html.unescape(alvo.group(1))
            return posixpath.normpath(t.lstrip("/") if t.startswith("/") else "xl/" + t)
    raise _SemPatch()


def _xml_celula(ref: bytes, estilo: bytes, v) -> bytes:
    s = (b' s="' + estilo + b'"') if estilo else b""
    if v is None:   # célula esvaziada (promo da planilha comum): mantém só o estilo
        return b'<c r="' + ref + b'"' + s + b"/>"
    if isinstance(v, str):   # preço guardado como texto (Shopee, TikTok)
        return b'<c r="' + ref + b'"' + s + b' t="inlineStr"><is><t>' + escape(v).encode("utf-8") + b"</t></is></c>"
    return b'<c r="' + ref + b'"' + s + b"><v>" + repr(float(v)).encode() + b"</v></c>"


def _por_celula(dentro: bytes, col: int, row: int, valor) -> bytes:
    """Troca (ou cria, na ordem certa) uma célula dentro do XML de uma linha, mantendo o estilo que ela já tinha."""
    ref = f"{get_column_letter(col)}{row}".encode()
    m = re.search(rb'<c\b(?=[^>]*\sr="' + ref + rb'")[^>]*?(?:/>|>.*?</c>)', dentro, re.S)
    if m:
        est = re.search(rb'\ss="(\d+)"', m.group(0).split(b">", 1)[0])
        return dentro[:m.start()] + _xml_celula(ref, est.group(1) if est else b"", valor) + dentro[m.end():]
    pos = len(dentro)
    for o in re.finditer(rb'<c\b[^>]*?\sr="([A-Z]+)\d+"', dentro):
        if column_index_from_string(o.group(1).decode()) > col:
            pos = o.start()
            break
    return dentro[:pos] + _xml_celula(ref, b"", valor) + dentro[pos:]


def _patch_aba(xml: bytes, novos: dict) -> bytes:
    por_linha: dict = {}
    for (l, c), v in novos.items():
        por_linha.setdefault(l, {})[c] = v
    achadas = {}
    for m in _LINHA_XML.finditer(xml):
        n = int(m.group(1))
        if n in por_linha:
            achadas[n] = m
    if len(achadas) != len(por_linha):
        raise _SemPatch()
    for n in sorted(achadas, reverse=True):   # de baixo para cima: as posições das linhas de cima não mudam
        m = achadas[n]
        fim = xml.find(b"</row>", m.end())
        if m.group(2) or fim < 0:
            raise _SemPatch()
        dentro = xml[m.end():fim]
        for c in sorted(por_linha[n]):
            dentro = _por_celula(dentro, c, n, por_linha[n][c])
        xml = xml[:m.end()] + dentro + xml[fim:]
    return xml


def _gravar_no_xml(conteudo: bytes, titulo: str, novos: dict) -> bytes:
    """Grava SÓ as células de preço direto no XML da aba e copia todo o resto do arquivo exatamente como veio: fórmulas COM o
    resultado guardado (título, status...), formatação, validações, imagens, abas de ajuda. É o que mantém a planilha igual à que
    você enviou para o envio em massa do marketplace. (O openpyxl, ao salvar, apagava o resultado de todas as fórmulas.)"""
    try:
        zin = zipfile.ZipFile(io.BytesIO(conteudo))
    except zipfile.BadZipFile:
        raise _SemPatch()
    with zin:
        try:
            caminho = _caminho_da_aba(zin, titulo)
            novo_xml = _patch_aba(zin.read(caminho), novos)
        except (KeyError, ValueError):
            raise _SemPatch()
        saida = io.BytesIO()
        with zipfile.ZipFile(saida, "w", zipfile.ZIP_DEFLATED) as zout:
            for item in zin.infolist():
                zout.writestr(item, novo_xml if item.filename == caminho else zin.read(item.filename))
    return saida.getvalue(), caminho


# Planilha já aberta, reaproveitada entre uma gravação e a seguinte (só o robô usa: slot != None).
# Abrir o .xlsx inteiro com o openpyxl (duas vezes: valores + resultado das fórmulas) era o que mais demorava em cada SKU.
# A chave é o SHA-1 dos bytes do arquivo: se o arquivo mudou por fora (Excel, outro programa), não bate e a planilha é aberta de novo.
_ABERTAS: dict = {}          # slot -> (sha1 dos bytes, vba, perfil.chave, wb, ws, cols)
_TRAVA_ABERTAS = threading.Lock()
_MAX_SLOTS = 4


def limpar_cache() -> None:
    """Solta as planilhas guardadas (o robô chama ao terminar o lote, para liberar memória)."""
    with _TRAVA_ABERTAS:
        _ABERTAS.clear()


def _abrir_reaproveitando(conteudo: bytes, vba: bool, perfil: Perfil, slot):
    """(wb, ws, cols). Com `slot`, tenta reaproveitar a planilha aberta na gravação anterior do mesmo destino.
    A planilha guardada sai do cache ao ser usada (se algo falhar no meio, ela não volta com valores pela metade)."""
    if not slot:
        return _abrir(conteudo, vba, perfil)
    h = hashlib.sha1(conteudo).hexdigest()
    with _TRAVA_ABERTAS:
        achou = _ABERTAS.pop(slot, None)
    if achou and achou[:3] == (h, vba, perfil.chave):
        return achou[3], achou[4], achou[5]
    return _abrir(conteudo, vba, perfil)


def _guardar_aberta(slot, pronto: bytes, vba: bool, perfil: Perfil, wb, ws, cols) -> None:
    for aba in wb.worksheets:   # o dict de origem é o mesmo em todas as abas: a leitura sob demanda passa a olhar o arquivo novo
        origem = getattr(aba, "_origem_xlsx", None)
        if origem is not None:
            origem["conteudo"] = pronto
            break
    with _TRAVA_ABERTAS:
        if slot not in _ABERTAS and len(_ABERTAS) >= _MAX_SLOTS:
            _ABERTAS.clear()
        _ABERTAS[slot] = (hashlib.sha1(pronto).hexdigest(), vba, perfil.chave, wb, ws, cols)


def gravar(conteudo: bytes, busca: str, preco_cheio, preco_promocional, vba: bool = False, perfil: Perfil = ML, nome: str = "", linhas=None, slot=None):
    """Grava na planilha .xlsx/.xlsm e devolve (arquivo_pronto, resultado). Confere que só as células de preço mudaram."""
    wb, ws, cols = _abrir_reaproveitando(conteudo, vba, perfil, slot)
    r = aplicar(ws, cols, busca, preco_cheio, preco_promocional, perfil, nome, linhas)
    novos = {(l, c): ws.cell(l, c).value for l, c in r["celulas"]}
    via_xml = False
    dif = None   # None = ainda não conferido (ou a conferência rápida achou algo: refaz do jeito completo antes de reprovar)
    try:
        pronto, caminho = _gravar_no_xml(conteudo, ws.title, novos)
        via_xml = True
        try:
            rapido = _verificar_rapido(conteudo, pronto, caminho, r["celulas"])
            dif = rapido if not rapido else None
        except Exception:   # algo fora do padrão: confere do jeito completo (mais lento)
            dif = None
    except _SemPatch:   # estrutura incomum: salva pelo openpyxl (as fórmulas ficam, mas sem o resultado guardado)
        via_xml = False
        saida = io.BytesIO()
        wb.save(saida)
        pronto = saida.getvalue()
    if dif is None:
        dif = _verificar(conteudo, pronto, {(ws.title, l, c) for l, c in r["celulas"]})
    r["conferencia_ok"] = not dif
    r["diferencas"] = dif[:10]
    if slot and via_xml and not dif:   # só guarda quando o arquivo novo é exatamente o que está na memória
        _guardar_aberta(slot, pronto, vba, perfil, wb, ws, cols)
    return pronto, r
