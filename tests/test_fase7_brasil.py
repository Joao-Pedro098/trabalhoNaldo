import json

import numpy as np
import pytest
import shapely

from modelo import correlacao, territorio
from modelo.falha import categoria_falha
from modelo.fontes import sgb, usp
from modelo.fontes.usgs import ErroFonte

CABECALHO = ("#EventID|Time|Latitude|Longitude|Depth/km|Author|Catalog|Contributor|ContributorID|"
             "MagType|Magnitude|MagAuthor|EventLocationName|EventType")
TEXTO_USP = "\n".join([
    CABECALHO,
    "usp2020abc|2020-05-01T10:20:30.123456|-5.53|-35.81|0.0|x||USP|usp2020abc|mR|3.4|x|Joao Camara-RN|earthquake",
    "usp2021def|2021-01-02T00:00:00|-5.40|-35.70||x||USP|usp2021def|mR|2.1|x|RN|earthquake",
    "usp2022exp|2022-01-02T00:00:00|-5.40|-35.70|0|x||USP|usp2022exp|mR|2.0|x|Pedreira|quarry blast",
    "linha quebrada",
])


# ---------------- USP ----------------

def test_converter_texto_usp():
    regs = usp.converter_texto(TEXTO_USP)
    assert [r["id_externo"] for r in regs] == ["usp:usp2020abc", "usp:usp2021def"]  # pedreira fora
    a, b = regs
    assert a["data_hora"] == "2020-05-01 10:20:30" and a["profundidade_km"] == 0.0 and a["magnitude"] == 3.4
    assert b["profundidade_km"] is None  # não determinada
    assert a["fonte"] == "USP" and a["tipo_magnitude"] == "mR" and a["local"] == "Joao Camara-RN"


def test_buscar_usp_erros(monkeypatch):
    class Resp:
        def __init__(self, status, texto):
            self.status_code, self.text = status, texto
    monkeypatch.setattr(usp.requests, "get", lambda *a, **k: Resp(204, ""))
    assert usp.buscar({"sul": 0, "oeste": 0, "norte": 1, "leste": 1}, "2020-01-01", "2020-12-31", 2) == []
    monkeypatch.setattr(usp.requests, "get", lambda *a, **k: Resp(400, "Error 400: Bad Request\n\nminmagnitude inválida"))
    with pytest.raises(ErroFonte, match="USP respondeu 400: minmagnitude"):
        usp.buscar({"sul": 0, "oeste": 0, "norte": 1, "leste": 1}, "2020-01-01", "2020-12-31", 2)


def test_api_importar_usp(cliente, monkeypatch):
    monkeypatch.setattr(usp, "buscar", lambda *a: usp.converter_texto(TEXTO_USP))
    corpo = {"fonte": "usp", "bbox": {"sul": -7, "oeste": -39, "norte": -4, "leste": -34},
             "inicio": "2000-01-01", "fim": "2024-12-31", "min_mag": 0}
    r = cliente.post("/api/epicentros/importar", json=corpo).get_json()
    assert r["sucesso"] and r["novos"] == 2 and "USP" in r["mensagem"]
    assert cliente.get("/api/importacoes").get_json()["importacoes"][0]["fonte"] == "USP"
    corpo["fonte"] = "xyz"
    assert cliente.post("/api/epicentros/importar", json=corpo).status_code == 400


# ---------------- SGB ----------------

def _linha(fid, tipo, coords, nome=" "):
    return {"type": "Feature", "geometry": {"type": "LineString", "coordinates": coords},
            "properties": {"FID": fid, "TIPO_ESTRU": tipo, "NMESTRUTUR": nome, "SENTIDO_DE": " ",
                           "MERGULHO": 0, "REGIME_TEC": "Compressional", "NOME_MAPA": "Folha X"}}


def test_sgb_baixa_em_paginas_e_filtra(monkeypatch, tmp_path):
    feicoes = [
        _linha(0, "Falha contracional (inversa ou empurrão)", [[-36.0, -5.6], [-35.8, -5.4]], "Falha de Samambaia"),
        _linha(1, "Lineamentos estruturais: traços de superfícies S", [[-36.0, -5.0], [-35.9, -5.1]]),
        _linha(2001, "Zona de cisalhamento transcorrente dextral", [[-40.0, -10.0], [-39.0, -9.0]]),
    ]
    pedidos = []

    def falso_get(params):
        pedidos.append(params)
        if params.get("returnCountOnly"):
            return {"count": 2002}
        ini, fim = [int(x.split("<")[-1].split(">=")[-1]) for x in params["where"].split(" AND ")]
        return {"features": [f for f in feicoes if ini <= f["properties"]["FID"] < fim]}

    monkeypatch.setattr(sgb, "_get", falso_get)
    monkeypatch.setattr(sgb, "PASTA_CACHE", str(tmp_path))
    monkeypatch.setattr(sgb, "ARQUIVO_CACHE", str(tmp_path / "sgb.geojson"))

    rn = {"sul": -7, "oeste": -39, "norte": -4, "leste": -34}
    regs = sgb.buscar(rn)
    assert [r["nome"] for r in regs] == ["Falha de Samambaia"]  # lineamento fora, outra falha longe
    assert regs[0]["id_externo"].startswith("SGB:0:") and regs[0]["fonte"] == sgb.FONTE
    attrs = json.loads(regs[0]["atributos_json"])
    assert "sentido" not in attrs and attrs["regime_tectonico"] == "Compressional"  # vazios removidos
    assert len(pedidos) == 1 + 3  # contagem + páginas 0, 2000, 4000
    assert len(sgb.buscar(rn, incluir_lineamentos=True)) == 2
    assert len(pedidos) == 4  # segunda busca usa o cache


@pytest.mark.parametrize("tipo, esperado", [
    ("Falha contracional (inversa ou empurrão)", "reversa"),
    ("Falha ou zona de cisalhamento compressional", "reversa"),
    ("Falha extensional (normal)", "normal"),
    ("Zona de cisalhamento transcorrente dextral", "transcorrente"),
    ("Falha ou fratura", "outra"),
])
def test_categoria_tipos_sgb(tipo, esperado):
    assert categoria_falha(tipo) == esperado


# ---------------- territórios ----------------

def test_territorios_areas_oficiais():
    assert territorio.area_km2(territorio.poligono("BR")) == pytest.approx(8_510_000, rel=0.01)
    assert territorio.area_km2(territorio.poligono("RN")) == pytest.approx(52_809, rel=0.01)
    assert len(territorio.listar()) == 28 and territorio.listar()[0]["codigo"] == "BR"
    with pytest.raises(ValueError):
        territorio.poligono("XX")


def test_pontos_aleatorios_dentro_do_poligono():
    rn = territorio.poligono("RN")
    lon, lat = correlacao.pontos_aleatorios(territorio.bbox("RN"), 5000, np.random.default_rng(1), rn)
    assert len(lon) == 5000 and shapely.contains_xy(rn, lon, lat).all()


def test_erro_de_escala_da_projecao():
    # canto a ~157 km do centro: erro ≈ c²/6 ≈ 0,0102%
    assert correlacao.erro_escala_pct({"sul": -1, "oeste": -1, "norte": 1, "leste": 1}) == pytest.approx(0.0102, abs=5e-4)
    assert correlacao.erro_escala_pct(territorio.bbox("BR")) == pytest.approx(4.2, abs=0.3)


# ---------------- análise por território ----------------

def _popular_rn(cliente):
    from modelo.epicentro import EpicentroModelo
    from modelo.falha import FalhaModelo
    from modelo.fontes.geometria import normalizar
    from modelo.importacao import ImportacaoModelo

    rng = np.random.default_rng(3)
    lon, lat = correlacao.pontos_aleatorios(territorio.bbox("RN"), 40, rng, territorio.poligono("RN"))
    regs = [{"id_externo": f"rn{i}", "fonte": "USP", "data_hora": "2015-01-01 00:00:00", "lat": float(y),
             "lon": float(x), "profundidade_km": None if i % 2 else 0.0, "magnitude": 2.5, "tipo_magnitude": "mR",
             "local": "RN"} for i, (x, y) in enumerate(zip(lon, lat))]
    # No oceano, fora do RN mas dentro da caixa: não pode entrar na análise
    regs.append({"id_externo": "mar", "fonte": "USP", "data_hora": "2015-01-01 00:00:00", "lat": -5.0,
                 "lon": -35.0, "profundidade_km": 5.0, "magnitude": 3.0, "tipo_magnitude": "mR", "local": "mar"})
    EpicentroModelo.salvar_lote(regs)
    ImportacaoModelo.registrar("epicentros", "USP", territorio.bbox("RN"), {}, len(regs))
    FalhaModelo.salvar_lote([normalizar({"type": "LineString", "coordinates": [[-37.5, -6.5], [-35.5, -5.2]]},
                                        {"nome": "F"}, "SGB 1:1.000.000")])


def test_analise_por_territorio(cliente):
    _popular_rn(cliente)
    r = cliente.post("/api/analise", json={"territorio": "rn", "n_simulacoes": 99,
                                           "prof_max_km": 35}).get_json()["resultado"]
    assert r["n_epicentros"] == 40  # o do oceano ficou de fora
    assert r["area_km2"] == pytest.approx(52_809, rel=0.01)
    assert r["parametros"]["territorio"] == "RN" and r["cobertura_importada_pct"] == pytest.approx(100.0)
    assert any("tratados como rasos" in a for a in r["avisos"])  # 20 sem profundidade incluídos

    sem = cliente.post("/api/analise", json={"territorio": "RN", "n_simulacoes": 99, "prof_max_km": 35,
                                             "incluir_sem_profundidade": False}).get_json()["resultado"]
    assert sem["n_epicentros"] == 20

    # Zona de buffer recortada ao contorno do RN (nada no oceano)
    import shapely.geometry as sg
    zona = sg.shape(cliente.get(f"/api/analises/{r['id']}/buffer?km=50").get_json()["geometria"])
    assert zona.difference(territorio.poligono("RN").buffer(0.01)).area < 1e-6

    assert cliente.post("/api/analise", json={"territorio": "ZZ"}).status_code == 400
    contorno = cliente.get("/api/territorios/RN").get_json()
    assert contorno["nome"] == "Rio Grande do Norte" and contorno["geometria"]["type"] in ("Polygon", "MultiPolygon")
    assert cliente.get("/api/territorios/ZZ").status_code == 404


def test_listagem_simplificada_e_versao_das_falhas(cliente):
    from modelo.falha import FalhaModelo
    from modelo.fontes.geometria import normalizar
    v0 = FalhaModelo.versao()
    sinuosa = [[-36 + i * 0.001, -5 + 0.0005 * (i % 2)] for i in range(500)]
    FalhaModelo.salvar_lote([normalizar({"type": "LineString", "coordinates": sinuosa}, {}, "t")])
    assert FalhaModelo.versao() != v0

    q = "sul=-6&oeste=-37&norte=-4&leste=-35"
    cheia = cliente.get(f"/api/falhas?{q}").get_json()["falhas"]["features"][0]["geometry"]["coordinates"]
    leve = cliente.get(f"/api/falhas?{q}&tolerancia=0.01").get_json()["falhas"]["features"][0]["geometry"]["coordinates"]
    assert len(cheia) == 500 and len(leve) < 10


def test_listar_epicentros_so_no_territorio(cliente):
    _popular_rn(cliente)
    q = "sul=-7&oeste=-39&norte=-4&leste=-34"
    assert cliente.get(f"/api/epicentros?{q}").get_json()["total"] == 41
    so_rn = cliente.get(f"/api/epicentros?{q}&territorio=RN&limite=5").get_json()
    assert so_rn["total"] == 40 and len(so_rn["epicentros"]) == 5
    assert all(e["id_externo"] != "mar" for e in so_rn["epicentros"])
    assert cliente.get(f"/api/epicentros?{q}&territorio=XX").status_code == 400
