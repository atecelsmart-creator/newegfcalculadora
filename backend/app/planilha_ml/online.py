"""
Modo ONLINE da planilha de preços (Mercado Livre / Shopee).

No modo local o backend grava direto no arquivo do PC (arquivo.py). Num servidor web ele não enxerga o seu computador,
então aqui o caminho é outro:

  1. o navegador ENVIA a planilha;
  2. ela fica numa pasta temporária do servidor (uma por "sessão" do navegador + marketplace);
  3. cada preço calculado é gravado nela pelas MESMAS regras do modo local (editor.gravar / arquivo._gravar_csv, com a
     conferência de que só as células de preço mudaram);
  4. a aba "Planilha online" mostra o arquivo como ele está agora, e o navegador BAIXA a versão atualizada.

Arquivos parados há mais de 12 horas são apagados sozinhos. Formatos: .xlsx, .xlsm e .csv (.xls/.xlsb/.ods dependem do
Excel instalado no PC, então só existem no modo local).
"""
from __future__ import annotations

import json
import os
import re
import shutil
import tempfile
import threading
import time
from pathlib import Path
from urllib.parse import quote

from app.planilha_ml import arquivo, editor
from app.planilha_ml.editor import ML, Perfil, PlanilhaInvalida

EXTENSOES = {".xlsx", ".xlsm", ".csv"}
LIMITE_BYTES = 25 * 1024 * 1024
VALIDADE_S = 12 * 3600
MEDIA = {
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".xlsm": "application/vnd.ms-excel.sheet.macroEnabled.12",
    ".csv": "text/csv",
}

PASTA = Path(os.environ.get("PLANILHA_ONLINE_DIR") or Path(tempfile.gettempdir()) / "calculadora_planilhas_online")
_SESSAO = re.compile(r"[A-Za-z0-9_-]{16,64}")
_COR = re.compile(r"#[0-9a-fA-F]{6}")
_trava = threading.RLock()
_cache: dict = {}   # (caminho, marketplace, mtime, tamanho) -> linhas lidas; evita reabrir o arquivo a cada página
_cache_ws: dict = {}   # (caminho, marketplace, mtime, tamanho) -> (planilha, colunas) já abertas; evita reabrir o .xlsx a cada busca de SKU


# ------------------------------------------------------------------ armazenamento
def _pasta(sessao: str, perfil: Perfil) -> Path:
    if not _SESSAO.fullmatch(sessao or ""):
        raise PlanilhaInvalida("Sessão inválida. Recarregue a página e envie a planilha de novo.")
    return PASTA / sessao / perfil.chave


def _salvar_meta(d: Path, meta: dict) -> None:
    tmp = d / "meta.json.tmp"
    tmp.write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, d / "meta.json")


def _procurar(sessao: str, perfil: Perfil):
    """(arquivo, meta, pasta) da planilha enviada, ou None se ainda não enviou (ou se expirou)."""
    d = _pasta(sessao, perfil)
    try:
        meta = json.loads((d / "meta.json").read_text(encoding="utf-8"))
        p = d / ("planilha" + meta["ext"])
    except (OSError, ValueError, KeyError):
        return None
    return (p, meta, d) if p.is_file() else None


def _exigir(sessao: str, perfil: Perfil):
    achou = _procurar(sessao, perfil)
    if not achou:
        raise PlanilhaInvalida(f"Nenhuma planilha do {perfil.nome} foi enviada nesta sessão (ou ela expirou). "
                               "Envie o arquivo de novo.")
    return achou


def _limpar_antigas() -> None:
    if not PASTA.is_dir():
        return
    limite = time.time() - VALIDADE_S
    for s in PASTA.iterdir():
        try:
            recente = max((f.stat().st_mtime for f in s.rglob("*") if f.is_file()), default=0)
            if recente < limite:
                shutil.rmtree(s, ignore_errors=True)
        except OSError:
            pass


def _nome_download(meta: dict) -> str:
    return f"{Path(meta['nome']).stem}_atualizado{meta['ext']}"


# ------------------------------------------------------------------ leitura
def _carregar(p: Path, perfil: Perfil):
    """xlsx/xlsm/csv: mesma leitura do modo local, mas guardada na memória enquanto o arquivo não mudar (mtime/tamanho).
    Antes, cada busca de SKU (cor do quadro na Calculadora) reabria a planilha inteira do disco. Só leitura: a gravação
    trabalha com os bytes do arquivo, então a planilha em cache nunca é alterada. Chamar sempre com a trava `_trava` presa."""
    st = p.stat()
    chave = (str(p), perfil.chave, st.st_mtime_ns, st.st_size)
    achou = _cache_ws.get(chave)
    if achou is None:
        achou = arquivo._carregar(p, perfil)
        if len(_cache_ws) >= 2:
            _cache_ws.clear()   # poucas planilhas na memória (cada uma pode ter vários MB)
        _cache_ws[chave] = achou
    return achou


def _linhas(p: Path, perfil: Perfil) -> list[dict]:
    st = p.stat()
    chave = (str(p), perfil.chave, st.st_mtime_ns, st.st_size)
    if chave not in _cache:
        ws, cols = _carregar(p, perfil)
        if len(_cache) > 8:
            _cache.clear()
        _cache[chave] = [editor._info(ws, cols, row, item, perfil) for row, item in editor._anuncios(ws, cols, perfil)]
    return _cache[chave]


def _marcar(info: dict, meta: dict) -> dict:
    a = meta["alteracoes"].get(str(info["linha"]))
    return {**info, "alterado": bool(a),
            "cor": meta.get("cores", {}).get(str(info["linha"]), ""),
            "preco_original": a["preco_original"] if a else None,
            "promo_original": a["promo_original"] if a else None}


# ------------------------------------------------------------------ operações (usadas pelas rotas)
def _chave_linha(x: dict) -> tuple:
    """Identifica o anúncio pelo conteúdo (ID, variação, SKU) e não pelo número da linha, que muda se a planilha mudar."""
    return (x["item_id"].upper(), x["variacao_id"].upper(), x["sku"].upper())


def _marcas_antigas(sessao: str, perfil: Perfil) -> tuple:
    """({chave: cor}, {chave: alteração}) da cópia atual, para sobreviverem quando a cópia for refeita (reconectar, atualizar)."""
    try:
        achou = _procurar(sessao, perfil)
        if not achou:
            return {}, {}
        p, meta, _ = achou
        cores, alts = {}, {}
        for x in _linhas(p, perfil):
            k, n = _chave_linha(x), str(x["linha"])
            if meta.get("cores", {}).get(n):
                cores[k] = meta["cores"][n]
            if n in meta.get("alteracoes", {}):
                alts[k] = meta["alteracoes"][n]
        return cores, alts
    except Exception:  # noqa: BLE001
        return {}, {}


def _herdar_marcas(d: Path, meta: dict, perfil: Perfil, herdadas: tuple) -> None:
    """Devolve as cores e marcas às linhas da cópia nova que são o mesmo anúncio (mesmo ID/variação/SKU) das antigas."""
    cores, alts = herdadas
    try:
        for x in _linhas(d / ("planilha" + meta["ext"]), perfil):
            k, n = _chave_linha(x), str(x["linha"])
            if k in cores:
                meta["cores"][n] = cores[k]
            if k in alts:
                meta["alteracoes"][n] = alts[k]
        _salvar_meta(d, meta)
    except Exception:  # noqa: BLE001
        pass


def enviar(sessao: str, nome: str, conteudo: bytes, perfil: Perfil = ML) -> dict:
    nome = re.split(r"[\\/]", nome or "")[-1]
    ext = Path(nome).suffix.lower()
    if ext not in EXTENSOES:
        raise PlanilhaInvalida("Formato não aceito no modo online. Envie um arquivo " + ", ".join(sorted(EXTENSOES))
                               + " (.xls, .xlsb e .ods só funcionam na calculadora aberta no seu computador).")
    if not conteudo:
        raise PlanilhaInvalida("O arquivo está vazio.")
    if len(conteudo) > LIMITE_BYTES:
        raise PlanilhaInvalida(f"O arquivo passa de {LIMITE_BYTES // 2 ** 20} MB.")
    d = _pasta(sessao, perfil)

    # confere que é a planilha deste marketplace ANTES de guardar qualquer coisa
    if ext == ".csv":
        ws = arquivo._tabela_csv(arquivo._ler_csv(conteudo))
        cols = editor._colunas(ws, perfil)
    else:
        _, ws, cols = editor._abrir(conteudo, ext == ".xlsm", perfil)
    r = editor.resumo(ws, cols, perfil)

    with _trava:
        _limpar_antigas()
        herdadas = _marcas_antigas(sessao, perfil)   # cores e marcas da cópia que vai ser substituída: só saem se o usuário desmarcar
        shutil.rmtree(d, ignore_errors=True)
        d.mkdir(parents=True, exist_ok=True)
        (d / ("planilha" + ext)).write_bytes(conteudo)
        meta = {"nome": nome, "ext": ext, "enviado_em": time.time(), "alteracoes": {}, "cores": {}}
        _salvar_meta(d, meta)
        if herdadas[0] or herdadas[1]:
            _herdar_marcas(d, meta, perfil, herdadas)
    r.update(carregado=True, nome_arquivo=nome, nome_download=_nome_download(meta), alterados=len(meta["alteracoes"]))
    return r


def resumo(sessao: str, perfil: Perfil = ML) -> dict:
    achou = _procurar(sessao, perfil)
    if not achou:
        return {"carregado": False}
    p, meta, _ = achou
    with _trava:
        linhas = _linhas(p, perfil)
    return {"carregado": True, "nome_arquivo": meta["nome"], "nome_download": _nome_download(meta),
            "total_anuncios": len(linhas), "alterados": len(meta["alteracoes"]),
            "tem_coluna_promocao": bool(linhas and linhas[0]["tem_coluna_promocao"])}


def localizar(sessao: str, busca: str, perfil: Perfil = ML) -> dict:
    p, meta, _ = _exigir(sessao, perfil)
    with _trava:
        ws, cols = _carregar(p, perfil)
        achado = _marcar(editor._achar(ws, cols, busca, perfil), meta)
        # posição (0, 1, 2...) da linha na lista da aba Tabela sem filtro: o front usa a paridade pra dar a mesma zebra (.28 / .16)
        for i, x in enumerate(_linhas(p, perfil)):
            if x["linha"] == achado["linha"]:
                achado["posicao"] = i
                break
        return achado


def gravar(sessao: str, busca: str, preco_cheio, preco_promocional, perfil: Perfil = ML, cor: str = "", nome: str = "",
           linhas: list | None = None, reutilizar: bool = False) -> dict:
    """Grava o preço na linha. `cor` ("#rrggbb") é a cor que a linha atualizada recebe na aba Tabela; vazia = marca verde padrão.
    `linhas` (números de linha da planilha): grava só nessas linhas, todas com o mesmo preço (seleção em grupo da aba Tabela)."""
    cor = (cor or "").strip()
    if cor and not _COR.fullmatch(cor):
        raise PlanilhaInvalida("Cor inválida.")
    p, meta, d = _exigir(sessao, perfil)
    with _trava:
        st0 = p.stat()
        chave0 = (str(p), perfil.chave, st0.st_mtime_ns, st0.st_size)   # chave do cache antes de gravar
        conteudo = p.read_bytes()
        if p.suffix == ".csv":
            pronto, r = arquivo._gravar_csv(conteudo, busca, preco_cheio, preco_promocional, perfil, nome, linhas)
        else:
            pronto, r = editor.gravar(conteudo, busca, preco_cheio, preco_promocional, p.suffix == ".xlsm", perfil, nome, linhas,
                                      slot=("online:" + str(p)) if reutilizar else None)
        if r["conferencia_ok"]:
            tmp = p.with_name(p.name + ".tmp")
            tmp.write_bytes(pronto)
            os.replace(tmp, p)
            antes = r["antes"]
            cores = meta.setdefault("cores", {})
            for a in r.get("antes_todas") or [r["antes"]]:   # SKU em várias linhas: marca todas
                alt = meta["alteracoes"].setdefault(str(a["linha"]), {"preco_original": a["preco_atual"],
                                                                     "promo_original": a["promocao_atual"]})
                alt["em"] = time.time()   # o "original" é sempre o valor da planilha ANTES da primeira gravação
                if cor:
                    cores[str(a["linha"])] = cor   # cor escolhida para as linhas atualizadas (vale também para quem já tinha outra cor)
                # sem cor escolhida: a cor que a linha já tinha fica (cor só sai por "Desmarcar todas" ou clicando na linha)
            _salvar_meta(d, meta)
            # Atualiza as linhas em cache em vez de jogar tudo fora: assim a próxima atualização da tabela não reabre a planilha inteira
            em_cache = _cache.pop(chave0, None)
            novas = {x["linha"]: x for x in r.get("depois_todas") or []}
            if em_cache is not None and novas and set(novas) <= {x["linha"] for x in em_cache}:
                for item in em_cache:
                    x = novas.get(item["linha"])
                    if x:
                        item["preco_atual"] = x["preco_atual"]
                        item["promocao_atual"] = x["promocao_atual"]
                st1 = p.stat()
                _cache[(str(p), perfil.chave, st1.st_mtime_ns, st1.st_size)] = em_cache
    r.pop("celulas", None)
    r.pop("depois_todas", None)
    r.update(nome_arquivo=meta["nome"], nome_download=_nome_download(meta), alterados=len(meta["alteracoes"]))
    return r


def visualizar(sessao: str, perfil: Perfil = ML, busca: str = "", pagina: int = 1, por_pagina: int = 50) -> dict:
    achou = _procurar(sessao, perfil)
    if not achou:
        return {"carregado": False}
    p, meta, _ = achou
    with _trava:
        linhas = _linhas(p, perfil)
    b = (busca or "").strip().lower()
    saida = []
    for l in linhas:
        m = _marcar(l, meta)
        if b and b not in " ".join((l["sku"], l["item_id"], l["variacao_id"], l["titulo"])).lower():
            continue
        saida.append(m)
    por_pagina = max(10, min(100000, int(por_pagina or 50)))
    paginas = max(1, -(-len(saida) // por_pagina))
    pagina = max(1, min(paginas, int(pagina or 1)))
    ini = (pagina - 1) * por_pagina
    return {"carregado": True, "nome_arquivo": meta["nome"], "nome_download": _nome_download(meta),
            "total": len(linhas), "filtrados": len(saida), "alterados": len(meta["alteracoes"]),
            "pagina": pagina, "paginas": paginas, "por_pagina": por_pagina,
            "tem_coluna_promocao": bool(linhas and linhas[0]["tem_coluna_promocao"]),
            "linhas": saida[ini:ini + por_pagina],
            "linhas_filtradas": [m["linha"] for m in saida]}   # números de todas as linhas do filtro (selecionar além da página)


def pintar(sessao: str, linhas: list, cor: str, perfil: Perfil = ML) -> dict:
    """Pinta as linhas com a cor ("#rrggbb"); cor vazia tira a cor. Só visual: não mexe no arquivo."""
    _, meta, d = _exigir(sessao, perfil)
    cor = (cor or "").strip()
    if cor and not _COR.fullmatch(cor):
        raise PlanilhaInvalida("Cor inválida.")
    with _trava:
        cores = meta.setdefault("cores", {})
        for l in linhas:
            if cor:
                cores[str(l)] = cor
            else:
                cores.pop(str(l), None)
        _salvar_meta(d, meta)
    return {"cores": len(cores)}


def limpar_marcas(sessao: str, perfil: Perfil = ML, linhas: list | None = None) -> dict:
    """Tira a marca verde de "alterado" e a cor das linhas (todas, se linhas=None). Não desfaz preço nem mexe no arquivo:
    a próxima gravação na linha volta a marcá-la, guardando o preço de agora como "original"."""
    _, meta, d = _exigir(sessao, perfil)
    with _trava:
        cores = meta.setdefault("cores", {})
        if linhas is None:
            meta["alteracoes"].clear()
            cores.clear()
        else:
            for l in linhas:
                meta["alteracoes"].pop(str(l), None)
                cores.pop(str(l), None)
        _salvar_meta(d, meta)
    return {"alterados": len(meta["alteracoes"])}


def baixar(sessao: str, perfil: Perfil = ML):
    """(bytes, nome_do_download, media_type, cabecalho Content-Disposition) do arquivo como está agora."""
    p, meta, _ = _exigir(sessao, perfil)
    with _trava:
        conteudo = p.read_bytes()
    nome = _nome_download(meta)
    ascii_ = re.sub(r"[^A-Za-z0-9._-]", "_", nome)
    cab = f"attachment; filename=\"{ascii_}\"; filename*=UTF-8''{quote(nome)}"
    return conteudo, nome, MEDIA[meta["ext"]], cab


def descartar(sessao: str, perfil: Perfil = ML) -> dict:
    with _trava:
        shutil.rmtree(_pasta(sessao, perfil), ignore_errors=True)
        _cache.clear()
        _cache_ws.clear()
    return {"carregado": False}
