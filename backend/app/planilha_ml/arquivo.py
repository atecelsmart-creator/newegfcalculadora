"""
Lê e grava a planilha de preços do marketplace (Mercado Livre ou Shopee) direto do arquivo no computador, em qualquer formato do Excel:

  .xlsx / .xlsm        -> openpyxl (as macros do .xlsm são preservadas)
  .csv                 -> texto (detecta separador, acentuação e vírgula decimal)
  .xls / .xlsb / .ods  -> pelo Microsoft Excel instalado no PC (COM). Se o arquivo já estiver aberto no Excel,
                          grava nele mesmo, ao vivo (vale para todos os formatos).

Antes da primeira gravação fica uma cópia intacta ao lado do arquivo (<nome>_ORIGINAL_BACKUP.<ext>).
A regra de gravação é a mesma para todos os formatos: editor.aplicar (o Perfil diz quais colunas e o que gravar).
"""
from __future__ import annotations

import csv
import io
import os
import re
import shutil
import time
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import unquote

from app.planilha_ml import editor
from app.planilha_ml.editor import ML, BuscaInvalida, Perfil, PlanilhaInvalida

EXT_XLSX = {".xlsx", ".xlsm"}
EXT_CSV = {".csv"}
EXT_EXCEL = {".xls", ".xlsb", ".ods"}
EXTENSOES = EXT_XLSX | EXT_CSV | EXT_EXCEL


class ArquivoOcupado(Exception):
    """O arquivo está travado por outro programa. A mensagem já é para mostrar na tela."""


# ------------------------------------------------------------------ planilha em memória (CSV e Excel via COM)
class _Cel:
    __slots__ = ("_t", "_r", "column")

    def __init__(self, t, r, c):
        self._t, self._r, self.column = t, r, c

    @property
    def value(self):
        d = self._t.dados
        if self._r > len(d) or self.column > len(d[self._r - 1]):
            return None
        return d[self._r - 1][self.column - 1]

    @value.setter
    def value(self, v):
        d = self._t.dados
        while len(d) < self._r:
            d.append([])
        linha = d[self._r - 1]
        linha.extend([None] * (self.column - len(linha)))
        linha[self.column - 1] = v
        self._t.mudou[(self._r, self.column)] = v


class Tabela:
    """Mesma interface mínima do openpyxl que o editor usa: cell(), max_row e ws[linha]."""

    def __init__(self, dados):
        self.dados, self.mudou = dados, {}

    @property
    def max_row(self):
        return len(self.dados)

    def cell(self, r, c):
        return _Cel(self, r, c)

    def __getitem__(self, r):
        n = max((len(l) for l in self.dados), default=0)
        return [_Cel(self, r, c) for c in range(1, n + 1)]


# ------------------------------------------------------------------ CSV
_NUM = re.compile(r"^-?\d+(?:[.,]\d+)?$")


def _tipar(s: str):
    t = s.strip()
    return float(t.replace(",", ".")) if _NUM.match(t) and not re.match(r"^-?0\d", t) else s


def _ler_csv(b: bytes) -> dict:
    bom = b.startswith(b"\xef\xbb\xbf")
    for enc in ("utf-8", "cp1252"):
        try:
            texto = b.decode("utf-8-sig" if enc == "utf-8" else enc)
            break
        except UnicodeDecodeError:
            continue
    else:
        enc, texto = "latin-1", b.decode("latin-1")
    primeira = texto.split("\n", 1)[0]
    delim = max((";", ",", "\t"), key=primeira.count)
    brutos = list(csv.reader(io.StringIO(texto, newline=""), delimiter=delim))
    return {"brutos": brutos, "enc": enc, "bom": bom, "delim": delim, "eol": "\r\n" if "\r\n" in texto else "\n"}


def _tabela_csv(info: dict) -> Tabela:
    return Tabela([[_tipar(c) for c in l] for l in info["brutos"]])


def _virgula(brutos, col: int, delim: str, linha_cab: int = 1) -> bool:
    """O arquivo usa vírgula como separador decimal? (olha os preços que já estão nele)"""
    for l in brutos[linha_cab:]:
        if col <= len(l):
            v = l[col - 1].strip()
            if re.fullmatch(r"\d+,\d+", v):
                return True
            if re.fullmatch(r"\d+\.\d+", v):
                return False
    return delim == ";"


def _gravar_csv(b: bytes, busca, cheio, promo, perfil: Perfil = ML, nome: str = "", linhas=None):
    info = _ler_csv(b)
    t = _tabela_csv(info)
    cols = editor._colunas(t, perfil)
    r = editor.aplicar(t, cols, busca, cheio, promo, perfil, nome, linhas)
    virg = _virgula(info["brutos"], cols["PRICE"], info["delim"], cols["_LINHA"])
    brutos = [list(l) for l in info["brutos"]]
    for (lin, col), v in t.mudou.items():
        linha = brutos[lin - 1]
        linha.extend([""] * (col - len(linha)))
        txt = "" if v is None else v if isinstance(v, str) and not editor._NUM_TXT.match(v.strip()) else f"{float(v):.2f}"
        linha[col - 1] = txt.replace(".", ",") if (virg and txt != v) else txt
    saida = io.StringIO(newline="")
    csv.writer(saida, delimiter=info["delim"], lineterminator=info["eol"]).writerows(brutos)
    texto = saida.getvalue()
    if info["enc"] == "utf-8":
        pronto = texto.encode("utf-8-sig" if info["bom"] else "utf-8")
    else:
        pronto = texto.encode(info["enc"])

    # confere que a única diferença são as células de preço gravadas
    ant, novo, dif = _tabela_csv(info).dados, _tabela_csv(_ler_csv(pronto)).dados, []
    for i in range(max(len(ant), len(novo))):
        a = ant[i] if i < len(ant) else []
        n = novo[i] if i < len(novo) else []
        for j in range(max(len(a), len(n))):
            va = a[j] if j < len(a) else None
            vn = n[j] if j < len(n) else None
            va = None if va == "" else va
            vn = None if vn == "" else vn
            if va != vn and (i + 1, j + 1) not in t.mudou:
                dif.append(f"linha {i + 1}, coluna {j + 1}")
    r["conferencia_ok"] = not dif
    r["diferencas"] = dif[:10]
    return pronto, r


# ------------------------------------------------------------------ .xls / .xlsb / .ods pelo Excel instalado (COM)
@contextmanager
def _sessao_excel(p: Path):
    try:
        import pythoncom
        import win32com.client as w32
    except ImportError:
        raise PlanilhaInvalida("Para arquivos .xls, .xlsb e .ods a calculadora usa o Microsoft Excel instalado no PC. "
                               "Feche e abra o calculadora.bat (ele instala o componente pywin32) e tente de novo.")
    pythoncom.CoInitialize()
    app = wb = None
    novo = abriu = False
    try:
        try:   # Excel já aberto? Se o arquivo estiver aberto nele, usa o próprio (grava ao vivo)
            app = w32.GetActiveObject("Excel.Application")
            alvo = os.path.normcase(os.path.abspath(str(p)))
            for w in app.Workbooks:
                if os.path.normcase(os.path.abspath(w.FullName)) == alvo:
                    wb = w
                    break
        except Exception:
            app = None
        if wb is None:
            if app is None:
                app = w32.DispatchEx("Excel.Application")
                app.Visible = False
                app.DisplayAlerts = False
                novo = True
            wb = app.Workbooks.Open(str(p))
            abriu = True
        yield wb
    except (PlanilhaInvalida, BuscaInvalida, ArquivoOcupado):
        raise
    except Exception as e:
        raise PlanilhaInvalida("O Excel recusou a operação. Se ele estiver com uma célula em edição ou uma janela "
                               f"aberta, feche-a e tente de novo. ({e})")
    finally:
        try:
            if abriu and wb is not None:
                wb.Close(SaveChanges=False)
        except Exception:
            pass
        try:
            if novo and app is not None:
                app.Quit()
        except Exception:
            pass
        pythoncom.CoUninitialize()


def _tabela_excel(ws) -> Tabela:
    ur = ws.UsedRange
    v = ur.Value
    if v is None:
        v = ((None,),)
    elif not isinstance(v, tuple):
        v = ((v,),)
    dados = [[] for _ in range(ur.Row - 1)]
    for linha in v:
        dados.append([None] * (ur.Column - 1) + list(linha))
    return Tabela(dados)


def _localizar_aba(wb, perfil: Perfil):
    """Devolve (aba, tabela, colunas). Mercado Livre: aba 'Anúncios'. Shopee: a primeira aba que tiver as colunas."""
    if perfil.aba:
        try:
            ws = wb.Worksheets(perfil.aba)
        except Exception:
            ws = wb.Worksheets(1)
        t = _tabela_excel(ws)
        return ws, t, editor._colunas(t, perfil)
    erro = None
    for i in range(1, wb.Worksheets.Count + 1):
        ws = wb.Worksheets(i)
        t = _tabela_excel(ws)
        try:
            return ws, t, editor._colunas(t, perfil)
        except PlanilhaInvalida as e:
            erro = erro or e
    raise erro or PlanilhaInvalida(f"Não achei a planilha do {perfil.nome} neste arquivo.")


def _gravar_excel(p: Path, busca, cheio, promo, perfil: Perfil = ML, nome: str = "") -> dict:
    with _sessao_excel(p) as wb:
        ws, t, cols = _localizar_aba(wb, perfil)
        r = editor.aplicar(t, cols, busca, cheio, promo, perfil, nome)
        _backup(p)
        for (lin, col), v in t.mudou.items():
            ws.Cells(lin, col).Value = v
        wb.Save()
        dif = []
        for (lin, col), v in t.mudou.items():
            lido = ws.Cells(lin, col).Value
            try:   # o preço pode estar como número (Mercado Livre) ou como texto (Shopee, TikTok)
                ok = abs(float(str(lido).replace(",", ".")) - float(v)) <= 0.005
            except ValueError:
                ok = False
            if not ok:
                dif.append(str(ws.Cells(lin, col).Address(False, False)))
    for k in [k for k in _cache if k[0] == str(p)]:
        _cache.pop(k, None)
    r["conferencia_ok"] = not dif
    r["diferencas"] = dif[:10]
    return r


# ------------------------------------------------------------------ disco
def _aberto_no_excel(p: Path) -> bool:
    """O arquivo está aberto agora numa janela do Excel? (nesse caso o disco fica travado e grava-se pelo próprio Excel)"""
    if os.name != "nt":
        return False
    try:
        import pythoncom
        import win32com.client as w32
    except ImportError:
        return False
    pythoncom.CoInitialize()
    try:
        app = w32.GetActiveObject("Excel.Application")
        alvo = os.path.normcase(os.path.abspath(str(p)))
        return any(os.path.normcase(os.path.abspath(w.FullName)) == alvo for w in app.Workbooks)
    except Exception:
        return False
    finally:
        pythoncom.CoUninitialize()


def _ler_disco(p: Path) -> bytes:
    try:
        return p.read_bytes()
    except OSError as e:
        raise PlanilhaInvalida(f"Não consegui ler o arquivo ({e.strerror or e}).")


def _backup(p: Path) -> None:
    b = p.with_name(p.stem + "_ORIGINAL_BACKUP" + p.suffix)
    if not b.exists():
        try:
            shutil.copyfile(p, b)
        except OSError:
            pass


def _salvar(p: Path, pronto: bytes) -> None:
    """Troca o arquivo de forma atômica (grava num .tmp e substitui)."""
    _backup(p)
    tmp = p.with_name(p.name + ".tmp")
    try:
        tmp.write_bytes(pronto)
        os.replace(tmp, p)
    except PermissionError:
        tmp.unlink(missing_ok=True)
        raise ArquivoOcupado("Não consegui gravar: o arquivo está aberto no Excel. Feche-o e tente de novo.")
    except OSError as e:
        tmp.unlink(missing_ok=True)
        raise PlanilhaInvalida(f"Não consegui gravar no arquivo ({e.strerror or e}).")


_cache: dict = {}   # .xls/.xlsb/.ods: evita abrir o Excel a cada busca de SKU (vale enquanto o arquivo não mudar)


def _carregar(p: Path, perfil: Perfil = ML):
    """Lê o arquivo e devolve (planilha, colunas)."""
    ext = p.suffix.lower()
    if ext in EXT_XLSX:
        _, ws, cols = editor._abrir(_ler_disco(p), ext == ".xlsm", perfil)
        return ws, cols
    if ext in EXT_CSV:
        t = _tabela_csv(_ler_csv(_ler_disco(p)))
        return t, editor._colunas(t, perfil)
    st = p.stat()
    chave = (st.st_mtime_ns, st.st_size)
    c = _cache.get((str(p), perfil.chave))
    if c and c[0] == chave:
        return c[1], c[2]
    with _sessao_excel(p) as wb:
        _, t, cols = _localizar_aba(wb, perfil)
    _cache[(str(p), perfil.chave)] = (chave, t, cols)
    return t, cols


# ------------------------------------------------------------------ operações (usadas pelas rotas)
_IGNORAR = {".git", "node_modules", ".venv", "venv", "__pycache__", "appdata", "$recycle.bin", "windows",
            "program files", "program files (x86)", "profile"}


def _limpar(texto: str) -> str:
    """Aceita o caminho como vier: com aspas, 'file:///...', %USERPROFILE%, ~ etc."""
    t = (texto or "").strip().strip('"').strip("'").strip()
    if t.lower().startswith("file:///"):
        t = unquote(t[8:])
    return os.path.expandvars(os.path.expanduser(t))


def _procurar_por_nome(nome: str) -> list[Path]:
    """Arquivo mudou de pasta? Procura o mesmo nome nos lugares de sempre (Desktop, Downloads, Documentos, OneDrive,
    pasta do projeto). Limita a profundidade e o tempo para não travar."""
    home = Path.home()
    bases = [home / "Desktop", home / "Downloads", home / "Documents", home / "Documentos", home / "OneDrive",
             Path(__file__).resolve().parents[3]]
    for var in ("OneDrive", "OneDriveConsumer", "OneDriveCommercial"):
        if os.environ.get(var):
            bases.append(Path(os.environ[var]))
    alvo, achados, vistos = nome.lower(), [], set()
    limite = time.time() + 6
    for base in bases:
        if not base.is_dir():
            continue
        for raiz, dirs, arqs in os.walk(base):
            if time.time() > limite:
                return achados
            try:
                profundidade = len(Path(raiz).relative_to(base).parts)
            except ValueError:
                profundidade = 0
            dirs[:] = [] if profundidade >= 6 else [d for d in dirs if d.lower() not in _IGNORAR]
            for a in arqs:
                if a.lower() == alvo:
                    p = Path(raiz) / a
                    chave = os.path.normcase(str(p.resolve()))
                    if chave not in vistos:
                        vistos.add(chave)
                        achados.append(p)
    return achados


def caminho(texto: str) -> Path:
    p = Path(_limpar(texto))
    if p.suffix.lower() not in EXTENSOES:
        raise PlanilhaInvalida("Formato não aceito. Use um arquivo " + ", ".join(sorted(EXTENSOES)) + ".")
    if p.is_file():
        return p
    achados = _procurar_por_nome(p.name)
    if len(achados) == 1:   # mudou de pasta: segue o arquivo
        return achados[0]
    if len(achados) > 1:
        raise PlanilhaInvalida(f"Não encontrei o arquivo em {p} e existem {len(achados)} arquivos com esse nome em outras "
                               "pastas. Clique em Procurar e escolha o certo.")
    raise PlanilhaInvalida(f"Não encontrei o arquivo: {p}. Clique em Procurar para escolher onde ele está agora.")


def escolher_arquivo() -> str:
    """Abre a janela do Windows para escolher o arquivo em qualquer pasta (a calculadora roda no seu PC). Devolve o caminho."""
    try:
        import tkinter as tk
        from tkinter import filedialog
    except ImportError:
        raise PlanilhaInvalida("Este computador não tem o seletor de arquivos do Python (tkinter). Digite o caminho do arquivo.")
    try:
        raiz = tk.Tk()
    except Exception as e:
        raise PlanilhaInvalida(f"Não consegui abrir a janela de escolher arquivo ({e}). Digite o caminho do arquivo.")
    raiz.withdraw()
    raiz.attributes("-topmost", True)
    try:
        c = filedialog.askopenfilename(
            parent=raiz, title="Escolha a planilha de preços",
            filetypes=[("Planilhas do Excel", "*.xlsx *.xlsm *.xlsb *.xls *.csv *.ods"), ("Todos os arquivos", "*.*")])
    finally:
        raiz.destroy()
    return os.path.normpath(c) if c else ""


def abrir(texto: str, perfil: Perfil = ML) -> dict:
    p = caminho(texto)
    ws, cols = _carregar(p, perfil)
    r = editor.resumo(ws, cols, perfil)
    r["caminho"] = str(p)
    r["nome_arquivo"] = p.name
    return r


def localizar(texto: str, busca: str, perfil: Perfil = ML) -> dict:
    p = caminho(texto)
    ws, cols = _carregar(p, perfil)
    r = editor._achar(ws, cols, busca, perfil)
    r["caminho"] = str(p)
    return r


def listar_skus(texto: str, perfil: Perfil = ML) -> dict:
    """Lista as linhas de anúncio da planilha (linha, SKU, IDs, título, preços atuais). Só leitura: usado pelo robô de preços."""
    p = caminho(texto)
    ws, cols = _carregar(p, perfil)
    itens = []
    for row, item in editor._anuncios(ws, cols, perfil):
        info = editor._info(ws, cols, row, item, perfil)
        itens.append({k: info[k] for k in ("linha", "item_id", "variacao_id", "sku", "titulo", "preco_atual", "promocao_atual")})
    return {"caminho": str(p), "nome_arquivo": p.name, "total": len(itens), "itens": itens}


def gravar(texto: str, busca: str, preco_cheio, preco_promocional, perfil: Perfil = ML, nome: str = "") -> dict:
    p = caminho(texto)
    ext = p.suffix.lower()
    if _aberto_no_excel(p):   # planilha aberta no Excel: grava ao vivo nela, sem precisar fechar
        r = _gravar_excel(p, busca, preco_cheio, preco_promocional, perfil, nome)
    elif ext in EXT_XLSX:
        pronto, r = editor.gravar(_ler_disco(p), busca, preco_cheio, preco_promocional, ext == ".xlsm", perfil, nome)
        if r["conferencia_ok"]:
            _salvar(p, pronto)
    elif ext in EXT_CSV:
        pronto, r = _gravar_csv(_ler_disco(p), busca, preco_cheio, preco_promocional, perfil, nome)
        if r["conferencia_ok"]:
            _salvar(p, pronto)
    else:
        r = _gravar_excel(p, busca, preco_cheio, preco_promocional, perfil, nome)
    r.pop("celulas", None)
    r.pop("depois_todas", None)
    r["nome_arquivo"] = p.name
    r["caminho"] = str(p)
    return r
