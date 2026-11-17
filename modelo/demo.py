"""Dados de demonstração offline (Coquimbo, Chile) — para apresentar sem internet.

Arquivos em data/demo/ (ver data/demo/LEIA-ME.md para fontes e licenças).
Carregar de novo não duplica: os ids externos são os mesmos das fontes originais.
"""
import json
import os
from typing import Dict

from modelo.epicentro import EpicentroModelo
from modelo.falha import FalhaModelo
from modelo.fontes.geometria import normalizar
from modelo.importacao import ImportacaoModelo

PASTA_DEMO = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "demo")


def _ler(nome: str) -> Dict:
    with open(os.path.join(PASTA_DEMO, nome), encoding="utf-8") as f:
        return json.load(f)


def carregar() -> Dict:
    meta = _ler("demo.json")

    m_epi = meta["epicentros"]
    epicentros = []
    for f in _ler(m_epi["arquivo"])["features"]:
        lon, lat = f["geometry"]["coordinates"][:2]
        epicentros.append({**f["properties"], "lat": lat, "lon": lon})
    res_epi = EpicentroModelo.salvar_lote(epicentros)
    ImportacaoModelo.registrar("epicentros", m_epi["fonte"], m_epi["bbox"],
                               {**m_epi["parametros"], "demonstracao": True}, len(epicentros))

    m_fal = meta["falhas"]
    falhas = []
    for f in _ler(m_fal["arquivo"])["features"]:
        props = dict(f["properties"])
        id_externo = props.pop("id_externo")
        registro = normalizar(f["geometry"], props, m_fal["fonte"])
        registro["id_externo"] = id_externo  # mantém o id original do GEM
        falhas.append(registro)
    res_fal = FalhaModelo.salvar_lote(falhas)
    ImportacaoModelo.registrar("falhas", m_fal["fonte"], m_fal["bbox"], {"demonstracao": True}, len(falhas))

    return {"regiao": meta["nome"], "bbox": m_epi["bbox"],
            "epicentros": {"recebidos": len(epicentros), **res_epi},
            "falhas": {"recebidos": len(falhas), **res_fal}}
