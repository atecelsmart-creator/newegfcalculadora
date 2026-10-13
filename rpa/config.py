"""
Configuração do robô de preços (primeira etapa: Shopee / SP).

Nada aqui é senha. Os valores marcados PENDENTE dependem de confirmação
(seção 12 do PDF de arquitetura) e estão com um padrão provisório.
"""
from pathlib import Path

RAIZ = Path(__file__).resolve().parent

API_URL = "http://127.0.0.1:8000"
MARKETPLACE = "shopee"
# Marketplaces (SP) que o robô atende. O lote escolhe um deles em servico.iniciar (ou --marketplace na linha de comando).
MARKETPLACES_ROBO = ("shopee", "tiktok")
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

# PENDENTE: o que sobe na coluna de preço da Shopee (a planilha dela só tem UM preço).
#   "cheio"       -> preco_cheio (o "de" do de/por)
#   "promocional" -> preco_promocional (o preço realmente cobrado do cliente)
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
