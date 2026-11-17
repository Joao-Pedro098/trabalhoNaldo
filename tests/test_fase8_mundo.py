import json
import sqlite3

import numpy as np
import pytest
from pyproj import Geod

from modelo import correlacao
from modelo.correlacao import analisar, eh_limite_placa
from modelo.fontes import usgs
from modelo.geodesia import IndiceGeodesico

GEOD = Geod(ellps="WGS84")
MUNDO = {"sul": -90.0, "oeste": -180.0, "norte": 90.0, "leste": 180.0}


def _ref_elipsoide(lon, lat, coords):
    """Distância de referência no elipsoide: falha amostrada a cada 50 m."""
    lons, lats = [], []
    for (x1, y1), (x2, y2) in zip(coords[:-1], coords[1:]):
        n = max(2, int(GEOD.inv(x1, y1, x2, y2)[2] / 50))
        pts = GEOD.npts(x1, y1, x2, y2, n)
        lons += [x1] + [p[0] for p in pts]
        lats += [y1] + [p[1] for p in pts]
    lons.append(coords[-1][0]); lats.append(coords[-1][1])
    _, _, d = GEOD.inv(np.full(len(lons), lon), np.full(len(lats), lat), np.array(lons), np.array(lats))
    return float(np.min(d)) / 1000


# ---------------- distâncias geodésicas ----------------

@pytest.mark.parametrize("coords, lon0, lat0", [
    ([[0, -1.5], [0, 1.5]], 0, 0),                      # equador
    ([[10, 59], [12, 61], [15, 62]], 12, 60.5),          # latitude alta
    ([[179.5, -17], [-179.6, -16.2]], 179.9, -16.6),     # cruza a longitude 180 (Fiji)
    ([[0, 88], [90, 88], [180, 88]], 45, 88),            # perto do polo
])
def test_distancia_geodesica_confere_com_elipsoide(coords, lon0, lat0):
    rng = np.random.default_rng(7)
    idx = IndiceGeodesico([{"id": 1, "geometria": {"type": "LineString", "coordinates": coords}}])
    lon = (lon0 + rng.uniform(-2, 2, 12) + 180) % 360 - 180
    lat = np.clip(lat0 + rng.uniform(-2, 2, 12), -89.9, 89.9)
    d, dono, plon, plat = idx.mais_proxima(lon, lat)
    ref = np.array([_ref_elipsoide(x, y, coords) for x, y in zip(lon, lat)])
    # esfera x elipsoide: no máximo ~0,5% (+ 1,5 km de folga para distâncias pequenas)
    assert np.all(np.abs(d - ref) <= 0.006 * ref + 1.5)
    assert set(dono) == {1}


def test_ponto_mais_proximo_fica_sobre_a_falha():
    idx = IndiceGeodesico([{"id": 9, "geometria": {"type": "LineString", "coordinates": [[0, -1], [0, 1]]}}])
    d, _, plon, plat = idx.mais_proxima([0.5], [0.3])
    assert plon[0] == pytest.approx(0, abs=1e-6) and plat[0] == pytest.approx(0.3, abs=1e-3)
    assert d[0] == pytest.approx(55.6, rel=0.005)  # 0,5° no equador (esfera)


def test_analise_mundial_sem_distorcao():
    rng = np.random.default_rng(1)
    falhas = [{"id": i, "nome": None, "tipo": "Normal", "categoria": "normal",
               "geometria": {"type": "LineString", "coordinates": [[lon, -30], [lon, 30]]}}
              for i, lon in enumerate(range(-170, 180, 40))]
    lon = rng.choice(range(-170, 180, 40), 200) + rng.normal(0, 0.05, 200)
    lat = rng.uniform(-25, 25, 200)
    epis = [{"id": i, "lon": float(x), "lat": float(y), "magnitude": 5.0, "profundidade_km": 10}
            for i, (x, y) in enumerate(zip(lon, lat))]
    r = analisar(epis, falhas, MUNDO, n_simulacoes=199)
    assert r["conclusao"] == "associacao"
    assert r["distancias"]["mediana_km"] < 10  # ~0,05° das falhas, em qualquer longitude
    assert not any("Área grande" in a for a in r["avisos"])
    assert r["metodo_distancia"].startswith("geodésica")
    assert r["area_km2"] == pytest.approx(510_065_622, rel=0.002)  # superfície da Terra (esfera)


# ---------------- intraplaca e categorias ----------------

def _cenario_placas():
    """Uma dorsal (limite de placa) com muitos sismos e uma falha normal intraplaca com poucos."""
    rng = np.random.default_rng(2)
    falhas = [
        {"id": 1, "nome": "Dorsal", "tipo": "Spreading_Ridge", "categoria": "dorsal",
         "geometria": {"type": "LineString", "coordinates": [[-20, -10], [-20, 10]]}},
        {"id": 2, "nome": "Intraplaca", "tipo": "Normal", "categoria": "normal",
         "geometria": {"type": "LineString", "coordinates": [[10, -5], [10, 5]]}},
    ]
    perto_dorsal = [(-20 + rng.normal(0, 0.05), rng.uniform(-9, 9)) for _ in range(150)]
    perto_intra = [(10 + rng.normal(0, 0.03), rng.uniform(-4, 4)) for _ in range(40)]
    epis = [{"id": i, "lon": x, "lat": y, "magnitude": 4.5, "profundidade_km": 10}
            for i, (x, y) in enumerate(perto_dorsal + perto_intra)]
    return epis, falhas, {"sul": -15, "oeste": -30, "norte": 15, "leste": 20}


def test_intraplaca_descarta_limites_de_placa():
    epis, falhas, bbox = _cenario_placas()
    r = analisar(epis, falhas, bbox, n_simulacoes=199, intraplaca_km=200)
    assert r["n_excluidos_intraplaca"] == 150 and r["n_epicentros"] == 40
    assert r["n_falhas"] == 1  # a dorsal saiu
    assert all(p["falha_id"] == 2 for p in r["por_epicentro"])
    assert any("intraplaca" in a for a in r["avisos"])
    # área efetiva menor que a caixa (a faixa de 200 km em volta da dorsal saiu do sorteio)
    assert r["area_km2"] < correlacao.area_bbox_km2(bbox) * 0.95
    assert r["conclusao"] == "associacao"
    assert r["por_categoria"] == []  # só sobrou uma categoria


def test_comparacao_por_categoria():
    epis, falhas, bbox = _cenario_placas()
    r = analisar(epis, falhas, bbox, n_simulacoes=199)
    cats = {c["categoria"]: c for c in r["por_categoria"]}
    assert set(cats) == {"dorsal", "normal"}
    assert cats["dorsal"]["observado_pct"] > 70 and cats["dorsal"]["razao"] > 5
    assert cats["dorsal"]["p_ajustado"] == pytest.approx(min(1, cats["dorsal"]["p_valor"] * 2), abs=1e-3)
    assert r["por_categoria"][0]["razao"] >= r["por_categoria"][1]["razao"]  # ordenado


@pytest.mark.parametrize("tipo, esperado", [
    ("Subduction_Thrust", True), ("Spreading_Ridge", True), ("Dextral_Transform", True),
    ("Zona de subducção", True), ("Normal", False), ("Falha ou fratura", False), (None, False),
])
def test_eh_limite_placa(tipo, esperado):
    assert eh_limite_placa(tipo) is esperado


# ---------------- importação em lotes ----------------

def _contagem_por_ano(anual):
    """Contagem falsa: `anual` eventos por ano, proporcional aos dias."""
    from datetime import date
    def contar(bbox, inicio, fim, min_mag):
        dias = (date.fromisoformat(fim) - date.fromisoformat(inicio)).days + 1
        return int(anual * dias / 365)
    return contar


def test_planejar_lotes_divide_ate_caber():
    lotes = usgs.planejar_lotes(MUNDO, "1973-01-01", "2026-12-31", 5, contar_fn=_contagem_por_ano(1700))
    assert all(l["total"] <= usgs.LIMITE_USGS for l in lotes)
    assert lotes[0]["inicio"] == "1973-01-01" and lotes[-1]["fim"] == "2026-12-31"
    from datetime import date, timedelta
    for a, b in zip(lotes[:-1], lotes[1:]):  # sem buracos nem sobreposição
        assert date.fromisoformat(b["inicio"]) == date.fromisoformat(a["fim"]) + timedelta(days=1)
    with pytest.raises(usgs.ErroFonte, match="teto"):
        usgs.planejar_lotes(MUNDO, "1900-01-01", "2026-12-31", 2, contar_fn=_contagem_por_ano(300_000))


def test_api_importa_em_lotes_sem_duplicar(cliente, monkeypatch):
    contar = _contagem_por_ano(30_000)
    monkeypatch.setattr(usgs, "contar", contar)
    chamadas = []

    def buscar(bbox, inicio, fim, min_mag):
        chamadas.append((inicio, fim))
        # 3 eventos por lote + 1 repetido entre todos os lotes (fronteira)
        base = {"fonte": "USGS", "lat": 0.0, "lon": 0.0, "profundidade_km": 10.0, "magnitude": 5.0,
                "tipo_magnitude": "mw", "local": "x", "data_hora": f"{inicio} 00:00:00"}
        return [dict(base, id_externo=f"{inicio}-{i}") for i in range(3)] + [dict(base, id_externo="repetido")]

    monkeypatch.setattr(usgs, "buscar", buscar)
    r = cliente.post("/api/epicentros/importar", json={
        "bbox": MUNDO, "inicio": "2020-01-01", "fim": "2021-12-31", "min_mag": 5}).get_json()
    assert r["sucesso"] and len(chamadas) >= 3
    assert r["recebidos"] == 3 * len(chamadas) + 1  # o repetido entra uma vez só


# ---------------- catálogos, resultados grandes e migração ----------------

def _popular_dois_catalogos(cliente):
    from modelo.epicentro import EpicentroModelo
    from modelo.falha import FalhaModelo
    from modelo.fontes.geometria import normalizar
    from modelo.importacao import ImportacaoModelo
    rng = np.random.default_rng(4)
    regs = []
    for fonte in ("USGS", "USP"):
        for i in range(30):
            regs.append({"id_externo": f"{fonte}{i}", "fonte": fonte, "data_hora": "2020-01-01 00:00:00",
                         "lat": float(rng.uniform(-1, 1)), "lon": float(rng.normal(0.5, 0.05)),
                         "profundidade_km": 5.0, "magnitude": 3.0, "tipo_magnitude": "mb", "local": "x"})
    EpicentroModelo.salvar_lote(regs)
    ImportacaoModelo.registrar("epicentros", "USGS", {"sul": -1, "oeste": 0, "norte": 1, "leste": 1}, {}, 30)
    ImportacaoModelo.registrar("epicentros", "USP", {"sul": -5, "oeste": -5, "norte": 5, "leste": 5}, {}, 30)
    FalhaModelo.salvar_lote([normalizar({"type": "LineString", "coordinates": [[0.5, -2], [0.5, 2]]}, {}, "t")])


def test_um_catalogo_por_analise(cliente):
    _popular_dois_catalogos(cliente)
    misto = cliente.post("/api/analise", json={"bbox": {"sul": -1, "oeste": 0, "norte": 1, "leste": 1},
                                               "n_simulacoes": 99}).get_json()["resultado"]
    assert misto["n_epicentros"] == 60 and any("Catálogos misturados" in a for a in misto["avisos"])

    usgs_so = cliente.post("/api/analise", json={"bbox": {"sul": -3, "oeste": -3, "norte": 3, "leste": 3},
                                                 "area": "importada", "fontes_epicentros": ["USGS"],
                                                 "n_simulacoes": 99}).get_json()["resultado"]
    # a área importada é a do USGS, não a soma com a importação maior da USP
    assert usgs_so["parametros"]["bbox"] == {"sul": -1, "oeste": 0, "norte": 1, "leste": 1}
    assert usgs_so["n_epicentros"] == 30 and usgs_so["catalogos_epicentros"] == ["USGS"]
    assert not any("misturados" in a for a in usgs_so["avisos"])
    fontes = cliente.get("/api/epicentros/fontes").get_json()["fontes"]
    assert {f["fonte"]: f["total"] for f in fontes} == {"USGS": 30, "USP": 30}


def test_resultado_grande_sem_lista_por_epicentro(cliente, monkeypatch):
    import controle.analise_controle as ctrl
    import modelo.analise as an
    monkeypatch.setattr(an, "LIMITE_POR_EPICENTRO_NA_RESPOSTA", 10)
    monkeypatch.setattr(ctrl, "LIMITE_POR_EPICENTRO_NA_RESPOSTA", 10)
    _popular_dois_catalogos(cliente)
    r = cliente.post("/api/analise", json={"bbox": {"sul": -1, "oeste": 0, "norte": 1, "leste": 1},
                                           "fontes_epicentros": ["USP"], "n_simulacoes": 99}).get_json()["resultado"]
    assert r["por_epicentro"] == [] and r["por_epicentro_omitido"] == 30
    salvo = cliente.get(f"/api/analises/{r['id']}").get_json()["resultado"]
    assert salvo["por_epicentro_omitido"] == 30
    # popup: um epicentro por vez
    from modelo.epicentro import EpicentroModelo
    eid = EpicentroModelo.listar(fontes=["USP"], limite=1)["epicentros"][0]["id"]
    info = cliente.get(f"/api/analises/{r['id']}/epicentros/{eid}").get_json()["epicentro"]
    assert info["dist_km"] >= 0 and len(info["ponto_falha"]) == 2
    assert cliente.get(f"/api/analises/{r['id']}/epicentros/999999").status_code == 404
    # exportação continua completa
    csv = cliente.get(f"/api/analises/{r['id']}/exportar?formato=csv").data.decode("utf-8")
    assert len(csv.strip().splitlines()) == 31
    # histórico usa o resumo
    item = cliente.get("/api/analises").get_json()["analises"][0]
    assert item["n_epicentros"] == 30 and item["conclusao"]


def test_migracao_adiciona_coluna_resumo(tmp_path, monkeypatch):
    caminho = tmp_path / "antigo.db"
    con = sqlite3.connect(caminho)
    con.execute("CREATE TABLE analises (id INTEGER PRIMARY KEY AUTOINCREMENT, nome TEXT, "
                "parametros_json TEXT NOT NULL, resultado_json TEXT NOT NULL, criado_em TIMESTAMP)")
    con.execute("INSERT INTO analises (nome, parametros_json, resultado_json) VALUES (?, ?, ?)",
                ("velha", "{}", json.dumps({"conclusao": "sem_associacao", "n_epicentros": 12})))
    con.commit(); con.close()

    monkeypatch.setenv("DB_BACKEND", "sqlite")
    monkeypatch.setenv("SQLITE_PATH", str(caminho))
    import importlib
    import db.database as database
    importlib.reload(database)
    database.init_db()
    colunas = {l[1] for l in sqlite3.connect(caminho).execute("PRAGMA table_info(analises)")}
    assert "resumo_json" in colunas
    from modelo.sistema import SistemaModelo
    item = SistemaModelo.listar_analises()[0]
    assert item["nome"] == "velha" and item["conclusao"] == "sem_associacao" and item["n_epicentros"] == 12
