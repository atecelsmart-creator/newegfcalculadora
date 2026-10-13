"""Progresso salvo a cada SKU: se travar, o robô retoma de onde parou."""
import json
import os
import time
from pathlib import Path


def carregar(caminho: Path) -> dict | None:
    if not caminho.exists():
        return None
    try:
        return json.loads(caminho.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise RuntimeError(f"Arquivo de progresso ilegível ({caminho}): {e}. Apague-o ou use --recomecar.")


def salvar(caminho: Path, estado: dict) -> None:
    """Grava num .tmp e troca o arquivo. No Windows a troca pode dar 'Acesso negado' por uns instantes
    (antivírus, OneDrive ou o indexador segurando o arquivo): tenta de novo e, se não der, grava direto."""
    caminho.parent.mkdir(parents=True, exist_ok=True)
    texto = json.dumps(estado, ensure_ascii=False, separators=(",", ":"))
    tmp = caminho.with_name(caminho.name + ".tmp")
    ultimo = None
    for tentativa in range(6):
        try:
            tmp.write_text(texto, encoding="utf-8")
            os.replace(tmp, caminho)
            return
        except OSError as e:
            ultimo = e
            time.sleep(0.15 * (tentativa + 1))
    try:   # última saída: escrita direta (menos segura contra queda de energia, mas não perde o progresso)
        caminho.write_text(texto, encoding="utf-8")
        tmp.unlink(missing_ok=True)
        return
    except OSError as e:
        ultimo = e
    raise OSError(f"Não consegui salvar o progresso em {caminho}: {ultimo}")
