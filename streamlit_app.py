import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from streamlit_option_menu import option_menu
import psycopg2
from datetime import date


st.set_page_config(layout="wide", page_title="F1 Analytics", page_icon="f1.png")
F1_PALETTE = ["#ff0800", "#7F7F7F", "#6b0000", "#B1B1B8", "#c52929", "#FFFFFF", "#9c0000"]
F1_RED = F1_PALETTE[0]
F1_BLACK = F1_PALETTE[2]
F1_GREY = F1_PALETTE[1]
F1_WHITE = F1_PALETTE[5]

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
        st.cache_data.clear()
        return True
    except Exception as e:
        conn.rollback()
        st.error(f"Erro ao executar comando SQL: {e}")
        return False

@st.cache_data(ttl=60)
def carregar_todos_os_dados(_conn):

    
    queries = {
        'races': 'select * from races', 
        'results': 'select * from results',
        'drivers': 'select * from drivers', 
        'constructors': 'select * from constructors',
        'circuits': 'select * from circuits', 
        'status': 'select * from status',
        'driver_standings': 'select * from driver_standings',
        'constructor_standings': 'select * from constructor_standings',
        'qualifying': 'select * from qualifying', 
        'pit_stops': 'select * from pit_stops',
        'lap_times': 'select * from lap_times'
    }
    data = {}
    try:
        for name, query in queries.items():
            df = pd.read_sql_query(query, _conn)
            df.columns = [col.lower() for col in df.columns]
            rename_map = {
                'raceid': 'raceId', 'driverid': 'driverId', 'constructorid': 'constructorId',
                'circuitid': 'circuitId', 'statusid': 'statusId', 'driverref': 'driverRef'
            }
            df.rename(columns=rename_map, inplace=True)
            data[name] = df
        
        for df_name in data:
            data[df_name].replace('\\N', pd.NA, inplace=True)
        
        data['races']['date'] = pd.to_datetime(data['races']['date'])
        
        data['drivers']['driver_name'] = data['drivers']['forename'] + ' ' + data['drivers']['surname']
        
        
        numeric_cols = {
            'races': ['year', 'round'],
            'results': ['points', 'position', 'grid', 'rank'],
            'pit_stops': ['milliseconds'],
            'driver_standings': ['points', 'position'],
            'constructor_standings': ['points', 'position'],
            'lap_times': ['milliseconds', 'position', 'lap'] 
        }

        for df_name, cols in numeric_cols.items():
            if df_name in data:
                for col in cols:
                    data[df_name][col] = pd.to_numeric(data[df_name][col], errors='coerce')

        if 'pit_stops' in data and not data['pit_stops'].empty:
            data['pit_stops']['duration'] = data['pit_stops']['milliseconds'] / 1000
        
        if all(k in data for k in ['results', 'races', 'drivers', 'constructors', 'status']):
            data['results_full'] = data['results'].merge(data['races'], on='raceId')\
                                                  .merge(data['drivers'], on='driverId')\
                                                  .merge(data['constructors'], on='constructorId')\
                                                  .merge(data['status'], on='statusId')
        
        return data
        
    except Exception as e:
        st.error(f"Erro ao carregar ou processar os dados: {e}. Verifique nomes de tabelas/colunas.")
        return None


def render_visao_geral(data):
    st.title("🏁 Visão Geral da Temporada")
    st.markdown("---")

    ano_selecionado = st.selectbox(
        "Selecione a Temporada",
        options=sorted(data['races']['year'].unique(), reverse=True)
    )

    races_ano = data['races'][data['races']['year'] == ano_selecionado]
    race_ids_ano = races_ano['raceId']
    results_full_ano = data['results_full'][data['results_full']['raceId'].isin(race_ids_ano)]
    
    if results_full_ano.empty:
        st.warning(f"Não há dados de resultados para a temporada de {ano_selecionado}.")
        return

    id_ultima_corrida = data['driver_standings'][data['driver_standings']['raceId'].isin(race_ids_ano)].sort_values('raceId', ascending=False).iloc[0]['raceId']
    standings_final_pilotos = data['driver_standings'][data['driver_standings']['raceId'] == id_ultima_corrida]
    standings_final_constr = data['constructor_standings'][data['constructor_standings']['raceId'] == id_ultima_corrida]
    
    campeao_piloto_nome = data['drivers'][data['drivers']['driverId'] == standings_final_pilotos[standings_final_pilotos['position'] == 1]['driverId'].iloc[0]]['driver_name'].iloc[0]
    campeao_constr_nome = data['constructors'][data['constructors']['constructorId'] == standings_final_constr[standings_final_constr['position'] == 1]['constructorId'].iloc[0]]['name'].iloc[0]
    vencedores_unicos = results_full_ano[results_full_ano['position'] == 1]['driverId'].nunique()
    poles_unicos = data['qualifying'][(data['qualifying']['raceId'].isin(race_ids_ano)) & (data['qualifying']['position'] == 1)]['driverId'].nunique()
    podios_por_equipe = results_full_ano[results_full_ano['position'].isin([1, 2, 3])]['name_y'].value_counts().nlargest(1)
    
    poles_ano = data['qualifying'][(data['qualifying']['raceId'].isin(race_ids_ano)) & (data['qualifying']['position'] == 1)][['raceId', 'driverId']]
    vitorias_ano = results_full_ano[results_full_ano['position'] == 1][['raceId', 'driverId']]
    voltas_rapidas_ano = results_full_ano[results_full_ano['rank'] == 1][['raceId', 'driverId']]
    hat_tricks = poles_ano.merge(vitorias_ano, on=['raceId', 'driverId']).merge(voltas_rapidas_ano, on=['raceId', 'driverId'])
    piloto_hat_trick = hat_tricks['driverId'].value_counts().nlargest(1)

    results_full_ano['posicoes_ganhas'] = results_full_ano['grid'] - results_full_ano['position']
    maior_escalada = results_full_ano.loc[results_full_ano['posicoes_ganhas'].idxmax()]
    piloto_escalada = maior_escalada['driver_name']

    st.subheader(f"Destaques da Temporada de {ano_selecionado}")
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("🏆 Campeão de Pilotos", campeao_piloto_nome)
    col2.metric("🏎️ Campeão de Construtores", campeao_constr_nome)
    col3.metric("🏁 Total de Corridas", races_ano['raceId'].nunique())
    col4.metric("🥇 Vencedores Diferentes", f"{vencedores_unicos} pilotos")
    
    col5, col6, col7, col8 = st.columns(4)
    col5.metric("⏱️ Pole Sitters Diferentes", f"{poles_unicos} pilotos")
    if not podios_por_equipe.empty:
        col6.metric("🍾 Equipe com Mais Pódios", f"{podios_por_equipe.index[0]} ({podios_por_equipe.values[0]})")
    if not piloto_hat_trick.empty:
        nome_piloto_ht = data['drivers'][data['drivers']['driverId'] == piloto_hat_trick.index[0]]['driver_name'].iloc[0]
        col7.metric("🎩 Mais 'Hat-Tricks'", f"{nome_piloto_ht} ({piloto_hat_trick.values[0]})")
    else:
        col7.metric("🎩 'Hat-Tricks'", "Nenhum")
    col8.metric("🚀 Maior Escalada", f"{piloto_escalada} (+{int(maior_escalada['posicoes_ganhas'])})")
    st.markdown("---")

    st.subheader("A História do Campeonato")
    top_3_pilotos_ids = standings_final_pilotos.head(3)['driverId']
    standings_ano = data['driver_standings'][data['driver_standings']['raceId'].isin(race_ids_ano)]
    standings_top_3 = standings_ano[standings_ano['driverId'].isin(top_3_pilotos_ids)].merge(data['races'], on='raceId').merge(data['drivers'], on='driverId')
    fig_disputa = px.line(standings_top_3, x='round', y='points', color='driver_name', labels={'round': 'Rodada', 'points': 'Pontos Acumulados', 'driver_name': 'Piloto'}, markers=True, color_discrete_sequence=F1_PALETTE)
    st.plotly_chart(fig_disputa, use_container_width=True)
    st.markdown("---")

    g1, g2 = st.columns(2)
    with g1:
        st.subheader("Classificação Final de Pilotos")
        top_10_drivers = standings_final_pilotos.head(10).merge(data['drivers'], on='driverId')
        fig = px.bar(top_10_drivers, x='points', y='driver_name', orientation='h', text='points', color_discrete_sequence=[F1_RED])
        fig.update_layout(yaxis={'categoryorder':'total ascending'}, yaxis_title="")
        st.plotly_chart(fig, use_container_width=True)

    with g2:
        st.subheader("Vitórias por Piloto")
        vitorias_piloto = results_full_ano[results_full_ano['position'] == 1]['driver_name'].value_counts()
        fig_vitorias = px.bar(vitorias_piloto, x=vitorias_piloto.index, y=vitorias_piloto.values, text=vitorias_piloto.values, color_discrete_sequence=[F1_GREY])
        fig_vitorias.update_layout(xaxis_title="Piloto", yaxis_title="Número de Vitórias")
        st.plotly_chart(fig_vitorias, use_container_width=True)
    st.markdown("---")

    g3, g4 = st.columns(2)
    with g3:
        st.subheader("Domínio do Pódio por Equipe")
        podios_df = results_full_ano[results_full_ano['position'].isin([1, 2, 3])]
        podios_df['position'] = podios_df['position'].astype(str)
        podios_por_equipe_detalhado = podios_df.groupby('name_y')['position'].value_counts().unstack(fill_value=0).reindex(columns=['1.0', '2.0', '3.0'], fill_value=0)
        podios_por_equipe_detalhado['total'] = podios_por_equipe_detalhado.sum(axis=1)
        podios_por_equipe_detalhado.sort_values(by=['total'], ascending=False, inplace=True)
        
        fig_podios = go.Figure()
        fig_podios.add_trace(go.Bar(name='1º Lugar', x=podios_por_equipe_detalhado.index, y=podios_por_equipe_detalhado['1.0'], marker_color=F1_RED, text=podios_por_equipe_detalhado['1.0']))
        fig_podios.add_trace(go.Bar(name='2º Lugar', x=podios_por_equipe_detalhado.index, y=podios_por_equipe_detalhado['2.0'], marker_color=F1_GREY, text=podios_por_equipe_detalhado['2.0']))
        fig_podios.add_trace(go.Bar(name='3º Lugar', x=podios_por_equipe_detalhado.index, y=podios_por_equipe_detalhado['3.0'], marker_color=F1_BLACK, text=podios_por_equipe_detalhado['3.0']))
        fig_podios.update_traces(texttemplate='%{text}', textposition='inside')
        fig_podios.update_layout(barmode='stack', xaxis_title='Equipe', yaxis_title='Número de Pódios')
        st.plotly_chart(fig_podios, use_container_width=True)
        
    with g4:
        st.subheader("Pontos por Equipe a Cada Corrida (Top 4)")
        top_4_construtores_ids = standings_final_constr.head(4)['constructorId']
        pontos_corrida_construtor = results_full_ano[results_full_ano['constructorId'].isin(top_4_construtores_ids)]
        pontos_corrida_agrupado = pontos_corrida_construtor.groupby(['name_x', 'name_y'])['points'].sum().reset_index()
        
        fig_pontos_corrida = px.bar(pontos_corrida_agrupado, x='name_x', y='points', color='name_y',
                                    labels={'name_x': 'Grande Prêmio', 'points': 'Pontos', 'name_y': 'Equipe'},
                                    color_discrete_sequence=F1_PALETTE)
        st.plotly_chart(fig_pontos_corrida, use_container_width=True)

    st.markdown("---")
    st.subheader("Análise: Posição de Largada vs. Posição Final na Temporada")
    grid_final_ano = results_full_ano[['grid', 'position']].dropna()
    grid_final_ano = grid_final_ano[(grid_final_ano['grid'] > 0) & (grid_final_ano['position'] > 0)]
    fig_grid_final = px.scatter(grid_final_ano, x='grid', y='position',
                                labels={'grid': 'Grid de Largada', 'position': 'Posição Final'},
                                trendline='ols', trendline_color_override=F1_WHITE,
                                color_discrete_sequence=[F1_RED],
                                title="Correlação entre largar na frente e terminar bem")
    st.plotly_chart(fig_grid_final, use_container_width=True)
    
from datetime import date

def render_analise_pilotos(data):
    st.title("🧑‍🚀 Análise de Pilotos")
    st.markdown("---")
    piloto_nome = st.selectbox(
        "Selecione um Piloto",
        options=data['drivers'].sort_values('surname')['driver_name'],
        index=None,
        placeholder="Digite o nome de um piloto..."
    )

    if not piloto_nome:
        st.info("Selecione um piloto para ver o dossiê completo de sua carreira.")
        return
        
    piloto_info = data['drivers'][data['drivers']['driver_name'] == piloto_nome].iloc[0]
    id_piloto = piloto_info['driverId']
    
    res_piloto = data['results_full'][data['results_full']['driverId'] == id_piloto]
    quali_piloto = data['qualifying'][data['qualifying']['driverId'] == id_piloto]

    if res_piloto.empty:
        st.warning(f"Não há dados de resultados detalhados para {piloto_nome}.")
        return

    today = date.today()
    dob = pd.to_datetime(piloto_info['dob']).date()
    idade = today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))
    primeiro_ano = res_piloto['year'].min()
    ultimo_ano = res_piloto['year'].max()

    races_com_standings = data['races'].merge(data['driver_standings'], on='raceId')
    finais_de_ano = races_com_standings.loc[races_com_standings.groupby('year')['date'].idxmax()]
    campeonatos_vencidos = finais_de_ano[(finais_de_ano['position'] == 1) & (finais_de_ano['driverId'] == id_piloto)].shape[0]

    total_corridas = res_piloto['raceId'].nunique()
    total_vitorias = (res_piloto['position'] == 1).sum()
    total_podios = res_piloto['position'].isin([1, 2, 3]).sum()
    total_poles = (quali_piloto['position'] == 1).sum()
    total_voltas_rapidas = (res_piloto['rank'] == 1).sum()
    total_pontos = res_piloto['points'].sum()
    total_voltas_corridas = res_piloto['laps'].sum()
    total_dnfs = res_piloto['position'].isna().sum()
    
    poles_df = quali_piloto[quali_piloto['position'] == 1][['raceId']]
    vitorias_df = res_piloto[res_piloto['position'] == 1][['raceId']]
    voltas_rapidas_df = res_piloto[res_piloto['rank'] == 1][['raceId']]
    hat_tricks = poles_df.merge(vitorias_df, on='raceId').merge(voltas_rapidas_df, on='raceId').shape[0]

    perc_vitorias = (total_vitorias / total_corridas * 100) if total_corridas > 0 else 0
    perc_podios = (total_podios / total_corridas * 100) if total_corridas > 0 else 0
    media_grid = quali_piloto['position'].mean()
    media_final = res_piloto['position'].dropna().mean()

    st.header(f"Dossiê de Carreira: {piloto_nome}")

    st.subheader("Informações Gerais")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("🌍 Nacionalidade", piloto_info['nationality'])
    c2.metric("🎂 Idade", f"{idade} anos")
    c3.metric("🏁 Primeira Temporada", f"{primeiro_ano}")
    c4.metric("🔚 Última Temporada", f"{ultimo_ano}")

    st.subheader("Números da Carreira")
    c5, c6, c7, c8, c9 = st.columns(5)
    c5.metric("👑 Campeonatos Mundiais", f"{campeonatos_vencidos}")
    c6.metric("🥇 Vitórias", f"{total_vitorias}")
    c7.metric("🍾 Pódios", f"{total_podios}")
    c8.metric("⏱️ Pole Positions", f"{total_poles}")
    c9.metric("🚀 Voltas Rápidas", f"{total_voltas_rapidas}")

    c10, c11, c12, c13, c14 = st.columns(5)
    c10.metric("💯 Pontos Totais", f"{total_pontos:,.0f}")
    c11.metric("🏎️ Corridas Disputadas", f"{total_corridas}")
    c12.metric("🔄 Total de Voltas", f"{total_voltas_corridas:,.0f}")
    c13.metric("💥 Total de Abandonos", f"{total_dnfs}")
    c14.metric("🎩 Hat-Tricks", f"{hat_tricks}")

    st.subheader("Métricas de Performance")
    c15, c16, c17, c18 = st.columns(4)
    c15.metric("📊 % de Vitórias", f"{perc_vitorias:.2f}%")
    c16.metric("📈 % de Pódios", f"{perc_podios:.2f}%")
    c17.metric("📉 Média de Largada", f"{media_grid:.2f}")
    c18.metric("📈 Média de Chegada", f"{media_final:.2f}")

    st.markdown("---")

    st.header("Análise Gráfica da Carreira")
    
    g1, g2 = st.columns(2)
    with g1:
        st.subheader("Resumo da Carreira")
        def categoriza_resultado_carreira(pos):
            if pos == 1: return 'Vitória'
            if pos in [2, 3]: return 'Pódio (2º-3º)'
            if 4 <= pos <= 10: return 'Terminou nos Pontos'
            if pd.notna(pos): return 'Fora dos Pontos'
            return 'Não Terminou (DNF)'
        
        res_piloto['categoria_resultado'] = res_piloto['position'].apply(categoriza_resultado_carreira)
        resultado_counts = res_piloto['categoria_resultado'].value_counts()
        fig_pie = px.pie(resultado_counts, values=resultado_counts.values, names=resultado_counts.index, 
                         hole=0.4, title=f"Distribuição de Resultados ({total_corridas} corridas)",
                         color=resultado_counts.index,
                         color_discrete_map={
                             'Vitória': F1_RED,
                             'Pódio (2º-3º)': F1_GREY,
                             'Terminou nos Pontos': F1_BLACK,
                             'Fora dos Pontos': '#D3D3D3',
                             'Não Terminou (DNF)': '#A9A9A9'
                         })
        st.plotly_chart(fig_pie, use_container_width=True, key="pilot_results_pie")

    with g2:
        st.subheader("Desempenho Anual")
        standings_piloto = data['driver_standings'][data['driver_standings']['driverId'] == id_piloto]
        if not standings_piloto.empty:
            races_com_standings_anual = data['races'].merge(standings_piloto, on='raceId')
            pos_final_ano = races_com_standings_anual.loc[races_com_standings_anual.groupby('year')['date'].idxmax()]
            
            fig_champ = px.line(pos_final_ano, x='year', y='position', markers=True, 
                                title="Posição Final no Campeonato por Ano",
                                labels={'year': 'Temporada', 'position': 'Posição Final'},
                                color_discrete_sequence=[F1_BLACK])
            fig_champ.update_yaxes(autorange="reversed")
            st.plotly_chart(fig_champ, use_container_width=True, key="pilot_standings_line")
        else:
            st.info("Dados de classificação anual não disponíveis para este piloto.")
    
    st.markdown("---")

    g3, g4 = st.columns(2)
    with g3:
        st.subheader("Maiores Palcos (Vitórias por Circuito)")
        vitorias_circuito = res_piloto[res_piloto['position'] == 1]['name_x'].value_counts().nlargest(10)
        fig_circ = px.bar(vitorias_circuito, y=vitorias_circuito.index, x=vitorias_circuito.values, orientation='h',
                           color_discrete_sequence=[F1_RED], text=vitorias_circuito.values)
        fig_circ.update_layout(xaxis_title="Número de Vitórias", yaxis_title="Circuito", yaxis={'categoryorder':'total ascending'})
        st.plotly_chart(fig_circ, use_container_width=True, key="pilot_wins_circuit_bar")

    with g4:
        st.subheader("Análise de Confiabilidade")
        dnf_reasons = res_piloto[res_piloto['position'].isna()]['status'].value_counts().nlargest(10)
        fig_dnf = px.bar(dnf_reasons, x=dnf_reasons.values, y=dnf_reasons.index, orientation='h',
                          color_discrete_sequence=[F1_GREY], text=dnf_reasons.values)
        fig_dnf.update_layout(yaxis={'categoryorder':'total ascending'}, yaxis_title="", xaxis_title="Ocorrências")
        st.plotly_chart(fig_dnf, use_container_width=True, key="pilot_dnf_bar")
        
    st.markdown("---")
    st.subheader("Grid de Largada vs. Resultado Final (Carreira)")
    grid_final_piloto = res_piloto[['grid', 'position']].dropna()
    grid_final_piloto = grid_final_piloto[(grid_final_piloto['grid'] > 0) & (grid_final_piloto['position'] > 0)]
    fig_grid_final = px.scatter(grid_final_piloto, x='grid', y='position',
                                labels={'grid': 'Grid de Largada', 'position': 'Posição Final'},
                                trendline='ols', trendline_color_override=F1_RED,
                                color_discrete_sequence=[F1_RED],
                                title=f"Correlação entre largar e chegar ({len(grid_final_piloto)} corridas)")
    st.plotly_chart(fig_grid_final, use_container_width=True, key="pilot_grid_scatter")

def render_analise_construtores(data):
    st.title("🔧 Análise de Construtores")
    st.markdown("---")

    construtor_nome = st.selectbox(
        "Selecione um Construtor",
        options=data['constructors'].sort_values('name')['name'],
        index=None,
        placeholder="Digite o nome de um construtor..."
    )

    if not construtor_nome:
        st.info("Selecione um construtor para ver o dossiê completo de sua história.")
        return

    construtor_info = data['constructors'][data['constructors']['name'] == construtor_nome].iloc[0]
    id_construtor = construtor_info['constructorId']
    
    results_construtor = data['results_full'][data['results_full']['constructorId'] == id_construtor]

    if results_construtor.empty:
        st.warning(f"Não há dados de resultados para {construtor_nome}.")
        return

    st.header(f"Dossiê da Equipe: {construtor_nome}")

    primeiro_ano = results_construtor['year'].min()
    ultimo_ano = results_construtor['year'].max()
    
    standings_construtor = data['constructor_standings'][data['constructor_standings']['constructorId'] == id_construtor]
    campeonatos_constr = 0
    pos_final_ano_constr = pd.DataFrame() 
    if not standings_construtor.empty:
        races_com_standings = data['races'].merge(standings_construtor, on='raceId')
        races_com_standings['round'] = pd.to_numeric(races_com_standings['round'], errors='coerce')
        pos_final_ano_constr = races_com_standings.loc[races_com_standings.groupby('year')['round'].idxmax()]
        campeonatos_constr = (pos_final_ano_constr['position'] == 1).sum()

    vitorias_por_piloto = results_construtor[results_construtor['position'] == 1]['driver_name'].value_counts().nlargest(1)
    pontos_por_piloto = results_construtor.groupby('driver_name')['points'].sum().nlargest(1)
    
    anos_com_pilotos_campeoes = []
    standings_pilotos_geral = data['driver_standings']
    for year in results_construtor['year'].unique():
        id_ultima_corrida_ano = data['races'][data['races']['year'] == year]['raceId'].max()
        campeao_ano = standings_pilotos_geral[(standings_pilotos_geral['raceId'] == id_ultima_corrida_ano) & (standings_pilotos_geral['position'] == 1)]
        if not campeao_ano.empty:
            id_piloto_campeao = campeao_ano['driverId'].iloc[0]
            if id_piloto_campeao in results_construtor[results_construtor['year'] == year]['driverId'].unique():
                anos_com_pilotos_campeoes.append(year)
    
    st.subheader("Visão Geral da Equipe")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("🌍 Nacionalidade", construtor_info['nationality'])
    c2.metric("🏁 Primeira Temporada", f"{primeiro_ano}")
    c3.metric("🔚 Última Temporada", f"{ultimo_ano}")
    c4.metric("🏆 Títulos de Construtores", campeonatos_constr)

    st.subheader("Pilotos de Destaque da Equipe")
    c5, c6, c7, c8 = st.columns(4)
    c5.metric("👥 Total de Pilotos", results_construtor['driverId'].nunique())
    if not vitorias_por_piloto.empty:
        c6.metric("🥇 Piloto com Mais Vitórias", f"{vitorias_por_piloto.index[0]} ({vitorias_por_piloto.values[0]})")
    if not pontos_por_piloto.empty:
        c7.metric("💯 Piloto com Mais Pontos", f"{pontos_por_piloto.index[0]} ({int(pontos_por_piloto.values[0])})")
    c8.metric("👑 Anos com Pilotos Campeões", str(len(anos_com_pilotos_campeoes)) if anos_com_pilotos_campeoes else "0")

    st.markdown("---")

    st.header("Análise Gráfica Histórica")

    st.subheader("Desempenho Anual no Campeonato de Construtores")
    if not pos_final_ano_constr.empty:
        fig_champ = px.line(pos_final_ano_constr, x='year', y='position', markers=True, 
                            labels={'year': 'Temporada', 'position': 'Posição Final'},
                            color_discrete_sequence=[F1_BLACK])
        fig_champ.update_yaxes(autorange="reversed")
        st.plotly_chart(fig_champ, use_container_width=True)
    
    st.markdown("---")

    st.subheader("Pilotos Lendários da Equipe")
    g1, g2 = st.columns(2)
    with g1:
        st.markdown("**Top 5 Pilotos por Pontos**")
        top_pontos = results_construtor.groupby('driver_name')['points'].sum().nlargest(5)
        fig_top_pontos = px.bar(top_pontos, y=top_pontos.index, x=top_pontos.values, orientation='h', color_discrete_sequence=[F1_GREY], text=top_pontos.values)
        fig_top_pontos.update_layout(yaxis={'categoryorder':'total ascending'}, yaxis_title="", xaxis_title="Pontos")
        st.plotly_chart(fig_top_pontos, use_container_width=True)
    with g2:
        st.markdown("**Top 5 Pilotos por Vitórias**")
        top_vitorias = results_construtor[results_construtor['position'] == 1]['driver_name'].value_counts().nlargest(5)
        fig_top_vitorias = px.bar(top_vitorias, y=top_vitorias.index, x=top_vitorias.values, orientation='h', color_discrete_sequence=[F1_RED], text=top_vitorias.values)
        fig_top_vitorias.update_layout(yaxis={'categoryorder':'total ascending'}, yaxis_title="", xaxis_title="Vitórias")
        st.plotly_chart(fig_top_vitorias, use_container_width=True)
        
def render_h2h(data):
    st.title("⚔️ Head-to-Head: Comparativo de Pilotos")
    st.markdown("---")

    def get_winner_metric_label(value1, value2):
        if value1 > value2:
            return f"+"
        elif value2 > value1:
            return f"-"
        return ""

    col1, col2 = st.columns(2)
    drivers_sorted = data['drivers'].sort_values('surname')['driver_name']
    piloto1_nome = col1.selectbox("Selecione o Piloto 1", options=drivers_sorted, index=None, placeholder="Primeiro piloto...")
    piloto2_nome = col2.selectbox("Selecione o Piloto 2", options=drivers_sorted, index=None, placeholder="Segundo piloto...")

    if not piloto1_nome or not piloto2_nome:
        st.info("Selecione dois pilotos para iniciar a comparação.")
        return

    if piloto1_nome == piloto2_nome:
        st.warning("Por favor, selecione dois pilotos diferentes.")
        return

    id1 = data['drivers'][data['drivers']['driver_name'] == piloto1_nome]['driverId'].iloc[0]
    id2 = data['drivers'][data['drivers']['driver_name'] == piloto2_nome]['driverId'].iloc[0]
    
    res1 = data['results_full'][data['results_full']['driverId'] == id1].sort_values(by='date').reset_index()
    res2 = data['results_full'][data['results_full']['driverId'] == id2].sort_values(by='date').reset_index()
    quali1 = data['qualifying'][data['qualifying']['driverId'] == id1]
    quali2 = data['qualifying'][data['qualifying']['driverId'] == id2]

    vitorias1, vitorias2 = (res1['position'] == 1).sum(), (res2['position'] == 1).sum()
    podios1, podios2 = res1['position'].isin([1,2,3]).sum(), res2['position'].isin([1,2,3]).sum()
    poles1, poles2 = (quali1['position'] == 1).sum(), (quali2['position'] == 1).sum()
    
    ultima_corrida1 = res1.iloc[-1] if not res1.empty else None
    ultima_corrida2 = res2.iloc[-1] if not res2.empty else None

    res_comum = res1.merge(res2, on='raceId', suffixes=('_p1', '_p2'))
    res_comum_finalizado = res_comum.dropna(subset=['position_p1', 'position_p2'])
    vantagem_corrida_p1 = (res_comum_finalizado['position_p1'] < res_comum_finalizado['position_p2']).sum()
    vantagem_corrida_p2 = (res_comum_finalizado['position_p2'] < res_comum_finalizado['position_p1']).sum()

    st.subheader("Placar Geral")
    
    c1, c2 = st.columns(2)
    with c1:
        st.markdown(f"<h3 style='text-align: center;'>{piloto1_nome}</h3>", unsafe_allow_html=True)
        st.metric("Vitórias", f"{vitorias1}", delta=get_winner_metric_label(vitorias1, vitorias2))
        st.metric("Pódios", f"{podios1}", delta=get_winner_metric_label(podios1, podios2))
        st.metric("Pole Positions", f"{poles1}", delta=get_winner_metric_label(poles1, poles2))
        if ultima_corrida1 is not None:
            st.metric("Última Corrida", f"{int(ultima_corrida1['year'])} - {ultima_corrida1['name_x']}")
            st.metric("Última Equipe", ultima_corrida1['name_y'])
        
    with c2:
        st.markdown(f"<h3 style='text-align: center;'>{piloto2_nome}</h3>", unsafe_allow_html=True)
        st.metric("Vitórias", f"{vitorias2}", delta=get_winner_metric_label(vitorias2, vitorias1), delta_color="inverse")
        st.metric("Pódios", f"{podios2}", delta=get_winner_metric_label(podios2, podios1), delta_color="inverse")
        st.metric("Pole Positions", f"{poles2}", delta=get_winner_metric_label(poles2, poles1), delta_color="inverse")
        if ultima_corrida2 is not None:
            st.metric("Última Corrida", f"{int(ultima_corrida2['year'])} - {ultima_corrida2['name_x']}")
            st.metric("Última Equipe", ultima_corrida2['name_y'])
    
    st.markdown("---")

    st.header("Análise Gráfica Comparativa")

    st.subheader("Trajetória de Vitórias na Carreira")
    vitorias_p1_df = res1[res1['position'] == 1].reset_index(drop=True)
    vitorias_p1_df['num_vitoria'] = vitorias_p1_df.index + 1
    vitorias_p1_df['num_corrida'] = vitorias_p1_df['index'] + 1

    vitorias_p2_df = res2[res2['position'] == 1].reset_index(drop=True)
    vitorias_p2_df['num_vitoria'] = vitorias_p2_df.index + 1
    vitorias_p2_df['num_corrida'] = vitorias_p2_df['index'] + 1

    fig_traj = go.Figure()
    fig_traj.add_trace(go.Scatter(x=vitorias_p1_df['num_corrida'], y=vitorias_p1_df['num_vitoria'], name=piloto1_nome, mode='lines+markers', line=dict(color=F1_RED, shape='spline')))
    fig_traj.add_trace(go.Scatter(x=vitorias_p2_df['num_corrida'], y=vitorias_p2_df['num_vitoria'], name=piloto2_nome, mode='lines+markers', line=dict(color=F1_GREY, shape='spline')))
    fig_traj.update_layout(title="Curva de Vitórias (Nº de GPs para cada vitória)",
                           xaxis_title="Número de Corridas na Carreira",
                           yaxis_title="Número de Vitórias Acumuladas")
    st.plotly_chart(fig_traj, use_container_width=True)
    st.markdown("---")
    
    g1, g2 = st.columns(2)
    with g1:
        st.subheader(f"Confronto Direto em Corrida ({len(res_comum_finalizado)} corridas)")
        df_pie_race = pd.DataFrame({'Piloto': [piloto1_nome, piloto2_nome], 'Vezes na Frente': [vantagem_corrida_p1, vantagem_corrida_p2]})
        fig_pie_r = px.pie(df_pie_race, values='Vezes na Frente', names='Piloto', hole=0.4, color='Piloto', color_discrete_map={piloto1_nome: F1_RED, piloto2_nome: F1_GREY})
        st.plotly_chart(fig_pie_r, use_container_width=True)
    with g2:
        quali_comum = quali1.merge(quali2, on='raceId', suffixes=('_p1', '_p2'))
        vantagem_quali_p1 = (quali_comum['position_p1'] < quali_comum['position_p2']).sum()
        vantagem_quali_p2 = (quali_comum['position_p2'] < quali_comum['position_p1']).sum()
        st.subheader(f"Confronto em Qualificação ({len(quali_comum)} sessões)")
        df_pie_quali = pd.DataFrame({'Piloto': [piloto1_nome, piloto2_nome], 'Vezes na Frente': [vantagem_quali_p1, vantagem_quali_p2]})
        fig_pie_q = px.pie(df_pie_quali, values='Vezes na Frente', names='Piloto', hole=0.4, color='Piloto', color_discrete_map={piloto1_nome: F1_RED, piloto2_nome: F1_GREY})
        st.plotly_chart(fig_pie_q, use_container_width=True)

    st.markdown("---")
    
    st.subheader("Placar de Posições Finais (Apenas em Corridas Juntos)")
    posicoes_p1 = res_comum_finalizado['position_p1'].value_counts().nlargest(10)
    posicoes_p2 = res_comum_finalizado['position_p2'].value_counts().nlargest(10)
    df_pos = pd.DataFrame({piloto1_nome: posicoes_p1, piloto2_nome: posicoes_p2}).fillna(0).astype(int)
    
    fig_pos = go.Figure()
    fig_pos.add_trace(go.Bar(name=piloto1_nome, x=df_pos.index, y=df_pos[piloto1_nome], text=df_pos[piloto1_nome], marker_color=F1_RED))
    fig_pos.add_trace(go.Bar(name=piloto2_nome, x=df_pos.index, y=df_pos[piloto2_nome], text=df_pos[piloto2_nome], marker_color=F1_GREY))
    fig_pos.update_layout(barmode='group', xaxis_title="Posição Final", yaxis_title="Número de Vezes", xaxis={'categoryorder':'category ascending'})
    st.plotly_chart(fig_pos, use_container_width=True)
    
def render_hall_da_fama(data):
    st.title("🏆 Hall da Fama: As Lendas do Esporte")
    
    st.markdown("---")

    results_full = data['results_full']
    drivers = data['drivers']
    constructors = data['constructors']
    qualifying = data['qualifying']
    
    pontos_por_ano_piloto = results_full.groupby(['year', 'driverId'])['points'].sum().reset_index()
    indices_campeoes = pontos_por_ano_piloto.loc[pontos_por_ano_piloto.groupby('year')['points'].idxmax()]
    campeoes_df = indices_campeoes.merge(drivers, on='driverId')
    campeoes_pilotos = campeoes_df['driver_name'].value_counts()
    
    pontos_por_ano_construtor = results_full.groupby(['year', 'constructorId'])['points'].sum().reset_index()
    indices_campeoes_c = pontos_por_ano_construtor.loc[pontos_por_ano_construtor.groupby('year')['points'].idxmax()]
    campeoes_construtores_df = indices_campeoes_c.merge(constructors, on='constructorId')
    
    campeoes_construtores = campeoes_construtores_df['name'].value_counts()

    vitorias_temporada_piloto = results_full[results_full['position'] == 1].groupby(['year', 'driver_name']).size().nlargest(1)
    vitorias_temporada_construtor = results_full[results_full['position'] == 1].groupby(['year', 'name_y']).size().nlargest(1)
    corridas_por_piloto = results_full.groupby('driverId')['raceId'].nunique()
    corridas_validas = corridas_por_piloto[corridas_por_piloto >= 50].index
    vitorias_por_piloto_raw = results_full[results_full['driverId'].isin(corridas_validas)]
    vitorias_por_piloto_raw = vitorias_por_piloto_raw[vitorias_por_piloto_raw['position'] == 1]['driverId'].value_counts()
    perc_vitorias = (vitorias_por_piloto_raw / corridas_por_piloto).dropna().nlargest(1)
    vitorias_pilotos = results_full[results_full['position'] == 1]['driver_name'].value_counts()
    podios_pilotos = results_full[results_full['position'].isin([1,2,3])]['driver_name'].value_counts()
    poles_pilotos = qualifying[qualifying['position'] == 1].merge(drivers, on='driverId')['driver_name'].value_counts()
    vitorias_construtores = results_full[results_full['position'] == 1]['name_y'].value_counts()
    podios_construtores = results_full[results_full['position'].isin([1,2,3])]['name_y'].value_counts()


    st.header("Os Recordistas Absolutos (Baseado nos Dados Históricos)")
    st.subheader("Pilotos Lendários")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("👑 Mais Títulos", f"{campeoes_pilotos.index[0]}", f"{campeoes_pilotos.values[0]} Títulos")
    c2.metric("🥇 Mais Vitórias", f"{vitorias_pilotos.index[0]}", f"{vitorias_pilotos.values[0]} Vitórias")
    c3.metric("🍾 Mais Pódios", f"{podios_pilotos.index[0]}", f"{podios_pilotos.values[0]} Pódios")
    c4.metric("⏱️ Mais Poles", f"{poles_pilotos.index[0]}", f"{poles_pilotos.values[0]} Poles")

    st.subheader("Construtores Dominantes")
    c5, c6, c7, c8 = st.columns(4)
    c5.metric("👑 Mais Títulos", f"{campeoes_construtores.index[0]}", f"{campeoes_construtores.values[0]} Títulos")
    c6.metric("🥇 Mais Vitórias", f"{vitorias_construtores.index[0]}", f"{vitorias_construtores.values[0]} Vitórias")
    c7.metric("🍾 Mais Pódios", f"{podios_construtores.index[0]}", f"{podios_construtores.values[0]} Pódios")
    if not vitorias_temporada_construtor.empty:
        c8.metric("🗓️ Mais Vitórias (Equipe/Ano)", f"{vitorias_temporada_construtor.index[0][1]} ({vitorias_temporada_construtor.index[0][0]})", f"{vitorias_temporada_construtor.values[0]} Vitórias")

    st.header("Rankings Históricos Detalhados")
    tab_vit, tab_pod, tab_pol, tab_camp, tab_nacoes = st.tabs(["Vitórias", "Pódios", "Pole Positions", "Campeonatos", "Batalha das Nações"])

    with tab_vit:
        g1, g2 = st.columns(2)
        with g1:
            st.markdown("**Top 15 Pilotos por Vitórias**")
            fig = px.bar(vitorias_pilotos.head(15), x=vitorias_pilotos.head(15).values, y=vitorias_pilotos.head(15).index, orientation='h', text=vitorias_pilotos.head(15).values, color_discrete_sequence=[F1_RED])
            fig.update_layout(yaxis={'categoryorder':'total ascending'}, yaxis_title="")
            st.plotly_chart(fig, use_container_width=True)
        with g2:
            st.markdown("**Top 15 Construtores por Vitórias**")
            fig = px.bar(vitorias_construtores.head(15), x=vitorias_construtores.head(15).values, y=vitorias_construtores.head(15).index, orientation='h', text=vitorias_construtores.head(15).values, color_discrete_sequence=[F1_GREY])
            fig.update_layout(yaxis={'categoryorder':'total ascending'}, yaxis_title="")
            st.plotly_chart(fig, use_container_width=True)
            
    with tab_pod:
        g1, g2 = st.columns(2)
        with g1:
            st.markdown("**Top 15 Pilotos por Pódios**")
            fig = px.bar(podios_pilotos.head(15), x=podios_pilotos.head(15).values, y=podios_pilotos.head(15).index, orientation='h', text=podios_pilotos.head(15).values, color_discrete_sequence=[F1_RED])
            fig.update_layout(yaxis={'categoryorder':'total ascending'}, yaxis_title="")
            st.plotly_chart(fig, use_container_width=True)
        with g2:
            st.markdown("**Top 15 Construtores por Pódios**")
            fig = px.bar(podios_construtores.head(15), x=podios_construtores.head(15).values, y=podios_construtores.head(15).index, orientation='h', text=podios_construtores.head(15).values, color_discrete_sequence=[F1_GREY])
            fig.update_layout(yaxis={'categoryorder':'total ascending'}, yaxis_title="")
            st.plotly_chart(fig, use_container_width=True)

    with tab_pol:
        st.markdown("**Top 15 Pilotos por Pole Positions**")
        fig = px.bar(poles_pilotos.head(15), x=poles_pilotos.head(15).values, y=poles_pilotos.head(15).index, orientation='h', text=poles_pilotos.head(15).values, color_discrete_sequence=[F1_BLACK])
        fig.update_layout(yaxis={'categoryorder':'total ascending'}, yaxis_title="")
        st.plotly_chart(fig, use_container_width=True)

    with tab_camp:
        g1, g2 = st.columns(2)
        with g1:
            st.markdown("**Pilotos Multicampeões**")
            fig = px.bar(campeoes_pilotos, x=campeoes_pilotos.index, y=campeoes_pilotos.values, text=campeoes_pilotos.values, color_discrete_sequence=[F1_RED])
            fig.update_layout(xaxis_title="Piloto", yaxis_title="Nº de Títulos")
            st.plotly_chart(fig, use_container_width=True)
        with g2:
            st.markdown("**Construtores Multicampeões**")
            fig = px.bar(campeoes_construtores, x=campeoes_construtores.index, y=campeoes_construtores.values, text=campeoes_construtores.values, color_discrete_sequence=[F1_GREY])
            fig.update_layout(xaxis_title="Construtor", yaxis_title="Nº de Títulos")
            st.plotly_chart(fig, use_container_width=True)
            
    with tab_nacoes:
        st.subheader("Domínio por Nacionalidade")
        g1, g2 = st.columns(2)
        with g1:
            st.markdown("**Títulos Mundiais de Pilotos por País**")
            nacoes_campeas = campeoes_df['nationality'].value_counts()
            fig_nac_camp = px.pie(nacoes_campeas, values=nacoes_campeas.values, names=nacoes_campeas.index, hole=0.4, color_discrete_sequence=F1_PALETTE)
            st.plotly_chart(fig_nac_camp, use_container_width=True)
        with g2:
            st.markdown("**Vitórias de Pilotos por País (Top 10)**")
            nacoes_vitoriosas = results_full[results_full['position'] == 1]['nationality_x'].value_counts().nlargest(10)
            fig_nac_vit = px.bar(nacoes_vitoriosas, x=nacoes_vitoriosas.index, y=nacoes_vitoriosas.values, text=nacoes_vitoriosas.values, color_discrete_sequence=F1_PALETTE)
            st.plotly_chart(fig_nac_vit, use_container_width=True)
        
def render_analise_circuitos(data):
    st.title("🛣️ Análise de Circuitos")
    st.markdown("---")

    circuito_nome = st.selectbox(
        "Selecione um Circuito",
        options=data['circuits'].sort_values('name')['name'],
        index=None,
        placeholder="Digite o nome de um circuito..."
    )

    if not circuito_nome:
        st.info("Selecione um circuito para ver suas estatísticas detalhadas.")
        return

    circuito_info = data['circuits'][data['circuits']['name'] == circuito_nome].iloc[0]
    id_circuito = circuito_info['circuitId']
    
    races_circuito = data['races'][data['races']['circuitId'] == id_circuito]
    race_ids_circuito = races_circuito['raceId']
    results_circuito = data['results_full'][data['results_full']['raceId'].isin(race_ids_circuito)]

    if results_circuito.empty:
        st.warning(f"Não há dados de resultados detalhados para {circuito_nome}.")
        return

    primeiro_gp = int(races_circuito['year'].min())
    ultimo_gp = int(races_circuito['year'].max())
    total_gps = races_circuito['raceId'].nunique()
    
    id_ultima_corrida = races_circuito[races_circuito['year'] == ultimo_gp]['raceId'].iloc[0]
    vencedor_ultimo_gp = results_circuito[(results_circuito['raceId'] == id_ultima_corrida) & (results_circuito['position'] == 1)]['driver_name'].iloc[0]

    lap_times_circuito = data['lap_times'][data['lap_times']['raceId'].isin(race_ids_circuito)]
    if not lap_times_circuito.empty:
        lap_record_row = lap_times_circuito.loc[lap_times_circuito['milliseconds'].idxmin()]
        piloto_recordista = data['drivers'][data['drivers']['driverId'] == lap_record_row['driverId']]['driver_name'].iloc[0]
        tempo_recorde = pd.to_datetime(lap_record_row['time'], format='%M:%S.%f').strftime('%M:%S.%f')[:-3]
    else:
        piloto_recordista, tempo_recorde = "N/A", "N/A"
        
    poles_no_circuito = data['qualifying'][(data['qualifying']['raceId'].isin(race_ids_circuito)) & (data['qualifying']['position'] == 1)]
    vitorias_da_pole = poles_no_circuito.merge(results_circuito[results_circuito['position'] == 1], on=['raceId', 'driverId'])
    perc_win_pole = (len(vitorias_da_pole) / len(poles_no_circuito) * 100) if not poles_no_circuito.empty else 0

    st.header(f"Dossiê do Circuito: {circuito_nome}")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("🌍 País", circuito_info['country'])
    c2.metric("📍 Localização", circuito_info['location'])
    c3.metric("🏁 Primeiro GP", f"{primeiro_gp}")
    c4.metric("🏎️ Total de GPs", f"{total_gps}")

    c5, c6, c7, c8 = st.columns(4)
    c5.metric("🗓️ Último GP", f"{ultimo_gp}")
    c6.metric("🏆 Vencedor do Último GP", vencedor_ultimo_gp)
    c7.metric("⏱️ Recorde da Pista", f"{piloto_recordista} ({tempo_recorde})")
    c8.metric("📊 % Vitória da Pole", f"{perc_win_pole:.2f}%")
    st.markdown("---")

    st.header("Análise Gráfica do Circuito")
    
    g1, g2 = st.columns(2)
    with g1:
        st.subheader("Reis da Pista (Mais Vitórias)")
        maiores_vencedores = results_circuito[results_circuito['position'] == 1]['driver_name'].value_counts().nlargest(10)
        fig_vitorias = px.bar(maiores_vencedores, y=maiores_vencedores.index, x=maiores_vencedores.values, orientation='h',
                              color_discrete_sequence=[F1_RED], text=maiores_vencedores.values)
        fig_vitorias.update_layout(yaxis={'categoryorder':'total ascending'}, yaxis_title="", xaxis_title="Número de Vitórias")
        st.plotly_chart(fig_vitorias, use_container_width=True, key="circuit_wins_chart")
    with g2:
        st.subheader("Recordistas de Pole Position")
        recordistas_pole = poles_no_circuito.merge(data['drivers'], on='driverId')['driver_name'].value_counts().nlargest(10)
        fig_poles = px.bar(recordistas_pole, y=recordistas_pole.index, x=recordistas_pole.values, orientation='h',
                           color_discrete_sequence=[F1_BLACK], text=recordistas_pole.values)
        fig_poles.update_layout(yaxis={'categoryorder':'total ascending'}, yaxis_title="", xaxis_title="Número de Poles")
        st.plotly_chart(fig_poles, use_container_width=True, key="circuit_poles_chart")
    
    st.markdown("---")
    
    st.subheader("Evolução do Tempo da Volta Mais Rápida")
    if not lap_times_circuito.empty:
        fastest_laps_ano = lap_times_circuito.loc[lap_times_circuito.groupby('raceId')['milliseconds'].idxmin()]
        fastest_laps_ano = fastest_laps_ano.merge(races_circuito, on='raceId')
        fig_lap_evo = px.line(fastest_laps_ano, x='year', y='milliseconds',
                              labels={'year': 'Ano', 'milliseconds': 'Tempo de Volta (ms)'},
                              title="Como os Carros Ficaram Mais Rápidos", markers=True,
                              color_discrete_sequence=[F1_GREY])
        st.plotly_chart(fig_lap_evo, use_container_width=True, key="circuit_lap_evo_chart")
    st.markdown("---")

    g3, g4 = st.columns(2)
    with g3:
        st.subheader("De Onde Saem os Vencedores?")
        pos_grid_vencedores = results_circuito[(results_circuito['position'] == 1) & (results_circuito['grid'] > 0)]
        fig_grid = px.histogram(pos_grid_vencedores, x='grid', nbins=20, text_auto=True, color_discrete_sequence=F1_PALETTE)
        fig_grid.update_layout(xaxis_title="Posição de Largada", yaxis_title="Número de Vitórias")
        st.plotly_chart(fig_grid, use_container_width=True, key="circuit_winner_grid_chart")
    with g4:
        st.subheader("Confiabilidade das Equipes no Circuito")
        dnfs_por_equipe = results_circuito[results_circuito['position'].isna()]['name_y'].value_counts().nlargest(10)
        fig_dnf = px.bar(dnfs_por_equipe, y=dnfs_por_equipe.index, x=dnfs_por_equipe.values, orientation='h',
                         color_discrete_sequence=F1_PALETTE, text=dnfs_por_equipe.values)
        fig_dnf.update_layout(yaxis={'categoryorder':'total ascending'}, yaxis_title="", xaxis_title="Total de Abandonos (DNF)")
        st.plotly_chart(fig_dnf, use_container_width=True, key="circuit_dnf_chart")

def render_pagina_gerenciamento(conn):
    st.title("🔩 Gerenciamento de Dados (CRUD)")

    try:
        pilotos_df_completo = pd.read_sql_query('SELECT id_piloto, ref_piloto, codigo, numero, nome, sobrenome, data_nascimento, nacionalidade FROM tbl_pilotos ORDER BY sobrenome', conn)
        pilotos_df_completo.dropna(subset=['id_piloto', 'nome', 'sobrenome'], inplace=True)
        pilotos_df_completo['nome_completo'] = pilotos_df_completo['nome'] + ' ' + pilotos_df_completo['sobrenome']
    except Exception as e:
        st.error(f"Não foi possível carregar os dados dos pilotos do banco: {e}")
        return

    tab_create, tab_read, tab_update, tab_delete = st.tabs(["➕ Criar Piloto", "🔍 Consultar Pilotos", "🔄 Atualizar Piloto", "❌ Deletar Piloto"])

    with tab_create:
        st.subheader("Adicionar Novo Piloto")
        nationalities = sorted([
            "Argentine", "Australian", "Austrian", "Belgian", "Brazilian", "British", "Canadian", "Colombian",
            "Danish", "Dutch", "Finnish", "French", "German", "Hungarian", "Indian", "Irish", "Italian",
            "Japanese", "Malaysian", "Mexican", "Monegasque", "New Zealander", "Polish", "Portuguese",
            "Russian", "South African", "Spanish", "Swedish", "Swiss", "Thai", "American", "Venezuelan"
        ])

        with st.form("form_create", clear_on_submit=True):
            nome = st.text_input("Nome")
            sobrenome = st.text_input("Sobrenome")
            ref_piloto = st.text_input("Referência Única (ex: 'hamilton')")
            numero = st.number_input("Número do Piloto", min_value=0, max_value=99, step=1, value=None)
            codigo = st.text_input("Código de 3 letras (ex: 'HAM')", max_chars=3)
            data_nascimento = st.date_input("Data de Nascimento")
            nacionalidade = st.selectbox("Nacionalidade", options=nationalities, index=None, placeholder="Selecione...")
            
            if st.form_submit_button("Adicionar Piloto"):
                if all([nome, sobrenome, ref_piloto, data_nascimento, nacionalidade, codigo]):
                    try:
                        cursor = conn.cursor()
                        cursor.execute("SELECT MAX(id_piloto) FROM tbl_pilotos")
                        max_id = cursor.fetchone()[0]
                        novo_id = (max_id or 0) + 1
                        
                        query = 'INSERT INTO tbl_pilotos (id_piloto, ref_piloto, numero, codigo, nome, sobrenome, data_nascimento, nacionalidade) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)'
                        params = (novo_id, ref_piloto, numero, codigo.upper(), nome, sobrenome, data_nascimento, nacionalidade)
                        
                        cursor.execute(query, params)
                        conn.commit()
                        cursor.close()
                        
                        st.success(f"Piloto {nome} {sobrenome} adicionado com SUCESSO!")
                        st.rerun()

                    except Exception as e:
                        conn.rollback()
                        st.error(f"Falha ao adicionar piloto no banco de dados: {e}")
                else:
                    st.warning("Por favor, preencha todos os campos obrigatórios.")

    with tab_read:
        st.subheader("Consultar e Filtrar Pilotos")
        search_term = st.selectbox("Selecione um piloto para procurar", options=pilotos_df_completo['nome_completo'], index=None)
        
        df_display = pilotos_df_completo
        if search_term:
            search_term = search_term.lower()
            df_display = df_display[
                df_display['nome'].str.lower().contains(search_term) |
                df_display['sobrenome'].str.lower().contains(search_term) |
                df_display['codigo'].str.lower().contains(search_term, na=False)
            ]
        st.dataframe(df_display, use_container_width=True, hide_index=True)

    with tab_update:
        st.subheader("Atualizar Dados de um Piloto")
        piloto_selecionado_nome = st.selectbox("Selecione um piloto para atualizar", options=pilotos_df_completo['nome_completo'], index=None)
        
        if piloto_selecionado_nome:
            piloto_info = pilotos_df_completo[pilotos_df_completo['nome_completo'] == piloto_selecionado_nome].iloc[0]
            id_piloto = int(piloto_info['id_piloto'])
            st.write("---")
            
            current_number = piloto_info['numero']
            number_value = int(current_number) if pd.notna(current_number) else None

            novo_codigo = st.text_input("Código (3 letras)", value=piloto_info['codigo'] or "", max_chars=3, key=f"code_{id_piloto}")
            novo_numero = st.number_input("Número do Piloto", value=number_value, min_value=0, max_value=99, step=1, key=f"number_{id_piloto}")
            
            if st.button("Salvar Alterações"):
                query = 'UPDATE tbl_pilotos SET codigo = %s, numero = %s WHERE id_piloto = %s'
                if executar_comando_sql(conn, query, (novo_codigo.upper(), novo_numero, id_piloto)):
                    st.success(f"Dados do piloto {piloto_selecionado_nome} atualizados!")
                    st.rerun()

    with tab_delete:
        st.subheader("Deletar um Piloto")
        st.warning("CUIDADO: Esta ação é irreversível.", icon="⚠️")
        piloto_para_deletar = st.selectbox("Selecione um piloto para deletar", options=pilotos_df_completo['nome_completo'], index=None, key="delete_select")
        
        if piloto_para_deletar:
            id_piloto_del = int(pilotos_df_completo[pilotos_df_completo['nome_completo'] == piloto_para_deletar]['id_piloto'].iloc[0])
            if st.button(f"DELETAR PERMANENTEMENTE {piloto_para_deletar}", type="primary"):
                query = 'DELETE FROM tbl_pilotos WHERE id_piloto = %s'
                if executar_comando_sql(conn, query, (id_piloto_del,)):
                    st.success(f"Piloto {piloto_para_deletar} deletado!")
                    st.rerun()
            
def main():
    with st.sidebar:
        st.image("f1_logo.png", width=300)
        app_page = option_menu(
            menu_title='F1 Analytics',
            options=['Visão Geral', 'Análise de Pilotos', 'Análise de Construtores', 'Análise de Circuitos', 'H2H', 'Hall da Fama', 'Gerenciamento (CRUD)'],
            icons=['trophy-fill', 'person-badge', 'tools', 'signpost-split', 'people-fill', 'award-fill', 'pencil-square'],
            menu_icon='speed',
            default_index=0,
            key='main_menu',
            styles={"nav-link-selected": {"background-color": F1_RED}}
        )
    
    conn = conectar_db()
    if conn is None:
        st.stop()
    
    if app_page == 'Gerenciamento (CRUD)':
        render_pagina_gerenciamento(conn)
    else:
        dados_completos = carregar_todos_os_dados(conn)
        if dados_completos is None:
            st.stop()
        
        page_map = {
            'Visão Geral': render_visao_geral,
            'Análise de Pilotos': render_analise_pilotos,
            'Análise de Construtores': render_analise_construtores,
            'Análise de Circuitos': render_analise_circuitos,
            'H2H': render_h2h,
            'Hall da Fama': render_hall_da_fama,
            'Gerenciamento (CRUD)': render_pagina_gerenciamento
        }
        page_function = page_map.get(app_page)
        if page_function:
            page_function(dados_completos)

if __name__ == "__main__":
    main()
