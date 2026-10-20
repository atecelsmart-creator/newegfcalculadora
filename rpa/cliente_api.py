"""
Cliente HTTP do backend local (127.0.0.1:8000). O motor de cálculo NÃO é alterado:
o robô só monta o pedido, chama /api/calcular e /api/planilha-ml/arquivo/gravar e lê a resposta.
"""
import requests

from rpa import config
from rpa import ml_frete
from rpa import modelos as m
from rpa.cenario import Decisao

# O backend (modo local) só aceita as rotas de planilha/robô de quem tem o cookie local; o token fica neste arquivo,
# criado pelo próprio backend ao iniciar (backend/app/core/seguranca.py).
_ARQUIVO_TOKEN = config.RAIZ.parent / "backend" / "data" / ".local_token"


def _cookies() -> dict:
    try:
        t = _ARQUIVO_TOKEN.read_text(encoding="utf-8").strip()
    except OSError:
        return {}
    return {"calc_local": t} if t else {}


class ErroApi(Exception):
    """Falha ao falar com o backend ou recusa dele. A mensagem já serve para o relatório."""


def _base() -> str:
    return config.API_URL.rstrip("/")


def _detalhe(r: requests.Response) -> str:
    try:
        d = r.json().get("detail", r.text)
    except Exception:
        d = r.text
    return f"HTTP {r.status_code}: {d}"


def _post(url: str, **kw) -> requests.Response:
    try:
        return requests.post(url, timeout=120, cookies=_cookies(), **kw)
    except requests.RequestException as e:
        raise ErroApi(f"Backend inacessível ({e}). Ele está rodando em {_base()}?")


def verificar_backend() -> None:
    try:
        r = requests.get(f"{_base()}/api/cenarios", timeout=10)
    except requests.RequestException as e:
        raise ErroApi(f"Backend inacessível ({e}). Suba o calculadora.bat e tente de novo.")
    if r.status_code != 200:
        raise ErroApi(f"O backend respondeu algo inesperado em /api/cenarios ({_detalhe(r)}).")


def montar_payload(dados: m.DadosProduto, decisao: Decisao, margem: float, desconto: float) -> dict:
    """Mapa de campos robô -> calculadora (seção 6 do PDF). Shopee, TikTok e Mercado Livre (SP e RJ)."""
    perc_st = dados.st.mva if decisao.com_st else config.PERC_ST_SEM_ST
    payload = {
        "cenario": decisao.cenario,
        "marketplace": config.MARKETPLACE,
        "estado": config.ESTADO,
        "origem_base_reduzida": decisao.origem_base_reduzida,
        "custo_sem_ipi": dados.unitario,        # PENDENTE (pergunta 1): confirmar que o Unitário já vem sem IPI
        "perc_ipi": dados.perc_ipi,
        "perc_frete": dados.perc_frete,
        "perc_st": perc_st,
        "custo_caixa_papelao": config.CUSTO_CAIXA_PAPELAO,
        "margem_desejada": margem,
        "desconto_promocional": desconto,
    }
    codigo_pma = dados.codigo_fabricante if config.PMA_CODIGO_DE == "fabricante" else dados.sku
    if codigo_pma:
        payload["codigo_pma"] = codigo_pma
    if config.MARKETPLACE == "mercado_livre":
        # Mesmos campos da tela: comissão do produto (C21) e frete (D20) — em R$ direto, ou pela tabela peso x faixa de valor.
        payload["ml_comissao_pct"] = dados.ml_comissao
        if dados.frete_ml is not None and dados.frete_ml > 0:
            payload["custo_frete"] = dados.frete_ml
        else:
            payload["ml_peso"] = ml_frete.canonico_peso(dados.ml_peso)
            payload["ml_faixa_valor"] = ml_frete.canonico_faixa(dados.ml_faixa_valor)
    return payload


def calcular(payload: dict) -> dict:
    r = _post(f"{_base()}/api/calcular", json=payload)
    if r.status_code != 200:
        raise ErroApi(f"Calculadora recusou: {_detalhe(r)}")
    return r.json()


def listar_skus(caminho_planilha: str) -> dict:
    r = _post(f"{_base()}/api/planilha-ml/arquivo/listar-skus",
              data={"caminho": caminho_planilha, "marketplace": config.MARKETPLACE})
    if r.status_code != 200:
        raise ErroApi(f"Não consegui listar os SKUs: {_detalhe(r)}")
    return r.json()


def gravar(caminho_planilha: str, sku: str, preco_cheio: float, preco_promocional: float | None) -> dict:
    """Grava na linha do SKU. O gravador faz backup, valida as regras da Shopee e confere as células alteradas."""
    if config.PRECO_QUE_SOBE == "promocional":
        preco_cheio, preco_promocional = preco_promocional, None
    dados = {"caminho": caminho_planilha, "busca": sku, "marketplace": config.MARKETPLACE,
             "preco_cheio": f"{preco_cheio:.2f}"}
    if preco_promocional is not None:
        dados["preco_promocional"] = f"{preco_promocional:.2f}"
    r = _post(f"{_base()}/api/planilha-ml/arquivo/gravar", data=dados)
    if r.status_code != 200:
        raise ErroApi(f"Gravação recusada: {_detalhe(r)}")
    return r.json()
