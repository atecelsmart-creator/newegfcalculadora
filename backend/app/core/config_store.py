"""
Store genérico de configuração persistida em JSON.

Cada marketplace (Shopee, Mercado Livre, TikTok) tem seus "campos
ajustáveis" (comissão, taxa fixa, mentoria, custo logístico, perda etc.)
guardados num arquivo JSON próprio em backend/data/. Isso permite que a
aba "Campos Ajustáveis" do frontend leia e grave esses valores via API,
sem precisar reiniciar o backend — e sem mexer no código-fonte toda vez
que uma plataforma mudar uma taxa.

Uso: cada módulo de config (ex: app/engine/shopee/constants.py) cria um
JSONConfigStore apontando pro seu próprio arquivo e seus próprios
defaults (extraídos da planilha original).
"""
import json
from pathlib import Path
from threading import Lock


class JSONConfigStore:
    def __init__(self, path: Path, defaults: dict):
        self._path = path
        self._defaults = dict(defaults)
        self._lock = Lock()
        self._dados = self._carregar()

    def _carregar(self) -> dict:
        if self._path.exists():
            try:
                salvo = json.loads(self._path.read_text(encoding="utf-8"))
                # Mescla com os defaults: garante que uma chave nova
                # adicionada no código (ex: um campo novo) não quebre a
                # leitura de um arquivo salvo antes dela existir.
                return {**self._defaults, **salvo}
            except (json.JSONDecodeError, OSError):
                # Arquivo corrompido ou ilegível — não derruba a API,
                # volta pros defaults e deixa o usuário salvar de novo.
                return dict(self._defaults)
        return dict(self._defaults)

    def obter(self) -> dict:
        return dict(self._dados)

    def atualizar(self, novos: dict) -> dict:
        """Mescla só as chaves enviadas (nível superior) e persiste no disco."""
        with self._lock:
            self._dados = {**self._dados, **novos}
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._path.write_text(
                json.dumps(self._dados, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            return dict(self._dados)
