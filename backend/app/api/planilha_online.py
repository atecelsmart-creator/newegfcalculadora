"""
Endpoints do modo ONLINE do quadro de planilha: enviar o arquivo, localizar o anúncio, gravar o preço, ver a planilha
atualizada (aba "Planilha online") e baixar. Funciona em qualquer servidor — o arquivo é enviado pelo navegador e fica
numa pasta temporária do servidor, separado por sessão do navegador ("sessao") e por marketplace.

O modo local (gravar direto no arquivo do PC) continua em api/planilha_ml.py.
"""
from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import Response

from app.planilha_ml import online
from app.planilha_ml.editor import BuscaInvalida, PlanilhaInvalida, perfil_de

router = APIRouter(prefix="/planilha-online")


def _executar(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except (PlanilhaInvalida, BuscaInvalida) as e:
        raise HTTPException(status_code=422, detail=str(e))


def _lista_linhas(txt: str) -> list:
    try:
        return [int(x) for x in (txt or "").split(",") if x.strip()]
    except ValueError:
        raise HTTPException(status_code=422, detail="Linhas inválidas.")


@router.post("/enviar")
def enviar(sessao: str = Form(...), marketplace: str = Form("mercado_livre"), planilha: UploadFile = File(...)):
    conteudo = planilha.file.read(online.LIMITE_BYTES + 1)
    return _executar(online.enviar, sessao, planilha.filename or "", conteudo, perfil_de(marketplace))


@router.post("/resumo")
def resumo(sessao: str = Form(...), marketplace: str = Form("mercado_livre")):
    return _executar(online.resumo, sessao, perfil_de(marketplace))


@router.post("/localizar")
def localizar(sessao: str = Form(...), busca: str = Form(""), marketplace: str = Form("mercado_livre")):
    return _executar(online.localizar, sessao, busca, perfil_de(marketplace))


@router.post("/gravar")
def gravar(sessao: str = Form(...), busca: str = Form(""), preco_cheio: float = Form(...),
           preco_promocional: float | None = Form(None), marketplace: str = Form("mercado_livre"), cor: str = Form(""),
           nome: str = Form(""), linhas: str = Form("")):
    """Com "linhas" (ex.: "7,9,12"): grava o mesmo preço só nessas linhas (seleção em grupo); sem: procura por "busca"."""
    return _executar(online.gravar, sessao, busca, preco_cheio, preco_promocional, perfil_de(marketplace), cor, nome,
                     _lista_linhas(linhas) or None)


@router.post("/visualizar")
def visualizar(sessao: str = Form(...), marketplace: str = Form("mercado_livre"), busca: str = Form(""),
               pagina: int = Form(1), por_pagina: int = Form(50)):
    return _executar(online.visualizar, sessao, perfil_de(marketplace), busca, pagina, por_pagina)


@router.post("/pintar")
def pintar(sessao: str = Form(...), marketplace: str = Form("mercado_livre"), linhas: str = Form(""), cor: str = Form("")):
    return _executar(online.pintar, sessao, _lista_linhas(linhas) or [], cor, perfil_de(marketplace))


@router.post("/limpar-marcas")
def limpar_marcas(sessao: str = Form(...), marketplace: str = Form("mercado_livre"), linhas: str = Form("")):
    """Sem "linhas": limpa a marca verde e as cores de todas as linhas; com "linhas" (ex.: "7,9"): só dessas."""
    return _executar(online.limpar_marcas, sessao, perfil_de(marketplace), _lista_linhas(linhas) or None)


@router.post("/baixar")
def baixar(sessao: str = Form(...), marketplace: str = Form("mercado_livre")):
    conteudo, _nome, media, cabecalho = _executar(online.baixar, sessao, perfil_de(marketplace))
    return Response(content=conteudo, media_type=media, headers={"Content-Disposition": cabecalho})


@router.post("/descartar")
def descartar(sessao: str = Form(...), marketplace: str = Form("mercado_livre")):
    return _executar(online.descartar, sessao, perfil_de(marketplace))
