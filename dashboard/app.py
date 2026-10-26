"""Dashboard público do Censo Escolar (INEP) — Plotly Dash + IA generativa (Gemini).

Rodar localmente:
    python app.py
"""

import os

import dash
import pandas as pd
import plotly.graph_objects as go
from dash import Input, Output, State, ctx, dcc, html

import db
from ai.chat import responder as ai_responder
from ai.insights import gerar_insight

# --- Paleta validada (ver skill de dataviz / references/palette.md) ---
CORES = {
    "azul": "#2a78d6",
    "laranja": "#eb6834",
    "verde_agua": "#1baf7a",
    "ink": "#0b0b0b",
    "ink_secundaria": "#52514e",
    "muted": "#898781",
    "grid": "#e8e7e1",
    "surface": "#ffffff",
}
CORES_REDE = {"Pública": CORES["azul"], "Privada": CORES["laranja"]}
CORES_LOCAL = {"Urbana": CORES["azul"], "Rural": CORES["laranja"]}

ORDEM_FAIXAS = ["0-3", "4-5", "6-10", "11-14", "15-17", "18+"]
NOMES_FAIXAS = {"0-3": "0–3", "4-5": "4–5", "6-10": "6–10", "11-14": "11–14", "15-17": "15–17", "18+": "18+"}

FONTE = "Inter, system-ui, -apple-system, 'Segoe UI', sans-serif"

SUGESTOES_CHAT = [
    "Qual UF tem mais matrículas na zona rural?",
    "Quantos alunos com 18 anos ou mais estão na rede privada?",
    "Quais os 5 municípios com mais matrículas?",
    "Qual a participação da rede pública no Ensino Médio?",
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


def fmt_pct(valor) -> str:
    return f"{valor:.1f}%".replace(".", ",")


def fmt_compacto(valor) -> str:
    for limite, sufixo in ((1e9, " bi"), (1e6, " mi"), (1e3, " mil")):
        if abs(valor) >= limite:
            return f"{valor / limite:.1f}".replace(".", ",").replace(",0", "") + sufixo
    return fmt_int(valor)


# --- Componentes de layout ---
def stat_tile(titulo, valor_id, detalhe_id, com_medidor=False):
    filhos = [
        html.Span(titulo, className="stat-titulo"),
        html.Span(id=valor_id, className="stat-valor"),
    ]
    if com_medidor:
        filhos.append(html.Div(className="medidor", children=html.Div(id=f"{valor_id}-medidor", className="medidor-fill")))
    filhos.append(html.Span(id=detalhe_id, className="stat-detalhe"))
    return html.Div(className="stat-tile", children=filhos)


def card_grafico(titulo, subtitulo, grafico_id, insight_id, tabela_id, classe_extra=""):
    return html.Article(
        className=f"card {classe_extra}".strip(),
        children=[
            html.Header(
                className="card-header",
                children=[html.H3(titulo), html.P(subtitulo, className="card-sub")],
            ),
            dcc.Loading(
                type="circle",
                color=CORES["azul"],
                delay_show=300,
                children=dcc.Graph(
                    id=grafico_id,
                    config={"displayModeBar": False, "responsive": True},
                    className="grafico",
                ),
            ),
            html.Div(
                className="insight",
                children=[
                    html.Span("✦ Leitura da IA", className="insight-rotulo"),
                    dcc.Loading(
                        type="dot",
                        color=CORES["azul"],
                        children=html.P(id=insight_id, className="insight-texto"),
                    ),
                ],
            ),
            html.Details(
                className="tabela-dados",
                children=[html.Summary("Ver dados em tabela"), html.Div(id=tabela_id)],
            ),
        ],
    )


def secao(titulo, descricao, filhos):
    return html.Section(
        className="secao",
        children=[
            html.Div(className="secao-cabecalho", children=[html.H2(titulo), html.P(descricao)]),
            *filhos,
        ],
    )


def tabela_html(df: pd.DataFrame, colunas: dict):
    """Tabela acessível (alternativa ao gráfico). `colunas` mapeia coluna -> rótulo."""
    if df.empty:
        return html.P("Sem dados para os filtros selecionados.", className="vazio")
    cabecalho = html.Thead(html.Tr([html.Th(rotulo) for rotulo in colunas.values()]))
    linhas = []
    for _, linha in df.iterrows():
        celulas = []
        for coluna in colunas:
            valor = linha[coluna]
            numerico = isinstance(valor, (int, float)) and not isinstance(valor, bool)
            celulas.append(html.Td(fmt_int(valor) if numerico else str(valor), className="num" if numerico else None))
        linhas.append(html.Tr(celulas))
    return html.Table(className="tabela", children=[cabecalho, html.Tbody(linhas)])


def montar_layout():
    # Função (não valor fixo): se o banco falhar no boot, cada recarga da página tenta de novo.
    try:
        anos = db.listar_anos()
        ufs = db.listar_ufs()
        erro_banco = None
    except Exception as erro:
        print(f"[ERRO] Falha ao carregar anos/UFs do Supabase: {erro!r}", flush=True)
        anos, ufs, erro_banco = [], [], erro

    periodo = f"{min(anos)}–{max(anos)}" if len(anos) > 1 else (str(anos[0]) if anos else "")

    return html.Div(
        className="pagina",
        children=[
            html.Div(
                className="topo",
                children=html.Div(
                    className="topo-conteudo",
                    children=[
                        html.Div(
                            className="marca",
                            children=[
                                html.Span("CE", className="marca-logo"),
                                html.Div(
                                    [
                                        html.Strong("Censo Escolar"),
                                        html.Span(f"Painel público · INEP {periodo}".strip(), className="marca-sub"),
                                    ]
                                ),
                            ],
                        ),
                        html.Div(
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
                                        ),
                                    ],
                                ),
                                html.Div(
                                    className="filtro filtro-uf",
                                    children=[
                                        html.Label("Estado", htmlFor="f-uf"),
                                        dcc.Dropdown(
                                            id="f-uf",
                                            options=[{"label": "Brasil (todas)", "value": "TODAS"}]
                                            + [{"label": u, "value": u} for u in ufs],
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
                                html.Button("Limpar", id="btn-limpar", className="btn-limpar", n_clicks=0),
                            ],
                        ),
                    ],
                ),
            ),
            html.Main(
                className="conteudo",
                children=[
                    html.Div(
                        className="alerta",
                        children=[
                            html.Strong("Não foi possível conectar ao banco de dados. "),
                            "Verifique a variável SUPABASE_DB_URL e abra /saude para ver o erro.",
                        ],
                    )
                    if erro_banco
                    else None,
                    html.Section(
                        className="hero",
                        children=[
                            html.Div(
                                className="hero-principal",
                                children=[
                                    html.Span(id="hero-contexto", className="hero-contexto"),
                                    html.Div(id="hero-valor", className="hero-valor"),
                                    html.P(id="hero-frase", className="hero-frase"),
                                ],
                            ),
                            html.Div(
                                className="hero-stats",
                                children=[
                                    stat_tile("Rede pública", "kpi-publica", "kpi-publica-det", com_medidor=True),
                                    stat_tile("Zona urbana", "kpi-urbana", "kpi-urbana-det", com_medidor=True),
                                    stat_tile("Municípios com matrículas", "kpi-municipios", "kpi-municipios-det"),
                                ],
                            ),
                        ],
                    ),
                    secao(
                        "Quem são os alunos",
                        "Idade e etapa de ensino das matrículas no recorte selecionado.",
                        [
                            html.Div(
                                className="grade-2",
                                children=[
                                    card_grafico(
                                        "Matrículas por faixa etária",
                                        "Idade do aluno em anos",
                                        "g-idade",
                                        "i-idade",
                                        "t-idade",
                                    ),
                                    card_grafico(
                                        "Matrículas por etapa de ensino",
                                        "Total e participação de cada etapa",
                                        "g-escolaridade",
                                        "i-escolaridade",
                                        "t-escolaridade",
                                    ),
                                ],
                            )
                        ],
                    ),
                    secao(
                        "Onde estudam",
                        "Clique em um estado no gráfico para filtrar o painel inteiro por ele.",
                        [
                            card_grafico(
                                "Matrículas por estado, zona urbana e rural",
                                "Estados ordenados pelo total de matrículas",
                                "g-uf",
                                "i-uf",
                                "t-uf",
                                classe_extra="card-largo",
                            )
                        ],
                    ),
                    secao(
                        "Rede pública e privada",
                        "Quanto de cada etapa é atendido pela rede pública (não usa o filtro de rede).",
                        [
                            card_grafico(
                                "Participação da rede por etapa de ensino",
                                "% das matrículas de cada etapa",
                                "g-rede",
                                "i-rede",
                                "t-rede",
                                classe_extra="card-largo",
                            )
                        ],
                    ),
                    html.Div(
                        id="secao-serie",
                        style={"display": "block" if len(anos) > 1 else "none"},
                        children=secao(
                            "Evolução no tempo",
                            "Matrículas por ano e rede.",
                            [
                                card_grafico(
                                    f"Evolução das matrículas ({periodo})",
                                    "Total por ano",
                                    "g-serie",
                                    "i-serie",
                                    "t-serie",
                                    classe_extra="card-largo",
                                )
                            ],
                        ),
                    ),
                    html.Section(
                        className="secao chat",
                        children=[
                            html.Div(
                                className="secao-cabecalho",
                                children=[
                                    html.H2("Pergunte aos dados"),
                                    html.P(
                                        "A IA transforma sua pergunta em uma consulta segura (somente leitura) "
                                        "às tabelas do Censo e mostra o resultado."
                                    ),
                                ],
                            ),
                            html.Div(
                                className="chat-caixa",
                                children=[
                                    html.Div(
                                        className="chat-sugestoes",
                                        children=[
                                            html.Button(s, id={"tipo": "sugestao", "i": i}, className="chip", n_clicks=0)
                                            for i, s in enumerate(SUGESTOES_CHAT)
                                        ],
                                    ),
                                    html.Div(id="chat-historico", className="chat-historico"),
                                    dcc.Loading(type="dot", color=CORES["azul"], children=html.Div(id="chat-carregando")),
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
                                            html.Button("Perguntar", id="chat-enviar", n_clicks=0, className="btn-primario"),
                                        ],
                                    ),
                                ],
                            ),
                        ],
                    ),
                ],
            ),
            html.Footer(
                className="rodape",
                children=[
                    html.P(
                        "Fonte: INEP — Microdados do Censo Escolar da Educação Básica. "
                        "Dados agregados, sem identificação individual."
                    ),
                    html.P("Os textos marcados com ✦ são gerados por IA e podem conter imprecisões."),
                ],
            ),
        ],
    )


app.layout = montar_layout


# --- Dados ---
def _filtrar(df: pd.DataFrame, ano, uf, rede) -> pd.DataFrame:
    out = df[df["ano_censo"] == ano] if ano is not None else df
    if uf and uf != "TODAS" and "uf" in out.columns:
        out = out[out["uf"] == uf]
    if rede and rede != "TODAS" and "rede" in out.columns:
        out = out[out["rede"] == rede]
    return out


def _agregados(ano, uf, rede) -> dict:
    idade = (
        _filtrar(db.carregar_tabela("diamond_por_idade"), ano, uf, rede)
        .groupby("faixa_etaria", as_index=False)["qtd_matriculas"]
        .sum()
    )
    idade["ordem"] = idade["faixa_etaria"].map({f: i for i, f in enumerate(ORDEM_FAIXAS)})
    idade = idade.sort_values("ordem").drop(columns="ordem")

    etapa = (
        _filtrar(db.carregar_tabela("diamond_por_escolaridade"), ano, uf, rede)
        .groupby("etapa_ensino", as_index=False)["qtd_matriculas"]
        .sum()
        .sort_values("qtd_matriculas", ascending=False)
    )

    # Por UF: não filtra por UF (mostra todas e destaca a selecionada)
    local_uf = _filtrar(db.carregar_tabela("diamond_por_localidade"), ano, None, rede)
    por_uf = (
        local_uf[local_uf["localizacao"].isin(["Urbana", "Rural"])]
        .pivot_table(index="uf", columns="localizacao", values="qtd_matriculas", aggfunc="sum", fill_value=0)
        .reindex(columns=["Urbana", "Rural"], fill_value=0)
        .reset_index()
    )
    por_uf["Total"] = por_uf["Urbana"] + por_uf["Rural"]
    por_uf = por_uf.sort_values("Total", ascending=False)

    # Rede por etapa: não filtra por rede (é o próprio corte)
    rede_etapa = (
        _filtrar(db.carregar_tabela("diamond_por_escolaridade"), ano, uf, None)
        .pivot_table(index="etapa_ensino", columns="rede", values="qtd_matriculas", aggfunc="sum", fill_value=0)
        .reindex(columns=["Pública", "Privada"], fill_value=0)
        .reset_index()
    )
    rede_etapa["Total"] = rede_etapa["Pública"] + rede_etapa["Privada"]
    rede_etapa = rede_etapa[rede_etapa["Total"] > 0]
    rede_etapa["% Pública"] = 100 * rede_etapa["Pública"] / rede_etapa["Total"]
    rede_etapa = rede_etapa.sort_values("% Pública")

    serie = db.carregar_tabela("diamond_serie_temporal")
    serie = _filtrar(serie, None, uf, rede).groupby(["ano_censo", "rede"], as_index=False)["qtd_matriculas"].sum()

    # KPIs a partir da tabela de localidade (respeita ano, UF e rede)
    local = _filtrar(db.carregar_tabela("diamond_por_localidade"), ano, uf, rede)
    local_sem_rede = _filtrar(db.carregar_tabela("diamond_por_localidade"), ano, uf, None)
    total = float(local["qtd_matriculas"].sum())
    kpis = {
        "total": total,
        "urbana": float(local.loc[local["localizacao"] == "Urbana", "qtd_matriculas"].sum()),
        "rural": float(local.loc[local["localizacao"] == "Rural", "qtd_matriculas"].sum()),
        "municipios": int(local.loc[local["qtd_matriculas"] > 0, "co_municipio"].nunique()),
        "total_sem_rede": float(local_sem_rede["qtd_matriculas"].sum()),
        "publica": float(local_sem_rede.loc[local_sem_rede["rede"] == "Pública", "qtd_matriculas"].sum()),
    }
    return {"idade": idade, "etapa": etapa, "por_uf": por_uf, "rede_etapa": rede_etapa, "serie": serie, "kpis": kpis}


# --- Gráficos ---
def _estilo_base(fig: go.Figure, altura: int, legenda=False) -> go.Figure:
    fig.update_layout(
        height=altura,
        margin=dict(l=4, r=12, t=36 if legenda else 12, b=4),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family=FONTE, size=12, color=CORES["ink_secundaria"]),
        separators=",.",
        showlegend=legenda,
        legend=dict(
            orientation="h",
            x=0,
            y=1.02,
            yanchor="bottom",
            xanchor="left",
            traceorder="normal",
            font=dict(color=CORES["ink"]),
            title=None,
        ),
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


def _figura_vazia(altura=300) -> go.Figure:
    fig = go.Figure()
    fig.add_annotation(text="Sem dados para os filtros selecionados", showarrow=False, font=dict(size=14, color=CORES["muted"]))
    _estilo_base(fig, altura)
    fig.update_xaxes(visible=False)
    fig.update_yaxes(visible=False)
    return fig


def fig_idade(df: pd.DataFrame) -> go.Figure:
    if df.empty:
        return _figura_vazia()
    total = df["qtd_matriculas"].sum()
    rotulos = [NOMES_FAIXAS.get(f, f) for f in df["faixa_etaria"]]
    fig = go.Figure(
        go.Bar(
            x=rotulos,
            y=df["qtd_matriculas"],
            marker=dict(color=CORES["azul"]),
            text=[fmt_compacto(v) for v in df["qtd_matriculas"]],
            textposition="outside",
            textfont=dict(color=CORES["ink_secundaria"]),
            cliponaxis=False,
            customdata=[fmt_pct(100 * v / total) for v in df["qtd_matriculas"]],
            hovertemplate="<b>%{x} anos</b><br>%{y:,.0f} matrículas<br>%{customdata} do total<extra></extra>",
        )
    )
    _estilo_base(fig, 320)
    fig.update_yaxes(tickformat="~s", showgrid=True)
    fig.update_xaxes(showgrid=False, tickfont=dict(color=CORES["ink_secundaria"], size=13))
    return fig


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
            marker=dict(color=CORES["azul"]),
            text=[f"{fmt_compacto(v)} · {fmt_pct(100 * v / total)}" for v in df["qtd_matriculas"]],
            textposition="outside",
            textfont=dict(color=CORES["ink_secundaria"]),
            cliponaxis=False,
            hovertemplate="<b>%{y}</b><br>%{x:,.0f} matrículas<extra></extra>",
        )
    )
    _estilo_base(fig, 320)
    fig.update_layout(margin=dict(l=4, r=96, t=12, b=4))
    fig.update_xaxes(tickformat="~s", showgrid=True)
    fig.update_yaxes(showgrid=False, tickfont=dict(color=CORES["ink"], size=13))
    return fig


def fig_uf(df: pd.DataFrame, uf_selecionada) -> go.Figure:
    if df.empty:
        return _figura_vazia(380)
    destaque = uf_selecionada and uf_selecionada != "TODAS"
    opacidade = [1.0 if (not destaque or u == uf_selecionada) else 0.28 for u in df["uf"]]
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
    _estilo_base(fig, 380, legenda=True)
    fig.update_layout(barmode="stack", bargap=0.25, hovermode="closest")
    fig.update_yaxes(tickformat="~s")
    fig.update_xaxes(showgrid=False, tickfont=dict(color=CORES["ink_secundaria"], size=12))
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
    _estilo_base(fig, 60 + 46 * len(df), legenda=True)
    fig.update_layout(barmode="stack", bargap=0.3, barcornerradius=0)
    fig.update_xaxes(range=[0, 100], ticksuffix="%", showgrid=False, showticklabels=False)
    fig.update_yaxes(showgrid=False, tickfont=dict(color=CORES["ink"], size=13))
    return fig


def fig_serie(df: pd.DataFrame) -> go.Figure:
    if df.empty or df["ano_censo"].nunique() < 2:
        return _figura_vazia()
    fig = go.Figure()
    for rede in ["Pública", "Privada"]:
        d = df[df["rede"] == rede].sort_values("ano_censo")
        fig.add_scatter(
            name=rede,
            x=d["ano_censo"],
            y=d["qtd_matriculas"],
            mode="lines+markers",
            line=dict(color=CORES_REDE[rede], width=2),
            marker=dict(size=8, color=CORES_REDE[rede], line=dict(color=CORES["surface"], width=2)),
            hovertemplate=f"{rede}: %{{y:,.0f}}<extra></extra>",
        )
    _estilo_base(fig, 320, legenda=True)
    fig.update_layout(hovermode="x unified")
    fig.update_xaxes(dtick=1, showgrid=False)
    fig.update_yaxes(tickformat="~s")
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


@app.callback(
    Output("hero-contexto", "children"),
    Output("hero-valor", "children"),
    Output("hero-frase", "children"),
    Output("kpi-publica", "children"),
    Output("kpi-publica-medidor", "style"),
    Output("kpi-publica-det", "children"),
    Output("kpi-urbana", "children"),
    Output("kpi-urbana-medidor", "style"),
    Output("kpi-urbana-det", "children"),
    Output("kpi-municipios", "children"),
    Output("kpi-municipios-det", "children"),
    Output("g-idade", "figure"),
    Output("t-idade", "children"),
    Output("g-escolaridade", "figure"),
    Output("t-escolaridade", "children"),
    Output("g-uf", "figure"),
    Output("t-uf", "children"),
    Output("g-rede", "figure"),
    Output("t-rede", "children"),
    Output("g-serie", "figure"),
    Output("t-serie", "children"),
    Input("f-ano", "value"),
    Input("f-uf", "value"),
    Input("f-rede", "value"),
)
def atualizar_dashboard(ano, uf, rede):
    dados = _agregados(ano, uf, rede)
    k = dados["kpis"]

    lugar = "no Brasil" if not uf or uf == "TODAS" else f"em {uf}"
    recorte_rede = "" if not rede or rede == "TODAS" else f" da rede {rede.lower()}"
    lugar_titulo = lugar[0].upper() + lugar[1:]
    contexto = f"{lugar_titulo} · {ano}" if ano else lugar_titulo
    frase = (
        f"matrículas{recorte_rede} na educação básica {lugar}"
        + (f" em {ano}" if ano else "")
        + (f", em {fmt_int(k['municipios'])} municípios." if k["municipios"] else ".")
    )

    pct_publica = 100 * k["publica"] / k["total_sem_rede"] if k["total_sem_rede"] else 0
    pct_urbana = 100 * k["urbana"] / k["total"] if k["total"] else 0

    idade, etapa, por_uf, rede_etapa, serie = (
        dados["idade"],
        dados["etapa"],
        dados["por_uf"],
        dados["rede_etapa"],
        dados["serie"],
    )

    return (
        contexto,
        fmt_int(k["total"]),
        frase,
        fmt_pct(pct_publica),
        {"width": f"{pct_publica:.1f}%"},
        f"{fmt_compacto(k['publica'])} de matrículas públicas",
        fmt_pct(pct_urbana),
        {"width": f"{pct_urbana:.1f}%"},
        f"{fmt_compacto(k['rural'])} na zona rural",
        fmt_int(k["municipios"]),
        "de 5.570 municípios do país" if not uf or uf == "TODAS" else f"no estado de {uf}",
        fig_idade(idade),
        tabela_html(idade, {"faixa_etaria": "Faixa etária", "qtd_matriculas": "Matrículas"}),
        fig_etapa(etapa),
        tabela_html(etapa, {"etapa_ensino": "Etapa", "qtd_matriculas": "Matrículas"}),
        fig_uf(por_uf, uf),
        tabela_html(por_uf, {"uf": "UF", "Urbana": "Urbana", "Rural": "Rural", "Total": "Total"}),
        fig_rede(rede_etapa),
        tabela_html(
            rede_etapa.sort_values("% Pública", ascending=False),
            {"etapa_ensino": "Etapa", "Pública": "Pública", "Privada": "Privada", "Total": "Total"},
        ),
        fig_serie(serie),
        tabela_html(serie, {"ano_censo": "Ano", "rede": "Rede", "qtd_matriculas": "Matrículas"}),
    )


@app.callback(
    Output("i-idade", "children"),
    Output("i-escolaridade", "children"),
    Output("i-uf", "children"),
    Output("i-rede", "children"),
    Output("i-serie", "children"),
    Input("f-ano", "value"),
    Input("f-uf", "value"),
    Input("f-rede", "value"),
)
def atualizar_insights(ano, uf, rede):
    # Callback separado: os gráficos aparecem na hora e os textos da IA chegam depois.
    dados = _agregados(ano, uf, rede)
    recorte = f"ano {ano}, UF {uf}, rede {rede}"
    serie = dados["serie"]
    return (
        gerar_insight(dados["idade"], f"Matrículas por faixa etária ({recorte})"),
        gerar_insight(dados["etapa"], f"Matrículas por etapa de ensino ({recorte})"),
        gerar_insight(dados["por_uf"].head(27), f"Matrículas por UF, urbana x rural (ano {ano}, rede {rede})"),
        gerar_insight(dados["rede_etapa"], f"Participação da rede pública x privada por etapa (ano {ano}, UF {uf})"),
        gerar_insight(serie, "Evolução das matrículas por ano") if serie["ano_censo"].nunique() > 1 else "",
    )


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
    prevent_initial_call=True,
)
def responder_chat(_cliques, _enter, pergunta, historico_atual):
    historico_atual = historico_atual or []
    if not pergunta or not pergunta.strip():
        return historico_atual, "", None

    texto_resposta, df_resultado = ai_responder(pergunta.strip())

    resposta = [html.P(texto_resposta)]
    if df_resultado is not None and not df_resultado.empty:
        resposta.append(tabela_html(df_resultado.head(10), {c: c for c in df_resultado.columns}))

    bloco = html.Div(
        className="chat-bloco",
        children=[
            html.Div(pergunta, className="chat-pergunta"),
            html.Div(resposta, className="chat-resposta"),
        ],
    )
    return [bloco] + historico_atual, "", None


if __name__ == "__main__":
    debug = os.environ.get("DASH_DEBUG", "0") == "1"
    app.run(debug=debug, host="0.0.0.0", port=int(os.environ.get("PORT", 8050)))
