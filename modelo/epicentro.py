from typing import Dict, List, Optional, Tuple

from db.database import get_db_connection, ph

COLUNAS = ("id_externo", "fonte", "data_hora", "lat", "lon",
           "profundidade_km", "magnitude", "tipo_magnitude", "local")


def _sql(comando: str) -> str:
    """Escreve as consultas com '?' e adapta para o placeholder do backend."""
    return comando.replace("?", ph())


def _filtros(bbox: Optional[Dict], min_mag: Optional[float],
             inicio: Optional[str], fim: Optional[str], fontes: Optional[List[str]] = None) -> Tuple[str, list]:
    condicoes, valores = [], []
    if fontes:
        condicoes.append(f"fonte IN ({', '.join('?' for _ in fontes)})")
        valores += list(fontes)
    if bbox:
        condicoes.append("lat BETWEEN ? AND ? AND lon BETWEEN ? AND ?")
        valores += [bbox["sul"], bbox["norte"], bbox["oeste"], bbox["leste"]]
    if min_mag is not None:
        condicoes.append("magnitude >= ?")
        valores.append(min_mag)
    if inicio:
        condicoes.append("data_hora >= ?")
        valores.append(f"{inicio} 00:00:00")
    if fim:
        condicoes.append("data_hora <= ?")
        valores.append(f"{fim} 23:59:59")
    where = f"WHERE {' AND '.join(condicoes)}" if condicoes else ""
    return where, valores


class EpicentroModelo:
    """Persistência e consulta dos epicentros."""

    @staticmethod
    def salvar_lote(registros: List[Dict]) -> Dict[str, int]:
        """Insere ou atualiza (pelo id_externo). Retorna quantos eram novos."""
        if not registros:
            return {"novos": 0, "atualizados": 0}

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) AS total FROM epicentros")
        antes = _valor(cursor.fetchone())

        colunas = ", ".join(COLUNAS)
        marcadores = ", ".join("?" for _ in COLUNAS)
        atualizacao = ", ".join(f"{c} = excluded.{c}" for c in COLUNAS if c != "id_externo")
        # ON CONFLICT ... DO UPDATE funciona no PostgreSQL e no SQLite (>= 3.24)
        comando = _sql(
            f"INSERT INTO epicentros ({colunas}) VALUES ({marcadores}) "
            f"ON CONFLICT (id_externo) DO UPDATE SET {atualizacao}"
        )
        cursor.executemany(comando, [tuple(r[c] for c in COLUNAS) for r in registros])

        cursor.execute("SELECT COUNT(*) AS total FROM epicentros")
        novos = _valor(cursor.fetchone()) - antes
        conn.commit()
        conn.close()
        return {"novos": novos, "atualizados": len(registros) - novos}

    @staticmethod
    def listar(bbox: Optional[Dict] = None, min_mag: Optional[float] = None,
               inicio: Optional[str] = None, fim: Optional[str] = None,
               limite: int = 5000, fontes: Optional[List[str]] = None) -> Dict:
        """Epicentros filtrados, maiores magnitudes primeiro. Inclui o total sem limite."""
        where, valores = _filtros(bbox, min_mag, inicio, fim, fontes)
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute(_sql(f"SELECT COUNT(*) AS total FROM epicentros {where}"), valores)
        total = _valor(cursor.fetchone())

        cursor.execute(
            _sql(f"SELECT id, {', '.join(COLUNAS)} FROM epicentros {where} "
                 f"ORDER BY magnitude DESC, data_hora DESC LIMIT ?"),
            valores + [limite],
        )
        linhas = [dict(l) for l in cursor.fetchall()]
        conn.close()
        for l in linhas:
            l["data_hora"] = str(l["data_hora"])
        return {"total": total, "epicentros": linhas}

    @staticmethod
    def fontes(bbox: Optional[Dict] = None) -> List[Dict]:
        """Quantidade de epicentros por catálogo (na área, se dada)."""
        where, valores = _filtros(bbox, None, None, None)
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(_sql(f"SELECT fonte, COUNT(*) AS total FROM epicentros {where} GROUP BY fonte ORDER BY total DESC"),
                       valores)
        linhas = [dict(l) for l in cursor.fetchall()]
        conn.close()
        return linhas

    @staticmethod
    def resumo() -> Dict:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT COUNT(*) AS total, MIN(magnitude) AS mag_min, MAX(magnitude) AS mag_max, "
            "MIN(data_hora) AS inicio, MAX(data_hora) AS fim FROM epicentros"
        )
        linha = dict(cursor.fetchone())
        conn.close()
        for chave in ("inicio", "fim"):
            if linha[chave] is not None:
                linha[chave] = str(linha[chave])[:10]
        return linha

    @staticmethod
    def apagar_todos() -> int:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM epicentros")
        apagados = cursor.rowcount
        conn.commit()
        conn.close()
        return apagados


def _valor(linha):
    return linha["total"] if hasattr(linha, "keys") else linha[0]
