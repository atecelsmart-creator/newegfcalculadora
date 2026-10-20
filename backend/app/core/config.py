"""
Configuração central do Módulo 1.

Lê tudo de variáveis de ambiente / .env — nada de credenciais hardcoded.
Reaproveita o PostgreSQL já existente no ambiente: este arquivo só aponta
para ele, não provisiona nada.
"""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env")

    app_name: str = "Calculadora Marketplace — Módulo 1"

    # Aponta para o Postgres já existente no ambiente do usuário.
    # Preencher via .env — não usar valores default em produção.
    database_url: str = "postgresql://user:password@localhost:5432/marketplace_calc"

    # "local" (PC do usuário, via calculadora.bat) ou "online" (servidor). Padrão = online (o mais restrito):
    # esquecer de definir nunca abre as rotas que mexem em arquivos do computador.
    modo: str = "online"
    # Só modo online: domínios aceitos (ex.: "calc.minhaempresa.com.br") e origens CORS, separados por vírgula.
    allowed_hosts: str = ""
    cors_origins: str = ""


settings = Settings()
