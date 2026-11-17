import json
import unicodedata
from typing import Dict, List, Optional

from db.database import get_db_connection, ph

COLUNAS = ("id_externo", "nome", "tipo", "fonte", "geometria_geojson",
           "min_lat", "min_lon", "max_lat", "max_lon", "atributos_json")

# Categoria pelo mecanismo principal (primeiro termo do tipo). Aceita termos do
# GEM (inglês) e de bases brasileiras (português).
CATEGORIAS = [
    ("normal", ("normal",)),
    ("reversa", ("reverse", "thrust", "subduction", "reversa", "inversa", "empurr", "cavalgamento")),
    ("transcorrente", ("dextral", "sinistral", "strike", "transform", "transcorr")),
    ("dorsal", ("spreading", "ridge", "dorsal")),
]


def _sem_acento(texto: str) -> str:
    return unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode().lower()


def categoria_falha(tipo: Optional[str]) -> str:
    """'normal' | 'reversa' | 'transcorrente' | 'dorsal' | 'outra'."""
    if not tipo:
        return "outra"
    texto = _sem_acento(tipo)
    # O mecanismo dominante é o que aparece primeiro (ex.: "Dextral-Reverse" = transcorrente)
    melhor, posicao = "outra", len(texto) + 1
    for categoria, termos in CATEGORIAS:
        for termo in termos:
            i = texto.find(termo)
            if i != -1 and i < posicao:
                melhor, posicao = categoria, i
    return melhor


def _sql(comando: str) -> str:
    return comando.replace("?", ph())


def _total(linha):
    return linha["total"] if hasattr(linha, "keys") else linha[0]


class FalhaModelo:

    @staticmethod
    def salvar_lote(registros: List[Dict]) -> Dict[str, int]:
        if not registros:
            return {"novos": 0, "atualizados": 0}
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) AS total FROM falhas")
        antes = _total(cursor.fetchone())

        colunas = ", ".join(COLUNAS)
        marcadores = ", ".join("?" for _ in COLUNAS)
        atualizacao = ", ".join(f"{c} = excluded.{c}" for c in COLUNAS if c != "id_externo")
        cursor.executemany(
            _sql(f"INSERT INTO falhas ({colunas}) VALUES ({marcadores}) "
                 f"ON CONFLICT (id_externo) DO UPDATE SET {atualizacao}"),
            [tuple(r[c] for c in COLUNAS) for r in registros],
        )
        cursor.execute("SELECT COUNT(*) AS total FROM falhas")
        novos = _total(cursor.fetchone()) - antes
        conn.commit()
        conn.close()
        return {"novos": novos, "atualizados": len(registros) - novos}

    @staticmethod
    def listar(bbox: Optional[Dict] = None, limite: int = 5000) -> Dict:
        """Falhas que cruzam a área, como FeatureCollection GeoJSON, + total."""
        where, valores = "", []
        if bbox:
            where = "WHERE min_lat <= ? AND max_lat >= ? AND min_lon <= ? AND max_lon >= ?"
            valores = [bbox["norte"], bbox["sul"], bbox["leste"], bbox["oeste"]]

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(_sql(f"SELECT COUNT(*) AS total FROM falhas {where}"), valores)
        total = _total(cursor.fetchone())
        # Falhas mais extensas primeiro, para que o limite corte as menores
        cursor.execute(
            _sql(f"SELECT id, nome, tipo, fonte, geometria_geojson, atributos_json FROM falhas {where} "
                 f"ORDER BY (max_lat - min_lat) + (max_lon - min_lon) DESC LIMIT ?"),
            valores + [limite],
        )
        linhas = cursor.fetchall()
        conn.close()

        features = []
        for l in linhas:
            l = dict(l)
            features.append({
                "type": "Feature",
                "id": l["id"],
                "geometry": json.loads(l["geometria_geojson"]),
                "properties": {
                    "id": l["id"], "nome": l["nome"], "tipo": l["tipo"], "fonte": l["fonte"],
                    "categoria": categoria_falha(l["tipo"]),
                    "atributos": json.loads(l["atributos_json"] or "{}"),
                },
            })
        return {"total": total, "falhas": {"type": "FeatureCollection", "features": features}}

    @staticmethod
    def fontes() -> List[Dict]:
        """Quantidade de falhas por fonte."""
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT fonte, COUNT(*) AS total FROM falhas GROUP BY fonte ORDER BY fonte")
        linhas = [dict(l) for l in cursor.fetchall()]
        conn.close()
        return linhas

    @staticmethod
    def apagar(fonte: Optional[str] = None) -> int:
        conn = get_db_connection()
        cursor = conn.cursor()
        if fonte:
            cursor.execute(_sql("DELETE FROM falhas WHERE fonte = ?"), (fonte,))
        else:
            cursor.execute("DELETE FROM falhas")
        apagadas = cursor.rowcount
        conn.commit()
        conn.close()
        return apagadas
