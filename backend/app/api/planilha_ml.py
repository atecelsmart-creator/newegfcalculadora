"""
Endpoints do quadro "Planilha do Mercado Livre / Shopee" da calculadora: abrir o arquivo, localizar um anúncio e gravar
o preço na linha dele, direto no arquivo do computador (xlsx, xlsm, xlsb, xls, csv...).
O campo `marketplace` escolhe o perfil de colunas (mercado_livre ou shopee; sem ele vale o Mercado Livre).

Só funciona quando a calculadora roda no próprio PC (o backend precisa enxergar o arquivo). Nada é guardado no servidor.
"""
from fastapi import APIRouter, Form, HTTPException, Request

from app.core.seguranca import exigir_local
from app.planilha_ml import arquivo, online
from app.planilha_ml import editor
from app.planilha_ml.editor import BuscaInvalida, PlanilhaInvalida, perfil_de

router = APIRouter(prefix="/planilha-ml")


def _executar(request: Request, fn, *args):
    # Modo local + cookie da página (seguranca.py). Não confia mais no IP do cliente: atrás de proxy ele é sempre 127.0.0.1.
    exigir_local(request)
    try:
        return fn(*args)
    except (PlanilhaInvalida, BuscaInvalida) as e:
        raise HTTPException(status_code=422, detail=str(e))
    except arquivo.ArquivoOcupado as e:
        raise HTTPException(status_code=409, detail=str(e))


def _marcar_origem(sessao: str, perfil, p) -> None:
    """Guarda, junto da cópia interna, qual arquivo do PC (e em que estado) ela representa."""
    try:
        st = p.stat()
        achou = online._procurar(sessao, perfil)
        if achou:
            _, meta, d = achou
            with online._trava:
                meta["origem"] = {"caminho": str(p), "mtime_ns": st.st_mtime_ns, "size": st.st_size}
                online._salvar_meta(d, meta)
    except Exception:  # noqa: BLE001
        pass


def _espelhar_abrir(sessao: str, resultado: dict, perfil, forcar: bool = True) -> dict:
    """Modo Computador: ao conectar o arquivo, cria sozinha a cópia interna (a mesma que o modo Online usa) para a aba
    Tabela e o Robô de preços funcionarem também no PC. Falha aqui nunca derruba a abertura do arquivo.
    forcar=False (reconexão automática ao abrir a página): se o arquivo não mudou, mantém a cópia como está (com as cores e marcas)."""
    if not sessao:
        return {"ok": False, "motivo": "sem sessão"}
    try:
        p = arquivo.caminho(resultado.get("caminho", ""))
        if p.suffix.lower() not in online.EXTENSOES:
            return {"ok": False, "motivo": "Formato " + p.suffix.lower() + " não alimenta a aba Tabela (só .xlsx, .xlsm e .csv)."}
        if not forcar:
            achou = online._procurar(sessao, perfil)
            if achou:
                o, st = achou[1].get("origem") or {}, p.stat()
                if o.get("caminho") == str(p) and o.get("mtime_ns") == st.st_mtime_ns and o.get("size") == st.st_size:
                    return {"ok": True, "reaproveitada": True}
        online.enviar(sessao, p.name, arquivo._ler_disco(p), perfil)
        _marcar_origem(sessao, perfil, p)
        return {"ok": True}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "motivo": str(e)}


def _espelhar_gravar(sessao: str, resultado: dict, busca, cheio, promo, perfil, cor: str, nome: str, linhas=None) -> dict:
    """Modo Computador: repete a gravação na cópia interna, para a aba Tabela e o robô enxergarem o preço novo."""
    if not sessao or resultado.get("conferencia_ok") is False:
        return {"ok": False, "motivo": "sem sessão" if not sessao else "gravação não conferida"}
    try:
        d = online.gravar(sessao, busca, cheio, promo, perfil, cor, nome, linhas)
        try:   # o arquivo do PC acabou de mudar por esta gravação: a cópia continua valendo para ele
            _marcar_origem(sessao, perfil, arquivo.caminho(resultado.get("caminho", "")))
        except Exception:  # noqa: BLE001
            pass
        return {"ok": True, "alterados": d.get("alterados"), "nome_download": d.get("nome_download")}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "motivo": str(e)}


def _lista_linhas(txt: str) -> list:
    try:
        return [int(x) for x in (txt or "").split(",") if x.strip()]
    except ValueError:
        raise HTTPException(status_code=422, detail="Linhas inválidas.")


def _conferir_linhas(sessao: str, caminho: str, perfil, linhas: list) -> None:
    """Gravação por número de linha (edição/grupo da aba Tabela): antes de escrever no arquivo do PC, confere que as linhas da
    cópia interna (a que a aba Tabela mostra) ainda são as mesmas do arquivo. Se você mexeu no arquivo pelo Excel depois de
    conectar, os números podem ter mudado e o preço iria para a linha errada."""
    achou = online._procurar(sessao, perfil)
    if not achou:
        raise PlanilhaInvalida("A aba Tabela ainda não tem a cópia deste arquivo. Clique em Conectar arquivo e tente de novo.")
    with online._trava:
        copia = {x["linha"]: x for x in online._linhas(achou[0], perfil)}
    ws, cols = arquivo._carregar(arquivo.caminho(caminho), perfil)
    disco = {}
    for row, item in editor._anuncios(ws, cols, perfil):
        info = editor._info(ws, cols, row, item, perfil)
        disco[info["linha"]] = info
    for n in linhas:
        a, b = copia.get(n), disco.get(n)
        if not a or not b or any(a[k] != b[k] for k in ("sku", "item_id", "variacao_id")):
            raise PlanilhaInvalida("O arquivo no seu computador mudou depois de conectado (as linhas não batem com a aba Tabela). "
                                   "Clique em Conectar arquivo para atualizar e tente de novo. Nada foi gravado.")


@router.post("/arquivo/escolher")
def arquivo_escolher(request: Request):
    """Abre a janela do Windows para escolher a planilha em qualquer pasta e devolve o caminho escolhido."""
    return _executar(request, lambda: {"caminho": arquivo.escolher_arquivo()})


@router.post("/arquivo/abrir")
def arquivo_abrir(request: Request, caminho: str = Form(""), marketplace: str = Form("mercado_livre"),
                  sessao: str = Form(""), forcar: str = Form("")):
    perfil = perfil_de(marketplace)
    r = _executar(request, arquivo.abrir, caminho, perfil)
    r["espelho"] = _espelhar_abrir(sessao, r, perfil, bool(forcar))   # clique em Conectar: refaz a cópia; reconexão automática: só se o arquivo mudou
    return r


@router.post("/arquivo/localizar")
def arquivo_localizar(request: Request, caminho: str = Form(""), busca: str = Form(""),
                      marketplace: str = Form("mercado_livre")):
    return _executar(request, arquivo.localizar, caminho, busca, perfil_de(marketplace))


@router.post("/arquivo/listar-skus")
def arquivo_listar_skus(request: Request, caminho: str = Form(""), marketplace: str = Form("mercado_livre")):
    """Só leitura: lista os anúncios/SKUs da planilha (usado pelo robô de atualização de preços)."""
    return _executar(request, arquivo.listar_skus, caminho, perfil_de(marketplace))


@router.post("/arquivo/gravar")
def arquivo_gravar(request: Request, caminho: str = Form(""), busca: str = Form(""),
                   preco_cheio: float = Form(...), preco_promocional: float | None = Form(None),
                   marketplace: str = Form("mercado_livre"), nome: str = Form(""), sessao: str = Form(""),
                   cor: str = Form(""), linhas: str = Form("")):
    """Com "linhas" (ex.: "7,9,12"): grava o mesmo preço só nessas linhas (aba Tabela); sem: procura por "busca"."""
    perfil = perfil_de(marketplace)
    nums = _lista_linhas(linhas) or None
    if nums:
        _executar(request, _conferir_linhas, sessao, caminho, perfil, nums)
    r = _executar(request, arquivo.gravar, caminho, busca, preco_cheio, preco_promocional, perfil, nome, nums)
    r["espelho"] = _espelhar_gravar(sessao, r, busca, preco_cheio, preco_promocional, perfil, cor, nome, nums)
    return r
