"""Dashboard público do Censo Escolar (INEP) — Plotly Dash + IA generativa (Gemini).

Rodar localmente:
    python app.py
"""

import os

import dash
import pandas as pd
import plotly.express as px
from dash import Input, Output, State, dcc, html

import db
from ai.chat import responder as ai_responder
from ai.insights import gerar_insight

# --- Paleta validada (ver skill de dataviz / references/palette.md) ---
CORES = {
    "azul": "#2a78d6",
    "laranja": "#eb6834",
    "verde_agua": "#1baf7a",
    "amarelo": "#eda100",
    "ink": "#0b0b0b",
    "ink_secundaria": "#52514e",
    "muted": "#898781",
    "grid": "#e1e0d9",
    "surface": "#fcfcfb",
}
COLORWAY = [CORES["azul"], CORES["laranja"], CORES["verde_agua"], CORES["amarelo"]]
CORES_REDE = {"Pública": CORES["azul"], "Privada": CORES["laranja"], "Não informado": CORES["muted"]}
CORES_LOCAL = {"Urbana": CORES["azul"], "Rural": CORES["laranja"], "Não informado": CORES["muted"]}

TEMPLATE_BASE = dict(
    layout=dict(
        colorway=COLORWAY,
        font=dict(family="system-ui, -apple-system, 'Segoe UI', sans-serif", color=CORES["ink"]),
        plot_bgcolor=CORES["surface"],
        paper_bgcolor=CORES["surface"],
        margin=dict(l=40, r=20, t=50, b=40),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        xaxis=dict(gridcolor=CORES["grid"], zerolinecolor=CORES["grid"]),
        yaxis=dict(gridcolor=CORES["grid"], zerolinecolor=CORES["grid"]),
    )
)

app = dash.Dash(__name__, title="Censo Escolar — Painel Público", suppress_callback_exceptions=True)
server = app.server


def kpi_card(titulo, valor_id):
    return html.Div(
        className="kpi-card",
        children=[
            html.Span(titulo, className="kpi-titulo"),
            html.Span(id=valor_id, className="kpi-valor"),
        ],
    )


def grafico_com_insight(titulo, grafico_id, insight_id):
    return html.Div(
        className="card",
        children=[
            html.H3(titulo),
            dcc.Graph(id=grafico_id, config={"displayModeBar": False}),
            html.P(id=insight_id, className="insight-texto"),
        ],
    )


try:
    ANOS_DISPONIVEIS = db.listar_anos()
    UFS_DISPONIVEIS = db.listar_ufs()
except Exception:
    ANOS_DISPONIVEIS, UFS_DISPONIVEIS = [], []

app.layout = html.Div(
    className="app-container",
    children=[
        html.Header(
            className="app-header",
            children=[
                html.H1("Censo Escolar da Educação Básica"),
                html.P(
                    "Idade, escolaridade e localidade dos alunos matriculados na rede pública e privada do Brasil "
                    "(dados oficiais do INEP, 2019-2023). Painel público e gratuito."
                ),
            ],
        ),
        html.Section(
            className="filtros",
            children=[
                html.Div(
                    className="filtro",
                    children=[
                        html.Label("Ano"),
                        dcc.Dropdown(
                            id="f-ano",
                            options=[{"label": str(a), "value": a} for a in ANOS_DISPONIVEIS],
                            value=max(ANOS_DISPONIVEIS) if ANOS_DISPONIVEIS else None,
                            clearable=False,
                        ),
                    ],
                ),
                html.Div(
                    className="filtro",
                    children=[
                        html.Label("UF"),
                        dcc.Dropdown(
                            id="f-uf",
                            options=[{"label": "Todas", "value": "TODAS"}]
                            + [{"label": u, "value": u} for u in UFS_DISPONIVEIS],
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
            ],
        ),
        html.Section(
            className="kpis",
            children=[
                kpi_card("Total de matrículas", "kpi-total"),
                kpi_card("% rede pública", "kpi-publica"),
                kpi_card("% zona urbana", "kpi-urbana"),
                kpi_card("Municípios com dados", "kpi-municipios"),
            ],
        ),
        html.Section(
            className="graficos-grid",
            children=[
                grafico_com_insight("Matrículas por faixa etária", "g-idade", "i-idade"),
                grafico_com_insight("Matrículas por etapa de ensino", "g-escolaridade", "i-escolaridade"),
                grafico_com_insight("Matrículas por localidade (urbana x rural)", "g-localidade", "i-localidade"),
                grafico_com_insight("Evolução das matrículas (2019-2023)", "g-serie", "i-serie"),
            ],
        ),
        html.Section(
            className="chat-ia",
            children=[
                html.H3("Pergunte à IA sobre os dados"),
                html.P(
                    "Experimente: \"qual UF tem mais matrículas rurais em 2023?\" ou "
                    "\"como evoluiu a rede privada desde 2019?\"",
                    className="chat-dica",
                ),
                html.Div(id="chat-historico", className="chat-historico"),
                html.Div(
                    className="chat-input-row",
                    children=[
                        dcc.Input(id="chat-input", type="text", placeholder="Digite sua pergunta...", debounce=False),
                        html.Button("Perguntar", id="chat-enviar", n_clicks=0),
                    ],
                ),
                dcc.Loading(html.Div(id="chat-loading-anchor"), type="dot"),
            ],
        ),
        html.Footer(
            className="app-footer",
            children=[
                html.P("Fonte: INEP — Microdados do Censo Escolar da Educação Básica. Dados agregados, sem identificação individual."),
            ],
        ),
    ],
)


def _filtrar(df: pd.DataFrame, ano, uf, rede) -> pd.DataFrame:
    out = df[df["ano_censo"] == ano] if ano is not None else df
    if uf and uf != "TODAS" and "uf" in out.columns:
        out = out[out["uf"] == uf]
    if rede and rede != "TODAS" and "rede" in out.columns:
        out = out[out["rede"] == rede]
    return out


@app.callback(
    Output("kpi-total", "children"),
    Output("kpi-publica", "children"),
    Output("kpi-urbana", "children"),
    Output("kpi-municipios", "children"),
    Output("g-idade", "figure"),
    Output("i-idade", "children"),
    Output("g-escolaridade", "figure"),
    Output("i-escolaridade", "children"),
    Output("g-localidade", "figure"),
    Output("i-localidade", "children"),
    Output("g-serie", "figure"),
    Output("i-serie", "children"),
    Input("f-ano", "value"),
    Input("f-uf", "value"),
    Input("f-rede", "value"),
)
def atualizar_dashboard(ano, uf, rede):
    resumo = _filtrar(db.carregar_tabela("diamond_resumo_geral"), ano, None, None)
    total = int(resumo["total_matriculas"].sum()) if not resumo.empty else 0
    pct_publica = (
        100 * resumo["total_rede_publica"].sum() / resumo["total_matriculas"].sum() if total else 0
    )
    pct_urbana = 100 * resumo["total_urbana"].sum() / resumo["total_matriculas"].sum() if total else 0
    qtd_municipios = int(resumo["qtd_municipios"].sum()) if not resumo.empty else 0

    df_idade = _filtrar(db.carregar_tabela("diamond_por_idade"), ano, uf, rede)
    fig_idade = px.bar(
        df_idade.groupby("faixa_etaria", as_index=False)["qtd_matriculas"].sum().sort_values("faixa_etaria"),
        x="faixa_etaria",
        y="qtd_matriculas",
        labels={"faixa_etaria": "Faixa etária", "qtd_matriculas": "Matrículas"},
        template=None,
    )
    fig_idade.update_traces(marker_color=CORES["azul"])
    fig_idade.update_layout(**TEMPLATE_BASE["layout"])

    df_escolaridade = _filtrar(db.carregar_tabela("diamond_por_escolaridade"), ano, uf, rede)
    fig_escolaridade = px.bar(
        df_escolaridade.groupby("etapa_ensino", as_index=False)["qtd_matriculas"]
        .sum()
        .sort_values("qtd_matriculas", ascending=True),
        x="qtd_matriculas",
        y="etapa_ensino",
        orientation="h",
        labels={"etapa_ensino": "Etapa de ensino", "qtd_matriculas": "Matrículas"},
    )
    fig_escolaridade.update_traces(marker_color=CORES["azul"])
    fig_escolaridade.update_layout(**TEMPLATE_BASE["layout"])

    df_localidade = _filtrar(db.carregar_tabela("diamond_por_localidade"), ano, uf, rede)
    agg_local = df_localidade.groupby("localizacao", as_index=False)["qtd_matriculas"].sum()
    fig_localidade = px.pie(
        agg_local,
        names="localizacao",
        values="qtd_matriculas",
        color="localizacao",
        color_discrete_map=CORES_LOCAL,
        hole=0.5,
    )
    fig_localidade.update_layout(**TEMPLATE_BASE["layout"])

    df_serie = db.carregar_tabela("diamond_serie_temporal")
    if uf and uf != "TODAS":
        df_serie = df_serie[df_serie["uf"] == uf]
    if rede and rede != "TODAS":
        df_serie = df_serie[df_serie["rede"] == rede]
    agg_serie = df_serie.groupby(["ano_censo", "rede"], as_index=False)["qtd_matriculas"].sum()
    fig_serie = px.line(
        agg_serie.sort_values("ano_censo"),
        x="ano_censo",
        y="qtd_matriculas",
        color="rede",
        color_discrete_map=CORES_REDE,
        markers=True,
        labels={"ano_censo": "Ano", "qtd_matriculas": "Matrículas", "rede": "Rede"},
    )
    fig_serie.update_layout(**TEMPLATE_BASE["layout"])

    insight_idade = gerar_insight(df_idade, "Matrículas por faixa etária")
    insight_escolaridade = gerar_insight(df_escolaridade, "Matrículas por etapa de ensino")
    insight_localidade = gerar_insight(df_localidade, "Matrículas por localidade urbana/rural")
    insight_serie = gerar_insight(agg_serie, "Evolução das matrículas 2019-2023")

    return (
        f"{total:,}".replace(",", "."),
        f"{pct_publica:.1f}%",
        f"{pct_urbana:.1f}%",
        f"{qtd_municipios:,}".replace(",", "."),
        fig_idade,
        insight_idade,
        fig_escolaridade,
        insight_escolaridade,
        fig_localidade,
        insight_localidade,
        fig_serie,
        insight_serie,
    )


@app.callback(
    Output("chat-historico", "children"),
    Output("chat-input", "value"),
    Input("chat-enviar", "n_clicks"),
    State("chat-input", "value"),
    State("chat-historico", "children"),
    prevent_initial_call=True,
)
def responder_chat(n_clicks, pergunta, historico_atual):
    historico_atual = historico_atual or []
    if not pergunta:
        return historico_atual, ""

    texto_resposta, df_resultado = ai_responder(pergunta)

    bloco = html.Div(
        className="chat-bloco",
        children=[
            html.Div(pergunta, className="chat-pergunta"),
            html.Div(texto_resposta, className="chat-resposta"),
        ],
    )
    return historico_atual + [bloco], ""


if __name__ == "__main__":
    debug = os.environ.get("DASH_DEBUG", "0") == "1"
    app.run(debug=debug, host="0.0.0.0", port=int(os.environ.get("PORT", 8050)))
