"""Registro das importações (área consultada, filtros e quantidade recebida)."""
import json
import math
from typing import Dict, List, Optional

import shapely

from db.database import get_db_connection, ph


def _caixa_area_igual(b: Dict):
    """Caixa lat/lon numa projeção de áreas iguais (x = lon, y = sen(lat)).

    Para caixas alinhadas a meridianos/paralelos isso dá a proporção de área exata na esfera.
    """
    return shapely.box(b["oeste"], math.sin(math.radians(b["sul"])),
                       b["leste"], math.sin(math.radians(b["norte"])))


class ImportacaoModelo:

    @staticmethod
    def registrar(tipo: str, fonte: str, bbox: Dict, parametros: Optional[Dict], recebidos: int) -> None:
        conn = get_db_connection()
        cursor = conn.cursor()
        valores = (tipo, fonte, bbox["sul"], bbox["oeste"], bbox["norte"], bbox["leste"],
                   json.dumps(parametros or {}), recebidos)
        marcadores = ", ".join(ph() for _ in valores)
        cursor.execute(
            f"INSERT INTO importacoes (tipo, fonte, sul, oeste, norte, leste, parametros_json, recebidos) "
            f"VALUES ({marcadores})", valores)
        conn.commit()
        conn.close()

    @staticmethod
    def listar(tipo: Optional[str] = None, limite: int = 50) -> List[Dict]:
        conn = get_db_connection()
        cursor = conn.cursor()
        if tipo:
            cursor.execute(f"SELECT * FROM importacoes WHERE tipo = {ph()} ORDER BY id DESC LIMIT {ph()}", (tipo, limite))
        else:
            cursor.execute(f"SELECT * FROM importacoes ORDER BY id DESC LIMIT {ph()}", (limite,))
        linhas = [dict(l) for l in cursor.fetchall()]
        conn.close()
        for l in linhas:
            l["parametros"] = json.loads(l.pop("parametros_json") or "{}")
            l["criado_em"] = str(l["criado_em"])
            l["bbox"] = {k: l.pop(k) for k in ("sul", "oeste", "norte", "leste")}
        return linhas

    @staticmethod
    def cobertura(tipo: str, bbox: Dict) -> Optional[float]:
        """Fração (0–1) da área `bbox` coberta pelas importações do `tipo`.

        None quando não há nenhuma importação registrada (dados antigos, de antes do registro).
        """
        importacoes = ImportacaoModelo.listar(tipo, limite=10_000)
        if not importacoes:
            return None
        uniao = shapely.union_all([_caixa_area_igual(i["bbox"]) for i in importacoes])
        area = _caixa_area_igual(bbox)
        return float(shapely.intersection(uniao, area).area / area.area) if area.area > 0 else None

    @staticmethod
    def area_importada(tipo: str, bbox_referencia: Optional[Dict] = None) -> Optional[Dict]:
        """Caixa que envolve as importações do `tipo` (só as que cruzam `bbox_referencia`, se dada)."""
        caixas = [i["bbox"] for i in ImportacaoModelo.listar(tipo, limite=10_000)]
        if bbox_referencia:
            r = bbox_referencia
            caixas = [b for b in caixas if b["sul"] <= r["norte"] and b["norte"] >= r["sul"]
                      and b["oeste"] <= r["leste"] and b["leste"] >= r["oeste"]]
        if not caixas:
            return None
        return {"sul": min(b["sul"] for b in caixas), "oeste": min(b["oeste"] for b in caixas),
                "norte": max(b["norte"] for b in caixas), "leste": max(b["leste"] for b in caixas)}
