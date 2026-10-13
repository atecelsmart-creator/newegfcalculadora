"""
Endpoints do quadro "Planilha do Mercado Livre / Shopee" da calculadora: abrir o arquivo, localizar um anúncio e gravar
o preço na linha dele, direto no arquivo do computador (xlsx, xlsm, xlsb, xls, csv...).
O campo `marketplace` escolhe o perfil de colunas (mercado_livre ou shopee; sem ele vale o Mercado Livre).

Só funciona quando a calculadora roda no próprio PC (o backend precisa enxergar o arquivo). Nada é guardado no servidor.
"""
from fastapi import APIRouter, Form, HTTPException, Request

from app.planilha_ml import arquivo
from app.planilha_ml.editor import BuscaInvalida, PlanilhaInvalida, perfil_de

router = APIRouter(prefix="/planilha-ml")


def _executar(request: Request, fn, *args):
    host = request.client.host if request.client else ""
    if host not in ("127.0.0.1", "::1", "localhost"):
        raise HTTPException(status_code=403, detail="Gravar direto no arquivo só funciona na calculadora aberta no seu computador.")
    try:
        return fn(*args)
    except (PlanilhaInvalida, BuscaInvalida) as e:
        raise HTTPException(status_code=422, detail=str(e))
    except arquivo.ArquivoOcupado as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.post("/arquivo/escolher")
def arquivo_escolher(request: Request):
    """Abre a janela do Windows para escolher a planilha em qualquer pasta e devolve o caminho escolhido."""
    return _executar(request, lambda: {"caminho": arquivo.escolher_arquivo()})


@router.post("/arquivo/abrir")
def arquivo_abrir(request: Request, caminho: str = Form(""), marketplace: str = Form("mercado_livre")):
    return _executar(request, arquivo.abrir, caminho, perfil_de(marketplace))


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
                   marketplace: str = Form("mercado_livre"), nome: str = Form("")):
    return _executar(request, arquivo.gravar, caminho, busca, preco_cheio, preco_promocional, perfil_de(marketplace), nome)
