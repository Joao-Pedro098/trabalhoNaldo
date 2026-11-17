"""Territórios para a área de estudo: o Brasil inteiro ou uma unidade da federação.

Polígonos do IBGE (Malhas territoriais, API v3, qualidade intermediária) em
static/data/brasil_ufs.geojson. Usar um polígono — e não um retângulo — evita que a
hipótese nula sorteie pontos no oceano ou em países vizinhos, onde não há falhas
mapeadas pelo SGB nem cobertura do catálogo brasileiro.
"""
import json
import os
from functools import lru_cache
from typing import Dict, List, Optional

import shapely
import shapely.geometry
from pyproj import Geod

ARQUIVO = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "static", "data", "brasil_ufs.geojson")
BRASIL = "BR"
_GEOD = Geod(ellps="WGS84")


@lru_cache(maxsize=1)
def _ufs() -> Dict[str, Dict]:
    with open(ARQUIVO, encoding="utf-8") as f:
        dados = json.load(f)
    return {f["properties"]["sigla"]: {**f["properties"], "geometria": shapely.geometry.shape(f["geometry"])}
            for f in dados["features"]}


def listar() -> List[Dict]:
    """[{codigo: 'BR', nome: 'Brasil'}, {codigo: 'AC', nome: 'Acre'}, ...]"""
    return [{"codigo": BRASIL, "nome": "Brasil (território inteiro)"}] + [
        {"codigo": sigla, "nome": uf["nome"]} for sigla, uf in sorted(_ufs().items(), key=lambda x: x[1]["nome"])]


@lru_cache(maxsize=32)
def poligono(codigo: str):
    """Geometria shapely (lon/lat) do território. ValueError se o código não existir."""
    codigo = (codigo or "").upper()
    if codigo == BRASIL:
        geom = shapely.union_all([uf["geometria"] for uf in _ufs().values()])
    elif codigo in _ufs():
        geom = _ufs()[codigo]["geometria"]
    else:
        raise ValueError(f"Território desconhecido: '{codigo}'. Use BR ou a sigla de uma UF.")
    shapely.prepare(geom)
    return geom


def nome(codigo: str) -> str:
    codigo = codigo.upper()
    return "Brasil" if codigo == BRASIL else _ufs()[codigo]["nome"]


def bbox(codigo: str) -> Dict:
    minx, miny, maxx, maxy = poligono(codigo).bounds
    return {"sul": miny, "oeste": minx, "norte": maxy, "leste": maxx}


def area_km2(geom) -> float:
    """Área geodésica (elipsoide WGS84) de um polígono lon/lat."""
    area, _ = _GEOD.geometry_area_perimeter(shapely.geometry.polygon.orient(geom) if geom.geom_type == "Polygon" else geom)
    return abs(area) / 1e6


def geojson(codigo: str, tolerancia: float = 0.01) -> Optional[Dict]:
    """Contorno simplificado para desenhar no mapa."""
    return shapely.geometry.mapping(shapely.simplify(poligono(codigo), tolerancia, preserve_topology=True))
