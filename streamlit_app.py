import streamlit as st
import psycopg2
import pandas as pd
import plotly.express as px
from streamlit_option_menu import option_menu

st.set_page_config(layout="wide", page_title="F1 Super Analytics", page_icon="f1.png")

F1_RED = "#E10600"

@st.cache_resource
def conectar_db():
    try:
        return psycopg2.connect(**st.secrets["database"])
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
        "races": "SELECT raceId, year, round, circuitId, name as race_name, date FROM races",
        "results": "SELECT resultId, raceId, driverId, constructorId, grid, positionOrder, points, laps, fastestLap, statusId FROM results",
        "drivers": "SELECT driverId, driverRef, number, code, forename, surname, dob, nationality FROM drivers",
        "constructors": "SELECT constructorId, constructorRef, name as constructor_name, nationality as constructor_nationality FROM constructors",
        "driver_standings": "SELECT raceId, driverId, points, position, wins FROM driver_standings",
        "constructor_standings": "SELECT raceId, constructorId, points, position, wins FROM constructor_standings",
        "pit_stops": "SELECT raceId, driverId, stop, lap, milliseconds FROM pit_stops",
        "qualifying": "SELECT raceId, driverId, constructorId, position as quali_position FROM qualifying",
        "circuits": "SELECT circuitId, name as circuit_name, location, country FROM circuits",
        "status": "SELECT statusId, status FROM status"
    }
    data = {name: consultar_dados_df(query) for name, query in queries.items()}
    if not data["drivers"].empty:
        data["drivers"]['driver_name'] = data["drivers"]['forename'] + ' ' + data["drivers"]['surname']
    return data

def render_pagina_visao_geral(data):
    st.title("🏁 Visão Geral da Temporada de F1")
    races, results, drivers, constructors, driver_standings, constructor_standings, pit_stops = (
        data['races'], data['results'], data['drivers'], data['constructors'],
        data['driver_standings'], data['constructor_standings'], data['pit_stops']
    )
    st.sidebar.header("Filtros de Análise")
    anos_disponiveis = sorted(races[races['year'] <= 2024]['year'].unique(), reverse=True)
    ano_selecionado = st.sidebar.selectbox("Selecione a Temporada", anos_disponiveis, key="visao_geral_ano")

    races_ano = races[races['year'] == ano_selecionado]
    race_ids_ano = races_ano['raceId'].unique()

    if races_ano.empty:
        st.warning(f"Não há dados de corrida para a temporada de {ano_selecionado}.")
        return

    st.header(f"Resumo da Temporada de {ano_selecionado}")
    ultima_corrida_id = races_ano.sort_values(by='round', ascending=False).iloc[0]['raceId']

    driver_standings_final = driver_standings[driver_standings['raceId'] == ultima_corrida_id]
    campeao_piloto_info = driver_standings_final[driver_standings_final['position'] == 1]
    nome_campeao_piloto = drivers[drivers['driverId'] == campeao_piloto_info['driverId'].iloc[0]]['driver_name'].iloc[0] if not campeao_piloto_info.empty else "N/A"

    constructor_standings_final = constructor_standings[constructor_standings['raceId'] == ultima_corrida_id]
    campeao_constr_info = constructor_standings_final[constructor_standings_final['position'] == 1]
    nome_campeao_constr = constructors[constructors['constructorId'] == campeao_constr_info['constructorId'].iloc[0]]['constructor_name'].iloc[0] if not campeao_constr_info.empty else "N/A"

    pit_stops_ano = pit_stops[pit_stops['raceId'].isin(race_ids_ano)]
    media_pit_stop = pit_stops_ano['milliseconds'].mean() / 1000 if not pit_stops_ano.empty else 0
    media_pit_stop_str = f"{media_pit_stop:.3f}s" if media_pit_stop > 0 else "N/A"

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("🏆 Campeão de Pilotos", nome_campeao_piloto)
    col2.metric("🏎️ Campeão de Construtores", nome_campeao_constr)
    col3.metric("🏁 Total de Corridas", len(race_ids_ano))
    col4.metric("⏱️ Média de Pit Stop", media_pit_stop_str)
    st.divider()

    col_graf1, col_graf2 = st.columns(2)
    with col_graf1:
        st.subheader("🏆 Classificação Final de Pilotos")
        classificacao_pilotos = driver_standings_final.merge(drivers, on='driverId').sort_values(by='position').head(10)
        fig = px.bar(classificacao_pilotos, x='points', y='driver_name', orientation='h', text='points', color_discrete_sequence=[F1_RED])
        fig.update_layout(yaxis={'categoryorder':'total ascending'}, xaxis_title="Pontos", yaxis_title="Piloto")
        st.plotly_chart(fig, use_container_width=True)

    with col_graf2:
        st.subheader("🏎️ Classificação Final de Construtores")
        classificacao_constr = constructor_standings_final.merge(constructors, on='constructorId').sort_values(by='position')
        fig = px.bar(classificacao_constr, x='points', y='constructor_name', orientation='h', text='points', color_discrete_sequence=[F1_RED])
        fig.update_layout(yaxis={'categoryorder':'total ascending'}, xaxis_title="Pontos", yaxis_title="Construtor")
        st.plotly_chart(fig, use_container_width=True)

def render_pagina_analise_pilotos(data):
    st.title("🧑‍🚀 Análise Detalhada de Pilotos")
    drivers, results, qualifying, races = data['drivers'], data['results'], data['qualifying'], data['races']
    
    piloto_selecionado = st.selectbox("Selecione um Piloto", options=drivers.sort_values('surname')['driver_name'], index=None, placeholder="Buscar piloto...")

    if piloto_selecionado:
        driver_id = drivers[drivers['driver_name'] == piloto_selecionado]['driverId'].iloc[0]
        resultados_piloto = results[results['driverId'] == driver_id]
        poles_piloto = qualifying[(qualifying['driverId'] == driver_id) & (qualifying['quali_position'] == 1)]
        
        total_corridas = resultados_piloto['raceId'].nunique()
        total_vitorias = resultados_piloto[resultados_piloto['positionOrder'] == 1].shape[0]
        total_podios = resultados_piloto[resultados_piloto['positionOrder'].isin([1, 2, 3])].shape[0]
        total_poles = poles_piloto.shape[0]
        total_pontos = resultados_piloto['points'].sum()

        col1, col2, col3, col4, col5 = st.columns(5)
        col1.metric("🏁 Corridas", total_corridas)
        col2.metric("🏆 Vitórias", total_vitorias)
        col3.metric("🍾 Pódios", total_podios)
        col4.metric("⏱️ Pole Positions", total_poles)
        col5.metric("💯 Total de Pontos", f"{total_pontos:,.0f}")
        st.divider()

        col_graf1, col_graf2 = st.columns(2)
        with col_graf1:
            st.subheader("Desempenho por Posição de Largada vs. Chegada")
            grid_vs_final = resultados_piloto[['grid', 'positionOrder']]
            grid_vs_final = grid_vs_final[(grid_vs_final['grid'] > 0) & (grid_vs_final['positionOrder'] > 0)]
            fig = px.scatter(grid_vs_final, x='grid', y='positionOrder', labels={'grid': 'Posição de Largada', 'positionOrder': 'Posição Final'},
                             trendline='ols', trendline_color_override=F1_RED)
            st.plotly_chart(fig, use_container_width=True)

        with col_graf2:
            st.subheader("Distribuição de Resultados Finais")
            contagem_posicao = resultados_piloto['positionOrder'].value_counts().reset_index().sort_values('positionOrder')
            fig = px.bar(contagem_posicao.head(10), x='positionOrder', y='count', labels={'positionOrder': 'Posição Final', 'count': 'Número de Vezes'},
                         text='count', color_discrete_sequence=[F1_RED])
            fig.update_layout(xaxis_type='category')
            st.plotly_chart(fig, use_container_width=True)

def render_pagina_analise_construtores(data):
    st.title("🔧 Análise Detalhada de Construtores")
    constructors, results, status, races = data['constructors'], data['results'], data['status'], data['races']

    construtor_selecionado = st.selectbox("Selecione um Construtor", options=constructors.sort_values('constructor_name')['constructor_name'], index=None, placeholder="Buscar construtor...")

    if construtor_selecionado:
        constructor_id = constructors[constructors['constructor_name'] == construtor_selecionado]['constructorId'].iloc[0]
        resultados_construtor = results[results['constructorId'] == constructor_id]
        
        total_corridas = resultados_construtor['raceId'].nunique()
        total_vitorias = resultados_construtor[resultados_construtor['positionOrder'] == 1].shape[0]
        total_pontos = resultados_construtor['points'].sum()

        col1, col2, col3 = st.columns(3)
        col1.metric("🏁 Corridas Disputadas", total_corridas)
        col2.metric("🏆 Total de Vitórias", total_vitorias)
        col3.metric("💯 Total de Pontos", f"{total_pontos:,.0f}")
        st.divider()

        st.subheader("Análise de Confiabilidade (Status de Chegada)")
        status_merged = resultados_construtor.merge(status, on='statusId')
        status_counts = status_merged['status'].value_counts().reset_index()
        
        finished_statuses = ['Finished'] + [f'+{i} Lap' for i in range(1, 10)]
        status_counts['category'] = status_counts['status'].apply(lambda x: 'Finalizou' if x in finished_statuses else 'Não Finalizou (Problema)')
        
        category_summary = status_counts.groupby('category')['count'].sum().reset_index()

        fig = px.pie(category_summary, names='category', values='count', hole=0.4, 
                     color_discrete_map={'Finalizou': 'green', 'Não Finalizou (Problema)': F1_RED})
        st.plotly_chart(fig, use_container_width=True)

def render_pagina_crud(data):
    st.title("🔩 Gerenciamento de Dados (CRUD)")
    drivers, constructors = data['drivers'], data['constructors']

    tab_create, tab_update, tab_delete = st.tabs(["➕ Criar", "✏️ Atualizar", "❌ Deletar"])

    with tab_create:
        st.subheader("Adicionar Novo Piloto")
        with st.form("form_novo_piloto"):
            ref = st.text_input("Referência (ex: verstappen)")
            num = st.number_input("Número", min_value=1, max_value=99)
            code = st.text_input("Código (3 letras, ex: VER)", max_chars=3)
            fname = st.text_input("Nome")
            sname = st.text_input("Sobrenome")
            dob = st.date_input("Data de Nascimento")
            nac = st.text_input("Nacionalidade")
            if st.form_submit_button("Adicionar Piloto"):
                query = "INSERT INTO drivers (driverRef, number, code, forename, surname, dob, nationality) VALUES (%s, %s, %s, %s, %s, %s, %s)"
                if executar_comando_sql(query, (ref, num, code.upper(), fname, sname, dob, nac)):
                    st.success(f"Piloto {fname} {sname} adicionado com sucesso!")
                    
    with tab_update:
        st.subheader("Atualizar Nacionalidade de um Construtor")
        constr_list = constructors.sort_values('constructor_name')['constructor_name'].tolist()
        constr_sel = st.selectbox("Selecione o Construtor", options=constr_list, index=None)
        if constr_sel:
            id_constr = int(constructors[constructors['constructor_name'] == constr_sel]['constructorId'].iloc[0])
            nova_nac = st.text_input("Digite a Nova Nacionalidade", key=f"nac_{id_constr}")
            if st.button("Atualizar Nacionalidade"):
                if executar_comando_sql("UPDATE constructors SET nationality = %s WHERE constructorId = %s", (nova_nac, id_constr)):
                    st.success(f"Nacionalidade de '{constr_sel}' atualizada!")

    with tab_delete:
        st.subheader("Deletar um Piloto")
        st.warning("A exclusão de um piloto é irreversível e pode afetar dados históricos.", icon="⚠️")
        piloto_del = st.selectbox("Selecione o Piloto a ser deletado", options=drivers.sort_values('surname')['driver_name'], index=None)
        if piloto_del and st.button(f"DELETAR {piloto_del}", type="primary"):
            id_piloto_del = int(drivers[drivers['driver_name'] == piloto_del]['driverId'].iloc[0])
            if executar_comando_sql("DELETE FROM drivers WHERE driverId = %s", (id_piloto_del,)):
                st.success(f"Piloto '{piloto_del}' deletado com sucesso.")

def main():
    with st.sidebar:
        app_page = option_menu(
            menu_title='F1 Super Analytics',
            options=['Visão Geral', 'Análise de Pilotos', 'Análise de Construtores', 'CRUD'],
            icons=['trophy', 'person-badge', 'tools', 'pencil-square'],
            menu_icon='speed',
            default_index=0,
            styles={
                "container": {"padding": "5!important", "background-color": "#15151E"},
                "icon": {"color": "white", "font-size": "25px"}, 
                "nav-link": {"font-size": "16px", "text-align": "left", "margin":"0px", "--hover-color": F1_RED},
                "nav-link-selected": {"background-color": F1_RED},
            }
        )
    
    dados_completos = carregar_todos_os_dados()
    if any(df.empty for df in dados_completos.values()):
        st.error("Falha ao carregar um ou mais conjuntos de dados. A aplicação não pode continuar. Verifique a conexão com o banco e os nomes das tabelas.")
        return

    if app_page == 'Visão Geral':
        render_pagina_visao_geral(dados_completos)
    elif app_page == 'Análise de Pilotos':
        render_pagina_analise_pilotos(dados_completos)
    elif app_page == 'Análise de Construtores':
        render_pagina_analise_construtores(dados_completos)
    elif app_page == 'CRUD':
        render_pagina_crud(dados_completos)

if __name__ == "__main__":
    main()
