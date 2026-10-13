"""
Executa o robô de preços em segundo plano, para a tela "Automático" da calculadora (sem linha de comando).

É o mesmo caminho do `python -m rpa.main`: lê os SKUs da planilha, busca os dados de cada um, valida, define o cenário,
calcula na calculadora e (se pedido) grava na planilha. A diferença é que aqui o andamento fica guardado em memória
para a tela consultar (barra de progresso e lista de produtos).

Só roda um lote por vez. A FONTE DE DADOS de hoje é o CSV de teste; os coletores reais (Citel, Econet, Confaz)
entram depois no lugar do FonteCSV, sem mudar o resto.
"""
import threading
from datetime import datetime
from pathlib import Path

from rpa import cliente_api, config, relatorio
from rpa.fonte_csv import FonteCSV
from rpa.main import processar_sku

from app.planilha_ml import online   # o robô grava na mesma planilha online que a aba Tabela mostra
from app.planilha_ml.editor import perfil_de

CAMPOS_TELA = ("sku", "titulo", "status", "motivo", "cenario", "preco_antes", "preco_cheio",
               "preco_promocional", "margem_promocional", "gravado", "preco_enviado", "hora", "detalhes")


class LoteEmAndamento(Exception):
    """Já existe um lote rodando."""


class Lote:
    def __init__(self, params: dict):
        self.params = params
        self.estado = "rodando"          # rodando | concluido | cancelado | erro
        self.total = 0
        self.linhas: list[dict] = []
        self.erro = ""
        self.relatorio: Path | None = None
        self.cancelar = threading.Event()
        self.trava = threading.Lock()
        self.inicio = datetime.now()

    def snapshot(self, desde: int = 0) -> dict:
        with self.trava:
            contagem = {"OK": 0, "ABAIXO DO PMA": 0, "REVISAR": 0}
            for l in self.linhas:
                contagem[l.get("status", "REVISAR")] = contagem.get(l.get("status", "REVISAR"), 0) + 1
            novas = [{k: l.get(k) for k in CAMPOS_TELA} for l in self.linhas[max(desde, 0):]]
            return {
                "estado": self.estado,
                "total": self.total,
                "feitos": len(self.linhas),
                "contagem": contagem,
                "linhas": novas,
                "proximo": len(self.linhas),
                "erro": self.erro,
                "gravando": bool(self.params.get("gravar")),
                "tem_relatorio": self.relatorio is not None,
            }


_atual: Lote | None = None
_trava_global = threading.Lock()


def lote_atual() -> Lote | None:
    return _atual


def _agora() -> str:
    return datetime.now().strftime("%H:%M:%S")


def _skus_e_dados_da_planilha(planilha: str) -> tuple[list[str], dict]:
    r = cliente_api.listar_skus(planilha)
    vistos, skus, extra = set(), [], {}
    for it in r["itens"]:
        sku = (it.get("sku") or "").strip()
        if sku and sku.upper() not in vistos:
            vistos.add(sku.upper())
            skus.append(sku)
            extra[sku.upper()] = {"titulo": it.get("titulo"), "preco_antes": it.get("preco_atual")}
    return skus, extra


def _skus_e_dados_da_sessao(sessao: str) -> tuple[list[str], dict]:
    """SKUs da planilha Shopee que o cliente enviou na tela (a mesma que a aba Tabela mostra)."""
    d = online.visualizar(sessao, perfil_de(config.MARKETPLACE), "", 1, 100000)
    if not d.get("carregado"):
        nome = perfil_de(config.MARKETPLACE).nome
        raise ValueError(f"Nenhuma planilha do {nome} foi enviada ainda. Envie na aba Calculadora SP (quadro Tabela → Online → Escolher tabela).")
    vistos, skus, extra = set(), [], {}
    for it in d["linhas"]:
        sku = (it.get("sku") or "").strip()
        if sku and sku.upper() not in vistos:
            vistos.add(sku.upper())
            skus.append(sku)
            extra[sku.upper()] = {"titulo": it.get("titulo"), "preco_antes": it.get("preco_atual")}
    return skus, extra


def _gravador_online(sessao: str, cor: str):
    """Grava na planilha online da tela, pelas mesmas regras do preenchimento manual (e com a cor escolhida na Tabela)."""
    perfil = perfil_de(config.MARKETPLACE)

    def gravar(sku, preco_cheio, preco_promocional):
        if config.PRECO_QUE_SOBE == "promocional":
            preco_cheio, preco_promocional = preco_promocional, None
        return online.gravar(sessao, sku, preco_cheio, preco_promocional, perfil, cor)
    return gravar


def _rodar(lote: Lote) -> None:
    p = lote.params
    try:
        if not p.get("sessao"):
            cliente_api.verificar_backend()
        fonte = FonteCSV(p["csv"])
        skus, extra = _skus_e_dados_da_sessao(p["sessao"]) if p.get("sessao") else _skus_e_dados_da_planilha(p["planilha"])
        gravador = _gravador_online(p["sessao"], p.get("cor", "")) if p.get("sessao") else None
        no_csv = fonte.skus()
        skus = [s for s in skus if s.upper() in no_csv]   # só os SKUs que existem no arquivo de dados
        if not skus:
            raise ValueError("Nenhum SKU da planilha está no arquivo de dados.")
        lote.total = len(skus)

        concluiu = True
        for sku in skus:
            if lote.cancelar.is_set():
                concluiu = False
                break
            linha = processar_sku(sku, fonte, p["planilha"], p["margem"], p["desconto"], p["gravar"], gravador)
            linha.update(extra.get(sku.upper(), {}))
            linha["hora"] = _agora()
            with lote.trava:
                lote.linhas.append(linha)
        lote.estado = "concluido" if concluiu else "cancelado"
    except (cliente_api.ErroApi, OSError, ValueError) as e:
        lote.erro = str(e)
        lote.estado = "erro"
    except Exception as e:   # nada derruba o servidor
        lote.erro = f"Erro inesperado: {type(e).__name__}: {e}"
        lote.estado = "erro"
    finally:
        with lote.trava:
            linhas = list(lote.linhas)
        if linhas:
            try:
                prefixo = f"{p.get('marketplace', config.MARKETPLACE)}_sp" + ("" if p["gravar"] else "_simulacao")
                lote.relatorio = relatorio.gerar(linhas, config.PASTA_RELATORIOS, prefixo)
            except Exception as e:
                lote.erro = (lote.erro + " | " if lote.erro else "") + f"Não consegui gerar o relatório: {e}"


def iniciar(planilha: str, csv: str, margem: float, desconto: float, gravar: bool, preco_que_sobe: str,
            sessao: str = "", cor: str = "", marketplace: str = "shopee") -> Lote:
    """margem e desconto em FRAÇÃO (0.15 = 15%). Com `sessao`, trabalha na planilha online da tela; sem, no arquivo do PC (`planilha`).
    `marketplace`: um de config.MARKETPLACES_ROBO (Shopee ou TikTok, ambos em SP)."""
    global _atual
    if marketplace not in config.MARKETPLACES_ROBO:
        raise ValueError("O robô, por enquanto, só atende: " + ", ".join(config.MARKETPLACES_ROBO) + ".")
    if preco_que_sobe not in ("cheio", "promocional"):
        raise ValueError("Escolha qual preço sobe na planilha: cheio ou promocional.")
    if not (0 < margem < 1):
        raise ValueError("Informe a margem desejada entre 0% e 100%.")
    if not (0 <= desconto < 1):
        raise ValueError("Informe o desconto promocional entre 0% e 100% (0 = nenhum).")
    if not planilha and not sessao:
        raise ValueError("Escolha a planilha da Shopee.")
    if not csv:
        raise ValueError("Escolha o arquivo de dados dos produtos (CSV).")
    with _trava_global:
        if _atual is not None and _atual.estado == "rodando":
            raise LoteEmAndamento("Já existe um lote rodando. Espere terminar ou cancele.")
        config.PRECO_QUE_SOBE = preco_que_sobe
        config.MARKETPLACE = marketplace   # o lote inteiro (payload, planilha, detalhes) segue este marketplace
        lote = Lote({"planilha": planilha, "csv": csv, "margem": margem, "desconto": desconto,
                     "gravar": gravar, "preco_que_sobe": preco_que_sobe, "sessao": sessao, "cor": cor,
                     "marketplace": marketplace})
        _atual = lote
        threading.Thread(target=_rodar, args=(lote,), daemon=True, name="robo-precos").start()
        return lote


def limpar() -> bool:
    """Esquece o último lote (a lista de resultados da tela). Não mexe nos preços já gravados na planilha. Recusa se ainda está rodando."""
    global _atual
    with _trava_global:
        if _atual is not None and _atual.estado == "rodando":
            return False
        _atual = None
        return True


def cancelar() -> bool:
    lote = _atual
    if lote is None or lote.estado != "rodando":
        return False
    lote.cancelar.set()
    return True
