import io
import json
import zipfile

import pytest
import shapefile

from modelo.falha import categoria_falha
from modelo.fontes import arquivo_falhas, gem
from modelo.fontes.geometria import ErroArquivo, normalizar

BBOX_RN = {"sul": -6.5, "oeste": -37.0, "norte": -5.0, "leste": -35.0}


def colecao(*features):
    return {"type": "FeatureCollection", "features": list(features)}


def linha(coords, **props):
    return {"type": "Feature", "properties": props,
            "geometry": {"type": "LineString", "coordinates": coords}}


FALHA_RN = linha([[-35.9, -5.6], [-35.7, -5.4]], nome="Falha de Samambaia", tipo="Transcorrente dextral")
FALHA_LONGE = linha([[-71.0, -30.0], [-70.5, -29.0]], nome="Falha andina", tipo="Reverse")


def zip_shapefile(linhas, prj=None, encoding="utf-8"):
    shp, shx, dbf = io.BytesIO(), io.BytesIO(), io.BytesIO()
    w = shapefile.Writer(shp=shp, shx=shx, dbf=dbf, shapeType=shapefile.POLYLINE, encoding=encoding)
    w.field("NOME", "C", size=60)
    w.field("TIPO", "C", size=40)
    for coords, nome, tipo in linhas:
        w.line([coords])
        w.record(nome, tipo)
    w.close()
    saida = io.BytesIO()
    with zipfile.ZipFile(saida, "w") as z:
        z.writestr("falhas.shp", shp.getvalue())
        z.writestr("falhas.shx", shx.getvalue())
        z.writestr("falhas.dbf", dbf.getvalue())
        if prj:
            z.writestr("falhas.prj", prj)
        if encoding != "utf-8":
            z.writestr("falhas.cpg", encoding)
    return saida.getvalue()


def enviar(cliente, conteudo, nome="falhas.geojson", fonte=""):
    if isinstance(conteudo, dict):
        conteudo = json.dumps(conteudo).encode()
    return cliente.post("/api/falhas/upload", content_type="multipart/form-data",
                        data={"arquivo": (io.BytesIO(conteudo), nome), "fonte": fonte})


# ---------------- categorias ----------------

@pytest.mark.parametrize("tipo, esperado", [
    ("Normal", "normal"),
    ("Reverse", "reversa"),
    ("Subduction_Thrust", "reversa"),
    ("Reverse-Strike-Slip", "reversa"),       # primeiro termo manda
    ("Dextral-Reverse", "transcorrente"),
    ("Sinistral_Transform", "transcorrente"),
    ("Spreading_Ridge", "dorsal"),
    ("Falha de empurrão", "reversa"),
    ("Zona de cisalhamento transcorrente", "transcorrente"),
    ("Anticline", "outra"),
    (None, "outra"),
])
def test_categoria_falha(tipo, esperado):
    assert categoria_falha(tipo) == esperado


# ---------------- normalização ----------------

def test_normalizar_remove_z_e_calcula_caixa():
    geom = {"type": "MultiLineString",
            "coordinates": [[[-36.0, -5.0, 10], [-35.5, -5.5, 12]], [[-35.0, -6.0], [-35.1, -6.1]]]}
    r = normalizar(geom, {"name": "X", "slip_type": "Normal"}, "teste")
    assert (r["min_lat"], r["max_lat"], r["min_lon"], r["max_lon"]) == (-6.1, -5.0, -36.0, -35.0)
    assert json.loads(r["geometria_geojson"])["coordinates"][0][0] == [-36.0, -5.0]
    assert (r["nome"], r["tipo"]) == ("X", "Normal")
    # mesma geometria -> mesmo id (reimportar não duplica)
    assert normalizar(geom, {}, "teste")["id_externo"] == r["id_externo"]


def test_normalizar_ignora_nao_linhas_e_recusa_utm():
    assert normalizar({"type": "Point", "coordinates": [0, 0]}, {}, "t") is None
    with pytest.raises(ErroArquivo, match="projeção"):
        normalizar({"type": "LineString", "coordinates": [[500000, 9300000], [510000, 9310000]]}, {}, "t")


# ---------------- leitura de arquivos ----------------

def test_geojson_ignora_poligonos_e_duplicatas():
    poligono = {"type": "Feature", "properties": {},
                "geometry": {"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 0]]]}}
    regs, ignoradas = arquivo_falhas.ler_geojson(
        json.dumps(colecao(FALHA_RN, FALHA_RN, poligono)).encode(), "t")
    assert len(regs) == 1 and ignoradas == 1


def test_geojson_recusa_crs_projetado():
    dados = colecao(FALHA_RN)
    dados["crs"] = {"type": "name", "properties": {"name": "urn:ogc:def:crs:EPSG::31984"}}
    with pytest.raises(ErroArquivo, match="Sistema de coordenadas"):
        arquivo_falhas.ler_geojson(json.dumps(dados).encode(), "t")


def test_shapefile_latin1_com_acentos():
    conteudo = zip_shapefile([([[-35.9, -5.6], [-35.7, -5.4]], "Falha São Luís", "Transcorrente")],
                             prj='GEOGCS["SIRGAS 2000"]', encoding="latin-1")
    regs, _ = arquivo_falhas.ler("x.zip", conteudo, "SGB")
    assert regs[0]["nome"] == "Falha São Luís" and regs[0]["tipo"] == "Transcorrente"


def test_shapefile_projetado_recusado():
    conteudo = zip_shapefile([([[-35.9, -5.6], [-35.7, -5.4]], "A", "B")],
                             prj='PROJCS["SIRGAS 2000 / UTM zone 25S"]')
    with pytest.raises(ErroArquivo, match="projetadas"):
        arquivo_falhas.ler("x.zip", conteudo, "SGB")


def test_zip_sem_shp_e_formato_desconhecido():
    vazio = io.BytesIO()
    with zipfile.ZipFile(vazio, "w") as z:
        z.writestr("leia-me.txt", "nada")
    with pytest.raises(ErroArquivo, match=r"\.shp"):
        arquivo_falhas.ler("x.zip", vazio.getvalue(), "t")
    with pytest.raises(ErroArquivo, match="Formato"):
        arquivo_falhas.ler("x.kml", b"<kml/>", "t")


# ---------------- GEM ----------------

def test_gem_filtra_pela_area(cliente, monkeypatch):
    base = colecao(
        linha([[-71.0, -30.0], [-70.5, -29.0]], catalog_id="SARA_1", name="A", slip_type="Reverse"),
        linha([[-71.2, -30.1], [-70.9, -29.5]], catalog_id="SARA_1", name="A bis", slip_type="Reverse"),
        linha([[100.0, 30.0], [101.0, 31.0]], catalog_id="HIM_9", name="Longe", slip_type="Normal"),
    )
    monkeypatch.setattr(gem, "carregar_colecao", lambda: base)
    corpo = {"bbox": {"sul": -31, "oeste": -72, "norte": -28, "leste": -69}}

    r = cliente.post("/api/falhas/importar-gem", json=corpo).get_json()
    # mesmo catalog_id com traçados diferentes vira dois registros
    assert r["sucesso"] and r["novos"] == 2

    vazio = cliente.post("/api/falhas/importar-gem",
                         json={"bbox": BBOX_RN}).get_json()
    assert vazio["recebidos"] == 0 and "Brasil" in vazio["mensagem"]


# ---------------- API ----------------

def test_upload_listar_fontes_apagar(cliente):
    r = enviar(cliente, colecao(FALHA_RN, FALHA_LONGE), fonte="SGB teste").get_json()
    assert r["sucesso"] and r["novos"] == 2 and r["fonte"] == "SGB teste"
    assert enviar(cliente, colecao(FALHA_RN), fonte="SGB teste").get_json()["novos"] == 0

    q = "&".join(f"{k}={v}" for k, v in BBOX_RN.items())
    dados = cliente.get(f"/api/falhas?{q}").get_json()
    assert dados["total"] == 1
    props = dados["falhas"]["features"][0]["properties"]
    assert props["nome"] == "Falha de Samambaia" and props["categoria"] == "transcorrente"

    enviar(cliente, zip_shapefile([([[-35.0, -6.0], [-35.2, -6.2]], "Z", "Normal")]),
           nome="outra.zip")  # fonte = nome do arquivo
    fontes = {f["fonte"]: f["total"] for f in cliente.get("/api/falhas/fontes").get_json()["fontes"]}
    assert fontes == {"SGB teste": 2, "outra": 1}

    apagadas = cliente.delete("/api/falhas?fonte=SGB%20teste").get_json()["apagadas"]
    assert apagadas == 2
    assert cliente.get("/api/status").get_json()["contagens"]["falhas"] == 1


def test_upload_erros(cliente):
    assert cliente.post("/api/falhas/upload").status_code == 400
    resp = enviar(cliente, b"{nao e json", nome="x.geojson")
    assert resp.status_code == 400 and "GeoJSON inválido" in resp.get_json()["erro"]
    resp = enviar(cliente, colecao(FALHA_RN), fonte="GEM GAF-DB")
    assert resp.status_code == 400 and "reservado" in resp.get_json()["erro"]
