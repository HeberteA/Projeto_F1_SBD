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
        db_secrets = st.secrets["database"]
        for key in ["url", "uri", "connection_string"]:
            if key in db_secrets:
                return psycopg2.connect(db_secrets[key])
        return psycopg2.connect(**db_secrets)
    except Exception as e:
        st.error(f"Erro CRÍTICO de conexão com o banco de dados: {e}")
        return None

conn = conectar_db()

@st.cache_data(ttl=3600)
def consultar_dados_df(query, params=None):
    if not conn: return pd.DataFrame()
    try:
        with conn.cursor() as cur:
            return pd.read_sql_query(query, conn, params=params)
    except Exception as e:
        st.warning(f"Erro ao consultar dados: {e}")
        return pd.DataFrame()

def executar_comando_sql(comando, params=None):
    if not conn: return None
    try:
        with conn.cursor() as cur:
            cur.execute(comando, params)
            conn.commit()
        st.cache_data.clear()
        st.cache_resource.clear()
        return True
    except Exception as e:
        conn.rollback()
        st.error(f"Erro ao executar comando SQL: {e}")
        return None

@st.cache_data(ttl=3600)
def carregar_todos_os_dados():
    queries = {
        "tbl_corridas": 'SELECT id_corrida, ano, rodada, nome_gp, id_circuito_fk FROM tbl_corridas',
        "tbl_resultados": 'SELECT posicao_final, pontos, posicao_grid, id_corrida_fk, id_piloto_fk, id_construtor_fk, id_status_fk FROM tbl_resultados',
        "tbl_pilotos": 'SELECT id_piloto, nome as nome_piloto, sobrenome FROM tbl_pilotos',
        "tbl_construtores": 'SELECT id_construtor, nome as nome_construtor, nacionalidade as nacionalidade_construtor FROM tbl_construtores',
        "driver_standings": 'SELECT "raceId", "driverId", points, position, wins FROM driver_standings',
        "constructor_standings": 'SELECT "raceId", "constructorId", points, position, wins FROM constructor_standings',
        "qualifying": 'SELECT "raceId", "driverId", "constructorId", position as quali_position FROM qualifying',
        "tbl_circuitos": 'SELECT id_circuito, nome as nome_circuito, cidade, pais FROM tbl_circuitos',
        "tbl_status_resultado": 'SELECT id_status, status FROM tbl_status_resultado'
    }
    data = {name: consultar_dados_df(query) for name, query in queries.items()}
    if not data["tbl_pilotos"].empty:
        data["tbl_pilotos"]['nome_completo_piloto'] = data["tbl_pilotos"]['nome_piloto'] + ' ' + data["tbl_pilotos"]['sobrenome']
    return data

def render_pagina_visao_geral(data):
    st.title("🏁 Visão Geral da Temporada de F1")
    races, drivers, constructors, driver_standings, constructor_standings = (
        data['tbl_corridas'], data['tbl_pilotos'], data['tbl_construtores'],
        data['driver_standings'], data['constructor_standings']
    )
    st.sidebar.header("Filtros")
    anos_disponiveis = sorted(races[races['ano'] <= 2024]['ano'].unique(), reverse=True)
    ano_selecionado = st.sidebar.selectbox("Selecione a Temporada", anos_disponiveis, key="visao_geral_ano")

    races_ano = races[races['ano'] == ano_selecionado]
    if races_ano.empty:
        st.warning(f"Não há dados de corrida para a temporada de {ano_selecionado}.")
        return

    st.header(f"Resumo da Temporada de {ano_selecionado}")
    ultima_corrida_id = races_ano.sort_values(by='rodada', ascending=False).iloc[0]['id_corrida']

    driver_standings_final = driver_standings[driver_standings['raceId'] == ultima_corrida_id]
    campeao_piloto_info = driver_standings_final[driver_standings_final['position'] == 1]
    nome_campeao_piloto = drivers[drivers['id_piloto'] == campeao_piloto_info['driverId'].iloc[0]]['nome_completo_piloto'].iloc[0] if not campeao_piloto_info.empty else "N/A"

    constructor_standings_final = constructor_standings[constructor_standings['raceId'] == ultima_corrida_id]
    campeao_constr_info = constructor_standings_final[constructor_standings_final['position'] == 1]
    nome_campeao_constr = constructors[constructors['id_construtor'] == campeao_constr_info['constructorId'].iloc[0]]['nome_construtor'].iloc[0] if not campeao_constr_info.empty else "N/A"

    col1, col2, col3 = st.columns(3)
    col1.metric("🏆 Campeão de Pilotos", nome_campeao_piloto)
    col2.metric("🏎️ Campeão de Construtores", nome_campeao_constr)
    col3.metric("🏁 Total de Corridas", races_ano['id_corrida'].nunique())
    st.divider()

    col_graf1, col_graf2 = st.columns(2)
    with col_graf1:
        st.subheader("🏆 Classificação Final de Pilotos")
        classificacao_pilotos = driver_standings_final.merge(drivers, left_on='driverId', right_on='id_piloto').sort_values(by='position').head(10)
        fig = px.bar(classificacao_pilotos, x='points', y='nome_completo_piloto', orientation='h', text='points', color_discrete_sequence=[F1_RED])
        fig.update_layout(yaxis={'categoryorder':'total ascending'}, xaxis_title="Pontos", yaxis_title="Piloto")
        st.plotly_chart(fig, use_container_width=True)

    with col_graf2:
        st.subheader("🏎️ Classificação Final de Construtores")
        classificacao_constr = constructor_standings_final.merge(constructors, left_on='constructorId', right_on='id_construtor').sort_values(by='position')
        fig = px.bar(classificacao_constr, x='points', y='nome_construtor', orientation='h', text='points', color_discrete_sequence=[F1_RED])
        fig.update_layout(yaxis={'categoryorder':'total ascending'}, xaxis_title="Pontos", yaxis_title="Construtor")
        st.plotly_chart(fig, use_container_width=True)

def render_pagina_analise_pilotos(data):
    st.title("🧑‍🚀 Análise Detalhada de Pilotos")
    drivers, results, qualifying = data['tbl_pilotos'], data['tbl_resultados'], data['qualifying']
    piloto_selecionado = st.selectbox("Selecione um Piloto", options=drivers.sort_values('sobrenome')['nome_completo_piloto'], index=None, placeholder="Buscar piloto...")
    if piloto_selecionado:
        driver_id = drivers[drivers['nome_completo_piloto'] == piloto_selecionado]['id_piloto'].iloc[0]
        resultados_piloto = results[results['id_piloto_fk'] == driver_id]
        poles_piloto = qualifying[(qualifying['driverId'] == driver_id) & (qualifying['quali_position'] == 1)]
        
        col1, col2, col3, col4, col5 = st.columns(5)
        col1.metric("🏁 Corridas", resultados_piloto['id_corrida_fk'].nunique())
        col2.metric("🏆 Vitórias", resultados_piloto[resultados_piloto['posicao_final'] == 1].shape[0])
        col3.metric("🍾 Pódios", resultados_piloto[resultados_piloto['posicao_final'].isin([1, 2, 3])].shape[0])
        col4.metric("⏱️ Pole Positions", poles_piloto.shape[0])
        col5.metric("💯 Total de Pontos", f"{resultados_piloto['pontos'].sum():,.0f}")
        st.divider()

        col_graf1, col_graf2 = st.columns(2)
        with col_graf1:
            st.subheader("Desempenho: Largada vs. Chegada")
            grid_vs_final = resultados_piloto[['posicao_grid', 'posicao_final']]
            grid_vs_final = grid_vs_final[(grid_vs_final['posicao_grid'] > 0) & (grid_vs_final['posicao_final'] > 0)]
            fig = px.scatter(grid_vs_final, x='posicao_grid', y='posicao_final', labels={'posicao_grid': 'Grid', 'posicao_final': 'Final'},
                             trendline='ols', trendline_color_override=F1_RED)
            st.plotly_chart(fig, use_container_width=True)
        with col_graf2:
            st.subheader("Distribuição de Resultados")
            contagem_posicao = resultados_piloto['posicao_final'].value_counts().reset_index().sort_values('posicao_final')
            fig = px.bar(contagem_posicao.head(10), x='posicao_final', y='count', labels={'posicao_final': 'Posição', 'count': 'Nº de Vezes'},
                         text='count', color_discrete_sequence=[F1_RED])
            fig.update_layout(xaxis_type='category')
            st.plotly_chart(fig, use_container_width=True)

def render_pagina_analise_construtores(data):
    st.title("🔧 Análise Detalhada de Construtores")
    constructors, results, status, constructor_standings = data['tbl_construtores'], data['tbl_resultados'], data['tbl_status_resultado'], data['constructor_standings']
    construtor_selecionado = st.selectbox("Selecione um Construtor", options=constructors.sort_values('nome_construtor')['nome_construtor'], index=None, placeholder="Buscar construtor...")
    if construtor_selecionado:
        constructor_id = constructors[constructors['nome_construtor'] == construtor_selecionado]['id_construtor'].iloc[0]
        resultados_construtor = results[results['id_construtor_fk'] == constructor_id]
        
        campeonatos = constructor_standings[(constructor_standings['constructorId'] == constructor_id) & (constructor_standings['position'] == 1)].shape[0]

        col1, col2, col3, col4 = st.columns(4)
        col1.metric("🏁 Corridas", resultados_construtor['id_corrida_fk'].nunique())
        col2.metric("🏆 Vitórias", resultados_construtor[resultados_construtor['posicao_final'] == 1].shape[0])
        col3.metric("🌍 Campeonatos", campeonatos)
        col4.metric("💯 Total de Pontos", f"{resultados_construtor['pontos'].sum():,.0f}")
        st.divider()

        col_graf1, col_graf2 = st.columns(2)
        with col_graf1:
            st.subheader("Análise de Confiabilidade")
            status_merged = resultados_construtor.merge(status, left_on='id_status_fk', right_on='id_status')
            finished_statuses = ['Finished'] + [f'+{i} Lap' for i in range(1, 20)]
            status_merged['category'] = status_merged['status'].apply(lambda x: 'Finalizou' if x in finished_statuses else 'Não Finalizou')
            category_summary = status_merged.groupby('category')['status'].count().reset_index(name='count')
            fig = px.pie(category_summary, names='category', values='count', hole=0.4, 
                         color_discrete_map={'Finalizou': 'green', 'Não Finalizou': F1_RED})
            st.plotly_chart(fig, use_container_width=True)
        with col_graf2:
            st.subheader("Distribuição de Resultados")
            posicoes = resultados_construtor[resultados_construtor['posicao_final'] > 0]['posicao_final'].value_counts().reset_index().sort_values('posicao_final').head(15)
            fig = px.bar(posicoes, x='posicao_final', y='count', color_discrete_sequence=[F1_RED], labels={'posicao_final': 'Posição', 'count': 'Nº de Vezes'})
            fig.update_layout(xaxis_type='category')
            st.plotly_chart(fig, use_container_width=True)

def render_pagina_analise_circuitos(data):
    st.title("🛣️ Análise de Circuitos")
    circuits, races, results, drivers = data['tbl_circuitos'], data['tbl_corridas'], data['tbl_resultados'], data['tbl_pilotos']
    circuito_selecionado = st.selectbox("Selecione um Circuito", options=circuits.sort_values('nome_circuito')['nome_circuito'], index=None, placeholder="Buscar circuito...")
    if circuito_selecionado:
        circuit_id = circuits[circuits['nome_circuito'] == circuito_selecionado]['id_circuito'].iloc[0]
        corridas_no_circuito = races[races['id_circuito_fk'] == circuit_id]
        resultados_circuito = results[results['id_corrida_fk'].isin(corridas_no_circuito['id_corrida'])]
        
        vencedores = resultados_circuito[resultados_circuito['posicao_final'] == 1].merge(drivers, left_on='id_piloto_fk', right_on='id_piloto')
        maior_vencedor = vencedores['nome_completo_piloto'].value_counts().idxmax() if not vencedores.empty else "N/A"
        
        st.metric("🏆 Maior Vencedor no Circuito", maior_vencedor)
        st.divider()

        st.subheader(f"Todos os Vencedores em {circuito_selecionado}")
        vencedores_por_ano = vencedores.merge(corridas_no_circuito, left_on='id_corrida_fk', right_on='id_corrida')[['ano', 'nome_completo_piloto']]
        st.dataframe(vencedores_por_ano.sort_values('ano', ascending=False), use_container_width=True)

def render_pagina_h2h(data):
    st.title("⚔️ Head-to-Head de Pilotos")
    drivers, results = data['tbl_pilotos'], data['tbl_resultados']
    
    col1, col2 = st.columns(2)
    with col1:
        piloto1 = st.selectbox("Selecione o Piloto 1", options=drivers.sort_values('sobrenome')['nome_completo_piloto'], index=None, key="h2h_p1")
    with col2:
        piloto2 = st.selectbox("Selecione o Piloto 2", options=drivers.sort_values('sobrenome')['nome_completo_piloto'], index=None, key="h2h_p2")
        
    if piloto1 and piloto2 and piloto1 != piloto2:
        id1 = drivers[drivers['nome_completo_piloto'] == piloto1]['id_piloto'].iloc[0]
        id2 = drivers[drivers['nome_completo_piloto'] == piloto2]['id_piloto'].iloc[0]
        
        stats1 = results[results['id_piloto_fk'] == id1]
        stats2 = results[results['id_piloto_fk'] == id2]

        vitorias1 = stats1[stats1['posicao_final'] == 1].shape[0]
        vitorias2 = stats2[stats2['posicao_final'] == 1].shape[0]
        podios1 = stats1[stats1['posicao_final'].isin([1,2,3])].shape[0]
        podios2 = stats2[stats2['posicao_final'].isin([1,2,3])].shape[0]
        pontos1 = stats1['pontos'].sum()
        pontos2 = stats2['pontos'].sum()

        corridas_juntos = stats1.merge(stats2, on='id_corrida_fk', suffixes=('_p1', '_p2'))
        vitorias_h2h_p1 = corridas_juntos[corridas_juntos['posicao_final_p1'] < corridas_juntos['posicao_final_p2']].shape[0]
        vitorias_h2h_p2 = corridas_juntos[corridas_juntos['posicao_final_p2'] < corridas_juntos['posicao_final_p1']].shape[0]

        st.subheader(f"Comparativo: {piloto1} vs {piloto2}")
        
        fig = go.Figure()
        fig.add_trace(go.Bar(name=piloto1, x=['Vitórias', 'Pódios', 'Pontos'], y=[vitorias1, podios1, pontos1], marker_color=F1_RED))
        fig.add_trace(go.Bar(name=piloto2, x=['Vitórias', 'Pódios', 'Pontos'], y=[vitorias2, podios2, pontos2], marker_color=F1_GREY))
        fig.update_layout(barmode='group', title_text='Estatísticas da Carreira')
        st.plotly_chart(fig, use_container_width=True)

        st.subheader("Resultados em Corridas Juntos")
        col_h2h1, col_h2h2, col_h2h3 = st.columns(3)
        col_h2h1.metric("Total de Corridas Juntos", corridas_juntos.shape[0])
        col_h2h2.metric(f"Vantagem para {piloto1}", f"{vitorias_h2h_p1} vezes")
        col_h2h3.metric(f"Vantagem para {piloto2}", f"{vitorias_h2h_p2} vezes")

def main():
    with st.sidebar:
        st.image("f1_logo.png", width=300)
        app_page = option_menu(
            menu_title='F1 Super Analytics',
            options=['Visão Geral', 'Análise de Pilotos', 'Análise de Construtores', 'Análise de Circuitos', 'H2H Pilotos'],
            icons=['trophy', 'person-badge', 'tools', 'signpost-split', 'people-fill'],
            menu_icon='speed',
            default_index=0,
            styles={
                "container": {"padding": "5!important", "background-color": F1_BLACK},
                "icon": {"color": "white", "font-size": "23px"}, 
                "nav-link": {"font-size": "16px", "text-align": "left", "margin":"0px", "--hover-color": F1_RED},
                "nav-link-selected": {"background-color": F1_RED},
            }
        )
    
    if conn is None:
        return
    dados_completos = carregar_todos_os_dados()
    if any(df.empty for name, df in dados_completos.items()):
        st.error(f"Falha ao carregar um ou mais conjuntos de dados. Verifique a conexão e os nomes das tabelas no banco.")
        return

    page_map = {
        'Visão Geral': render_pagina_visao_geral,
        'Análise de Pilotos': render_pagina_analise_pilotos,
        'Análise de Construtores': render_pagina_analise_construtores,
        'Análise de Circuitos': render_pagina_analise_circuitos,
        'H2H Pilotos': render_pagina_h2h
    }
    page_function = page_map.get(app_page)
    if page_function:
        page_function(dados_completos)

if __name__ == "__main__":
    main()

if __name__ == "__main__":
    main()
