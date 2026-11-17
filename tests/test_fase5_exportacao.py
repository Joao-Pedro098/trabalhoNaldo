import csv
import io
import json

import numpy as np
import pytest

from modelo.fontes import usgs
from modelo.importacao import ImportacaoModelo

AREA = {"sul": -1.0, "oeste": 0.0, "norte": 1.0, "leste": 1.0}


def _feature(i, lon, lat):
    return {"type": "Feature", "id": f"us{i}",
            "properties": {"mag": 3.0 + (i % 10) / 10, "place": f"Local {i}", "time": 1600000000000 + i * 1000,
                           "magType": "mb"},
            "geometry": {"type": "Point", "coordinates": [lon, lat, 10.0]}}


@pytest.fixture()
def com_dados(cliente, monkeypatch):
    """Importa 40 sismos pela API (USGS simulada) e envia uma falha em lon 0,3."""
    rng = np.random.default_rng(5)
    colecao = {"features": [_feature(i, float(rng.uniform(0.0, 1.0)), float(rng.uniform(-1, 1)))
                            for i in range(40)]}
    monkeypatch.setattr(usgs, "contar", lambda *a: 40)
    monkeypatch.setattr(usgs, "buscar", lambda *a: usgs.converter_geojson(colecao))
    r = cliente.post("/api/epicentros/importar",
                     json={"bbox": AREA, "inicio": "2020-01-01", "fim": "2020-12-31", "min_mag": 2})
    assert r.status_code == 200
    falha = {"type": "FeatureCollection", "features": [{"type": "Feature", "properties": {"nome": "Falha Ç"},
             "geometry": {"type": "LineString", "coordinates": [[0.3, -1.5], [0.3, 1.5]]}}]}
    cliente.post("/api/falhas/upload", content_type="multipart/form-data",
                 data={"arquivo": (io.BytesIO(json.dumps(falha).encode()), "f.geojson"), "fonte": "Teste"})
    return cliente


def _analisar(cliente, **extra):
    corpo = {"bbox": AREA, "n_simulacoes": 99, "nome": "Análise de teste"}
    corpo.update(extra)
    resp = cliente.post("/api/analise", json=corpo)
    assert resp.status_code == 200, resp.get_json()
    return resp.get_json()["resultado"]


# ---------------- registro de importações ----------------

def test_importacoes_sao_registradas(com_dados):
    imps = com_dados.get("/api/importacoes").get_json()["importacoes"]
    por_tipo = {i["tipo"]: i for i in imps}
    assert por_tipo["epicentros"]["bbox"] == AREA and por_tipo["epicentros"]["recebidos"] == 40
    assert por_tipo["epicentros"]["parametros"]["min_mag"] == 2
    # upload: a área registrada é a extensão do arquivo
    assert por_tipo["falhas"]["bbox"] == {"sul": -1.5, "oeste": 0.3, "norte": 1.5, "leste": 0.3}
    assert por_tipo["falhas"]["fonte"] == "Teste"
    so_epi = com_dados.get("/api/importacoes?tipo=epicentros").get_json()["importacoes"]
    assert [i["tipo"] for i in so_epi] == ["epicentros"]


def test_cobertura_proporcional_a_area(cliente):
    assert ImportacaoModelo.cobertura("epicentros", AREA) is None  # sem registro
    ImportacaoModelo.registrar("epicentros", "t", {"sul": -1, "oeste": 0, "norte": 1, "leste": 0.5}, None, 0)
    assert ImportacaoModelo.cobertura("epicentros", AREA) == pytest.approx(0.5)
    ImportacaoModelo.registrar("epicentros", "t", {"sul": -1, "oeste": 0.4, "norte": 1, "leste": 1}, None, 0)
    assert ImportacaoModelo.cobertura("epicentros", AREA) == pytest.approx(1.0)  # união, sem contar 2x


def test_cobertura_usa_area_na_esfera(cliente):
    # Faixa 0–30° tem mais área que 30–60° (sen 30° = 0,5; sen 60° ≈ 0,866)
    ImportacaoModelo.registrar("epicentros", "t", {"sul": 0, "oeste": 0, "norte": 30, "leste": 10}, None, 0)
    frac = ImportacaoModelo.cobertura("epicentros", {"sul": 0, "oeste": 0, "norte": 60, "leste": 10})
    assert frac == pytest.approx(0.5 / 0.866, rel=1e-3)


def test_area_importada_so_considera_as_proximas(cliente):
    ImportacaoModelo.registrar("epicentros", "t", AREA, None, 0)
    ImportacaoModelo.registrar("epicentros", "t", {"sul": 40, "oeste": 40, "norte": 41, "leste": 41}, None, 0)
    assert ImportacaoModelo.area_importada("epicentros", {"sul": -2, "oeste": -2, "norte": 2, "leste": 2}) == AREA


# ---------------- análise com a área importada ----------------

def test_analise_area_importada_e_aviso_de_cobertura(com_dados):
    larga = {"sul": -1.0, "oeste": -1.0, "norte": 1.0, "leste": 1.0}  # metade sem dados
    r = _analisar(com_dados, bbox=larga)
    assert r["cobertura_importada_pct"] == pytest.approx(50.0)
    assert any("Só 50% da área" in a for a in r["avisos"])

    r2 = _analisar(com_dados, bbox={"sul": -5, "oeste": -5, "norte": 5, "leste": 5}, area="importada")
    assert r2["parametros"]["bbox"] == AREA
    assert r2["cobertura_importada_pct"] == pytest.approx(100.0)
    assert not any("da área" in a for a in r2["avisos"])


def test_area_importada_sem_registro(cliente):
    resp = cliente.post("/api/analise", json={"bbox": AREA, "area": "importada"})
    assert resp.status_code == 400 and "Nenhuma importação" in resp.get_json()["erro"]


# ---------------- exportação ----------------

def test_exportar_csv(com_dados):
    r = _analisar(com_dados)
    resp = com_dados.get(f"/api/analises/{r['id']}/exportar?formato=csv")
    assert resp.status_code == 200
    assert "attachment" in resp.headers["Content-Disposition"]
    assert "analise-de-teste.csv" in resp.headers["Content-Disposition"]
    texto = resp.data.decode("utf-8")
    assert texto.startswith("﻿")
    linhas = list(csv.reader(io.StringIO(texto[1:]), delimiter=";"))
    cab = linhas[0]
    assert cab[:4] == ["id_evento", "data_hora_utc", "latitude", "longitude"]
    assert len(linhas) == 1 + r["n_epicentros"]
    linha = dict(zip(cab, linhas[1]))
    assert "," in linha["latitude"] and "." not in linha["latitude"]  # vírgula decimal
    assert linha["falha_nome"] == "Falha Ç"
    # distância exportada = distância do resultado
    por_id = {p["id_externo"]: p for p in r["por_epicentro"]}
    assert float(linha["distancia_falha_km"].replace(",", ".")) == pytest.approx(
        por_id[linha["id_evento"]]["dist_km"], rel=1e-5)


def test_exportar_geojson_e_json(com_dados):
    r = _analisar(com_dados)
    g = json.loads(com_dados.get(f"/api/analises/{r['id']}/exportar?formato=geojson").data)
    camadas = [f["properties"]["camada"] for f in g["features"]]
    n = r["n_epicentros"]
    assert camadas.count("epicentro") == n and camadas.count("ligacao") == n and camadas.count("area_estudo") == 1
    ponto = next(f for f in g["features"] if f["properties"]["camada"] == "epicentro")
    assert ponto["geometry"]["type"] == "Point"

    j = json.loads(com_dados.get(f"/api/analises/{r['id']}/exportar?formato=json").data)
    assert j["id"] == r["id"] and j["teste_mediana"] == r["teste_mediana"]

    assert com_dados.get(f"/api/analises/{r['id']}/exportar?formato=xls").status_code == 400
    assert com_dados.get("/api/analises/999/exportar").status_code == 404


def test_exportar_analise_antiga_completa_pelo_banco(com_dados):
    """Análises salvas antes da Fase 5 só tinham id/distância por epicentro."""
    from db.database import get_db_connection
    r = _analisar(com_dados)
    for p in r["por_epicentro"]:
        for campo in ("id_externo", "data_hora", "lat", "lon", "magnitude", "profundidade_km", "falha_nome"):
            p.pop(campo)
    conn = get_db_connection()
    conn.execute("UPDATE analises SET resultado_json = ? WHERE id = ?", (json.dumps(r), r["id"]))
    conn.commit()
    conn.close()

    texto = com_dados.get(f"/api/analises/{r['id']}/exportar?formato=csv").data.decode("utf-8")[1:]
    linhas = list(csv.DictReader(io.StringIO(texto), delimiter=";"))
    assert len(linhas) == r["n_epicentros"]
    assert all(l["latitude"] and l["id_evento"].startswith("us") and l["falha_nome"] == "Falha Ç" for l in linhas)


# ---------------- histórico ----------------

def test_historico_com_conclusao_e_apagar_uma(com_dados):
    a = _analisar(com_dados)
    b = _analisar(com_dados, nome="Segunda")
    lista = com_dados.get("/api/analises").get_json()["analises"]
    assert [x["id"] for x in lista] == [b["id"], a["id"]]
    assert lista[0]["conclusao"] == b["conclusao"] and lista[0]["n_epicentros"] == b["n_epicentros"]

    assert com_dados.delete(f"/api/analises/{a['id']}").get_json()["sucesso"]
    assert [x["id"] for x in com_dados.get("/api/analises").get_json()["analises"]] == [b["id"]]
    assert com_dados.delete(f"/api/analises/{a['id']}").status_code == 404
