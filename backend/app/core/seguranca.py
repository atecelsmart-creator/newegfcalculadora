"""
Segurança dos dois modos de execução (variável de ambiente MODO):

  MODO=local   -> a calculadora roda no PC do usuário (calculadora.bat). As rotas que mexem em arquivos do
                  computador (planilha-ml, robo) existem, mas só respondem a quem tem o cookie local.
  MODO=online  -> a calculadora roda num servidor. Essas rotas NÃO são registradas (404): não há o que atacar.

Por que cookie e não o IP do cliente: atrás de um proxy (nginx, Railway...) o IP visto pelo backend costuma ser
127.0.0.1, o que liberaria as rotas locais para qualquer pessoa. O cookie é entregue só a quem abre a página no
próprio PC (SameSite=Strict + HttpOnly), então outro site aberto no navegador não consegue chamar essas rotas.
"""
import hmac
import secrets
from pathlib import Path

from fastapi import HTTPException, Request

from app.core.config import settings

COOKIE_LOCAL = "calc_local"
ARQUIVO_TOKEN = Path(__file__).resolve().parents[2] / "data" / ".local_token"   # backend/data/.local_token (fora do git)

_token_cache: str | None = None


def modo_local() -> bool:
    return settings.modo.strip().lower() == "local"


def token_local() -> str:
    """Token do modo local. Fica num arquivo para sobreviver ao --reload do uvicorn e ser lido pelo robô (rpa/)."""
    global _token_cache
    if _token_cache:
        return _token_cache
    try:
        t = ARQUIVO_TOKEN.read_text(encoding="utf-8").strip()
    except OSError:
        t = ""
    if len(t) < 32:
        t = secrets.token_urlsafe(32)
        ARQUIVO_TOKEN.parent.mkdir(parents=True, exist_ok=True)
        ARQUIVO_TOKEN.write_text(t, encoding="utf-8")
    _token_cache = t
    return t


def exigir_local(request: Request) -> None:
    """Dependência das rotas que acessam o computador (arquivos, janelas, Excel, robô)."""
    if not modo_local():
        raise HTTPException(status_code=404, detail="Not Found")
    enviado = request.cookies.get(COOKIE_LOCAL, "")
    if not enviado or not hmac.compare_digest(enviado, token_local()):
        raise HTTPException(status_code=403, detail="Acesso negado: abra a calculadora pelo calculadora.bat (http://127.0.0.1:8000/).")
