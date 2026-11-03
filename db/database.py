import sqlite3
import os

DB_DIR = os.path.dirname(os.path.abspath(__file__))
DATABASE_PATH = os.path.join(DB_DIR, 'maps.db')

def get_db_connection():
    """Retorna uma conexão ativa com o banco SQLite."""
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Cria a tabela de histórico de rotas se ela não existir."""
    conn = get_db_connection()
    cursor = conn.cursor()
    
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
        )
    ''')
    
    conn.commit()
    conn.close()
