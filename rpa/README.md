# Robô de atualização de preços (rpa/)

Primeira etapa: **Shopee / SP**. O motor de cálculo (`backend/app/engine`) não é alterado:
o robô só entrega os dados certos e recebe os preços.

## O que já está pronto
- `cenario.py` matriz dos 6 cenários (SP) + regras de tipo, ST e Base Reduzida
- `validador.py` regras da seção 8 do PDF (recorte Shopee SP)
- `cliente_api.py` chama `/api/calcular`, `/api/planilha-ml/arquivo/listar-skus` e `/gravar`
- `relatorio.py` xlsx + csv (OK / REVISAR / ABAIXO DO PMA, com o motivo)
- `progresso.py` salva a cada SKU e retoma
- `fonte_csv.py` fonte de dados de TESTE (no lugar dos coletores Citel/Econet, que vêm depois)
- `coletor_confaz.py` coletor do Confaz (Convênio 52/91): lê o `confaz.html` salvo em `rpa/` e devolve BASE_REDUZIDA / CONDICIONAL / FORA_DA_LISTA / FALHOU por NCM. Teste rápido: `python -m rpa.coletor_confaz 84198999 84151011`
- `main.py` orquestrador

## Rodando (na raiz do projeto, em outro terminal, com o backend ligado)
```bat
pip install -r rpa\requirements.txt
python -m pytest rpa\tests
python -m rpa.main --planilha "C:\caminho\shopee_teste.xlsx" --csv rpa\dados_teste.csv --margem 0.15 --desconto 0.10
```
Sem `--gravar` é simulação. Use uma CÓPIA da planilha da Shopee nos primeiros testes.
Os SKUs de `dados_teste.csv` são fictícios: troque pelos SKUs da sua planilha de teste.

## Ainda provisório (config.py)
- `PERC_ST_SEM_ST`: valor de ST nos cenários sem ST
- `PRECO_QUE_SOBE`: cheio ou promocional na coluna de preço da Shopee
- `GRAVAR_ABAIXO_DO_PMA`: gravar ou só avisar
- `TOLERANCIA_MARGEM`: confere `margem_promocional` x margem desejada
