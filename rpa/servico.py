"""
Executa o robô de preços em segundo plano, para a tela "Automático" da calculadora (sem linha de comando).

É o mesmo caminho do `python -m rpa.main`: lê os SKUs da planilha, busca os dados de cada um, valida, define o cenário,
calcula na calculadora e (se pedido) grava na planilha. A diferença é que aqui o andamento fica guardado em memória
para a tela consultar (barra de progresso e lista de produtos).

Só roda um lote por vez. A FONTE DE DADOS de hoje é o CSV de teste; os coletores reais (Citel, Econet, Confaz)
entram depois no lugar do FonteCSV, sem mudar o resto.
"""
import json
import os
import re
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path

from rpa import cliente_api, config, relatorio
from rpa.fonte_csv import FonteCSV
from rpa.main import processar_sku

from app.planilha_ml import arquivo, editor, online   # o robô grava na mesma planilha online que a aba Tabela mostra (e, no modo Computador, também no arquivo do PC)
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


_lotes: dict[str, Lote] = {}   # um lote por estado: SP e RJ têm, cada um, os seus próprios resultados
_ultimo: Lote | None = None    # o último lote iniciado, de qualquer estado
_trava_global = threading.Lock()


def _chave(estado: str | None, dono: str = "") -> str:
    """Chave do lote. Local: o estado (SP/RJ). Online: a sessão do navegador (`dono`) — cada navegador só enxerga o próprio lote,
    porque o lote traz custos dos produtos. A sessão já chega validada (robo.py) e aqui ainda perde qualquer caractere de caminho."""
    dono = (dono or "").strip()
    if dono:
        return re.sub(r"[^A-Za-z0-9_-]", "_", dono)
    return (estado or "SP").strip().upper()


def lote_atual(estado: str | None = None, dono: str = "") -> Lote | None:
    """Lote do estado pedido (SP ou RJ). Sem `estado`, o último que foi iniciado (qualquer estado).
    Se o servidor foi reiniciado, os resultados voltam do disco: só somem com o botão Limpar."""
    global _ultimo
    if estado is None:
        if _ultimo is None:
            achados = [l for l in (lote_atual(e) for e in config.ESTADOS_ROBO) if l is not None]
            if achados:
                _ultimo = max(achados, key=lambda l: l.inicio)
        return _ultimo
    chave = _chave(estado, dono)
    lote = _lotes.get(chave)
    if lote is None:
        with _trava_global:
            lote = _lotes.get(chave)
            if lote is None:
                lote = _ler_do_disco(chave)
                if lote is not None:
                    _lotes[chave] = lote
                    if _ultimo is None:
                        _ultimo = lote
    return lote


# ---- Resultados guardados em disco (um arquivo por estado): sobrevivem a F5, a reinício do servidor e a fechar o .bat.
# Só o botão Limpar apaga. (O servidor roda com --reload: sem isto, qualquer alteração em um .py zerava a lista do robô.)
PASTA_LOTES = Path(__file__).resolve().parent / ".lotes"


def _arquivo_lote(chave: str) -> Path:   # chave = "SP"/"RJ" (local) ou a sessão do navegador (online)
    return PASTA_LOTES / ("lote_" + re.sub(r"[^A-Za-z0-9_-]", "_", chave) + ".json")


def _descartar_antigos() -> None:
    """Online: lotes de sessões paradas há mais de 12 h saem da memória e do disco (o servidor não acumula custos de ninguém). SP/RJ do modo local ficam."""
    limite = datetime.now() - timedelta(hours=12)
    for k in [k for k, l in _lotes.items() if k not in config.ESTADOS_ROBO and l.estado != "rodando" and l.inicio < limite]:
        _lotes.pop(k, None)
    try:
        corte = time.time() - 12 * 3600
        for f in PASTA_LOTES.glob("lote_*.json"):
            if f.stem not in ("lote_SP", "lote_RJ") and f.stat().st_mtime < corte:
                f.unlink(missing_ok=True)
    except OSError:
        pass


def _salvar(lote: Lote) -> None:
    try:
        PASTA_LOTES.mkdir(parents=True, exist_ok=True)
        with lote.trava:
            dados = {"params": lote.params, "estado": lote.estado, "total": lote.total, "linhas": list(lote.linhas),
                     "erro": lote.erro, "relatorio": str(lote.relatorio) if lote.relatorio else "",
                     "inicio": lote.inicio.isoformat()}
            texto = json.dumps(dados, ensure_ascii=False, default=str)
        arq = _arquivo_lote(_chave(lote.params.get("estado", "SP"), lote.params.get("dono", "")))
        tmp = arq.with_suffix(".tmp")
        tmp.write_text(texto, encoding="utf-8")
        os.replace(tmp, arq)
    except Exception:   # noqa: BLE001 - guardar em disco nunca pode derrubar o robô
        pass


def _ler_do_disco(estado: str) -> Lote | None:
    try:
        d = json.loads(_arquivo_lote(estado).read_text(encoding="utf-8"))
        lote = Lote(d["params"])
        lote.estado = d.get("estado") or "concluido"
        if lote.estado == "rodando":   # o servidor reiniciou no meio do lote: a execução parou, os resultados já feitos ficam
            lote.estado = "cancelado"
            lote.erro = lote.erro or "O servidor foi reiniciado durante a execução; os produtos já calculados foram mantidos."
        lote.total = int(d.get("total") or 0)
        lote.linhas = list(d.get("linhas") or [])
        lote.erro = d.get("erro") or lote.erro
        if d.get("relatorio") and Path(d["relatorio"]).is_file():
            lote.relatorio = Path(d["relatorio"])
        try:
            lote.inicio = datetime.fromisoformat(d["inicio"])
        except (KeyError, ValueError, TypeError):
            pass
        return lote
    except (OSError, ValueError, KeyError, TypeError):
        return None


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
    """SKUs da planilha do marketplace do lote que o cliente enviou na tela (a mesma que a aba Tabela mostra)."""
    d = online.visualizar(sessao, perfil_de(config.MARKETPLACE), "", 1, 100000)
    if not d.get("carregado"):
        nome = perfil_de(config.MARKETPLACE).nome
        raise ValueError(f"Nenhuma planilha do {nome} foi enviada ainda. Envie na aba Calculadora {config.ESTADO} (quadro Tabela → Online → Escolher tabela).")
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
        return online.gravar(sessao, sku, preco_cheio, preco_promocional, perfil, cor, reutilizar=True)
    return gravar


def _gravador_pc_e_copia(sessao: str, planilha: str, cor: str):
    """Modo Computador: grava o preço no arquivo do PC (com backup e conferência, como na Calculadora) e depois na cópia que a
    aba Tabela mostra. Se o arquivo do PC recusar, a exceção vira o motivo da linha e a cópia não é tocada."""
    perfil = perfil_de(config.MARKETPLACE)

    def gravar(sku, preco_cheio, preco_promocional):
        if config.PRECO_QUE_SOBE == "promocional":
            preco_cheio, preco_promocional = preco_promocional, None
        r = arquivo.gravar(planilha, sku, preco_cheio, preco_promocional, perfil, reutilizar=True)
        if r.get("conferencia_ok", False):
            try:
                online.gravar(sessao, sku, preco_cheio, preco_promocional, perfil, cor, reutilizar=True)
            except Exception as e:   # noqa: BLE001
                r.setdefault("avisos", []).append(f"Gravei no arquivo do PC, mas a cópia da aba Tabela não foi atualizada ({e}).")
        return r
    return gravar


def _rodar(lote: Lote) -> None:
    p = lote.params
    try:
        if not p.get("sessao"):
            cliente_api.verificar_backend()
        fonte = FonteCSV(p["csv"])
        skus, extra = _skus_e_dados_da_sessao(p["sessao"]) if p.get("sessao") else _skus_e_dados_da_planilha(p["planilha"])
        no_pc = bool(p.get("sessao") and p.get("planilha"))   # modo Computador: tem a cópia (sessão) E o arquivo do PC
        if no_pc and p["gravar"]:
            try:
                arquivo.caminho(p["planilha"])   # o arquivo ainda existe?
            except Exception as e:   # noqa: BLE001
                raise ValueError(str(e))
        if no_pc:
            gravador = _gravador_pc_e_copia(p["sessao"], p["planilha"], p.get("cor", ""))
        else:
            gravador = _gravador_online(p["sessao"], p.get("cor", "")) if p.get("sessao") else None
        no_csv = fonte.skus()
        skus = [s for s in skus if s.upper() in no_csv]   # só os SKUs que existem no arquivo de dados
        if not skus:
            raise ValueError("Nenhum SKU da planilha está no arquivo de dados.")
        lote.total = len(skus)

        concluiu = True
        ultimo_salvo = time.monotonic()
        for sku in skus:
            if lote.cancelar.is_set():
                concluiu = False
                break
            linha = processar_sku(sku, fonte, p["planilha"], p["margem"], p["desconto"], p["gravar"], gravador)
            linha.update(extra.get(sku.upper(), {}))
            linha["hora"] = _agora()
            with lote.trava:
                lote.linhas.append(linha)
            if time.monotonic() - ultimo_salvo > 5:   # guarda em disco de tempos em tempos (não a cada produto: a lista pode ser grande)
                _salvar(lote)
                ultimo_salvo = time.monotonic()
        lote.estado = "concluido" if concluiu else "cancelado"
    except (cliente_api.ErroApi, OSError, ValueError) as e:
        lote.erro = str(e)
        lote.estado = "erro"
    except Exception as e:   # nada derruba o servidor
        lote.erro = f"Erro inesperado: {type(e).__name__}: {e}"
        lote.estado = "erro"
    finally:
        if p.get("sessao") and p.get("planilha") and p.get("gravar"):   # o arquivo do PC mudou por causa do lote: a cópia continua valendo para ele
            try:
                from app.api.planilha_ml import _marcar_origem
                _marcar_origem(p["sessao"], perfil_de(config.MARKETPLACE), arquivo.caminho(p["planilha"]))
            except Exception:   # noqa: BLE001
                pass
        with lote.trava:
            linhas = list(lote.linhas)
        if linhas:
            try:
                prefixo = f"{p.get('marketplace', config.MARKETPLACE)}_{p.get('estado', 'SP').lower()}" + ("" if p["gravar"] else "_simulacao")
                lote.relatorio = relatorio.gerar(linhas, config.PASTA_RELATORIOS, prefixo)
            except Exception as e:
                lote.erro = (lote.erro + " | " if lote.erro else "") + f"Não consegui gerar o relatório: {e}"
        editor.limpar_cache()   # solta as planilhas que ficaram abertas na memória durante o lote
        _salvar(lote)


def iniciar(planilha: str, csv: str, margem: float, desconto: float, gravar: bool, preco_que_sobe: str,
            sessao: str = "", cor: str = "", marketplace: str = "shopee", estado: str = "SP", dono: str = "") -> Lote:
    """margem e desconto em FRAÇÃO (0.15 = 15%). Com `sessao`, trabalha na planilha online da tela; sem, no arquivo do PC (`planilha`).
    `marketplace`: um de config.MARKETPLACES_ROBO (Shopee, TikTok ou Mercado Livre). `estado`: um de config.ESTADOS_ROBO (SP ou RJ; no RJ não há ST)."""
    global _ultimo
    estado = _chave(estado)
    if estado not in config.ESTADOS_ROBO:
        raise ValueError("O robô só atende os estados: " + ", ".join(config.ESTADOS_ROBO) + ".")
    if marketplace not in config.MARKETPLACES_ROBO:
        raise ValueError("O robô, por enquanto, só atende: Shopee, TikTok Shop e Mercado Livre.")
    if preco_que_sobe not in ("cheio", "promocional"):
        raise ValueError("Escolha qual preço sobe na planilha: cheio ou promocional.")
    if not (0 < margem < 1):
        raise ValueError("Informe a margem desejada entre 0% e 100%.")
    if not (0 <= desconto < 1):
        raise ValueError("Informe o desconto promocional entre 0% e 100% (0 = nenhum).")
    if not planilha and not sessao:
        raise ValueError("Escolha a planilha do marketplace.")
    if not csv:
        raise ValueError("Escolha o arquivo de dados dos produtos (CSV).")
    chave = _chave(estado, dono)
    with _trava_global:
        _descartar_antigos()
        rodando = next((k for k, l in _lotes.items() if l.estado == "rodando"), None)
        if rodando is not None:   # o motor usa configurações globais (config.ESTADO etc.): um lote por vez, mesmo entre SP e RJ (e entre usuários, online)
            if rodando == chave:
                raise LoteEmAndamento("Já existe um lote rodando. Espere terminar ou cancele.")
            raise LoteEmAndamento("Outro lote do robô ainda está rodando. Espere terminar (um de cada vez)." if dono
                                  else f"O robô do {rodando} ainda está rodando. Espere terminar ou cancele (um de cada vez).")
        config.PRECO_QUE_SOBE = preco_que_sobe
        config.MARKETPLACE = marketplace   # o lote inteiro (payload, planilha, detalhes) segue este marketplace
        config.ESTADO = estado             # ... e este estado (SP ou RJ)
        lote = Lote({"planilha": planilha, "csv": csv, "margem": margem, "desconto": desconto,
                     "gravar": gravar, "preco_que_sobe": preco_que_sobe, "sessao": sessao, "cor": cor,
                     "marketplace": marketplace, "estado": estado, "dono": dono})
        _lotes[chave] = lote
        _ultimo = lote
        _salvar(lote)
        threading.Thread(target=_rodar, args=(lote,), daemon=True, name="robo-precos").start()
        return lote


def limpar(estado: str | None = None, dono: str = "") -> bool:
    """Esquece o lote do estado (a lista de resultados da tela daquele estado; o outro estado não é tocado). Sem `estado`, esquece os de todos.
    Não mexe nos preços já gravados na planilha. Recusa se ainda está rodando."""
    global _ultimo
    with _trava_global:
        alvo = sorted(set(_lotes) | set(config.ESTADOS_ROBO)) if estado is None else [_chave(estado, dono)]
        if any(_lotes.get(e) is not None and _lotes[e].estado == "rodando" for e in alvo):
            return False
        for e in alvo:
            _lotes.pop(e, None)
            try:
                _arquivo_lote(e).unlink(missing_ok=True)   # o Limpar apaga também o que estava guardado em disco
            except OSError:
                pass
        if _ultimo is not None and _ultimo not in _lotes.values():
            _ultimo = None
        return True


def cancelar(estado: str | None = None, dono: str = "") -> bool:
    lotes = list(_lotes.values()) if estado is None else [_lotes.get(_chave(estado, dono))]
    achou = False
    for lote in lotes:
        if lote is not None and lote.estado == "rodando":
            lote.cancelar.set()
            achou = True
    return achou
