"""
Detalhes de cada linha do robô: tudo o que foi aplicado no cálculo daquele SKU (custos, impostos do cenário, taxas da Shopee)
e a conferência de cada taxa. A tela mostra isso num popup ao clicar na linha.

Só LÊ os mesmos valores que o cálculo usa (rpa.config + constantes do motor da Shopee). Não altera nenhuma regra de cálculo.
Qualquer falha aqui vira uma lista vazia: o preço da linha nunca depende deste módulo.

Cada item: {"g": grupo, "r": rótulo, "v": valor já formatado, "ok": True (confere) | False (atenção) | None (informativo), "n": nota}
"""
from rpa import config, ml_frete


def _frete_ml(add, grupo, dados, res) -> None:
    """Mercado Livre: frete aplicado (D20) e, se veio da tabela, conferência da faixa de valor com o preço promocional."""
    manual = dados.frete_ml is not None and dados.frete_ml > 0
    add(grupo, "Frete do ML", _r(res.get("ml_frete_aplicado")), None,
        "Informado em R$ no arquivo de dados" if manual else "Tabela BASE FRETE MELI (peso x faixa de valor)")
    if manual:
        return
    aplicada = res.get("ml_faixa_valor_aplicada")
    add(grupo, "Peso (frete ML)", dados.ml_peso or "—")
    try:
        certa = ml_frete.faixa_do_preco(res.get("preco_promocional"))
    except Exception:   # a conferência é só informativa
        certa = None
    if certa is None:
        add(grupo, "Faixa de valor (frete ML)", aplicada or "—")
    else:
        ok = certa == aplicada
        add(grupo, "Faixa de valor (frete ML)", aplicada or "—", ok,
            "Confere com o preço promocional" if ok else f"O preço promocional cai em {certa}")


def _p(x) -> str:          # fração -> "18,00%"
    return "—" if x is None else f"{x * 100:.2f}".replace(".", ",") + "%"


def _pn(x) -> str:         # número já em % (12 -> "12,00%")
    return "—" if x is None else f"{x:.2f}".replace(".", ",") + "%"


def _r(x) -> str:
    if x is None:
        return "—"
    return "R$ " + f"{x:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


# Nomes iguais aos do seletor "Cenário" da calculadora
NOMES_CENARIO = {
    "nacional_sem_st": "Produto Nacional — sem ST",
    "nacional_com_st": "Produto Nacional — com ST",
    "base_reduzida_sem_st": "Produto com Base Reduzida — sem ST",
    "base_reduzida_com_st": "Produto com Base Reduzida — com ST",
    "importado_sem_st": "Produto Importado — sem ST",
    "importado_com_st": "Produto Importado — com ST",
}


def _nome_cenario(c: str) -> str:
    return NOMES_CENARIO.get(c or "", (c or "").replace("_", " "))


# No RJ não existe ST: o nome do cenário não leva "sem ST" (mesmos nomes do seletor Cenário da Calculadora RJ)
NOMES_CENARIO_RJ = {
    "nacional_sem_st": "Produto Nacional",
    "base_reduzida_sem_st": "Produto com Base Reduzida",
    "importado_sem_st": "Produto Importado",
}


def _nome_cenario_rj(c: str) -> str:
    return NOMES_CENARIO_RJ.get(c or "", _nome_cenario(c))


def montar(dados, decisao, res: dict, margem: float, desconto: float) -> dict:
    try:
        return {"itens": _itens(dados, decisao, res, margem, desconto)}
    except Exception as e:   # nunca derruba o cálculo
        return {"itens": [], "erro": f"{type(e).__name__}: {e}"}


def _itens(dados, decisao, res, margem, desconto) -> list:
    if config.ESTADO == "RJ":
        return _itens_rj(dados, decisao, res, margem, desconto)
    from app.engine.shopee import constants as C

    ml = config.MARKETPLACE == "mercado_livre"
    it = []

    def add(g, r, v, ok=None, n=""):
        it.append({"g": g, "r": r, "v": v, "ok": ok, "n": n})

    # ---- Produto (dados de entrada)
    add("Produto", "Custo unitário (sem IPI)", _r(dados.unitario))
    add("Produto", "NCM", dados.ncm or "—")
    add("Produto", "Aliq. ICMS (Citel)", _pn(dados.aliq_icms))

    # ---- Custo
    perc_st = dados.st.mva if decisao.com_st else config.PERC_ST_SEM_ST
    add("Custo", "IPI", _p(dados.perc_ipi))
    add("Custo", "Frete de compra", _p(dados.perc_frete))
    if decisao.com_st:
        ok_st = dados.st.mva is not None and abs(perc_st - dados.st.mva) < 1e-9
        add("Custo", "ST (MVA)", _p(perc_st), ok_st, "MVA do Econet aplicado" if ok_st else "MVA diferente do Econet")
    else:
        ok_st = abs((perc_st or 0) - (config.PERC_ST_SEM_ST or 0)) < 1e-9
        add("Custo", "ST", _p(perc_st), ok_st, "Sem ST no Econet")
    add("Custo", "Caixa de papelão", _r(config.CUSTO_CAIXA_PAPELAO))

    # ---- Cenário
    add("Cenário", "Cenário aplicado", _nome_cenario(decisao.cenario))
    add("Cenário", "Tipo (pela Aliq. ICMS)", decisao.tipo or "—")
    add("Cenário", "Substituição tributária", "COM ST" if decisao.com_st else "SEM ST")
    add("Cenário", "Base reduzida (Confaz 52/91)", "Sim" if decisao.base_reduzida else "Não", None, dados.confaz.detalhe or "")
    if decisao.base_reduzida:
        add("Cenário", "Origem (base reduzida)", decisao.origem_base_reduzida)

    # ---- Impostos do cenário
    if decisao.base_reduzida:
        sem = (C.BASE_REDUZIDA_SEM_ST_IMPORTADO if decisao.origem_base_reduzida == "importado" else C.BASE_REDUZIDA_SEM_ST)
    elif decisao.tipo == "importado":
        sem = C.IMPORTADO_SEM_ST
    else:
        sem = C.NACIONAL_SEM_ST

    def impostos(rot, d, conferir=False):
        g = "Impostos" + (f" — {rot}" if rot else "")
        entrada = d["icms_entrada_credito"]
        ok, nota = None, ""
        if conferir and decisao.tipo == "nacional" and not decisao.base_reduzida and dados.aliq_icms is not None:
            ok = abs(dados.aliq_icms / 100 - entrada) < 1e-9
            nota = "Confere com a Aliq. ICMS do Citel" if ok else f"Citel informa {_pn(dados.aliq_icms)}; o motor usa {_p(entrada)} fixo no cenário nacional"
        elif conferir and decisao.tipo == "importado" and not decisao.base_reduzida and dados.aliq_icms is not None:
            ok = abs(dados.aliq_icms / 100 - entrada) < 1e-9
            nota = "Confere com a Aliq. ICMS do Citel" if ok else f"Citel informa {_pn(dados.aliq_icms)}; o motor usa {_p(entrada)}"
        elif conferir and decisao.base_reduzida:
            ok = True
            nota = "Base reduzida: entrada 4,00% (importado) ou 8,80% (nacional), pela origem"
        add(g, "ICMS entrada (crédito)", _p(entrada), ok, nota)
        add(g, "ICMS saída", _p(d["icms_saida"]))
        add(g, "ICMS frete (crédito)", _p(d["icms_frete_ml_credito"]))
        if d.get("credito_presumido"):
            add(g, "Crédito presumido", _p(d["credito_presumido"]))
        add(g, "PIS/COFINS crédito", _p(d["pis_cofins_credito"]))
        add(g, "PIS/COFINS débito", _p(d["pis_cofins_debito"]))
        add(g, "IR/CSLL crédito", _p(d["ir_cs_credito"]))
        add(g, "IR/CSLL débito", _p(d["ir_cs_debito"]))

    fora_sp = sem
    if ml and decisao.com_st and not decisao.base_reduzida and decisao.tipo == "nacional":
        from app.engine.ml import scenarios as ML_S
        fora_sp = ML_S.NACIONAL_VENDA_FORA_SP_COM_ST_ML   # a aba do ML usa 12% (H54) neste sub-bloco, não os 18% da Shopee

    if decisao.com_st:
        impostos(f"venda p/ SP (peso {int(C.PESO_VENDA_SP * 100)}%)", C.VENDA_SP_COM_ST)
        impostos(f"venda p/ fora de SP (peso {int(C.PESO_VENDA_FORA_SP * 100)}%)", fora_sp, conferir=True)
    else:
        impostos("", sem, conferir=True)

    # ---- Taxas do marketplace (pelo preço promocional, que é o preço cobrado)
    promo = res.get("preco_promocional")
    if ml:
        from app.engine.ml import config as ML_C
        from app.engine.ml import custos_base as ML_CB
        cfg_ml = ML_C.obter()
        g = "Taxas Mercado Livre"
        comissao = dados.ml_comissao if dados.ml_comissao is not None else cfg_ml.get("comissao_pct")
        add(g, "Comissão", _p(comissao), None, "informada por produto (arquivo de dados)")
        add(g, "Taxa Citel + prêmio", _r(ML_CB.TAXA_CITEL_PREMIO))
        _frete_ml(add, g, dados, res)
        add(g, "Mentoria", _p(cfg_ml.get("perc_mentoria")))
        add(g, "Custo logístico", _p(cfg_ml.get("perc_custo_logistico")))
        add(g, "Perda", _p(cfg_ml.get("perc_perda")))
    else:
        cfg = C.config_atual()
        add("Taxas Shopee", "Comissão", _p(C.custo_shopee_pct(promo)), None, f"faixa pelo preço promocional {_r(promo)}")
        add("Taxas Shopee", "Taxa fixa + prêmio", _r(C.taxa_shp_premio(promo)))
        add("Taxas Shopee", "Mentoria", _p(cfg.get("perc_mentoria")))
        add("Taxas Shopee", "Custo logístico", _p(cfg.get("perc_custo_logistico")))
        add("Taxas Shopee", "Perda", _p(cfg.get("perc_perda")))

    # ---- Resultado
    desvio = abs(res["margem_promocional"] - margem)
    ok_m = desvio <= config.TOLERANCIA_MARGEM
    add("Resultado", "Margem desejada", _p(margem))
    add("Resultado", "Margem promocional obtida", _p(res["margem_promocional"]), ok_m,
        "Dentro da tolerância" if ok_m else "Fora da tolerância")
    add("Resultado", "Desconto promocional", _p(desconto))
    add("Resultado", "Preço cheio", _r(res.get("preco_cheio")))
    add("Resultado", "Preço promocional", _r(promo))
    pma = res.get("pma")
    if pma and pma.get("encontrado"):
        add("Resultado", "PMA (revenda)", _r(pma.get("revenda")), not pma.get("abaixo"),
            "Promocional acima do PMA" if not pma.get("abaixo") else f"Promocional abaixo do PMA (faltam {_r(pma.get('diferenca'))})")
    return it


def _itens_rj(dados, decisao, res, margem, desconto) -> list:
    """Mesmos grupos do SP, mas com os impostos e as taxas do motor do RJ (app/engine/rj): sem ST, sem perda, com crédito presumido e custo fixo."""
    from app.engine.rj import config as RJ
    from app.engine.rj import motor as RM

    it = []

    def add(g, r, v, ok=None, n=""):
        it.append({"g": g, "r": r, "v": v, "ok": ok, "n": n})

    mk = config.MARKETPLACE
    nome_mk = {"shopee": "Shopee", "tiktok": "TikTok Shop", "mercado_livre": "Mercado Livre"}.get(mk, mk)
    tipo_rj = "base_reduzida" if decisao.base_reduzida else decisao.tipo
    aliq = dict(RM.ALIQUOTAS[tipo_rj])
    if decisao.base_reduzida and decisao.origem_base_reduzida == "importado":
        aliq["icms_entrada_credito"] = 0.04   # mesma regra do motor: em Base Reduzida só o ICMS de entrada muda pela origem

    # ---- Produto (dados de entrada)
    add("Produto", "Custo unitário (sem IPI)", _r(dados.unitario))
    add("Produto", "NCM", dados.ncm or "—")
    add("Produto", "Aliq. ICMS (Citel)", _pn(dados.aliq_icms))

    # ---- Custo
    add("Custo", "IPI", _p(dados.perc_ipi))
    add("Custo", "Frete de compra", _p(dados.perc_frete))
    add("Custo", "ST", "Não existe no RJ")
    add("Custo", "Caixa de papelão", _r(config.CUSTO_CAIXA_PAPELAO))

    # ---- Cenário
    add("Cenário", "Cenário aplicado", _nome_cenario_rj(decisao.cenario))
    add("Cenário", "Tipo (pela Aliq. ICMS)", decisao.tipo or "—")
    add("Cenário", "Substituição tributária", "SEM ST (o RJ não tem ST)")
    add("Cenário", "Base reduzida (Confaz 52/91)", "Sim" if decisao.base_reduzida else "Não", None, dados.confaz.detalhe or "")
    if decisao.base_reduzida:
        add("Cenário", "Origem (base reduzida)", decisao.origem_base_reduzida)

    # ---- Impostos do cenário (RJ)
    entrada = aliq["icms_entrada_credito"]
    ok, nota = None, ""
    if decisao.base_reduzida:
        ok, nota = True, "Base reduzida: entrada 4,00% (importado) ou 8,80% (nacional), pela origem"
    elif dados.aliq_icms is not None and decisao.tipo in ("nacional", "importado"):
        ok = abs(dados.aliq_icms / 100 - entrada) < 1e-9
        nota = "Confere com a Aliq. ICMS do Citel" if ok else f"Citel informa {_pn(dados.aliq_icms)}; o motor do RJ usa {_p(entrada)} (padrão da planilha)"
    add("Impostos", "ICMS entrada (crédito)", _p(entrada), ok, nota)
    add("Impostos", "ICMS saída", _p(aliq["icms_saida"]))
    add("Impostos", "ICMS frete (crédito)", _p(aliq["icms_frete_ml_credito"]))
    add("Impostos", "Crédito presumido", _p(aliq["credito_presumido"]))
    add("Impostos", "PIS/COFINS crédito", _p(aliq["pis_cofins_credito"]))
    add("Impostos", "PIS/COFINS débito", _p(aliq["pis_cofins_debito"]))
    add("Impostos", "IR/CSLL crédito", _p(aliq["ir_cs_credito"]))
    add("Impostos", "IR/CSLL débito", _p(aliq["ir_cs_debito"]))

    # ---- Taxas do marketplace (pelo preço promocional, que é o preço cobrado)
    promo = res.get("preco_promocional")
    grupo = f"Taxas {nome_mk}"
    try:
        cfg = RJ.obter(mk)
        ent = RM.EntradasRJ(marketplace=mk, tipo=tipo_rj, custo_sem_ipi=dados.unitario or 0.0,
                            custo_caixa_papelao=config.CUSTO_CAIXA_PAPELAO,
                            comissao_pct=dados.ml_comissao if mk == "mercado_livre" else None)
        perc_mkt, taxa_premio, _outros = RM._taxas_marketplace(mk, promo, cfg, ent)
        add(grupo, "Comissão", _p(perc_mkt), None,
            "informada por produto (arquivo de dados)" if mk == "mercado_livre" else f"faixa pelo preço promocional {_r(promo)}")
        add(grupo, "Taxa fixa + prêmio", _r(taxa_premio))
        if mk == "mercado_livre":
            _frete_ml(add, grupo, dados, res)
        if mk == "tiktok":
            add(grupo, "Comissão de afiliados", _p(cfg.get("comissao_afiliados_pct")))
        add(grupo, "Mentoria", _p(cfg.get("perc_mentoria")))
        add(grupo, "Custo logístico", _p(cfg.get("perc_custo_logistico")))
        add(grupo, "Custo fixo", _p(cfg.get("perc_custo_fixo")))
    except Exception as e:   # as taxas são só informativas: sem elas o resto do popup continua
        add(grupo, "Taxas", "não consegui ler", None, f"{type(e).__name__}: {e}")

    # ---- Resultado
    desvio = abs(res["margem_promocional"] - margem)
    ok_m = desvio <= config.TOLERANCIA_MARGEM
    add("Resultado", "Margem desejada", _p(margem))
    add("Resultado", "Margem promocional obtida", _p(res["margem_promocional"]), ok_m,
        "Dentro da tolerância" if ok_m else "Fora da tolerância")
    add("Resultado", "Desconto promocional", _p(desconto))
    add("Resultado", "Preço cheio", _r(res.get("preco_cheio")))
    add("Resultado", "Preço promocional", _r(promo))
    pma = res.get("pma")
    if pma and pma.get("encontrado"):
        add("Resultado", "PMA (revenda)", _r(pma.get("revenda")), not pma.get("abaixo"),
            "Promocional acima do PMA" if not pma.get("abaixo") else f"Promocional abaixo do PMA (faltam {_r(pma.get('diferenca'))})")
    return it
