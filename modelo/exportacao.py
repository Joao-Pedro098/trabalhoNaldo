"""Exportação de uma análise: CSV (Excel pt-BR), GeoJSON (QGIS) e JSON completo."""
import csv
import io
import json
import re
import unicodedata
from typing import Dict, List

from db.database import get_db_connection, ph

COLUNAS_CSV = [
    ("id_externo", "id_evento"), ("data_hora", "data_hora_utc"), ("lat", "latitude"), ("lon", "longitude"),
    ("magnitude", "magnitude"), ("profundidade_km", "profundidade_km"), ("dist_km", "distancia_falha_km"),
    ("falha_id", "falha_id"), ("falha_nome", "falha_nome"),
    ("ponto_falha_lat", "ponto_falha_lat"), ("ponto_falha_lon", "ponto_falha_lon"),
]


def _consultar(sql_base: str, ids: List) -> Dict:
    if not ids:
        return {}
    conn = get_db_connection()
    cursor = conn.cursor()
    linhas = {}
    for i in range(0, len(ids), 500):  # lotes: limite de parâmetros do SQLite
        lote = ids[i:i + 500]
        cursor.execute(sql_base.format(", ".join(ph() for _ in lote)), lote)
        for l in cursor.fetchall():
            l = dict(l)
            linhas[l["id"]] = l
    conn.close()
    return linhas


def registros_epicentros(resultado: Dict) -> List[Dict]:
    """Uma linha por epicentro analisado.

    Análises antigas guardavam só id/distância; nesse caso completa com o banco
    (eventos ou falhas apagados depois ficam com campos vazios).
    """
    itens = resultado.get("por_epicentro", [])
    faltando_epi = [p["id"] for p in itens if "lat" not in p and p.get("id") is not None]
    faltando_falha = list({p["falha_id"] for p in itens if "falha_nome" not in p})
    epi_db = _consultar("SELECT id, id_externo, data_hora, lat, lon, magnitude, profundidade_km "
                        "FROM epicentros WHERE id IN ({})", faltando_epi)
    falha_db = _consultar("SELECT id, nome FROM falhas WHERE id IN ({})", faltando_falha)

    registros = []
    for p in itens:
        r = dict(epi_db.get(p.get("id"), {}))
        r.update({k: v for k, v in p.items() if k != "ponto_falha"})
        if "falha_nome" not in p:
            r["falha_nome"] = falha_db.get(p["falha_id"], {}).get("nome")
        r["ponto_falha_lat"], r["ponto_falha_lon"] = p["ponto_falha"]
        r["data_hora"] = str(r["data_hora"]) if r.get("data_hora") is not None else None
        registros.append(r)
    return registros


def _numero_br(valor) -> str:
    if valor is None:
        return ""
    if isinstance(valor, float):
        return f"{valor:.6g}".replace(".", ",") if abs(valor) < 1e6 else str(valor).replace(".", ",")
    return str(valor)


def csv_epicentros(resultado: Dict) -> str:
    """CSV para Excel em português: separador ';', vírgula decimal e BOM UTF-8."""
    saida = io.StringIO()
    escritor = csv.writer(saida, delimiter=";", lineterminator="\r\n")
    escritor.writerow([titulo for _, titulo in COLUNAS_CSV])
    for r in registros_epicentros(resultado):
        escritor.writerow([_numero_br(r.get(campo)) for campo, _ in COLUNAS_CSV])
    return "﻿" + saida.getvalue()


def geojson(resultado: Dict) -> Dict:
    """Epicentros (pontos) e ligações até a falha mais próxima (linhas), para QGIS."""
    features = []
    for r in registros_epicentros(resultado):
        props = {titulo: r.get(campo) for campo, titulo in COLUNAS_CSV}
        if r.get("lat") is not None:
            features.append({"type": "Feature", "properties": {"camada": "epicentro", **props},
                             "geometry": {"type": "Point", "coordinates": [r["lon"], r["lat"]]}})
            features.append({"type": "Feature",
                             "properties": {"camada": "ligacao", "id_evento": r.get("id_externo"),
                                            "distancia_falha_km": r.get("dist_km"), "falha_id": r.get("falha_id")},
                             "geometry": {"type": "LineString", "coordinates": [
                                 [r["lon"], r["lat"]], [r["ponto_falha_lon"], r["ponto_falha_lat"]]]}})
    b = resultado["parametros"]["bbox"]
    features.append({"type": "Feature", "properties": {"camada": "area_estudo"},
                     "geometry": {"type": "Polygon", "coordinates": [[
                         [b["oeste"], b["sul"]], [b["leste"], b["sul"]], [b["leste"], b["norte"]],
                         [b["oeste"], b["norte"]], [b["oeste"], b["sul"]]]]}})
    return {"type": "FeatureCollection", "features": features}


def geojson_texto(resultado: Dict) -> str:
    return json.dumps(geojson(resultado), ensure_ascii=False)


def json_completo(resultado: Dict) -> str:
    return json.dumps(resultado, ensure_ascii=False, indent=2, default=str)


def nome_arquivo(resultado: Dict, extensao: str) -> str:
    base = resultado.get("nome") or f"analise-{resultado.get('id', '')}"
    base = unicodedata.normalize("NFKD", base).encode("ascii", "ignore").decode()
    base = re.sub(r"[^A-Za-z0-9]+", "-", base).strip("-").lower()[:60] or "analise"
    return f"sismofalhas-{resultado.get('id', '')}-{base}.{extensao}"
