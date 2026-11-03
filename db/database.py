import os
import sqlite3

# Configurações do PostgreSQL (podem ser definidas via variáveis de ambiente)
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_NAME = os.getenv("DB_NAME", "maps_db")
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASS = os.getenv("DB_PASS", "postgres")

# Caminho de fallback para SQLite se o PostgreSQL não estiver ativo
DB_DIR = os.path.dirname(os.path.abspath(__file__))
SQLITE_PATH = os.path.join(DB_DIR, 'maps.db')

IS_POSTGRES = False

def get_db_connection():
    """
    Retorna uma conexão ativa com o banco PostgreSQL.
    Caso o PostgreSQL não esteja rodando, faz fallback seguro para SQLite.
    """
    global IS_POSTGRES
    try:
        import psycopg2
        from psycopg2.extras import RealDictCursor
        conn = psycopg2.connect(
            host=DB_HOST,
            port=DB_PORT,
            dbname=DB_NAME,
            user=DB_USER,
            password=DB_PASS,
            cursor_factory=RealDictCursor
        )
        IS_POSTGRES = True
        return conn
    except Exception as pg_err:
        # Fallback para SQLite para a aplicação nunca quebrar
        IS_POSTGRES = False
        conn = sqlite3.connect(SQLITE_PATH)
        conn.row_factory = sqlite3.Row
        return conn

def is_using_postgres():
    return IS_POSTGRES

def init_db():
    """
    Cria as tabelas necessárias no PostgreSQL (ou SQLite).
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    if IS_POSTGRES:
        print("[Banco de Dados] Conectado com sucesso ao PostgreSQL!")
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS historico_rotas (
                id SERIAL PRIMARY KEY,
                origem_nome TEXT NOT NULL,
                origem_lat DOUBLE PRECISION NOT NULL,
                origem_lon DOUBLE PRECISION NOT NULL,
                destino_nome TEXT NOT NULL,
                destino_lat DOUBLE PRECISION NOT NULL,
                destino_lon DOUBLE PRECISION NOT NULL,
                distancia_km DOUBLE PRECISION NOT NULL,
                duracao_minutos DOUBLE PRECISION NOT NULL,
                criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        ''')
    else:
        print("[Banco de Dados] PostgreSQL indisponível. Usando fallback SQLite.")
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS historico_rotas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                origem_nome TEXT NOT NULL,
                origem_lat REAL NOT NULL,
                origem_lon REAL NOT NULL,
                destino_nome TEXT NOT NULL,
                destino_lat REAL NOT NULL,
                destino_lon REAL NOT NULL,
                distancia_km REAL NOT NULL,
                duracao_minutos REAL NOT NULL,
                criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        ''')

    conn.commit()
    conn.close()
