import streamlit as st
import psycopg2
import pandas as pd
import plotly.express as px
from streamlit_option_menu import option_menu

# Configuração da página
st.set_page_config(layout="wide", page_title="F1 Super Analytics", page_icon="🏎️")

# Paleta de cores padrão da F1
F1_PALETTE = ["#E10600", "#15151E", "#7F7F7F", "#B1B1B8", "#FFFFFF", "#FF8700", "#00A000"]
F1_RED = F1_PALETTE[0]
F1_BLACK = F1_PALETTE[1]
F1_GREY = F1_PALETTE[2]

# --- FUNÇÕES DE BANCO DE DADOS ---
@st.cache_resource
def conectar_db():
    try:
        # CORREÇÃO: A conexão agora usa st.secrets diretamente, esperando chaves como host, dbname, etc.
        return psycopg2.connect(**st.secrets["database"])
    except Exception as e:
        st.error(f"Erro CRÍTICO de conexão com o banco de dados: {e}")
        return None
conn = conectar_db()

@st.cache_data(ttl=3600) # Aumentado o cache para 1 hora
def consultar_dados_df(query, params=None):
    if not conn: return pd.DataFrame()
    try:
        return pd.read_sql_query(query, conn, params=params)
    except Exception as e:
        st.warning(f"Erro ao consultar dados: {e}")
        return pd.DataFrame()

def executar_comando_sql(query, params=None):
    if not conn: return None
    try:
        with conn.cursor() as cursor:
            cursor.execute(query, params)
            conn.commit()
            return cursor.rowcount
    except Exception as e:
        st.error(f"Erro ao executar comando no banco de dados: {e}")
        conn.rollback()
        return None

# --- SIDEBAR DE NAVEGAÇÃO ---
with st.sidebar:
    st.image("f1_logo.png", width=300)
    pagina_selecionada = option_menu(
        menu_title="Menu Principal", options=["Análises", "Gerenciamento"],
        icons=["trophy-fill", "pencil-square"], menu_icon="joystick", default_index=0
    )

# --- PÁGINA DE ANÁLISES ---
if pagina_selecionada == "Análises":
    st.title("📊 Análises e Dashboards de F1")
    
    tab_piloto, tab_equipe, tab_h2h, tab_circuito, tab_temporada, tab_corrida, tab_records = st.tabs(["Dashboard de Piloto", "Dashboard de Equipe", "Comparador H2H", "Análise de Circuito", "📈 Análise de Temporada", "🏁 Análise de Corrida", "🏆 Hall da Fama"])

    # --- ABA: DASHBOARD DE PILOTO ---
    with tab_piloto:
        st.header("Análise de Performance de Piloto")
        pilotos_df = consultar_dados_df("SELECT id_piloto, nome, sobrenome, nacionalidade, numero FROM tbl_pilotos ORDER BY sobrenome")
        if not pilotos_df.empty:
            pilotos_df["nome_completo"] = pilotos_df["nome"] + " " + pilotos_df["sobrenome"]
            piloto_selecionado = st.selectbox("Selecione um Piloto", options=pilotos_df["nome_completo"], index=None, placeholder="Digite o nome de um piloto...", key="sel_piloto")
            
            if piloto_selecionado:
                piloto_info = pilotos_df[pilotos_df["nome_completo"] == piloto_selecionado].iloc[0]
                id_piloto = int(piloto_info["id_piloto"])
                
                with st.container(border=True):
                    c1, c2, c3 = st.columns([2, 1, 1])
                    with c1: st.markdown(f"<h2 style='text-align: left; font-size: 50px;'>{piloto_info['nome_completo']}</h2>", unsafe_allow_html=True)
                    with c2: st.metric("País", str(piloto_info['nacionalidade']))
                    with c3: st.metric("Número", "N/A" if pd.isna(piloto_info['numero']) else int(piloto_info['numero']))

                st.subheader("Estatísticas da Carreira")
                kpi_query = "WITH pilot_champs AS (SELECT piloto, COUNT(*) as titulos FROM (SELECT p.nome || ' ' || p.sobrenome as piloto FROM tbl_resultados r JOIN tbl_corridas c ON r.id_corrida_fk = c.id_corrida JOIN tbl_pilotos p ON r.id_piloto_fk = p.id_piloto GROUP BY c.ano, p.nome, p.sobrenome HAVING SUM(r.pontos) = (SELECT MAX(total_pontos) FROM (SELECT SUM(pontos) as total_pontos FROM tbl_resultados r2 JOIN tbl_corridas c2 ON r2.id_corrida_fk = c2.id_corrida WHERE c2.ano = c.ano GROUP BY r2.id_piloto_fk) as sub)) as champs WHERE piloto = %(nome_piloto)s GROUP BY piloto) SELECT COUNT(*) AS total_corridas, SUM(CASE WHEN posicao_final = 1 THEN 1 ELSE 0 END) AS vitorias, SUM(CASE WHEN posicao_grid = 1 THEN 1 ELSE 0 END) AS poles, SUM(CASE WHEN posicao_final <= 3 THEN 1 ELSE 0 END) AS podios, SUM(CASE WHEN rank = 1 THEN 1 ELSE 0 END) AS voltas_rapidas, COALESCE((SELECT titulos FROM pilot_champs), 0) as titulos FROM tbl_resultados WHERE id_piloto_fk = %(id_piloto)s;"
                kpi_df = consultar_dados_df(kpi_query, params={"id_piloto": id_piloto, "nome_piloto": piloto_selecionado})

                if not kpi_df.empty:
                    kpi_data = kpi_df.iloc[0]
                    c1, c2, c3, c4, c5, c6 = st.columns(6)
                    c1.metric("🏆 Títulos", int(kpi_data["titulos"]))
                    c2.metric("Corridas", int(kpi_data["total_corridas"]))
                    c3.metric("🥇 Vitórias", int(kpi_data["vitorias"]))
                    c4.metric("🥈 Pódios", int(kpi_data["podios"]))
                    c5.metric("⏱️ Poles", int(kpi_data["poles"]))
                    c6.metric("🚀 Voltas R.", int(kpi_data["voltas_rapidas"]))

                st.subheader("Análise de Pit Stops")
                pit_stats_q = "SELECT COUNT(*) as total_paradas, AVG(duracao_ms) as media_ms FROM tbl_paradas WHERE id_piloto_fk = %(id)s;"
                pit_stats_df = consultar_dados_df(pit_stats_q, params={'id': id_piloto})
                if not pit_stats_df.empty and pit_stats_df.iloc[0]['total_paradas'] > 0:
                    c1, c2 = st.columns(2)
                    c1.metric("Total de Pit Stops na Carreira", f"{pit_stats_df.iloc[0]['total_paradas']:.0f}")
                    c2.metric("Tempo Médio de Parada", f"{pit_stats_df.iloc[0]['media_ms']/1000:.3f}s")
                
                st.divider()
                
                st.subheader("Análise de Confiabilidade: Motivos de Abandono")
                dnf_query = "SELECT s.status, COUNT(*) as total FROM tbl_resultados r JOIN tbl_status s ON r.id_status_fk = s.id_status WHERE r.id_piloto_fk = %(id)s AND s.status NOT IN ('Finished') AND s.status NOT LIKE '%% Lap%%' GROUP BY s.status ORDER BY total DESC LIMIT 10;"
                dnf_df = consultar_dados_df(dnf_query, params={'id': id_piloto})
                if not dnf_df.empty:
                    fig_dnf = px.bar(dnf_df, x='total', y='status', orientation='h', text_auto=True, color_discrete_sequence=[F1_BLACK], labels={'total': 'Número de Ocorrências', 'status': 'Motivo do Abandono'})
                    fig_dnf.update_layout(yaxis={'categoryorder':'total ascending'})
                    st.plotly_chart(fig_dnf, use_container_width=True)

    # --- ABA: DASHBOARD DE EQUIPE ---
    with tab_equipe:
        st.header("Análise de Performance de Equipe")
        equipes_df = consultar_dados_df("SELECT id_construtor, nome, nacionalidade FROM tbl_construtores ORDER BY nome")
        if not equipes_df.empty:
            equipe_selecionada = st.selectbox("Selecione uma Equipe", options=equipes_df["nome"], index=None, placeholder="Digite o nome de uma equipe...", key="sel_equipe")
            if equipe_selecionada:
                equipe_info = equipes_df[equipes_df["nome"] == equipe_selecionada].iloc[0]
                id_equipe = int(equipe_info["id_construtor"])
                
                kpi_equipe_query = "WITH constructor_champs AS (SELECT construtor, COUNT(*) as titulos FROM (SELECT con.nome as construtor FROM tbl_resultados r JOIN tbl_corridas c ON r.id_corrida_fk = c.id_corrida JOIN tbl_construtores con ON r.id_construtor_fk = con.id_construtor GROUP BY c.ano, con.nome HAVING SUM(r.pontos) = (SELECT MAX(total_pontos) FROM (SELECT SUM(pontos) as total_pontos FROM tbl_resultados r2 JOIN tbl_corridas c2 ON r2.id_corrida_fk = c2.id_corrida WHERE c2.ano = c.ano GROUP BY r2.id_construtor_fk) as sub)) as champs WHERE construtor = %(nome_equipe)s GROUP BY construtor) SELECT SUM(CASE WHEN posicao_final = 1 THEN 1 ELSE 0 END) as vitorias, SUM(CASE WHEN posicao_grid = 1 THEN 1 ELSE 0 END) AS poles, SUM(CASE WHEN rank = 1 THEN 1 ELSE 0 END) AS voltas_rapidas, COALESCE((SELECT titulos FROM constructor_champs), 0) as titulos FROM tbl_resultados WHERE id_construtor_fk = %(id_equipe)s;"
                kpi_equipe_df = consultar_dados_df(kpi_equipe_query, params={"id_equipe": id_equipe, "nome_equipe": equipe_selecionada}).iloc[0]
                
                c1, c2, c3, c4 = st.columns(4)
                c1.metric("🏆 Títulos", int(kpi_equipe_df["titulos"]))
                c2.metric("🥇 Vitórias", int(kpi_equipe_df["vitorias"]))
                c3.metric("⏱️ Poles", int(kpi_equipe_df["poles"]))
                c4.metric("🚀 Voltas R.", int(kpi_equipe_df["voltas_rapidas"]))

                st.subheader("Métricas de Domínio")
                c1, c2 = st.columns(2)
                dobradinhas_q = "SELECT COUNT(*) as total FROM (SELECT id_corrida_fk FROM tbl_resultados WHERE id_construtor_fk = %(id)s AND posicao_final IN (1, 2) GROUP BY id_corrida_fk HAVING COUNT(DISTINCT id_piloto_fk) = 2) as d;"
                c1.metric("Dobradinhas (1º-2º na Corrida)", consultar_dados_df(dobradinhas_q, params={'id':id_equipe}).iloc[0]['total'])
                front_row_q = "SELECT COUNT(*) as total FROM (SELECT id_corrida_fk FROM tbl_qualificacao WHERE id_construtor_fk = %(id)s AND posicao IN (1, 2) GROUP BY id_corrida_fk HAVING COUNT(DISTINCT id_piloto_fk) = 2) as d;"
                c2.metric("Bloqueios de 1ª Fila (1º-2º na Quali)", consultar_dados_df(front_row_q, params={'id':id_equipe}).iloc[0]['total'])
                
                st.subheader("Performance Média de Pit Stops por Temporada")
                pit_team_q = "SELECT c.ano, AVG(p.duracao_ms) as media_ms FROM tbl_paradas p JOIN tbl_resultados r ON p.id_piloto_fk = r.id_piloto_fk AND p.id_corrida_fk = r.id_corrida_fk JOIN tbl_corridas c ON p.id_corrida_fk = c.id_corrida WHERE r.id_construtor_fk = %(id)s GROUP BY c.ano ORDER BY c.ano;"
                pit_team_df = consultar_dados_df(pit_team_q, params={'id': id_equipe})
                if not pit_team_df.empty:
                    pit_team_df['media_s'] = pit_team_df['media_ms'] / 1000
                    fig_pit_team = px.bar(pit_team_df, x='ano', y='media_s', text_auto='.3f', labels={'ano': 'Temporada', 'media_s': 'Tempo Médio de Parada (s)'}, color_discrete_sequence=[F1_GREY])
                    st.plotly_chart(fig_pit_team, use_container_width=True)
    
    # --- ABA: COMPARADOR H2H ---
    with tab_h2h:
        st.header("Comparador de Pilotos: Head-to-Head")
        pilotos_h2h_df = consultar_dados_df("SELECT id_piloto, nome, sobrenome FROM tbl_pilotos ORDER BY sobrenome")
        if not pilotos_h2h_df.empty:
            pilotos_h2h_df["nome_completo"] = pilotos_h2h_df["nome"] + " " + pilotos_h2h_df["sobrenome"]
            sel_col1, sel_col2 = st.columns(2)
            piloto1_nome = sel_col1.selectbox("Piloto 1", options=pilotos_h2h_df["nome_completo"], index=None, key="p1")
            piloto2_nome = sel_col2.selectbox("Piloto 2", options=pilotos_h2h_df["nome_completo"], index=None, key="p2")

            if piloto1_nome and piloto2_nome:
                id_piloto1 = int(pilotos_h2h_df[pilotos_h2h_df["nome_completo"] == piloto1_nome].iloc[0]['id_piloto'])
                id_piloto2 = int(pilotos_h2h_df[pilotos_h2h_df["nome_completo"] == piloto2_nome].iloc[0]['id_piloto'])
                
                st.subheader("Confrontos Diretos")
                params_h2h = {'p1': id_piloto1, 'p2': id_piloto2}
                g1, g2 = st.columns(2)
                with g1:
                    st.markdown("##### Final de Corrida")
                    confronto_query = "WITH corridas_comuns AS (SELECT id_corrida_fk FROM tbl_resultados WHERE id_piloto_fk = %(p1)s INTERSECT SELECT id_corrida_fk FROM tbl_resultados WHERE id_piloto_fk = %(p2)s) SELECT MAX(CASE WHEN id_piloto_fk = %(p1)s THEN posicao_final END) as p1_pos, MAX(CASE WHEN id_piloto_fk = %(p2)s THEN posicao_final END) as p2_pos FROM tbl_resultados WHERE id_corrida_fk IN (SELECT id_corrida_fk FROM corridas_comuns) AND id_piloto_fk IN (%(p1)s, %(p2)s) GROUP BY id_corrida_fk"
                    confronto_df = consultar_dados_df(confronto_query, params=params_h2h)
                    if not confronto_df.empty:
                        confronto_df.dropna(inplace=True) 
                        p1_a_frente = (confronto_df['p1_pos'] < confronto_df['p2_pos']).sum()
                        p2_a_frente = (confronto_df['p2_pos'] < confronto_df['p1_pos']).sum()
                        fig_confronto_h2h = px.bar(x=[piloto1_nome, piloto2_nome], y=[p1_a_frente, p2_a_frente], labels={'x': 'Piloto', 'y': 'Vezes que terminou à frente'}, color=[piloto1_nome, piloto2_nome], color_discrete_map={piloto1_nome: F1_RED, piloto2_nome: F1_GREY}, text_auto=True)
                        st.plotly_chart(fig_confronto_h2h, use_container_width=True)

    # --- ABA: ANÁLISE DE CIRCUITO ---
    with tab_circuito:
        st.header("Análise por Circuito")
        circuitos_df = consultar_dados_df("SELECT id_circuito, nome FROM tbl_circuitos ORDER BY nome")
        if not circuitos_df.empty:
            circuito_nome_sel = st.selectbox("Selecione um Circuito", options=circuitos_df["nome"], index=None, key="sel_circuito")
            if circuito_nome_sel:
                id_circuito = int(circuitos_df[circuitos_df["nome"] == circuito_nome_sel].iloc[0]['id_circuito'])
                
                st.subheader(f"De Onde Saem os Vencedores em {circuito_nome_sel}?")
                grid_vencedor_q = "SELECT posicao_grid FROM tbl_resultados r JOIN tbl_corridas c ON r.id_corrida_fk = c.id_corrida WHERE c.id_circuito_fk=%(id)s AND r.posicao_final = 1 AND r.posicao_grid IS NOT NULL;"
                grid_vencedor_df = consultar_dados_df(grid_vencedor_q, params={'id': id_circuito})
                if not grid_vencedor_df.empty:
                    fig_grid_vencedor = px.histogram(grid_vencedor_df, x='posicao_grid', nbins=20, text_auto=True, color_discrete_sequence=[F1_BLACK], labels={'posicao_grid': 'Posição de Largada', 'count': 'Número de Vitórias'})
                    st.plotly_chart(fig_grid_vencedor, use_container_width=True)

    # --- ABA: ANÁLISE DE TEMPORADA ---
    with tab_temporada:
        st.header("📈 Análise de Temporada")
        anos_df = consultar_dados_df("SELECT DISTINCT ano FROM tbl_corridas ORDER BY ano DESC;")
        if not anos_df.empty:
            ano_sel = st.selectbox("Selecione o Ano", options=anos_df['ano'], key="sel_ano_temporada")
            
            st.subheader(f"Evolução do Campeonato de Pilotos {ano_sel}")
            class_pilotos_q = "SELECT c.rodada, c.nome_gp, p.codigo, cl.pontos FROM tbl_classificacao_pilotos cl JOIN tbl_corridas c ON cl.id_corrida_fk = c.id_corrida JOIN tbl_pilotos p ON cl.id_piloto_fk = p.id_piloto WHERE c.ano = %(ano)s AND cl.posicao <= 5 ORDER BY c.rodada, cl.posicao;"
            class_pilotos_df = consultar_dados_df(class_pilotos_q, params={'ano': ano_sel})
            if not class_pilotos_df.empty:
                fig = px.line(class_pilotos_df, x='rodada', y='pontos', color='codigo', markers=True, labels={'rodada': 'Rodada', 'pontos': 'Pontos Acumulados', 'codigo': 'Piloto'}, hover_name='nome_gp')
                st.plotly_chart(fig, use_container_width=True)

    # --- ABA: ANÁLISE DE CORRIDA ---
    with tab_corrida:
        st.header("🏁 Análise Detalhada de Corrida")
        anos_df_corrida = consultar_dados_df("SELECT DISTINCT ano FROM tbl_corridas ORDER BY ano DESC;")
        if not anos_df_corrida.empty:
            ano_sel_corrida = st.selectbox("Selecione o Ano", options=anos_df_corrida['ano'], key="sel_ano_corrida")
            corridas_df = consultar_dados_df("SELECT id_corrida, nome_gp FROM tbl_corridas WHERE ano = %(ano)s ORDER BY rodada ASC;", params={'ano': ano_sel_corrida})
            if not corridas_df.empty:
                corrida_sel_nome = st.selectbox("Selecione a Corrida", options=corridas_df['nome_gp'], key="sel_nome_corrida")
                id_corrida = int(corridas_df[corridas_df['nome_gp'] == corrida_sel_nome].iloc[0]['id_corrida'])
                st.subheader(f"Análise Estratégica: {corrida_sel_nome} {ano_sel_corrida}")
                
                col1, col2 = st.columns(2)
                with col1:
                    st.markdown("##### Pit Stops na Corrida")
                    pit_race_q = "SELECT p.nome || ' ' || p.sobrenome as piloto, pa.volta, pa.parada, pa.duracao_s FROM tbl_paradas pa JOIN tbl_pilotos p ON pa.id_piloto_fk = p.id_piloto WHERE pa.id_corrida_fk = %(id)s ORDER BY pa.parada, pa.volta;"
                    pit_race_df = consultar_dados_df(pit_race_q, params={'id': id_corrida})
                    st.dataframe(pit_race_df, height=300, use_container_width=True)
                with col2:
                    st.markdown("##### Tempo Médio de Parada por Equipe")
                    pit_race_team_q = "SELECT con.nome, AVG(pa.duracao_s) as media_s FROM tbl_paradas pa JOIN tbl_resultados r ON pa.id_piloto_fk = r.id_piloto_fk AND pa.id_corrida_fk = r.id_corrida_fk JOIN tbl_construtores con ON r.id_construtor_fk = con.id_construtor WHERE pa.id_corrida_fk = %(id)s GROUP BY con.nome ORDER BY media_s ASC;"
                    pit_race_team_df = consultar_dados_df(pit_race_team_q, params={'id': id_corrida})
                    fig_pit_race = px.bar(pit_race_team_df, x='media_s', y='nome', orientation='h', text_auto='.3f', labels={'media_s': 'Tempo Médio (s)', 'nome': 'Equipe'}, color_discrete_sequence=[F1_BLACK])
                    st.plotly_chart(fig_pit_race, use_container_width=True)

                st.subheader("Performance dos Pilotos")
                pilotos_na_corrida_q = "SELECT DISTINCT p.id_piloto, p.nome || ' ' || p.sobrenome as nome_completo FROM tbl_resultados r JOIN tbl_pilotos p ON r.id_piloto_fk = p.id_piloto WHERE r.id_corrida_fk = %(id)s ORDER BY nome_completo ASC;"
                pilotos_na_corrida_df = consultar_dados_df(pilotos_na_corrida_q, params={'id': id_corrida})
                
                if not pilotos_na_corrida_df.empty:
                    pilotos_sel_corrida = st.multiselect("Selecione os pilotos para comparar", options=pilotos_na_corrida_df['nome_completo'], default=pilotos_na_corrida_df['nome_completo'].head(5).tolist())
                    if pilotos_sel_corrida:
                        ids_pilotos_sel = pilotos_na_corrida_df[pilotos_na_corrida_df['nome_completo'].isin(pilotos_sel_corrida)]['id_piloto'].tolist()
                        st.markdown("##### Posição Volta a Volta")
                        pos_volta_q = "SELECT l.volta, l.posicao, p.nome || ' ' || p.sobrenome as piloto FROM tbl_voltas l JOIN tbl_pilotos p ON l.id_piloto_fk = p.id_piloto WHERE l.id_corrida_fk = %(id_c)s AND l.id_piloto_fk = ANY(%(ids_p)s) ORDER BY l.volta;"
                        pos_volta_df = consultar_dados_df(pos_volta_q, params={'id_c': id_corrida, 'ids_p': ids_pilotos_sel})
                        if not pos_volta_df.empty:
                            fig_pos_volta = px.line(pos_volta_df, x='volta', y='posicao', color='piloto', markers=False, color_discrete_sequence=px.colors.qualitative.Plotly)
                            fig_pos_volta.update_yaxes(autorange="reversed")
                            st.plotly_chart(fig_pos_volta, use_container_width=True)
    
    # --- ABA: HALL DA FAMA ---
    with tab_records:
        st.header("Hall da Fama: Recordes e Rankings Históricos")
        st.subheader("Recordistas de Todos os Tempos")
        query_records = "WITH pilot_champs_agg AS (SELECT piloto, COUNT(*) as titulos FROM (SELECT c.ano, p.nome || ' ' || p.sobrenome as piloto FROM tbl_resultados r JOIN tbl_corridas c ON r.id_corrida_fk = c.id_corrida JOIN tbl_pilotos p ON r.id_piloto_fk = p.id_piloto GROUP BY c.ano, p.nome, p.sobrenome HAVING SUM(r.pontos) = (SELECT MAX(total_pontos) FROM (SELECT SUM(pontos) as total_pontos FROM tbl_resultados r2 JOIN tbl_corridas c2 ON r2.id_corrida_fk = c2.id_corrida WHERE c2.ano = c.ano GROUP BY r2.id_piloto_fk) as sub)) as champs GROUP BY piloto), constructor_champs_agg AS (SELECT construtor, COUNT(*) as titulos FROM (SELECT c.ano, con.nome as construtor FROM tbl_resultados r JOIN tbl_corridas c ON r.id_corrida_fk = c.id_corrida JOIN tbl_construtores con ON r.id_construtor_fk = con.id_construtor GROUP BY c.ano, con.nome HAVING SUM(r.pontos) = (SELECT MAX(total_pontos) FROM (SELECT SUM(pontos) as total_pontos FROM tbl_resultados r2 JOIN tbl_corridas c2 ON r2.id_corrida_fk = c2.id_corrida WHERE c2.ano = c.ano GROUP BY r2.id_construtor_fk) as sub)) as champs GROUP BY construtor), pilot_stats AS (SELECT p.nome || ' ' || p.sobrenome as piloto, SUM(CASE WHEN r.posicao_final = 1 THEN 1 ELSE 0 END) as vitorias, SUM(CASE WHEN r.posicao_grid = 1 THEN 1 ELSE 0 END) as poles, SUM(CASE WHEN r.posicao_final <= 3 THEN 1 ELSE 0 END) as podios, SUM(CASE WHEN r.rank = 1 THEN 1 ELSE 0 END) as voltas_rapidas FROM tbl_resultados r JOIN tbl_pilotos p ON r.id_piloto_fk = p.id_piloto GROUP BY piloto), constructor_stats AS (SELECT con.nome as construtor, SUM(CASE WHEN r.posicao_final = 1 THEN 1 ELSE 0 END) as vitorias, SUM(CASE WHEN r.posicao_grid = 1 THEN 1 ELSE 0 END) as poles, SUM(CASE WHEN r.posicao_final <= 3 THEN 1 ELSE 0 END) as podios, SUM(CASE WHEN r.rank = 1 THEN 1 ELSE 0 END) as voltas_rapidas FROM tbl_resultados r JOIN tbl_construtores con ON r.id_construtor_fk = con.id_construtor GROUP BY construtor) SELECT * FROM (SELECT piloto as recordista, titulos as recorde, 'Títulos (Piloto)' as tipo FROM pilot_champs_agg ORDER BY recorde DESC LIMIT 1) a UNION ALL SELECT * FROM (SELECT construtor as recordista, titulos as recorde, 'Títulos (Equipe)' as tipo FROM constructor_champs_agg ORDER BY recorde DESC LIMIT 1) b UNION ALL SELECT * FROM (SELECT piloto as recordista, vitorias as recorde, 'Vitórias (Piloto)' as tipo FROM pilot_stats ORDER BY recorde DESC LIMIT 1) c UNION ALL SELECT * FROM (SELECT construtor as recordista, vitorias as recorde, 'Vitórias (Equipe)' as tipo FROM constructor_stats ORDER BY recorde DESC LIMIT 1) d UNION ALL SELECT * FROM (SELECT piloto as recordista, poles as recorde, 'Poles (Piloto)' as tipo FROM pilot_stats ORDER BY recorde DESC LIMIT 1) e UNION ALL SELECT * FROM (SELECT construtor as recordista, poles as recorde, 'Poles (Equipe)' as tipo FROM constructor_stats ORDER BY recorde DESC LIMIT 1) f UNION ALL SELECT * FROM (SELECT piloto as recordista, podios as recorde, 'Pódios (Piloto)' as tipo FROM pilot_stats ORDER BY recorde DESC LIMIT 1) g UNION ALL SELECT * FROM (SELECT construtor as recordista, podios as recorde, 'Pódios (Equipe)' as tipo FROM constructor_stats ORDER BY recorde DESC LIMIT 1) h UNION ALL SELECT * FROM (SELECT piloto as recordista, voltas_rapidas as recorde, 'Voltas Rápidas (Piloto)' as tipo FROM pilot_stats ORDER BY recorde DESC LIMIT 1) i UNION ALL SELECT * FROM (SELECT construtor as recordista, voltas_rapidas as recorde, 'Voltas Rápidas (Equipe)' as tipo FROM constructor_stats ORDER BY recorde DESC LIMIT 1) j;"
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

# --- PÁGINA DE GERENCIAMENTO (CRUD) ---
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
            numero = st.number_input("Número do Carro", min_value=0, step=1, value=None)
            codigo = st.text_input("Código do Piloto (3 letras)", max_chars=3)
            data_nascimento = st.date_input("Data de Nascimento")
            
            submitted = st.form_submit_button("Adicionar Piloto")
            if submitted:
                query = "INSERT INTO tbl_pilotos (id_piloto, ref_piloto, numero, codigo, nome, sobrenome, data_nascimento, nacionalidade) VALUES (%s, %s, %s, %s, %s, %s, %s, %s);"
                params = (id_piloto, ref, numero, codigo.upper(), nome, sobrenome, data_nascimento, nacionalidade)
                if executar_comando_sql(query, params) is not None:
                    st.success(f"Piloto {nome} {sobrenome} adicionado com sucesso!")
    
    with tab_read:
        st.subheader("Consultar Tabelas")
        tabelas_disponiveis = ["Pilotos", "Construtores", "Circuitos", "Corridas", "Status"]
        tabela_selecionada = st.selectbox("Escolha a tabela para visualizar:", options=tabelas_disponiveis)
        
        map_tabelas = {
            "Pilotos": "tbl_pilotos",
            "Construtores": "tbl_construtores",
            "Circuitos": "tbl_circuitos",
            "Corridas": "tbl_corridas",
            "Status": "tbl_status"
        }
        
        if tabela_selecionada:
            df = consultar_dados_df(f"SELECT * FROM {map_tabelas[tabela_selecionada]} LIMIT 100;")
            st.dataframe(df, use_container_width=True)

    with tab_update:
        st.subheader("Atualizar Nacionalidade de um Construtor")
        constr_df_update = consultar_dados_df("SELECT id_construtor, nome FROM tbl_construtores ORDER BY nome")
        if not constr_df_update.empty:
            constr_sel = st.selectbox("Selecione o Construtor", options=constr_df_update["nome"], key="update_constr")
            id_constr = int(constr_df_update[constr_df_update["nome"] == constr_sel]["id_construtor"].iloc[0])
            nova_nac = st.text_input("Digite a Nova Nacionalidade", key=f"nac_{id_constr}")
            if st.button("Atualizar Nacionalidade"):
                if executar_comando_sql("UPDATE tbl_construtores SET nacionalidade = %s WHERE id_construtor = %s", (nova_nac, id_constr)) is not None:
                    st.success(f"Nacionalidade de '{constr_sel}' atualizada!")
    
    with tab_delete:
        st.subheader("Deletar um Piloto")
        st.warning("CUIDADO: Ação irreversível. A exclusão de um piloto pode causar problemas de integridade de dados se ele estiver associado a resultados de corridas.", icon="⚠️")
        pilotos_del_df = consultar_dados_df("SELECT id_piloto, nome, sobrenome FROM tbl_pilotos ORDER BY sobrenome")
        if not pilotos_del_df.empty:
            pilotos_del_df["nome_completo"] = pilotos_del_df["nome"] + " " + pilotos_del_df["sobrenome"]
            piloto_del = st.selectbox("Selecione o Piloto a ser deletado", options=pilotos_del_df["nome_completo"], index=None, placeholder="Selecione um piloto...")
            if piloto_del and st.button(f"DELETAR {piloto_del}", type="primary"):
                id_piloto_del = int(pilotos_del_df[pilotos_del_df["nome_completo"] == piloto_del]["id_piloto"].iloc[0])
                if executar_comando_sql("DELETE FROM tbl_pilotos WHERE id_piloto = %s", (id_piloto_del,)) is not None:
                    st.success(f"Piloto '{piloto_del}' deletado!")
                    st.rerun()
