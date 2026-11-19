"""Dashboard público do Censo Escolar (INEP) — Plotly Dash + DuckDB + IA generativa (Gemini).

Rodar localmente:
    python app.py
"""

import os
from functools import lru_cache

import dash
import pandas as pd
import plotly.graph_objects as go
from dash import Input, Output, State, ctx, dcc, html

import db
from ai.chat import responder as ai_responder
from ai.insights import gerar_leituras

# --- Paleta (validada com o validador da skill de dataviz sobre a superfície #fffbf3) ---
CORES = {
    "primaria": "#008a7e",  # verde-petróleo: Pública / Urbana / série única
    "secundaria": "#c95b28",  # terracota: Privada / Rural
    "neutra": "#b9b1a0",  # "Não informado"
    "ink": "#1d1b16",
    "ink_secundaria": "#5a554b",
    "muted": "#8c8576",
    "grid": "#ece5d6",
    "surface": "#fffbf3",
}
CORES_REDE = {"Pública": CORES["primaria"], "Privada": CORES["secundaria"]}
CORES_LOCAL = {"Urbana": CORES["primaria"], "Rural": CORES["secundaria"], "Não informado": CORES["neutra"]}

ORDEM_FAIXAS = ["0-3", "4-5", "6-10", "11-14", "15-17", "18+"]
NOMES_FAIXAS = {"0-3": "0–3", "4-5": "4–5", "6-10": "6–10", "11-14": "11–14", "15-17": "15–17", "18+": "18+"}
TOTAL_MUNICIPIOS_BR = 5570

FONTE = "Inter, system-ui, -apple-system, 'Segoe UI', sans-serif"

SUGESTOES_CHAT = [
    "Quais os 5 municípios com mais matrículas?",
    "Qual UF tem a maior proporção de alunos na zona rural?",
    "Em quais estados a rede privada tem mais peso no Ensino Médio?",
    "Quantos alunos com 18 anos ou mais estudam na rede pública?",
]

app = dash.Dash(
    __name__,
    title="Censo Escolar — Painel Público",
    suppress_callback_exceptions=True,
    external_stylesheets=["https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap"],
    meta_tags=[{"name": "viewport", "content": "width=device-width, initial-scale=1"}],
)
server = app.server


@server.route("/saude")
def saude():
    return db.diagnostico()


# --- Formatação pt-BR ---
def fmt_int(valor) -> str:
    return f"{int(round(valor)):,}".replace(",", ".")


def fmt_dec(valor, casas=1) -> str:
    return f"{valor:,.{casas}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def fmt_pct(valor) -> str:
    return fmt_dec(valor) + "%"


def fmt_compacto(valor) -> str:
    for limite, sufixo in ((1e9, " bi"), (1e6, " mi"), (1e3, " mil")):
        if abs(valor) >= limite:
            numero = fmt_dec(valor / limite)
            return (numero[:-2] if numero.endswith(",0") else numero) + sufixo
    return fmt_int(valor)


def fmt_numero(valor) -> str:
    if isinstance(valor, float) and not valor.is_integer():
        return fmt_dec(valor)
    return fmt_int(valor)


def _compacto_partes(valor) -> tuple[str, str]:
    """'47,3 mi' -> ('47,3', 'mi') para o número grande do KPI."""
    numero, _, sufixo = fmt_compacto(valor).partition(" ")
    return numero, sufixo


# --- Componentes de layout ---
def icone(nome, classe=""):
    return html.Span(className=f"ic ic-{nome} {classe}".strip(), **{"aria-hidden": "true"})


def kpi_card(chave, titulo, nome_icone):
    return html.Article(
        className="kpi",
        children=[
            html.Div(className="kpi-topo", children=[icone(nome_icone, "ic-chip"), html.Span(titulo, className="kpi-titulo")]),
            html.Div(id=f"kpi-{chave}", className="kpi-corpo"),
        ],
    )


def card(titulo, subtitulo, nome_icone, corpo, chave, classe_extra="", id_card=None):
    filhos = [
        html.Header(
            className="card-header",
            children=[
                icone(nome_icone, "ic-chip"),
                html.Div([html.H3(titulo), html.P(subtitulo, className="card-sub")]),
            ],
        ),
        *corpo,
        html.Div(
            className="insight",
            children=[
                html.Span("✦", className="insight-marca", title="Leitura gerada por IA"),
                dcc.Loading(
                    type="dot",
                    color=CORES["primaria"],
                    parent_className="insight-loading",
                    children=dcc.Markdown(id=f"i-{chave}", className="insight-texto"),
                ),
            ],
        ),
        html.Details(className="tabela-dados", children=[html.Summary("Ver dados em tabela"), html.Div(id=f"t-{chave}")]),
    ]
    props = {"id": id_card} if id_card else {}
    return html.Article(className=f"card {classe_extra}".strip(), children=filhos, **props)


# Altura fixa por gráfico (igual à da figura): o card não "pula" ao carregar nem sobrepõe o texto abaixo.
ALTURAS = {"g-uf": 420, "g-local": 240, "g-etapa": 300, "g-idade": 300, "g-rede": 330, "g-serie": 300}


def grafico(id_grafico):
    return dcc.Loading(
        type="circle",
        color=CORES["primaria"],
        delay_show=300,
        children=dcc.Graph(
            id=id_grafico,
            config={"displayModeBar": False, "responsive": True},
            className="grafico",
            style={"height": f"{ALTURAS[id_grafico]}px"},
        ),
    )


def tabela_html(df: pd.DataFrame, colunas: dict):
    """Tabela acessível (alternativa ao gráfico). `colunas` mapeia coluna -> rótulo."""
    if df is None or df.empty:
        return html.P("Sem dados para os filtros selecionados.", className="vazio")
    cabecalho = html.Thead(html.Tr([html.Th(rotulo) for rotulo in colunas.values()]))
    linhas = []
    for _, linha in df.iterrows():
        celulas = []
        for coluna in colunas:
            valor = linha[coluna]
            numerico = pd.api.types.is_number(valor) and not isinstance(valor, bool)
            celulas.append(html.Td(fmt_numero(valor) if numerico else str(valor), className="num" if numerico else None))
        linhas.append(html.Tr(celulas))
    return html.Table(className="tabela", children=[cabecalho, html.Tbody(linhas)])


def nav_item(rotulo, ancora, nome_icone):
    return html.A(href=f"#{ancora}", className="nav-item", children=[icone(nome_icone), html.Span(rotulo)])


def montar_layout():
    # Função (não valor fixo): se o arquivo de dados mudar ou faltar, cada recarga da página tenta de novo.
    try:
        anos = db.listar_anos()
        ufs = db.listar_ufs()
        erro_dados = None
    except Exception as erro:
        print(f"[ERRO] Falha ao ler o DuckDB: {erro!r}", flush=True)
        anos, ufs, erro_dados = [], [], erro

    periodo = f"{min(anos)}–{max(anos)}" if len(anos) > 1 else (str(anos[0]) if anos else "")

    sidebar = html.Aside(
        className="sidebar",
        children=[
            html.Div(
                className="marca",
                children=[
                    html.Span(icone("escola"), className="marca-logo"),
                    html.Div([html.Strong("Censo Escolar"), html.Span(f"INEP · {periodo}".strip(" ·"), className="marca-sub")]),
                ],
            ),
            html.Nav(
                className="nav",
                children=[
                    html.Span("Painel", className="nav-grupo"),
                    nav_item("Visão geral", "visao-geral", "grade"),
                    nav_item("Território", "territorio", "mapa"),
                    nav_item("Perfil dos alunos", "perfil", "alunos"),
                    nav_item("Redes de ensino", "redes", "predio"),
                    html.Span("Inteligência", className="nav-grupo"),
                    nav_item("Resumo da IA", "resumo", "brilho"),
                    nav_item("Pergunte aos dados", "chat", "chat"),
                ],
            ),
            html.Div(
                className="sidebar-rodape",
                children=[
                    html.Strong("Fonte dos dados"),
                    html.P("INEP — Microdados do Censo Escolar da Educação Básica. Dados agregados, sem identificação individual."),
                    html.A("Status dos dados →", href="/saude", target="_blank", className="link-sutil"),
                ],
            ),
        ],
    )

    filtros = html.Div(
        className="filtros",
        children=[
            html.Div(
                className="filtro",
                children=[
                    html.Label("Ano", htmlFor="f-ano"),
                    dcc.Dropdown(
                        id="f-ano",
                        options=[{"label": str(a), "value": a} for a in anos],
                        value=max(anos) if anos else None,
                        clearable=False,
                        searchable=False,
                        placeholder="—",
                    ),
                ],
            ),
            html.Div(
                className="filtro filtro-uf",
                children=[
                    html.Label("Estado", htmlFor="f-uf"),
                    dcc.Dropdown(
                        id="f-uf",
                        options=[{"label": "Brasil (todas)", "value": "TODAS"}] + [{"label": u, "value": u} for u in ufs],
                        value="TODAS",
                        clearable=False,
                    ),
                ],
            ),
            html.Div(
                className="filtro",
                children=[
                    html.Label("Rede"),
                    dcc.RadioItems(
                        id="f-rede",
                        className="segmentado",
                        options=[
                            {"label": "Todas", "value": "TODAS"},
                            {"label": "Pública", "value": "Pública"},
                            {"label": "Privada", "value": "Privada"},
                        ],
                        value="TODAS",
                        inline=True,
                    ),
                ],
            ),
            html.Button([icone("limpar"), "Limpar"], id="btn-limpar", className="btn-sec", n_clicks=0),
        ],
    )

    alerta = (
        html.Div(
            className="alerta",
            children=[
                html.Strong("Não foi possível ler os dados do painel. "),
                "O arquivo dados/censo.duckdb não foi encontrado ou está corrompido — rode o ETL e o dbt "
                "(veja o README) e abra /saude para o detalhe.",
            ],
        )
        if erro_dados
        else None
    )

    conteudo = html.Main(
        className="principal",
        children=[
            html.Header(
                className="cabecalho",
                children=[
                    html.Div(
                        [
                            html.H1("Matrículas na educação básica"),
                            html.P(id="contexto", className="cabecalho-sub"),
                        ]
                    ),
                    filtros,
                ],
            ),
            alerta,
            html.Section(
                id="visao-geral",
                className="kpis",
                children=[
                    kpi_card("total", "Matrículas", "alunos"),
                    kpi_card("publica", "Rede pública", "predio"),
                    kpi_card("rural", "Zona rural", "folha"),
                    kpi_card("municipios", "Municípios atendidos", "pino"),
                ],
            ),
            html.Section(
                id="resumo",
                className="resumo",
                children=[
                    html.Div(
                        className="resumo-topo",
                        children=[
                            icone("brilho", "ic-chip ic-chip-forte"),
                            html.Div([html.H2("Resumo da IA"), html.P(id="resumo-origem", className="card-sub")]),
                        ],
                    ),
                    dcc.Loading(
                        type="dot",
                        color=CORES["primaria"],
                        children=html.Ol(id="resumo-lista", className="resumo-lista"),
                    ),
                ],
            ),
            html.Section(
                id="territorio",
                className="grade grade-2-1",
                children=[
                    card(
                        "Matrículas por estado",
                        "Zona de residência do aluno · clique em um estado para filtrar o painel",
                        "mapa",
                        [grafico("g-uf")],
                        "uf",
                    ),
                    card(
                        "Urbana × rural",
                        "Participação das matrículas por zona",
                        "folha",
                        [html.Div(className="donut", children=[grafico("g-local"), html.Ul(id="legenda-local", className="legenda-lista")])],
                        "local",
                    ),
                ],
            ),
            html.Section(
                id="perfil",
                className="grade grade-1-1",
                children=[
                    card("Etapa de ensino", "Matrículas e participação de cada etapa", "camadas", [grafico("g-etapa")], "etapa"),
                    card("Faixa etária", "Idade do aluno, em anos", "alunos", [grafico("g-idade")], "idade"),
                ],
            ),
            html.Section(
                id="redes",
                className="grade grade-auto",
                children=[
                    card(
                        "Rede pública × privada por etapa",
                        "% das matrículas de cada etapa (ignora o filtro de rede)",
                        "predio",
                        [grafico("g-rede")],
                        "rede",
                    ),
                    card(
                        f"Evolução das matrículas ({periodo})",
                        "Total por ano e rede",
                        "grafico",
                        [grafico("g-serie")],
                        "serie",
                        id_card="card-serie",
                    ),
                ],
            ),
            html.Section(
                id="chat",
                className="card chat",
                children=[
                    html.Header(
                        className="card-header",
                        children=[
                            icone("chat", "ic-chip ic-chip-forte"),
                            html.Div(
                                [
                                    html.H3("Pergunte aos dados"),
                                    html.P(
                                        "A IA transforma a pergunta em SQL, roda numa cópia somente leitura do Censo "
                                        "e responde com o número. Sem ano/estado na pergunta, usa o recorte dos filtros.",
                                        className="card-sub",
                                    ),
                                ]
                            ),
                        ],
                    ),
                    html.Div(
                        className="chat-sugestoes",
                        children=[
                            html.Button(s, id={"tipo": "sugestao", "i": i}, className="chip", n_clicks=0)
                            for i, s in enumerate(SUGESTOES_CHAT)
                        ],
                    ),
                    html.Div(
                        className="chat-entrada",
                        children=[
                            dcc.Input(
                                id="chat-input",
                                type="text",
                                placeholder="Ex.: qual UF tem mais matrículas no Ensino Médio?",
                                debounce=False,
                                n_submit=0,
                                autoComplete="off",
                            ),
                            html.Button([icone("enviar"), "Perguntar"], id="chat-enviar", n_clicks=0, className="btn-primario"),
                        ],
                    ),
                    dcc.Loading(type="dot", color=CORES["primaria"], children=html.Div(id="chat-carregando")),
                    html.Div(id="chat-historico", className="chat-historico"),
                ],
            ),
            html.Footer(
                className="rodape",
                children=[
                    html.P("Fonte: INEP — Microdados do Censo Escolar da Educação Básica."),
                    html.P("Textos marcados com ✦ são gerados por IA a partir de números calculados pelo painel."),
                ],
            ),
        ],
    )

    return html.Div(className="app", children=[sidebar, conteudo])


app.layout = montar_layout


# --- Dados ---
def _filtrar(df: pd.DataFrame, ano=None, uf=None, rede=None) -> pd.DataFrame:
    out = df[df["ano_censo"] == ano] if ano is not None else df
    if uf and uf != "TODAS" and "uf" in out.columns:
        out = out[out["uf"] == uf]
    if rede and rede != "TODAS" and "rede" in out.columns:
        out = out[out["rede"] == rede]
    return out


def _indicadores(loc_rede: pd.DataFrame, loc_sem_rede: pd.DataFrame, chave: str) -> pd.DataFrame:
    """Total, % rural, % pública e municípios atendidos por `chave` (uf ou ano_censo)."""
    soma = lambda d: d.groupby(chave)["qtd_matriculas"].sum()  # noqa: E731
    out = pd.DataFrame(
        {
            "total": soma(loc_rede),
            "rural": soma(loc_rede[loc_rede["localizacao"] == "Rural"]),
            "municipios": loc_rede[loc_rede["qtd_matriculas"] > 0].groupby(chave)["co_municipio"].nunique(),
        }
    ).fillna(0)
    pct_publica = 100 * soma(loc_sem_rede[loc_sem_rede["rede"] == "Pública"]) / soma(loc_sem_rede)
    out["pct_publica"] = pct_publica.reindex(out.index).fillna(0)
    out["pct_rural"] = (100 * out["rural"] / out["total"].where(out["total"] > 0)).fillna(0)
    return out


@lru_cache(maxsize=128)
def _agregados(ano, uf, rede) -> dict:
    """Tudo que o painel precisa para um recorte. Cacheado: os DataFrames retornados não devem ser alterados."""
    localidade = db.carregar_tabela("diamond_por_localidade")
    escolaridade = db.carregar_tabela("diamond_por_escolaridade")

    idade = _filtrar(db.carregar_tabela("diamond_por_idade"), ano, uf, rede).groupby("faixa_etaria", as_index=False)[
        "qtd_matriculas"
    ].sum()
    idade = idade.assign(ordem=idade["faixa_etaria"].map({f: i for i, f in enumerate(ORDEM_FAIXAS)})).sort_values("ordem")
    idade = idade.drop(columns="ordem").reset_index(drop=True)

    etapa = (
        _filtrar(escolaridade, ano, uf, rede)
        .groupby("etapa_ensino", as_index=False)["qtd_matriculas"]
        .sum()
        .sort_values("qtd_matriculas", ascending=False)
        .reset_index(drop=True)
    )

    loc = _filtrar(localidade, ano, uf, rede)
    por_local = loc.groupby("localizacao", as_index=False)["qtd_matriculas"].sum()
    por_local = por_local[por_local["qtd_matriculas"] > 0]
    por_local = por_local.assign(ordem=por_local["localizacao"].map({"Urbana": 0, "Rural": 1})).fillna({"ordem": 2})
    por_local = por_local.sort_values("ordem").drop(columns="ordem").reset_index(drop=True)

    # Por UF: não filtra por UF (mostra todas e destaca a selecionada)
    loc_ufs = _filtrar(localidade, ano, None, rede)
    por_uf = (
        loc_ufs[loc_ufs["localizacao"].isin(["Urbana", "Rural"])]
        .pivot_table(index="uf", columns="localizacao", values="qtd_matriculas", aggfunc="sum", fill_value=0)
        .reindex(columns=["Urbana", "Rural"], fill_value=0)
        .reset_index()
    )
    por_uf["Total"] = por_uf["Urbana"] + por_uf["Rural"]
    por_uf = por_uf.sort_values("Total", ascending=False).reset_index(drop=True)

    # Rede por etapa: não filtra por rede (é o próprio corte)
    rede_etapa = (
        _filtrar(escolaridade, ano, uf, None)
        .pivot_table(index="etapa_ensino", columns="rede", values="qtd_matriculas", aggfunc="sum", fill_value=0)
        .reindex(columns=["Pública", "Privada"], fill_value=0)
        .reset_index()
    )
    rede_etapa["Total"] = rede_etapa["Pública"] + rede_etapa["Privada"]
    rede_etapa = rede_etapa[rede_etapa["Total"] > 0].copy()
    rede_etapa["% Pública"] = 100 * rede_etapa["Pública"] / rede_etapa["Total"]
    rede_etapa = rede_etapa.sort_values("% Pública").reset_index(drop=True)

    serie = (
        _filtrar(db.carregar_tabela("diamond_serie_temporal"), None, uf, rede)
        .groupby(["ano_censo", "rede"], as_index=False)["qtd_matriculas"]
        .sum()
    )

    # Indicadores: por UF (ano selecionado) e por ano (UF selecionada) — alimentam KPIs e mini-barras
    ind_uf = _indicadores(loc_ufs, _filtrar(localidade, ano, None, None), "uf")
    ind_ano = _indicadores(_filtrar(localidade, None, uf, rede), _filtrar(localidade, None, uf, None), "ano_censo")
    ind_brasil = _indicadores(
        loc_ufs.assign(br="BR"), _filtrar(localidade, ano, None, None).assign(br="BR"), "br"
    ).iloc[0]
    atual = ind_ano.loc[ano] if ano in ind_ano.index else pd.Series({"total": 0, "rural": 0, "municipios": 0, "pct_publica": 0, "pct_rural": 0})

    return {
        "idade": idade,
        "etapa": etapa,
        "por_local": por_local,
        "por_uf": por_uf,
        "rede_etapa": rede_etapa,
        "serie": serie,
        "ind_uf": ind_uf,
        "ind_ano": ind_ano,
        "ind_brasil": ind_brasil,
        "atual": atual,
    }


# --- KPIs ---
def _mini_barras(itens):
    """itens: lista de (rótulo, valor, texto, ativo). Barras em HTML, sem custo de Plotly."""
    if not itens:
        return None
    maximo = max(v for _, v, _, _ in itens) or 1
    algum_ativo = any(a for *_, a in itens)
    return html.Div(
        className="mini-barras" + (" mini-barras-densa" if len(itens) > 12 else ""),
        children=[
            html.Span(
                className="mb" + (" mb-ativa" if ativo or not algum_ativo and i == 0 else ""),
                style={"height": f"{max(6, 100 * valor / maximo):.0f}%"},
                title=f"{rotulo}: {texto}",
            )
            for i, (rotulo, valor, texto, ativo) in enumerate(itens)
        ],
    )


def _kpi(valor, sufixo, pill, legenda, barras, detalhe):
    seta, texto_pill = pill
    return [
        html.Div(
            className="kpi-delta",
            children=[
                html.Span(className="pill", children=[html.Span(seta, className="pill-seta") if seta else None, texto_pill]),
                html.Span(legenda, className="kpi-legenda"),
            ],
        ),
        html.Div(
            className="kpi-base",
            children=[
                html.Div(className="kpi-numero", children=[html.Span(valor, className="kpi-valor"), html.Span(sufixo, className="kpi-sufixo")]),
                _mini_barras(barras),
            ],
        ),
        html.Span(detalhe, className="kpi-det"),
    ]


def _seta(diferenca):
    return "↗" if diferenca > 0 else ("↘" if diferenca < 0 else "→")


def _kpis(d, ano, uf, rede):
    """Compara com o ano anterior quando há série; senão, com o Brasil / entre estados."""
    atual, ind_ano, ind_uf, br = d["atual"], d["ind_ano"], d["ind_uf"], d["ind_brasil"]
    anos = sorted(ind_ano.index)
    anterior = max([a for a in anos if a < ano], default=None) if ano is not None else None
    tem_uf = bool(uf and uf != "TODAS")

    def barras(coluna, formatar):
        if len(anos) > 1:
            return [(str(a), ind_ano.loc[a, coluna], formatar(ind_ano.loc[a, coluna]), a == ano) for a in anos]
        ordenado = ind_uf.sort_values(coluna, ascending=False)
        return [(u, linha[coluna], formatar(linha[coluna]), u == uf) for u, linha in ordenado.iterrows()]

    def comparacao_pp(coluna, nome):
        if anterior is not None:
            dif = atual[coluna] - ind_ano.loc[anterior, coluna]
            return (_seta(dif), fmt_dec(abs(dif)) + " p.p."), f"vs {anterior}"
        if tem_uf:
            dif = atual[coluna] - br[coluna]
            return (_seta(dif), fmt_dec(abs(dif)) + " p.p."), f"{'acima' if dif >= 0 else 'abaixo'} do Brasil ({fmt_pct(br[coluna])})"
        lider = ind_uf[coluna].idxmax()
        return (None, f"{lider} {fmt_pct(ind_uf.loc[lider, coluna])}"), nome

    # 1. Total
    if anterior is not None and ind_ano.loc[anterior, "total"]:
        var = 100 * (atual["total"] / ind_ano.loc[anterior, "total"] - 1)
        pill_total, leg_total = (_seta(var), fmt_pct(abs(var))), f"vs {anterior}"
    elif tem_uf:
        pill_total, leg_total = (None, fmt_pct(100 * atual["total"] / br["total"] if br["total"] else 0)), "das matrículas do Brasil"
    else:
        lider = ind_uf["total"].idxmax()
        pill_total, leg_total = (None, f"{lider} {fmt_pct(100 * ind_uf.loc[lider, 'total'] / br['total'])}"), "maior estado"
    total = _kpi(
        *_compacto_partes(atual["total"]),
        pill_total,
        leg_total,
        barras("total", fmt_compacto),
        f"{fmt_int(atual['total'])} matrículas" + (f" na rede {rede.lower()}" if rede and rede != "TODAS" else ""),
    )

    # 2. % pública (sempre sobre todas as redes)
    pill, leg = comparacao_pp("pct_publica", "maior rede pública")
    publica = _kpi(
        fmt_dec(atual["pct_publica"]),
        "%",
        pill,
        leg,
        barras("pct_publica", fmt_pct),
        "das matrículas estão em escolas públicas",
    )

    # 3. % rural
    pill, leg = comparacao_pp("pct_rural", "estado mais rural")
    rural = _kpi(
        fmt_dec(atual["pct_rural"]),
        "%",
        pill,
        leg,
        barras("pct_rural", fmt_pct),
        f"{fmt_compacto(atual['rural'])} de alunos moram na zona rural",
    )

    # 4. Municípios
    if anterior is not None:
        dif = atual["municipios"] - ind_ano.loc[anterior, "municipios"]
        pill_mun, leg_mun = (_seta(dif), fmt_int(abs(dif))), f"vs {anterior}"
    else:
        pill_mun = (None, fmt_pct(100 * atual["municipios"] / TOTAL_MUNICIPIOS_BR))
        leg_mun = "dos municípios do país"
    municipios = _kpi(
        fmt_int(atual["municipios"]),
        "",
        pill_mun,
        leg_mun,
        barras("municipios", fmt_int),
        f"no estado de {uf}" if tem_uf else f"em {len(ind_uf)} unidades da federação",
    )
    return total, publica, rural, municipios


# --- Fatos para a IA (números já calculados e formatados) ---
def _fatos(d, ano, uf, rede) -> dict:
    fatos = {}
    tem_uf = bool(uf and uf != "TODAS")

    por_uf = d["por_uf"]
    if not por_uf.empty:
        total_br = por_uf["Total"].sum()
        top = por_uf.head(3)
        itens = [
            "Estados com mais matrículas: "
            + "; ".join(f"{u} {fmt_compacto(t)} ({fmt_pct(100 * t / total_br)} do país)" for u, t in zip(top["uf"], top["Total"]))
        ]
        rural = por_uf.assign(pct=100 * por_uf["Rural"] / por_uf["Total"]).sort_values("pct", ascending=False)
        itens.append(
            "Estados com maior % de alunos na zona rural: "
            + "; ".join(f"{u} {fmt_pct(p)}" for u, p in zip(rural["uf"].head(3), rural["pct"].head(3)))
        )
        itens.append(f"Estado com menor % rural: {rural['uf'].iloc[-1]} {fmt_pct(rural['pct'].iloc[-1])}")
        if tem_uf and uf in set(por_uf["uf"]):
            posicao = int(por_uf.index[por_uf["uf"] == uf][0]) + 1
            linha = por_uf[por_uf["uf"] == uf].iloc[0]
            itens.insert(0, f"{uf} é o {posicao}º estado em matrículas, com {fmt_compacto(linha['Total'])} ({fmt_pct(100 * linha['Total'] / total_br)} do país)")
        fatos["uf"] = itens

    loc = d["por_local"]
    if not loc.empty:
        total = loc["qtd_matriculas"].sum()
        itens = [
            f"{nome}: {fmt_compacto(v)} matrículas ({fmt_pct(100 * v / total)})"
            for nome, v in zip(loc["localizacao"], loc["qtd_matriculas"])
            if 100 * v / total >= 0.5
        ]
        if tem_uf:
            mesma_rede = f" (rede {rede.lower()})" if rede and rede != "TODAS" else ""
            itens.append(f"Média do Brasil{mesma_rede} na zona rural: {fmt_pct(d['ind_brasil']['pct_rural'])}")
        fatos["local"] = itens

    etapa = d["etapa"]
    if not etapa.empty:
        total = etapa["qtd_matriculas"].sum()
        fatos["etapa"] = [
            f"{n}: {fmt_compacto(v)} ({fmt_pct(100 * v / total)} do total)" for n, v in zip(etapa["etapa_ensino"], etapa["qtd_matriculas"])
        ] + ["Educação Especial se sobrepõe às demais etapas (o aluno também é contado na sua etapa)."]

    idade = d["idade"]
    if not idade.empty:
        total = idade["qtd_matriculas"].sum()
        por_faixa = dict(zip(idade["faixa_etaria"], idade["qtd_matriculas"]))
        maior = idade.loc[idade["qtd_matriculas"].idxmax()]
        obrigatoria = sum(por_faixa.get(f, 0) for f in ["4-5", "6-10", "11-14", "15-17"])
        fatos["idade"] = [
            f"Maior faixa: {NOMES_FAIXAS[maior['faixa_etaria']]} anos, {fmt_compacto(maior['qtd_matriculas'])} ({fmt_pct(100 * maior['qtd_matriculas'] / total)})",
            f"Idade escolar obrigatória (4 a 17 anos): {fmt_pct(100 * obrigatoria / total)} das matrículas",
            f"Alunos com 18 anos ou mais: {fmt_compacto(por_faixa.get('18+', 0))} ({fmt_pct(100 * por_faixa.get('18+', 0) / total)})",
            f"Creche (0 a 3 anos): {fmt_compacto(por_faixa.get('0-3', 0))} ({fmt_pct(100 * por_faixa.get('0-3', 0) / total)})",
        ]

    rede_etapa = d["rede_etapa"]
    if not rede_etapa.empty:
        mais = rede_etapa.iloc[-1]
        menos = rede_etapa.iloc[0]
        fatos["rede"] = [
            f"Etapa mais pública: {mais['etapa_ensino']}, {fmt_pct(mais['% Pública'])} na rede pública",
            f"Etapa com maior presença privada: {menos['etapa_ensino']}, {fmt_pct(100 - menos['% Pública'])} na rede privada",
        ]

    serie = d["serie"].groupby("ano_censo")["qtd_matriculas"].sum()
    if len(serie) > 1:
        primeiro, ultimo = serie.index.min(), serie.index.max()
        var = 100 * (serie[ultimo] / serie[primeiro] - 1)
        fatos["serie"] = [
            f"De {primeiro} a {ultimo}: {fmt_compacto(serie[primeiro])} para {fmt_compacto(serie[ultimo])} ({'+' if var >= 0 else ''}{fmt_pct(var)})",
            f"Ano com mais matrículas: {serie.idxmax()} ({fmt_compacto(serie.max())})",
        ]
    return fatos


def _texto_recorte(ano, uf, rede) -> str:
    lugar = "Brasil" if not uf or uf == "TODAS" else uf
    redes = "todas as redes" if not rede or rede == "TODAS" else f"rede {rede.lower()}"
    return " · ".join(p for p in [lugar, str(ano) if ano else "", redes] if p)


# --- Gráficos ---
def _estilo_base(fig: go.Figure, altura: int, legenda=False) -> go.Figure:
    fig.update_layout(
        height=altura,
        margin=dict(l=4, r=12, t=34 if legenda else 8, b=4),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family=FONTE, size=12, color=CORES["ink_secundaria"]),
        separators=",.",
        showlegend=legenda,
        legend=dict(orientation="h", x=0, y=1.02, yanchor="bottom", xanchor="left", traceorder="normal", font=dict(color=CORES["ink"]), title=None),
        hoverlabel=dict(bgcolor=CORES["surface"], bordercolor=CORES["grid"], font=dict(family=FONTE, color=CORES["ink"], size=13)),
        bargap=0.35,
        barcornerradius=4,
        uniformtext=dict(minsize=11, mode="hide"),
    )
    eixo = dict(
        gridcolor=CORES["grid"],
        gridwidth=1,
        zeroline=False,
        linecolor=CORES["grid"],
        tickfont=dict(color=CORES["muted"]),
        title=None,
        fixedrange=True,
    )
    fig.update_xaxes(**eixo)
    fig.update_yaxes(**eixo)
    return fig


def _eixo_pt(fig: go.Figure, maximo: float, eixo="y") -> None:
    """Marcas do eixo em pt-BR ("10 mi", "500 mil") no lugar do SI do Plotly ("10M", "500k")."""
    if maximo <= 0:
        return
    bruto = maximo / 4
    potencia = 10 ** (len(str(int(bruto))) - 1)
    passo = next(m * potencia for m in (1, 2, 2.5, 5, 10) if m * potencia >= bruto)
    marcas = [i * passo for i in range(int(maximo // passo) + 2) if i * passo <= maximo * 1.05]
    (fig.update_yaxes if eixo == "y" else fig.update_xaxes)(tickvals=marcas, ticktext=[fmt_compacto(m) for m in marcas])


def _figura_vazia(altura=300, mensagem="Sem dados para os filtros selecionados") -> go.Figure:
    fig = go.Figure()
    fig.add_annotation(text=mensagem, showarrow=False, font=dict(size=14, color=CORES["muted"]), x=0.5, y=0.5, xref="paper", yref="paper")
    _estilo_base(fig, altura)
    fig.update_xaxes(visible=False)
    fig.update_yaxes(visible=False)
    return fig


def fig_uf(df: pd.DataFrame, uf_selecionada) -> go.Figure:
    if df.empty:
        return _figura_vazia(ALTURAS["g-uf"])
    destaque = uf_selecionada and uf_selecionada != "TODAS"
    opacidade = [1.0 if (not destaque or u == uf_selecionada) else 0.3 for u in df["uf"]]
    fig = go.Figure()
    for localizacao in ["Urbana", "Rural"]:
        pct = 100 * df[localizacao] / df["Total"].where(df["Total"] > 0, 1)
        fig.add_bar(
            name=localizacao,
            x=df["uf"],
            y=df[localizacao],
            marker=dict(color=CORES_LOCAL[localizacao], opacity=opacidade, line=dict(color=CORES["surface"], width=1)),
            customdata=[fmt_pct(p) for p in pct],
            hovertemplate=f"<b>%{{x}}</b> · {localizacao}<br>%{{y:,.0f}} matrículas (%{{customdata}})<extra></extra>",
        )
    _estilo_base(fig, ALTURAS["g-uf"], legenda=True)
    fig.update_layout(barmode="stack", bargap=0.28, hovermode="closest")
    _eixo_pt(fig, df["Total"].max())
    fig.update_xaxes(showgrid=False, tickfont=dict(color=CORES["ink_secundaria"], size=11))
    return fig


def _zonas_visiveis(df: pd.DataFrame) -> pd.DataFrame:
    total = df["qtd_matriculas"].sum()
    return df[100 * df["qtd_matriculas"] / total >= 0.5] if total else df


def fig_local(df: pd.DataFrame) -> go.Figure:
    df = _zonas_visiveis(df)
    if df.empty:
        return _figura_vazia(240)
    total = df["qtd_matriculas"].sum()
    fig = go.Figure(
        go.Pie(
            labels=df["localizacao"],
            values=df["qtd_matriculas"],
            hole=0.7,
            sort=False,
            direction="clockwise",
            marker=dict(colors=[CORES_LOCAL.get(l, CORES["neutra"]) for l in df["localizacao"]], line=dict(color=CORES["surface"], width=3)),
            textinfo="none",
            customdata=[fmt_int(v) for v in df["qtd_matriculas"]],
            hovertemplate="<b>%{label}</b><br>%{customdata} matrículas (%{percent})<extra></extra>",
        )
    )
    fig.add_annotation(
        text=f"<span style='font-size:12px;color:{CORES['muted']}'>Total</span><br><b>{fmt_compacto(total)}</b>",
        showarrow=False,
        font=dict(size=22, color=CORES["ink"], family=FONTE),
        x=0.5,
        y=0.5,
    )
    _estilo_base(fig, ALTURAS["g-local"])
    fig.update_layout(margin=dict(l=0, r=0, t=0, b=0))
    return fig


def legenda_local(df: pd.DataFrame):
    if df.empty:
        return []
    total = df["qtd_matriculas"].sum()
    df = _zonas_visiveis(df)
    return [
        html.Li(
            [
                html.Span(className="legenda-cor", style={"background": CORES_LOCAL.get(nome, CORES["neutra"])}),
                html.Span(nome, className="legenda-nome"),
                html.Strong(fmt_pct(100 * v / total)),
                html.Span(f"{fmt_compacto(v)} de alunos", className="legenda-det"),
            ]
        )
        for nome, v in zip(df["localizacao"], df["qtd_matriculas"])
    ]


def fig_etapa(df: pd.DataFrame) -> go.Figure:
    if df.empty:
        return _figura_vazia()
    total = df["qtd_matriculas"].sum()
    df = df.sort_values("qtd_matriculas")
    fig = go.Figure(
        go.Bar(
            x=df["qtd_matriculas"],
            y=df["etapa_ensino"],
            orientation="h",
            marker=dict(color=CORES["primaria"]),
            text=[f"{fmt_compacto(v)} · {fmt_pct(100 * v / total)}" for v in df["qtd_matriculas"]],
            textposition="outside",
            textfont=dict(color=CORES["ink_secundaria"]),
            cliponaxis=False,
            hovertemplate="<b>%{y}</b><br>%{x:,.0f} matrículas<extra></extra>",
        )
    )
    _estilo_base(fig, 300)
    fig.update_layout(margin=dict(l=4, r=110, t=8, b=4))
    fig.update_xaxes(showgrid=True)
    _eixo_pt(fig, df["qtd_matriculas"].max(), "x")
    fig.update_yaxes(showgrid=False, tickfont=dict(color=CORES["ink"], size=13))
    return fig


def fig_idade(df: pd.DataFrame) -> go.Figure:
    if df.empty:
        return _figura_vazia()
    total = df["qtd_matriculas"].sum()
    fig = go.Figure(
        go.Bar(
            x=[NOMES_FAIXAS.get(f, f) for f in df["faixa_etaria"]],
            y=df["qtd_matriculas"],
            marker=dict(color=CORES["primaria"]),
            text=[fmt_compacto(v) for v in df["qtd_matriculas"]],
            textposition="outside",
            textfont=dict(color=CORES["ink_secundaria"]),
            cliponaxis=False,
            customdata=[fmt_pct(100 * v / total) for v in df["qtd_matriculas"]],
            hovertemplate="<b>%{x} anos</b><br>%{y:,.0f} matrículas<br>%{customdata} do total<extra></extra>",
        )
    )
    _estilo_base(fig, 300)
    fig.update_layout(margin=dict(l=4, r=12, t=24, b=4))
    fig.update_yaxes(showgrid=True)
    _eixo_pt(fig, df["qtd_matriculas"].max())
    fig.update_xaxes(showgrid=False, tickfont=dict(color=CORES["ink_secundaria"], size=13))
    return fig


def fig_rede(df: pd.DataFrame) -> go.Figure:
    if df.empty:
        return _figura_vazia()
    fig = go.Figure()
    for rede in ["Pública", "Privada"]:
        pct = 100 * df[rede] / df["Total"]
        fig.add_bar(
            name=rede,
            x=pct,
            y=df["etapa_ensino"],
            orientation="h",
            marker=dict(color=CORES_REDE[rede], line=dict(color=CORES["surface"], width=2)),
            text=[fmt_pct(p) if p >= 10 else "" for p in pct],
            textposition="inside",
            insidetextanchor="middle",
            textfont=dict(color="#ffffff", size=12),
            customdata=[fmt_int(v) for v in df[rede]],
            hovertemplate=f"<b>%{{y}}</b> · {rede}<br>%{{x:.1f}}% (%{{customdata}} matrículas)<extra></extra>",
        )
    _estilo_base(fig, ALTURAS["g-rede"], legenda=True)
    fig.update_layout(barmode="stack", bargap=0.3, barcornerradius=0)
    fig.update_xaxes(range=[0, 100], showgrid=False, showticklabels=False)
    fig.update_yaxes(showgrid=False, tickfont=dict(color=CORES["ink"], size=13))
    return fig


def fig_serie(df: pd.DataFrame, ano) -> go.Figure:
    if df.empty or df["ano_censo"].nunique() < 2:
        return _figura_vazia(300, "A evolução aparece quando houver mais de um ano carregado")
    anos = sorted(df["ano_censo"].unique())
    fig = go.Figure()
    for rede in ["Pública", "Privada"]:
        d = df[df["rede"] == rede].set_index("ano_censo").reindex(anos, fill_value=0)
        fig.add_bar(
            name=rede,
            x=[str(a) for a in anos],
            y=d["qtd_matriculas"],
            marker=dict(
                color=CORES_REDE[rede],
                opacity=[1.0 if a == ano else 0.45 for a in anos],
                line=dict(color=CORES["surface"], width=2),
            ),
            hovertemplate=f"{rede}: %{{y:,.0f}}<extra></extra>",
        )
    _estilo_base(fig, 300, legenda=True)
    fig.update_layout(barmode="stack", hovermode="x unified", bargap=0.45)
    fig.update_xaxes(showgrid=False, type="category")
    _eixo_pt(fig, df.groupby("ano_censo")["qtd_matriculas"].sum().max())
    return fig


# --- Callbacks ---
@app.callback(
    Output("f-uf", "value"),
    Output("f-rede", "value"),
    Input("g-uf", "clickData"),
    Input("btn-limpar", "n_clicks"),
    State("f-uf", "value"),
    prevent_initial_call=True,
)
def filtrar_por_clique(click, _limpar, uf_atual):
    if ctx.triggered_id == "btn-limpar":
        return "TODAS", "TODAS"
    if not click:
        return dash.no_update, dash.no_update
    uf_clicada = click["points"][0]["x"]
    return ("TODAS" if uf_clicada == uf_atual else uf_clicada), dash.no_update


SAIDAS_PAINEL = [
    Output("contexto", "children"),
    Output("kpi-total", "children"),
    Output("kpi-publica", "children"),
    Output("kpi-rural", "children"),
    Output("kpi-municipios", "children"),
    Output("g-uf", "figure"),
    Output("t-uf", "children"),
    Output("g-local", "figure"),
    Output("legenda-local", "children"),
    Output("t-local", "children"),
    Output("g-etapa", "figure"),
    Output("t-etapa", "children"),
    Output("g-idade", "figure"),
    Output("t-idade", "children"),
    Output("g-rede", "figure"),
    Output("t-rede", "children"),
    Output("g-serie", "figure"),
    Output("t-serie", "children"),
    Output("card-serie", "style"),
]


@app.callback(*SAIDAS_PAINEL, Input("f-ano", "value"), Input("f-uf", "value"), Input("f-rede", "value"))
def atualizar_dashboard(ano, uf, rede):
    try:
        d = _agregados(ano, uf, rede)
        kpis = _kpis(d, ano, uf, rede)
    except Exception as erro:
        print(f"[ERRO] Falha ao montar o painel: {erro!r}", flush=True)
        vazio_kpi = [html.Span("—", className="kpi-valor"), html.Span("Dados indisponíveis", className="kpi-det")]
        vazia = _figura_vazia(300, "Dados indisponíveis — veja /saude")
        return (
            "Dados indisponíveis",
            *([vazio_kpi] * 4),
            vazia, None, vazia, [], None, vazia, None, vazia, None, vazia, None, vazia, None,
            {"display": "none"},
        )

    serie = d["serie"]
    return (
        _texto_recorte(ano, uf, rede) + " · fonte INEP",
        *kpis,
        fig_uf(d["por_uf"], uf),
        tabela_html(d["por_uf"], {"uf": "UF", "Urbana": "Urbana", "Rural": "Rural", "Total": "Total"}),
        fig_local(d["por_local"]),
        legenda_local(d["por_local"]),
        tabela_html(d["por_local"], {"localizacao": "Zona", "qtd_matriculas": "Matrículas"}),
        fig_etapa(d["etapa"]),
        tabela_html(d["etapa"], {"etapa_ensino": "Etapa", "qtd_matriculas": "Matrículas"}),
        fig_idade(d["idade"]),
        tabela_html(d["idade"], {"faixa_etaria": "Faixa etária", "qtd_matriculas": "Matrículas"}),
        fig_rede(d["rede_etapa"]),
        tabela_html(
            d["rede_etapa"].sort_values("% Pública", ascending=False),
            {"etapa_ensino": "Etapa", "Pública": "Pública", "Privada": "Privada", "% Pública": "% Pública"},
        ),
        fig_serie(serie, ano),
        tabela_html(serie, {"ano_censo": "Ano", "rede": "Rede", "qtd_matriculas": "Matrículas"}),
        {} if serie["ano_censo"].nunique() > 1 else {"display": "none"},
    )


CHAVES_LEITURA = ["uf", "local", "etapa", "idade", "rede", "serie"]


@app.callback(
    Output("resumo-lista", "children"),
    Output("resumo-origem", "children"),
    *[Output(f"i-{c}", "children") for c in CHAVES_LEITURA],
    Input("f-ano", "value"),
    Input("f-uf", "value"),
    Input("f-rede", "value"),
)
def atualizar_leituras(ano, uf, rede):
    # Callback separado: os gráficos aparecem na hora e os textos da IA chegam depois (1 chamada por recorte).
    try:
        d = _agregados(ano, uf, rede)
    except Exception:
        return [], "Dados indisponíveis", *[""] * len(CHAVES_LEITURA)
    leituras = gerar_leituras(_texto_recorte(ano, uf, rede), _fatos(d, ano, uf, rede))
    origem = (
        "Os 3 achados mais relevantes do recorte, escritos pela IA a partir de números calculados pelo painel."
        if leituras["_origem"] == "ia"
        else "IA indisponível agora — destaques calculados automaticamente pelo painel."
    )
    itens = [html.Li(dcc.Markdown(frase, className="resumo-frase")) for frase in leituras["resumo"]]
    return itens, origem, *[leituras.get(c, "") for c in CHAVES_LEITURA]


@app.callback(
    Output("chat-input", "value", allow_duplicate=True),
    Input({"tipo": "sugestao", "i": dash.ALL}, "n_clicks"),
    prevent_initial_call=True,
)
def usar_sugestao(cliques):
    if not ctx.triggered_id or not any(cliques):
        return dash.no_update
    return SUGESTOES_CHAT[ctx.triggered_id["i"]]


@app.callback(
    Output("chat-historico", "children"),
    Output("chat-input", "value"),
    Output("chat-carregando", "children"),
    Input("chat-enviar", "n_clicks"),
    Input("chat-input", "n_submit"),
    State("chat-input", "value"),
    State("chat-historico", "children"),
    State("f-ano", "value"),
    State("f-uf", "value"),
    State("f-rede", "value"),
    prevent_initial_call=True,
)
def responder_chat(_cliques, _enter, pergunta, historico_atual, ano, uf, rede):
    historico_atual = historico_atual or []
    if not pergunta or not pergunta.strip():
        return historico_atual, "", None

    try:
        texto, df, sql = ai_responder(pergunta.strip(), ano=ano, uf=uf, rede=rede)
    except Exception as erro:  # ex.: arquivo de dados ausente
        texto, df, sql = f"Não foi possível consultar os dados agora ({erro}).", None, None

    resposta = [dcc.Markdown(texto, className="chat-texto")]
    if df is not None and not df.empty:
        resposta.append(html.Div(className="chat-tabela", children=tabela_html(df.head(15), {c: c for c in df.columns})))
    if sql:
        resposta.append(html.Details(className="chat-sql", children=[html.Summary("Ver consulta SQL"), html.Pre(sql)]))

    bloco = html.Div(
        className="chat-bloco",
        children=[html.Div(pergunta, className="chat-pergunta"), html.Div(resposta, className="chat-resposta")],
    )
    return [bloco] + historico_atual, "", None


if __name__ == "__main__":
    debug = os.environ.get("DASH_DEBUG", "0") == "1"
    app.run(debug=debug, host="0.0.0.0", port=int(os.environ.get("PORT", 8050)))
