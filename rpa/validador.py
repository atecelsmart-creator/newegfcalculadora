"""
Validador (seção 8 do PDF, recorte Shopee SP). Devolve a lista de motivos; lista vazia = pode seguir.
Regra geral: qualquer dúvida bloqueia o preço daquela linha. Nenhum zero por falta de leitura.

As checagens de ST (falha/ambíguo) e de Confaz (condicional/falha) ficam em cenario.definir_cenario.
"""
import re

from rpa import cenario
from rpa import modelos as m


def ncm_limpo(ncm) -> str | None:
    """Devolve o NCM só com os 8 dígitos (aceita pontos), ou None se não tiver exatamente 8."""
    if ncm is None:
        return None
    t = str(ncm).strip().replace(".", "").replace(" ", "")
    return t if re.fullmatch(r"\d{8}", t) else None


def validar(dados: m.DadosProduto) -> list[str]:
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

    if dados.st.status == m.COM_ST:
        if dados.st.mva is None:
            motivos.append("Econet indicou ST mas nenhum MVA foi lido")
        elif dados.st.mva <= 0:
            motivos.append(f"MVA {dados.st.mva:g} inválido")

    return motivos
