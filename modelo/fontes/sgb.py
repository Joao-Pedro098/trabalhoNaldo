"""Estruturas geológicas do Brasil — Serviço Geológico do Brasil (SGB/CPRM).

Camada "Estruturas_GIS_Brasil_2004" (Carta Geológica do Brasil ao Milionésimo, 1:1.000.000):
falhas, zonas de cisalhamento, fraturas e lineamentos de todo o território.
https://geoportal.sgb.gov.br/server/rest/services/geologia/Estruturas_GIS_Brasil_2004/MapServer

Diferente do GEM, são estruturas em sua maioria ANTIGAS (pré-cambrianas), não falhas
comprovadamente ativas. No Brasil (intraplaca) a pergunta passa a ser se os sismos
ocorrem sobre zonas de fraqueza antigas, possivelmente reativadas.

Por padrão os "lineamentos estruturais: traços de superfícies S" (foliação) ficam de fora:
são traços de foliação, não falhas.
"""
import json
import os
import time
from typing import Dict, List

import requests

from modelo.fontes.geometria import intersecta, normalizar
from modelo.fontes.usgs import ErroFonte

SGB_URL = ("https://geoportal.sgb.gov.br/server/rest/services/geologia/"
           "Estruturas_GIS_Brasil_2004/MapServer/0/query")
FONTE = "SGB 1:1.000.000"
PAGINA = 2000  # máximo por requisição no servidor
TIMEOUT = 120

PASTA_CACHE = os.getenv("CACHE_DIR", os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "data", "cache"))
ARQUIVO_CACHE = os.path.join(PASTA_CACHE, "sgb_estruturas_2004.geojson")
VALIDADE_CACHE_S = 90 * 24 * 3600

# Atributos guardados (o resto é vazio na maioria das feições)
CAMPOS = {"NMESTRUTUR": "nome", "TIPO_ESTRU": "tipo", "SENTIDO_DE": "sentido", "MERGULHO": "mergulho",
          "RUMO": "rumo", "REGIME_TEC": "regime_tectonico", "IDADE_DESL": "idade_deslocamento_ma",
          "EVENTO_ORO": "evento_orogenico", "NOME_MAPA": "folha", "COD_FOLHA": "cod_folha", "FID": "fid"}


def _get(params: Dict) -> Dict:
    try:
        resp = requests.get(SGB_URL, params=params, timeout=TIMEOUT)
    except requests.RequestException as e:
        raise ErroFonte(f"Sem conexão com o geoportal do SGB: {e}") from e
    if resp.status_code != 200:
        raise ErroFonte(f"SGB respondeu {resp.status_code}.")
    dados = resp.json()
    if "error" in dados:
        raise ErroFonte(f"SGB: {dados['error'].get('message', 'erro')}")
    return dados


def _limpar(props: Dict) -> Dict:
    saida = {}
    for origem, destino in CAMPOS.items():
        valor = props.get(origem)
        if isinstance(valor, str):
            valor = valor.strip()
        if valor in (None, "", 0, "0") and origem not in ("FID",):
            continue
        saida[destino] = valor
    return saida


def _baixar() -> None:
    total = _get({"where": "1=1", "returnCountOnly": "true", "f": "json"}).get("count", 0)
    features = []
    inicio = 0
    while inicio < total + PAGINA:
        dados = _get({"where": f"FID>={inicio} AND FID<{inicio + PAGINA}", "outFields": ",".join(CAMPOS),
                      "outSR": 4326, "f": "geojson"})
        for f in dados.get("features", []):
            if f.get("geometry"):
                features.append({"type": "Feature", "geometry": f["geometry"],
                                 "properties": _limpar(f.get("properties") or {})})
        inicio += PAGINA
    if not features:
        raise ErroFonte("O SGB não devolveu nenhuma estrutura.")
    os.makedirs(PASTA_CACHE, exist_ok=True)
    temporario = ARQUIVO_CACHE + ".parcial"
    with open(temporario, "w", encoding="utf-8") as f:
        json.dump({"type": "FeatureCollection", "features": features}, f, ensure_ascii=False)
    os.replace(temporario, ARQUIVO_CACHE)


def carregar_colecao() -> Dict:
    velho = (not os.path.exists(ARQUIVO_CACHE)
             or time.time() - os.path.getmtime(ARQUIVO_CACHE) > VALIDADE_CACHE_S)
    if velho:
        try:
            _baixar()
        except ErroFonte:
            if not os.path.exists(ARQUIVO_CACHE):
                raise
    with open(ARQUIVO_CACHE, encoding="utf-8") as f:
        return json.load(f)


def eh_lineamento(tipo: str) -> bool:
    return "lineamento" in (tipo or "").lower()


def filtrar(colecao: Dict, bbox: Dict, incluir_lineamentos: bool = False) -> List[Dict]:
    registros = []
    for feature in colecao.get("features", []):
        props = feature.get("properties") or {}
        if not incluir_lineamentos and eh_lineamento(props.get("tipo")):
            continue
        registro = normalizar(feature.get("geometry"), props, FONTE, prefixo_id=f"SGB:{props.get('fid')}")
        if registro and intersecta(registro, bbox):
            registros.append(registro)
    return registros


def buscar(bbox: Dict, incluir_lineamentos: bool = False) -> List[Dict]:
    return filtrar(carregar_colecao(), bbox, incluir_lineamentos)
