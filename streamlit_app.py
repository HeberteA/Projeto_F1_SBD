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
            
            if piloto_selecionado:
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
                        COALESCE((SELECT titulos FROM pilot_champs), 0) as titulos
                    FROM tbl_resultados WHERE id_piloto_fk = %(id_piloto)s;
                """
                kpi_df = consultar_dados_df(kpi_query, params={"id_piloto": id_piloto, "nome_piloto": piloto_selecionado})

                if not kpi_df.empty:
                    kpi_data = kpi_df.iloc[0]
                    col1, col2, col3, col4, col5, col6 = st.columns(6)
                    col1.metric("🏆 Títulos", int(kpi_data["titulos"]))
                    col2.metric("🏎️ Corridas", int(kpi_data["total_corridas"]))
                    col3.metric("🥇 Vitórias", int(kpi_data["vitorias"]))
                    col4.metric("🥈 Pódios", int(kpi_data["podios"]))
                    col5.metric("⏱️ Poles", int(kpi_data["poles"]))
                    col6.metric(" Média Pontos", f"{kpi_data['media_pontos']:.2f}")

                st.divider()

                col_chart1, col_chart2 = st.columns(2)
                
                with col_chart1:
                    st.subheader("Pontos por Temporada")
                    pontos_query = "SELECT c.ano, SUM(r.pontos) as pontos FROM tbl_resultados r JOIN tbl_corridas c ON r.id_corrida_fk = c.id_corrida WHERE r.id_piloto_fk = %(id)s GROUP BY c.ano ORDER BY c.ano;"
                    pontos_df = consultar_dados_df(pontos_query, params={'id': id_piloto})
                    if not pontos_df.empty:
                        fig_pontos_piloto = px.bar(pontos_df, x='ano', y='pontos', text_auto=True, color_discrete_sequence=[F1_RED], labels={'ano': 'Temporada', 'pontos': 'Pontos'})
                        st.plotly_chart(fig_pontos_piloto, use_container_width=True)
                
                with col_chart2:
                    st.subheader("Posição Média (Grid vs. Final)")
                    pos_query = "SELECT AVG(posicao_grid) as media_grid, AVG(posicao_final) as media_final FROM tbl_resultados WHERE id_piloto_fk = %(id)s AND posicao_final IS NOT NULL;"
                    pos_df = consultar_dados_df(pos_query, params={'id': id_piloto})
                    if not pos_df.empty and pos_df.iloc[0]['media_grid'] is not None:
                        pos_df_melted = pos_df.melt(var_name='Tipo de Posição', value_name='Posição Média')
                        pos_df_melted['Tipo de Posição'] = pos_df_melted['Tipo de Posição'].map({'media_grid': 'Grid', 'media_final': 'Final'})
                        fig_pos_piloto = px.bar(pos_df_melted, x='Tipo de Posição', y='Posição Média', text_auto='.2f', color='Tipo de Posição', color_discrete_sequence=[F1_GREY, F1_RED])
                        fig_pos_piloto.update_layout(showlegend=False)
                        st.plotly_chart(fig_pos_piloto, use_container_width=True)

                col_chart3, col_chart4 = st.columns(2)
                with col_chart3:
                    st.subheader("Distribuição de Resultados")
                    dist_query = "SELECT CASE WHEN posicao_final IS NULL THEN 'Não Terminou (DNF)' WHEN posicao_final BETWEEN 1 AND 3 THEN 'Pódio' WHEN posicao_final BETWEEN 4 AND 10 THEN 'Pontos (4-10)' ELSE 'Fora dos Pontos' END as resultado, COUNT(*) as total FROM tbl_resultados WHERE id_piloto_fk = %(id)s GROUP BY resultado ORDER BY total DESC;"
                    dist_df = consultar_dados_df(dist_query, params={'id': id_piloto})
                    if not dist_df.empty:
                        fig_dist_piloto = px.pie(dist_df, names='resultado', values='total', hole=0.3, color_discrete_sequence=F1_PALETTE)
                        st.plotly_chart(fig_dist_piloto, use_container_width=True)
                
                with col_chart4:
                    st.subheader("Comparativo Grid vs. Final por Ano")
                    grid_final_ano_query = "SELECT c.ano, AVG(r.posicao_grid) as media_grid, AVG(r.posicao_final) as media_final FROM tbl_resultados r JOIN tbl_corridas c ON r.id_corrida_fk = c.id_corrida WHERE r.id_piloto_fk = %(id)s GROUP BY c.ano ORDER BY c.ano;"
                    grid_final_ano_df = consultar_dados_df(grid_final_ano_query, params={'id': id_piloto})
                    if not grid_final_ano_df.empty:
                        fig_grid_final_piloto = px.line(grid_final_ano_df, x='ano', y=['media_grid', 'media_final'], labels={'value': 'Posição Média', 'ano': 'Temporada', 'variable': 'Tipo'}, color_discrete_map={'media_grid': F1_GREY, 'media_final': F1_RED})
                        fig_grid_final_piloto.update_traces(mode='markers+lines')
                        st.plotly_chart(fig_grid_final_piloto, use_container_width=True)

    with tab_equipe:
        st.header("Análise de Performance de Equipe")
        equipes_df = consultar_dados_df("SELECT id_construtor, nome, nacionalidade FROM tbl_construtores ORDER BY nome")
        if not equipes_df.empty:
            equipe_selecionada = st.selectbox("Selecione uma Equipe", options=equipes_df["nome"], index=None, placeholder="Digite o nome de uma equipe...", key="sel_equipe")

            if equipe_selecionada:
                equipe_info = equipes_df[equipes_df["nome"] == equipe_selecionada].iloc[0]
                id_equipe = int(equipe_info["id_construtor"])
                
                with st.container(border=True):
                    c1, c2, c3 = st.columns(3)
                    with c1:
                        st.markdown(f"<h2 style='text-align: left;'>{equipe_info['nome']}</h2>", unsafe_allow_html=True)
                    with c2:
                        st.metric("País", str(equipe_info['nacionalidade']))
                    with c3:
                        total_pilotos_query = "SELECT COUNT(DISTINCT id_piloto_fk) as total_pilotos FROM tbl_resultados WHERE id_construtor_fk = %(id)s;"
                        total_pilotos_df = consultar_dados_df(total_pilotos_query, params={'id': id_equipe})
                        if not total_pilotos_df.empty:
                            st.metric("Total de Pilotos na História", total_pilotos_df.iloc[0]['total_pilotos'])

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
                        SUM(pontos) as total_pontos,
                        COALESCE((SELECT titulos FROM constructor_champs), 0) as titulos
                    FROM tbl_resultados WHERE id_construtor_fk = %(id_equipe)s;
                """
                kpi_equipe_df = consultar_dados_df(kpi_equipe_query, params={"id_equipe": id_equipe, "nome_equipe": equipe_selecionada})
                
                if not kpi_equipe_df.empty:
                    kpi_equipe_data = kpi_equipe_df.iloc[0]
                    c1, c2, c3, c4, c5 = st.columns(5)
                    c1.metric("🏆 Títulos", int(kpi_equipe_data["titulos"]))
                    c2.metric("🏎️ Corridas", int(kpi_equipe_data["total_corridas"]))
                    c3.metric("🥇 Vitórias", int(kpi_equipe_data["vitorias"]))
                    c4.metric("🥈 Pódios", int(kpi_equipe_data["podios"]))
                    c5.metric("⏱️ Poles", int(kpi_equipe_data["poles"]))

                st.divider()

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

                st.subheader("Evolução de Pódios por Temporada")
                podios_temporada_query = "SELECT c.ano, SUM(CASE WHEN r.posicao_final <= 3 THEN 1 ELSE 0 END) as podios FROM tbl_resultados r JOIN tbl_corridas c ON r.id_corrida_fk = c.id_corrida WHERE r.id_construtor_fk = %(id)s GROUP BY c.ano HAVING SUM(CASE WHEN r.posicao_final <= 3 THEN 1 ELSE 0 END) > 0 ORDER BY c.ano;"
                podios_temporada_df = consultar_dados_df(podios_temporada_query, params={'id': id_equipe})
                if not podios_temporada_df.empty:
                    fig_podios_equipe = px.line(podios_temporada_df, x='ano', y='podios', text='podios', markers=True, color_discrete_sequence=[F1_GREY])
                    fig_podios_equipe.update_traces(textposition="top center")
                    st.plotly_chart(fig_podios_equipe, use_container_width=True)
                
                st.subheader("Lista de Vitórias da Equipe")
                vitorias_equipe_query = f"SELECT c.ano, c.nome_gp, p.nome || ' ' || p.sobrenome as piloto FROM tbl_resultados r JOIN tbl_corridas c ON r.id_corrida_fk = c.id_corrida JOIN tbl_pilotos p ON r.id_piloto_fk = p.id_piloto WHERE r.id_construtor_fk = {id_equipe} AND r.posicao_final = 1 ORDER BY c.ano DESC;"
                vitorias_equipe_df = consultar_dados_df(vitorias_equipe_query)
                st.dataframe(vitorias_equipe_df, use_container_width=True)

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
                    
                    with st.spinner("Analisando dados do Head-to-Head..."):
                        h2h_data_query = """
                            WITH results_filtered AS (
                                SELECT r.* FROM tbl_resultados r
                                JOIN tbl_corridas c ON r.id_corrida_fk = c.id_corrida
                                WHERE c.ano BETWEEN %(sy)s AND %(ey)s AND r.id_piloto_fk IN (%(p1)s, %(p2)s)
                            ),
                            pilot_champs AS (
                                SELECT piloto, COUNT(*) as titulos FROM (
                                    SELECT p.nome || ' ' || p.sobrenome as piloto FROM tbl_resultados r
                                    JOIN tbl_corridas c ON r.id_corrida_fk = c.id_corrida JOIN tbl_pilotos p ON r.id_piloto_fk = p.id_piloto
                                    WHERE c.ano BETWEEN %(sy)s AND %(ey)s
                                    GROUP BY c.ano, p.nome, p.sobrenome, r.id_piloto_fk
                                    HAVING SUM(r.pontos) = (SELECT MAX(total_pontos) FROM (SELECT SUM(pontos) as total_pontos FROM tbl_resultados r2 JOIN tbl_corridas c2 ON r2.id_corrida_fk = c2.id_corrida WHERE c2.ano = c.ano GROUP BY r2.id_piloto_fk) as sub)
                                ) as champs WHERE piloto IN (%(n1)s, %(n2)s) GROUP BY piloto
                            )
                            SELECT
                                p.id_piloto, p.nome || ' ' || p.sobrenome as piloto_nome, p.nacionalidade, p.numero,
                                COUNT(rf.id_resultado) AS total_corridas,
                                SUM(CASE WHEN rf.posicao_final = 1 THEN 1 ELSE 0 END) AS vitorias,
                                SUM(CASE WHEN rf.posicao_grid = 1 THEN 1 ELSE 0 END) AS poles,
                                SUM(CASE WHEN rf.posicao_final <= 3 THEN 1 ELSE 0 END) AS podios,
                                SUM(rf.pontos) AS total_pontos,
                                AVG(rf.posicao_grid) as media_grid, AVG(rf.posicao_final) as media_final,
                                COALESCE((SELECT titulos FROM pilot_champs pc WHERE pc.piloto = p.nome || ' ' || p.sobrenome), 0) as titulos
                            FROM tbl_pilotos p
                            LEFT JOIN results_filtered rf ON p.id_piloto = rf.id_piloto_fk
                            WHERE p.id_piloto IN (%(p1)s, %(p2)s)
                            GROUP BY p.id_piloto, p.nome, p.sobrenome, p.nacionalidade, p.numero;
                        """
                        params = {'p1': id_piloto1, 'p2': id_piloto2, 'n1': piloto1_nome, 'n2': piloto2_nome, 'sy': start_year, 'ey': end_year}
                        h2h_df = consultar_dados_df(h2h_data_query, params=params)
                        
                        if not h2h_df.empty and len(h2h_df) == 2:
                            piloto1_data = h2h_df[h2h_df['id_piloto'] == id_piloto1].iloc[0]
                            piloto2_data = h2h_df[h2h_df['id_piloto'] == id_piloto2].iloc[0]
                            
                            col1, col2 = st.columns(2)
                            with col1:
                                with st.container(border=True):
                                    st.markdown(f"<h5 style='text-align: center;'>{piloto1_data['piloto_nome']}</h5>", unsafe_allow_html=True)
                                    c1_sub, c2_sub, c3_sub = st.columns(3)
                                    c1_sub.metric("País", str(piloto1_data['nacionalidade']))
                                    c2_sub.metric("Número", "N/A" if pd.isna(piloto1_data['numero']) else int(piloto1_data['numero']))
                                    vitorias_equipe_p1_q = "SELECT con.nome FROM tbl_resultados r JOIN tbl_construtores con ON r.id_construtor_fk = con.id_construtor JOIN tbl_corridas c ON r.id_corrida_fk = c.id_corrida WHERE r.id_piloto_fk = %(id)s AND c.ano BETWEEN %(sy)s AND %(ey)s AND r.posicao_final = 1 GROUP BY con.nome ORDER BY COUNT(*) DESC LIMIT 1;"
                                    vitorias_equipe_p1_df = consultar_dados_df(vitorias_equipe_p1_q, params={'id': id_piloto1, 'sy': start_year, 'ey': end_year})
                                    c3_sub.metric("Equipe (Mais Vitórias)", vitorias_equipe_p1_df.iloc[0]['nome'] if not vitorias_equipe_p1_df.empty else "Nenhuma")
                                st.subheader(" ") 
                                c1, c2, c3 = st.columns(3)
                                c1.metric("Títulos", int(piloto1_data["titulos"]))
                                c2.metric("Vitórias", int(piloto1_data["vitorias"]))
                                c3.metric("Pódios", int(piloto1_data["podios"]))
                                c4, c5, c6 = st.columns(3)
                                c4.metric("Poles", int(piloto1_data["poles"]))
                                c5.metric("Corridas", int(piloto1_data["total_corridas"]))
                                c6.metric("Pontos", int(piloto1_data["total_pontos"]))
                            with col2:
                                with st.container(border=True):
                                    st.markdown(f"<h5 style='text-align: center;'>{piloto2_data['piloto_nome']}</h5>", unsafe_allow_html=True)
                                    c1_sub, c2_sub, c3_sub = st.columns(3)
                                    c1_sub.metric("País", str(piloto2_data['nacionalidade']))
                                    c2_sub.metric("Número", "N/A" if pd.isna(piloto2_data['numero']) else int(piloto2_data['numero']))
                                    vitorias_equipe_p2_q = "SELECT con.nome FROM tbl_resultados r JOIN tbl_construtores con ON r.id_construtor_fk = con.id_construtor JOIN tbl_corridas c ON r.id_corrida_fk = c.id_corrida WHERE r.id_piloto_fk = %(id)s AND c.ano BETWEEN %(sy)s AND %(ey)s AND r.posicao_final = 1 GROUP BY con.nome ORDER BY COUNT(*) DESC LIMIT 1;"
                                    vitorias_equipe_p2_df = consultar_dados_df(vitorias_equipe_p2_q, params={'id': id_piloto2, 'sy': start_year, 'ey': end_year})
                                    c3_sub.metric("Equipe (Mais Vitórias)", vitorias_equipe_p2_df.iloc[0]['nome'] if not vitorias_equipe_p2_df.empty else "Nenhuma")
                                st.subheader(" ")
                                c1, c2, c3 = st.columns(3)
                                c1.metric("Títulos", int(piloto2_data["titulos"]))
                                c2.metric("Vitórias", int(piloto2_data["vitorias"]))
                                c3.metric("Pódios", int(piloto2_data["podios"]))
                                c4, c5, c6 = st.columns(3)
                                c4.metric("Poles", int(piloto2_data["poles"]))
                                c5.metric("Corridas", int(piloto2_data["total_corridas"]))
                                c6.metric("Pontos", int(piloto2_data["total_pontos"]))
                                
                    st.divider()
                    st.subheader(f"Análise Gráfica ({start_year}-{end_year})")
                    pos_df_p1 = pd.DataFrame({'Tipo de Posição': ['Grid', 'Final'], 'Posição Média': [piloto1_data['media_grid'], piloto1_data['media_final']], 'piloto': piloto1_nome})
                    pos_df_p2 = pd.DataFrame({'Tipo de Posição': ['Grid', 'Final'], 'Posição Média': [piloto2_data['media_grid'], piloto2_data['media_final']], 'piloto': piloto2_nome})
                    pos_h2h_df = pd.concat([pos_df_p1, pos_df_p2])
                    fig_pos_h2h = px.bar(pos_h2h_df, x='Tipo de Posição', y='Posição Média', color='piloto', barmode='group', text_auto='.2f', labels={'Posição Média': 'Posição Média', 'piloto': 'Piloto', 'Tipo de Posição': ''}, color_discrete_map={piloto1_nome: F1_RED, piloto2_nome: F1_GREY}, title="Posição Média (Grid vs. Final)")
                    st.plotly_chart(fig_pos_h2h, use_container_width=True)


                    st.divider()
                    st.subheader("Confronto Direto (em corridas que ambos participaram)")

                    confronto_query = f"""
                        WITH corridas_filtradas AS (
                            SELECT id_corrida FROM tbl_corridas WHERE ano BETWEEN {start_year} AND {end_year}
                        ),
                        corridas_comuns AS (
                            SELECT id_corrida_fk FROM tbl_resultados WHERE id_piloto_fk = {id_piloto1} AND id_corrida_fk IN (SELECT id_corrida FROM corridas_filtradas)
                            INTERSECT
                            SELECT id_corrida_fk FROM tbl_resultados WHERE id_piloto_fk = {id_piloto2} AND id_corrida_fk IN (SELECT id_corrida FROM corridas_filtradas)
                        )
                        SELECT id_corrida_fk,
                               MAX(CASE WHEN id_piloto_fk = {id_piloto1} THEN posicao_final END) as p1_pos,
                               MAX(CASE WHEN id_piloto_fk = {id_piloto2} THEN posicao_final END) as p2_pos
                        FROM tbl_resultados
                        WHERE id_corrida_fk IN (SELECT id_corrida_fk FROM corridas_comuns)
                        GROUP BY id_corrida_fk
                    """
                    confronto_df = consultar_dados_df(confronto_query, params=params)
                        if not confronto_df.empty:
                            confronto_df.dropna(inplace=True) 
                            p1_a_frente = (confronto_df['p1_pos'] < confronto_df['p2_pos']).sum()
                            p2_a_frente = (confronto_df['p2_pos'] < confronto_df['p1_pos']).sum()
                            fig_confronto_h2h = px.bar(x=[piloto1_nome, piloto2_nome], y=[p1_a_frente, p2_a_frente], labels={'x': 'Piloto', 'y': 'Vezes que terminou à frente'}, color=[piloto1_nome, piloto2_nome], color_discrete_map={piloto1_nome: F1_RED, piloto2_nome: F1_GREY}, text_auto=True)
                            fig_confronto_h2h.update_layout(showlegend=False)
                            st.plotly_chart(fig_confronto_h2h, use_container_width=True)

        else:
            st.error("Não foi possível carregar os dados para o filtro de temporada. Verifique a conexão com o banco de dados e se a tabela 'tbl_corridas' contém dados.")

    with tab_circ:
        st.header("Análise por Circuito")
        circuitos_df = consultar_dados_df("SELECT id_circuito, nome, cidade, pais FROM tbl_circuitos ORDER BY nome")
        if not circuitos_df.empty:
            circuito_nome = st.selectbox("Selecione um Circuito", options=circuitos_df["nome"], index=None, key="sel_circuito")
            if circuito_nome:
                circuito_info = circuitos_df[circuitos_df["nome"] == circuito_nome].iloc[0]
                id_circuito = int(circuito_info["id_circuito"])
                
                st.subheader(circuito_info['nome'])
                with st.container(border=True):
                    c1, c2 = st.columns(2)
                    c1.metric("Cidade", circuito_info['cidade'])
                    c2.metric("País", circuito_info['pais'])
                
                st.subheader(f"Resumo Histórico do Circuito")
                
                kpi_circ_query = f"""
                    WITH poles AS (
                        SELECT COUNT(*) as total_poles FROM tbl_resultados r JOIN tbl_corridas c ON r.id_corrida_fk = c.id_corrida WHERE c.id_circuito_fk={id_circuito} AND r.posicao_grid = 1
                    ), wins_from_pole AS (
                        SELECT COUNT(*) as wins_fp FROM tbl_resultados r JOIN tbl_corridas c ON r.id_corrida_fk = c.id_corrida WHERE c.id_circuito_fk={id_circuito} AND r.posicao_grid = 1 AND r.posicao_final = 1
                    )
                    SELECT
                        (SELECT p.nome || ' ' || p.sobrenome FROM tbl_resultados r JOIN tbl_pilotos p ON r.id_piloto_fk=p.id_piloto JOIN tbl_corridas c ON r.id_corrida_fk=c.id_corrida WHERE c.id_circuito_fk={id_circuito} AND r.posicao_final=1 GROUP BY p.nome, p.sobrenome ORDER BY COUNT(*) DESC LIMIT 1) as maior_vencedor,
                        (SELECT con.nome FROM tbl_resultados r JOIN tbl_construtores con ON r.id_construtor_fk=con.id_construtor JOIN tbl_corridas c ON r.id_corrida_fk=c.id_corrida WHERE c.id_circuito_fk={id_circuito} AND r.posicao_final=1 GROUP BY con.nome ORDER BY COUNT(*) DESC LIMIT 1) as equipe_vitoriosa,
                        (SELECT p.nome || ' ' || p.sobrenome FROM tbl_resultados r JOIN tbl_pilotos p ON r.id_piloto_fk=p.id_piloto JOIN tbl_corridas c ON r.id_corrida_fk=c.id_corrida WHERE c.id_circuito_fk={id_circuito} AND r.posicao_grid=1 GROUP BY p.nome, p.sobrenome ORDER BY COUNT(*) DESC LIMIT 1) as maior_pole,
                        (SELECT CAST(wins_fp AS FLOAT) / total_poles * 100 FROM poles, wins_from_pole) as pole_win_rate
                    FROM tbl_corridas WHERE id_circuito_fk={id_circuito} LIMIT 1;
                """
                kpi_circ_df = consultar_dados_df(kpi_circ_query).iloc[0]
                c1, c2, c3, c4 = st.columns(4)
                c1.metric("Maior Vencedor", str(kpi_circ_df["maior_vencedor"]))
                c2.metric("Equipe com Mais Vitórias", str(kpi_circ_df["equipe_vitoriosa"]))
                c3.metric("Recordista de Poles", str(kpi_circ_df["maior_pole"]))
                c4.metric("% Vitórias da Pole", f"{kpi_circ_df['pole_win_rate']:.1f}%")
                st.divider()

                g1, g2 = st.columns(2)
                with g1:
                    st.subheader("Top 10 Pilotos Vencedores")
                    vencedores_query = "SELECT p.nome || ' ' || p.sobrenome as piloto, COUNT(*) as vitorias FROM tbl_resultados r JOIN tbl_corridas c ON r.id_corrida_fk=c.id_corrida JOIN tbl_pilotos p ON r.id_piloto_fk=p.id_piloto WHERE c.id_circuito_fk=%(id)s AND r.posicao_final=1 GROUP BY piloto ORDER BY vitorias DESC LIMIT 10;"
                    vencedores_df = consultar_dados_df(vencedores_query, params={'id': id_circuito})
                    if not vencedores_df.empty:
                        fig_vencedores_circ = px.bar(vencedores_df, x='vitorias', y='piloto', orientation='h', color_discrete_sequence=[F1_RED], text_auto=True)
                        fig_vencedores_circ.update_layout(yaxis={'categoryorder':'total ascending'})
                        st.plotly_chart(fig_vencedores_circ, use_container_width=True)
                with g2:
                    st.subheader("Top 10 Equipes Vitoriosas")
                    vencedores_eq_query = "SELECT con.nome as equipe, COUNT(*) as vitorias FROM tbl_resultados r JOIN tbl_corridas c ON r.id_corrida_fk=c.id_corrida JOIN tbl_construtores con ON r.id_construtor_fk=con.id_construtor WHERE c.id_circuito_fk=%(id)s AND r.posicao_final=1 GROUP BY equipe ORDER BY vitorias DESC LIMIT 10;"
                    vencedores_eq_df = consultar_dados_df(vencedores_eq_query, params={'id': id_circuito})
                    if not vencedores_eq_df.empty:
                        fig_vencedores_eq_circ = px.bar(vencedores_eq_df, x='vitorias', y='equipe', orientation='h', color_discrete_sequence=[F1_GREY], text_auto=True)
                        fig_vencedores_eq_circ.update_layout(yaxis={'categoryorder':'total ascending'})
                        st.plotly_chart(fig_vencedores_eq_circ, use_container_width=True)

                g3, g4 = st.columns(2)
                with g3:
                    st.subheader("Top 10 Pilotos (Poles)")
                    poles_piloto_query = "SELECT p.nome || ' ' || p.sobrenome as piloto, COUNT(*) as poles FROM tbl_resultados r JOIN tbl_corridas c ON r.id_corrida_fk=c.id_corrida JOIN tbl_pilotos p ON r.id_piloto_fk=p.id_piloto WHERE c.id_circuito_fk=%(id)s AND r.posicao_grid=1 GROUP BY piloto ORDER BY poles DESC LIMIT 10;"
                    poles_piloto_df = consultar_dados_df(poles_piloto_query, params={'id': id_circuito})
                    if not poles_piloto_df.empty:
                        fig_poles_piloto_circ = px.bar(poles_piloto_df, x='poles', y='piloto', orientation='h', color_discrete_sequence=[F1_RED], text_auto=True)
                        fig_poles_piloto_circ.update_layout(yaxis={'categoryorder':'total ascending'})
                        st.plotly_chart(fig_poles_piloto_circ, use_container_width=True)
                with g4:
                    st.subheader("Poles por Equipe")
                    poles_equipe_query = "SELECT con.nome as equipe, COUNT(*) as poles FROM tbl_resultados r JOIN tbl_corridas c ON r.id_corrida_fk = c.id_corrida JOIN tbl_construtores con ON r.id_construtor_fk = con.id_construtor WHERE c.id_circuito_fk = %(id)s AND r.posicao_grid = 1 GROUP BY equipe ORDER BY poles DESC;"
                    poles_equipe_df = consultar_dados_df(poles_equipe_query, params={'id': id_circuito})
                    if not poles_equipe_df.empty:
                        fig_poles_equipe_circ = px.pie(poles_equipe_df, names='equipe', values='poles', hole=0.3, color_discrete_sequence=F1_PALETTE)
                        st.plotly_chart(fig_poles_equipe_circ, use_container_width=True)

    with tab_records:
        st.header("Hall da Fama: Recordes Históricos da F1")
        
        query_records = """
            WITH pilot_champs_yearly AS (SELECT c.ano, p.nome || ' ' || p.sobrenome as piloto FROM tbl_resultados r JOIN tbl_corridas c ON r.id_corrida_fk = c.id_corrida JOIN tbl_pilotos p ON r.id_piloto_fk = p.id_piloto GROUP BY c.ano, p.nome, p.sobrenome HAVING SUM(r.pontos) = (SELECT MAX(total_pontos) FROM (SELECT SUM(pontos) as total_pontos FROM tbl_resultados r2 JOIN tbl_corridas c2 ON r2.id_corrida_fk = c2.id_corrida WHERE c2.ano = c.ano GROUP BY r2.id_piloto_fk) as sub)),
            pilot_champs_agg AS (SELECT piloto, COUNT(*) as titulos FROM pilot_champs_yearly GROUP BY piloto),
            constructor_champs_yearly AS (SELECT c.ano, con.nome as construtor FROM tbl_resultados r JOIN tbl_corridas c ON r.id_corrida_fk = c.id_corrida JOIN tbl_construtores con ON r.id_construtor_fk = con.id_construtor GROUP BY c.ano, con.nome HAVING SUM(r.pontos) = (SELECT MAX(total_pontos) FROM (SELECT SUM(pontos) as total_pontos FROM tbl_resultados r2 JOIN tbl_corridas c2 ON r2.id_corrida_fk = c2.id_corrida WHERE c2.ano = c.ano GROUP BY r2.id_construtor_fk) as sub)),
            constructor_champs_agg AS (SELECT construtor, COUNT(*) as titulos FROM constructor_champs_yearly GROUP BY construtor),
            pilot_stats AS (SELECT p.nome || ' ' || p.sobrenome as piloto, SUM(CASE WHEN r.posicao_final = 1 THEN 1 ELSE 0 END) as vitorias, SUM(CASE WHEN r.posicao_grid = 1 THEN 1 ELSE 0 END) as poles, SUM(CASE WHEN r.posicao_final <= 3 THEN 1 ELSE 0 END) as podios FROM tbl_resultados r JOIN tbl_pilotos p ON r.id_piloto_fk = p.id_piloto GROUP BY piloto),
            constructor_stats AS (SELECT con.nome as construtor, SUM(CASE WHEN r.posicao_final = 1 THEN 1 ELSE 0 END) as vitorias, SUM(CASE WHEN r.posicao_grid = 1 THEN 1 ELSE 0 END) as poles, SUM(CASE WHEN r.posicao_final <= 3 THEN 1 ELSE 0 END) as podios FROM tbl_resultados r JOIN tbl_construtores con ON r.id_construtor_fk = con.id_construtor GROUP BY construtor)
            SELECT
                (SELECT piloto FROM pilot_champs_agg ORDER BY titulos DESC LIMIT 1) as recordista_titulos_piloto, (SELECT titulos FROM pilot_champs_agg ORDER BY titulos DESC LIMIT 1) as recorde_titulos_piloto,
                (SELECT construtor FROM constructor_champs_agg ORDER BY titulos DESC LIMIT 1) as recordista_titulos_equipe, (SELECT titulos FROM constructor_champs_agg ORDER BY titulos DESC LIMIT 1) as recorde_titulos_equipe,
                (SELECT piloto FROM pilot_stats ORDER BY vitorias DESC LIMIT 1) as recordista_vitorias_piloto, (SELECT vitorias FROM pilot_stats ORDER BY vitorias DESC LIMIT 1) as recorde_vitorias_piloto,
                (SELECT construtor FROM constructor_stats ORDER BY vitorias DESC LIMIT 1) as recordista_vitorias_equipe, (SELECT vitorias FROM constructor_stats ORDER BY vitorias DESC LIMIT 1) as recorde_vitorias_equipe,
                (SELECT piloto FROM pilot_stats ORDER BY poles DESC LIMIT 1) as recordista_poles_piloto, (SELECT poles FROM pilot_stats ORDER BY poles DESC LIMIT 1) as recorde_poles_piloto,
                (SELECT construtor FROM constructor_stats ORDER BY poles DESC LIMIT 1) as recordista_poles_equipe, (SELECT poles FROM constructor_stats ORDER BY poles DESC LIMIT 1) as recorde_poles_equipe,
                (SELECT piloto FROM pilot_stats ORDER BY podios DESC LIMIT 1) as recordista_podios_piloto, (SELECT podios FROM pilot_stats ORDER BY podios DESC LIMIT 1) as recorde_podios_piloto,
                (SELECT construtor FROM constructor_stats ORDER BY podios DESC LIMIT 1) as recordista_podios_equipe, (SELECT podios FROM constructor_stats ORDER BY podios DESC LIMIT 1) as recorde_podios_equipe;
        """
        
        records_df = consultar_dados_df(query_records)
        if not records_df.empty:
            rec = records_df.iloc[0]
            st.subheader("Recordes de Pilotos")
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("🏆 Mais Títulos", rec['recordista_titulos_piloto'], f"{int(rec['recorde_titulos_piloto'])} Títulos")
            c2.metric("🥇 Mais Vitórias", rec['recordista_vitorias_piloto'], f"{int(rec['recorde_vitorias_piloto'])} Vitórias")
            c3.metric("⏱️ Mais Poles", rec['recordista_poles_piloto'], f"{int(rec['recorde_poles_piloto'])} Poles")
            c4.metric("🥈 Mais Pódios", rec['recordista_podios_piloto'], f"{int(rec['recorde_podios_piloto'])} Pódios")
            
            st.subheader("Recordes de Equipes (Construtores)")
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("🏆 Mais Títulos", rec['recordista_titulos_equipe'], f"{int(rec['recorde_titulos_equipe'])} Títulos")
            c2.metric("🥇 Mais Vitórias", rec['recordista_vitorias_equipe'], f"{int(rec['recorde_vitorias_equipe'])} Vitórias")
            c3.metric("⏱️ Mais Poles", rec['recordista_poles_equipe'], f"{int(rec['recorde_poles_equipe'])} Poles")
            c4.metric("🥈 Mais Pódios", rec['recordista_podios_equipe'], f"{int(rec['recorde_podios_equipe'])} Pódios")
            
        st.divider()

        col1, col2 = st.columns(2)
        with col1:
            st.subheader("Ranking de Títulos de Pilotos")
            query_pilot_champs_rank = "WITH yearly_points AS (SELECT c.ano, p.nome || ' ' || p.sobrenome as piloto, SUM(r.pontos) as total_pontos FROM tbl_resultados r JOIN tbl_corridas c ON r.id_corrida_fk = c.id_corrida JOIN tbl_pilotos p ON r.id_piloto_fk = p.id_piloto GROUP BY c.ano, piloto), yearly_max_points AS (SELECT ano, MAX(total_pontos) as max_pontos FROM yearly_points GROUP BY ano), champions AS (SELECT yp.ano, yp.piloto FROM yearly_points yp JOIN yearly_max_points ymp ON yp.ano = ymp.ano AND yp.total_pontos = ymp.max_pontos) SELECT piloto, COUNT(*) as titulos FROM champions GROUP BY piloto ORDER BY titulos DESC LIMIT 15;"
            pilot_champs_df = consultar_dados_df(query_pilot_champs_rank)
            if not pilot_champs_df.empty:
                fig_pilot_champs_rank = px.bar(pilot_champs_df, x='titulos', y='piloto', orientation='h', text_auto=True, labels={'titulos': 'Títulos Mundiais', 'piloto': 'Piloto'}, color_discrete_sequence=[F1_RED])
                fig_pilot_champs_rank.update_layout(yaxis={'categoryorder':'total ascending'})
                st.plotly_chart(fig_pilot_champs_rank, use_container_width=True)
        with col2:
            st.subheader("Ranking de Títulos de Construtores")
            query_constructor_champs_rank = "WITH yearly_points AS (SELECT c.ano, con.nome as construtor, SUM(r.pontos) as total_pontos FROM tbl_resultados r JOIN tbl_corridas c ON r.id_corrida_fk = c.id_corrida JOIN tbl_construtores con ON r.id_construtor_fk = con.id_construtor GROUP BY c.ano, construtor), yearly_max_points AS (SELECT ano, MAX(total_pontos) as max_pontos FROM yearly_points GROUP BY ano), champions AS (SELECT yp.ano, yp.construtor FROM yearly_points yp JOIN yearly_max_points ymp ON yp.ano = ymp.ano AND yp.total_pontos = ymp.max_pontos) SELECT construtor, COUNT(*) as titulos FROM champions GROUP BY construtor ORDER BY titulos DESC LIMIT 15;"
            constructor_champs_df = consultar_dados_df(query_constructor_champs_rank)
            if not constructor_champs_df.empty:
                fig_constructor_champs_rank = px.bar(constructor_champs_df, x='titulos', y='construtor', orientation='h', text_auto=True, labels={'titulos': 'Títulos Mundais', 'construtor': 'Equipe'}, color_discrete_sequence=[F1_GREY])
                fig_constructor_champs_rank.update_layout(yaxis={'categoryorder':'total ascending'})
                st.plotly_chart(fig_constructor_champs_rank, use_container_width=True)
                
        st.divider()

        col1, col2 = st.columns(2)
        with col1:
            st.subheader("Títulos de Pilotos")
            query_pilot_champs = """
                WITH yearly_points AS (
                    SELECT c.ano, r.id_piloto_fk, p.nome || ' ' || p.sobrenome as piloto, SUM(r.pontos) as total_pontos
                    FROM tbl_resultados r
                    JOIN tbl_corridas c ON r.id_corrida_fk = c.id_corrida
                    JOIN tbl_pilotos p ON r.id_piloto_fk = p.id_piloto
                    GROUP BY c.ano, r.id_piloto_fk, piloto
                ),
                yearly_max_points AS (
                    SELECT ano, MAX(total_pontos) as max_pontos
                    FROM yearly_points
                    GROUP BY ano
                ),
                champions AS (
                    SELECT yp.ano, yp.piloto
                    FROM yearly_points yp
                    JOIN yearly_max_points ymp ON yp.ano = ymp.ano AND yp.total_pontos = ymp.max_pontos
                )
                SELECT piloto, COUNT(*) as titulos
                FROM champions
                GROUP BY piloto
                ORDER BY titulos DESC
                LIMIT 15;
            """
            pilot_champs_df = consultar_dados_df(query_pilot_champs)
            if not pilot_champs_df.empty:
                fig = px.bar(pilot_champs_df, x='titulos', y='piloto', orientation='h', text_auto=True,
                             labels={'titulos': 'Títulos Mundiais', 'piloto': 'Piloto'},
                             color_discrete_sequence=[F1_RED])
                fig.update_layout(yaxis={'categoryorder':'total ascending'})
                st.plotly_chart(fig, use_container_width=True)

        with col2:
            st.subheader("Títulos de Construtores")
            query_constructor_champs = """
                WITH yearly_points AS (
                    SELECT c.ano, r.id_construtor_fk, con.nome as construtor, SUM(r.pontos) as total_pontos
                    FROM tbl_resultados r
                    JOIN tbl_corridas c ON r.id_corrida_fk = c.id_corrida
                    JOIN tbl_construtores con ON r.id_construtor_fk = con.id_construtor
                    GROUP BY c.ano, r.id_construtor_fk, construtor
                ),
                yearly_max_points AS (
                    SELECT ano, MAX(total_pontos) as max_pontos
                    FROM yearly_points
                    GROUP BY ano
                ),
                champions AS (
                    SELECT yp.ano, yp.construtor
                    FROM yearly_points yp
                    JOIN yearly_max_points ymp ON yp.ano = ymp.ano AND yp.total_pontos = ymp.max_pontos
                )
                SELECT construtor, COUNT(*) as titulos
                FROM champions
                GROUP BY construtor
                ORDER BY titulos DESC
                LIMIT 15;
            """
            constructor_champs_df = consultar_dados_df(query_constructor_champs)
            if not constructor_champs_df.empty:
                fig = px.bar(constructor_champs_df, x='titulos', y='construtor', orientation='h', text_auto=True,
                             labels={'titulos': 'Títulos Mundais', 'construtor': 'Equipe'},
                             color_discrete_sequence=[F1_GREY])
                fig.update_layout(yaxis={'categoryorder':'total ascending'})
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
                if executar_comando_sql(sql, (nova_nac, id_constr)):
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
                    if executar_comando_sql(sql, (id_piloto_del,)):
                        st.success(f"Piloto '{piloto_del}' deletado!")
                        st.rerun()
