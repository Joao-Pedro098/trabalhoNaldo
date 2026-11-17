import json
import os

import pytest

from modelo.importacao import ImportacaoModelo

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_carregar_demo_sem_internet(cliente, monkeypatch):
    # Qualquer acesso à rede faria o teste falhar
    import requests
    monkeypatch.setattr(requests, "get", lambda *a, **k: pytest.fail("a demonstração não pode usar a rede"))

    r = cliente.post("/api/demo").get_json()
    assert r["sucesso"] and r["epicentros"]["novos"] == 984 and r["falhas"]["novos"] == 13
    status = cliente.get("/api/status").get_json()["contagens"]
    assert (status["epicentros"], status["falhas"]) == (984, 13)

    # Carregar de novo não duplica dados nem o registro de importações
    r2 = cliente.post("/api/demo").get_json()
    assert r2["epicentros"]["novos"] == 0 and r2["falhas"]["novos"] == 0
    assert len(cliente.get("/api/importacoes").get_json()["importacoes"]) == 2

    # A falha mantém o id original do GEM e a fonte (atribuição CC-BY-SA no mapa)
    fontes = cliente.get("/api/falhas/fontes").get_json()["fontes"]
    assert fontes == [{"fonte": "GEM GAF-DB", "total": 13}]


def test_analise_com_a_demonstracao(cliente):
    cliente.post("/api/demo")
    r = cliente.post("/api/analise", json={
        "bbox": {"sul": -40, "oeste": -80, "norte": -20, "leste": -60}, "area": "importada",
        "prof_max_km": 35, "n_simulacoes": 999}).get_json()["resultado"]
    assert r["cobertura_importada_pct"] == 100.0
    assert r["n_epicentros"] > 300
    # Resultado de referência documentado no README (semente fixa = reprodutível)
    assert r["conclusao"] == "associacao"
    assert r["teste_mediana"]["p_valor"] == pytest.approx(0.001)


def test_arquivos_da_demo_consistentes():
    meta = json.load(open(os.path.join(RAIZ, "data", "demo", "demo.json"), encoding="utf-8"))
    epi = json.load(open(os.path.join(RAIZ, "data", "demo", meta["epicentros"]["arquivo"]), encoding="utf-8"))
    b = meta["epicentros"]["bbox"]
    assert len(epi["features"]) == meta["epicentros"]["quantidade"]
    for f in epi["features"]:
        lon, lat = f["geometry"]["coordinates"]
        assert b["sul"] - 0.01 <= lat <= b["norte"] + 0.01 and b["oeste"] - 0.01 <= lon <= b["leste"] + 0.01


def test_registro_repetido_atualiza(cliente):
    area = {"sul": 0, "oeste": 0, "norte": 1, "leste": 1}
    ImportacaoModelo.registrar("epicentros", "USGS", area, {"min_mag": 2}, 10)
    ImportacaoModelo.registrar("epicentros", "USGS", area, {"min_mag": 2}, 12)
    ImportacaoModelo.registrar("epicentros", "USGS", area, {"min_mag": 3}, 5)  # filtro diferente = outro registro
    imps = ImportacaoModelo.listar("epicentros")
    assert sorted(i["recebidos"] for i in imps) == [5, 12]


def test_bibliotecas_e_mapa_offline_servidos_localmente(cliente):
    html = cliente.get("/").data.decode("utf-8")
    for caminho in ("vendor/leaflet/leaflet.js", "vendor/leaflet/leaflet.css", "vendor/chartjs/chart.umd.min.js",
                    "vendor/leaflet-heat/leaflet-heat.js", "vendor/fontawesome/css/all.min.css"):
        assert caminho in html
        assert cliente.get(f"/static/{caminho}").status_code == 200
    assert "unpkg.com" not in html and "cdnjs" not in html
    assert cliente.get("/static/vendor/fontawesome/webfonts/fa-solid-900.woff2").status_code == 200
    paises = json.loads(cliente.get("/static/data/paises_ne50m.geojson").data)
    assert len(paises["features"]) > 200
