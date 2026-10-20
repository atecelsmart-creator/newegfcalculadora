"""
Custos base (D9:D21) — compartilhados por TODOS os 6 cenários da planilha.

Na planilha, D11, D13, D14, D15, D16, D17, D19, D20 têm a MESMA fórmula
não importa qual dos 6 blocos (G/L/Q, sem ST ou com ST) você está olhando —
só o bloco de impostos (aliquotas H/M/R) muda por cenário. Este módulo
calcula essa parte comum uma única vez.

D12 (FRETE percentual sobre custo+IPI) fica fora do escopo por decisão
registrada — tratado como 0 aqui, igual em nacional_sem_st.py.
"""
from dataclasses import dataclass

from app.engine.shopee import constants


@dataclass
class CustosBase:
    ipi: float                   # D11
    valor_st: float               # D13
    custo_produto_total: float    # D14
    mentoria: float                 # D15
    custo_logistico: float          # D16
    perda: float                     # D17
    custo_shopee_perc: float          # C19
    custo_shopee: float                # D19
    taxa_shp_premio: float               # D20
    frete_compra: float = 0.0            # D12 (FRETE % sobre custo+IPI)


def calcular_custos_base(
    preco_venda: float,
    custo_sem_ipi: float,
    perc_ipi: float,
    perc_st: float = 0.0,
    perc_frete: float = 0.0,
) -> CustosBase:
    """
    Reproduz D11, D13, D14, D15, D16, D17, D19, D20 da planilha.
    perc_st = 0 para os 3 cenários "sem ST" (decisão registrada: ST travado
    em 0 nesses casos). Para os 3 cenários "com ST", perc_st é a entrada do
    usuário (equivalente a C13 na planilha).
    """
    ipi = perc_ipi * custo_sem_ipi                              # D11
    frete_compra = perc_frete * (custo_sem_ipi + ipi)           # D12 = C12*(D10+D11) (FRETE em %)
    valor_st = perc_st * custo_sem_ipi                          # D13
    custo_produto_total = frete_compra + custo_sem_ipi + ipi + valor_st        # D14 = D12+D11+D10+D13

    mentoria = preco_venda * constants.PERC_MENTORIA            # D15
    custo_logistico = preco_venda * constants.PERC_CUSTO_LOGISTICO  # D16
    perda = constants.PERC_PERDA * custo_produto_total          # D17

    custo_shopee_perc = constants.custo_shopee_pct(preco_venda)  # C19
    custo_shopee = custo_shopee_perc * preco_venda               # D19
    taxa_shp_premio = constants.taxa_shp_premio(preco_venda)     # D20

    return CustosBase(
        ipi=ipi,
        valor_st=valor_st,
        custo_produto_total=custo_produto_total,
        mentoria=mentoria,
        custo_logistico=custo_logistico,
        perda=perda,
        custo_shopee_perc=custo_shopee_perc,
        custo_shopee=custo_shopee,
        taxa_shp_premio=taxa_shp_premio,
        frete_compra=frete_compra,
    )
