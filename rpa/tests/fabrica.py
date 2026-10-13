from rpa import modelos as m


def dados(**kw) -> m.DadosProduto:
    """Produto válido de referência (nacional, sem ST, fora do Confaz). Sobrescreva o que o teste precisar."""
    base = dict(
        sku="X1",
        codigo_fabricante="ABC123",
        unitario=100.0,
        aliq_icms=12.0,
        ncm="85176277",
        perc_frete=0.03,
        perc_ipi=0.05,
        st=m.ResultadoST(m.SEM_ST),
        confaz=m.ResultadoConfaz(m.FORA_DA_LISTA),
    )
    base.update(kw)
    return m.DadosProduto(**base)
