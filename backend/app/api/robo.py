"""
Endpoints da aba "Automático" (robô de preços, Shopee SP): iniciar o lote, acompanhar o andamento, cancelar e baixar o relatório.

O robô roda em segundo plano dentro do próprio servidor (rpa/servico.py). Só funciona com a calculadora aberta no próprio PC
(o backend precisa enxergar a planilha), igual ao quadro de planilha local.
"""
import os
import re
import sys
import tempfile
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse

RAIZ_PROJETO = Path(__file__).resolve().parents[3]   # a pasta rpa/ fica na raiz do projeto, fora de backend/
if str(RAIZ_PROJETO) not in sys.path:
    sys.path.insert(0, str(RAIZ_PROJETO))

router = APIRouter(prefix="/robo")


def _local(request: Request) -> None:
    host = request.client.host if request.client else ""
    if host not in ("127.0.0.1", "::1", "localhost"):
        raise HTTPException(status_code=403, detail="O robô só funciona na calculadora aberta no seu computador.")


def _servico():
    try:
        from rpa import servico
        return servico
    except ImportError as e:
        raise HTTPException(status_code=503, detail=f"Falta um componente do robô ({e}). Feche e abra o calculadora.bat e tente de novo.")


@router.post("/escolher-csv")
def escolher_csv(request: Request):
    """Janela do Windows para escolher o arquivo de dados de teste (CSV). Devolve o caminho ('' se cancelou)."""
    _local(request)
    try:
        import tkinter as tk
        from tkinter import filedialog
    except ImportError:
        raise HTTPException(status_code=422, detail="Este computador não tem o seletor de arquivos do Python (tkinter). Digite o caminho.")
    try:
        raiz = tk.Tk()
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Não consegui abrir a janela de escolher arquivo ({e}). Digite o caminho.")
    raiz.withdraw()
    raiz.attributes("-topmost", True)
    try:
        c = filedialog.askopenfilename(parent=raiz, title="Escolha o arquivo de dados de teste (CSV ou XLSX)",
                                       filetypes=[("CSV ou Excel", "*.csv *.xlsx *.xlsm"), ("CSV", "*.csv"), ("Excel", "*.xlsx *.xlsm"), ("Todos os arquivos", "*.*")])
    finally:
        raiz.destroy()
    return {"caminho": os.path.normpath(c) if c else ""}


@router.post("/enviar-dados")
async def enviar_dados(request: Request, arquivo: UploadFile = File(...)):
    """O cliente escolhe o arquivo de dados dos produtos (CSV ou XLSX) direto na tela: guardamos numa pasta temporária e devolvemos o caminho."""
    _local(request)
    nome = Path(arquivo.filename or "dados.csv").name
    ext = Path(nome).suffix.lower()
    if ext not in (".csv", ".xlsx", ".xlsm"):
        raise HTTPException(status_code=422, detail="Envie um arquivo .csv ou .xlsx.")
    conteudo = await arquivo.read(5 * 2 ** 20 + 1)
    if not conteudo or len(conteudo) > 5 * 2 ** 20:
        raise HTTPException(status_code=422, detail="O arquivo está vazio ou passa de 5 MB.")
    pasta = Path(tempfile.gettempdir()) / "calculadora_robo"
    pasta.mkdir(parents=True, exist_ok=True)
    destino = pasta / ("dados_produtos" + ext)
    destino.write_bytes(conteudo)
    return _resumo_dados(destino, nome)


@router.post("/dados-teste")
def dados_teste(request: Request):
    """Usa o arquivo de exemplo que acompanha o projeto (custos fictícios, só para testar): rpa/dados_teste.csv ou rpa/dados_teste.xlsx
    (se existirem os dois, vale o que foi alterado por último)."""
    _local(request)
    candidatos = [p for p in (RAIZ_PROJETO / "rpa" / "dados_teste.csv", RAIZ_PROJETO / "rpa" / "dados_teste.xlsx") if p.is_file()]
    if not candidatos:
        raise HTTPException(status_code=404, detail="Não achei rpa/dados_teste.csv nem rpa/dados_teste.xlsx.")
    arq = max(candidatos, key=lambda p: p.stat().st_mtime)
    return _resumo_dados(arq, f"{arq.name} (exemplo)")


def _resumo_dados(caminho: Path, nome: str) -> dict:
    _servico()
    from rpa.fonte_csv import FonteCSV
    try:
        skus = FonteCSV(caminho).skus()
    except (OSError, ValueError, UnicodeError) as e:
        raise HTTPException(status_code=422, detail=f"Não consegui ler o arquivo ({e}).")
    if not skus:
        raise HTTPException(status_code=422, detail="O arquivo não tem nenhum SKU (precisa da coluna 'sku').")
    return {"caminho": str(caminho), "nome": nome, "skus": len(skus)}


@router.post("/iniciar")
def iniciar(request: Request, planilha: str = Form(""), csv: str = Form(""), margem: float = Form(...),
            desconto: float = Form(...), gravar: bool = Form(False), preco_que_sobe: str = Form("cheio"),
            sessao: str = Form(""), cor: str = Form(""), marketplace: str = Form("shopee")):
    """margem e desconto chegam em % (15 = 15%). Sem 'gravar' é simulação: calcula e mostra, mas não mexe na planilha.
    Com 'sessao', o robô trabalha na planilha online da aba Tabela (a que o cliente enviou); sem, no arquivo do PC ('planilha').
    'marketplace': shopee (padrão) ou tiktok (SP)."""
    _local(request)
    s = _servico()
    cor = cor.strip()
    if cor and not re.fullmatch(r"#[0-9a-fA-F]{6}", cor):
        raise HTTPException(status_code=422, detail="Cor inválida.")
    try:
        s.iniciar(planilha.strip().strip('"'), csv.strip().strip('"'), margem / 100, desconto / 100, gravar,
                  preco_que_sobe, sessao.strip(), cor, marketplace.strip().lower())
    except s.LoteEmAndamento as e:
        raise HTTPException(status_code=409, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return s.lote_atual().snapshot(0)


@router.get("/status")
def status(request: Request, desde: int = Query(0)):
    _local(request)
    s = _servico()
    lote = s.lote_atual()
    if lote is None:
        return {"estado": "parado", "total": 0, "feitos": 0, "contagem": {}, "linhas": [], "proximo": 0,
                "erro": "", "gravando": False, "tem_relatorio": False}
    return lote.snapshot(desde)


@router.get("/sku")
def dados_do_sku(request: Request, sku: str = Query("")):
    """Dados que o robô usou no último lote para este SKU (custo, IPI, frete, ST, cenário, margem, desconto), para a Calculadora
    preencher os campos sozinha. Sem lote ou SKU que o robô não calculou: {"encontrado": false}."""
    _local(request)
    s = _servico()
    from rpa import cenario, config
    alvo = (sku or "").strip().upper()
    lote = s.lote_atual()
    if lote is None or not alvo:
        return {"encontrado": False}
    with lote.trava:
        linhas = list(lote.linhas)
    linha = next((l for l in reversed(linhas) if str(l.get("sku") or "").upper() == alvo), None)
    if not linha or linha.get("unitario") is None:
        return {"encontrado": False}
    cen = linha.get("cenario")
    com_st = bool(cen) and cen.endswith("_com_st")
    return {
        "encontrado": True, "sku": linha.get("sku"), "titulo": linha.get("titulo"), "status": linha.get("status"),
        "motivo": linha.get("motivo"), "cenario": cen,
        "origem": cenario.tipo_produto(linha.get("aliq_icms")) or "nacional",
        "unitario": linha.get("unitario"), "perc_ipi": linha.get("perc_ipi") or 0, "perc_frete": linha.get("perc_frete") or 0,
        "perc_st": (linha.get("mva") or 0) if com_st else 0, "caixa": config.CUSTO_CAIXA_PAPELAO or 0,
        "margem": lote.params.get("margem"), "desconto": lote.params.get("desconto"),
        "preco_cheio": linha.get("preco_cheio"), "preco_promocional": linha.get("preco_promocional"),
        "detalhes": linha.get("detalhes"),   # os mesmos detalhes do pop-up da tabela do robô (clicar no produto da Calculadora abre ele)
    }


@router.post("/cancelar")
def cancelar(request: Request):
    _local(request)
    return {"cancelando": _servico().cancelar()}


@router.post("/limpar")
def limpar(request: Request):
    """Limpa a lista de resultados do robô (não desfaz preços já gravados na planilha)."""
    _local(request)
    if not _servico().limpar():
        raise HTTPException(status_code=409, detail="O robô ainda está rodando. Pare o robô antes de limpar.")
    return {"limpo": True}


@router.get("/relatorio")
def relatorio(request: Request):
    _local(request)
    lote = _servico().lote_atual()
    if lote is None or lote.relatorio is None or not Path(lote.relatorio).is_file():
        raise HTTPException(status_code=404, detail="Ainda não há relatório. Rode um lote primeiro.")
    return FileResponse(lote.relatorio, filename=Path(lote.relatorio).name,
                        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
