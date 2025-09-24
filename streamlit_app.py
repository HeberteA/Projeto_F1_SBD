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
        "tbl_corridas": "SELECT id_corrida, ano, rodada, nome_gp, data_corrida, id_circuito_fk FROM tbl_corridas",
        "tbl_resultados": "SELECT id_resultado, posicao_final, pontos, posicao_grid, voltas, id_corrida_fk, id_piloto_fk, id_construtor_fk, id_status_fk FROM tbl_resultados",
        "tbl_pilotos": "SELECT id_piloto, ref_piloto, numero, codigo, nome as nome_piloto, sobrenome, data_nascimento, nacionalidade FROM tbl_pilotos",
        "tbl_construtores": "SELECT id_construtor, ref_construtor, nome as nome_construtor, nacionalidade as nacionalidade_construtor FROM tbl_construtores",
        "driver_standings": "SELECT raceId, driverId, points, position, wins FROM driver_standings",
        "constructor_standings": "SELECT raceId, constructorId, points, position, wins FROM constructor_standings",
        "pit_stops": "SELECT raceId, driverId, stop, lap, milliseconds FROM pit_stops",
        "qualifying": "SELECT raceId, driverId, constructorId, position as quali_position FROM qualifying",
        "tbl_circuitos": "SELECT id_circuito, nome as nome_circuito, cidade, pais FROM tbl_circuitos",
        "tbl_status_resultado": "SELECT id_status, status FROM tbl_status_resultado"
    }
    data = {name: consultar_dados_df(query) for name, query in queries.items()}
    if not data["tbl_pilotos"].empty:
        data["tbl_pilotos"]['nome_completo_piloto'] = data["tbl_pilotos"]['nome_piloto'] + ' ' + data["tbl_pilotos"]['sobrenome']
    return data

def render_pagina_visao_geral(data):
    st.title("🏁 Visão Geral da Temporada de F1")
    races, results, drivers, constructors, driver_standings, constructor_standings, pit_stops = (
        data['tbl_corridas'], data['tbl_resultados'], data['tbl_pilotos'], data['tbl_construtores'],
        data['driver_standings'], data['constructor_standings'], data['pit_stops']
    )
    st.sidebar.header("Filtros de Análise")
    anos_disponiveis = sorted(races[races['ano'] <= 2024]['ano'].unique(), reverse=True)
    ano_selecionado = st.sidebar.selectbox("Selecione a Temporada", anos_disponiveis, key="visao_geral_ano")

    races_ano = races[races['ano'] == ano_selecionado]
    race_ids_ano = races_ano['id_corrida'].unique()

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
        
        total_corridas = resultados_piloto['id_corrida_fk'].nunique()
        total_vitorias = resultados_piloto[resultados_piloto['posicao_final'] == 1].shape[0]
        total_podios = resultados_piloto[resultados_piloto['posicao_final'].isin([1, 2, 3])].shape[0]
        total_poles = poles_piloto.shape[0]
        total_pontos = resultados_piloto['pontos'].sum()

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
            grid_vs_final = resultados_piloto[['posicao_grid', 'posicao_final']]
            grid_vs_final = grid_vs_final[(grid_vs_final['posicao_grid'] > 0) & (grid_vs_final['posicao_final'] > 0)]
            fig = px.scatter(grid_vs_final, x='posicao_grid', y='posicao_final', labels={'posicao_grid': 'Posição de Largada', 'posicao_final': 'Posição Final'},
                             trendline='ols', trendline_color_override=F1_RED)
            st.plotly_chart(fig, use_container_width=True)

        with col_graf2:
            st.subheader("Distribuição de Resultados Finais")
            contagem_posicao = resultados_piloto['posicao_final'].value_counts().reset_index().sort_values('posicao_final')
            fig = px.bar(contagem_posicao.head(10), x='posicao_final', y='count', labels={'posicao_final': 'Posição Final', 'count': 'Número de Vezes'},
                         text='count', color_discrete_sequence=[F1_RED])
            fig.update_layout(xaxis_type='category')
            st.plotly_chart(fig, use_container_width=True)

def render_pagina_analise_construtores(data):
    st.title("🔧 Análise Detalhada de Construtores")
    constructors, results, status = data['tbl_construtores'], data['tbl_resultados'], data['tbl_status_resultado']

    construtor_selecionado = st.selectbox("Selecione um Construtor", options=constructors.sort_values('nome_construtor')['nome_construtor'], index=None, placeholder="Buscar construtor...")

    if construtor_selecionado:
        constructor_id = constructors[constructors['nome_construtor'] == construtor_selecionado]['id_construtor'].iloc[0]
        resultados_construtor = results[results['id_construtor_fk'] == constructor_id]
        
        total_corridas = resultados_construtor['id_corrida_fk'].nunique()
        total_vitorias = resultados_construtor[resultados_construtor['posicao_final'] == 1].shape[0]
        total_pontos = resultados_construtor['pontos'].sum()

        col1, col2, col3 = st.columns(3)
        col1.metric("🏁 Corridas Disputadas", total_corridas)
        col2.metric("🏆 Total de Vitórias", total_vitorias)
        col3.metric("💯 Total de Pontos", f"{total_pontos:,.0f}")
        st.divider()

        st.subheader("Análise de Confiabilidade (Status de Chegada)")
        status_merged = resultados_construtor.merge(status, left_on='id_status_fk', right_on='id_status')
        status_counts = status_merged['status'].value_counts().reset_index()
        
        finished_statuses = ['Finished'] + [f'+{i} Lap' for i in range(1, 10)]
        status_counts['category'] = status_counts['status'].apply(lambda x: 'Finalizou' if x in finished_statuses else 'Não Finalizou (Problema)')
        
        category_summary = status_counts.groupby('category')['count'].sum().reset_index()

        fig = px.pie(category_summary, names='category', values='count', hole=0.4, 
                     color_discrete_map={'Finalizou': 'green', 'Não Finalizou (Problema)': F1_RED})
        st.plotly_chart(fig, use_container_width=True)

def render_pagina_crud(data):
    st.title("🔩 Gerenciamento de Dados (CRUD)")
    drivers, constructors = data['tbl_pilotos'], data['tbl_construtores']

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
                query = "INSERT INTO tbl_pilotos (ref_piloto, numero, codigo, nome, sobrenome, data_nascimento, nacionalidade) VALUES (%s, %s, %s, %s, %s, %s, %s)"
                if executar_comando_sql(query, (ref, num, code.upper(), fname, sname, dob, nac)):
                    st.success(f"Piloto {fname} {sname} adicionado com sucesso!")
                    
    with tab_update:
        st.subheader("Atualizar Nacionalidade de um Construtor")
        constr_list = constructors.sort_values('nome_construtor')['nome_construtor'].tolist()
        constr_sel = st.selectbox("Selecione o Construtor", options=constr_list, index=None)
        if constr_sel:
            id_constr = int(constructors[constructors['nome_construtor'] == constr_sel]['id_construtor'].iloc[0])
            nova_nac = st.text_input("Digite a Nova Nacionalidade", key=f"nac_{id_constr}")
            if st.button("Atualizar Nacionalidade"):
                if executar_comando_sql("UPDATE tbl_construtores SET nacionalidade = %s WHERE id_construtor = %s", (nova_nac, id_constr)):
                    st.success(f"Nacionalidade de '{constr_sel}' atualizada!")

    with tab_delete:
        st.subheader("Deletar um Piloto")
        st.warning("A exclusão de um piloto é irreversível e pode afetar dados históricos.", icon="⚠️")
        piloto_del = st.selectbox("Selecione o Piloto a ser deletado", options=drivers.sort_values('sobrenome')['nome_completo_piloto'], index=None)
        if piloto_del and st.button(f"DELETAR {piloto_del}", type="primary"):
            id_piloto_del = int(drivers[drivers['nome_completo_piloto'] == piloto_del]['id_piloto'].iloc[0])
            if executar_comando_sql("DELETE FROM tbl_pilotos WHERE id_piloto = %s", (id_piloto_del,)):
                st.success(f"Piloto '{piloto_del}' deletado com sucesso.")

def main():
    with st.sidebar:
        st.image("f1_logo.png", width=300)
        app_page = option_menu(
            menu_title='F1 Super Analytics',
            options=['Visão Geral', 'Análise de Pilotos', 'Análise de Construtores', 'CRUD'],
            icons=['trophy', 'person-badge', 'tools', 'pencil-square'],
            menu_icon='speed',
            default_index=0,
            styles={
                "container": {"padding": "5!important", "background-color": F1_BLACK},
                "icon": {"color": "white", "font-size": "25px"}, 
                "nav-link": {"font-size": "16px", "text-align": "left", "margin":"0px", "--hover-color": F1_RED},
                "nav-link-selected": {"background-color": F1_RED},
            }
        )
    
    if conn is None:
        return

    dados_completos = carregar_todos_os_dados()
    if any(df.empty for df in dados_completos.values()):
        st.error("Falha ao carregar um ou mais conjuntos de dados. A aplicação não pode continuar. Verifique os nomes das tabelas no banco de dados.")
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
