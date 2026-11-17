import pytest

from modelo.fontes import usgs

BBOX = {"sul": -10, "oeste": -40, "norte": 0, "leste": -30}


def feature(id_, mag, lon, lat, prof, ms=1700000000000, local="Teste"):
    return {
        "type": "Feature", "id": id_,
        "properties": {"mag": mag, "place": local, "time": ms, "magType": "mb"},
        "geometry": {"type": "Point", "coordinates": [lon, lat, prof]},
    }


COLECAO = {"type": "FeatureCollection", "features": [
    feature("a1", 4.5, -35.8, -5.5, 5.0),
    feature("a2", 2.1, -36.0, -5.2, 12.0, ms=1600000000000),
    feature("a3", None, -35.0, -6.0, None, ms=1560000000000),  # sem magnitude/profundidade (2019)
    {"type": "Feature", "id": "ruim", "properties": {}, "geometry": None},  # descartado
]}


def importar(cliente, **extra):
    corpo = {"bbox": BBOX, "inicio": "2015-01-01", "fim": "2024-12-31", "min_mag": 2}
    corpo.update(extra)
    return cliente.post("/api/epicentros/importar", json=corpo)


@pytest.fixture()
def usgs_falso(monkeypatch):
    chamadas = {}

    def buscar(bbox, inicio, fim, min_mag):
        chamadas.update(bbox=bbox, inicio=inicio, fim=fim, min_mag=min_mag)
        return usgs.converter_geojson(COLECAO)

    monkeypatch.setattr(usgs, "contar", lambda *a: 3)
    monkeypatch.setattr(usgs, "buscar", buscar)
    return chamadas


# ---------------- conversão ----------------

def test_converter_geojson():
    regs = usgs.converter_geojson(COLECAO)
    assert [r["id_externo"] for r in regs] == ["a1", "a2", "a3"]
    a1 = regs[0]
    assert (a1["lat"], a1["lon"], a1["profundidade_km"], a1["magnitude"]) == (-5.5, -35.8, 5.0, 4.5)
    assert a1["data_hora"] == "2023-11-14 22:13:20"  # epoch em ms -> UTC
    assert regs[2]["magnitude"] is None and regs[2]["profundidade_km"] is None


# ---------------- importação ----------------

def test_importar_salva_e_nao_duplica(cliente, usgs_falso):
    r1 = importar(cliente).get_json()
    assert r1["sucesso"] and r1["novos"] == 3 and r1["atualizados"] == 0
    assert usgs_falso["bbox"] == {k: float(v) for k, v in BBOX.items()}

    r2 = importar(cliente).get_json()
    assert r2["novos"] == 0 and r2["atualizados"] == 3
    assert cliente.get("/api/status").get_json()["contagens"]["epicentros"] == 3


def test_importar_recusa_acima_do_limite(cliente, monkeypatch):
    monkeypatch.setattr(usgs, "contar", lambda *a: 50000)
    monkeypatch.setattr(usgs, "buscar", lambda *a: pytest.fail("não deveria baixar"))
    resp = importar(cliente)
    assert resp.status_code == 400
    assert "50.000" in resp.get_json()["erro"]


def test_importar_erro_da_fonte_vira_502(cliente, monkeypatch):
    def falha(*a):
        raise usgs.ErroFonte("USGS respondeu 503: fora do ar")
    monkeypatch.setattr(usgs, "contar", lambda *a: None)
    monkeypatch.setattr(usgs, "buscar", falha)
    resp = importar(cliente)
    assert resp.status_code == 502
    assert "503" in resp.get_json()["erro"]


@pytest.mark.parametrize("extra, trecho", [
    ({"bbox": {"sul": 5, "oeste": -40, "norte": 0, "leste": -30}}, "Latitudes"),
    ({"bbox": {"sul": -10, "oeste": -30, "norte": 0, "leste": -40}}, "Longitudes"),
    ({"bbox": {"sul": "x"}}, "Área inválida"),
    ({"inicio": "01/02/2020"}, "AAAA-MM-DD"),
    ({"inicio": "2024-01-01", "fim": "2020-01-01"}, "posterior"),
    ({"min_mag": 12}, "intervalo"),
])
def test_importar_valida_entrada(cliente, usgs_falso, extra, trecho):
    resp = importar(cliente, **extra)
    assert resp.status_code == 400
    assert trecho in resp.get_json()["erro"]


# ---------------- consulta ----------------

def test_listar_filtra_e_ordena(cliente, usgs_falso):
    importar(cliente)
    todos = cliente.get("/api/epicentros").get_json()
    assert todos["total"] == 3

    q = "sul=-5.6&oeste=-36.1&norte=-5.0&leste=-35.5&min_mag=2"
    dados = cliente.get(f"/api/epicentros?{q}").get_json()
    assert [e["id_externo"] for e in dados["epicentros"]] == ["a1", "a2"]  # maior magnitude primeiro

    so_2023 = cliente.get("/api/epicentros?inicio=2023-01-01&fim=2023-12-31").get_json()
    assert [e["id_externo"] for e in so_2023["epicentros"]] == ["a1"]

    limitado = cliente.get("/api/epicentros?limite=1").get_json()
    assert limitado["total"] == 3 and len(limitado["epicentros"]) == 1


def test_resumo_e_apagar(cliente, usgs_falso):
    importar(cliente)
    r = cliente.get("/api/epicentros/resumo").get_json()
    assert (r["total"], r["mag_min"], r["mag_max"]) == (3, 2.1, 4.5)
    assert r["inicio"] == "2019-06-08" and r["fim"] == "2023-11-14"

    assert cliente.delete("/api/epicentros").get_json()["apagados"] == 3
    assert cliente.get("/api/epicentros").get_json()["total"] == 0
