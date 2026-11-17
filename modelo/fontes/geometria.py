"""Normalização de geometrias de falhas (GeoJSON) para a tabela `falhas`."""
import hashlib
import json
from typing import Dict, List, Optional

TIPOS_LINHA = ("LineString", "MultiLineString")
CASAS_DECIMAIS = 5  # ~1 m; reduz o tamanho sem afetar a análise

# Chaves comuns de nome e tipo em bases de falhas (GEM, SGB/CPRM, USGS...)
CHAVES_NOME = ("name", "nome", "fault_name", "nome_falha", "NAME", "NOME", "Name", "Nome", "FAULT_NAME")
CHAVES_TIPO = ("slip_type", "tipo", "type", "TIPO", "Tipo", "SLIP_TYPE", "tipo_falha", "TIPO_FALHA", "classe", "CLASSE")


class ErroArquivo(ValueError):
    """Arquivo de falhas inválido ou em formato não suportado."""


def _primeiro(props: Dict, chaves) -> Optional[str]:
    for chave in chaves:
        valor = props.get(chave)
        if valor not in (None, ""):
            return str(valor).strip()
    return None


def _linhas(geometria: Dict) -> List[List[List[float]]]:
    """Lista de linhas [[lon, lat], ...], só 2D e arredondada."""
    tipo = geometria.get("type")
    coords = geometria.get("coordinates") or []
    linhas = [coords] if tipo == "LineString" else coords
    saida = []
    for linha in linhas:
        pontos = [[round(float(p[0]), CASAS_DECIMAIS), round(float(p[1]), CASAS_DECIMAIS)]
                  for p in linha if p is not None and len(p) >= 2]
        if len(pontos) >= 2:
            saida.append(pontos)
    return saida


def normalizar(geometria: Optional[Dict], props: Optional[Dict], fonte: str,
               prefixo_id: Optional[str] = None) -> Optional[Dict]:
    """Converte uma feature em registro da tabela. Retorna None se não for linha."""
    if not geometria or geometria.get("type") not in TIPOS_LINHA:
        return None
    props = props or {}
    linhas = _linhas(geometria)
    if not linhas:
        return None

    lons = [p[0] for l in linhas for p in l]
    lats = [p[1] for l in linhas for p in l]
    if min(lats) < -90 or max(lats) > 90 or min(lons) < -180 or max(lons) > 180:
        raise ErroArquivo(
            "Coordenadas fora de latitude/longitude. O arquivo parece estar em projeção "
            "métrica (ex.: UTM); reprojete para WGS84 / SIRGAS 2000 geográfico (EPSG:4326 ou 4674)."
        )

    geom = {"type": "LineString", "coordinates": linhas[0]} if len(linhas) == 1 \
        else {"type": "MultiLineString", "coordinates": linhas}
    geom_txt = json.dumps(geom, separators=(",", ":"))
    # Id estável: reimportar o mesmo traçado atualiza em vez de duplicar
    impressao = hashlib.sha1(geom_txt.encode()).hexdigest()[:12]
    id_externo = f"{prefixo_id or fonte}:{impressao}"

    return {
        "id_externo": id_externo,
        "nome": _primeiro(props, CHAVES_NOME),
        "tipo": _primeiro(props, CHAVES_TIPO),
        "fonte": fonte,
        "geometria_geojson": geom_txt,
        "min_lat": min(lats), "max_lat": max(lats),
        "min_lon": min(lons), "max_lon": max(lons),
        "atributos_json": json.dumps(props, ensure_ascii=False, default=str),
    }


def intersecta(registro: Dict, bbox: Dict) -> bool:
    """A caixa da falha cruza a área pedida?"""
    return (registro["min_lat"] <= bbox["norte"] and registro["max_lat"] >= bbox["sul"]
            and registro["min_lon"] <= bbox["leste"] and registro["max_lon"] >= bbox["oeste"])
