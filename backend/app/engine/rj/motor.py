"""
Motor de cálculo do RJ (Shopee, Mercado Livre e TikTok Shop).

Reproduz literalmente as abas SHOPEE RJ, MELI RJ e TIK TOP SHOP de
CALCULO_MKTPLACE_RJ.xlsx. As 3 abas têm o MESMO bloco de impostos e só
mudam nas taxas do marketplace, então há uma função única. Mapeamento
(células da aba SHOPEE RJ; ML e TikTok têm o mesmo desenho):
  D3 custo, D4 IPI, D5 frete de compra (C5*(D3+D4)), D6 custo produto total
  D7 mentoria, D8 logístico, D9 custo fixo, D10 frete R$ (só ML, tabela),
  D11 custo do marketplace, D12 taxa + prêmio,
  D13 caixa papelão (Shopee/ML) ou comissão afiliado (TikTok)
  I3..I12 impostos, I14 lucro real.

Regras do RJ que diferem de SP: sem ST (só 3 cenários), sem perda, crédito
presumido de 6% do preço, ICMS saída nacional 22%, ICMS frete de compra 12%.
"""
from dataclasses import dataclass

from app.engine.rj import config, frete

# Cenário da API (enum Cenario, só os "sem ST") -> tipo de produto do RJ.
TIPO_POR_CENARIO = {
    "nacional_sem_st": "nacional",
    "base_reduzida_sem_st": "base_reduzida",
    "importado_sem_st": "importado",
}

_COMUNS = {
    "credito_presumido": 0.06,        # H3/M3/R3 (R3 = H3)
    "icms_frete_ml_credito": 0.12,    # H4/M4/R4
    "pis_cofins_credito": 0.0925,     # H7/M7/R7
    "pis_cofins_debito": 0.0925,      # H8/M8/R8
    "ir_cs_credito": 0.34,            # H9/M9/R9
    "ir_cs_debito": 0.34,             # H10/M10/R10
}
ALIQUOTAS = {
    "nacional": {**_COMUNS, "icms_entrada_credito": 0.12, "icms_saida": 0.22},         # H5, H6
    "base_reduzida": {**_COMUNS, "icms_entrada_credito": 0.088, "icms_saida": 0.088},  # M5, M6
    "importado": {**_COMUNS, "icms_entrada_credito": 0.04, "icms_saida": 0.088},       # R5, R6
}
ICMS_FRETE_COMPRA = 0.12  # "D5*0.12" fixo dentro de I5/N5/S5

# A planilha NÃO subtrai custo logístico (D8) nem custo fixo (D9) no LUCRO REAL
# (I14 = D2-D6-D7-D10-D11-D12-I12-D13); eles só entram na base do IR/CSLL crédito.
# Mantido idêntico à planilha. Se a empresa confirmar que deveriam ser
# descontados do lucro, basta trocar para True.
DESCONTA_LOGISTICO_E_FIXO_NO_LUCRO = False


@dataclass
class EntradasRJ:
    marketplace: str            # "shopee" | "mercado_livre" | "tiktok"
    tipo: str                   # "nacional" | "base_reduzida" | "importado"
    custo_sem_ipi: float
    perc_ipi: float = 0.0
    perc_frete: float = 0.0     # C5: % sobre custo + IPI
    custo_frete: float = 0.0    # D10/D13: R$ — ML e Amazon DBA (tabela peso x faixa, escolhida na tela)
    custo_caixa_papelao: float = 0.0  # Shopee/ML/Magalu/Amazon (D13 ou D16 da planilha); TikTok não tem célula de caixa
    # Magalu: o frete depende do PREÇO (0 se <= R$79), então é calculado dentro do motor.
    magalu_peso: str | None = None
    magalu_nivel: str | None = None
    # Só Mercado Livre: comissão (C14 da aba MELI RJ) informada na tela; None = valor salvo nos ajustáveis.
    comissao_pct: float | None = None
    # Só Base Reduzida (igual ao SP): "nacional" -> ICMS entrada 8,80%; "importado" -> 4,00%.
    origem: str = "nacional"
    # Só Nacional e Importado (campo visível na tela do RJ): em fração (0.12 = 12%).
    #   nacional  -> ICMS ENTRADA CRÉDITO (padrão da planilha: 12%)
    #   importado -> ICMS SAÍDA           (padrão da planilha: 8,80%)
    # None = usa o padrão de ALIQUOTAS. Ignorado em Base Reduzida (que tem o toggle de origem).
    icms_pct: float | None = None
    # Só Amazon DBA — KG ADICIONAL (H5 da aba AMAZON DBA = valor/kg da faixa x kg), em R$.
    # Soma ao frete que SAI DO LUCRO (D15 = C15 + H5), mas NÃO entra nos créditos de imposto,
    # que continuam calculados sobre o frete base (C15) — igual à planilha.
    frete_adicional: float = 0.0


@dataclass
class ResultadoRJ:
    preco_venda: float
    custo_produto_total: float
    mentoria: float
    custo_logistico: float
    custo_fixo: float
    custo_marketplace_perc: float
    custo_marketplace: float
    taxa_premio: float
    outros_custos: float        # caixa (Shopee/ML) ou afiliado (TikTok)
    icms_saida: float
    pis_cofins_debito: float
    ir_cs: float
    custo_total_impostos: float
    lucro_real: float
    margem_real: float
    frete_aplicado: float = 0.0   # frete base (C15/D10/D13), o mesmo usado nos créditos de imposto
    frete_adicional: float = 0.0  # kg adicional da Amazon DBA (H5); já descontado no lucro_real

def _taxas_marketplace(mk: str, preco: float, cfg: dict, ent: EntradasRJ):
    """-> (perc do marketplace, taxa+prêmio em R$, outros custos em R$)."""
    if mk == "shopee":
        perc = cfg["comissao_pct_ate_limiar"] if preco <= cfg["comissao_limiar"] else cfg["comissao_pct_acima_limiar"]
        faixas = cfg["taxa_fixa_faixas"]
        base = faixas[-1]["valor"]
        for f in faixas:
            if f["ate"] is None or preco <= f["ate"]:
                base = f["valor"]
                break
        return perc, base + cfg["taxa_premio_fixo"], ent.custo_caixa_papelao
    if mk == "tiktok":
        abaixo = preco < cfg["comissao_limiar"]
        perc = cfg["comissao_pct_abaixo_limiar"] if abaixo else cfg["comissao_pct_acima_limiar"]
        base = cfg["taxa_fixa_abaixo_limiar"] if abaixo else cfg["taxa_fixa_acima_limiar"]
        return perc, base + cfg["taxa_premio_fixo"], preco * cfg["comissao_afiliados_pct"] + ent.custo_caixa_papelao  # caixa: extra nosso (a planilha do TikTok RJ não tem)
    if mk == "mercado_livre":
        return (ent.comissao_pct if ent.comissao_pct is not None else cfg["comissao_pct"]), cfg["taxa_premio_fixo"], ent.custo_caixa_papelao
    if mk == "magalu":                                   # C14 (informada na tela; senão, o valor salvo), D15 (=5+1.35); D16 (caixa) entra no lucro como nas outras abas
        return (ent.comissao_pct if ent.comissao_pct is not None else cfg["comissao_pct"]), cfg["taxa_fixa"] + cfg["taxa_premio_fixo"], ent.custo_caixa_papelao
    if mk == "amazon_dba":                               # C14 (=12%+1.5%), D15
        if preco < cfg["taxa_limiar_1"]:
            base = cfg["taxa_fixa_1"]
        elif preco < cfg["taxa_limiar_2"]:
            base = cfg["taxa_fixa_2"]
        else:
            base = cfg["taxa_fixa_3"]
        return (ent.comissao_pct if ent.comissao_pct is not None else cfg["comissao_pct"]), base + cfg["taxa_premio_fixo"], ent.custo_caixa_papelao
    raise ValueError(f"Marketplace inválido para o RJ: {mk!r}")


def calcular(preco_venda: float, ent: EntradasRJ) -> ResultadoRJ:
    a = ALIQUOTAS[ent.tipo]
    if ent.tipo == "base_reduzida" and ent.origem == "importado":
        a = {**a, "icms_entrada_credito": 0.04}  # mesma regra do SP: só o ICMS entrada muda
    if ent.icms_pct is not None:
        if ent.tipo == "nacional":
            a = {**a, "icms_entrada_credito": ent.icms_pct}   # H5
        elif ent.tipo == "importado":
            a = {**a, "icms_saida": ent.icms_pct}             # R6
    cfg = config.obter(ent.marketplace)
    p = preco_venda

    ipi = ent.perc_ipi * ent.custo_sem_ipi                              # D4
    frete_compra = ent.perc_frete * (ent.custo_sem_ipi + ipi)           # D5
    custo_produto = frete_compra + ipi + ent.custo_sem_ipi              # D6

    mentoria = p * cfg["perc_mentoria"]                                 # D7
    logistico = p * cfg["perc_custo_logistico"]                         # D8
    fixo = p * cfg["perc_custo_fixo"]                                   # D9
    perc_mkt, taxa_premio, outros = _taxas_marketplace(ent.marketplace, p, cfg, ent)
    custo_mkt = perc_mkt * p                                            # D11
    frete_r = ent.custo_frete                                           # D10/D13
    if ent.marketplace == "magalu" and ent.custo_frete <= 0:   # D13 digitado direto (> 0) vale no lugar da fórmula
        frete_r = frete.frete_magalu(p, ent.magalu_peso, ent.magalu_nivel)
    adicional = ent.frete_adicional if ent.marketplace == "amazon_dba" else 0.0   # H5 (só Amazon DBA)

    cred_pres = a["credito_presumido"] * p                              # I3
    icms_frete_cred = frete_r * a["icms_frete_ml_credito"]              # I4
    icms_entrada = ent.custo_sem_ipi * a["icms_entrada_credito"] + frete_compra * ICMS_FRETE_COMPRA  # I5
    icms_saida = p * a["icms_saida"]                                    # I6
    pis_cred = (custo_produto - icms_entrada + frete_r - icms_frete_cred) * a["pis_cofins_credito"]  # I7
    pis_deb = (p - icms_saida) * a["pis_cofins_debito"]                 # I8
    ir_cred = (custo_produto + mentoria + logistico + fixo + frete_r
               + custo_mkt + taxa_premio + icms_saida + pis_deb) * a["ir_cs_credito"]   # I9
    ir_deb = (p + cred_pres + icms_frete_cred + icms_entrada + pis_cred) * a["ir_cs_debito"]  # I10
    ir_cs = max(0.0, ir_deb - ir_cred)                                  # I11
    impostos = (icms_saida + pis_deb + ir_cs) - (icms_frete_cred + icms_entrada + pis_cred + cred_pres)  # I12

    # I14 (D15 da Amazon = frete base + kg adicional; impostos acima usam só o frete base)
    lucro = p - custo_produto - mentoria - (frete_r + adicional) - custo_mkt - taxa_premio - impostos - outros
    if DESCONTA_LOGISTICO_E_FIXO_NO_LUCRO:
        lucro -= logistico + fixo

    return ResultadoRJ(
        preco_venda=p,
        custo_produto_total=custo_produto,
        mentoria=mentoria,
        custo_logistico=logistico,
        custo_fixo=fixo,
        custo_marketplace_perc=perc_mkt,
        custo_marketplace=custo_mkt,
        taxa_premio=taxa_premio,
        outros_custos=outros,
        icms_saida=icms_saida,
        pis_cofins_debito=pis_deb,
        ir_cs=ir_cs,
        custo_total_impostos=impostos,
        lucro_real=lucro,
        margem_real=lucro / p if p else 0.0,                            # J14
        frete_aplicado=frete_r,
        frete_adicional=adicional,
    )
