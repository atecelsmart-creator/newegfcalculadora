"""
Tabela de frete do Mercado Livre vista pelo robô.

O robô lê peso e faixa de valor do arquivo de dados em texto livre ("0,5 a 1 kg", "49 a 78,99") e precisa dos rótulos exatos
da tabela que a calculadora usa (backend/app/engine/ml/frete.py, aba "BASE FRETE MELI"). Aqui ficam só as conversões:
nenhum valor de frete é calculado ou guardado neste arquivo (a fonte única continua sendo o backend).
"""
import importlib.util
import re
import sys
import unicodedata

from rpa import config

_modulo = None


def _tabela():
    """Módulo backend/app/engine/ml/frete.py. Dentro do servidor ele já está carregado; pela linha de comando (e nos testes) é
    lido direto do arquivo, que não importa nada: assim o robô não precisa do backend inteiro (pydantic, FastAPI) no caminho."""
    global _modulo
    if _modulo is None:
        mod = sys.modules.get("app.engine.ml.frete")
        if mod is None:
            caminho = config.RAIZ.parent / "backend" / "app" / "engine" / "ml" / "frete.py"
            spec = importlib.util.spec_from_file_location("rpa_ml_frete_tabela", caminho)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
        _modulo = mod
    return _modulo


def _chave(txt) -> str:
    """'De 0,5 a 1 kg' / '0,5 a 1 KG' -> '05a1kg'; '19 a R$ 48,99' / '19 a 48,99' -> '19a4899'. Sem acento, sem R$, sem pontuação."""
    t = unicodedata.normalize("NFKD", str(txt or "")).encode("ascii", "ignore").decode().lower()
    t = t.replace("r$", "")
    t = re.sub(r"[^a-z0-9]", "", t)
    if re.match(r"de\d", t):   # "De 2 a 3 kg" e "2 a 3 kg" são a mesma linha da tabela
        t = t[2:]
    return t


def _canonico(txt, rotulos: list[str]) -> str | None:
    chave = _chave(txt)
    if not chave:
        return None
    for r in rotulos:
        if _chave(r) == chave:
            return r
    return None


def canonico_peso(txt) -> str | None:
    """Rótulo exato da tabela de frete do ML para o peso, ou None se não existir."""
    return _canonico(txt, _tabela().PESOS)


def canonico_faixa(txt) -> str | None:
    """Rótulo exato da faixa de valor da tabela de frete do ML, ou None se não existir."""
    return _canonico(txt, _tabela().FAIXAS_VALOR)


def faixa_do_preco(preco: float) -> str:
    """Faixa de valor da tabela em que o preço (o promocional, que é o cobrado do cliente) cai: a mesma regra do backend."""
    return _tabela().faixa_por_preco(preco)
