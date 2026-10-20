"""Segurança dos modos local/online (app/core/seguranca.py): rotas que mexem no PC só existem no modo local e exigem o cookie."""
import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from app.core import seguranca
from app.core.config import settings


@pytest.fixture()
def cli(tmp_path, monkeypatch):
    monkeypatch.setattr(seguranca, "ARQUIVO_TOKEN", tmp_path / ".local_token")
    monkeypatch.setattr(seguranca, "_token_cache", None)
    app = FastAPI()

    @app.get("/x", dependencies=[Depends(seguranca.exigir_local)])
    def x():
        return {"ok": True}

    return TestClient(app)


def cookie(valor: str) -> dict:
    return {"Cookie": f"{seguranca.COOKIE_LOCAL}={valor}"}


def test_padrao_e_online():
    """Esquecer de definir MODO nunca abre as rotas locais."""
    assert type(settings).model_fields["modo"].default == "online"


def test_online_nega_ate_com_cookie_certo(cli, monkeypatch):
    monkeypatch.setattr(settings, "modo", "online")
    token = seguranca.token_local()
    assert cli.get("/x").status_code == 404
    assert cli.get("/x", headers=cookie(token)).status_code == 404


def test_local_sem_cookie_ou_com_cookie_errado_e_negado(cli, monkeypatch):
    monkeypatch.setattr(settings, "modo", "local")
    assert cli.get("/x").status_code == 403
    assert cli.get("/x", headers=cookie("errado")).status_code == 403
    assert cli.get("/x", headers=cookie("")).status_code == 403


def test_local_com_cookie_certo_passa(cli, monkeypatch):
    monkeypatch.setattr(settings, "modo", "local")
    r = cli.get("/x", headers=cookie(seguranca.token_local()))
    assert r.status_code == 200 and r.json() == {"ok": True}


def test_token_e_forte_e_persiste_em_arquivo(cli, monkeypatch):
    t1 = seguranca.token_local()
    assert len(t1) >= 32
    assert seguranca.ARQUIVO_TOKEN.read_text(encoding="utf-8").strip() == t1
    monkeypatch.setattr(seguranca, "_token_cache", None)   # simula o --reload do uvicorn
    assert seguranca.token_local() == t1
