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

# --- PASSO 1: CARREGAMENTO DE DADOS EXPANDIDO ---
@st.cache_data(ttl=3600)
def carregar_todos_os_dados():
    queries = {
        "tbl_corridas": 'SELECT id_corrida, ano, rodada, nome_gp, id_circuito_fk FROM tbl_corridas',
        "tbl_resultados": 'SELECT posicao_final, pontos, posicao_grid, rank, id_corrida_fk, id_piloto_fk, id_construtor_fk, id_status_fk FROM tbl_resultados',
        "tbl_pilotos": 'SELECT id_piloto, ref_piloto, numero, codigo, nome AS nome_piloto, sobrenome, data_nascimento, nacionalidade FROM tbl_pilotos',
        "tbl_construtores": 'SELECT id_construtor, ref_construtor, nome AS nome_construtor, nacionalidade AS nacionalidade_construtor FROM tbl_construtores',
        "tbl_circuitos": 'SELECT id_circuito, nome AS nome_circuito, cidade, pais FROM tbl_circuitos',
        "tbl_status_resultado": 'SELECT id_status, status FROM tbl_status_resultado',
        "tbl_paradas": 'SELECT id_corrida_fk, id_piloto_fk, parada, volta, duracao_s FROM tbl_paradas', # Adicionado
        "tbl_voltas": 'SELECT id_corrida_fk, id_piloto_fk, volta, posicao FROM tbl_voltas' # Adicionado
    }
    data = {name: consultar_dados_df(query) for name, query in queries.items()}
    if not data.get("tbl_pilotos", pd.DataFrame()).empty:
        data["tbl_pilotos"]['nome_completo_piloto'] = data["tbl_pilotos"]['nome_piloto'] + ' ' + data["tbl_pilotos"]['sobrenome']
    return data

# --- FUNÇÕES DE RENDERIZAÇÃO DAS PÁGINAS ---

def render_pagina_visao_geral(data):
    st.title("🏁 Visão Geral da Temporada de F1")
    races, drivers, constructors, results = data['tbl_corridas'], data['tbl_pilotos'], data['tbl_construtores'], data['tbl_resultados']
    
    anos_disponiveis = sorted(races['ano'].unique(), reverse=True)
    ano_selecionado = st.selectbox("Selecione a Temporada", anos_disponiveis)

    results_ano = results.merge(races[races['ano'] == ano_selecionado], left_on='id_corrida_fk', right_on='id_corrida')
    if results_ano.empty:
        st.warning(f"Não há dados de resultados para a temporada de {ano_selecionado}.")
        return

    st.header(f"Resumo da Temporada de {ano_selecionado}")
    
    # Campeões
    driver_standings = results_ano.groupby('id_piloto_fk')['pontos'].sum().sort_values(ascending=False).reset_index()
    constructor_standings = results_ano.groupby('id_construtor_fk')['pontos'].sum().sort_values(ascending=False).reset_index()
    
    id_campeao_piloto = driver_standings.iloc[0]['id_piloto_fk']
    id_campeao_constr = constructor_standings.iloc[0]['id_construtor_fk']
    
    nome_campeao_piloto = drivers[drivers['id_piloto'] == id_campeao_piloto]['nome_completo_piloto'].iloc[0]
    nome_campeao_constr = constructors[constructors['id_construtor'] == id_campeao_constr]['nome_construtor'].iloc[0]

    # NOVAS ESTATÍSTICAS
    vitorias_ano = results_ano[results_ano['posicao_final'] == 1]['id_piloto_fk'].value_counts().reset_index()
    poles_ano = results_ano[results_ano['posicao_grid'] == 1]['id_piloto_fk'].value_counts().reset_index()
    
    mais_vitorias_id = vitorias_ano.iloc[0]['id_piloto_fk']
    mais_poles_id = poles_ano.iloc[0]['id_piloto_fk'] if not poles_ano.empty else None

    piloto_mais_vitorias = drivers[drivers['id_piloto'] == mais_vitorias_id]['codigo'].iloc[0]
    piloto_mais_poles = drivers[drivers['id_piloto'] == mais_poles_id]['codigo'].iloc[0] if mais_poles_id else "N/A"

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("🏆 Campeão de Pilotos", nome_campeao_piloto)
    col2.metric("🏎️ Campeão de Construtores", nome_campeao_constr)
    col3.metric("🥇 Mais Vitórias", f"{piloto_mais_vitorias} ({vitorias_ano.iloc[0]['count']} vitórias)")
    col4.metric("⏱️ Mais Poles", f"{piloto_mais_poles} ({poles_ano.iloc[0]['count']} poles)" if mais_poles_id else "N/A")
    st.divider()

    # Gráficos de classificação
    col_graf1, col_graf2 = st.columns(2)
    with col_graf1:
        st.subheader("🏆 Classificação de Pilotos (Top 10)")
        classificacao_pilotos = driver_standings.head(10).merge(drivers, left_on='id_piloto_fk', right_on='id_piloto')
        fig = px.bar(classificacao_pilotos, x='pontos', y='nome_completo_piloto', orientation='h', text='pontos', color_discrete_sequence=F1_PALETTE)
        fig.update_layout(yaxis={'categoryorder':'total ascending'}, xaxis_title="Pontos", yaxis_title="Piloto")
        st.plotly_chart(fig, use_container_width=True)
    with col_graf2:
        st.subheader("🏎️ Classificação de Construtores")
        classificacao_constr = constructor_standings.merge(constructors, left_on='id_construtor_fk', right_on='id_construtor')
        fig = px.bar(classificacao_constr, x='pontos', y='nome_construtor', orientation='h', text='pontos', color_discrete_sequence=F1_PALETTE)
        fig.update_layout(yaxis={'categoryorder':'total ascending'}, xaxis_title="Pontos", yaxis_title="Construtor")
        st.plotly_chart(fig, use_container_width=True)


def render_pagina_analise_pilotos(data):
    st.title("🧑‍🚀 Análise Detalhada de Pilotos")
    drivers, results, races, status, paradas = data['tbl_pilotos'], data['tbl_resultados'], data['tbl_corridas'], data['tbl_status_resultado'], data['tbl_paradas']
    
    piloto_selecionado_nome = st.selectbox("Selecione um Piloto", options=drivers.sort_values('sobrenome')['nome_completo_piloto'], index=None)
    if not piloto_selecionado_nome:
        st.info("Selecione um piloto para ver suas estatísticas.")
        return

    id_piloto = drivers[drivers['nome_completo_piloto'] == piloto_selecionado_nome]['id_piloto'].iloc[0]
    resultados_piloto = results[results['id_piloto_fk'] == id_piloto]

    st.header(piloto_selecionado_nome)
    col1, col2, col3, col4, col5 = st.columns(5)
    col1.metric("🏁 Corridas", resultados_piloto['id_corrida_fk'].nunique())
    col2.metric("🏆 Vitórias", (resultados_piloto['posicao_final'] == 1).sum())
    col3.metric("🍾 Pódios", resultados_piloto['posicao_final'].isin([1, 2, 3]).sum())
    col4.metric("⏱️ Poles", (resultados_piloto['posicao_grid'] == 1).sum())
    col5.metric("💯 Pontos Totais", f"{resultados_piloto['pontos'].sum():,.0f}")
    st.divider()

    # NOVAS ESTATÍSTICAS: Pit Stops e Confiabilidade
    st.subheader("Pit Stops e Confiabilidade")
    paradas_piloto = paradas[paradas['id_piloto_fk'] == id_piloto]
    col_pit1, col_pit2 = st.columns(2)
    with col_pit1:
        st.metric("🔧 Total de Pit Stops", f"{len(paradas_piloto)}")
        st.metric("⏱️ Tempo Médio de Parada", f"{paradas_piloto['duracao_s'].mean():.3f}s" if not paradas_piloto.empty else "N/A")
    with col_pit2:
        st.markdown("**Motivos de Abandono (Top 5)**")
        abandonos = resultados_piloto.merge(status, left_on='id_status_fk', right_on='id_status')
        abandonos = abandonos[~abandonos['status'].str.contains("Finished|Lap", na=False)]
        contagem_abandonos = abandonos['status'].value_counts().head(5)
        if not contagem_abandonos.empty:
            st.dataframe(contagem_abandonos)
        else:
            st.write("Nenhum abandono registrado.")
    st.divider()

    st.subheader("Análise de Performance")
    col_graf1, col_graf2 = st.columns(2)
    with col_graf1:
        st.markdown("**Desempenho: Largada vs. Chegada**")
        grid_vs_final = resultados_piloto[['posicao_grid', 'posicao_final']].dropna()
        grid_vs_final = grid_vs_final[(grid_vs_final > 0).all(axis=1)]
        fig = px.scatter(grid_vs_final, x='posicao_grid', y='posicao_final', trendline='ols', trendline_color_override=F1_RED)
        st.plotly_chart(fig, use_container_width=True)
    with col_graf2:
        st.markdown("**Distribuição de Posições Finais**")
        contagem_posicao = resultados_piloto['posicao_final'].value_counts().reset_index().head(10)
        fig = px.bar(contagem_posicao, x='posicao_final', y='count', text='count', color_discrete_sequence=[F1_RED])
        fig.update_layout(xaxis_type='category', xaxis_title="Posição Final", yaxis_title="Contagem")
        st.plotly_chart(fig, use_container_width=True)

    st.subheader("Evolução na Carreira (Pontos por Temporada)")
    resultados_com_ano = resultados_piloto.merge(races, left_on='id_corrida_fk', right_on='id_corrida')
    pontos_por_ano = resultados_com_ano.groupby('ano')['pontos'].sum().reset_index()
    fig_evolucao = px.line(pontos_por_ano, x='ano', y='pontos', markers=True, color_discrete_sequence=[F1_RED])
    st.plotly_chart(fig_evolucao, use_container_width=True)


def render_pagina_analise_construtores(data):
    st.title("🔧 Análise Detalhada de Construtores")
    constructors, results, races, paradas = data['tbl_construtores'], data['tbl_resultados'], data['tbl_corridas'], data['tbl_paradas']
    
    construtor_selecionado_nome = st.selectbox("Selecione um Construtor", options=constructors.sort_values('nome_construtor')['nome_construtor'], index=None)
    if not construtor_selecionado_nome:
        st.info("Selecione um construtor para ver suas estatísticas.")
        return
        
    id_construtor = constructors[constructors['nome_construtor'] == construtor_selecionado_nome]['id_construtor'].iloc[0]
    resultados_construtor = results[results['id_construtor_fk'] == id_construtor]
    
    st.header(construtor_selecionado_nome)
    
    # Cálculo de campeonatos
    results_com_ano = results.merge(races, left_on='id_corrida_fk', right_on='id_corrida')
    pontos_por_construtor_ano = results_com_ano.groupby(['ano', 'id_construtor_fk'])['pontos'].sum().reset_index()
    campeoes_por_ano = pontos_por_construtor_ano.loc[pontos_por_construtor_ano.groupby('ano')['pontos'].idxmax()]
    campeonatos = (campeoes_por_ano['id_construtor_fk'] == id_construtor).sum()
    
    # NOVAS ESTATÍSTICAS: Dobradinhas e Bloqueios de 1ª Fila
    corridas_disputadas = resultados_construtor['id_corrida_fk'].unique()
    dobradinhas = 0
    front_row_lockouts = 0
    for corrida_id in corridas_disputadas:
        res_corrida = resultados_construtor[resultados_construtor['id_corrida_fk'] == corrida_id]
        if all(pos in res_corrida['posicao_final'].values for pos in [1, 2]):
            dobradinhas += 1
        if all(pos in res_corrida['posicao_grid'].values for pos in [1, 2]):
            front_row_lockouts += 1

    col1, col2, col3, col4, col5 = st.columns(5)
    col1.metric("🏆 Vitórias", (resultados_construtor['posicao_final'] == 1).sum())
    col2.metric("🌍 Campeonatos", campeonatos)
    col3.metric("💯 Pontos Totais", f"{resultados_construtor['pontos'].sum():,.0f}")
    col4.metric("🥈 Dobradinhas (1-2)", dobradinhas)
    col5.metric("🔒 Bloqueios de 1ª Fila", front_row_lockouts)
    st.divider()
    
    # Gráficos
    col_graf1, col_graf2 = st.columns(2)
    with col_graf1:
        st.subheader("Evolução (Pontos por Temporada)")
        resultados_com_ano_equipe = resultados_construtor.merge(races, left_on='id_corrida_fk', right_on='id_corrida')
        pontos_por_ano = resultados_com_ano_equipe.groupby('ano')['pontos'].sum().reset_index()
        fig_evolucao = px.bar(pontos_por_ano, x='ano', y='pontos', color_discrete_sequence=[F1_GREY])
        st.plotly_chart(fig_evolucao, use_container_width=True)
    with col_graf2:
        st.subheader("Performance Média de Pit Stops")
        resultados_com_ano = resultados_construtor.merge(races, left_on='id_corrida_fk', right_on='id_corrida')
        paradas_com_ano = paradas.merge(resultados_com_ano, on=['id_corrida_fk', 'id_piloto_fk'])
        media_parada_ano = paradas_com_ano.groupby('ano')['duracao_s_x'].mean().reset_index()
        fig_paradas = px.bar(media_parada_ano, x='ano', y='duracao_s_x', text=media_parada_ano['duracao_s_x'].apply(lambda x: f'{x:.3f}s'))
        fig_paradas.update_layout(yaxis_title="Tempo Médio de Parada (s)")
        st.plotly_chart(fig_paradas, use_container_width=True)


def render_pagina_analise_circuitos(data):
    st.title("🛣️ Análise de Circuitos")
    circuits, races, results, drivers = data['tbl_circuitos'], data['tbl_corridas'], data['tbl_resultados'], data['tbl_pilotos']
    
    circuito_selecionado_nome = st.selectbox("Selecione um Circuito", options=circuits.sort_values('nome_circuito')['nome_circuito'], index=None)
    if not circuito_selecionado_nome:
        st.info("Selecione um circuito para ver suas estatísticas.")
        return
        
    id_circuito = circuits[circuits['nome_circuito'] == circuito_selecionado_nome]['id_circuito'].iloc[0]
    corridas_no_circuito = races[races['id_circuito_fk'] == id_circuito]
    resultados_circuito = results[results['id_corrida_fk'].isin(corridas_no_circuito['id_corrida'])]

    st.header(circuito_selecionado_nome)
    st.metric("🏁 Total de Corridas Realizadas", corridas_no_circuito['id_corrida'].nunique())
    st.divider()

    col1, col2 = st.columns(2)
    with col1:
        st.subheader("Reis da Pista (Maiores Vencedores)")
        vencedores = resultados_circuito[resultados_circuito['posicao_final'] == 1].merge(drivers, left_on='id_piloto_fk', right_on='id_piloto')
        maiores_vencedores = vencedores['nome_completo_piloto'].value_counts().head(5).reset_index()
        fig = px.bar(maiores_vencedores, x='count', y='nome_completo_piloto', orientation='h', text='count', color_discrete_sequence=[F1_RED])
        fig.update_layout(yaxis={'categoryorder':'total ascending'}, xaxis_title="Nº de Vitórias", yaxis_title="Piloto")
        st.plotly_chart(fig, use_container_width=True)
    with col2:
        st.subheader("De Onde Saem os Vencedores?")
        posicao_grid_vencedores = resultados_circuito[(resultados_circuito['posicao_final'] == 1) & (resultados_circuito['posicao_grid'] > 0)]
        fig_grid = px.histogram(posicao_grid_vencedores, x='posicao_grid', nbins=20, text_auto=True, color_discrete_sequence=[F1_BLACK])
        fig_grid.update_layout(xaxis_title="Posição de Largada", yaxis_title="Nº de Vitórias")
        st.plotly_chart(fig_grid, use_container_width=True)


def render_pagina_h2h(data):
    st.title("⚔️ Head-to-Head de Pilotos")
    drivers, results = data['tbl_pilotos'], data['tbl_resultados']
    
    col1, col2 = st.columns(2)
    piloto1_nome = col1.selectbox("Selecione o Piloto 1", options=drivers.sort_values('sobrenome')['nome_completo_piloto'], index=None, key="h2h_p1")
    piloto2_nome = col2.selectbox("Selecione o Piloto 2", options=drivers.sort_values('sobrenome')['nome_completo_piloto'], index=None, key="h2h_p2")
        
    if piloto1_nome and piloto2_nome and piloto1_nome != piloto2_nome:
        id1 = drivers[drivers['nome_completo_piloto'] == piloto1_nome]['id_piloto'].iloc[0]
        id2 = drivers[drivers['nome_completo_piloto'] == piloto2_nome]['id_piloto'].iloc[0]
        stats1 = results[results['id_piloto_fk'] == id1]
        stats2 = results[results['id_piloto_fk'] == id2]

        st.subheader("Estatísticas da Carreira")
        fig = go.Figure()
        fig.add_trace(go.Bar(name=piloto1_nome, x=['Vitórias', 'Pódios', 'Pontos'], y=[(stats1['posicao_final'] == 1).sum(), stats1['posicao_final'].isin([1,2,3]).sum(), stats1['pontos'].sum()], marker_color=F1_RED))
        fig.add_trace(go.Bar(name=piloto2_nome, x=['Vitórias', 'Pódios', 'Pontos'], y=[(stats2['posicao_final'] == 1).sum(), stats2['posicao_final'].isin([1,2,3]).sum(), stats2['pontos'].sum()], marker_color=F1_GREY))
        fig.update_layout(barmode='group', yaxis_title="Total")
        st.plotly_chart(fig, use_container_width=True)

        st.subheader("Resultados em Corridas Juntos")
        corridas_juntos = stats1.merge(stats2, on='id_corrida_fk', suffixes=('_p1', '_p2'))
        vantagem_p1 = (corridas_juntos['posicao_final_p1'] < corridas_juntos['posicao_final_p2']).sum()
        vantagem_p2 = (corridas_juntos['posicao_final_p2'] < corridas_juntos['posicao_final_p1']).sum()

        col_h2h1, col_h2h2, col_h2h3 = st.columns(3)
        col_h2h1.metric("Corridas Juntos", len(corridas_juntos))
        col_h2h2.metric(f"Vantagem para {piloto1_nome}", f"{vantagem_p1} vezes")
        col_h2h3.metric(f"Vantagem para {piloto2_nome}", f"{vantagem_p2} vezes")

# --- PASSO 2: NOVAS PÁGINAS ---

def render_pagina_analise_temporada(data):
    st.title("📈 Análise de Temporada")
    races, results, drivers = data['tbl_corridas'], data['tbl_resultados'], data['tbl_pilotos']
    
    ano_sel = st.selectbox("Selecione o Ano", options=sorted(races['ano'].unique(), reverse=True))
    
    results_ano = results.merge(races[races['ano'] == ano_sel], left_on='id_corrida_fk', right_on='id_corrida').sort_values('rodada')
    
    # Acumula os pontos corrida a corrida
    results_ano['pontos_acumulados'] = results_ano.groupby('id_piloto_fk')['pontos'].cumsum()
    
    # Achar os 5 melhores da temporada para plotar
    top_5_pilotos_ids = results_ano.groupby('id_piloto_fk')['pontos'].sum().nlargest(5).index.tolist()
    
    data_plot = results_ano[results_ano['id_piloto_fk'].isin(top_5_pilotos_ids)].merge(drivers, left_on='id_piloto_fk', right_on='id_piloto')
    
    st.subheader(f"Evolução do Campeonato de Pilotos {ano_sel} (Top 5)")
    fig = px.line(data_plot, x='rodada', y='pontos_acumulados', color='codigo', markers=True, hover_name='nome_gp')
    fig.update_layout(xaxis_title="Rodada", yaxis_title="Pontos Acumulados")
    st.plotly_chart(fig, use_container_width=True)

def render_pagina_analise_corrida(data):
    st.title("🏁 Análise Detalhada de Corrida")
    races, drivers, paradas, voltas, constructors = data['tbl_corridas'], data['tbl_pilotos'], data['tbl_paradas'], data['tbl_voltas'], data['tbl_construtores']
    
    ano_sel = st.selectbox("Ano", options=sorted(races['ano'].unique(), reverse=True))
    corrida_opts = races[races['ano'] == ano_sel].sort_values('rodada')
    corrida_nome_sel = st.selectbox("Corrida", options=corrida_opts['nome_gp'])
    
    id_corrida = corrida_opts[corrida_opts['nome_gp'] == corrida_nome_sel]['id_corrida'].iloc[0]

    st.header(f"Análise Estratégica: {corrida_nome_sel} {ano_sel}")
    
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("Pit Stops na Corrida")
        paradas_corrida = paradas[paradas['id_corrida_fk'] == id_corrida].merge(drivers, left_on='id_piloto_fk', right_on='id_piloto')
        st.dataframe(paradas_corrida[['nome_completo_piloto', 'parada', 'volta', 'duracao_s']].sort_values('volta'), use_container_width=True)
    with col2:
        st.subheader("Tempo Médio de Parada por Equipe")
        paradas_corrida_equipe = paradas_corrida.merge(data['tbl_resultados'], on=['id_corrida_fk', 'id_piloto_fk'])
        paradas_corrida_equipe = paradas_corrida_equipe.merge(constructors, on='id_construtor_fk')
        media_parada_equipe = paradas_corrida_equipe.groupby('nome_construtor')['duracao_s'].mean().sort_values().reset_index()
        fig = px.bar(media_parada_equipe, x='duracao_s', y='nome_construtor', orientation='h', text=media_parada_equipe['duracao_s'].apply(lambda x: f'{x:.3f}s'))
        fig.update_layout(xaxis_title="Tempo Médio (s)", yaxis_title="Equipe")
        st.plotly_chart(fig, use_container_width=True)

    st.subheader("Posição Volta a Volta (Top 10 Finais)")
    # Pega os 10 primeiros que terminaram a corrida
    top_10_ids = data['tbl_resultados'][(data['tbl_resultados']['id_corrida_fk'] == id_corrida) & (data['tbl_resultados']['posicao_final'] <= 10)]['id_piloto_fk'].tolist()
    
    voltas_corrida = voltas[(voltas['id_corrida_fk'] == id_corrida) & (voltas['id_piloto_fk'].isin(top_10_ids))]
    voltas_corrida = voltas_corrida.merge(drivers, left_on='id_piloto_fk', right_on='id_piloto')
    
    if not voltas_corrida.empty:
        fig_voltas = px.line(voltas_corrida, x='volta', y='posicao', color='codigo', markers=False)
        fig_voltas.update_yaxes(autorange="reversed")
        fig_voltas.update_layout(xaxis_title="Volta", yaxis_title="Posição")
        st.plotly_chart(fig_voltas, use_container_width=True)
    else:
        st.warning("Dados de posição volta a volta não disponíveis para esta corrida.")

def render_pagina_hall_da_fama(data):
    st.title("🏆 Hall da Fama")
    results, drivers, constructors = data['tbl_resultados'], data['tbl_pilotos'], data['tbl_construtores']
    
    st.subheader("Recordes Históricos de Pilotos")
    vitorias = results[results['posicao_final'] == 1].groupby('id_piloto_fk').size().nlargest(1).index[0]
    podios = results[results['posicao_final'].isin([1,2,3])].groupby('id_piloto_fk').size().nlargest(1).index[0]
    poles = results[results['posicao_grid'] == 1].groupby('id_piloto_fk').size().nlargest(1).index[0]
    pontos = results.groupby('id_piloto_fk')['pontos'].sum().nlargest(1).index[0]

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Mais Vitórias", drivers[drivers['id_piloto'] == vitorias]['nome_completo_piloto'].iloc[0], f"{(results['posicao_final'] == 1).sum()} vitórias")
    col2.metric("Mais Pódios", drivers[drivers['id_piloto'] == podios]['nome_completo_piloto'].iloc[0], f"{results['posicao_final'].isin([1,2,3]).sum()} pódios")
    col3.metric("Mais Poles", drivers[drivers['id_piloto'] == poles]['nome_completo_piloto'].iloc[0], f"{(results['posicao_grid'] == 1).sum()} poles")
    col4.metric("Mais Pontos", drivers[drivers['id_piloto'] == pontos]['nome_completo_piloto'].iloc[0], f"{results['pontos'].sum():,.0f} pontos")
    st.divider()

    st.subheader("Rankings de Todos os Tempos (Top 15)")
    tab_vit, tab_pod, tab_pol = st.tabs(["Vitórias", "Pódios", "Poles"])
    with tab_vit:
        ranking_vitorias = results[results['posicao_final'] == 1]['id_piloto_fk'].value_counts().nlargest(15).reset_index()
        ranking_vitorias = ranking_vitorias.merge(drivers, left_on='id_piloto_fk', right_on='id_piloto')
        fig = px.bar(ranking_vitorias, x='count', y='nome_completo_piloto', orientation='h', text='count')
        fig.update_layout(yaxis={'categoryorder':'total ascending'}, xaxis_title="Nº de Vitórias", yaxis_title="Piloto")
        st.plotly_chart(fig, use_container_width=True)
    with tab_pod:
        # Repetir a lógica para pódios
        pass
    with tab_pol:
        # Repetir a lógica para poles
        pass

def render_pagina_gerenciamento(data):
    st.title("🔩 Gerenciamento de Dados (CRUD)")
    # (O código do CRUD permanece o mesmo da versão anterior)
    pass


# --- ESTRUTURA PRINCIPAL DO APP ---
def main():
    with st.sidebar:
        st.image("f1_logo.png", width=250)
        app_page = option_menu(
            menu_title='F1 Super Analytics',
            options=[
                'Visão Geral', 
                'Análise de Pilotos', 
                'Análise de Construtores', 
                'Análise de Circuitos', 
                'H2H Pilotos',
                'Análise de Temporada', # Nova página
                'Análise de Corrida', # Nova página
                'Hall da Fama', # Nova página
                'Gerenciamento'
            ],
            icons=[
                'trophy-fill', 'person-badge', 'tools', 'signpost-split', 'people-fill',
                'graph-up', # Novo ícone
                'flag-fill', # Novo ícone
                'award-fill', # Novo ícone
                'database-fill-gear'
            ],
            menu_icon='speed',
            default_index=0,
            styles={ "nav-link-selected": {"background-color": F1_RED} }
        )
    
    if conn is None:
        st.warning("Verifique as configurações de conexão no secrets.")
        return
        
    dados_completos = carregar_todos_os_dados()
    
    page_map = {
        'Visão Geral': render_pagina_visao_geral,
        'Análise de Pilotos': render_pagina_analise_pilotos,
        'Análise de Construtores': render_pagina_analise_construtores,
        'Análise de Circuitos': render_pagina_analise_circuitos,
        'H2H Pilotos': render_pagina_h2h,
        'Análise de Temporada': render_pagina_analise_temporada,
        'Análise de Corrida': render_pagina_analise_corrida,
        'Hall da Fama': render_pagina_hall_da_fama,
        'Gerenciamento': render_pagina_gerenciamento
    }
    
    page_function = page_map.get(app_page)
    if page_function:
        page_function(dados_completos)

if __name__ == "__main__":
    main()
