"""
Fretes do RJ que NÃO são do Mercado Livre (o ML do RJ reaproveita ml/frete.py,
tabela idêntica à de SP). Tabelas literais das abas BASE FRETE MAGALU e
BASE FRETE AMZ DBA de CALCULO_MKTPLACE_RJ.xlsx.
"""

# ---- Magalu: D13 = IF(D5<=79, 0, VLOOKUP(peso, tabela, coluna do nível de serviço)) ----
LIMITE_FRETE_MAGALU = 79.0  # preço <= 79 -> frete 0 (fixo na fórmula da planilha)
NIVEIS_MAGALU = ["<92%", "92 e 97%", ">97%", "FULL 75%"]
TABELA_MAGALU = [
    ("Até 500gr", [35.9, 26.93, 17.95, 8.98]),
    ("De 500gr a 1kg", [40.9, 30.68, 20.45, 10.23]),
    ("De 1kg a 2kg", [42.9, 32.18, 21.45, 10.73]),
    ("De 2kg a 5kg", [50.9, 38.18, 25.45, 12.73]),
    ("De 5kg a 9kg", [77.9, 58.43, 38.95, 19.48]),
    ("De 9kg a 13kg", [98.9, 74.18, 49.45, 24.73]),
    ("De 13kg a 17kg", [111.9, 83.93, 55.95, 27.98]),
    ("De 17kg a 23kg", [134.9, 101.18, 67.45, 33.73]),
    ("De 23kg a 30kg", [148.9, 111.68, 74.45, 37.23]),
    ("De 30kg a 40kg", [159.9, 119.93, 79.95, 39.98]),
    ("De 40kg a 50kg", [189.9, 142.43, 94.95, 47.48]),
    ("De 50kg a 60kg", [197.9, 148.43, 98.95, 49.48]),
    ("De 60kg a 70kg", [206.9, 155.18, 103.45, 51.73]),
    ("De 70kg a 80kg", [215.9, 161.93, 107.95, 53.98]),
    ("De 80kg a 90kg", [225.9, 169.43, 112.95, 56.48]),
    ("De 90kg a 100kg", [235.9, 176.93, 117.95, 58.98]),
    ("De 100kg a 110kg", [245.9, 184.43, 122.95, 61.48]),
    ("De 110kg a 120kg", [256.9, 192.68, 128.45, 64.23]),
    ("De 120kg a 130kg", [267.9, 200.93, 133.95, 66.98]),
    ("De 130kg a 140kg", [279.9, 209.93, 139.95, 69.98]),
    ("De 140kg a 150kg", [291.9, 218.93, 145.95, 72.98]),
    ("De 150kg a 160kg", [304.9, 228.68, 152.45, 76.23]),
    ("De 160kg a 170kg", [317.9, 238.43, 158.95, 79.48]),
    ("De 170kg a 180kg", [331.9, 248.93, 165.95, 82.98]),
    ("De 180kg a 190kg", [345.9, 259.43, 172.95, 86.48]),
    ("De 190kg a 200kg", [360.9, 270.68, 180.45, 90.23]),
    ("Acima de 200kg", [375.9, 281.93, 187.95, 93.98]),
]
PESOS_MAGALU = [p for p, _ in TABELA_MAGALU]
_MAGALU = {p: dict(zip(NIVEIS_MAGALU, v)) for p, v in TABELA_MAGALU}


def tabela_magalu(peso: str, nivel: str) -> float:
    """Valor da tabela (nivel x peso), sem a regra de preço <= R$79. Usado pra preencher o campo na tela."""
    if peso not in _MAGALU:
        raise ValueError(f"Peso inválido pro frete da Magalu: {peso!r}")
    if nivel not in _MAGALU[peso]:
        raise ValueError(f"Nível de serviço inválido pro frete da Magalu: {nivel!r}")
    return _MAGALU[peso][nivel]


def frete_magalu(preco: float, peso: str, nivel: str) -> float:
    if preco <= LIMITE_FRETE_MAGALU:
        return 0.0
    return tabela_magalu(peso, nivel)


# ---- Amazon DBA: VLOOKUP(peso, tabela, coluna da faixa de valor); célula vazia -> 0 ----
# Aba BASE FRETE AMZ DBA, colunas B:I (as 8 faixas do dropdown C3). As 3 faixas abaixo de R$79 só têm
# valor na linha "0 a 250 g" (R$4,50 / 6,50 / 6,75); nas outras linhas a célula é vazia e o VLOOKUP
# devolve 0 — mantido igual aqui. A linha 14 ("Kg adicional") NÃO é opção do dropdown de peso
# (C2 = A2:A13): é só a legenda do valor por kg extra, que agora vem de KG_ADICIONAL_AMZ.
SEM_FRETE_AMZ = "Abaixo de R$ 79 (sem frete)"  # legado (antes só havia faixas a partir de R$79); a tela não lista mais
FAIXAS_AMZ = [
    "R$ 0 a 29,99", "R$ 30 a 49,99", "R$ 50 a 78,99",
    "R$ 79 a 99,99", "R$ 100 a 119,99", "R$ 120 a 149,99", "R$ 150 a 199,99", "Acima R$200",
]
TABELA_AMZ = [
    ("0 a 250 g", [4.5, 6.5, 6.75, 11.95, 13.95, 15.95, 17.95, 20.45]),
    ("250 a 500 g", [0, 0, 0, 12.85, 15, 17.15, 19.3, 20.95]),
    ("500 g a 1 kg", [0, 0, 0, 13.45, 15.7, 17.95, 20.2, 21.95]),
    ("1 a 2 kg", [0, 0, 0, 14, 16.35, 18.75, 21.1, 23.45]),
    ("2 a 3 kg", [0, 0, 0, 14.95, 17.45, 19.95, 22.4, 24.45]),
    ("3 a 4 kg", [0, 0, 0, 16.15, 18.85, 21.55, 24.2, 25.95]),
    ("4 a 5 kg", [0, 0, 0, 17, 19.9, 22.75, 25.6, 27.95]),
    ("5 a 6 kg", [0, 0, 0, 25, 30, 34, 38, 36.95]),
    ("6 a 7 kg", [0, 0, 0, 26, 31, 35, 39, 39.45]),
    ("7 a 8 kg", [0, 0, 0, 27, 32, 36, 40, 40.45]),
    ("8 a 9 kg", [0, 0, 0, 28, 33, 37, 41, 46.95]),
    ("9 a 10 kg", [0, 0, 0, 39.5, 46, 52.75, 59, 65.95]),
]
PESOS_AMZ = [p for p, _ in TABELA_AMZ]
_AMZ = {p: dict(zip(FAIXAS_AMZ, v)) for p, v in TABELA_AMZ}


def frete_amazon(peso: str, faixa: str) -> float:
    if faixa == SEM_FRETE_AMZ:
        return 0.0
    if peso not in _AMZ:
        raise ValueError(f"Peso inválido pro frete da Amazon DBA: {peso!r}")
    if faixa not in _AMZ[peso]:
        raise ValueError(f"Faixa de valor inválida pro frete da Amazon DBA: {faixa!r}")
    return _AMZ[peso][faixa]


# ---- Amazon DBA: KG ADICIONAL (aba AMAZON DBA G2:H5; tabela K1:L6 da BASE FRETE AMZ DBA) ----
# H2 = faixa de preço (dropdown K2:K6) | H3 = VLOOKUP(H2, K1:L6, 2, 0) = valor por kg extra
# H4 = quantidade de kg                 | H5 = IF(H3="", 0, H3*H4)
# D15 (frete que sai do lucro) = IF(H5=0, C15, H5+C15).
# ATENÇÃO: só D15 recebe o adicional. Os créditos de imposto (I9, I12, I14, I15...) usam C15 (frete base).
KG_ADICIONAL_AMZ = {
    "R$ 79 a 99,99": 3.05,
    "R$ 100 a 119,99": 3.05,
    "R$ 120 a 149,99": 3.05,
    "R$ 150 a 199,99": 3.5,
    "Acima R$200": 4.0,
}


def frete_adicional_amazon(faixa: str | None, qtd_kg: float) -> float:
    """H5 da planilha: valor/kg da faixa x kg. Sem faixa ou sem kg -> 0 (igual ao IF/IFERROR da planilha)."""
    if not faixa or not qtd_kg or qtd_kg <= 0:
        return 0.0
    if faixa not in KG_ADICIONAL_AMZ:
        raise ValueError(f"Faixa de preço inválida pro kg adicional da Amazon DBA: {faixa!r}")
    return KG_ADICIONAL_AMZ[faixa] * qtd_kg
