import streamlit as st
import psycopg2
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from streamlit_option_menu import option_menu

# --- CONFIGURAÇÃO DA PÁGINA E PALETA DE CORES ---
st.set_page_config(layout="wide", page_title="F1 Super Analytics", page_icon="f1.png")

F1_PALETTE = ["#E10600", "#15151E", "#7F7F7F", "#B1B1B8", "#FFFFFF", "#FF8700", "#00A000"]
F1_RED = F1_PALETTE[0]
F1_BLACK = F1_PALETTE[1]
F1_GREY = F1_PALETTE[2]

# --- FUNÇÕES DE BANCO DE DADOS (CORRIGIDO PARA SUPABASE) ---
@st.cache_resource
def conectar_db():
    try:
        db_secrets = st.secrets["database"]
        conn_str = db_secrets.get("uri") or db_secrets.get("url") or db_secrets.get("connection_string")
        if conn_str:
            return psycopg2.connect(conn_str)
        else:
            return psycopg2.connect(**db_secrets)
    except Exception as e:
        st.error(f"Erro CRÍTICO de conexão com o banco de dados: {e}")
        return None

conn = conectar_db()

@st.cache_data(ttl=3600)
def consultar_dados_df(query, params=None):
    if not conn: return pd.DataFrame()
    try:
        return pd.read_sql_query(query, conn, params=params)
    except Exception as e:
        st.warning(f"Erro ao consultar dados: {e}")
        return pd.DataFrame()

def executar_comando_sql(comando, params=None):
    if not conn: return False
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
        return False

# --- CARREGAMENTO CENTRALIZADO DE DADOS (CORRIGIDO) ---
@st.cache_data(ttl=3600)
def carregar_todos_os_dados():
    # Removidas as queries para tabelas que não existem
    queries = {
        "tbl_corridas": 'SELECT id_corrida, ano, rodada, nome_gp, id_circuito_fk FROM tbl_corridas',
        "tbl_resultados": 'SELECT posicao_final, pontos, posicao_grid, id_corrida_fk, id_piloto_fk, id_construtor_fk, id_status_fk FROM tbl_resultados',
        "tbl_pilotos": 'SELECT id_piloto, ref_piloto, numero, codigo, nome AS nome_piloto, sobrenome, data_nascimento, nacionalidade FROM tbl_pilotos',
        "tbl_construtores": 'SELECT id_construtor, ref_construtor, nome AS nome_construtor, nacionalidade AS nacionalidade_construtor FROM tbl_construtores',
        "tbl_circuitos": 'SELECT id_circuito, nome AS nome_circuito, cidade, pais FROM tbl_circuitos',
        "tbl_status_resultado": 'SELECT id_status, status FROM tbl_status_resultado'
    }
    data = {name: consultar_dados_df(query) for name, query in queries.items()}
    if not data.get("tbl_pilotos", pd.DataFrame()).empty:
        data["tbl_pilotos"]['nome_completo_piloto'] = data["tbl_pilotos"]['nome_piloto'] + ' ' + data["tbl_pilotos"]['sobrenome']
    return data

# --- RENDERIZAÇÃO DAS PÁGINAS (LÓGICA DE CÁLCULO AJUSTADA) ---

def render_pagina_visao_geral(data):
    st.title("🏁 Visão Geral da Temporada de F1")
    races, drivers, constructors, results = (
        data['tbl_corridas'], data['tbl_pilotos'], data['tbl_construtores'], data['tbl_resultados']
    )
    
    anos_disponiveis = sorted(races[races['ano'] <= 2024]['ano'].unique(), reverse=True)
    ano_selecionado = st.selectbox("Selecione a Temporada", anos_disponiveis, key="visao_geral_ano")

    # Filtra corridas e resultados para o ano selecionado
    races_ano = races[races['ano'] == ano_selecionado]
    if races_ano.empty:
        st.warning(f"Não há dados de corrida para a temporada de {ano_selecionado}.")
        return

    results_ano = results.merge(races_ano, left_on='id_corrida_fk', right_on='id_corrida')

    # Calcula a classificação dos pilotos
    driver_standings_final = results_ano.groupby('id_piloto_fk')['pontos'].sum().reset_index()
    driver_standings_final = driver_standings_final.sort_values(by='pontos', ascending=False).reset_index(drop=True)
    driver_standings_final['position'] = driver_standings_final.index + 1
    
    # Calcula a classificação dos construtores
    constructor_standings_final = results_ano.groupby('id_construtor_fk')['pontos'].sum().reset_index()
    constructor_standings_final = constructor_standings_final.sort_values(by='pontos', ascending=False).reset_index(drop=True)
    constructor_standings_final['position'] = constructor_standings_final.index + 1

    st.header(f"Resumo da Temporada de {ano_selecionado}")
    
    campeao_piloto_info = driver_standings_final[driver_standings_final['position'] == 1]
    nome_campeao_piloto = drivers[drivers['id_piloto'] == campeao_piloto_info['id_piloto_fk'].iloc[0]]['nome_completo_piloto'].iloc[0] if not campeao_piloto_info.empty else "N/A"
    
    campeao_constr_info = constructor_standings_final[constructor_standings_final['position'] == 1]
    nome_campeao_constr = constructors[constructors['id_construtor'] == campeao_constr_info['id_construtor_fk'].iloc[0]]['nome_construtor'].iloc[0] if not campeao_constr_info.empty else "N/A"

    col1, col2, col3 = st.columns(3)
    col1.metric("🏆 Campeão de Pilotos", nome_campeao_piloto)
    col2.metric("🏎️ Campeão de Construtores", nome_campeao_constr)
    col3.metric("🏁 Total de Corridas", races_ano['id_corrida'].nunique())
    st.divider()

    col_graf1, col_graf2 = st.columns(2)
    with col_graf1:
        st.subheader("🏆 Classificação Final de Pilotos (Top 10)")
        classificacao_pilotos = driver_standings_final.merge(drivers, left_on='id_piloto_fk', right_on='id_piloto').head(10)
        fig = px.bar(classificacao_pilotos, x='pontos', y='nome_completo_piloto', orientation='h', text='pontos', color_discrete_sequence=F1_PALETTE)
        fig.update_layout(yaxis={'categoryorder':'total ascending'}, xaxis_title="Pontos", yaxis_title="Piloto", showlegend=False)
        st.plotly_chart(fig, use_container_width=True)

    with col_graf2:
        st.subheader("🏎️ Classificação Final de Construtores")
        classificacao_constr = constructor_standings_final.merge(constructors, left_on='id_construtor_fk', right_on='id_construtor')
        fig = px.bar(classificacao_constr, x='pontos', y='nome_construtor', orientation='h', text='pontos', color_discrete_sequence=F1_PALETTE)
        fig.update_layout(yaxis={'categoryorder':'total ascending'}, xaxis_title="Pontos", yaxis_title="Construtor", showlegend=False)
        st.plotly_chart(fig, use_container_width=True)

def render_pagina_analise_pilotos(data):
    st.title("🧑‍🚀 Análise Detalhada de Pilotos")
    drivers, results, races = data['tbl_pilotos'], data['tbl_resultados'], data['tbl_corridas']
    piloto_selecionado = st.selectbox("Selecione um Piloto", options=drivers.sort_values('sobrenome')['nome_completo_piloto'], index=None, placeholder="Buscar piloto...")
    if piloto_selecionado:
        driver_id = drivers[drivers['nome_completo_piloto'] == piloto_selecionado]['id_piloto'].iloc[0]
        resultados_piloto = results[results['id_piloto_fk'] == driver_id]
        # Pole positions calculadas a partir de 'posicao_grid'
        poles_piloto = resultados_piloto[resultados_piloto['posicao_grid'] == 1].shape[0]
        
        col1, col2, col3, col4, col5 = st.columns(5)
        col1.metric("🏁 Corridas", resultados_piloto['id_corrida_fk'].nunique())
        col2.metric("🏆 Vitórias", resultados_piloto[resultados_piloto['posicao_final'] == 1].shape[0])
        col3.metric("🍾 Pódios", resultados_piloto[resultados_piloto['posicao_final'].isin([1, 2, 3])].shape[0])
        col4.metric("⏱️ Pole Positions", poles_piloto)
        col5.metric("💯 Total de Pontos", f"{resultados_piloto['pontos'].sum():,.0f}")
        st.divider()

        col_graf1, col_graf2 = st.columns(2)
        with col_graf1:
            st.subheader("Desempenho: Largada vs. Chegada")
            grid_vs_final = resultados_piloto[['posicao_grid', 'posicao_final']].dropna()
            grid_vs_final = grid_vs_final[(grid_vs_final['posicao_grid'] > 0) & (grid_vs_final['posicao_final'] > 0)]
            fig = px.scatter(grid_vs_final, x='posicao_grid', y='posicao_final', labels={'posicao_grid': 'Grid', 'posicao_final': 'Final'},
                             trendline='ols', trendline_color_override=F1_RED, color_discrete_sequence=[F1_BLACK])
            st.plotly_chart(fig, use_container_width=True)
        with col_graf2:
            st.subheader("Distribuição de Resultados (Top 10 Posições)")
            contagem_posicao = resultados_piloto['posicao_final'].value_counts().reset_index().sort_values('posicao_final').head(10)
            fig = px.bar(contagem_posicao, x='posicao_final', y='count', labels={'posicao_final': 'Posição', 'count': 'Nº de Vezes'},
                         text='count', color_discrete_sequence=[F1_RED])
            fig.update_layout(xaxis_type='category')
            st.plotly_chart(fig, use_container_width=True)
        
        st.subheader("Evolução na Carreira (Pontos por Temporada)")
        resultados_com_ano = resultados_piloto.merge(races, left_on='id_corrida_fk', right_on='id_corrida')
        pontos_por_ano = resultados_com_ano.groupby('ano')['pontos'].sum().reset_index()
        fig_evolucao = px.line(pontos_por_ano, x='ano', y='pontos', markers=True, color_discrete_sequence=[F1_RED])
        fig_evolucao.update_layout(xaxis_title="Temporada", yaxis_title="Pontos Acumulados")
        st.plotly_chart(fig_evolucao, use_container_width=True)

def render_pagina_analise_construtores(data):
    st.title("🔧 Análise Detalhada de Construtores")
    constructors, results, status, races = data['tbl_construtores'], data['tbl_resultados'], data['tbl_status_resultado'], data['tbl_corridas']
    construtor_selecionado = st.selectbox("Selecione um Construtor", options=constructors.sort_values('nome_construtor')['nome_construtor'], index=None, placeholder="Buscar construtor...")
    if construtor_selecionado:
        constructor_id = constructors[constructors['nome_construtor'] == construtor_selecionado]['id_construtor'].iloc[0]
        resultados_construtor = results[results['id_construtor_fk'] == constructor_id]
        
        # Lógica para calcular campeonatos
        results_com_ano = results.merge(races, left_on='id_corrida_fk', right_on='id_corrida')
        pontos_por_ano_construtor = results_com_ano.groupby(['ano', 'id_construtor_fk'])['pontos'].sum().reset_index()
        campeoes_por_ano = pontos_por_ano_construtor.loc[pontos_por_ano_construtor.groupby('ano')['pontos'].idxmax()]
        campeonatos = campeoes_por_ano[campeoes_por_ano['id_construtor_fk'] == constructor_id].shape[0]

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
            finished_statuses = ['Finished'] + [f'+{i} Lap' for i in range(1, 20)] + [f'+{i} Laps' for i in range(1, 20)]
            status_merged['category'] = status_merged['status'].apply(lambda x: 'Finalizou' if x in finished_statuses else 'Não Finalizou')
            category_summary = status_merged.groupby('category')['status'].count().reset_index(name='count')
            fig = px.pie(category_summary, names='category', values='count', hole=0.4, 
                         color_discrete_map={'Finalizou': 'green', 'Não Finalizou': F1_RED})
            st.plotly_chart(fig, use_container_width=True)
        with col_graf2:
            st.subheader("Evolução (Pontos por Temporada)")
            resultados_com_ano_equipe = resultados_construtor.merge(races, left_on='id_corrida_fk', right_on='id_corrida')
            pontos_por_ano = resultados_com_ano_equipe.groupby('ano')['pontos'].sum().reset_index()
            fig_evolucao = px.bar(pontos_por_ano, x='ano', y='pontos', color_discrete_sequence=[F1_GREY])
            fig_evolucao.update_layout(xaxis_title="Temporada", yaxis_title="Pontos Acumulados", showlegend=False)
            st.plotly_chart(fig_evolucao, use_container_width=True)

def render_pagina_analise_circuitos(data):
    st.title("🛣️ Análise de Circuitos")
    circuits, races, results, drivers = data['tbl_circuitos'], data['tbl_corridas'], data['tbl_resultados'], data['tbl_pilotos']
    circuito_selecionado = st.selectbox("Selecione um Circuito", options=circuits.sort_values('nome_circuito')['nome_circuito'], index=None, placeholder="Buscar circuito...")
    if circuito_selecionado:
        circuit_id = circuits[circuits['nome_circuito'] == circuito_selecionado]['id_circuito'].iloc[0]
        corridas_no_circuito = races[races['id_circuito_fk'] == circuit_id]
        resultados_circuito = results[results['id_corrida_fk'].isin(corridas_no_circuito['id_corrida'])]
        
        vencedores = resultados_circuito[resultados_circuito['posicao_final'] == 1].merge(drivers, left_on='id_piloto_fk', right_on='id_piloto')
        maiores_vencedores = vencedores['nome_completo_piloto'].value_counts().reset_index().head(5)
        maiores_vencedores.columns = ['Piloto', 'Vitórias']

        st.metric("🏁 Total de Corridas Realizadas", corridas_no_circuito['id_corrida'].nunique())
        st.divider()

        st.subheader(f"Reis da Pista: Maiores Vencedores em {circuito_selecionado}")
        fig = px.bar(maiores_vencedores, x='Vitórias', y='Piloto', orientation='h', text='Vitórias', color_discrete_sequence=[F1_RED])
        fig.update_layout(yaxis={'categoryorder':'total ascending'}, showlegend=False)
        st.plotly_chart(fig, use_container_width=True)

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

        fig = go.Figure()
        fig.add_trace(go.Bar(name=piloto1, x=['Vitórias', 'Pódios', 'Pontos'], y=[stats1[stats1['posicao_final'] == 1].shape[0], stats1[stats1['posicao_final'].isin([1,2,3])].shape[0], stats1['pontos'].sum()], marker_color=F1_RED))
        fig.add_trace(go.Bar(name=piloto2, x=['Vitórias', 'Pódios', 'Pontos'], y=[stats2[stats2['posicao_final'] == 1].shape[0], stats2[stats2['posicao_final'].isin([1,2,3])].shape[0], stats2['pontos'].sum()], marker_color=F1_GREY))
        fig.update_layout(barmode='group', title_text='Estatísticas da Carreira', yaxis_title="Total")
        st.plotly_chart(fig, use_container_width=True)

        corridas_juntos = stats1.merge(stats2, on='id_corrida_fk', suffixes=('_p1', '_p2'))
        vitorias_h2h_p1 = corridas_juntos[corridas_juntos['posicao_final_p1'] < corridas_juntos['posicao_final_p2']].shape[0]
        vitorias_h2h_p2 = corridas_juntos[corridas_juntos['posicao_final_p2'] < corridas_juntos['posicao_final_p1']].shape[0]

        st.subheader("Resultados em Corridas Juntos")
        col_h2h1, col_h2h2, col_h2h3 = st.columns(3)
        col_h2h1.metric("Total de Corridas Juntos", corridas_juntos.shape[0])
        col_h2h2.metric(f"Vantagem para {piloto1}", f"{vitorias_h2h_p1} vezes")
        col_h2h3.metric(f"Vantagem para {piloto2}", f"{vitorias_h2h_p2} vezes")

def render_pagina_crud(data):
    st.title("🔩 Gerenciamento de Dados (CRUD)")
    drivers, constructors = data['tbl_pilotos'], data['tbl_construtores']

    tab_create, tab_read, tab_update, tab_delete = st.tabs(["➕ Adicionar", "🔍 Consultar", "🔄 Atualizar", "❌ Deletar"])

    with tab_create:
        st.subheader("Adicionar Novo Piloto")
        with st.form("form_novo_piloto", clear_on_submit=True):
            ref = st.text_input("Referência (ex: verstappen)")
            num = st.number_input("Número", min_value=1, max_value=99, value=None, format="%d")
            code = st.text_input("Código (3 letras, ex: VER)", max_chars=3)
            fname = st.text_input("Nome")
            sname = st.text_input("Sobrenome")
            dob = st.date_input("Data de Nascimento")
            nac = st.text_input("Nacionalidade")
            if st.form_submit_button("Adicionar Piloto"):
                query = "INSERT INTO tbl_pilotos (ref_piloto, numero, codigo, nome, sobrenome, data_nascimento, nacionalidade) VALUES (%s, %s, %s, %s, %s, %s, %s)"
                if executar_comando_sql(query, (ref, num, code.upper(), fname, sname, dob, nac)):
                    st.success(f"Piloto {fname} {sname} adicionado com sucesso!")
                    st.rerun()
    
    with tab_read:
        st.subheader("Consultar Dados")
        tabela_selecionada = st.radio("Selecione a tabela para visualizar:", ("Pilotos", "Construtores"), horizontal=True)
        if tabela_selecionada == "Pilotos":
            st.dataframe(drivers, use_container_width=True)
        else:
            st.dataframe(constructors, use_container_width=True)
            
    with tab_update:
        st.subheader("Atualizar Nacionalidade de um Construtor")
        constr_list = constructors.sort_values('nome_construtor')['nome_construtor'].tolist()
        constr_sel = st.selectbox("Selecione o Construtor", options=constr_list, index=None, placeholder="Selecione...")
        if constr_sel:
            id_constr = int(constructors[constructors['nome_construtor'] == constr_sel]['id_construtor'].iloc[0])
            nova_nac = st.text_input("Digite a Nova Nacionalidade", key=f"nac_{id_constr}")
            if st.button("Atualizar Nacionalidade"):
                if executar_comando_sql("UPDATE tbl_construtores SET nacionalidade_construtor = %s WHERE id_construtor = %s", (nova_nac, id_constr)):
                    st.success(f"Nacionalidade de '{constr_sel}' atualizada!")
                    st.rerun()

    with tab_delete:
        st.subheader("Deletar um Piloto")
        st.warning("A exclusão de um piloto é irreversível e pode afetar dados históricos.", icon="⚠️")
        piloto_del = st.selectbox("Selecione o Piloto a ser deletado", options=drivers.sort_values('sobrenome')['nome_completo_piloto'], index=None, placeholder="Selecione...")
        if piloto_del and st.button(f"DELETAR {piloto_del}", type="primary"):
            id_piloto_del = int(drivers[drivers['nome_completo_piloto'] == piloto_del]['id_piloto'].iloc[0])
            if executar_comando_sql("DELETE FROM tbl_pilotos WHERE id_piloto = %s", (id_piloto_del,)):
                st.success(f"Piloto '{piloto_del}' deletado com sucesso.")
                st.rerun()

# --- ESTRUTURA PRINCIPAL DO APP ---
def main():
    with st.sidebar:
        st.image("f1_logo.png", width=250)
        app_page = option_menu(
            menu_title='F1 Super Analytics',
            options=['Visão Geral', 'Análise de Pilotos', 'Análise de Construtores', 'Análise de Circuitos', 'H2H Pilotos', 'Gerenciamento'],
            icons=['trophy-fill', 'person-badge', 'tools', 'signpost-split', 'people-fill', 'database-fill-gear'],
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
        st.warning("Por favor, verifique as configurações de conexão no secrets do Streamlit.")
        return
        
    dados_completos = carregar_todos_os_dados()
    if any(df.empty for df in dados_completos.values()):
        st.error("Falha ao carregar um ou mais conjuntos de dados. Verifique a conexão e os nomes das tabelas no banco.")
        return

    page_map = {
        'Visão Geral': render_pagina_visao_geral,
        'Análise de Pilotos': render_pagina_analise_pilotos,
        'Análise de Construtores': render_pagina_analise_construtores,
        'Análise de Circuitos': render_pagina_analise_circuitos,
        'H2H Pilotos': render_pagina_h2h,
        'Gerenciamento': render_pagina_crud
    }
    
    page_function = page_map.get(app_page)
    if page_function:
        page_function(dados_completos)

if __name__ == "__main__":
    main()
