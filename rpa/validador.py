"""
Validador (seção 8 do PDF, recorte Shopee SP). Devolve a lista de motivos; lista vazia = pode seguir.
Regra geral: qualquer dúvida bloqueia o preço daquela linha. Nenhum zero por falta de leitura.

As checagens de ST (falha/ambíguo) e de Confaz (condicional/falha) ficam em cenario.definir_cenario.
"""
import re

from rpa import cenario, ml_frete
from rpa import modelos as m


def ncm_limpo(ncm) -> str | None:
    """Devolve o NCM só com os 8 dígitos (aceita pontos), ou None se não tiver exatamente 8."""
    if ncm is None:
        return None
    t = str(ncm).strip().replace(".", "").replace(" ", "")
    return t if re.fullmatch(r"\d{8}", t) else None


def validar(dados: m.DadosProduto, estado: str = "SP", marketplace: str | None = None) -> list[str]:
    """No RJ não existe ST: o MVA não é exigido (o resto das regras é igual ao SP).
    No Mercado Livre (`marketplace="mercado_livre"`) a comissão e o frete também são obrigatórios (ver _validar_ml)."""
    motivos: list[str] = []

    if not (dados.codigo_fabricante or "").strip():
        motivos.append("Código do fabricante ausente (não dá para conferir se o produto lido é o do SKU)")

    if dados.aliq_icms is None:
        motivos.append("Aliq ICMS ausente ou ilegível")
    elif cenario.tipo_produto(dados.aliq_icms) is None:
        motivos.append(f"Aliq ICMS {dados.aliq_icms:g}% fora de 4, 12, 16, 18, 20")

    if ncm_limpo(dados.ncm) is None:
        motivos.append("NCM ausente ou sem 8 dígitos")

    if dados.unitario is None or dados.unitario <= 0:
        motivos.append("Unitário ausente ou não maior que zero")

    if dados.perc_frete is None:
        motivos.append("Frete da empresa não encontrado")
    elif not (0 <= dados.perc_frete < 1):
        motivos.append(f"Frete {dados.perc_frete:g} fora de 0 a 1 (esperado em fração: 3% = 0.03)")

    if dados.perc_ipi is None:
        motivos.append("IPI não lido (0 é válido, vazio não)")
    elif not (0 <= dados.perc_ipi < 1):
        motivos.append(f"IPI {dados.perc_ipi:g} fora de 0 a 1 (esperado em fração: 5% = 0.05)")

    if estado != "RJ" and dados.st.status == m.COM_ST:
        if dados.st.mva is None:
            motivos.append("Econet indicou ST mas nenhum MVA foi lido")
        elif dados.st.mva <= 0:
            motivos.append(f"MVA {dados.st.mva:g} inválido")

    if marketplace == "mercado_livre":
        motivos.extend(_validar_ml(dados))

    return motivos


def _validar_ml(dados: m.DadosProduto) -> list[str]:
    """Regras só do Mercado Livre: comissão do produto e frete (R$ direto, ou peso + faixa da tabela BASE FRETE MELI)."""
    motivos: list[str] = []

    if dados.ml_comissao is None:
        motivos.append("Comissão do Mercado Livre ausente (varia por categoria: o robô não assume padrão)")
    elif not (0 < dados.ml_comissao < 1):
        motivos.append(f"Comissão do Mercado Livre {dados.ml_comissao:g} fora de 0 a 1 (esperado em fração: 12% = 0.12)")

    if dados.frete_ml is not None and dados.frete_ml < 0:
        motivos.append(f"Frete do Mercado Livre {dados.frete_ml:g} negativo")
    elif dados.frete_ml is not None and dados.frete_ml > 0:
        return motivos   # frete já conhecido em R$: dispensa peso e faixa (igual a digitar o frete na calculadora)

    if not (dados.ml_peso or "").strip():
        motivos.append("Frete do Mercado Livre ausente: informe frete_ml (R$) ou ml_peso + ml_faixa_valor")
    elif ml_frete.canonico_peso(dados.ml_peso) is None:
        motivos.append(f"Peso do frete do ML '{dados.ml_peso}' não existe na tabela BASE FRETE MELI")
    if not (dados.ml_faixa_valor or "").strip():
        if (dados.ml_peso or "").strip():
            motivos.append("Faixa de valor do frete do ML ausente (informe ml_faixa_valor ou frete_ml)")
    elif ml_frete.canonico_faixa(dados.ml_faixa_valor) is None:
        motivos.append(f"Faixa de valor do frete do ML '{dados.ml_faixa_valor}' não existe na tabela BASE FRETE MELI")
    return motivos
