"""
Frete do Mercado Livre (D20 da aba "ML OPERACAO SP").

Tabela extraída literalmente da aba "BASE FRETE MELI" de CALCULO_MKTPLACE_SP.xlsx
(A1:I31). Na planilha, D20 = VLOOKUP(peso escolhido em C8, tabela, coluna da
faixa de valor escolhida em C9) — aqui vira lookup por (peso, faixa).

Atenção: o VLOOKUP da planilha usa o intervalo A1:I30, que deixa de fora a
linha 31 ("Mais de 150 kg") — nessa linha a planilha devolveria 0 (IFERROR).
Aqui a linha está incluída de propósito (frete 0 seria erro de cálculo).

O "**" no rótulo da 1ª faixa é do próprio arquivo (sem explicação nele);
mantido no rótulo por fidelidade.
"""
FAIXAS_VALOR = [
    '0 a R$ 18,99**',
    '19 a R$ 48,99',
    '49 a R$ 78,99',
    '79 a R$ 99,99',
    '100 a R$ 119,99',
    '120 a R$ 149,99',
    '150 a R$ 199,99',
    'A partir de 200',
]
# peso -> frete por faixa de valor (mesma ordem de FAIXAS_VALOR)
TABELA_FRETE = [
    ('Até 0,3 kg', [5.65, 6.85, 8.15, 12.95, 14.95, 16.95, 19.05, 21.65]),
    ('De 0,3 a 0,5 kg', [5.95, 6.95, 8.25, 13.85, 16.15, 18.15, 20.45, 23.25]),
    ('De 0,5 a 1 kg', [6.05, 7.15, 8.45, 14.45, 16.85, 19.05, 21.35, 24.45]),
    ('De 1 a 1,5 kg', [6.15, 7.35, 8.65, 14.75, 17.15, 19.45, 21.75, 25.45]),
    ('De 1,5 a 2 kg', [6.25, 7.45, 8.75, 15.05, 17.65, 19.85, 22.25, 25.55]),
    ('De 2 a 3 kg', [6.35, 8.65, 9.15, 16.45, 19.15, 21.65, 24.35, 27.05]),
    ('De 3 a 4 kg', [6.45, 8.75, 9.75, 17.85, 20.75, 23.35, 26.35, 29.25]),
    ('De 4 a 5 kg', [6.55, 8.85, 10.25, 19.75, 22.85, 26.05, 29.25, 32.45]),
    ('De 5 a 6 kg', [6.65, 8.95, 10.35, 25.95, 29.15, 33.35, 36.45, 40.85]),
    ('De 6 a 7 kg', [6.75, 9.05, 10.45, 27.55, 31.65, 36.75, 40.85, 45.25]),
    ('De 7 a 8 kg', [6.85, 9.25, 10.55, 29.45, 34.35, 39.25, 44.15, 49.35]),
    ('De 8 a 9 kg', [6.95, 9.35, 10.65, 30.25, 35.25, 40.35, 45.35, 50.75]),
    ('De 9 a 10 kg', [7.05, 9.45, 10.85, 38.25, 45.05, 51.95, 58.75, 65.85]),
    ('De 10 a 11 kg', [7.05, 9.65, 11.05, 41.65, 48.55, 55.45, 62.35, 69.35]),
    ('De 11 a 13 kg', [7.15, 10.05, 11.45, 42.55, 49.75, 56.85, 63.85, 70.95]),
    ('De 13 a 15 kg', [7.25, 10.25, 11.65, 45.55, 52.95, 60.55, 68.15, 75.65]),
    ('De 15 a 17 kg', [7.35, 10.45, 11.85, 48.95, 56.55, 64.05, 71.35, 79.35]),
    ('De 17 a 20 kg', [7.45, 10.65, 12.05, 55.15, 64.35, 73.55, 82.75, 91.95]),
    ('De 20 a 25 kg', [7.65, 11.05, 12.25, 64.55, 75.75, 85.45, 96.25, 106.85]),
    ('De 25 a 30 kg', [7.75, 11.25, 12.45, 66.45, 76.05, 86.25, 97.15, 107.85]),
    ('De 30 a 40 kg', [7.85, 11.45, 12.65, 68.35, 79.65, 89.75, 100.05, 107.95]),
    ('De 40 a 50 kg', [7.95, 11.65, 12.85, 70.95, 81.85, 92.85, 103.45, 111.65]),
    ('De 50 a 60 kg', [8.05, 11.85, 13.05, 75.55, 87.25, 99.05, 110.25, 119.05]),
    ('De 60 a 70 kg', [8.15, 12.05, 13.25, 80.95, 93.75, 105.95, 118.05, 127.45]),
    ('De 70 a 80 kg', [8.25, 12.25, 13.45, 84.65, 97.95, 110.75, 123.35, 133.15]),
    ('De 80 a 90 kg', [8.35, 12.45, 13.65, 94.05, 108.35, 122.95, 136.95, 147.85]),
    ('De 90 a 100 kg', [8.45, 12.65, 13.85, 107.45, 124.85, 140.45, 156.45, 168.85]),
    ('De 100 a 125 kg', [8.55, 12.85, 14.05, 120.15, 138.95, 156.95, 174.85, 188.85]),
    ('De 125 a 150 kg', [8.65, 12.85, 14.25, 127.45, 147.05, 166.55, 185.55, 200.35]),
    ('Mais de 150 kg', [8.75, 12.85, 14.45, 167.05, 193.35, 218.45, 243.45, 262.85]),
]

PESOS = [p for p, _ in TABELA_FRETE]
_LOOKUP = {p: dict(zip(FAIXAS_VALOR, v)) for p, v in TABELA_FRETE}

# Valor especial de `ml_faixa_valor`: a faixa é escolhida pelo PREÇO DE VENDA
# que o solver encontra (em vez de fixada na mão como o dropdown C9 da
# planilha). É o padrão do sistema — evita frete errado por faixa esquecida.
FAIXA_AUTO = "auto"

# Limite inferior (R$, inclusive) de cada faixa de FAIXAS_VALOR, na mesma
# ordem. A planilha rotula as faixas como "19 a R$ 48,99", "49 a R$ 78,99"...
# (centavos até .99), então um preço >= 49,00 já cai na faixa seguinte.
LIMITES_INFERIORES = [0.0, 19.0, 49.0, 79.0, 100.0, 120.0, 150.0, 200.0]


def obter_frete(peso: str, faixa_valor: str) -> float:
    """Frete em R$ pra (peso, faixa de valor). ValueError se algum não existir."""
    if peso not in _LOOKUP:
        raise ValueError(f"Peso inválido pro frete do Mercado Livre: {peso!r}")
    if faixa_valor not in _LOOKUP[peso]:
        raise ValueError(f"Faixa de valor inválida pro frete do Mercado Livre: {faixa_valor!r}")
    return _LOOKUP[peso][faixa_valor]


def indice_faixa_por_preco(preco: float) -> int:
    """Índice (0..7) da faixa de FAIXAS_VALOR em que o preço de venda cai."""
    idx = 0
    for i, limite in enumerate(LIMITES_INFERIORES):
        if preco >= limite:
            idx = i
    return idx


def faixa_por_preco(preco: float) -> str:
    """Rótulo da faixa de valor (igual ao de FAIXAS_VALOR) pro preço de venda."""
    return FAIXAS_VALOR[indice_faixa_por_preco(preco)]


def obter_frete_por_preco(peso: str, preco: float) -> float:
    """Frete em R$ pro peso, com a faixa de valor deduzida do preço de venda."""
    return obter_frete(peso, faixa_por_preco(preco))
