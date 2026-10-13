"""
Orquestrador do robô de preços, Shopee / SP (primeira etapa).

Roda SKU a SKU: lê os dados -> valida -> define o cenário -> calcula -> (grava) -> relatório.
Qualquer dúvida bloqueia o preço daquela linha e segue para a próxima.

Uso (na raiz do projeto, com o backend rodando):
    python -m rpa.main --planilha "C:\\caminho\\shopee.xlsx" --csv rpa\\dados_teste.csv --margem 0.15 --desconto 0.10

SEM --gravar é SIMULAÇÃO: calcula e gera o relatório, mas não mexe na planilha.
Com --gravar, escreve na planilha (o gravador faz backup _ORIGINAL_BACKUP antes da primeira escrita).
"""
import argparse
import sys
from datetime import datetime
from pathlib import Path

from rpa import cenario, cliente_api, config, detalhes, progresso, relatorio, validador
from rpa.fonte_csv import FonteCSV

CONCLUIDOS = {"OK", "ABAIXO DO PMA"}   # esses não são refeitos ao retomar; REVISAR é tentado de novo


def _agora() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _reais(x: float) -> str:
    return "R$ " + f"{x:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _preencher_dados(linha: dict, d) -> None:
    linha.update(
        codigo_fabricante=d.codigo_fabricante, ncm=d.ncm, aliq_icms=d.aliq_icms, unitario=d.unitario,
        perc_ipi=d.perc_ipi, perc_frete=d.perc_frete, st_status=d.st.status, mva=d.st.mva,
        confaz_status=d.confaz.status,
    )


def processar_sku(sku: str, fonte, planilha: str, margem: float, desconto: float, gravar: bool, gravador=None) -> dict:
    """gravador(sku, preco_cheio, preco_promocional) -> dict: grava de outro jeito (ex.: planilha online da tela). Padrão: arquivo do PC."""
    linha = {"sku": sku, "status": "REVISAR", "motivo": "", "gravado": False}
    try:
        dados = fonte.obter(sku)
        if dados is None:
            linha["motivo"] = "SKU não encontrado na fonte de dados"
            return linha
        _preencher_dados(linha, dados)

        motivos = validador.validar(dados)
        if motivos:
            linha["motivo"] = " | ".join(motivos)
            return linha

        decisao = cenario.definir_cenario(dados, config.ESTADO)
        if not decisao.ok:
            linha["motivo"] = decisao.motivo
            if dados.confaz.status in ("CONDICIONAL", "FALHOU") and dados.confaz.detalhe:
                linha["motivo"] += " | Confaz: " + dados.confaz.detalhe   # diz qual item do Convênio conferir
            return linha
        linha["cenario"] = decisao.cenario

        res = cliente_api.calcular(cliente_api.montar_payload(dados, decisao, margem, desconto))
        linha.update(preco_cheio=res["preco_cheio"], preco_promocional=res["preco_promocional"],
                     margem_promocional=res["margem_promocional"])
        linha["detalhes"] = detalhes.montar(dados, decisao, res, margem, desconto)   # tudo que foi aplicado (popup da linha)

        desvio = abs(res["margem_promocional"] - margem)
        if desvio > config.TOLERANCIA_MARGEM:
            linha["motivo"] = (f"Margem promocional {res['margem_promocional']:.2%} fora do esperado "
                               f"({margem:.2%} ± {config.TOLERANCIA_MARGEM:.2%})")
            return linha

        obs = []
        status = "OK"
        pma = res.get("pma")
        if pma and pma.get("abaixo"):
            status = "ABAIXO DO PMA"
            obs.append(f"Promocional abaixo da REVENDA do PMA (faltam {_reais(pma.get('diferenca') or 0)})")
            if not config.GRAVAR_ABAIXO_DO_PMA:
                linha["status"] = status
                linha["motivo"] = obs[0] + "; preço não gravado até você decidir"
                return linha
        elif pma and not pma.get("encontrado"):
            obs.append("Código não encontrado na tabela PMA (sem comparação)")
        elif pma is None:
            obs.append("Sem comparação com o PMA")

        if not gravar:
            obs.append("simulação: nada foi gravado")
        else:
            if gravador is not None:
                r = gravador(sku, res["preco_cheio"], res["preco_promocional"])
            else:
                r = cliente_api.gravar(planilha, sku, res["preco_cheio"], res["preco_promocional"])
            if not r.get("conferencia_ok", False):
                linha["motivo"] = "Conferência da gravação falhou: " + ", ".join(r.get("diferencas") or [])
                return linha
            linha["gravado"] = True
            linha["preco_enviado"] = (res["preco_promocional"] if config.PRECO_QUE_SOBE == "promocional"
                                      else res["preco_cheio"])
            obs.extend(r.get("avisos") or [])

        linha["status"] = status
        linha["motivo"] = "; ".join(obs)
        return linha
    except cliente_api.ErroApi as e:
        linha["motivo"] = str(e)
        return linha
    except Exception as e:   # um SKU com problema nunca derruba o lote
        linha["motivo"] = f"Erro inesperado: {type(e).__name__}: {e}"
        return linha


def _skus_da_planilha(planilha: str) -> list[str]:
    r = cliente_api.listar_skus(planilha)
    vistos, skus, sem_sku = set(), [], 0
    for it in r["itens"]:
        sku = (it.get("sku") or "").strip()
        if not sku:
            sem_sku += 1
        elif sku.upper() not in vistos:
            vistos.add(sku.upper())
            skus.append(sku)
    print(f"Planilha: {r['nome_arquivo']} - {r['total']} linhas, {len(skus)} SKUs únicos"
          + (f" ({sem_sku} linhas sem SKU, ignoradas)" if sem_sku else ""))
    return skus


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Robô de atualização de preços - Shopee SP")
    ap.add_argument("--planilha", default=config.CAMINHO_PLANILHA, help="caminho da planilha da Shopee")
    ap.add_argument("--csv", required=True, help="CSV com os dados dos produtos (fonte de teste)")
    ap.add_argument("--margem", type=float, default=config.MARGEM_DESEJADA, help="margem desejada em fração (0.15 = 15%%)")
    ap.add_argument("--desconto", type=float, default=config.DESCONTO_PROMOCIONAL, help="desconto promocional em fração (0 = nenhum)")
    ap.add_argument("--gravar", action="store_true", help="grava na planilha (sem isso é só simulação)")
    ap.add_argument("--sku", action="append", help="processa só este SKU (pode repetir)")
    ap.add_argument("--limite", type=int, help="processa no máximo N SKUs pendentes")
    ap.add_argument("--recomecar", action="store_true", help="ignora o progresso salvo")
    ap.add_argument("--so-do-csv", action="store_true", help="processa só os SKUs da planilha que também estão no CSV")
    a = ap.parse_args(argv)

    if not a.planilha:
        return _erro("Informe --planilha.")
    if a.margem is None or not (0 < a.margem < 1):
        return _erro("Informe --margem entre 0 e 1 (ex.: 0.15). O robô não assume valor padrão.")
    if a.desconto is None or not (0 <= a.desconto < 1):
        return _erro("Informe --desconto entre 0 e 1 (use 0 para nenhum). O robô não assume valor padrão.")

    try:
        cliente_api.verificar_backend()
        fonte = FonteCSV(a.csv)
        skus = a.sku or _skus_da_planilha(a.planilha)
        if a.so_do_csv:
            no_csv = fonte.skus()
            skus = [s for s in skus if s.upper() in no_csv]
            print(f"{len(skus)} SKUs da planilha estão no CSV")
    except (cliente_api.ErroApi, OSError) as e:
        return _erro(str(e))

    parametros = {"planilha": str(Path(a.planilha)), "margem": a.margem, "desconto": a.desconto,
                  "gravar": a.gravar, "preco_que_sobe": config.PRECO_QUE_SOBE}
    arq_progresso = config.PASTA_PROGRESSO / "shopee_sp.json"
    estado = None if a.recomecar else progresso.carregar(arq_progresso)
    if estado and estado.get("parametros") != parametros:
        return _erro("Existe progresso salvo com parâmetros diferentes (planilha, margem, desconto ou modo gravar). "
                     "Use --recomecar para começar um lote novo.")
    if not estado:
        estado = {"parametros": parametros, "linhas": {}}

    pendentes = [s for s in skus if estado["linhas"].get(s, {}).get("status") not in CONCLUIDOS]
    if a.limite:
        pendentes = pendentes[:a.limite]
    print(f"Modo: {'GRAVANDO na planilha' if a.gravar else 'SIMULAÇÃO (não grava)'} | {len(pendentes)} SKUs a processar")
    avisou_progresso = False

    try:
        for i, sku in enumerate(pendentes, 1):
            linha = processar_sku(sku, fonte, a.planilha, a.margem, a.desconto, a.gravar)
            linha["hora"] = _agora()
            estado["linhas"][sku] = linha
            try:
                progresso.salvar(arq_progresso, estado)
            except OSError as e:   # não derruba o lote por causa do arquivo de progresso
                if not avisou_progresso:
                    print(f"AVISO: {e}. O lote continua, mas esta execução pode não ser retomável.")
                    avisou_progresso = True
            print(f"[{i}/{len(pendentes)}] {sku}: {linha['status']}" + (f" - {linha['motivo']}" if linha["motivo"] else ""))
    except KeyboardInterrupt:
        print("Interrompido. O progresso foi salvo; rode de novo para retomar.")
    finally:
        linhas = [estado["linhas"][s] for s in skus if s in estado["linhas"]]
        if linhas:
            print("Relatório:", relatorio.gerar(linhas, config.PASTA_RELATORIOS))
    return 0


def _erro(msg: str) -> int:
    print("ERRO:", msg, file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
