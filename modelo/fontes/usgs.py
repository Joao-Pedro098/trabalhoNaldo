"""Cliente do catálogo de sismos da USGS (FDSN Event Web Service).

Documentação: https://earthquake.usgs.gov/fdsnws/event/1/
"""
from datetime import datetime, timezone
from typing import Dict, List, Optional

import requests

USGS_URL = "https://earthquake.usgs.gov/fdsnws/event/1"
LIMITE_USGS = 20000  # máximo de eventos que a USGS devolve por requisição
TIMEOUT = 30


class ErroFonte(Exception):
    """Falha ao consultar uma fonte externa de dados."""


def _parametros(bbox: Dict, inicio: str, fim: str, min_mag: float) -> Dict:
    return {
        "format": "geojson",
        "minlatitude": bbox["sul"],
        "maxlatitude": bbox["norte"],
        "minlongitude": bbox["oeste"],
        "maxlongitude": bbox["leste"],
        "starttime": inicio,
        "endtime": f"{fim}T23:59:59",
        "minmagnitude": min_mag,
        "eventtype": "earthquake",
    }


def _mensagem_erro(resp: requests.Response) -> str:
    # A USGS responde erros em texto puro: "Error 400: Bad Request\n\n<detalhe>..."
    linhas = [l.strip() for l in resp.text.splitlines() if l.strip()]
    detalhe = linhas[1] if len(linhas) > 1 else (linhas[0] if linhas else "")
    return f"USGS respondeu {resp.status_code}: {detalhe[:200]}"


def contar(bbox: Dict, inicio: str, fim: str, min_mag: float) -> Optional[int]:
    """Quantos eventos a consulta retornaria. None se a USGS não responder a contagem."""
    params = _parametros(bbox, inicio, fim, min_mag)
    params["format"] = "text"
    try:
        resp = requests.get(f"{USGS_URL}/count", params=params, timeout=TIMEOUT)
        if resp.status_code == 200:
            return int(resp.text.strip())
    except (requests.RequestException, ValueError):
        pass
    return None


def buscar(bbox: Dict, inicio: str, fim: str, min_mag: float) -> List[Dict]:
    """Baixa os eventos e devolve no formato da tabela `epicentros`."""
    params = _parametros(bbox, inicio, fim, min_mag)
    params.update({"orderby": "time", "limit": LIMITE_USGS})
    try:
        resp = requests.get(f"{USGS_URL}/query", params=params, timeout=TIMEOUT)
    except requests.RequestException as e:
        raise ErroFonte(f"Sem conexão com a USGS: {e}") from e
    if resp.status_code == 204:  # nenhum evento
        return []
    if resp.status_code != 200:
        raise ErroFonte(_mensagem_erro(resp))
    return converter_geojson(resp.json())


def converter_geojson(colecao: Dict) -> List[Dict]:
    """Converte a FeatureCollection da USGS em registros da tabela `epicentros`."""
    registros = []
    for feature in colecao.get("features", []):
        props = feature.get("properties") or {}
        coords = (feature.get("geometry") or {}).get("coordinates") or []
        if len(coords) < 2 or props.get("time") is None or not feature.get("id"):
            continue
        data_hora = datetime.fromtimestamp(props["time"] / 1000, tz=timezone.utc)
        registros.append({
            "id_externo": feature["id"],
            "fonte": "USGS",
            "data_hora": data_hora.strftime("%Y-%m-%d %H:%M:%S"),
            "lon": float(coords[0]),
            "lat": float(coords[1]),
            "profundidade_km": float(coords[2]) if len(coords) > 2 and coords[2] is not None else None,
            "magnitude": float(props["mag"]) if props.get("mag") is not None else None,
            "tipo_magnitude": props.get("magType"),
            "local": props.get("place"),
        })
    return registros
