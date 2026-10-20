"""
Fonte de dados de TESTE: lê os dados do produto de um arquivo CSV ou XLSX, no mesmo formato (DadosProduto)
que os coletores reais (Citel, Econet, Confaz) vão entregar depois. Assim o resto do robô
já roda e é testado antes de ligar as ferramentas web.

Formatos aceitos: .csv (separador ; , ou tab; decimal com vírgula ou ponto) e .xlsx / .xlsm
(lê a primeira aba; a primeira linha são os nomes das colunas).

Colunas (as mesmas nos dois formatos):
  sku; codigo_fabricante; unitario; aliq_icms; ncm; frete; ipi; st_status; mva; confaz_status

  aliq_icms     em % (12 = 12%)
  frete, ipi, mva  em FRAÇÃO (0.03 = 3%). "3%" é lido como ilegível de propósito.
  st_status     COM_ST | SEM_ST | FALHOU | AMBIGUO
  confaz_status BASE_REDUZIDA | FORA_DA_LISTA | CONDICIONAL | FALHOU   (OPCIONAL: veja abaixo)
Célula vazia = dado ausente (o validador manda a linha para REVISAR).

Base Reduzida (Confaz): com config.USAR_COLETOR_CONFAZ = True (padrão), o status vem da consulta do NCM no rpa/confaz.html
(coletor_confaz) e a coluna confaz_status é ignorada. Ela só vale para linhas SEM NCM. Se o confaz.html sumir ou estiver
ilegível, a linha vai para REVISAR (FALHOU): nunca cai de volta na coluna do arquivo.

Colunas EXTRAS, só para o Mercado Livre (a Shopee e o TikTok ignoram):
  ml_comissao     comissão do ML do produto, em FRAÇÃO (0.12 = 12%) — varia por categoria, o robô não assume padrão
  frete_ml        frete do ML em R$ já conhecido (se > 0, vale no lugar de peso + faixa)
  ml_peso         peso da tabela de frete do ML (ex.: "De 0,5 a 1 kg"; aceita "0,5 a 1 kg")
  ml_faixa_valor  faixa de valor da tabela de frete do ML (ex.: "49 a R$ 78,99"; aceita "49 a 78,99")
  Sem frete_ml, são obrigatórios ml_peso E ml_faixa_valor.
"""
import csv
import io
import re
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

from rpa import config
from rpa import modelos as m
from rpa.coletor_confaz import ColetorConfaz

EXTENSOES = (".csv", ".xlsx", ".xlsm")
_NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
_NS_REL = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"


def _num(txt) -> float | None:
    if txt is None:
        return None
    t = str(txt).strip()
    if not t:
        return None
    if "," in t:
        t = t.replace(".", "").replace(",", ".")
    try:
        return float(t)
    except ValueError:
        return None


def _status(txt: str, validos: set, padrao: str) -> str:
    t = (txt or "").strip().upper()
    return t if t in validos else padrao


def _indice_coluna(ref: str) -> int:
    letras = re.match(r"[A-Za-z]+", ref or "")
    n = 0
    for ch in (letras.group().upper() if letras else "A"):
        n = n * 26 + (ord(ch) - 64)
    return n - 1


def _texto_celula(c, compartilhadas: list[str]) -> str:
    tipo = c.get("t")
    if tipo == "inlineStr":
        return "".join(t.text or "" for t in c.iter(_NS + "t"))
    v = c.find(_NS + "v")
    if v is None or v.text is None:
        return ""
    if tipo == "s":
        try:
            return compartilhadas[int(v.text)]
        except (ValueError, IndexError):
            return ""
    return v.text


def _caminho_primeira_aba(z: zipfile.ZipFile) -> str:
    """Primeira aba na ordem do workbook; se não achar, a primeira sheet*.xml."""
    try:
        wb = ET.fromstring(z.read("xl/workbook.xml"))
        primeira = wb.find(f"{_NS}sheets/{_NS}sheet")
        rid = primeira.get(_NS_REL + "id")
        rels = ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))
        for rel in rels:
            if rel.get("Id") == rid:
                alvo = rel.get("Target", "").lstrip("/")
                return alvo if alvo.startswith("xl/") else "xl/" + alvo
    except (KeyError, AttributeError, ET.ParseError):
        pass
    abas = sorted(n for n in z.namelist() if n.startswith("xl/worksheets/sheet") and n.endswith(".xml"))
    if not abas:
        raise ValueError("Não achei nenhuma aba na planilha.")
    return abas[0]


def _linhas_xlsx(caminho) -> list[dict]:
    """Lê a primeira aba do .xlsx sem depender de bibliotecas externas (e sem reclamar de formatações estranhas)."""
    try:
        with zipfile.ZipFile(caminho) as z:
            compartilhadas: list[str] = []
            if "xl/sharedStrings.xml" in z.namelist():
                for si in ET.fromstring(z.read("xl/sharedStrings.xml")).iter(_NS + "si"):
                    compartilhadas.append("".join(t.text or "" for t in si.iter(_NS + "t")))
            raiz = ET.fromstring(z.read(_caminho_primeira_aba(z)))
    except zipfile.BadZipFile:
        raise ValueError("O arquivo .xlsx está corrompido ou não é uma planilha do Excel.")
    except ET.ParseError:
        raise ValueError("Não consegui ler o conteúdo da planilha.")

    tabela: list[list[str]] = []
    for linha in raiz.iter(_NS + "row"):
        valores: list[str] = []
        for c in linha.findall(_NS + "c"):
            i = _indice_coluna(c.get("r", ""))
            while len(valores) <= i:
                valores.append("")
            valores[i] = _texto_celula(c, compartilhadas).strip()
        if any(valores):
            tabela.append(valores)
    if not tabela:
        return []
    cab = [(h or "").strip().lower() for h in tabela[0]]
    saida = []
    for valores in tabela[1:]:
        saida.append({cab[i]: (valores[i] if i < len(valores) else "") for i in range(len(cab)) if cab[i]})
    return saida


def _linhas_csv(caminho) -> list[dict]:
    bruto = Path(caminho).read_bytes()
    try:
        texto = bruto.decode("utf-8-sig")
    except UnicodeDecodeError:
        texto = bruto.decode("cp1252")
    primeira = texto.split("\n", 1)[0]
    delim = max((";", ",", "\t"), key=primeira.count)
    leitor = csv.DictReader(io.StringIO(texto, newline=""), delimiter=delim)
    return [{(k or "").strip().lower(): (v or "").strip() for k, v in row.items()} for row in leitor]


def _sku_limpo(sku: str) -> str:
    """No Excel o SKU numérico pode vir como 58708.0; tira o '.0' (SKU com zero à esquerda, em texto, fica como está)."""
    s = (sku or "").strip()
    return s[:-2] if re.fullmatch(r"\d+\.0", s) else s


class FonteCSV:
    """Lê .csv ou .xlsx (o nome da classe fica por compatibilidade com o resto do robô)."""

    def __init__(self, caminho, usar_confaz: bool | None = None):
        """usar_confaz: None = segue config.USAR_COLETOR_CONFAZ; True/False força (os testes usam False)."""
        if usar_confaz is None:
            usar_confaz = config.USAR_COLETOR_CONFAZ
        self._confaz = ColetorConfaz() if usar_confaz else None   # lê o confaz.html uma vez por lote
        ext = Path(caminho).suffix.lower()
        if ext in (".xlsx", ".xlsm"):
            linhas = _linhas_xlsx(caminho)
        else:
            linhas = _linhas_csv(caminho)
        self._linhas: dict[str, dict] = {}
        for row in linhas:
            sku = _sku_limpo(row.get("sku", ""))
            if sku:
                row["sku"] = sku
                self._linhas[sku.upper()] = row

    def skus(self) -> set[str]:
        """SKUs presentes no arquivo (em maiúsculas)."""
        return set(self._linhas)

    def obter(self, sku: str) -> m.DadosProduto | None:
        row = self._linhas.get((sku or "").strip().upper())
        if row is None:
            return None
        st = _status(row.get("st_status", ""),
                     {m.COM_ST, m.SEM_ST, m.ST_FALHOU, m.ST_AMBIGUO}, m.ST_NAO_CONSULTADO)
        ncm = row.get("ncm") or None
        if self._confaz is not None and ncm:
            confaz = self._confaz.consultar(ncm)          # NCM -> Confaz 52/91 (Anexos I e II em vigor)
        else:
            confaz = m.ResultadoConfaz(status=_status(
                row.get("confaz_status", ""),
                {m.BASE_REDUZIDA, m.FORA_DA_LISTA, m.CONDICIONAL, m.CONFAZ_FALHOU}, m.CONFAZ_NAO_CONSULTADO))
        return m.DadosProduto(
            sku=sku,
            codigo_fabricante=row.get("codigo_fabricante") or None,
            unitario=_num(row.get("unitario")),
            aliq_icms=_num(row.get("aliq_icms")),
            ncm=ncm,
            perc_frete=_num(row.get("frete")),
            perc_ipi=_num(row.get("ipi")),
            st=m.ResultadoST(status=st, mva=_num(row.get("mva"))),
            confaz=confaz,
            ml_comissao=_num(row.get("ml_comissao")),
            ml_peso=row.get("ml_peso") or None,
            ml_faixa_valor=row.get("ml_faixa_valor") or None,
            frete_ml=_num(row.get("frete_ml")),
        )
