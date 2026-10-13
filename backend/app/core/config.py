"""
Configuração central do Módulo 1.

Lê tudo de variáveis de ambiente / .env — nada de credenciais hardcoded.
Reaproveita o PostgreSQL já existente no ambiente: este arquivo só aponta
para ele, não provisiona nada.
"""
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_name: str = "Calculadora Marketplace — Módulo 1"

    # Aponta para o Postgres já existente no ambiente do usuário.
    # Preencher via .env — não usar valores default em produção.
    database_url: str = "postgresql://user:password@localhost:5432/marketplace_calc"

    class Config:
        env_file = ".env"


settings = Settings()
