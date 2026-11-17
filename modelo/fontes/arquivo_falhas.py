"""Leitura de arquivos de falhas enviados pelo usuário: GeoJSON ou shapefile (.zip)."""
import io
import json
import zipfile
from typing import Dict, List, Tuple

import shapefile  # pyshp

from modelo.fontes.geometria import ErroArquivo, normalizar

CRS_GEOGRAFICOS = ("CRS84", "4326", "4674", "4618", "4989")  # WGS84 / SIRGAS 2000 / SAD69


def ler(nome_arquivo: str, conteudo: bytes, fonte: str) -> Tuple[List[Dict], int]:
    """Retorna (registros, quantidade de feições ignoradas por não serem linhas)."""
    nome = nome_arquivo.lower()
    if nome.endswith(".zip"):
        return ler_shapefile_zip(conteudo, fonte)
    if nome.endswith((".geojson", ".json")):
        return ler_geojson(conteudo, fonte)
    raise ErroArquivo("Formato não suportado. Envie .geojson/.json ou um shapefile compactado em .zip.")


# ---------------------------------------------------------------- GeoJSON

def ler_geojson(conteudo: bytes, fonte: str) -> Tuple[List[Dict], int]:
    try:
        dados = json.loads(conteudo.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        raise ErroArquivo(f"GeoJSON inválido: {e}") from e

    crs = json.dumps((dados.get("crs") or {}).get("properties", {})) if isinstance(dados, dict) else ""
    if crs != "{}" and crs and not any(c in crs for c in CRS_GEOGRAFICOS):
        raise ErroArquivo(f"Sistema de coordenadas não suportado ({crs}). Reprojete para WGS84 (EPSG:4326).")

    if dados.get("type") == "FeatureCollection":
        features = dados.get("features") or []
    elif dados.get("type") == "Feature":
        features = [dados]
    elif dados.get("type") in ("LineString", "MultiLineString"):
        features = [{"geometry": dados, "properties": {}}]
    else:
        raise ErroArquivo("O GeoJSON precisa ser FeatureCollection, Feature ou geometria de linha.")

    return _normalizar_todas(((f.get("geometry"), f.get("properties")) for f in features), fonte)


# ---------------------------------------------------------------- Shapefile

def ler_shapefile_zip(conteudo: bytes, fonte: str) -> Tuple[List[Dict], int]:
    try:
        pacote = zipfile.ZipFile(io.BytesIO(conteudo))
    except zipfile.BadZipFile as e:
        raise ErroArquivo("O .zip está corrompido ou não é um arquivo zip.") from e

    nomes = {n.lower(): n for n in pacote.namelist() if not n.startswith("__MACOSX")}
    shps = [n for n in nomes if n.endswith(".shp")]
    if not shps:
        raise ErroArquivo("O .zip não contém um arquivo .shp.")
    if len(shps) > 1:
        raise ErroArquivo(f"O .zip contém {len(shps)} shapefiles; envie um por vez.")

    base = shps[0][:-4]
    def parte(ext):
        nome = nomes.get(base + ext)
        return io.BytesIO(pacote.read(nome)) if nome else None

    if parte(".dbf") is None:
        raise ErroArquivo("Faltou o arquivo .dbf (atributos) dentro do .zip.")

    prj = parte(".prj")
    if prj is not None:
        texto_prj = prj.read().decode("latin-1").upper()
        if texto_prj.startswith("PROJCS"):
            raise ErroArquivo(
                "O shapefile está em coordenadas projetadas (ex.: UTM). Reprojete no QGIS "
                "para SIRGAS 2000 geográfico (EPSG:4674) ou WGS84 (EPSG:4326)."
            )

    cpg = parte(".cpg")
    codificacoes = [cpg.read().decode("ascii", "ignore").strip()] if cpg else []
    codificacoes += ["utf-8", "latin-1"]

    ultimo_erro = None
    for codificacao in codificacoes:
        try:
            leitor = shapefile.Reader(shp=parte(".shp"), shx=parte(".shx"), dbf=parte(".dbf"),
                                      encoding=codificacao)
            pares = [(sr.shape.__geo_interface__ if sr.shape.shapeType != shapefile.NULL else None,
                      sr.record.as_dict())
                     for sr in leitor.iterShapeRecords()]
            return _normalizar_todas(pares, fonte)
        except (UnicodeDecodeError, LookupError) as e:
            ultimo_erro = e
        except shapefile.ShapefileException as e:
            raise ErroArquivo(f"Shapefile inválido: {e}") from e
    raise ErroArquivo(f"Não foi possível ler os atributos do shapefile: {ultimo_erro}")


# ---------------------------------------------------------------- comum

def _normalizar_todas(pares, fonte: str) -> Tuple[List[Dict], int]:
    registros, ignoradas = [], 0
    vistos = set()
    for geometria, props in pares:
        registro = normalizar(geometria, props, fonte)
        if registro is None:
            ignoradas += 1
        elif registro["id_externo"] not in vistos:  # traçados idênticos no mesmo arquivo
            vistos.add(registro["id_externo"])
            registros.append(registro)
    if not registros:
        raise ErroArquivo("Nenhuma linha (LineString/MultiLineString) encontrada no arquivo.")
    return registros, ignoradas
