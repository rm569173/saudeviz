"""
SaudeViz — Painel inteligente de acesso hospitalar e perfil de atendimento.

Challenge FIAP x Oracle 2026 · 1TSCOA
Lucas Ventura Araujo Ribas Colen — RM 569173

Execucao local:
    streamlit run app/streamlit_app.py

O painel consulta o Oracle Database da FIAP ao vivo e cai para o retrato em
parquet se o banco estiver indisponivel. O modo em uso aparece na barra
lateral - dado de contingencia nunca se passa por dado ao vivo.

Cinco paginas: visao geral, capacidade hospitalar, perfis de atendimento,
previsao de demanda e o tradutor de linguagem natural para SQL.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from app import dados, tema  # noqa: E402
from src.selectai import nl2sql  # noqa: E402

st.set_page_config(
    page_title="SaúdeViz — Painel de Acesso Hospitalar",
    page_icon="🏥",
    layout="wide",
    initial_sidebar_state="expanded",
)

UFS_DISPONIVEIS = ["ES", "MG", "RJ", "SP"]
NOMES_UF = {"ES": "Espírito Santo", "MG": "Minas Gerais",
            "RJ": "Rio de Janeiro", "SP": "São Paulo"}
NOMES_MES = ["Jan", "Fev", "Mar", "Abr", "Mai", "Jun",
             "Jul", "Ago", "Set", "Out", "Nov", "Dez"]


# ---------------------------------------------------------------------------
# Barra lateral
# ---------------------------------------------------------------------------

def barra_lateral() -> tuple[str, tuple[str, ...]]:
    st.sidebar.title("🏥 SaúdeViz")
    st.sidebar.caption("Dados que salvam vidas. Decisões que transformam o "
                       "sistema de saúde.")

    pagina = st.sidebar.radio(
        "Navegação",
        ["Visão geral",
         "Capacidade hospitalar",
         "Perfis de atendimento",
         "Previsão de demanda",
         "Pergunte em português"],
        label_visibility="collapsed",
    )

    st.sidebar.divider()
    ufs = st.sidebar.multiselect(
        "Unidades federativas", UFS_DISPONIVEIS, default=UFS_DISPONIVEIS,
        format_func=lambda uf: f"{uf} — {NOMES_UF[uf]}")

    st.sidebar.divider()
    modo, detalhe = dados.modo_conexao()
    if modo == "oracle":
        st.sidebar.success("**Conectado ao Oracle**", icon="🟢")
        st.sidebar.caption(detalhe)
    else:
        st.sidebar.warning("**Modo contingência**", icon="🟡")
        st.sidebar.caption(
            f"O painel está lendo o retrato local em parquet, não o banco.\n\n"
            f"Motivo: {detalhe}")

    st.sidebar.divider()
    st.sidebar.caption(
        "**Challenge FIAP × Oracle 2026**  \n"
        "1TSCOA · Lucas Ventura Araujo Ribas Colen — RM 569173  \n"
        "Fontes: SIH/SUS, CNES e IBGE · Sudeste, 2024")

    return pagina, tuple(ufs)


def exige_uf(ufs: tuple[str, ...]) -> bool:
    if not ufs:
        st.info("Selecione ao menos uma unidade federativa na barra lateral.")
        return False
    return True


# ---------------------------------------------------------------------------
# Visão geral
# ---------------------------------------------------------------------------

def pagina_visao_geral(ufs: tuple[str, ...]) -> None:
    st.title("Visão geral")
    st.caption("Internações do SIH/SUS ocorridas em 2024 na região Sudeste, "
               "pela data real de internação.")

    indicadores = dados.indicadores_gerais(ufs)
    if not indicadores:
        st.warning("Sem dados para a seleção atual.")
        return

    colunas = st.columns(5)
    colunas[0].metric("Internações",
                      tema.formata_milhar(indicadores["internacoes"]))
    colunas[1].metric("Valor pago",
                      tema.formata_reais(indicadores["valor_total"]))
    colunas[2].metric("Permanência média",
                      f"{indicadores['permanencia_media']:.2f} dias".replace(".", ","))
    colunas[3].metric("Taxa de mortalidade",
                      f"{indicadores['taxa_mortalidade']:.2f}%".replace(".", ","))
    colunas[4].metric("Taxa de transferência",
                      f"{indicadores['taxa_transferencia']:.2f}%".replace(".", ","))

    st.divider()

    esquerda, direita = st.columns([3, 2])

    with esquerda:
        st.subheader("Internações por mês de internação")
        fato = dados.carrega("fato_internacao_mensal")
        fato = fato[fato["uf"].isin(ufs)]
        mensal = (fato.groupby(["uf", "mes"], as_index=False)["internacoes"]
                  .sum().sort_values("mes"))

        figura = go.Figure()
        for uf in [u for u in UFS_DISPONIVEIS if u in ufs]:
            serie = mensal[mensal["uf"] == uf]
            figura.add_trace(go.Scatter(
                x=[NOMES_MES[int(m) - 1] for m in serie["mes"]],
                y=serie["internacoes"],
                name=uf,
                mode="lines+markers",
                line={"width": 2, "color": tema.COR_UF[uf]},
                marker={"size": 8, "color": tema.COR_UF[uf]},
                hovertemplate=f"<b>{uf}</b> %{{x}}<br>"
                              "%{y:,.0f} internações<extra></extra>",
            ))
        figura.update_layout(**tema.layout_base(altura=380))
        st.plotly_chart(figura, width="stretch")
        st.caption("O eixo de tempo é a **data de internação**, não a "
                   "competência de pagamento do SIH — que arrasta cerca de 42% "
                   "de registros de meses anteriores.")

    with direita:
        st.subheader("Total de internações por estado em 2024")
        resumo = (fato.groupby("uf", as_index=False)
                  .agg(internacoes=("internacoes", "sum"),
                       dias=("dias_permanencia", "sum"),
                       obitos=("obitos", "sum"),
                       valor=("valor_total", "sum")))
        resumo["permanencia"] = (resumo["dias"] / resumo["internacoes"]).round(2)
        resumo["mortalidade"] = (
            100 * resumo["obitos"] / resumo["internacoes"]).round(2)
        resumo["custo"] = (resumo["valor"] / resumo["internacoes"]).round(2)
        resumo = resumo.sort_values("internacoes", ascending=True)

        figura = go.Figure(go.Bar(
            x=resumo["internacoes"],
            y=resumo["uf"],
            orientation="h",
            marker={"color": [tema.COR_UF[uf] for uf in resumo["uf"]]},
            text=[tema.formata_milhar(v) for v in resumo["internacoes"]],
            # "inside" evita que o rotulo seja cortado na borda do grafico,
            # problema que "outside" causa quando a barra ocupa quase toda a
            # largura disponivel.
            textposition="inside",
            insidetextanchor="end",
            textfont={"color": "#ffffff", "size": 12},
            hovertemplate="<b>%{y}</b><br>%{x:,.0f} internações<extra></extra>",
        ))
        layout = tema.layout_base(altura=380)
        layout["xaxis"]["showgrid"] = False
        layout["xaxis"]["showticklabels"] = False
        figura.update_layout(**layout)
        st.plotly_chart(figura, width="stretch")

        st.dataframe(
            resumo[["uf", "permanencia", "mortalidade", "custo"]]
            .rename(columns={"uf": "UF", "permanencia": "Permanência",
                             "mortalidade": "Mortalidade %",
                             "custo": "Custo médio AIH"})
            .sort_values("UF"),
            hide_index=True, width="stretch")


# ---------------------------------------------------------------------------
# Capacidade
# ---------------------------------------------------------------------------

def pagina_capacidade(ufs: tuple[str, ...]) -> None:
    st.title("Capacidade hospitalar")
    st.caption("Onde a demanda por internação superou a capacidade de leitos "
               "SUS declarada ao CNES.")

    capacidade = dados.carrega("ind_capacidade_municipal")
    capacidade = capacidade[capacidade["uf"].isin(ufs)]

    contagem = capacidade["situacao"].value_counts()
    ordem = ["Folga", "Adequada", "Atencao", "Critica"]
    colunas = st.columns(4)
    for coluna, situacao in zip(colunas, ordem):
        coluna.metric(
            f"{tema.ICONE_STATUS[situacao]} {situacao}",
            tema.formata_milhar(int(contagem.get(situacao, 0))),
            help="Contagem de município-mês nesta classificação.")

    st.divider()

    st.subheader("Taxa de ocupação de leitos SUS por porte de município")
    ocupacao = dados.ocupacao_ponderada(ufs)

    figura = go.Figure()
    figura.add_trace(go.Bar(
        x=ocupacao["porte"], y=ocupacao["ocupacao_ponderada"],
        name="Ponderada por leitos-dia",
        marker={"color": tema.SERIES[0]},
        hovertemplate="<b>%{x}</b><br>Ocupação ponderada: "
                      "%{y:.1%}<extra></extra>",
    ))
    figura.add_trace(go.Bar(
        x=ocupacao["porte"], y=ocupacao["ocupacao_simples"],
        name="Média simples entre municípios",
        marker={"color": tema.SERIES[1]},
        hovertemplate="<b>%{x}</b><br>Média simples: %{y:.1%}<extra></extra>",
    ))
    layout = tema.layout_base(altura=360)
    layout["barmode"] = "group"
    layout["bargap"] = 0.3
    layout["yaxis"]["tickformat"] = ".0%"
    figura.update_layout(**layout)
    st.plotly_chart(figura, width="stretch")

    st.info(
        "**Por que dois números?** A média simples trata um município de três "
        "leitos igual a São Paulo. A ponderada divide o total de dias "
        "consumidos pelo total de leitos-dia disponíveis — é a taxa real do "
        "sistema, e é a que deve ser citada.\n\n"
        "No Sudeste as duas quase coincidem, e isso também informa: os "
        "municípios da região são homogêneos o bastante para que a média "
        "simples não engane. Num recorte nacional, com municípios de portes "
        "muito desiguais, a diferença seria grande — por isso o painel mostra "
        "as duas em vez de escolher uma em silêncio.", icon="📐")

    st.subheader("Municípios com maior taxa de ocupação de leitos")
    criticos = (capacidade[capacidade["situacao"].isin(["Critica", "Atencao"])]
                .nlargest(25, "taxa_ocupacao"))
    if criticos.empty:
        st.success("Nenhum município em situação de atenção ou crítica na "
                   "seleção atual.")
    else:
        exibicao = criticos[["municipio", "uf", "competencia", "populacao",
                             "internacoes", "leitos_sus", "taxa_ocupacao",
                             "situacao"]].copy()
        exibicao["situacao"] = exibicao["situacao"].map(
            lambda s: f"{tema.ICONE_STATUS.get(s, '')} {s}")
        st.dataframe(
            exibicao.rename(columns={
                "municipio": "Município", "uf": "UF",
                "competencia": "Competência", "populacao": "População",
                "internacoes": "Internações", "leitos_sus": "Leitos SUS",
                "taxa_ocupacao": "Ocupação", "situacao": "Situação"}),
            hide_index=True, width="stretch",
            column_config={"Ocupação": st.column_config.NumberColumn(
                format="%.2f")})

    st.warning(
        "**Ocupação acima de 1,0 é alerta para investigar, não prova de "
        "colapso.** Pode indicar sobrecarga real, leito desatualizado no CNES "
        "ou município-polo que atende toda uma região de saúde. O painel reduz "
        "1.668 municípios a uma lista de dezenas — a decisão continua humana.",
        icon="⚠️")


# ---------------------------------------------------------------------------
# Perfis
# ---------------------------------------------------------------------------

def pagina_perfis(ufs: tuple[str, ...]) -> None:
    st.title("Perfis de atendimento")
    st.caption("Quais tipos de atendimento mais pressionam o sistema — medidos "
               "por leito ocupado, não por volume.")

    perfil = dados.perfis_pressao(ufs).head(12)

    st.subheader("Consumo de leito por perfil, frente ao volume de internações")
    ordenado = perfil.sort_values("pressao_relativa")
    cores = [tema.SERIES[7] if v > 1.3 else
             tema.SERIES[3] if v > 1.0 else tema.SERIES[0]
             for v in ordenado["pressao_relativa"]]

    figura = go.Figure(go.Bar(
        x=ordenado["pressao_relativa"], y=ordenado["perfil_atendimento"],
        orientation="h",
        marker={"color": cores},
        text=[f"{v:.2f}".replace(".", ",") for v in ordenado["pressao_relativa"]],
        textposition="outside",
        textfont={"color": tema.TEXTO_SECUNDARIO},
        hovertemplate="<b>%{y}</b><br>Pressão relativa: %{x:.2f}<extra></extra>",
    ))
    layout = tema.layout_base(altura=460)
    layout["xaxis"]["showgrid"] = False
    layout["xaxis"]["showticklabels"] = False
    layout["margin"]["r"] = 60   # espaco para o rotulo externo nao ser cortado
    figura.update_layout(**layout)
    figura.add_vline(x=1.0, line={"width": 1, "dash": "dash",
                                  "color": tema.TEXTO_SECUNDARIO})
    st.plotly_chart(figura, width="stretch")

    st.info(
        "**Como ler:** pressão relativa é a participação do perfil nos "
        "leitos-dia dividida pela participação no número de internações. "
        "Acima de 1,0 o perfil ocupa mais leito do que o volume sugere — e "
        "isso é invisível num painel que só conta atendimentos.", icon="📊")

    st.dataframe(
        perfil[["perfil_atendimento", "internacoes", "pct_internacoes",
                "pct_leitos_dia", "pressao_relativa", "permanencia_media",
                "custo_medio_aih"]]
        .rename(columns={
            "perfil_atendimento": "Perfil (capítulo CID-10)",
            "internacoes": "Internações", "pct_internacoes": "% internações",
            "pct_leitos_dia": "% leitos-dia",
            "pressao_relativa": "Pressão relativa",
            "permanencia_media": "Permanência média",
            "custo_medio_aih": "Custo médio AIH"}),
        hide_index=True, width="stretch")


# ---------------------------------------------------------------------------
# Previsão
# ---------------------------------------------------------------------------

def pagina_previsao(ufs: tuple[str, ...]) -> None:
    st.title("Previsão de demanda")
    st.caption("Projeção diária de internações pelos próximos 90 dias.")

    previsao = dados.carrega("previsao_internacoes")
    previsao = previsao[previsao["uf"].isin(ufs)]
    previsao["data"] = pd.to_datetime(previsao["data"])

    uf_escolhida = st.selectbox(
        "Estado", [u for u in UFS_DISPONIVEIS if u in ufs],
        format_func=lambda uf: f"{uf} — {NOMES_UF[uf]}")

    serie = previsao[previsao["uf"] == uf_escolhida].sort_values("data")
    historico = serie[serie["tipo"] == "historico"]
    futuro = serie[serie["tipo"] == "previsao"]

    figura = go.Figure()
    figura.add_trace(go.Scatter(
        x=list(futuro["data"]) + list(futuro["data"])[::-1],
        y=list(futuro["limite_superior"]) + list(futuro["limite_inferior"])[::-1],
        fill="toself", fillcolor="rgba(42,120,214,0.12)",
        line={"width": 0}, hoverinfo="skip",
        name="Intervalo de 95%",
    ))
    figura.add_trace(go.Scatter(
        x=historico["data"], y=historico["internacoes_reais"],
        name="Observado", mode="lines",
        line={"width": 2, "color": tema.SERIES[0]},
        hovertemplate="%{x|%d/%m/%Y}<br>%{y:,.0f} internações<extra></extra>",
    ))
    figura.add_trace(go.Scatter(
        x=futuro["data"], y=futuro["internacoes_previstas"],
        name="Previsto", mode="lines",
        line={"width": 2, "color": tema.SERIES[1], "dash": "dot"},
        hovertemplate="%{x|%d/%m/%Y}<br>%{y:,.0f} previstas<extra></extra>",
    ))
    figura.update_layout(**tema.layout_base(altura=420))
    st.plotly_chart(figura, width="stretch")

    st.divider()
    esquerda, direita = st.columns(2)

    with esquerda:
        st.subheader("Erro de previsão por horizonte, em pontos percentuais")
        try:
            horizonte = dados.carrega("comparativo_horizonte")
            figura = go.Figure()
            figura.add_trace(go.Scatter(
                x=horizonte["horizonte_dias"], y=horizonte["mape_perfil"],
                name="Perfil semanal", mode="lines+markers",
                line={"width": 2, "color": tema.SERIES[0]},
                marker={"size": 8},
                hovertemplate="%{x} dias<br>Erro: %{y:.2f}%<extra></extra>"))
            figura.add_trace(go.Scatter(
                x=horizonte["horizonte_dias"], y=horizonte["mape_regressao"],
                name="Regressão", mode="lines+markers",
                line={"width": 2, "color": tema.SERIES[1]},
                marker={"size": 8},
                hovertemplate="%{x} dias<br>Erro: %{y:.2f}%<extra></extra>"))
            layout = tema.layout_base(altura=320)
            layout["yaxis"]["ticksuffix"] = "%"
            layout["xaxis"]["title"] = "Horizonte de previsão (dias)"
            figura.update_layout(**layout)
            st.plotly_chart(figura, width="stretch")
            st.caption("O erro da regressão cresce com o horizonte porque a "
                       "tendência linear extrapola. O perfil semanal permanece "
                       "estável — por isso ele é o modelo em produção.")
        except Exception as erro:
            st.info(f"Comparativo indisponível: {erro}")

    with direita:
        st.subheader("Variação de internações por dia da semana")
        try:
            coeficientes = dados.carrega("coeficientes_modelo")
            dias = coeficientes[
                coeficientes["variavel"].str.startswith(("dia_", "feriado"))]
            dias = dias[dias["uf"] == uf_escolhida].copy()
            dias["rotulo"] = dias["variavel"].str.replace("dia_", "", regex=False)
            dias = dias.sort_values("efeito_pct")

            figura = go.Figure(go.Bar(
                x=dias["efeito_pct"], y=dias["rotulo"], orientation="h",
                marker={"color": tema.SERIES[0]},
                text=[f"{v:.1f}%".replace(".", ",") for v in dias["efeito_pct"]],
                textposition="outside",
                textfont={"color": tema.TEXTO_SECUNDARIO},
                hovertemplate="<b>%{y}</b>: %{x:.1f}%<extra></extra>"))
            layout = tema.layout_base(altura=320)
            layout["xaxis"]["showticklabels"] = False
            layout["xaxis"]["showgrid"] = False
            layout["margin"]["r"] = 60
            figura.update_layout(**layout)
            st.plotly_chart(figura, width="stretch")
            st.caption("Variação percentual frente à segunda-feira. A queda de "
                       "fim de semana não é falta de doente: é a rede eletiva "
                       "parada.")
        except Exception as erro:
            st.info(f"Coeficientes indisponíveis: {erro}")


# ---------------------------------------------------------------------------
# NL -> SQL
# ---------------------------------------------------------------------------

def pagina_pergunte(ufs: tuple[str, ...]) -> None:
    st.title("Pergunte em português")
    st.caption("Digite a pergunta em linguagem natural. O painel traduz para "
               "SQL, executa no banco e mostra a consulta gerada.")

    with st.expander("Como isto se relaciona com o Oracle Select AI", expanded=False):
        st.markdown(
            "O **Select AI** da Oracle traduz perguntas em português para SQL "
            "usando os metadados do banco — os `COMMENT ON` de tabelas e "
            "colunas. Ele existe apenas no **Autonomous Database**.\n\n"
            "A instância acadêmica da FIAP é um **Oracle 19c Enterprise**, sem "
            "o pacote `DBMS_CLOUD_AI` — verificado por consulta a "
            "`all_objects`. Implementamos então o mecanismo equivalente sobre "
            "**os mesmos metadados** que o Select AI consumiria.\n\n"
            "É um tradutor **determinístico**: reconhece um repertório definido "
            "de perguntas e diz quando não entendeu, em vez de inventar. Num "
            "painel de saúde pública, admitir a dúvida é preferível a devolver "
            "um número errado com confiança.\n\n"
            "O script de configuração do Select AI está entregue em "
            "`src/db/ddl_oracle.sql`, pronto para rodar num Autonomous.")

    st.markdown("**Exemplos** — clique para usar:")
    colunas = st.columns(2)
    for indice, exemplo in enumerate(nl2sql.PERGUNTAS_EXEMPLO[:8]):
        if colunas[indice % 2].button(exemplo, key=f"ex{indice}",
                                      width="stretch"):
            st.session_state["pergunta"] = exemplo

    pergunta = st.text_input(
        "Sua pergunta",
        value=st.session_state.get("pergunta", ""),
        placeholder="Ex.: quais municípios tiveram maior crescimento de internações?")

    if not pergunta:
        return

    modo, _ = dados.modo_conexao()
    traducao = nl2sql.traduz(pergunta,
                             dialeto="oracle" if modo == "oracle" else "duckdb")

    if not traducao.sql:
        st.error(traducao.explicacao)
        st.markdown("**Tente uma destas:**")
        for alternativa in traducao.alternativas:
            st.markdown(f"- {alternativa}")
        return

    esquerda, direita = st.columns([1, 1])
    with esquerda:
        st.success(f"**Intenção reconhecida:** {traducao.intencao}")
    with direita:
        entidades = []
        if traducao.entidades.uf:
            entidades.append(f"UF = {traducao.entidades.uf}")
        if traducao.entidades.mes:
            entidades.append(f"mês = {traducao.entidades.mes:02d}")
        entidades.append(f"limite = {traducao.entidades.limite}")
        st.caption(f"Confiança {traducao.confianca:.0%} · "
                   f"Filtros: {' · '.join(entidades)}")

    st.caption(traducao.explicacao)

    with st.expander("SQL gerado", expanded=True):
        st.code(traducao.sql, language="sql")
        st.caption(f"Tabelas consultadas: {', '.join(traducao.tabelas)}")

    try:
        resultado = dados.consulta(traducao.sql)
        st.dataframe(resultado, hide_index=True, width="stretch")
        if modo == "oracle":
            st.caption(f"{len(resultado)} linhas retornadas do **Oracle "
                       f"Database**.")
        else:
            st.caption(f"{len(resultado)} linhas — executadas sobre o retrato "
                       f"local em parquet, porque o Oracle está indisponível. "
                       f"O SQL é o mesmo; muda apenas onde ele roda.")
    except Exception as erro:
        st.error(f"Erro ao executar a consulta: {erro}")



# ---------------------------------------------------------------------------

def main() -> None:
    pagina, ufs = barra_lateral()

    if pagina == "Pergunte em português":
        pagina_pergunte(ufs)
        return
    if not exige_uf(ufs):
        return

    if pagina == "Visão geral":
        pagina_visao_geral(ufs)
    elif pagina == "Capacidade hospitalar":
        pagina_capacidade(ufs)
    elif pagina == "Perfis de atendimento":
        pagina_perfis(ufs)
    elif pagina == "Previsão de demanda":
        pagina_previsao(ufs)


if __name__ == "__main__":
    main()
