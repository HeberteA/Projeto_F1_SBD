import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from streamlit_option_menu import option_menu
import psycopg2


st.set_page_config(layout="wide", page_title="F1 Super Analytics Pro", page_icon="f1.png")
F1_PALETTE = ["#E10600", "#FF8700", "#00A000", "#7F7F7F", "#15151E", "#B1B1B8", "#FFFFFF"]
F1_RED = F1_PALETTE[0]
F1_BLACK = F1_PALETTE[4]
F1_GREY = F1_PALETTE[3]

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
        'races': 'select * from races', 'results': 'select * from results',
        'drivers': 'select * from drivers', 'constructors': 'select * from constructors',
        'circuits': 'select * from circuits', 'status': 'select * from status',
        'driver_standings': 'select * from driver_standings',
        'constructor_standings': 'select * from constructor_standings',
        'qualifying': 'select * from qualifying', 'pit_stops': 'select * from pit_stops'
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

        data['drivers']['driver_name'] = data['drivers']['forename'] + ' ' + data['drivers']['surname']
        numeric_cols = {
            'results': ['points', 'position', 'grid', 'rank'], 
            'pit_stops': ['milliseconds']
        }
        for df_name, cols in numeric_cols.items():
            for col in cols:
                data[df_name][col] = pd.to_numeric(data[df_name][col], errors='coerce')
        data['pit_stops']['duration'] = data['pit_stops']['milliseconds'] / 1000
        
        data['results_full'] = data['results'].merge(data['races'], on='raceId')\
                                              .merge(data['drivers'], on='driverId')\
                                              .merge(data['constructors'], on='constructorId')\
                                              .merge(data['status'], on='statusId')
        
        return data
    except Exception as e:
        st.error(f"Erro ao consultar dados: {e}. Verifique nomes de tabelas/colunas.")
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
        fig_vitorias = px.bar(vitorias_piloto, x=vitorias_piloto.index, y=vitorias_piloto.values, text=vitorias_piloto.values, color_discrete_sequence=[F1_BLACK])
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
                                trendline='ols', trendline_color_override=F1_RED,
                                color_discrete_sequence=[F1_BLACK],
                                title="Correlação entre largar na frente e terminar bem")
    st.plotly_chart(fig_grid_final, use_container_width=True)
    
def render_analise_pilotos(data):
    st.title("🧑‍🚀 Análise de Pilotos")
    st.markdown("---")

    # --- FILTRO DE PILOTO ---
    piloto_nome = st.selectbox(
        "Selecione um Piloto",
        options=data['drivers'].sort_values('surname')['driver_name'],
        index=None,
        placeholder="Digite o nome de um piloto..."
    )

    if not piloto_nome:
        st.info("Selecione um piloto para ver o dossiê completo de sua carreira.")
        return

    # --- FILTRAGEM DE DADOS PARA O PILOTO SELECIONADO ---
    piloto_info = data['drivers'][data['drivers']['driver_name'] == piloto_nome].iloc[0]
    id_piloto = piloto_info['driverId']
    
    res_piloto = data['results_full'][data['results_full']['driverId'] == id_piloto]
    quali_piloto = data['qualifying'][data['qualifying']['driverId'] == id_piloto]

    if res_piloto.empty:
        st.warning(f"Não há dados de resultados detalhados para {piloto_nome}.")
        return

    # --- CÁLCULOS PARA OS CARDS ---
    # Informações básicas
    today = date.today()
    dob = pd.to_datetime(piloto_info['dob']).date()
    idade = today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))
    primeiro_ano = res_piloto['year'].min()
    ultimo_ano = res_piloto['year'].max()

    # Totais da Carreira
    total_corridas = res_piloto['raceId'].nunique()
    total_vitorias = (res_piloto['position'] == 1).sum()
    total_podios = res_piloto['position'].isin([1, 2, 3]).sum()
    total_poles = (quali_piloto['position'] == 1).sum()
    total_voltas_rapidas = (res_piloto['rank'] == 1).sum()
    total_pontos = res_piloto['points'].sum()
    total_voltas_corridas = res_piloto['laps'].sum()
    total_dnfs = res_piloto['position'].isna().sum()
    
    # Médias e Percentuais
    perc_vitorias = (total_vitorias / total_corridas * 100) if total_corridas > 0 else 0
    perc_podios = (total_podios / total_corridas * 100) if total_corridas > 0 else 0
    media_grid = quali_piloto['position'].mean()
    media_final = res_piloto['position'].dropna().mean()
    confiabilidade = ((total_corridas - total_dnfs) / total_corridas * 100) if total_corridas > 0 else 0

    # --- EXIBIÇÃO DOS CARDS ---
    st.header(f"Dossiê de Carreira: {piloto_nome}")

    st.subheader("Informações Gerais")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("🌍 Nacionalidade", piloto_info['nationality'])
    c2.metric("🎂 Idade", f"{idade} anos")
    c3.metric("🏁 Primeira Temporada", f"{primeiro_ano}")
    c4.metric("🔚 Última Temporada", f"{ultimo_ano}")

    st.subheader("Números da Carreira")
    c5, c6, c7, c8 = st.columns(4)
    c5.metric("🏆 Vitórias", f"{total_vitorias}")
    c6.metric("🍾 Pódios", f"{total_podios}")
    c7.metric("⏱️ Pole Positions", f"{total_poles}")
    c8.metric("🚀 Voltas Rápidas", f"{total_voltas_rapidas}")

    c9, c10, c11, c12 = st.columns(4)
    c9.metric("💯 Pontos Totais", f"{total_pontos:,.0f}")
    c10.metric("🏎️ Corridas Disputadas", f"{total_corridas}")
    c11.metric("🔄 Total de Voltas", f"{total_voltas_corridas:,.0f}")
    c12.metric("💥 Total de Abandonos", f"{total_dnfs}")

    st.subheader("Métricas de Performance")
    c13, c14, c15, c16 = st.columns(4)
    c13.metric("📊 % de Vitórias", f"{perc_vitorias:.2f}%")
    c14.metric("📈 % de Pódios", f"{perc_podios:.2f}%")
    c15.metric("📉 Média de Largada", f"{media_grid:.2f}")
    c16.metric("📈 Média de Chegada", f"{media_final:.2f}")

    st.markdown("---")

    # --- GRÁFICOS ---
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
        st.plotly_chart(fig_pie, use_container_width=True)

    with g2:
        st.subheader("Desempenho Anual")
        standings_piloto = data['driver_standings'][data['driver_standings']['driverId'] == id_piloto]
        # Pega a última corrida de cada ano para saber a posição final
        races_com_standings = data['races'].merge(standings_piloto, on='raceId')
        pos_final_ano = races_com_standings.loc[races_com_standings.groupby('year')['round'].idxmax()]
        
        fig_champ = px.line(pos_final_ano, x='year', y='position', markers=True, 
                            title="Posição Final no Campeonato por Ano",
                            labels={'year': 'Temporada', 'position': 'Posição Final'},
                            color_discrete_sequence=[F1_BLACK])
        fig_champ.update_yaxes(autorange="reversed") # Posição 1 fica no topo
        st.plotly_chart(fig_champ, use_container_width=True)
    
    st.markdown("---")

    g3, g4 = st.columns(2)
    with g3:
        st.subheader("Maiores Palcos (Vitórias por Circuito)")
        vitorias_circuito = res_piloto[res_piloto['position'] == 1]['name_x'].value_counts().nlargest(10)
        fig_circ = px.bar(vitorias_circuito, y=vitorias_circuito.index, x=vitorias_circuito.values, orientation='h',
                           color_discrete_sequence=[F1_RED], text=vitorias_circuito.values)
        fig_circ.update_layout(xaxis_title="Número de Vitórias", yaxis_title="Circuito", yaxis={'categoryorder':'total ascending'})
        st.plotly_chart(fig_circ, use_container_width=True)

    with g4:
        st.subheader("Análise de Confiabilidade")
        dnf_reasons = res_piloto[res_piloto['position'].isna()]['status'].value_counts().nlargest(10)
        fig_dnf = px.bar(dnf_reasons, x=dnf_reasons.values, y=dnf_reasons.index, orientation='h',
                          color_discrete_sequence=[F1_GREY], text=dnf_reasons.values)
        fig_dnf.update_layout(yaxis={'categoryorder':'total ascending'}, yaxis_title="", xaxis_title="Ocorrências")
        st.plotly_chart(fig_dnf, use_container_width=True)
        
    st.markdown("---")
    st.subheader("Grid de Largada vs. Resultado Final (Carreira)")
    grid_final_piloto = res_piloto[['grid', 'position']].dropna()
    grid_final_piloto = grid_final_piloto[(grid_final_piloto['grid'] > 0) & (grid_final_piloto['position'] > 0)]
    fig_grid_final = px.scatter(grid_final_piloto, x='grid', y='position',
                                labels={'grid': 'Grid de Largada', 'position': 'Posição Final'},
                                trendline='ols', trendline_color_override=F1_RED,
                                color_discrete_sequence=[F1_BLACK],
                                title=f"Correlação entre largar e chegar ({len(grid_final_piloto)} corridas)")
    st.plotly_chart(fig_grid_final, use_container_width=True)

def render_analise_construtores(data):
    st.title("🔧 Análise de Construtores")
    construtor_nome = st.selectbox("Selecione um Construtor", options=data['constructors'].sort_values('name')['name'], index=None)
    
    if construtor_nome:
        construtor_info = data['constructors'][data['constructors']['name'] == construtor_nome].iloc[0]
        id_construtor = construtor_info['constructorId']
        
        results_construtor = data['results_full'][data['results_full']['constructorId'] == id_construtor]
        
        st.header(construtor_nome)

        # --- Lógica para Campeonatos ---
        standings_construtor = data['constructor_standings'][data['constructor_standings']['constructorId'] == id_construtor]
        campeonatos = 0
        if not standings_construtor.empty:
            anos_disputados = data['races'][data['races']['raceId'].isin(standings_construtor['raceId'])]['year'].unique()
            for year in anos_disputados:
                races_ano = data['races'][data['races']['year'] == year]
                if races_ano.empty: continue
                ultima_corrida_ano = races_ano['raceId'].max()
                pos_final = data['constructor_standings'][(data['constructor_standings']['raceId'] == ultima_corrida_ano) & (data['constructor_standings']['position'] == 1)]
                if not pos_final.empty and pos_final['constructorId'].iloc[0] == id_construtor:
                    campeonatos += 1
        
        ### NOVOS CARDS ###
        total_entradas = len(results_construtor)
        total_dnfs = results_construtor['position'].isna().sum()
        confiabilidade = ((total_entradas - total_dnfs) / total_entradas * 100) if total_entradas > 0 else 0

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("🏆 Campeonatos", campeonatos)
        c2.metric("🌍 Nacionalidade", construtor_info['nationality'])
        c3.metric("💯 Pontos por Corrida (Média)", f"{results_construtor['points'].sum() / results_construtor['raceId'].nunique():.2f}")
        c4.metric("🔧 Confiabilidade", f"{confiabilidade:.2f}%")
        st.divider()

        ### NOVOS GRÁFICOS ###
        g1, g2 = st.columns(2)
        with g1:
            st.subheader("Pontos por Temporada")
            pontos_ano = results_construtor.groupby('year')['points'].sum().reset_index()
            fig_pontos = px.bar(pontos_ano, x='year', y='points', color_discrete_sequence=[F1_GREY])
            st.plotly_chart(fig_pontos, use_container_width=True)
            
        with g2:
            st.subheader("Motivos de Abandono (DNF)")
            dnf_reasons = results_construtor[results_construtor['position'].isna()]['status'].value_counts().nlargest(10)
            fig_dnf = px.bar(dnf_reasons, x=dnf_reasons.values, y=dnf_reasons.index, orientation='h', color_discrete_sequence=[F1_RED])
            fig_dnf.update_layout(yaxis={'categoryorder':'total ascending'}, yaxis_title="", xaxis_title="Ocorrências")
            st.plotly_chart(fig_dnf, use_container_width=True)

        st.subheader("Comparativo de Pilotos da Equipe por Temporada")
        pontos_piloto_ano = results_construtor.groupby(['year', 'driver_name'])['points'].sum().reset_index()
        fig_pilotos = px.bar(pontos_piloto_ano, x='year', y='points', color='driver_name', 
                             title="Pontos por Piloto a Cada Temporada", color_discrete_sequence=px.colors.qualitative.Plotly)
        st.plotly_chart(fig_pilotos, use_container_width=True)

def render_h2h(data):
    st.title("⚔️ Head-to-Head")
    
    col1, col2 = st.columns(2)
    drivers_sorted = data['drivers'].sort_values('surname')['driver_name']
    piloto1_nome = col1.selectbox("Selecione o Piloto 1", options=drivers_sorted, index=None)
    piloto2_nome = col2.selectbox("Selecione o Piloto 2", options=drivers_sorted, index=None)

    if piloto1_nome and piloto2_nome and piloto1_nome != piloto2_nome:
        id1 = data['drivers'][data['drivers']['driver_name'] == piloto1_nome]['driverId'].iloc[0]
        id2 = data['drivers'][data['drivers']['driver_name'] == piloto2_nome]['driverId'].iloc[0]
        
        res1 = data['results'][data['results']['driverId'] == id1]
        res2 = data['results'][data['results']['driverId'] == id2]
        
        res_comum = res1.merge(res2, on='raceId', suffixes=('_p1', '_p2'))
        res_comum.dropna(subset=['position_p1', 'position_p2'], inplace=True)
        
        vantagem_corrida_p1 = (res_comum['position_p1'] < res_comum['position_p2']).sum()
        vantagem_corrida_p2 = (res_comum['position_p2'] < res_comum['position_p1']).sum()
        
        st.subheader("Confronto Direto em Corrida")
        fig = go.Figure(go.Bar(
            x=[vantagem_corrida_p1, vantagem_corrida_p2],
            y=[piloto1_nome, piloto2_nome],
            orientation='h', text=[vantagem_corrida_p1, vantagem_corrida_p2],
            marker_color=[F1_RED, F1_GREY]
        ))
        fig.update_layout(title_text=f"Vezes que um terminou à frente do outro ({len(res_comum)} corridas juntos)")
        st.plotly_chart(fig, use_container_width=True)

def render_hall_da_fama(data):
    st.title("🏆 Hall da Fama")
    
    # Cálculos para os rankings
    vitorias_pilotos = data['results_full'][data['results_full']['position'] == 1]['driver_name'].value_counts().nlargest(15)
    podios_pilotos = data['results_full'][data['results_full']['position'].isin([1,2,3])]['driver_name'].value_counts().nlargest(15)
    poles_pilotos = data['qualifying'][data['qualifying']['position'] == 1].merge(data['drivers'], on='driverId')['driver_name'].value_counts().nlargest(15)
    vitorias_constr = data['results_full'][data['results_full']['position'] == 1]['name_y'].value_counts().nlargest(15)

    tab_vit, tab_pod, tab_pol, tab_con = st.tabs(["🥇 Vitórias", "🍾 Pódios", "⏱️ Poles", "🏎️ Construtores"])

    with tab_vit:
        fig = px.bar(vitorias_pilotos, x=vitorias_pilotos.values, y=vitorias_pilotos.index, orientation='h', color_discrete_sequence=[F1_RED])
        fig.update_layout(title="Top 15 Pilotos com Mais Vitórias", yaxis={'categoryorder':'total ascending'}, xaxis_title="Total", yaxis_title="")
        st.plotly_chart(fig, use_container_width=True)
    with tab_pod:
        fig = px.bar(podios_pilotos, x=podios_pilotos.values, y=podios_pilotos.index, orientation='h', color_discrete_sequence=[F1_GREY])
        fig.update_layout(title="Top 15 Pilotos com Mais Pódios", yaxis={'categoryorder':'total ascending'}, xaxis_title="Total", yaxis_title="")
        st.plotly_chart(fig, use_container_width=True)
    with tab_pol:
        fig = px.bar(poles_pilotos, x=poles_pilotos.values, y=poles_pilotos.index, orientation='h', color_discrete_sequence=[F1_BLACK])
        fig.update_layout(title="Top 15 Pilotos com Mais Poles", yaxis={'categoryorder':'total ascending'}, xaxis_title="Total", yaxis_title="")
        st.plotly_chart(fig, use_container_width=True)
    with tab_con:
        fig = px.bar(vitorias_constr, x=vitorias_constr.values, y=vitorias_constr.index, orientation='h', color_discrete_sequence=px.colors.qualitative.Plotly)
        fig.update_layout(title="Top 15 Construtores com Mais Vitórias", yaxis={'categoryorder':'total ascending'}, xaxis_title="Total", yaxis_title="")
        st.plotly_chart(fig, use_container_width=True)

def render_analise_circuitos(data):
    st.title("🛣️ Análise de Circuitos")
    circuito_nome = st.selectbox("Selecione um Circuito", options=data['circuits'].sort_values('name')['name'], index=None)
    
    if circuito_nome:
        circuito_info = data['circuits'][data['circuits']['name'] == circuito_nome].iloc[0]
        id_circuito = circuito_info['circuitId']
        
        races_circuito = data['races'][data['races']['circuitId'] == id_circuito]
        results_circuito = data['results_full'][data['results_full']['raceId'].isin(races_circuito['raceId'])]
        
        st.header(circuito_nome)
        
        ### NOVOS CARDS ###
        # Lap Record
        lap_times_circuito = data['lap_times'][data['lap_times']['raceId'].isin(races_circuito['raceId'])]
        if not lap_times_circuito.empty:
            lap_record = lap_times_circuito.loc[lap_times_circuito['milliseconds'].idxmin()]
            piloto_record = data['drivers'][data['drivers']['driverId'] == lap_record['driverId']]['driver_name'].iloc[0]
            tempo_record = pd.to_datetime(lap_record['time'], format='%M:%S.%f').strftime('%M:%S.%f')[:-3]
        else:
            piloto_record, tempo_record = "N/A", "N/A"

        dnf_comum = results_circuito[results_circuito['position'].isna()]['status'].value_counts().nlargest(1).index[0]

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("🌍 País", circuito_info['country'])
        c2.metric("📍 Localização", circuito_info['location'])
        c3.metric("⏱️ Recorde da Pista", f"{piloto_record} ({tempo_record})")
        c4.metric("💥 Abandono Mais Comum", dnf_comum)
        st.divider()

        ### NOVOS GRÁFICOS ###
        g1, g2 = st.columns(2)
        with g1:
            st.subheader("Reis da Pista (Mais Vitórias)")
            maiores_vencedores = results_circuito[results_circuito['position'] == 1]['driver_name'].value_counts().nlargest(10)
            fig = px.bar(maiores_vencedores, y=maiores_vencedores.index, x=maiores_vencedores.values, orientation='h', color_discrete_sequence=[F1_RED])
            fig.update_layout(yaxis={'categoryorder':'total ascending'}, yaxis_title="", xaxis_title="Nº de Vitórias")
            st.plotly_chart(fig, use_container_width=True)
        with g2:
            st.subheader("De Onde Saem os Vencedores?")
            pos_grid_vencedores = results_circuito[(results_circuito['position'] == 1) & (results_circuito['grid'] > 0)]
            fig_grid = px.histogram(pos_grid_vencedores, x='grid', nbins=20, text_auto=True, color_discrete_sequence=[F1_BLACK])
            fig_grid.update_layout(xaxis_title="Posição de Largada", yaxis_title="Nº de Vitórias")
            st.plotly_chart(fig_grid, use_container_width=True)

        st.subheader("Distribuição de Posições Finais por Posição de Largada (Top 10 Grid)")
        grid_final_df = results_circuito[['grid', 'position']].dropna()
        grid_final_df = grid_final_df[grid_final_df['grid'].isin(range(1, 11))]
        fig_box = px.box(grid_final_df, x='grid', y='position', color_discrete_sequence=F1_PALETTE)
        fig_box.update_yaxes(autorange="reversed")
        fig_box.update_layout(xaxis_title="Posição de Largada", yaxis_title="Posição Final")
        st.plotly_chart(fig_box, use_container_width=True)

def render_pagina_gerenciamento(conn):
    st.title("🔩 Gerenciamento de Pilotos (CRUD)")
    st.info("Esta página cumpre o requisito de operações básicas de CRUD (Criar, Consultar, Atualizar, Excluir) em uma tabela.")

    # CORREÇÃO: Todas as colunas em minúsculas nas queries para corresponder ao PostgreSQL
    tab_create, tab_read, tab_update, tab_delete = st.tabs(["➕ Criar Piloto", "🔍 Consultar Pilotos", "🔄 Atualizar Piloto", "❌ Deletar Piloto"])

    with tab_read:
        st.subheader("Consultar Tabela de Pilotos")
        try:
            # Usando nomes de colunas em minúsculas
            pilotos_df = pd.read_sql_query("SELECT driverid, driverref, code, forename, surname, dob, nationality FROM drivers ORDER BY surname", conn)
            st.dataframe(pilotos_df, use_container_width=True)
        except Exception as e:
            st.error(f"Não foi possível consultar os pilotos: {e}")

    with tab_create:
        st.subheader("Adicionar Novo Piloto")
        with st.form("form_create", clear_on_submit=True):
            forename = st.text_input("Nome (Forename)")
            surname = st.text_input("Sobrenome (Surname)")
            driverref = st.text_input("Referência Única (ex: 'hamilton')")
            code = st.text_input("Código de 3 letras (ex: 'HAM')", max_chars=3)
            dob = st.date_input("Data de Nascimento")
            nationality = st.text_input("Nacionalidade")
            submitted = st.form_submit_button("Adicionar Piloto")
            if submitted:
                query = "INSERT INTO drivers (driverref, code, forename, surname, dob, nationality) VALUES (%s, %s, %s, %s, %s, %s)"
                if executar_comando_sql(conn, query, (driverref, code.upper(), forename, surname, dob, nationality)):
                    st.success(f"Piloto {forename} {surname} adicionado com sucesso!")

    with tab_update:
        st.subheader("Atualizar Nacionalidade de um Piloto")
        pilotos_df_update = pd.read_sql_query("SELECT driverid, forename || ' ' || surname as driver_name FROM drivers ORDER BY surname", conn)
        piloto_sel = st.selectbox("Selecione um piloto para atualizar", options=pilotos_df_update['driver_name'], index=None)
        if piloto_sel:
            id_piloto = int(pilotos_df_update[pilotos_df_update['driver_name'] == piloto_sel]['driverid'].iloc[0])
            nova_nac = st.text_input("Digite a nova nacionalidade", key=f"update_nac_{id_piloto}")
            if st.button("Atualizar Nacionalidade"):
                query = "UPDATE drivers SET nationality = %s WHERE driverid = %s"
                if executar_comando_sql(conn, query, (nova_nac, id_piloto)):
                    st.success(f"Nacionalidade do piloto {piloto_sel} atualizada com sucesso!")

    with tab_delete:
        st.subheader("Deletar um Piloto")
        st.warning("CUIDADO: Ação irreversível.", icon="⚠️")
        pilotos_df_del = pd.read_sql_query("SELECT driverid, forename || ' ' || surname as driver_name FROM drivers ORDER BY surname", conn)
        piloto_del = st.selectbox("Selecione um piloto para deletar", options=pilotos_df_del['driver_name'], index=None, key="del_sel")
        if piloto_del:
            id_piloto_del = int(pilotos_df_del[pilotos_df_del['driver_name'] == piloto_del]['driverid'].iloc[0])
            if st.button(f"DELETAR PERMANENTEMENTE {piloto_del}", type="primary"):
                query = "DELETE FROM drivers WHERE driverid = %s"
                if executar_comando_sql(conn, query, (id_piloto_del,)):
                    st.success(f"Piloto {piloto_del} deletado com sucesso!")
def main():
    with st.sidebar:
        st.image("f1_logo.png", width=300)
        app_page = option_menu(
            menu_title='F1 Super Analytics',
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
