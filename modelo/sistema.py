import json
from typing import Dict, List

from db.database import get_db_connection, nome_backend, ph


class SistemaModelo:
    """Informações gerais do sistema e acesso às análises salvas."""

    @staticmethod
    def resumo() -> Dict:
        """Quantidade de registros em cada tabela e o banco em uso."""
        conn = get_db_connection()
        cursor = conn.cursor()
        contagens = {}
        for tabela in ("epicentros", "falhas", "analises"):
            cursor.execute(f"SELECT COUNT(*) AS total FROM {tabela}")
            linha = cursor.fetchone()
            contagens[tabela] = linha["total"] if hasattr(linha, "keys") else linha[0]
        conn.close()
        return {"banco": nome_backend(), "contagens": contagens}

    @staticmethod
    def listar_analises(limite: int = 20) -> List[Dict]:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            f"SELECT id, nome, parametros_json, criado_em FROM analises ORDER BY id DESC LIMIT {ph()}",
            (limite,),
        )
        linhas = cursor.fetchall()
        conn.close()

        analises = []
        for linha in linhas:
            item = dict(linha)
            item["parametros"] = json.loads(item.pop("parametros_json") or "{}")
            item["criado_em"] = str(item["criado_em"])
            analises.append(item)
        return analises

    @staticmethod
    def limpar_analises() -> None:
        conn = get_db_connection()
        conn.cursor().execute("DELETE FROM analises")
        conn.commit()
        conn.close()
