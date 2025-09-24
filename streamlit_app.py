import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from streamlit_option_menu import option_menu
import psycopg2 

st.set_page_config(layout="wide", page_title="F1 Super Analytics", page_icon="f1.png")

F1_PALETTE = ["#E10600", "#15151E", "#7F7F7F", "#B1B1B8", "#FF8700", "#00A000", "#FFFFFF"]
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

def executar_comando_sql(conn, comando, params=None):
    if not conn: return False
    try:
        with conn.cursor() as cur:
            cur.execute(comando, params)
            conn.commit()
        # Limpa o cache de dados após uma escrita no banco para refletir as mudanças
        st.cache_data.clear()
        return True
    except Exception as e:
        conn.rollback()
        st.error(f"Erro ao executar comando SQL: {e}")
        return False
        
@st.cache_data(ttl=60)
def carregar_todos_os_dados(_conn):
    st.info("Carregando dados do banco de dados...")
    queries = {
        'races': 'SELECT * FROM races', 'results': 'SELECT * FROM results',
        'drivers': 'SELECT * FROM drivers', 'constructors': 'SELECT * FROM constructors',
        'circuits': 'SELECT * FROM circuits', 'status': 'SELECT * FROM status',
        'driver_standings': 'SELECT * FROM driver_standings',
        'constructor_standings': 'SELECT * FROM constructor_standings',
        'qualifying': 'SELECT * FROM qualifying', 'lap_times': 'SELECT * FROM lap_times',
        'pit_stops': 'SELECT * FROM pit_stops'
    }
    data = {}
    try:
        for name, query in queries.items():
            data[name] = pd.read_sql_query(query, _conn)
        for df_name in data:
            data[df_name].replace('\\N', pd.NA, inplace=True)
        
        # Limpeza e Transformação
        data['drivers']['driver_name'] = data['drivers']['forename'] + ' ' + data['drivers']['surname']
        numeric_cols = {'results': ['points', 'position', 'grid', 'rank'], 'pit_stops': ['milliseconds']}
        for df_name, cols in numeric_cols.items():
            for col in cols:
                data[df_name][col] = pd.to_numeric(data[df_name][col])
        data['pit_stops']['duration'] = data['pit_stops']['milliseconds'] / 1000
        st.success("Dados carregados com sucesso!")
        return data
    except Exception as e:
        st.error(f"Erro ao consultar dados: {e}. Verifique se os nomes das colunas no código (minúsculas) correspondem aos do banco.")
        return None

def render_visao_geral(data):
    st.title("🏁 Visão Geral da Temporada")
    ano_selecionado = st.selectbox("Selecione a Temporada", options=sorted(data['races']['year'].unique(), reverse=True))
    
    races_ano = data['races'][data['races']['year'] == ano_selecionado]
    race_ids_ano = races_ano['raceid']
    id_ultima_corrida = data['driver_standings'][data['driver_standings']['raceid'].isin(race_ids_ano)].sort_values('raceid', ascending=False).iloc[0]['raceid']
    
    standings_final = data['driver_standings'][data['driver_standings']['raceid'] == id_ultima_corrida]
    campeao_id = standings_final[standings_final['position'] == 1]['driverid'].iloc[0]
    campeao_nome = data['drivers'][data['drivers']['driverid'] == campeao_id]['driver_name'].iloc[0]

    constr_standings_final = data['constructor_standings'][data['constructor_standings']['raceid'] == id_ultima_corrida]
    campeao_constr_id = constr_standings_final[constr_standings_final['position'] == 1]['constructorid'].iloc[0]
    campeao_constr_nome = data['constructors'][data['constructors']['constructorid'] == campeao_constr_id]['name'].iloc[0]

    results_ano = data['results'][data['results']['raceid'].isin(race_ids_ano)]
    vitorias_piloto = results_ano[results_ano['position'] == 1]['driverid'].value_counts().nlargest(1)
    poles_piloto = data['qualifying'][(data['qualifying']['raceid'].isin(race_ids_ano)) & (data['qualifying']['position'] == 1)]['driverid'].value_counts().nlargest(1)

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("🏆 Campeão de Pilotos", campeao_nome)
    col2.metric("🏎️ Campeão de Construtores", campeao_constr_nome)
    if not vitorias_piloto.empty:
        piloto_vitorias_nome = data['drivers'][data['drivers']['driverid'] == vitorias_piloto.index[0]]['driver_name'].iloc[0]
        col3.metric("🥇 Mais Vitórias", f"{piloto_vitorias_nome} ({vitorias_piloto.values[0]})")
    if not poles_piloto.empty:
        piloto_poles_nome = data['drivers'][data['drivers']['driverid'] == poles_piloto.index[0]]['driver_name'].iloc[0]
        col4.metric("⏱️ Mais Poles", f"{piloto_poles_nome} ({poles_piloto.values[0]})")
    
    st.divider()
    col_graf1, col_graf2 = st.columns(2)
    with col_graf1:
        st.subheader("Classificação Final de Pilotos (Top 10)")
        top_10_drivers = standings_final.head(10).merge(data['drivers'], on='driverid')
        fig = px.bar(top_10_drivers, x='points', y='driver_name', orientation='h', text='points', color_discrete_sequence=[F1_RED])
        fig.update_layout(yaxis={'categoryorder':'total ascending'}, yaxis_title="")
        st.plotly_chart(fig, use_container_width=True)
    with col_graf2:
        st.subheader("Classificação Final de Construtores")
        top_constructors = constr_standings_final.merge(data['constructors'], on='constructorid')
        fig = px.bar(top_constructors, x='points', y='name', orientation='h', text='points', color_discrete_sequence=[F1_GREY])
        fig.update_layout(yaxis={'categoryorder':'total ascending'}, yaxis_title="")
        st.plotly_chart(fig, use_container_width=True)

def render_analise_pilotos(data):
    st.title("🧑‍🚀 Análise de Pilotos")
    piloto_nome = st.selectbox("Selecione um Piloto", options=data['drivers'].sort_values('surname')['driver_name'], index=None)
    
    if piloto_nome:
        piloto_info = data['drivers'][data['drivers']['driver_name'] == piloto_nome].iloc[0]
        id_piloto = piloto_info['driverid']
        
        res_piloto = data['results'][data['results']['driverid'] == id_piloto]
        quali_piloto = data['qualifying'][data['qualifying']['driverid'] == id_piloto]

        pontos_por_equipe = res_piloto.groupby('constructorid')['points'].sum().nlargest(1)
        equipe_vitoriosa = "N/A"
        if not pontos_por_equipe.empty:
            id_equipe = pontos_por_equipe.index[0]
            equipe_vitoriosa = data['constructors'][data['constructors']['constructorid'] == id_equipe]['name'].iloc[0]
            
        races_piloto = data['races'][data['races']['raceId'].isin(res_piloto['raceId'])]
        standings_piloto = data['driver_standings'][data['driver_standings']['driverId'] == id_piloto]
        
        campeonatos = 0
        for year in races_piloto['year'].unique():
            races_ano = data['races'][data['races']['year'] == year]
            ultima_corrida_ano = races_ano['raceId'].max()
            pos_final = standings_piloto[(standings_piloto['raceId'] == ultima_corrida_ano) & (standings_piloto['position'] == 1)]
            if not pos_final.empty:
                campeonatos += 1

        st.header(piloto_nome)

        col1, col2, col3 = st.columns(3)
        col1.metric("🌍 Nacionalidade", piloto_info['nationality'])
        col2.metric("🎂 Data de Nascimento", str(piloto_info['dob']))
        col3.metric("🤝 Equipe Mais Vitoriosa", equipe_vitoriosa)
        
        c1, c2, c3, c4, c5, c6 = st.columns(6)
        c1.metric("🏆 Campeonatos", campeonatos)
        c2.metric("🏁 Corridas", res_piloto['raceId'].nunique())
        c3.metric("🥇 Vitórias", (res_piloto['position'] == 1).sum())
        c4.metric("🍾 Pódios", res_piloto['position'].isin([1, 2, 3]).sum())
        c5.metric("⏱️ Poles", (quali_piloto['position'] == 1).sum())
        c6.metric("🚀 Voltas R.", (res_piloto['rank'] == 1).sum())
        st.divider()

        st.subheader("Pontos por Equipe na Carreira")
        pontos_equipe_df = res_piloto.groupby('constructorid')['points'].sum().reset_index().merge(data['constructors'], on='constructorid')
        fig_pontos_equipe = px.bar(pontos_equipe_df, x='points', y='name', orientation='h', text='points', color_discrete_sequence=F1_PALETTE)
        fig_pontos_equipe.update_layout(yaxis={'categoryorder':'total ascending'}, yaxis_title="Equipe", xaxis_title="Pontos Acumulados")
        st.plotly_chart(fig_pontos_equipe, use_container_width=True)

        st.subheader("Performance ao Longo do Tempo")
        res_com_ano = res_piloto.merge(data['races'], on='raceId')
        pontos_ano = res_com_ano.groupby('year')['points'].sum().reset_index()
        fig_pontos = px.line(pontos_ano, x='year', y='points', title="Pontos por Temporada", markers=True)
        st.plotly_chart(fig_pontos, use_container_width=True)

        st.subheader("Análise de Performance e Confiabilidade")
        g1, g2 = st.columns(2)
        with g1:
            st.markdown("**Grid vs. Posição Final**")
            grid_final = res_piloto[['grid', 'position']].dropna()
            fig_grid = px.scatter(grid_final, x='grid', y='position', trendline='ols', trendline_color_override=F1_RED, labels={'grid': 'Posição de Largada', 'position': 'Posição Final'})
            st.plotly_chart(fig_grid, use_container_width=True)
        with g2:
            st.markdown("**Motivos de Abandono**")
            abandonos = res_piloto[res_piloto['position'].isna()].merge(data['status'], on='statusId')
            contagem_abandonos = abandonos['status'].value_counts().head(10)
            fig_status = px.bar(contagem_abandonos, y=contagem_abandonos.index, x=contagem_abandonos.values, orientation='h')
            fig_status.update_layout(xaxis_title="Contagem", yaxis_title="Motivo", yaxis={'categoryorder':'total ascending'})
            st.plotly_chart(fig_status, use_container_width=True)

def render_analise_construtores(data):
    st.title("🔧 Análise de Construtores")
    construtor_nome = st.selectbox("Selecione um Construtor", options=data['constructors'].sort_values('name')['name'], index=None)
    if construtor_nome:
        construtor_info = data['constructors'][data['constructors']['name'] == construtor_nome].iloc[0]
        id_construtor = construtor_info['constructorid']
        
        res_construtor = data['results'][data['results']['constructorid'] == id_construtor]
        quali_construtor = data['qualifying'][data['qualifying']['constructorId'] == id_construtor]
        
        st.header(construtor_nome)
        st.metric("🌍 Nacionalidade", construtor_info['nationality'])
        # Lógica para calcular campeonatos
        standings_construtor = data['constructor_standings'][data['constructor_standings']['constructorId'] == id_construtor]
        campeonatos = 0
        if not standings_construtor.empty:
            anos_disputados = data['races'][data['races']['raceId'].isin(standings_construtor['raceId'])]['year'].unique()
            for year in anos_disputados:
                races_ano = data['races'][data['races']['year'] == year]
                ultima_corrida_ano = races_ano['raceId'].max()
                pos_final = data['constructor_standings'][(data['constructor_standings']['raceId'] == ultima_corrida_ano) & (data['constructor_standings']['position'] == 1)]
                if not pos_final.empty and pos_final['constructorId'].iloc[0] == id_construtor:
                    campeonatos += 1

        # Lógica para dobradinhas (1-2)
        dobradinhas = 0
        corridas_com_multiplos_carros = res_construtor['raceId'].value_counts()
        corridas_validas = corridas_com_multiplos_carros[corridas_com_multiplos_carros >= 2].index
        for race_id in corridas_validas:
            res_corrida = res_construtor[res_construtor['raceId'] == race_id]
            if {1, 2}.issubset(set(res_corrida['position'])):
                dobradinhas += 1

        c1, c2, c3, c4, c5, c6 = st.columns(6)
        c1.metric("🏆 Campeonatos", campeonatos)
        c2.metric("🏁 Corridas", res_construtor['raceId'].nunique())
        c3.metric("🥇 Vitórias", (res_construtor['position'] == 1).sum())
        c4.metric("🍾 Pódios Totais", res_construtor['position'].isin([1, 2, 3]).sum())
        c5.metric("⏱️ Poles Totais", (quali_construtor['position'] == 1).sum())
        c6.metric("🥈 Dobradinhas (1-2)", dobradinhas)
        st.divider()

        st.subheader("Comparativo de Pilotos por Temporada")
        res_com_ano = res_construtor.merge(data['races'], on='raceid').merge(data['drivers'], on='driverid')
        pontos_piloto_ano = res_com_ano.groupby(['year', 'driver_name'])['points'].sum().reset_index()
        fig_pilotos = px.bar(pontos_piloto_ano, x='year', y='points', color='driver_name', title="Pontos por Piloto a Cada Temporada", color_discrete_sequence=px.colors.qualitative.Plotly)
        st.plotly_chart(fig_pilotos, use_container_width=True)

        st.subheader("Performance ao Longo do Tempo")
        res_com_ano = res_construtor.merge(data['races'], on='raceId')
        pontos_ano = res_com_ano.groupby('year')['points'].sum().reset_index()
        fig_pontos = px.bar(pontos_ano, x='year', y='points', title="Pontos por Temporada", color_discrete_sequence=[F1_GREY])
        st.plotly_chart(fig_pontos, use_container_width=True)

        st.subheader("Análise de Confiabilidade")
        res_com_status = res_construtor.merge(data['status'], on='statusId')
        res_com_status['outcome'] = res_com_status['status'].apply(lambda x: 'Finalizou' if x == 'Finished' or '+ ' in x else 'Não Finalizou')
        outcome_counts = res_com_status['outcome'].value_counts()
        fig_conf = px.pie(values=outcome_counts.values, names=outcome_counts.index, title="Taxa de Finalização de Corridas",
                          color=outcome_counts.index, color_discrete_map={'Finalizou':'green', 'Não Finalizou':F1_RED})
        st.plotly_chart(fig_conf, use_container_width=True)

def render_analise_temporada(data):
    st.title("📈 Análise de Temporada")
    ano = st.selectbox("Selecione a Temporada", options=sorted(data['races']['year'].unique(), reverse=True))

    races_ano = data['races'][data['races']['year'] == ano]
    standings_ano = data['driver_standings'][data['driver_standings']['raceId'].isin(races_ano['raceId'])]
    
    # Pegar os top 5 pilotos do fim da temporada
    id_ultima_corrida = races_ano['raceId'].max()
    top_5_ids = standings_ano[standings_ano['raceId'] == id_ultima_corrida].sort_values('position').head(5)['driverId']
    
    standings_top_5 = standings_ano[standings_ano['driverId'].isin(top_5_ids)]
    standings_top_5 = standings_top_5.merge(data['drivers'], on='driverId').merge(races_ano, on='raceId')
    
    st.subheader(f"Batalha pelo Campeonato de Pilotos em {ano}")
    fig = px.line(standings_top_5, x='round', y='points', color='code', markers=True, title="Evolução dos Pontos (Top 5)")
    st.plotly_chart(fig, use_container_width=True)

def render_analise_corrida(data):
    st.title("🏁 Análise de Corrida")
    
    ano = st.selectbox("Ano", options=sorted(data['races']['year'].unique(), reverse=True))
    corrida_opts = data['races'][data['races']['year'] == ano].sort_values('round')
    corrida_nome = st.selectbox("Corrida", options=corrida_opts['name'])
    
    id_corrida = corrida_opts[corrida_opts['name'] == corrida_nome]['raceId'].iloc[0]
    
    st.header(f"Análise de {corrida_nome} {ano}")
    
    st.subheader("Posição Volta a Volta (Top 5)")
    top_5_final = data['results'][(data['results']['raceId'] == id_corrida) & (data['results']['position'] <= 5)]['driverId']
    lap_times_top_5 = data['lap_times'][(data['lap_times']['raceId'] == id_corrida) & (data['lap_times']['driverId'].isin(top_5_final))]
    lap_times_top_5 = lap_times_top_5.merge(data['drivers'], on='driverId')
    
    if not lap_times_top_5.empty:
        fig = px.line(lap_times_top_5, x='lap', y='position', color='code', markers=False)
        fig.update_yaxes(autorange="reversed")
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.warning("Dados de volta a volta não disponíveis para esta corrida.")

    st.subheader("Estratégias de Pit Stop")
    pit_stops_corrida = data['pit_stops'][data['pit_stops']['raceId'] == id_corrida].merge(data['drivers'], on='driverId')
    fig_pit = px.scatter(pit_stops_corrida, x='lap', y='duration', color='driver_name', size='stop', hover_data=['time'])
    fig_pit.update_layout(xaxis_title="Volta", yaxis_title="Duração do Pit Stop (s)")
    st.plotly_chart(fig_pit, use_container_width=True)

def render_h2h(data):
    st.title("⚔️ Head-to-Head")
    
    col1, col2 = st.columns(2)
    piloto1_nome = col1.selectbox("Selecione o Piloto 1", options=data['drivers'].sort_values('surname')['driver_name'], index=None)
    piloto2_nome = col2.selectbox("Selecione o Piloto 2", options=data['drivers'].sort_values('surname')['driver_name'], index=None)

    if piloto1_nome and piloto2_nome and piloto1_nome != piloto2_nome:
        id1 = data['drivers'][data['drivers']['driver_name'] == piloto1_nome]['driverId'].iloc[0]
        id2 = data['drivers'][data['drivers']['driver_name'] == piloto2_nome]['driverId'].iloc[0]
        
        res1 = data['results'][data['results']['driverId'] == id1]
        res2 = data['results'][data['results']['driverId'] == id2]
        quali1 = data['qualifying'][data['qualifying']['driverId'] == id1]
        quali2 = data['qualifying'][data['qualifying']['driverId'] == id2]

        st.subheader("Comparativo de Carreira")
        fig = go.Figure()
        fig.add_trace(go.Bar(name=piloto1_nome, x=['Vitórias', 'Pódios', 'Poles'], y=[(res1['position'] == 1).sum(), res1['position'].isin([1,2,3]).sum(), (quali1['position'] == 1).sum()], marker_color=F1_RED))
        fig.add_trace(go.Bar(name=piloto2_nome, x=['Vitórias', 'Pódios', 'Poles'], y=[(res2['position'] == 1).sum(), res2['position'].isin([1,2,3]).sum(), (quali2['position'] == 1).sum()], marker_color=F1_GREY))
        fig.update_layout(barmode='group', title_text="Carreira: Vitórias vs Pódios vs Poles")
        st.plotly_chart(fig, use_container_width=True)
        
        st.divider()
        st.subheader("Confrontos Diretos")
        
        # Confrontos em corrida
        res_comum = res1.merge(res2, on='raceId', suffixes=('_p1', '_p2'))
        res_comum.dropna(subset=['position_p1', 'position_p2'], inplace=True)
        vantagem_corrida_p1 = (res_comum['position_p1'] < res_comum['position_p2']).sum()
        vantagem_corrida_p2 = (res_comum['position_p2'] < res_comum['position_p1']).sum()

        # Confrontos em qualificação
        quali_comum = quali1.merge(quali2, on='raceId', suffixes=('_p1', '_p2'))
        vantagem_quali_p1 = (quali_comum['position_p1'] < quali_comum['position_p2']).sum()
        vantagem_quali_p2 = (quali_comum['position_p2'] < quali_comum['position_p1']).sum()

        c1, c2 = st.columns(2)
        with c1:
            st.markdown(f"**Corridas ({len(res_comum)} no total)**")
            st.metric(f"Vantagem para {piloto1_nome}", f"{vantagem_corrida_p1} vezes")
            st.metric(f"Vantagem para {piloto2_nome}", f"{vantagem_corrida_p2} vezes")
        with c2:
            st.markdown(f"**Qualificação ({len(quali_comum)} no total)**")
            st.metric(f"Vantagem para {piloto1_nome}", f"{vantagem_quali_p1} vezes")
            st.metric(f"Vantagem para {piloto2_nome}", f"{vantagem_quali_p2} vezes")

def render_hall_da_fama(data):
    st.title("🏆 Hall da Fama: Recordes Históricos")

    # Agrupar dados para rankings
    vitorias_pilotos = data['results'][data['results']['position'] == 1]['driverId'].value_counts().reset_index()
    vitorias_pilotos.columns = ['driverId', 'count']
    vitorias_pilotos = vitorias_pilotos.merge(data['drivers'], on='driverId')

    podios_pilotos = data['results'][data['results']['position'].isin([1,2,3])]['driverId'].value_counts().reset_index()
    podios_pilotos.columns = ['driverId', 'count']
    podios_pilotos = podios_pilotos.merge(data['drivers'], on='driverId')

    poles_pilotos = data['qualifying'][data['qualifying']['position'] == 1]['driverId'].value_counts().reset_index()
    poles_pilotos.columns = ['driverId', 'count']
    poles_pilotos = poles_pilotos.merge(data['drivers'], on='driverId')

    vitorias_construtores = data['results'][data['results']['position'] == 1]['constructorId'].value_counts().reset_index()
    vitorias_construtores.columns = ['constructorId', 'count']
    vitorias_construtores = vitorias_construtores.merge(data['constructors'], on='constructorId')

    st.subheader("Recordistas de Todos os Tempos")
    c1, c2, c3 = st.columns(3)
    c1.metric("🥇 Mais Vitórias (Piloto)", vitorias_pilotos.iloc[0]['driver_name'], f"{vitorias_pilotos.iloc[0]['count']}")
    c2.metric("🍾 Mais Pódios (Piloto)", podios_pilotos.iloc[0]['driver_name'], f"{podios_pilotos.iloc[0]['count']}")
    c3.metric("⏱️ Mais Poles (Piloto)", poles_pilotos.iloc[0]['driver_name'], f"{poles_pilotos.iloc[0]['count']}")
    st.metric("🏎️ Mais Vitórias (Construtor)", vitorias_construtores.iloc[0]['name'], f"{vitorias_construtores.iloc[0]['count']}")
    st.divider()

    st.subheader("Rankings Históricos (Top 15)")
    tab_vit, tab_pod, tab_pol = st.tabs(["Vitórias", "Pódios", "Pole Positions"])

    with tab_vit:
        fig = px.bar(vitorias_pilotos.head(15), x='count', y='driver_name', orientation='h', text='count', title="Pilotos com Mais Vitórias")
        fig.update_layout(yaxis={'categoryorder':'total ascending'}, yaxis_title="")
        st.plotly_chart(fig, use_container_width=True)
    with tab_pod:
        fig = px.bar(podios_pilotos.head(15), x='count', y='driver_name', orientation='h', text='count', title="Pilotos com Mais Pódios")
        fig.update_layout(yaxis={'categoryorder':'total ascending'}, yaxis_title="")
        st.plotly_chart(fig, use_container_width=True)
    with tab_pol:
        fig = px.bar(poles_pilotos.head(15), x='count', y='driver_name', orientation='h', text='count', title="Pilotos com Mais Pole Positions")
        fig.update_layout(yaxis={'categoryorder':'total ascending'}, yaxis_title="")
        st.plotly_chart(fig, use_container_width=True)

def render_analise_circuitos(data):
    st.title("🛣️ Análise de Circuitos")
    circuito_nome = st.selectbox("Selecione um Circuito", options=data['circuits'].sort_values('name')['name'], index=None)
    if circuito_nome:
        circuito_info = data['circuits'][data['circuits']['name'] == circuito_nome].iloc[0]
        id_circuito = circuito_info['circuitid']
        
        races_circuito = data['races'][data['races']['circuitid'] == id_circuito]
        results_circuito = data['results'][data['results']['raceid'].isin(races_circuito['raceid'])]
        
        st.header(circuito_nome)
        c1, c2, c3 = st.columns(3)
        c1.metric("📍 Localização", circuito_info['location'])
        c2.metric("🌍 País", circuito_info['country'])
        c3.metric("🏁 Corridas Realizadas", races_circuito['raceid'].nunique())
        st.divider()

        # NOVO GRÁFICO
        st.subheader("Recordistas de Pole Position")
        quali_circuito = data['qualifying'][data['qualifying']['raceid'].isin(races_circuito['raceid'])]
        poles_circuito = quali_circuito[quali_circuito['position'] == 1]['driverid'].value_counts().nlargest(5).reset_index()
        poles_circuito = poles_circuito.merge(data['drivers'], on='driverid')
        fig_poles = px.bar(poles_circuito, x='count', y='driver_name', orientation='h', text='count', color_discrete_sequence=[F1_BLACK])
        fig_poles.update_layout(yaxis={'categoryorder':'total ascending'}, yaxis_title="", xaxis_title="Número de Poles")
        st.plotly_chart(fig_poles, use_container_width=True)

def render_pagina_gerenciamento(conn):
    st.title("🔩 Gerenciamento de Dados (CRUD)")
    tab_create, tab_read, tab_update, tab_delete = st.tabs(["➕ Criar", "🔍 Consultar", "🔄 Atualizar", "❌ Deletar"])

    with tab_read:
        st.subheader("Consultar Tabela de Pilotos")
        try:
            pilotos_df = pd.read_sql_query("SELECT driverid, driverref, code, forename, surname, dob, nationality FROM drivers ORDER BY surname", conn)
            st.dataframe(pilotos_df, use_container_width=True)
        except Exception as e:
            st.error(f"Não foi possível consultar os pilotos: {e}")

    with tab_create:
        st.subheader("Adicionar Novo Piloto")
        with st.form("form_create", clear_on_submit=True):
            forename = st.text_input("Nome")
            surname = st.text_input("Sobrenome")
            driverref = st.text_input("Referência (ex: 'hamilton')")
            code = st.text_input("Código (3 letras)", max_chars=3)
            dob = st.date_input("Data de Nascimento")
            nationality = st.text_input("Nacionalidade")
            if st.form_submit_button("Adicionar Piloto"):
                query = "INSERT INTO drivers (driverref, code, forename, surname, dob, nationality) VALUES (%s, %s, %s, %s, %s, %s)"
                if executar_comando_sql(conn, query, (driverref, code.upper(), forename, surname, dob, nationality)):
                    st.success(f"Piloto {forename} {surname} adicionado!")

    with tab_update:
        st.subheader("Atualizar Nacionalidade de um Piloto")
        pilotos_df_update = pd.read_sql_query("SELECT driverid, forename || ' ' || surname as driver_name FROM drivers ORDER BY surname", conn)
        piloto_sel = st.selectbox("Selecione um piloto", options=pilotos_df_update['driver_name'], index=None)
        if piloto_sel:
            id_piloto = int(pilotos_df_update[pilotos_df_update['driver_name'] == piloto_sel]['driverid'].iloc[0])
            nova_nac = st.text_input("Digite a nova nacionalidade")
            if st.button("Atualizar"):
                query = "UPDATE drivers SET nationality = %s WHERE driverid = %s"
                if executar_comando_sql(conn, query, (nova_nac, id_piloto)):
                    st.success("Nacionalidade atualizada!")

    with tab_delete:
        st.subheader("Deletar um Piloto")
        pilotos_df_del = pd.read_sql_query("SELECT driverid, forename || ' ' || surname as driver_name FROM drivers ORDER BY surname", conn)
        piloto_del = st.selectbox("Selecione um piloto para deletar", options=pilotos_df_del['driver_name'], index=None, key="del_sel")
        if piloto_del:
            id_piloto_del = int(pilotos_df_del[pilotos_df_del['driver_name'] == piloto_del]['driverid'].iloc[0])
            if st.button(f"DELETAR {piloto_del}", type="primary"):
                query = "DELETE FROM drivers WHERE driverid = %s"
                if executar_comando_sql(conn, query, (id_piloto_del,)):
                    st.success(f"Piloto {piloto_del} deletado!")

def main():
    with st.sidebar:
        st.image("f1_logo.png", width=300)
        app_page = option_menu(
            menu_title='F1 Super Analytics',
            options=['Visão Geral', 'Análise de Pilotos', 'Análise de Construtores', 'Análise de Circuitos', 'Gerenciamento (CRUD)'],
            icons=['trophy-fill', 'person-badge', 'tools', 'signpost-split', 'pencil-square'],
            menu_icon='speed', default_index=0,
            styles={"nav-link-selected": {"background-color": F1_RED}}
        )
    
    conn = conectar_db()
    if conn is None:
        st.stop()
    
    # A página de CRUD é a única que precisa da conexão direta para escrever/atualizar
    if app_page == 'Gerenciamento (CRUD)':
        # CORREÇÃO: Passa a conexão diretamente para a função de gerenciamento
        render_pagina_gerenciamento(conn)
    else:
        # As outras páginas usam os dados cacheados para performance
        dados_completos = carregar_todos_os_dados(conn)
        if dados_completos is None:
            st.stop()
        
        page_map = {
            'Visão Geral': render_visao_geral,
            'Análise de Pilotos': render_analise_pilotos,
            'Análise de Construtores': render_analise_construtores,
            'Análise de Circuitos': render_analise_circuitos
        }
        page_function = page_map.get(app_page)
        if page_function:
            page_function(dados_completos)

if __name__ == "__main__":
    main()
