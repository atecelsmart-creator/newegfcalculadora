"""
Modelos de entrada/saída da API. Só formato — nenhuma regra de negócio mora aqui.
"""
from enum import Enum

from pydantic import BaseModel, Field


class Marketplace(str, Enum):
    SHOPEE = "shopee"
    MERCADO_LIVRE = "mercado_livre"
    TIKTOK = "tiktok"
    # Só RJ (não existem na planilha de SP):
    MAGALU = "magalu"
    AMAZON_DBA = "amazon_dba"


class Estado(str, Enum):
    """SP usa o motor original; RJ usa app/engine/rj (regras da planilha do Rio)."""

    SP = "SP"
    RJ = "RJ"


class Cenario(str, Enum):
    NACIONAL_SEM_ST = "nacional_sem_st"
    NACIONAL_COM_ST = "nacional_com_st"
    BASE_REDUZIDA_SEM_ST = "base_reduzida_sem_st"
    BASE_REDUZIDA_COM_ST = "base_reduzida_com_st"
    IMPORTADO_SEM_ST = "importado_sem_st"
    IMPORTADO_COM_ST = "importado_com_st"


class OrigemBaseReduzida(str, Enum):
    """
    Só tem efeito nos cenários Base Reduzida - com ST e Base Reduzida - sem
    ST: define se o ICMS entrada crédito é 8,80% (NACIONAL, padrão) ou
    4,00% (IMPORTADO) — no com ST, isso vale só pro sub-bloco "venda p/
    fora de SP". Não tem NENHUMA relação com os cenários "Produto
    Importado" (esses continuam fixos em 4%, sem essa opção). Ignorado nos
    outros 4 cenários (Nacional sem/com ST, Importado sem/com ST).
    """

    NACIONAL = "nacional"
    IMPORTADO = "importado"


class CalculoInput(BaseModel):
    cenario: Cenario
    marketplace: Marketplace = Marketplace.SHOPEE
    # RJ só aceita os cenários "sem ST" (Nacional / Base Reduzida / Importado).
    estado: Estado = Estado.SP

    # Só Mercado Livre: peso + faixa de valor (C8/C9 da aba ML) definem o
    # frete (D20) via tabela "BASE FRETE MELI". No ML, custo_frete abaixo é
    # ignorado e substituído por esse lookup. Shopee/TikTok ignoram os dois.
    # ml_faixa_valor: um rótulo de faixa (ex. "19 a R$ 48,99") fixa a faixa na
    # mão, como o dropdown da planilha; "auto" (ou vazio) deduz a faixa do
    # preço de venda encontrado pelo solver.
    ml_peso: str | None = None
    ml_faixa_valor: str | None = None

    # Só Mercado Livre (SP): comissão do ML em fração (ex.: 0.12 = 12%), informada na
    # tela a cada cálculo (C21 da planilha é célula de entrada: muda por produto/categoria).
    # None = usa o valor salvo em campos_ajustaveis_mercado_livre.json (compatibilidade).
    ml_comissao_pct: float | None = Field(None, gt=0, lt=1)

    # Só RJ. Magalu: nível de serviço + peso (frete depende do preço, calculado no motor).
    # Amazon DBA: peso + faixa de valor (escolhida na tela, como no ML).
    magalu_nivel: str | None = None
    magalu_peso: str | None = None
    amz_peso: str | None = None
    amz_faixa_valor: str | None = None
    # Amazon DBA — KG ADICIONAL (H2 faixa de preço e H4 qtd de kg da aba AMAZON DBA). Opcional: sem faixa
    # ou sem kg o adicional vale 0 (igual à planilha). O valor por kg vem da tabela (rj/frete.py), não da tela.
    amz_kg_faixa: str | None = None
    amz_qtd_kg: float = Field(0, ge=0, le=1000, description="Quantidade de kg adicionais (Amazon DBA, RJ)")

    custo_sem_ipi: float = Field(..., gt=0, description="Preço de custo sem IPI")
    # Código do produto na tabela PMA (Preço Sugerido Revenda). Opcional: se informado, a resposta
    # traz em `pma` a comparação do preço promocional com a REVENDA da tabela.
    codigo_pma: str | None = None
    perc_ipi: float = Field(0, ge=0, description="Percentual de IPI (ex: 0.05 = 5%)")
    custo_frete: float = Field(
        0,
        ge=0,
        description=(
            "Custo do frete em R$. Mercado Livre: se > 0, é o frete já conhecido (D20 digitado "
            "direto) e substitui a tabela peso x faixa de valor. Demais marketplaces: ignorado."
        ),
    )
    perc_frete: float = Field(
        0,
        ge=0,
        lt=1,
        description=(
            "Todos os marketplaces: FRETE de compra (C14 no ML, C12 na Shopee/TikTok), percentual sobre "
            "custo + IPI (ex: 0.03 = 3%). Entra no custo do produto e no crédito de "
            "ICMS entrada. Em Shopee/TikTok, custo_frete (R$) é ignorado (D18 vazio na planilha)."
        ),
    )
    perc_st: float = Field(
        0,
        ge=0,
        description=(
            "Percentual de ST. CORRIGIDO (2026-09): entra no CUSTO do produto "
            "(D14) em TODOS os cenários, inclusive os 'sem ST' — a diferença "
            "real entre 'sem ST' e 'com ST' é que só no 'com ST' o valor do ST "
            "também soma na fórmula do ICMS entrada crédito (sub-bloco 'venda "
            "p/ fora de SP'). Não é mais travado em 0 nos cenários sem ST."
        ),
    )
    # CORRIGIDO: esse custo NÃO é fixo pra todo produto (decisão anterior estava
    # errada) — na planilha (D21) só se aplica a produtos específicos (latas de
    # tinta, frigideiras Wok). Volta a ser informado pelo usuário, com 0 como
    # padrão (produto sem caixa de papelão). Quando o produto usa a caixa, o
    # frontend sugere R$2,79 (constants.CUSTO_CAIXA_PAPELAO_PADRAO) como valor
    # de referência, mas o usuário pode digitar outro valor.
    custo_caixa_papelao: float = Field(
        0, ge=0, description="Custo da caixa de papelão, só se o produto usar (R$2,79 de referência); 0 se não usar"
    )
    margem_desejada: float = Field(
        ..., gt=0, lt=1, description="Margem desejada sobre o preço promocional (o preço real cobrado do cliente)"
    )
    desconto_promocional: float = Field(
        0, ge=0, lt=1, description="Desconto usado para inflar o preço promocional e gerar o preço cheio exibido no 'de/por'"
    )
    # Só RJ, cenários Nacional (ICMS ENTRADA CRÉDITO, padrão 12%) e Importado (ICMS SAÍDA, padrão 8,80%),
    # em fração (0.12 = 12%). None = usa o padrão da planilha. Ignorado nos outros cenários e em SP.
    icms_rj_pct: float | None = Field(None, ge=0, lt=1)
    origem_base_reduzida: OrigemBaseReduzida = Field(
        OrigemBaseReduzida.NACIONAL,
        description=(
            "Só usado nos cenários Base Reduzida — com ST e Base Reduzida — sem ST: "
            "'nacional' = ICMS entrada 8,80% (padrão), 'importado' = ICMS entrada 4,00%. "
            "Ignorado nos outros cenários — inclusive nos cenários 'Produto Importado', "
            "que não são afetados por este campo."
        ),
    )


class ConfigUpdateInput(BaseModel):
    """
    Corpo do PUT /api/config. Cada chave é opcional — manda só o(s)
    marketplace(s) que o usuário editou na aba "Campos Ajustáveis". O
    conteúdo de cada dict é livre (comissão, taxa fixa, mentoria etc.);
    a validação de formato fica por conta de cada módulo de config
    (app/engine/<marketplace>/config.py ou constants.py), não aqui —
    os campos mudam de marketplace pra marketplace.
    """
    shopee: dict | None = None
    mercado_livre: dict | None = None
    tiktok: dict | None = None
    # Campos ajustáveis do RJ: {"shopee": {...}, "mercado_livre": {...}, "tiktok": {...}}
    rj: dict | None = None


class PmaOutput(BaseModel):
    """Comparação do preço promocional com a REVENDA da tabela PMA (app/pma/store.py)."""

    codigo: str
    encontrado: bool
    tabela_carregada: bool = True
    descricao: str | None = None
    aba: str | None = None  # aba da planilha PMA onde o código foi achado
    marca: str | None = None  # marca da aba (ex.: B+D = Black + Decker; abas Stanley e Dewalt)
    revenda: float | None = None
    abaixo: bool = False
    diferenca: float | None = None  # quanto falta pro PMA (só quando abaixo)


class CalculoOutput(BaseModel):
    estado: Estado = Estado.SP
    cenario: Cenario
    marketplace: Marketplace
    preco_necessario: float
    preco_cheio: float
    preco_promocional: float
    lucro_real: float
    margem_real: float
    lucro_promocional: float
    margem_promocional: float

    # Campos de apoio à validação contra a planilha — não fazem parte
    # do contrato final da API, mas ajudam a comparar com o Excel na Etapa 8.
    custo_produto_total: float
    custo_total_impostos: float

    # Só Mercado Livre (None nos outros): faixa de valor e frete efetivamente
    # aplicados ao preço promocional — útil pra conferir com a planilha.
    ml_faixa_valor_aplicada: str | None = None
    ml_frete_aplicado: float | None = None

    # Só Amazon DBA (RJ): kg adicional em R$ (H5 da planilha), já descontado no lucro; None nos demais.
    amz_frete_adicional: float | None = None

    # Tabela PMA (None se nenhum código PMA foi informado).
    pma: PmaOutput | None = None
