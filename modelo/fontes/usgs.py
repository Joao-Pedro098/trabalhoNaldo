"""Cliente do catálogo de sismos da USGS (FDSN Event Web Service).

Documentação: https://earthquake.usgs.gov/fdsnws/event/1/
"""
from datetime import date, datetime, timedelta, timezone
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


LIMITE_TOTAL = 250_000   # teto de uma importação em lotes (o mundo, M >= 5 desde 1973, tem ~90 mil)
MAX_REQUISICOES = 80


def planejar_lotes(bbox: Dict, inicio: str, fim: str, min_mag: float, contar_fn=None) -> List[Dict]:
    """Divide o período ao meio, repetidamente, até cada parte caber no limite da USGS.

    Devolve [{inicio, fim, total}, ...]. Usa só o /count (rápido); ErroFonte se não couber
    em LIMITE_TOTAL ou se um único dia passar do limite.
    """
    contar_fn = contar_fn or contar
    total = contar_fn(bbox, inicio, fim, min_mag)
    if total is None:
        raise ErroFonte("A USGS não respondeu à contagem de eventos; tente de novo em instantes.")
    if total > LIMITE_TOTAL:
        raise ErroFonte(f"A consulta tem {total:,} eventos (teto de {LIMITE_TOTAL:,} por importação). "
                        "Aumente a magnitude mínima, reduza o período ou a área.".replace(",", "."))
    lotes, pendentes, chamadas = [], [(inicio, fim, total)], 1
    while pendentes:
        ini, fi, n = pendentes.pop()
        if n <= LIMITE_USGS:
            if n > 0:
                lotes.append({"inicio": ini, "fim": fi, "total": n})
            continue
        d_ini, d_fim = date.fromisoformat(ini), date.fromisoformat(fi)
        if d_ini >= d_fim:
            raise ErroFonte(f"Só o dia {ini} tem {n:,} eventos (limite da USGS: {LIMITE_USGS:,}). "
                            "Aumente a magnitude mínima.".replace(",", "."))
        meio = d_ini + (d_fim - d_ini) // 2
        for a, b in ((ini, meio.isoformat()), ((meio + timedelta(days=1)).isoformat(), fi)):
            chamadas += 1
            if chamadas > MAX_REQUISICOES:
                raise ErroFonte("Consulta grande demais para dividir em lotes; aumente a magnitude mínima.")
            m = contar_fn(bbox, a, b, min_mag)
            if m is None:
                raise ErroFonte("A USGS não respondeu à contagem de eventos; tente de novo em instantes.")
            pendentes.append((a, b, m))
    return sorted(lotes, key=lambda l: l["inicio"])


def buscar_em_lotes(bbox: Dict, inicio: str, fim: str, min_mag: float) -> List[Dict]:
    """Como `buscar`, mas sem o limite de 20.000: baixa período por período."""
    registros = []
    for lote in planejar_lotes(bbox, inicio, fim, min_mag):
        registros.extend(buscar(bbox, lote["inicio"], lote["fim"], min_mag))
    # Um evento na fronteira de dois lotes viria duas vezes
    unicos = {r["id_externo"]: r for r in registros}
    return list(unicos.values())


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
