import pandas as pd
import psycopg2
import os

SUPABASE_CONN_STRING = "postgresql://postgres.efryrgpkwwppfgumlaqm:Hebertes23@aws-1-sa-east-1.pooler.supabase.com:5432/postgres"
DATA_PATH = r"C:\Users\heber\OneDrive\Documentos\Banco Dados\Projeto_F1_SBD\archive"

def conectar_db():
    """Cria e retorna uma conexão com o banco de dados Supabase."""
    try:
        conn = psycopg2.connect(SUPABASE_CONN_STRING)
        print("Conexão com o Supabase bem-sucedida!")
        return conn
    except psycopg2.Error as e:
        print(f"Erro ao conectar ao banco de dados Supabase: {e}")
        return None

def importar_dados(conn):
    """Lê, transforma e carrega os dados dos CSVs para o banco de dados."""
    cursor = conn.cursor()

    try:
        print("\nImportando status...")
        df = pd.read_csv(os.path.join(DATA_PATH, 'status.csv'))
        df = df[['statusId', 'status']]
        df.rename(columns={'statusId': 'id_status'}, inplace=True)
        for index, row in df.iterrows():
            cursor.execute("INSERT INTO tbl_status_resultado (id_status, status) VALUES (%s, %s) ON CONFLICT (id_status) DO NOTHING", tuple(row))
        print(f"-> {len(df)} registros de status processados.")

        print("\nImportando circuitos...")
        df = pd.read_csv(os.path.join(DATA_PATH, 'circuits.csv'))
        df = df[['circuitId', 'circuitRef', 'name', 'location', 'country']]
        df.rename(columns={'circuitId': 'id_circuito', 'circuitRef': 'ref_circuito', 'name': 'nome', 'location': 'cidade', 'country': 'pais'}, inplace=True)
        for index, row in df.iterrows():
            cursor.execute("INSERT INTO tbl_circuitos (id_circuito, ref_circuito, nome, cidade, pais) VALUES (%s, %s, %s, %s, %s) ON CONFLICT (id_circuito) DO NOTHING", tuple(row))
        print(f"-> {len(df)} registros de circuitos processados.")

        print("\nImportando pilotos...")
        df = pd.read_csv(os.path.join(DATA_PATH, 'drivers.csv'))
        df = df[['driverId', 'driverRef', 'number', 'code', 'forename', 'surname', 'dob', 'nationality']]
        df.rename(columns={'driverId': 'id_piloto', 'driverRef': 'ref_piloto', 'number': 'numero', 'code': 'codigo', 'forename': 'nome', 'surname': 'sobrenome', 'dob': 'data_nascimento', 'nationality': 'nacionalidade'}, inplace=True)
        for index, row in df.iterrows():
            numero_piloto = None if (pd.isna(row['numero']) or str(row['numero']) == r'\N') else int(row['numero'])
            codigo_piloto = None if (pd.isna(row['codigo']) or str(row['codigo']) == r'\N') else str(row['codigo'])
            
            cursor.execute(
                "INSERT INTO tbl_pilotos (id_piloto, ref_piloto, numero, codigo, nome, sobrenome, data_nascimento, nacionalidade) VALUES (%s, %s, %s, %s, %s, %s, %s, %s) ON CONFLICT (id_piloto) DO NOTHING",
                (row['id_piloto'], row['ref_piloto'], numero_piloto, codigo_piloto, row['nome'], row['sobrenome'], row['data_nascimento'], row['nacionalidade'])
            )
        print(f"-> {len(df)} registros de pilotos processados.")
        
        print("\nImportando construtores (equipes)...")
        df = pd.read_csv(os.path.join(DATA_PATH, 'constructors.csv'))
        df = df[['constructorId', 'constructorRef', 'name', 'nationality']]
        df.rename(columns={'constructorId': 'id_construtor', 'constructorRef': 'ref_construtor', 'name': 'nome', 'nationality': 'nacionalidade'}, inplace=True)
        for index, row in df.iterrows():
            cursor.execute("INSERT INTO tbl_construtores (id_construtor, ref_construtor, nome, nacionalidade) VALUES (%s, %s, %s, %s) ON CONFLICT (id_construtor) DO NOTHING", tuple(row))
        print(f"-> {len(df)} registros de construtores processados.")

        print("\nImportando corridas...")
        df = pd.read_csv(os.path.join(DATA_PATH, 'races.csv'))
        df = df[['raceId', 'year', 'round', 'circuitId', 'name', 'date']]
        df.rename(columns={'raceId': 'id_corrida', 'year': 'ano', 'round': 'rodada', 'circuitId': 'id_circuito_fk', 'name': 'nome_gp', 'date': 'data_corrida'}, inplace=True)
        for index, row in df.iterrows():
            cursor.execute("INSERT INTO tbl_corridas (id_corrida, ano, rodada, id_circuito_fk, nome_gp, data_corrida) VALUES (%s, %s, %s, %s, %s, %s) ON CONFLICT (id_corrida) DO NOTHING", tuple(row))
        print(f"-> {len(df)} registros de corridas processados.")

        
        print("\nImportando resultados... (Isso pode demorar alguns minutos)")
        df = pd.read_csv(os.path.join(DATA_PATH, 'results.csv'))
        df = df[['resultId', 'raceId', 'driverId', 'constructorId', 'grid', 'position', 'points', 'laps', 'statusId']]
        df.rename(columns={'resultId': 'id_resultado', 'raceId': 'id_corrida_fk', 'driverId': 'id_piloto_fk', 'constructorId': 'id_construtor_fk', 'grid': 'posicao_grid', 'position': 'posicao_final', 'points': 'pontos', 'laps': 'voltas', 'statusId': 'id_status_fk'}, inplace=True)
        for index, row in df.iterrows():
            posicao_final = None if (pd.isna(row['posicao_final']) or str(row['posicao_final']) == r'\N') else int(row['posicao_final'])
            
            cursor.execute(
                "INSERT INTO tbl_resultados (id_resultado, id_corrida_fk, id_piloto_fk, id_construtor_fk, posicao_grid, posicao_final, pontos, voltas, id_status_fk) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) ON CONFLICT (id_resultado) DO NOTHING", 
                (row['id_resultado'], row['id_corrida_fk'], row['id_piloto_fk'], row['id_construtor_fk'], row['posicao_grid'], posicao_final, row['pontos'], row['voltas'], row['id_status_fk'])
            )
        print(f"-> {len(df)} registros de resultados processados.")

        conn.commit()
        print("\n IMPORTAÇÃO CONCLUÍDA! Todos os dados foram carregados no banco de dados.")

    except (Exception, psycopg2.Error) as error:
        print(f"❌ Um erro ocorreu durante a importação: {error}")
        conn.rollback()
    finally:
        if cursor:
            cursor.close()

if __name__ == "__main__":
    conn = conectar_db()
    if conn:
        importar_dados(conn)
        conn.close()
        print("\nConexão com o banco de dados foi fechada.")
