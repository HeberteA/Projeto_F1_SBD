import streamlit as st
import psycopg2
import pandas as pd
import plotly.express as px
from streamlit_option_menu import option_menu

st.set_page_config(layout="wide", page_title="F1 Super Analytics", page_icon="f1.png")

F1_PALETTE = ["#E10600", "#15151E", "#7F7F7F", "#B1B1B8", "#FFFFFF", "#FF8700", "#00A000"] 
F1_RED = F1_PALETTE[0]
F1_BLACK = F1_PALETTE[1]
F1_GREY = F1_PALETTE[2]

@st.cache_resource
def conectar_db():
    try:
        return psycopg2.connect(st.secrets["database"]["connection_string"])
    except psycopg2.Error as e:
        st.error(f"Erro CRÍTICO de conexão: {e}")
        return None
conn = conectar_db()

@st.cache_data(ttl=60)
def consultar_dados_df(query, params=None):
    if not conn: return pd.DataFrame()
    try:
        return pd.read_sql_query(query, conn, params=params)
    except Exception as e:
        st.warning(f"Erro ao ler dados: {e}")
        return pd.DataFrame()

def executar_comando_sql(query, params=None):
    if not conn: return None
    try:
        with conn.cursor() as cursor:
            cursor.execute(query, params)
            conn.commit()
            return cursor.rowcount
    except Exception as e:
        st.error(f"Erro de banco de dados: {e}")
        conn.rollback() 
        return None

with st.sidebar:
    st.image("f1_logo.png", width=300)
    pagina_selecionada = option_menu(
        menu_title="Menu Principal", options=["Análises", "Gerenciamento"],
        icons=["trophy-fill", "pencil-square"], menu_icon="joystick", default_index=0
    )

if pagina_selecionada == "Análises":
    st.title("📊 Análises e Dashboards de F1")
    
    tab_piloto, tab_equipe, tab_h2h, tab_circ, tab_records = st.tabs(["Dashboard de Piloto", "Dashboard de Equipe", "Comparador H2H", "Análise de Circuito", "🏆 Hall da Fama"])

    with tab_piloto:
        st.header("Análise de Performance de Piloto")
        pilotos_df = consultar_dados_df("SELECT * FROM tbl_pilotos ORDER BY sobrenome")
        if not pilotos_df.empty:
            pilotos_df["nome_completo"] = pilotos_df["nome"] + " " + pilotos_df["sobrenome"]
            piloto_selecionado = st.selectbox("Selecione um Piloto", options=pilotos_df["nome_completo"], index=None, placeholder="Digite o nome de um piloto...", key="sel_piloto")
            
            if not piloto_selecionado:
                st.info("Selecione um piloto para visualizar suas estatísticas.")
            else:
                piloto_info = pilotos_df[pilotos_df["nome_completo"] == piloto_selecionado].iloc[0]
                id_piloto = int(piloto_info["id_piloto"])
                with st.container(border=True):
                    c1, c2, c3, c4 = st.columns([2, 1, 1, 1.5])
                    with c1:
                        st.markdown(f"<h2 style='text-align: left; font-size: 50px; font-weight: sans-serif;'>{piloto_info['nome_completo']}</h2>", unsafe_allow_html=True)
                    with c2:
                        st.metric("País", str(piloto_info['nacionalidade']))
                    with c3:
                        st.metric("Número", "N/A" if pd.isna(piloto_info['numero']) else int(piloto_info['numero']))
                    with c4:
                        equipe_sucesso_query = "SELECT con.nome, SUM(r.pontos) as total_pontos FROM tbl_resultados r JOIN tbl_construtores con ON r.id_construtor_fk = con.id_construtor WHERE r.id_piloto_fk = %(id)s GROUP BY con.nome ORDER BY total_pontos DESC LIMIT 1;"
                        equipe_sucesso_df = consultar_dados_df(equipe_sucesso_query, params={"id": id_piloto})
                        if not equipe_sucesso_df.empty:
                            st.metric("Equipe de Maior Sucesso (Pontos)", equipe_sucesso_df.iloc[0]['nome'])

                st.subheader("Estatísticas da Carreira")
                kpi_query = """
                    WITH pilot_champs AS (
                        SELECT piloto, COUNT(*) as titulos FROM (
                            SELECT p.nome || ' ' || p.sobrenome as piloto FROM tbl_resultados r JOIN tbl_corridas c ON r.id_corrida_fk = c.id_corrida JOIN tbl_pilotos p ON r.id_piloto_fk = p.id_piloto GROUP BY c.ano, p.nome, p.sobrenome HAVING SUM(r.pontos) = (SELECT MAX(total_pontos) FROM (SELECT SUM(pontos) as total_pontos FROM tbl_resultados r2 JOIN tbl_corridas c2 ON r2.id_corrida_fk = c2.id_corrida WHERE c2.ano = c.ano GROUP BY r2.id_piloto_fk) as sub)
                        ) as champs WHERE piloto = %(nome_piloto)s GROUP BY piloto
                    )
                    SELECT 
                        COUNT(*) AS total_corridas,
                        SUM(CASE WHEN posicao_final = 1 THEN 1 ELSE 0 END) AS vitorias,
                        SUM(CASE WHEN posicao_grid = 1 THEN 1 ELSE 0 END) AS poles,
                        SUM(CASE WHEN posicao_final <= 3 THEN 1 ELSE 0 END) AS podios,
                        SUM(pontos) AS total_pontos,
                        AVG(pontos) AS media_pontos,
                        SUM(CASE WHEN rank_volta_rapida = 1 THEN 1 ELSE 0 END) AS voltas_rapidas,
                        COALESCE((SELECT titulos FROM pilot_champs), 0) as titulos
                    FROM tbl_resultados WHERE id_piloto_fk = %(id_piloto)s;
                """
                kpi_df = consultar_dados_df(kpi_query, params={"id_piloto": id_piloto, "nome_piloto": piloto_selecionado})

                if not kpi_df.empty:
                    kpi_data = kpi_df.iloc[0]
                    c1, c2, c3, c4, c5, c6, c7 = st.columns(7)
                    c1.metric("🏆 Títulos", int(kpi_data["titulos"]))
                    c2.metric("Corridas", int(kpi_data["total_corridas"]))
                    c3.metric("🥇 Vitórias", int(kpi_data["vitorias"]))
                    c4.metric("🥈 Pódios", int(kpi_data["podios"]))
                    c5.metric("⏱️ Poles", int(kpi_data["poles"]))
                    c6.metric("🚀 Voltas R.", int(kpi_data["voltas_rapidas"]))
                    c7.metric("Média Pontos", f"{kpi_data['media_pontos']:.2f}" if kpi_data['media_pontos'] else "0.00")

                    st.subheader("Métricas de Performance")
                    c1, c2, c3 = st.columns(3)
                    win_rate = (kpi_data["vitorias"] / kpi_data["total_corridas"] * 100) if kpi_data["total_corridas"] > 0 else 0
                    podium_rate = (kpi_data["podios"] / kpi_data["total_corridas"] * 100) if kpi_data["total_corridas"] > 0 else 0
                    c1.metric("% de Vitórias", f"{win_rate:.1f}%")
                    c2.metric("% de Pódios", f"{podium_rate:.1f}%")
                    
                    best_grid_query = "SELECT cir.nome, AVG(r.posicao_grid) as media_grid FROM tbl_resultados r JOIN tbl_corridas c ON r.id_corrida_fk = c.id_corrida JOIN tbl_circuitos cir ON c.id_circuito_fk = cir.id_circuito WHERE r.id_piloto_fk = %(id)s GROUP BY cir.nome ORDER BY media_grid ASC LIMIT 1;"
                    best_grid_df = consultar_dados_df(best_grid_query, params={'id': id_piloto})
                    if not best_grid_df.empty:
                         c3.metric("Melhor Média de Largada", best_grid_df.iloc[0]['nome'], f"#{best_grid_df.iloc[0]['media_grid']:.2f}")

                st.divider()
                st.subheader("Comparativo Anual (Vitórias, Poles, Pódios)")
                stats_anual_query = "SELECT c.ano, SUM(CASE WHEN r.posicao_final = 1 THEN 1 ELSE 0 END) AS vitorias, SUM(CASE WHEN r.posicao_grid = 1 THEN 1 ELSE 0 END) AS poles, SUM(CASE WHEN r.posicao_final <= 3 THEN 1 ELSE 0 END) AS podios FROM tbl_resultados r JOIN tbl_corridas c ON r.id_corrida_fk = c.id_corrida WHERE r.id_piloto_fk = %(id)s GROUP BY c.ano ORDER BY c.ano;"
                stats_anual_df = consultar_dados_df(stats_anual_query, params={'id': id_piloto})
                if not stats_anual_df.empty:
                    stats_anual_df_melted = stats_anual_df.melt(id_vars='ano', value_vars=['vitorias', 'poles', 'podios'], var_name='Estatística', value_name='Total')
                    fig_stats_anual_piloto = px.bar(stats_anual_df_melted, x='ano', y='Total', color='Estatística', barmode='group', text_auto=True, color_discrete_map={'vitorias': F1_RED, 'poles': F1_GREY, 'podios': F1_BLACK})
                    st.plotly_chart(fig_stats_anual_piloto, use_container_width=True)


                col_chart3, col_chart4 = st.columns(2)
                with col_chart3:
                    st.subheader("Distribuição de Resultados")
                    dist_query = "SELECT CASE WHEN posicao_final IS NULL THEN 'Não Terminou (DNF)' WHEN posicao_final BETWEEN 1 AND 3 THEN 'Pódio' WHEN posicao_final BETWEEN 4 AND 10 THEN 'Pontos (4-10)' ELSE 'Fora dos Pontos' END as resultado, COUNT(*) as total FROM tbl_resultados WHERE id_piloto_fk = %(id)s GROUP BY resultado ORDER BY total DESC;"
                    dist_df = consultar_dados_df(dist_query, params={'id': id_piloto})
                    if not dist_df.empty:
                        fig_dist_piloto = px.pie(dist_df, names='resultado', values='total', hole=0.3, color_discrete_sequence=F1_PALETTE)
                        st.plotly_chart(fig_dist_piloto, use_container_width=True)
                with col_chart4:
                    st.subheader("Pontos por Temporada")
                    pontos_query = "SELECT c.ano, SUM(r.pontos) as pontos FROM tbl_resultados r JOIN tbl_corridas c ON r.id_corrida_fk = c.id_corrida WHERE r.id_piloto_fk = %(id)s GROUP BY c.ano ORDER BY c.ano;"
                    pontos_df = consultar_dados_df(pontos_query, params={'id': id_piloto})
                    if not pontos_df.empty:
                        fig_pontos_piloto = px.bar(pontos_df, x='ano', y='pontos', text_auto=True, color_discrete_sequence=[F1_RED], labels={'ano': 'Temporada', 'pontos': 'Pontos'})
                        st.plotly_chart(fig_pontos_piloto, use_container_width=True)


    with tab_equipe:
        st.header("Análise de Performance de Equipe")
        equipes_df = consultar_dados_df("SELECT id_construtor, nome, nacionalidade FROM tbl_construtores ORDER BY nome")
        if not equipes_df.empty:
            equipe_selecionada = st.selectbox("Selecione uma Equipe", options=equipes_df["nome"], index=None, placeholder="Digite o nome de uma equipe...", key="sel_equipe")
            if not equipe_selecionada:
                st.info("Selecione uma equipe para visualizar suas estatísticas.")
            else:
                equipe_info = equipes_df[equipes_df["nome"] == equipe_selecionada].iloc[0]
                id_equipe = int(equipe_info["id_construtor"])
                
                with st.container(border=True):
                    c1, c2, c3 = st.columns([2,1,1])
                    with c1: st.markdown(f"<h2 style='text-align: left;'>{equipe_info['nome']}</h2>", unsafe_allow_html=True)
                    with c2: st.metric("País", str(equipe_info['nacionalidade']))
                    with c3:
                        total_pilotos_query = "SELECT COUNT(DISTINCT id_piloto_fk) as total FROM tbl_resultados WHERE id_construtor_fk = %(id)s;"
                        total_pilotos_df = consultar_dados_df(total_pilotos_query, params={'id': id_equipe})
                        st.metric("Total de Pilotos na História", total_pilotos_df.iloc[0]['total'] if not total_pilotos_df.empty else 0)

                st.subheader("Resumo Histórico")
                kpi_equipe_query = """
                    WITH constructor_champs AS (
                        SELECT construtor, COUNT(*) as titulos FROM (
                            SELECT con.nome as construtor FROM tbl_resultados r JOIN tbl_corridas c ON r.id_corrida_fk = c.id_corrida JOIN tbl_construtores con ON r.id_construtor_fk = con.id_construtor GROUP BY c.ano, con.nome HAVING SUM(r.pontos) = (SELECT MAX(total_pontos) FROM (SELECT SUM(pontos) as total_pontos FROM tbl_resultados r2 JOIN tbl_corridas c2 ON r2.id_corrida_fk = c2.id_corrida WHERE c2.ano = c.ano GROUP BY r2.id_construtor_fk) as sub)
                        ) as champs WHERE construtor = %(nome_equipe)s GROUP BY construtor
                    )
                    SELECT
                        COUNT(DISTINCT id_corrida_fk) as total_corridas,
                        SUM(CASE WHEN posicao_final = 1 THEN 1 ELSE 0 END) as vitorias,
                        SUM(CASE WHEN posicao_grid = 1 THEN 1 ELSE 0 END) AS poles,
                        SUM(CASE WHEN posicao_final <= 3 THEN 1 ELSE 0 END) as podios,
                        SUM(CASE WHEN rank_volta_rapida = 1 THEN 1 ELSE 0 END) AS voltas_rapidas,
                        SUM(pontos) as total_pontos,
                        COALESCE((SELECT titulos FROM constructor_champs), 0) as titulos
                    FROM tbl_resultados WHERE id_construtor_fk = %(id_equipe)s;
                """
                kpi_equipe_df = consultar_dados_df(kpi_equipe_query, params={"id_equipe": id_equipe, "nome_equipe": equipe_selecionada})
                
                if not kpi_equipe_df.empty:
                    kpi_equipe_data = kpi_equipe_df.iloc[0]
                    c1, c2, c3, c4, c5, c6 = st.columns(6)
                    c1.metric("🏆 Títulos", int(kpi_equipe_data["titulos"]))
                    c2.metric("Corridas", int(kpi_equipe_data["total_corridas"]))
                    c3.metric("🥇 Vitórias", int(kpi_equipe_data["vitorias"]))
                    c4.metric("🥈 Pódios", int(kpi_equipe_data["podios"]))
                    c5.metric("⏱️ Poles", int(kpi_equipe_data["poles"]))
                    c6.metric("🚀 Voltas R.", int(kpi_equipe_data["voltas_rapidas"]))

                    st.subheader("Métricas de Performance da Equipe")
                    c1, c2, c3 = st.columns(3)
                    pole_win_conv = (kpi_equipe_data["vitorias"] / kpi_equipe_data["poles"] * 100) if kpi_equipe_data["poles"] > 0 else 0
                    c1.metric("Conversão Pole > Vitória", f"{pole_win_conv:.1f}%")

                    dobradinhas_query = "SELECT COUNT(*) as total FROM (SELECT id_corrida_fk FROM tbl_resultados WHERE id_construtor_fk = %(id)s AND posicao_final IN (1, 2) GROUP BY id_corrida_fk HAVING COUNT(DISTINCT id_piloto_fk) = 2) as dobradinhas;"
                    dobradinhas_df = consultar_dados_df(dobradinhas_query, params={'id': id_equipe})
                    c2.metric("Dobradinhas (1º e 2º)", dobradinhas_df.iloc[0]['total'] if not dobradinhas_df.empty else 0)

                    primeira_vitoria_query = "SELECT c.ano FROM tbl_resultados r JOIN tbl_corridas c ON r.id_corrida_fk = c.id_corrida WHERE r.id_construtor_fk = %(id)s AND r.posicao_final = 1 ORDER BY c.ano ASC LIMIT 1;"
                    primeira_vitoria_df = consultar_dados_df(primeira_vitoria_query, params={'id': id_equipe})
                    c3.metric("Ano da Primeira Vitória", primeira_vitoria_df.iloc[0]['ano'] if not primeira_vitoria_df.empty else "N/A")


                st.divider()

                st.subheader("Dobradinhas por Temporada")
                dobradinhas_ano_query = "SELECT c.ano, COUNT(*) as total FROM (SELECT r.id_corrida_fk FROM tbl_resultados r WHERE r.id_construtor_fk = %(id)s AND r.posicao_final IN (1, 2) GROUP BY r.id_corrida_fk HAVING COUNT(DISTINCT r.id_piloto_fk) = 2) as dobradinhas JOIN tbl_corridas c ON dobradinhas.id_corrida_fk = c.id_corrida GROUP BY c.ano ORDER BY c.ano;"
                dobradinhas_ano_df = consultar_dados_df(dobradinhas_ano_query, params={'id': id_equipe})
                if not dobradinhas_ano_df.empty:
                    fig_dobradinhas_ano = px.bar(dobradinhas_ano_df, x='ano', y='total', text_auto=True, color_discrete_sequence=[F1_BLACK], labels={'ano': 'Temporada', 'total': 'Total de Dobradinhas'})
                    st.plotly_chart(fig_dobradinhas_ano, use_container_width=True)

                g1, g2 = st.columns(2)
                with g1:
                    st.subheader("Pontos por Temporada")
                    pontos_equipe_query = "SELECT c.ano, SUM(r.pontos) as pontos FROM tbl_resultados r JOIN tbl_corridas c ON r.id_corrida_fk = c.id_corrida WHERE r.id_construtor_fk = %(id)s GROUP BY c.ano ORDER BY c.ano;"
                    pontos_equipe_df = consultar_dados_df(pontos_equipe_query, params={'id': id_equipe})
                    if not pontos_equipe_df.empty:
                        fig_pontos_equipe = px.bar(pontos_equipe_df, x='ano', y='pontos', text_auto=True, color_discrete_sequence=[F1_RED])
                        st.plotly_chart(fig_pontos_equipe, use_container_width=True)
                with g2:
                    st.subheader("Top 5 Pilotos (Pontos)")
                    pilotos_pontos_query = "SELECT p.nome || ' ' || p.sobrenome as piloto, SUM(r.pontos) as total_pontos FROM tbl_resultados r JOIN tbl_pilotos p ON r.id_piloto_fk = p.id_piloto WHERE r.id_construtor_fk = %(id)s GROUP BY piloto ORDER BY total_pontos DESC LIMIT 5;"
                    pilotos_pontos_df = consultar_dados_df(pilotos_pontos_query, params={'id': id_equipe})
                    if not pilotos_pontos_df.empty:
                        fig_top_pilotos_equipe = px.pie(pilotos_pontos_df, names='piloto', values='total_pontos', hole=0.3, color_discrete_sequence=F1_PALETTE)
                        st.plotly_chart(fig_top_pilotos_equipe, use_container_width=True)


    with tab_h2h:
        st.header("Comparador de Pilotos: Head-to-Head")
        anos_df = consultar_dados_df("SELECT MIN(ano) as min_ano, MAX(ano) as max_ano FROM tbl_corridas;")
        
        if not anos_df.empty and not pd.isna(anos_df['min_ano'].iloc[0]):
            min_ano, max_ano = int(anos_df['min_ano'].iloc[0]), int(anos_df['max_ano'].iloc[0])
            temporada_selecionada = st.select_slider("Filtre por Temporada:", options=range(min_ano, max_ano + 1), value=(min_ano, max_ano))
            start_year, end_year = temporada_selecionada

            pilotos_df_h2h = consultar_dados_df("SELECT * FROM tbl_pilotos ORDER BY sobrenome")
            if not pilotos_df_h2h.empty:
                pilotos_df_h2h["nome_completo"] = pilotos_df_h2h["nome"] + " " + pilotos_df_h2h["sobrenome"]
                sel_col1, sel_col2 = st.columns(2)
                piloto1_nome = sel_col1.selectbox("Piloto 1", options=pilotos_df_h2h["nome_completo"], index=None, key="p1", placeholder="Selecione o piloto 1")
                piloto2_nome = sel_col2.selectbox("Piloto 2", options=pilotos_df_h2h["nome_completo"], index=None, key="p2", placeholder="Selecione o piloto 2")

                if piloto1_nome and piloto2_nome:
                    id_piloto1 = int(pilotos_df_h2h[pilotos_df_h2h["nome_completo"] == piloto1_nome].iloc[0]['id_piloto'])
                    id_piloto2 = int(pilotos_df_h2h[pilotos_df_h2h["nome_completo"] == piloto2_nome].iloc[0]['id_piloto'])
                    params_h2h = {'p1': id_piloto1, 'p2': id_piloto2, 'n1': piloto1_nome, 'n2': piloto2_nome, 'sy': start_year, 'ey': end_year}

                    st.divider()
                    st.subheader(f"Análise Gráfica Comparativa ({start_year}-{end_year})")
                    
                    g1, g2 = st.columns(2)
                    with g1:
                        st.markdown("##### Pódios por Temporada")
                        podios_h2h_q = "SELECT c.ano, p.nome || ' ' || p.sobrenome as piloto, SUM(CASE WHEN r.posicao_final <= 3 THEN 1 ELSE 0 END) as podios FROM tbl_resultados r JOIN tbl_corridas c ON r.id_corrida_fk = c.id_corrida JOIN tbl_pilotos p ON r.id_piloto_fk = p.id_piloto WHERE r.id_piloto_fk IN (%(p1)s, %(p2)s) AND c.ano BETWEEN %(sy)s AND %(ey)s GROUP BY c.ano, piloto ORDER BY c.ano;"
                        podios_h2h_df = consultar_dados_df(podios_h2h_q, params=params_h2h)
                        if not podios_h2h_df.empty:
                            fig_podios_h2h = px.bar(podios_h2h_df, x='ano', y='podios', color='piloto', barmode='group', text_auto=True, color_discrete_map={piloto1_nome: F1_RED, piloto2_nome: F1_GREY})
                            st.plotly_chart(fig_podios_h2h, use_container_width=True)
                    with g2:
                        st.markdown("##### Poles por Temporada")
                        poles_h2h_q = "SELECT c.ano, p.nome || ' ' || p.sobrenome as piloto, SUM(CASE WHEN r.posicao_grid = 1 THEN 1 ELSE 0 END) as poles FROM tbl_resultados r JOIN tbl_corridas c ON r.id_corrida_fk = c.id_corrida JOIN tbl_pilotos p ON r.id_piloto_fk = p.id_piloto WHERE r.id_piloto_fk IN (%(p1)s, %(p2)s) AND c.ano BETWEEN %(sy)s AND %(ey)s GROUP BY c.ano, piloto ORDER BY c.ano;"
                        poles_h2h_df = consultar_dados_df(poles_h2h_q, params=params_h2h)
                        if not poles_h2h_df.empty:
                            fig_poles_h2h = px.bar(poles_h2h_df, x='ano', y='poles', color='piloto', barmode='group', text_auto=True, color_discrete_map={piloto1_nome: F1_RED, piloto2_nome: F1_GREY})
                            st.plotly_chart(fig_poles_h2h, use_container_width=True)

                    st.subheader("Confrontos Diretos")
                    g1, g2 = st.columns(2)
                    with g1:
                        st.markdown("##### Final de Corrida")
                        confronto_query = "WITH corridas_comuns AS (SELECT id_corrida_fk FROM tbl_resultados WHERE id_piloto_fk = %(p1)s AND id_corrida_fk IN (SELECT id_corrida FROM tbl_corridas WHERE ano BETWEEN %(sy)s AND %(ey)s) INTERSECT SELECT id_corrida_fk FROM tbl_resultados WHERE id_piloto_fk = %(p2)s AND id_corrida_fk IN (SELECT id_corrida FROM tbl_corridas WHERE ano BETWEEN %(sy)s AND %(ey)s)) SELECT MAX(CASE WHEN id_piloto_fk = %(p1)s THEN posicao_final END) as p1_pos, MAX(CASE WHEN id_piloto_fk = %(p2)s THEN posicao_final END) as p2_pos FROM tbl_resultados WHERE id_corrida_fk IN (SELECT id_corrida_fk FROM corridas_comuns) GROUP BY id_corrida_fk"
                        confronto_df = consultar_dados_df(confronto_query, params=params_h2h)
                        if not confronto_df.empty:
                            confronto_df.dropna(inplace=True) 
                            p1_a_frente = (confronto_df['p1_pos'] < confronto_df['p2_pos']).sum()
                            p2_a_frente = (confronto_df['p2_pos'] < confronto_df['p1_pos']).sum()
                            fig_confronto_h2h = px.bar(x=[piloto1_nome, piloto2_nome], y=[p1_a_frente, p2_a_frente], labels={'x': 'Piloto', 'y': 'Vezes que terminou à frente'}, color=[piloto1_nome, piloto2_nome], color_discrete_map={piloto1_nome: F1_RED, piloto2_nome: F1_GREY}, text_auto=True)
                            fig_confronto_h2h.update_layout(showlegend=False)
                            st.plotly_chart(fig_confronto_h2h, use_container_width=True)
                    with g2:
                        st.markdown("##### Qualificação")
                        confronto_quali_q = "WITH corridas_comuns AS (SELECT id_corrida_fk FROM tbl_resultados WHERE id_piloto_fk = %(p1)s AND id_corrida_fk IN (SELECT id_corrida FROM tbl_corridas WHERE ano BETWEEN %(sy)s AND %(ey)s) INTERSECT SELECT id_corrida_fk FROM tbl_resultados WHERE id_piloto_fk = %(p2)s AND id_corrida_fk IN (SELECT id_corrida FROM tbl_corridas WHERE ano BETWEEN %(sy)s AND %(ey)s)) SELECT MAX(CASE WHEN id_piloto_fk = %(p1)s THEN posicao_grid END) as p1_pos, MAX(CASE WHEN id_piloto_fk = %(p2)s THEN posicao_grid END) as p2_pos FROM tbl_resultados WHERE id_corrida_fk IN (SELECT id_corrida_fk FROM corridas_comuns) GROUP BY id_corrida_fk"
                        confronto_quali_df = consultar_dados_df(confronto_quali_q, params=params_h2h)
                        if not confronto_quali_df.empty:
                            confronto_quali_df.dropna(inplace=True)
                            p1_grid_melhor = (confronto_quali_df['p1_pos'] < confronto_quali_df['p2_pos']).sum()
                            p2_grid_melhor = (confronto_quali_df['p2_pos'] < confronto_quali_df['p1_pos']).sum()
                            fig_quali_h2h = px.bar(x=[piloto1_nome, piloto2_nome], y=[p1_grid_melhor, p2_grid_melhor], labels={'x': 'Piloto', 'y': 'Vezes que largou à frente'}, color=[piloto1_nome, piloto2_nome], color_discrete_map={piloto1_nome: F1_RED, piloto2_nome: F1_GREY}, text_auto=True)
                            fig_quali_h2h.update_layout(showlegend=False)
                            st.plotly_chart(fig_quali_h2h, use_container_width=True)

    with tab_circ:
        st.header("Análise por Circuito")
        circuitos_df = consultar_dados_df("SELECT id_circuito, nome, cidade, pais FROM tbl_circuitos ORDER BY nome")
        if not circuitos_df.empty:
            circuito_nome = st.selectbox("Selecione um Circuito", options=circuitos_df["nome"], index=None, key="sel_circuito")
            if circuito_nome:
                circuito_info = circuitos_df[circuitos_df["nome"] == circuito_nome].iloc[0]
                id_circuito = int(circuito_info["id_circuito"])
                
                st.subheader(f"Resumo Histórico do Circuito: {circuito_info['nome']}")
                kpi_circ_query = "WITH poles AS (SELECT COUNT(*) as total_poles FROM tbl_resultados r JOIN tbl_corridas c ON r.id_corrida_fk = c.id_corrida WHERE c.id_circuito_fk=%(id)s AND r.posicao_grid = 1), wins_from_pole AS (SELECT COUNT(*) as wins_fp FROM tbl_resultados r JOIN tbl_corridas c ON r.id_corrida_fk = c.id_corrida WHERE c.id_circuito_fk=%(id)s AND r.posicao_grid = 1 AND r.posicao_final = 1) SELECT (SELECT COUNT(DISTINCT ano) FROM tbl_corridas WHERE id_circuito_fk=%(id)s) as total_corridas, (SELECT p.nome || ' ' || p.sobrenome FROM tbl_resultados r JOIN tbl_pilotos p ON r.id_piloto_fk=p.id_piloto JOIN tbl_corridas c ON r.id_corrida_fk=c.id_corrida WHERE c.id_circuito_fk=%(id)s AND r.posicao_final=1 GROUP BY p.nome, p.sobrenome ORDER BY COUNT(*) DESC LIMIT 1) as maior_vencedor, (SELECT p.nome || ' ' || p.sobrenome FROM tbl_resultados r JOIN tbl_pilotos p ON r.id_piloto_fk=p.id_piloto JOIN tbl_corridas c ON r.id_corrida_fk=c.id_corrida WHERE c.id_circuito_fk=%(id)s AND r.rank_volta_rapida=1 GROUP BY p.nome, p.sobrenome ORDER BY COUNT(*) DESC LIMIT 1) as mais_voltas_rapidas, (SELECT CAST(wins_fp AS FLOAT) / total_poles * 100 FROM poles, wins_from_pole) as pole_win_rate FROM tbl_corridas WHERE id_circuito_fk=%(id)s LIMIT 1;"
                kpi_circ_df = consultar_dados_df(kpi_circ_query, params={'id': id_circuito}).iloc[0]
                c1, c2, c3, c4 = st.columns(4)
                c1.metric("Total de Corridas", int(kpi_circ_df["total_corridas"]))
                c2.metric("Maior Vencedor", str(kpi_circ_df["maior_vencedor"]))
                c3.metric("Mais Voltas Rápidas", str(kpi_circ_df["mais_voltas_rapidas"]))
                c4.metric("% Vitórias da Pole", f"{kpi_circ_df['pole_win_rate']:.1f}%" if kpi_circ_df['pole_win_rate'] else "N/A")
                st.divider()

                st.subheader("De Onde Saem os Vencedores?")
                grid_vencedor_q = "SELECT posicao_grid FROM tbl_resultados r JOIN tbl_corridas c ON r.id_corrida_fk = c.id_corrida WHERE c.id_circuito_fk=%(id)s AND r.posicao_final = 1 AND r.posicao_grid IS NOT NULL;"
                grid_vencedor_df = consultar_dados_df(grid_vencedor_q, params={'id': id_circuito})
                if not grid_vencedor_df.empty:
                    fig_grid_vencedor = px.histogram(grid_vencedor_df, x='posicao_grid', nbins=20, text_auto=True, color_discrete_sequence=[F1_BLACK], labels={'posicao_grid': 'Posição de Largada', 'count': 'Número de Vitórias'})
                    fig_grid_vencedor.update_layout(bargap=0.2)
                    st.plotly_chart(fig_grid_vencedor, use_container_width=True)

                g1, g2 = st.columns(2)
                with g1:
                    st.subheader("Top 10 Pilotos Vencedores")
                    vencedores_query = "SELECT p.nome || ' ' || p.sobrenome as piloto, COUNT(*) as vitorias FROM tbl_resultados r JOIN tbl_corridas c ON r.id_corrida_fk=c.id_corrida JOIN tbl_pilotos p ON r.id_piloto_fk=p.id_piloto WHERE c.id_circuito_fk=%(id)s AND r.posicao_final=1 GROUP BY piloto ORDER BY vitorias DESC LIMIT 10;"
                    vencedores_df = consultar_dados_df(vencedores_query, params={'id': id_circuito})
                    fig_vencedores_circ = px.bar(vencedores_df, x='vitorias', y='piloto', orientation='h', color_discrete_sequence=[F1_RED], text_auto=True)
                    fig_vencedores_circ.update_layout(yaxis={'categoryorder':'total ascending'})
                    st.plotly_chart(fig_vencedores_circ, use_container_width=True)
                with g2:
                    st.subheader("Top 10 Equipes Vitoriosas")
                    vencedores_eq_query = "SELECT con.nome as equipe, COUNT(*) as vitorias FROM tbl_resultados r JOIN tbl_corridas c ON r.id_corrida_fk=c.id_corrida JOIN tbl_construtores con ON r.id_construtor_fk=con.id_construtor WHERE c.id_circuito_fk=%(id)s AND r.posicao_final=1 GROUP BY equipe ORDER BY vitorias DESC LIMIT 10;"
                    vencedores_eq_df = consultar_dados_df(vencedores_eq_query, params={'id': id_circuito})
                    fig_vencedores_eq_circ = px.bar(vencedores_eq_df, x='vitorias', y='equipe', orientation='h', color_discrete_sequence=[F1_GREY], text_auto=True)
                    fig_vencedores_eq_circ.update_layout(yaxis={'categoryorder':'total ascending'})
                    st.plotly_chart(fig_vencedores_eq_circ, use_container_width=True)

    with tab_records:
        st.header("Hall da Fama: Recordes e Rankings Históricos")
        st.subheader("Recordistas de Todos os Tempos")
        query_records = """
            WITH pilot_champs_agg AS (SELECT piloto, COUNT(*) as titulos FROM (SELECT c.ano, p.nome || ' ' || p.sobrenome as piloto FROM tbl_resultados r JOIN tbl_corridas c ON r.id_corrida_fk = c.id_corrida JOIN tbl_pilotos p ON r.id_piloto_fk = p.id_piloto GROUP BY c.ano, p.nome, p.sobrenome HAVING SUM(r.pontos) = (SELECT MAX(total_pontos) FROM (SELECT SUM(pontos) as total_pontos FROM tbl_resultados r2 JOIN tbl_corridas c2 ON r2.id_corrida_fk = c2.id_corrida WHERE c2.ano = c.ano GROUP BY r2.id_piloto_fk) as sub)) as champs GROUP BY piloto),
            constructor_champs_agg AS (SELECT construtor, COUNT(*) as titulos FROM (SELECT c.ano, con.nome as construtor FROM tbl_resultados r JOIN tbl_corridas c ON r.id_corrida_fk = c.id_corrida JOIN tbl_construtores con ON r.id_construtor_fk = con.id_construtor GROUP BY c.ano, con.nome HAVING SUM(r.pontos) = (SELECT MAX(total_pontos) FROM (SELECT SUM(pontos) as total_pontos FROM tbl_resultados r2 JOIN tbl_corridas c2 ON r2.id_corrida_fk = c2.id_corrida WHERE c2.ano = c.ano GROUP BY r2.id_construtor_fk) as sub)) as champs GROUP BY construtor),
            pilot_stats AS (SELECT p.nome || ' ' || p.sobrenome as piloto, SUM(CASE WHEN r.posicao_final = 1 THEN 1 ELSE 0 END) as vitorias, SUM(CASE WHEN r.posicao_grid = 1 THEN 1 ELSE 0 END) as poles, SUM(CASE WHEN r.posicao_final <= 3 THEN 1 ELSE 0 END) as podios, SUM(CASE WHEN r.rank_volta_rapida = 1 THEN 1 ELSE 0 END) as voltas_rapidas FROM tbl_resultados r JOIN tbl_pilotos p ON r.id_piloto_fk = p.id_piloto GROUP BY piloto),
            constructor_stats AS (SELECT con.nome as construtor, SUM(CASE WHEN r.posicao_final = 1 THEN 1 ELSE 0 END) as vitorias, SUM(CASE WHEN r.posicao_grid = 1 THEN 1 ELSE 0 END) as poles, SUM(CASE WHEN r.posicao_final <= 3 THEN 1 ELSE 0 END) as podios, SUM(CASE WHEN r.rank_volta_rapida = 1 THEN 1 ELSE 0 END) as voltas_rapidas FROM tbl_resultados r JOIN tbl_construtores con ON r.id_construtor_fk = con.id_construtor GROUP BY construtor)
            SELECT * FROM (SELECT piloto as recordista, titulos as recorde, 'Títulos (Piloto)' as tipo FROM pilot_champs_agg ORDER BY recorde DESC LIMIT 1) a
            UNION ALL
            SELECT * FROM (SELECT construtor as recordista, titulos as recorde, 'Títulos (Equipe)' as tipo FROM constructor_champs_agg ORDER BY recorde DESC LIMIT 1) b
            UNION ALL
            SELECT * FROM (SELECT piloto as recordista, vitorias as recorde, 'Vitórias (Piloto)' as tipo FROM pilot_stats ORDER BY recorde DESC LIMIT 1) c
            UNION ALL
            SELECT * FROM (SELECT construtor as recordista, vitorias as recorde, 'Vitórias (Equipe)' as tipo FROM constructor_stats ORDER BY recorde DESC LIMIT 1) d
            UNION ALL
            SELECT * FROM (SELECT piloto as recordista, poles as recorde, 'Poles (Piloto)' as tipo FROM pilot_stats ORDER BY recorde DESC LIMIT 1) e
            UNION ALL
            SELECT * FROM (SELECT construtor as recordista, poles as recorde, 'Poles (Equipe)' as tipo FROM constructor_stats ORDER BY recorde DESC LIMIT 1) f
            UNION ALL
            SELECT * FROM (SELECT piloto as recordista, podios as recorde, 'Pódios (Piloto)' as tipo FROM pilot_stats ORDER BY recorde DESC LIMIT 1) g
            UNION ALL
            SELECT * FROM (SELECT construtor as recordista, podios as recorde, 'Pódios (Equipe)' as tipo FROM constructor_stats ORDER BY recorde DESC LIMIT 1) h
            UNION ALL
            SELECT * FROM (SELECT piloto as recordista, voltas_rapidas as recorde, 'Voltas Rápidas (Piloto)' as tipo FROM pilot_stats ORDER BY recorde DESC LIMIT 1) i
            UNION ALL
            SELECT * FROM (SELECT construtor as recordista, voltas_rapidas as recorde, 'Voltas Rápidas (Equipe)' as tipo FROM constructor_stats ORDER BY recorde DESC LIMIT 1) j;
        """
        records_df = consultar_dados_df(query_records)
        if not records_df.empty:
            records_df = records_df.set_index('tipo')
            st.markdown("##### Pilotos")
            c1, c2, c3, c4, c5 = st.columns(5)
            c1.metric("🏆 Mais Títulos", records_df.loc['Títulos (Piloto)']['recordista'], f"{int(records_df.loc['Títulos (Piloto)']['recorde'])}")
            c2.metric("🥇 Mais Vitórias", records_df.loc['Vitórias (Piloto)']['recordista'], f"{int(records_df.loc['Vitórias (Piloto)']['recorde'])}")
            c3.metric("🥈 Mais Pódios", records_df.loc['Pódios (Piloto)']['recordista'], f"{int(records_df.loc['Pódios (Piloto)']['recorde'])}")
            c4.metric("⏱️ Mais Poles", records_df.loc['Poles (Piloto)']['recordista'], f"{int(records_df.loc['Poles (Piloto)']['recorde'])}")
            c5.metric("🚀 Mais Voltas R.", records_df.loc['Voltas Rápidas (Piloto)']['recordista'], f"{int(records_df.loc['Voltas Rápidas (Piloto)']['recorde'])}")
            st.markdown("##### Equipes")
            c1, c2, c3, c4, c5 = st.columns(5)
            c1.metric("🏆 Mais Títulos", records_df.loc['Títulos (Equipe)']['recordista'], f"{int(records_df.loc['Títulos (Equipe)']['recorde'])}")
            c2.metric("🥇 Mais Vitórias", records_df.loc['Vitórias (Equipe)']['recordista'], f"{int(records_df.loc['Vitórias (Equipe)']['recorde'])}")
            c3.metric("🥈 Mais Pódios", records_df.loc['Pódios (Equipe)']['recordista'], f"{int(records_df.loc['Pódios (Equipe)']['recorde'])}")
            c4.metric("⏱️ Mais Poles", records_df.loc['Poles (Equipe)']['recordista'], f"{int(records_df.loc['Poles (Equipe)']['recorde'])}")
            c5.metric("🚀 Mais Voltas R.", records_df.loc['Voltas Rápidas (Equipe)']['recordista'], f"{int(records_df.loc['Voltas Rápidas (Equipe)']['recorde'])}")

        st.divider()
        st.subheader("Rankings Top 15 de Todos os Tempos")
        tab_vitorias, tab_podios, tab_poles, tab_voltas_rapidas, tab_titulos = st.tabs(["Vitórias", "Pódios", "Poles", "Voltas Rápidas", "Títulos"])
        
        with tab_vitorias:
            c1, c2 = st.columns(2)
            with c1:
                st.markdown("###### Pilotos com mais vitórias")
                vitorias_p_df = consultar_dados_df("SELECT p.nome || ' ' || p.sobrenome as piloto, COUNT(*) as vitorias FROM tbl_resultados r JOIN tbl_pilotos p ON r.id_piloto_fk = p.id_piloto WHERE r.posicao_final = 1 GROUP BY piloto ORDER BY vitorias DESC LIMIT 15;")
                fig = px.bar(vitorias_p_df, x='vitorias', y='piloto', orientation='h', text_auto=True, color_discrete_sequence=[F1_RED]).update_layout(yaxis={'categoryorder':'total ascending'})
                st.plotly_chart(fig, use_container_width=True)
            with c2:
                st.markdown("###### Equipes com mais vitórias")
                vitorias_e_df = consultar_dados_df("SELECT con.nome as equipe, COUNT(*) as vitorias FROM tbl_resultados r JOIN tbl_construtores con ON r.id_construtor_fk = con.id_construtor WHERE r.posicao_final = 1 GROUP BY equipe ORDER BY vitorias DESC LIMIT 15;")
                fig = px.bar(vitorias_e_df, x='vitorias', y='equipe', orientation='h', text_auto=True, color_discrete_sequence=[F1_GREY]).update_layout(yaxis={'categoryorder':'total ascending'})
                st.plotly_chart(fig, use_container_width=True)

elif pagina_selecionada == "Gerenciamento":
    st.title("✏️ Gerenciamento de Dados (CRUD)")
    tab_create, tab_read, tab_update, tab_delete = st.tabs(["➕ Adicionar", "🔍 Consultar", "🔄 Atualizar", "❌ Deletar"])
    with tab_create:
        st.subheader("Adicionar Novo Piloto")
        with st.form("form_create_piloto", clear_on_submit=True):
            id_piloto = st.number_input("ID do Piloto", min_value=1, step=1)
            ref = st.text_input("Referência (ex: 'hamilton')")
            nome = st.text_input("Primeiro Nome")
            sobrenome = st.text_input("Sobrenome")
            nacionalidade = st.text_input("Nacionalidade")
            submitted = st.form_submit_button("Adicionar Piloto")
            if submitted:
                sql = "INSERT INTO tbl_pilotos (id_piloto, ref_piloto, nome, sobrenome, nacionalidade) VALUES (%s, %s, %s, %s, %s)"
                if executar_comando_sql(sql, (id_piloto, ref, nome, sobrenome, nacionalidade)) is not None:
                    st.success("Piloto adicionado com sucesso!")
    with tab_read:
        st.subheader("Consultar Tabelas")
        opcoes = {"Pilotos": "SELECT * FROM tbl_pilotos", "Equipes": "SELECT * FROM tbl_construtores", "Circuitos": "SELECT * FROM tbl_circuitos"}
        escolha = st.selectbox("Escolha a tabela para visualizar:", options=list(opcoes.keys()))
        df = consultar_dados_df(opcoes[escolha])
        st.dataframe(df, use_container_width=True, height=500)
    with tab_update:
        st.subheader("Atualizar Nacionalidade de um Construtor")
        constr_df = consultar_dados_df("SELECT id_construtor, nome FROM tbl_construtores ORDER BY nome")
        if not constr_df.empty:
            constr_sel = st.selectbox("Selecione o Construtor", options=constr_df["nome"])
            id_constr = constr_df[constr_df["nome"] == constr_sel]["id_construtor"].iloc[0]
            nova_nac = st.text_input("Digite a Nova Nacionalidade", key=f"nac_{id_constr}")
            if st.button("Atualizar Nacionalidade"):
                sql = "UPDATE tbl_construtores SET nacionalidade = %s WHERE id_construtor = %s"
                if executar_comando_sql(sql, (nova_nac, int(id_constr))):
                    st.success(f"Nacionalidade de '{constr_sel}' atualizada!")
    with tab_delete:
        st.subheader("Deletar um Piloto")
        st.warning("CUIDADO: Ação irreversível.", icon="⚠️")
        pilotos_del_df = consultar_dados_df("SELECT id_piloto, nome, sobrenome FROM tbl_pilotos ORDER BY sobrenome")
        if not pilotos_del_df.empty:
            pilotos_del_df["nome_completo"] = pilotos_del_df["nome"] + " " + pilotos_del_df["sobrenome"]
            piloto_del = st.selectbox("Selecione o Piloto a ser deletado", options=pilotos_del_df["nome_completo"], index=None)
            if piloto_del:
                if st.button(f"DELETAR {piloto_del}", type="primary"):
                    id_piloto_del = pilotos_del_df[pilotos_del_df["nome_completo"] == piloto_del]["id_piloto"].iloc[0]
                    sql = "DELETE FROM tbl_pilotos WHERE id_piloto = %s"
                    if executar_comando_sql(sql, (int(id_piloto_del),)):
                        st.success(f"Piloto '{piloto_del}' deletado!")
                        st.rerun()
