"""GEM Global Active Faults Database (GAF-DB).

Base mundial de falhas ativas, licença CC-BY-SA 4.0.
https://github.com/GEMScienceTools/gem-global-active-faults

Observação: a base cobre bordas de placas e regiões tectonicamente ativas
(Andes, Califórnia, Himalaia...). Ela NÃO tem falhas no território brasileiro;
para o Brasil use o upload de arquivo (ex.: dados do SGB/CPRM).
"""
import json
import os
import time
from typing import Dict, List

import requests

from modelo.fontes.geometria import intersecta, normalizar
from modelo.fontes.usgs import ErroFonte

GEM_URL = ("https://raw.githubusercontent.com/GEMScienceTools/gem-global-active-faults/"
           "master/geojson/gem_active_faults_harmonized.geojson")
FONTE = "GEM GAF-DB"
ATRIBUICAO = "Falhas: GEM Global Active Faults (CC-BY-SA 4.0)"

PASTA_CACHE = os.getenv("CACHE_DIR", os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "data", "cache"))
ARQUIVO_CACHE = os.path.join(PASTA_CACHE, "gem_active_faults_harmonized.geojson")
VALIDADE_CACHE_S = 30 * 24 * 3600  # baixa de novo após 30 dias


def _baixar() -> None:
    os.makedirs(PASTA_CACHE, exist_ok=True)
    temporario = ARQUIVO_CACHE + ".parcial"
    try:
        with requests.get(GEM_URL, stream=True, timeout=60) as resp:
            if resp.status_code != 200:
                raise ErroFonte(f"GitHub respondeu {resp.status_code} ao baixar a base do GEM.")
            with open(temporario, "wb") as f:
                for bloco in resp.iter_content(chunk_size=1 << 16):
                    f.write(bloco)
        os.replace(temporario, ARQUIVO_CACHE)
    except requests.RequestException as e:
        raise ErroFonte(f"Sem conexão para baixar a base do GEM: {e}") from e
    finally:
        if os.path.exists(temporario):
            os.remove(temporario)


def carregar_colecao() -> Dict:
    """Lê a base do cache local, baixando se não existir ou estiver velha."""
    velho = (not os.path.exists(ARQUIVO_CACHE)
             or time.time() - os.path.getmtime(ARQUIVO_CACHE) > VALIDADE_CACHE_S)
    if velho:
        try:
            _baixar()
        except ErroFonte:
            if not os.path.exists(ARQUIVO_CACHE):
                raise  # sem cache para usar no lugar
    with open(ARQUIVO_CACHE, encoding="utf-8") as f:
        return json.load(f)


def buscar(bbox: Dict) -> List[Dict]:
    """Falhas do GEM cuja caixa cruza a área pedida, no formato da tabela."""
    return filtrar(carregar_colecao(), bbox)


def filtrar(colecao: Dict, bbox: Dict) -> List[Dict]:
    registros = []
    for feature in colecao.get("features", []):
        props = feature.get("properties") or {}
        prefixo = f"GEM:{props.get('catalog_id') or 'sem-id'}"
        registro = normalizar(feature.get("geometry"), props, FONTE, prefixo_id=prefixo)
        if registro and intersecta(registro, bbox):
            registros.append(registro)
    return registros
