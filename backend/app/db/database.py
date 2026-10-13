"""
Conexão com o PostgreSQL já existente no ambiente (Docker local, WSL2).
Este módulo NÃO cria banco, NÃO cria containers — só aponta pra infra
que você já tem. Ajuste DATABASE_URL no .env antes de rodar.
"""
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import settings

engine = create_engine(settings.database_url)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
