import os
import sqlite3

# Configurações do PostgreSQL (definidas via variáveis de ambiente)
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_NAME = os.getenv("DB_NAME", "sismo_db")
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASS = os.getenv("DB_PASS", "postgres")
DB_CONNECT_TIMEOUT = int(os.getenv("DB_CONNECT_TIMEOUT", "3"))

# Caminho do SQLite (fallback quando o PostgreSQL não está disponível)
DB_DIR = os.path.dirname(os.path.abspath(__file__))
SQLITE_PATH = os.getenv("SQLITE_PATH", os.path.join(DB_DIR, "sismo.db"))

# Backend escolhido UMA vez em init_db(). Evita tentar o Postgres
# (e esperar o timeout) a cada requisição quando ele está fora do ar.
_BACKEND = None  # "postgres" | "sqlite"


def _conectar_postgres():
    import psycopg2
    from psycopg2.extras import RealDictCursor
    return psycopg2.connect(
        host=DB_HOST,
        port=DB_PORT,
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASS,
        connect_timeout=DB_CONNECT_TIMEOUT,
        cursor_factory=RealDictCursor,
    )


def _conectar_sqlite():
    conn = sqlite3.connect(SQLITE_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _detectar_backend() -> str:
    if os.getenv("DB_BACKEND", "").lower() == "sqlite":
        return "sqlite"
    try:
        _conectar_postgres().close()
        return "postgres"
    except Exception:
        return "sqlite"


def get_db_connection():
    """Retorna uma conexão com o backend definido na inicialização."""
    global _BACKEND
    if _BACKEND is None:
        _BACKEND = _detectar_backend()
    return _conectar_postgres() if _BACKEND == "postgres" else _conectar_sqlite()


def is_using_postgres() -> bool:
    return _BACKEND == "postgres"


def nome_backend() -> str:
    return "PostgreSQL" if is_using_postgres() else "SQLite"


def ph() -> str:
    """Placeholder de parâmetro SQL do backend atual (%s ou ?)."""
    return "%s" if is_using_postgres() else "?"


# ------------------------------------------------------------------
# Esquema
# ------------------------------------------------------------------
# A geometria das falhas é guardada como GeoJSON (texto) para que o
# fallback SQLite funcione igual ao PostgreSQL. Os cálculos espaciais
# são feitos em Python (shapely/pyproj) a partir da Fase 3.

_TIPOS = {
    "postgres": {"pk": "SERIAL PRIMARY KEY", "real": "DOUBLE PRECISION", "ts": "TIMESTAMP"},
    "sqlite": {"pk": "INTEGER PRIMARY KEY AUTOINCREMENT", "real": "REAL", "ts": "TIMESTAMP"},
}


def _ddl(backend: str):
    t = _TIPOS[backend]
    return [
        f"""
        CREATE TABLE IF NOT EXISTS epicentros (
            id {t['pk']},
            id_externo TEXT NOT NULL UNIQUE,
            fonte TEXT NOT NULL,
            data_hora {t['ts']} NOT NULL,
            lat {t['real']} NOT NULL,
            lon {t['real']} NOT NULL,
            profundidade_km {t['real']},
            magnitude {t['real']},
            tipo_magnitude TEXT,
            local TEXT,
            importado_em {t['ts']} DEFAULT CURRENT_TIMESTAMP
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_epicentros_lat_lon ON epicentros (lat, lon)",
        "CREATE INDEX IF NOT EXISTS idx_epicentros_data ON epicentros (data_hora)",
        f"""
        CREATE TABLE IF NOT EXISTS falhas (
            id {t['pk']},
            id_externo TEXT UNIQUE,
            nome TEXT,
            tipo TEXT,
            fonte TEXT NOT NULL,
            geometria_geojson TEXT NOT NULL,
            min_lat {t['real']} NOT NULL,
            min_lon {t['real']} NOT NULL,
            max_lat {t['real']} NOT NULL,
            max_lon {t['real']} NOT NULL,
            atributos_json TEXT,
            importado_em {t['ts']} DEFAULT CURRENT_TIMESTAMP
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_falhas_bbox ON falhas (min_lat, max_lat, min_lon, max_lon)",
        f"""
        CREATE TABLE IF NOT EXISTS analises (
            id {t['pk']},
            nome TEXT,
            parametros_json TEXT NOT NULL,
            resultado_json TEXT NOT NULL,
            criado_em {t['ts']} DEFAULT CURRENT_TIMESTAMP
        )
        """,
    ]


def init_db():
    """Escolhe o backend e cria as tabelas se não existirem."""
    global _BACKEND
    _BACKEND = _detectar_backend()

    conn = get_db_connection()
    cursor = conn.cursor()
    for comando in _ddl(_BACKEND):
        cursor.execute(comando)
    conn.commit()
    conn.close()

    if is_using_postgres():
        print("[Banco de Dados] Conectado ao PostgreSQL.")
    else:
        print(f"[Banco de Dados] PostgreSQL indisponível. Usando SQLite em {SQLITE_PATH}.")
