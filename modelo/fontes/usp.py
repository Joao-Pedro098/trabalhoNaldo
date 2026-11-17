"""Catálogo do Centro de Sismologia da USP (Rede Sismográfica Brasileira — RSBR).

Serviço FDSN Event: https://www.moho.iag.usp.br/fdsnws/event/1/
Diferenças em relação à USGS: responde em texto (não GeoJSON) e não tem /count.
É a fonte indicada para o Brasil: a USGS registra só os eventos maiores do país.
"""
from typing import Dict, List

import requests

from modelo.fontes.usgs import ErroFonte

USP_URL = "https://www.moho.iag.usp.br/fdsnws/event/1"
FONTE = "USP"
LIMITE = 20000
TIMEOUT = 60

# Colunas do formato texto FDSN
COLUNAS = ["EventID", "Time", "Latitude", "Longitude", "Depth/km", "Author", "Catalog", "Contributor",
           "ContributorID", "MagType", "Magnitude", "MagAuthor", "EventLocationName", "EventType"]


def buscar(bbox: Dict, inicio: str, fim: str, min_mag: float) -> List[Dict]:
    params = {
        "format": "text",
        "minlatitude": bbox["sul"], "maxlatitude": bbox["norte"],
        "minlongitude": bbox["oeste"], "maxlongitude": bbox["leste"],
        "starttime": inicio, "endtime": f"{fim}T23:59:59",
        "minmagnitude": min_mag,
        "orderby": "time",
        "limit": LIMITE + 1,  # um a mais para saber se passou do limite
    }
    try:
        resp = requests.get(f"{USP_URL}/query", params=params, timeout=TIMEOUT)
    except requests.RequestException as e:
        raise ErroFonte(f"Sem conexão com o Centro de Sismologia da USP: {e}") from e
    if resp.status_code == 204:
        return []
    if resp.status_code != 200:
        linhas = [l.strip() for l in resp.text.splitlines() if l.strip()]
        raise ErroFonte(f"USP respondeu {resp.status_code}: {(linhas[1] if len(linhas) > 1 else resp.text)[:200]}")
    registros = converter_texto(resp.text)
    if len(registros) > LIMITE:
        raise ErroFonte(f"A consulta passa de {LIMITE:,} eventos. Aumente a magnitude mínima ou reduza "
                        "a área/período.".replace(",", "."))
    return registros


def _num(valor: str):
    valor = (valor or "").strip()
    return float(valor) if valor else None


def converter_texto(texto: str) -> List[Dict]:
    """Converte a resposta FDSN em texto ('|' como separador) em registros da tabela `epicentros`."""
    registros = []
    for linha in texto.splitlines():
        if not linha.strip() or linha.startswith("#"):
            continue
        partes = linha.split("|")
        if len(partes) < len(COLUNAS):
            continue
        c = dict(zip(COLUNAS, partes))
        if (c["EventType"] or "earthquake").strip() not in ("earthquake", ""):
            continue  # explosões de pedreira etc.
        lat, lon = _num(c["Latitude"]), _num(c["Longitude"])
        if lat is None or lon is None or not c["EventID"].strip():
            continue
        data_hora = c["Time"].strip().replace("T", " ")[:19]
        mag = _num(c["Magnitude"])
        registros.append({
            "id_externo": f"usp:{c['EventID'].strip()}",
            "fonte": FONTE,
            "data_hora": data_hora,
            "lat": lat,
            "lon": lon,
            # Muitos sismos brasileiros têm profundidade não determinada (vazia ou 0)
            "profundidade_km": _num(c["Depth/km"]),
            "magnitude": round(mag, 2) if mag is not None else None,
            "tipo_magnitude": c["MagType"].strip() or None,
            "local": c["EventLocationName"].strip() or None,
        })
    return registros
