import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from streamlit_option_menu import option_menu
import psycopg2

# --- CONFIGURAÇÃO DA PÁGINA E ESTILO ---
st.set_page_config(layout="wide", page_title="F1 Super Analytics Pro", page_icon="f1.png")
F1_PALETTE = ["#E10600", "#FF8700", "#00A000", "#7F7F7F", "#15151E", "#B1B1B8", "#FFFFFF"]
F1_RED = F1_PALETTE[0]
F1_BLACK = F1_PALETTE[4]
F1_GREY = F1_PALETTE[3]

# --- FUNÇÕES DE BANCO DE DADOS ---
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
    ano_selecionado = st.selectbox("Selecione a Temporada", options=sorted(data['races']['year'].unique(), reverse=True))
    
    races_ano = data['races'][data['races']['year'] == ano_selecionado]
    race_ids_ano = races_ano['raceId']
    
    results_full_ano = data['results_full'][data['results_full']['raceId'].isin(race_ids_ano)]
    
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("🏁 Corridas no Ano", races_ano['raceId'].nunique())
    col2.metric("🏆 Vencedores Diferentes", results_full_ano[results_full_ano['position'] == 1]['driverId'].nunique())
    poles_ano = data['qualifying'][(data['qualifying']['raceId'].isin(race_ids_ano)) & (data['qualifying']['position'] == 1)]
    col3.metric("⏱️ Pole Sitters Diferentes", poles_ano['driverId'].nunique())
    podios_constr = results_full_ano[results_full_ano['position'].isin([1,2,3])]['name_y'].value_counts().nlargest(1)
    col4.metric("🍾 Equipe com Mais Pódios", f"{podios_constr.index[0]} ({podios_constr.values[0]})")
    st.divider()

    g1, g2 = st.columns(2)
    with g1:
        st.subheader("Circuitos da Temporada")
        circuits_ano = races_ano.merge(data['circuits'], on='circuitId')
        fig_map = px.scatter_geo(circuits_ano, lat='lat', lon='lng', hover_name='name_x',
                                 projection="natural earth", color_discrete_sequence=[F1_RED])
        st.plotly_chart(fig_map, use_container_width=True)
    with g2:
        st.subheader("Resultados das Corridas")
        status_counts = results_full_ano['status'].value_counts().nlargest(7)
        fig_status = px.pie(status_counts, values=status_counts.values, names=status_counts.index, 
                            hole=0.4, color_discrete_sequence=px.colors.sequential.Reds_r)
        st.plotly_chart(fig_status, use_container_width=True)

def render_analise_pilotos(data):
    st.title("🧑‍🚀 Análise de Pilotos")
    piloto_nome = st.selectbox("Selecione um Piloto", options=data['drivers'].sort_values('surname')['driver_name'], index=None)
    
    if piloto_nome:
        piloto_info = data['drivers'][data['drivers']['driver_name'] == piloto_nome].iloc[0]
        id_piloto = piloto_info['driverId']
        
        res_piloto = data['results_full'][data['results_full']['driverId'] == id_piloto]
        
        st.header(piloto_nome)
        
        ### NOVOS CARDS ###
        total_corridas = res_piloto['raceId'].nunique()
        total_vitorias = (res_piloto['position'] == 1).sum()
        total_poles = (data['qualifying'][data['qualifying']['driverId'] == id_piloto]['position'] == 1).sum()

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("🏆 % de Vitórias", f"{(total_vitorias / total_corridas * 100):.2f}%" if total_corridas > 0 else "0%")
        c2.metric(" Pole Position", total_poles)
        c3.metric("🏎️ Total de Voltas", f"{res_piloto['laps'].sum():,}")
        c4.metric("💥 Total de Abandonos (DNF)", (res_piloto['position'].isna()).sum())
        st.divider()

        ### NOVOS GRÁFICOS ###
        g1, g2 = st.columns(2)
        with g1:
            st.subheader("Vitórias por Circuito")
            vitorias_circuito = res_piloto[res_piloto['position'] == 1]['name_x'].value_counts().nlargest(10)
            fig_circ = px.bar(vitorias_circuito, y=vitorias_circuito.index, x=vitorias_circuito.values, orientation='h', color_discrete_sequence=[F1_RED])
            fig_circ.update_layout(xaxis_title="Nº de Vitórias", yaxis_title="Circuito", yaxis={'categoryorder':'total ascending'})
            st.plotly_chart(fig_circ, use_container_width=True)
        with g2:
            st.subheader("Posição no Campeonato por Ano")
            standings_piloto = data['driver_standings'][data['driver_standings']['driverId'] == id_piloto]
            pos_final_ano = standings_piloto.loc[standings_piloto.groupby('raceId')['raceId'].idxmax()]
            pos_final_ano = pos_final_ano.merge(data['races'], on='raceId')
            fig_champ = px.line(pos_final_ano, x='year', y='position', markers=True, color_discrete_sequence=[F1_BLACK])
            fig_champ.update_yaxes(autorange="reversed")
            fig_champ.update_layout(yaxis_title="Posição Final")
            st.plotly_chart(fig_champ, use_container_width=True)


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
