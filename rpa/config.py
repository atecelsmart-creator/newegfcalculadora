"""
Configuração do robô de preços (primeira etapa: Shopee / SP).

Nada aqui é senha. Os valores marcados PENDENTE dependem de confirmação
(seção 12 do PDF de arquitetura) e estão com um padrão provisório.
"""
import os
from pathlib import Path

RAIZ = Path(__file__).resolve().parent

# O robô chama a própria calculadora por HTTP. Local: 127.0.0.1:8000. Online (Render etc.): a porta interna do app, que a plataforma entrega na
# variável PORT — não precisa configurar nada. CALC_API_URL, se definida, vale sempre.
_ONLINE = os.environ.get("MODO", "online").strip().lower() != "local"   # mesmo padrão do backend (app/core/config.py): sem MODO = online
API_URL = os.environ.get("CALC_API_URL") or "http://127.0.0.1:" + (os.environ.get("PORT", "8000") if _ONLINE else "8000")
MARKETPLACE = "shopee"
# Marketplaces que o robô atende (em SP e no RJ). O lote escolhe um deles em servico.iniciar (ou --marketplace na linha de comando).
MARKETPLACES_ROBO = ("shopee", "tiktok", "mercado_livre")
# Estados que o robô atende. servico.iniciar define o ESTADO de cada lote (SP é o padrão da linha de comando).
ESTADOS_ROBO = ("SP", "RJ")
ESTADO = "SP"

# Definidos na linha de comando (--planilha, --margem, --desconto). Ficam None de propósito:
# o robô nunca assume valor padrão para margem/desconto.
CAMINHO_PLANILHA = None
MARGEM_DESEJADA = None
DESCONTO_PROMOCIONAL = None

# PENDENTE (pergunta 6): valor enviado em perc_st nos cenários SEM ST.
# O PDF diz 0, mas no motor o perc_st entra no custo em todos os cenários. Confirmar.
PERC_ST_SEM_ST = 0.0

# Só produtos com caixa de papelão (latas de tinta, frigideiras Wok) têm valor; o resto é 0.
CUSTO_CAIXA_PAPELAO = 0.0

# PENDENTE: o que sobe na coluna de preço da Shopee e do TikTok (a planilha deles só tem UM preço).
#   "cheio"       -> preco_cheio (o "de" do de/por)
#   "promocional" -> preco_promocional (o preço realmente cobrado do cliente)
# Mercado Livre: a planilha tem DUAS colunas (Preço e Preço em promoção). Com "cheio" o robô grava os dois (cheio em Preço,
# promocional em Preço em promoção); com "promocional" grava só o promocional na coluna de Preço, como nos outros.
PRECO_QUE_SOBE = "cheio"

# PENDENTE (pergunta 12): produto abaixo do PMA grava ou só avisa no relatório?
GRAVAR_ABAIXO_DO_PMA = False

# De onde vem o codigo_pma enviado à calculadora: "fabricante" ou "sku".
PMA_CODIGO_DE = "fabricante"

# Quanto a margem promocional devolvida pode se afastar da margem desejada antes de virar REVISAR.
TOLERANCIA_MARGEM = 0.01

# Página do Convênio ICMS 52/91 salva do navegador (usada pelo coletor do Confaz).
CONFAZ_HTML = RAIZ / "confaz.html"

# True: o Base Reduzida vem da consulta do NCM no confaz.html (coletor_confaz). A coluna confaz_status do arquivo de dados
# só vale para linhas sem NCM. False: usa só a coluna confaz_status do arquivo (modo de teste antigo).
USAR_COLETOR_CONFAZ = True

PASTA_PROGRESSO = RAIZ / "progresso"
PASTA_RELATORIOS = RAIZ / "relatorios"
