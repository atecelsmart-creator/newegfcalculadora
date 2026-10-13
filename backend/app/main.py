from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api.planilha_ml import router as planilha_ml_router
from app.api.planilha_online import router as planilha_online_router
from app.api.robo import router as robo_router
from app.api.routes import router
from app.core.config import settings

app = FastAPI(title=settings.app_name)

# O frontend (index.html na raiz) roda em outra origem — arquivo aberto
# direto no navegador (file://) ou servido por um live-server em outra
# porta. Sem isso, o navegador bloqueia o fetch antes mesmo de chegar
# aqui, e o JS só reporta "Failed to fetch" (sem detalhe do motivo).
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router, prefix="/api")
app.include_router(planilha_ml_router, prefix="/api")
app.include_router(planilha_online_router, prefix="/api")
app.include_router(robo_router, prefix="/api")


@app.get("/health")
def health():
    return {"status": "ok"}


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
    return FileResponse(ROOT_DIR / "index.html", headers={"Cache-Control": "no-cache"})


app.mount("/img", StaticFiles(directory=ROOT_DIR / "img"), name="img")
