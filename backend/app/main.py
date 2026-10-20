import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles

from app.api.planilha_online import router as planilha_online_router
from app.api.routes import router
from app.core import seguranca
from app.core.config import settings

log = logging.getLogger("uvicorn.error")
LOCAL = seguranca.modo_local()

# Online: sem /docs, /redoc e /openapi.json (não expor o mapa da API). Local: mantém, ajuda a depurar.
app = FastAPI(
    title=settings.app_name,
    docs_url="/docs" if LOCAL else None,
    redoc_url=None,
    openapi_url="/openapi.json" if LOCAL else None,
)

# O frontend é servido por este mesmo backend (mesma origem), então CORS aberto ("*") não é necessário e era um risco:
# qualquer site aberto no navegador poderia chamar a API. Agora só as origens da própria calculadora.
if LOCAL:
    _hosts = ["127.0.0.1", "localhost"]
    _cors = ["http://127.0.0.1:8000", "http://localhost:8000"]
else:
    _hosts = [h.strip() for h in settings.allowed_hosts.split(",") if h.strip()]
    _cors = [o.strip() for o in settings.cors_origins.split(",") if o.strip()]
    if not _hosts:
        log.warning("MODO=online sem ALLOWED_HOSTS: aceitando qualquer Host. Defina ALLOWED_HOSTS no ambiente do servidor.")
        _hosts = ["*"]

# Host permitido: no local barra DNS rebinding; no online barra Host forjado.
app.add_middleware(TrustedHostMiddleware, allowed_hosts=_hosts)
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors,
    allow_methods=["GET", "POST", "PUT"],
    allow_headers=["Content-Type"],
)

app.include_router(router, prefix="/api")
app.include_router(planilha_online_router, prefix="/api")

if LOCAL:
    # Rotas que mexem no COMPUTADOR (caminhos de arquivo, janelas do Windows, Excel/COM, robô). Só existem no modo
    # local; online elas nem são registradas (404). Mesmo no local exigem o cookie (seguranca.exigir_local).
    from app.api.planilha_ml import router as planilha_ml_router
    from app.api.robo import router as robo_router

    seguranca.token_local()   # garante o token em disco (o robô em rpa/ lê o mesmo arquivo)
    app.include_router(planilha_ml_router, prefix="/api")
    app.include_router(robo_router, prefix="/api")


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/api/modo")
def modo():
    """O front consulta isto para mostrar só o que existe no modo atual (local: arquivo do PC e robô; online: envio de planilha)."""
    return {"modo": "local" if LOCAL else "online"}


# Serve o frontend na MESMA origem do backend (http://127.0.0.1:8000/).
# O bloqueio real do "Failed to fetch" não era CORS — era o navegador
# recusando uma origem file:// acessar localhost (Private Network Access).
# Servindo os dois juntos, esse bloqueio não se aplica mais. Precisa vir
# DEPOIS do include_router: um mount em "/" é catch-all, então se viesse
# antes ele engoliria as rotas /api/* também.
# A partir de agora, abra http://127.0.0.1:8000/ no navegador — não abra
# mais o index.html direto do disco (file://).
#
# O index.html agora fica na RAIZ do projeto (junto com a pasta img/), pra
# subir no git. Como a raiz também contém backend/, NÃO montamos a raiz
# inteira como StaticFiles (isso exporia o código-fonte por HTTP): servimos
# só o index.html em "/" e a pasta img/ em "/img".
ROOT_DIR = Path(__file__).resolve().parent.parent.parent


@app.get("/", include_in_schema=False)
@app.get("/index.html", include_in_schema=False)
def index():
    # no-cache: o navegador sempre confere se o index.html mudou (evita ficar com a versao antiga)
    html = (ROOT_DIR / "index.html").read_text(encoding="utf-8")
    # A página fica sabendo o modo do servidor (local/online) antes de qualquer script: online esconde o que mexe no PC.
    html = html.replace("<head>", '<head><script>window.MODO_SERVIDOR="%s";</script>' % ("local" if LOCAL else "online"), 1)
    resposta = Response(
        content=html.encode("utf-8"),
        media_type="text/html; charset=utf-8",
        headers={"Cache-Control": "no-cache"},
    )
    if LOCAL:
        # Só quem abre a página no próprio PC recebe o cookie que libera as rotas locais. HttpOnly: o JS da página
        # não lê; SameSite=Strict: outro site aberto no navegador não consegue enviá-lo.
        resposta.set_cookie(seguranca.COOKIE_LOCAL, seguranca.token_local(), httponly=True, samesite="strict", path="/")
    return resposta


app.mount("/img", StaticFiles(directory=ROOT_DIR / "img"), name="img")
