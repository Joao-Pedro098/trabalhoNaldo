"""Motor de correlação espacial entre falhas mapeadas e epicentros.

Pergunta: os epicentros estão mais perto das falhas do que estariam por acaso?

Método
------
1. Projeta tudo numa projeção azimutal equidistante centrada na área de estudo
   (distâncias em metros, com pouca distorção em escala regional).
2. Distância observada: de cada epicentro até a falha mais próxima.
3. Hipótese nula: epicentros distribuídos uniformemente na área de estudo
   (uniforme na esfera dentro da caixa lat/lon).
4. Monte Carlo: sorteia `n_simulacoes` catálogos aleatórios do mesmo tamanho e
   compara a mediana das distâncias e a fração de eventos dentro de cada buffer.
   p-valor unilateral = (1 + nº de simulações tão extremas quanto o observado) / (n + 1).
5. Teste KS entre as distribuições observada e aleatória.

Este módulo não acessa banco nem rede: recebe listas e devolve um dicionário.
"""
import math
from typing import Dict, List, Optional, Sequence

import numpy as np
import shapely
import shapely.geometry
from pyproj import Transformer
from scipy import stats

from modelo.geodesia import IndiceGeodesico, distancia_haversine_km

RAIO_TERRA_KM = 6371.0088
EXTENSAO_MAX_RECOMENDADA_KM = 2500  # acima disso a projeção local distorce mais
TAMANHO_POOL_ALEATORIO = 200_000
LOTE_SIMULACOES = 100
TOP_FALHAS = 20


class ErroAnalise(ValueError):
    """Dados insuficientes ou parâmetros inválidos para a análise."""


# ---------------------------------------------------------------- utilidades

def proj_local(bbox: Dict) -> str:
    """Projeção azimutal equidistante centrada na área (string PROJ)."""
    lat0 = (bbox["sul"] + bbox["norte"]) / 2
    lon0 = (bbox["oeste"] + bbox["leste"]) / 2
    return f"+proj=aeqd +lat_0={lat0:.6f} +lon_0={lon0:.6f} +datum=WGS84 +units=m"


def _projetor(bbox: Dict) -> Transformer:
    return Transformer.from_crs("EPSG:4326", proj_local(bbox), always_xy=True)


def area_bbox_km2(bbox: Dict) -> float:
    """Área da caixa lat/lon na esfera."""
    dlon = math.radians(bbox["leste"] - bbox["oeste"])
    return RAIO_TERRA_KM ** 2 * dlon * (math.sin(math.radians(bbox["norte"])) - math.sin(math.radians(bbox["sul"])))


def pontos_aleatorios(bbox: Dict, n: int, rng: np.random.Generator, poligono=None, aceitar=None):
    """n pontos uniformes na esfera dentro da caixa (lon, lat em graus).

    Com `poligono` (lon/lat), sorteia na caixa e descarta os pontos fora dele
    (amostragem por rejeição: continua uniforme, agora só dentro do território).
    """
    s1, s2 = math.sin(math.radians(bbox["sul"])), math.sin(math.radians(bbox["norte"]))
    if poligono is None and aceitar is None:
        lon = rng.uniform(bbox["oeste"], bbox["leste"], n)
        lat = np.degrees(np.arcsin(rng.uniform(s1, s2, n)))
        return lon, lat
    lons, lats, total, tentativas = [], [], 0, 0
    while total < n:
        lote = max(1000, 2 * (n - total))
        lon = rng.uniform(bbox["oeste"], bbox["leste"], lote)
        lat = np.degrees(np.arcsin(rng.uniform(s1, s2, lote)))
        dentro = np.ones(lote, dtype=bool)
        if poligono is not None:
            dentro &= shapely.contains_xy(poligono, lon, lat)
        if aceitar is not None:
            dentro &= aceitar(lon, lat)
        lons.append(lon[dentro]); lats.append(lat[dentro]); total += int(dentro.sum())
        tentativas += lote
        if tentativas > 200 * n and total < n:
            raise ErroAnalise("A área de estudo que sobra (após os filtros) é pequena demais para sortear pontos.")
    return np.concatenate(lons)[:n], np.concatenate(lats)[:n]


def extensao_bbox_km(bbox: Dict) -> float:
    """Maior dimensão da caixa medida na esfera (largura no paralelo central ou altura)."""
    lat_c = (bbox["sul"] + bbox["norte"]) / 2
    largura = float(distancia_haversine_km(bbox["oeste"], lat_c, bbox["oeste"] + min(bbox["leste"] - bbox["oeste"], 180), lat_c)[0])
    if bbox["leste"] - bbox["oeste"] > 180:
        largura *= (bbox["leste"] - bbox["oeste"]) / 180
    altura = RAIO_TERRA_KM * math.radians(bbox["norte"] - bbox["sul"])
    return max(largura, altura)


def area_poligono_km2(poligono) -> float:
    """Área geodésica (elipsoide WGS84) de um polígono lon/lat."""
    from pyproj import Geod
    area, _ = Geod(ellps="WGS84").geometry_area_perimeter(poligono)
    return abs(area) / 1e6


def erro_escala_pct(bbox: Dict) -> float:
    """Maior exagero de distância (%) da projeção azimutal equidistante dentro da caixa.

    Nessa projeção a escala é exata na direção do centro e vale c/sen(c) na perpendicular,
    onde c é a distância angular ao centro: o pior caso é o canto mais distante.
    """
    lat0 = math.radians((bbox["sul"] + bbox["norte"]) / 2)
    lon0 = math.radians((bbox["oeste"] + bbox["leste"]) / 2)
    pior = 0.0
    for la in (bbox["sul"], bbox["norte"]):
        for lo in (bbox["oeste"], bbox["leste"]):
            la_r, lo_r = math.radians(la), math.radians(lo)
            c = math.acos(max(-1.0, min(1.0, math.sin(lat0) * math.sin(la_r)
                                          + math.cos(lat0) * math.cos(la_r) * math.cos(lo_r - lon0))))
            pior = max(pior, (c / math.sin(c) - 1) if c > 1e-9 else 0.0)
    return 100 * pior


def energia_joules(magnitude: Optional[float]) -> float:
    """Energia sísmica aproximada (Gutenberg–Richter): log10 E = 1,5 M + 4,8."""
    return 0.0 if magnitude is None else 10 ** (1.5 * magnitude + 4.8)


def _partes_linha(geometria: Dict) -> List[List[List[float]]]:
    if geometria["type"] == "LineString":
        return [geometria["coordinates"]]
    return list(geometria["coordinates"])


def _resumo(valores: np.ndarray) -> Dict:
    return {
        "media_km": round(float(np.mean(valores)), 2),
        "mediana_km": round(float(np.median(valores)), 2),
        "p25_km": round(float(np.percentile(valores, 25)), 2),
        "p75_km": round(float(np.percentile(valores, 75)), 2),
        "min_km": round(float(np.min(valores)), 3),
        "max_km": round(float(np.max(valores)), 2),
    }


# ---------------------------------------------------------------- principal

class IndiceFalhas:
    """Falhas projetadas + índice espacial para achar a mais próxima."""

    def __init__(self, falhas: Sequence[Dict], projetor: Transformer):
        geoms, dono = [], []
        self.comprimento_km: Dict = {}
        for falha in falhas:
            for parte in _partes_linha(falha["geometria"]):
                arr = np.asarray(parte, dtype=float)
                x, y = projetor.transform(arr[:, 0], arr[:, 1])
                linha = shapely.linestrings(np.column_stack([x, y]))
                geoms.append(linha)
                dono.append(falha["id"])
                self.comprimento_km[falha["id"]] = self.comprimento_km.get(falha["id"], 0.0) + linha.length / 1000
        if not geoms:
            raise ErroAnalise("Nenhuma falha com geometria válida na área.")
        self.geoms = np.array(geoms, dtype=object)
        self.dono = np.array(dono, dtype=object)
        self.arvore = shapely.STRtree(self.geoms)

    def mais_proxima(self, x: np.ndarray, y: np.ndarray):
        """(distância em km, índice da parte) para cada ponto."""
        pontos = shapely.points(x, y)
        idx_pontos, idx_geoms = self.arvore.query_nearest(pontos, return_distance=False, all_matches=False)
        # query_nearest devolve pares ordenados por ponto; reordena para garantir
        ordem = np.argsort(idx_pontos, kind="stable")
        idx_geoms = idx_geoms[ordem]
        dist = shapely.distance(pontos, self.geoms[idx_geoms]) / 1000
        return dist, idx_geoms, pontos


def analisar(epicentros: Sequence[Dict], falhas: Sequence[Dict], bbox: Dict,
             buffers_km: Sequence[float] = (5, 10, 20, 50), n_simulacoes: int = 999,
             semente: int = 42, cobertura_importada: Optional[float] = None,
             poligono=None, aceitar=None, intraplaca_km: Optional[float] = None,
             comparar_categorias: bool = True) -> Dict:
    """Roda a análise completa.

    epicentros: [{id, lat, lon, magnitude, profundidade_km}, ...] (dentro da área)
    falhas:     [{id, nome, tipo, categoria, geometria (GeoJSON linha)}, ...]
    bbox:       {sul, oeste, norte, leste} — área de estudo (hipótese nula)
    cobertura_importada: fração da área com sismos importados (registro de importações);
                         None quando desconhecida -> usa uma estimativa pela extensão dos eventos.
    poligono:   território de estudo (shapely, lon/lat). Quando dado, a hipótese nula sorteia
                pontos só dentro dele e `bbox` deve ser a caixa que o envolve.
    aceitar:    função (lon, lat) -> máscara booleana que restringe ainda mais onde a hipótese nula
                pode sortear (ex.: só longe dos limites de placa, na análise intraplaca).
    intraplaca_km: se dado, descarta epicentros a menos dessa distância de um LIMITE DE PLACA
                (subducção, dorsal, transformante), tira essas falhas da análise e sorteia a
                hipótese nula só na área que sobra. Testa a sismicidade intraplaca.
    comparar_categorias: calcula também a associação por tipo de falha (normal, reversa...).
    """
    avisos_previos = []
    n_excluidos_intraplaca = None
    if intraplaca_km:
        limites_placa = [f for f in falhas if eh_limite_placa(f.get("tipo"))]
        if not limites_placa:
            avisos_previos.append("Nenhum limite de placa entre as falhas da área: o filtro intraplaca não teve efeito.")
        else:
            indice_limites = IndiceGeodesico(limites_placa)
            d_lim = indice_limites.mais_proxima([e["lon"] for e in epicentros], [e["lat"] for e in epicentros])[0] \
                if epicentros else np.array([])
            manter = d_lim >= intraplaca_km
            n_excluidos_intraplaca = int((~manter).sum())
            epicentros = [e for e, m in zip(epicentros, manter) if m]
            falhas = [f for f in falhas if not eh_limite_placa(f.get("tipo"))]
            filtro_anterior = aceitar

            def aceitar(lon, lat, _f=filtro_anterior):
                ok = indice_limites.mais_proxima(lon, lat)[0] >= intraplaca_km
                return ok & _f(lon, lat) if _f is not None else ok

    if len(epicentros) < 10:
        extra = " depois de descartar os próximos a limites de placa" if n_excluidos_intraplaca else ""
        raise ErroAnalise(f"São necessários pelo menos 10 epicentros na área{extra} (há {len(epicentros)}).")
    if not falhas:
        raise ErroAnalise("Não há falhas na área (nem num raio do maior buffer em volta dela).")
    buffers_km = sorted({float(b) for b in buffers_km})
    if not buffers_km or buffers_km[0] <= 0:
        raise ErroAnalise("Os buffers devem ser distâncias positivas em km.")
    if not 99 <= n_simulacoes <= 9999:
        raise ErroAnalise("O número de simulações deve ficar entre 99 e 9999.")

    rng = np.random.default_rng(semente)
    # Distâncias geodésicas (na esfera): valem para uma região, um país ou o mundo inteiro
    indice = IndiceGeodesico(falhas)

    # ---- observado
    lon = np.array([e["lon"] for e in epicentros], dtype=float)
    lat = np.array([e["lat"] for e in epicentros], dtype=float)
    dist_obs, dono, fim_lon, fim_lat = indice.mais_proxima(lon, lat)
    n = len(dist_obs)

    # ---- hipótese nula: pool de distâncias de pontos aleatórios na área
    tamanho_pool = int(min(max(n_simulacoes * n, 20_000), TAMANHO_POOL_ALEATORIO))
    rlon, rlat = pontos_aleatorios(bbox, tamanho_pool, rng, poligono, aceitar)
    dist_pool, _, _, _ = indice.mais_proxima(rlon, rlat)

    # ---- Monte Carlo (catálogos aleatórios reamostrados do pool, em lotes)
    medianas_sim = np.empty(n_simulacoes)
    fracoes_sim = np.empty((n_simulacoes, len(buffers_km)))
    limites = np.array(buffers_km)
    # Lotes menores para catálogos grandes (ex.: 90 mil eventos do mundo) não estourarem a memória
    lote = max(1, min(LOTE_SIMULACOES, int(2_000_000 // max(n, 1))))
    for inicio in range(0, n_simulacoes, lote):
        fim = min(inicio + lote, n_simulacoes)
        amostra = rng.choice(dist_pool, size=(fim - inicio, n), replace=True)
        medianas_sim[inicio:fim] = np.median(amostra, axis=1)
        fracoes_sim[inicio:fim] = (amostra[:, :, None] <= limites).mean(axis=1)

    mediana_obs = float(np.median(dist_obs))
    p_mediana = (1 + int(np.sum(medianas_sim <= mediana_obs))) / (n_simulacoes + 1)
    # Cauda oposta: os eventos estão significativamente mais LONGE do que o acaso?
    p_afastamento = (1 + int(np.sum(medianas_sim >= mediana_obs))) / (n_simulacoes + 1)

    buffers = []
    for i, km in enumerate(buffers_km):
        frac_obs = float(np.mean(dist_obs <= km))
        frac_esp = float(np.mean(dist_pool <= km))
        p = (1 + int(np.sum(fracoes_sim[:, i] >= frac_obs))) / (n_simulacoes + 1)
        buffers.append({
            "km": km,
            "n_observado": int(np.sum(dist_obs <= km)),
            "observado_pct": round(100 * frac_obs, 1),
            "esperado_pct": round(100 * frac_esp, 1),
            "razao": round(frac_obs / frac_esp, 2) if frac_esp > 0 else None,
            "p_valor": round(p, 4),
            # Bonferroni: vários buffers testados ao mesmo tempo inflariam o falso positivo
            "p_ajustado": round(min(1.0, p * len(buffers_km)), 4),
        })

    # KS: alternativa "greater" = CDF observada acima da aleatória (eventos mais perto)
    ks = stats.ks_2samp(dist_obs, dist_pool, alternative="greater")

    # ---- magnitude x distância
    mags = np.array([e.get("magnitude") if e.get("magnitude") is not None else np.nan for e in epicentros])
    validos = ~np.isnan(mags)
    spearman = None
    if validos.sum() >= 10 and np.ptp(mags[validos]) > 0:
        rho, p_rho = stats.spearmanr(mags[validos], dist_obs[validos])
        spearman = {"rho": round(float(rho), 3), "p_valor": round(float(p_rho), 4), "n": int(validos.sum())}

    # ---- ranking das falhas (eventos atribuídos à mais próxima, até o maior buffer)
    raio = buffers_km[-1]
    info_falha = {f["id"]: f for f in falhas}
    ranking: Dict = {}
    for i in np.nonzero(dist_obs <= raio)[0]:
        fid = dono[i]
        r = ranking.setdefault(fid, {"eventos": 0, "energia_j": 0.0, "mag_max": None})
        r["eventos"] += 1
        m = None if np.isnan(mags[i]) else float(mags[i])
        r["energia_j"] += energia_joules(m)
        if m is not None and (r["mag_max"] is None or m > r["mag_max"]):
            r["mag_max"] = m
    lista_ranking = []
    for fid, r in ranking.items():
        f = info_falha[fid]
        comp = indice.comprimento_km.get(fid, 0.0)
        coords = [p for parte in _partes_linha(f["geometria"]) for p in parte]
        lista_ranking.append({
            "falha_id": fid, "nome": f.get("nome"), "tipo": f.get("tipo"),
            "limites": [[min(c[1] for c in coords), min(c[0] for c in coords)],
                        [max(c[1] for c in coords), max(c[0] for c in coords)]],
            "categoria": f.get("categoria"), "fonte": f.get("fonte"),
            "eventos": r["eventos"], "mag_max": r["mag_max"],
            "energia_j": r["energia_j"],
            "comprimento_km": round(comp, 1),
            "eventos_por_100km": round(100 * r["eventos"] / comp, 2) if comp > 0 else None,
        })
    lista_ranking.sort(key=lambda r: (r["eventos"], r["energia_j"]), reverse=True)

    # ---- comparação por tipo de falha (ex.: subducção x transformante x normal)
    por_categoria = []
    categorias = sorted({f.get("categoria") or "outra" for f in falhas})
    if comparar_categorias and len(categorias) > 1:
        km_ref = buffers_km[min(1, len(buffers_km) - 1)]  # 10 km no padrão
        amostra_pool = rng.choice(len(rlon), size=min(len(rlon), 50_000), replace=False)
        for cat in categorias:
            subconjunto = [f for f in falhas if (f.get("categoria") or "outra") == cat]
            idx_cat = IndiceGeodesico(subconjunto)
            d_obs_cat = idx_cat.mais_proxima(lon, lat)[0]
            d_pool_cat = idx_cat.mais_proxima(rlon[amostra_pool], rlat[amostra_pool])[0]
            frac_obs = float(np.mean(d_obs_cat <= km_ref))
            frac_esp = float(np.mean(d_pool_cat <= km_ref))
            # Monte Carlo: catálogos aleatórios do mesmo tamanho, reamostrados do pool da categoria
            sim = np.empty(n_simulacoes)
            lote_c = max(1, min(LOTE_SIMULACOES, int(2_000_000 // max(n, 1))))
            perto = d_pool_cat <= km_ref
            for ini in range(0, n_simulacoes, lote_c):
                fim_c = min(ini + lote_c, n_simulacoes)
                sim[ini:fim_c] = rng.choice(perto, size=(fim_c - ini, n), replace=True).mean(axis=1)
            p = (1 + int(np.sum(sim >= frac_obs))) / (n_simulacoes + 1)
            por_categoria.append({
                "categoria": cat, "n_falhas": len(subconjunto), "km": km_ref,
                "observado_pct": round(100 * frac_obs, 1), "esperado_pct": round(100 * frac_esp, 1),
                "razao": round(frac_obs / frac_esp, 2) if frac_esp > 0 else None,
                "p_valor": round(p, 4), "p_ajustado": round(min(1.0, p * len(categorias)), 4),
                "mediana_km": round(float(np.median(d_obs_cat)), 1),
            })
        por_categoria.sort(key=lambda c: (c["razao"] or 0), reverse=True)

    # ---- histograma observado x esperado
    # O último intervalo acumula tudo acima do teto (o painel o rotula como "≥")
    teto = max(buffers_km[-1], float(np.percentile(np.concatenate([dist_obs, dist_pool]), 99)))
    bordas = np.linspace(0, teto, 21)
    obs_hist, _ = np.histogram(np.clip(dist_obs, 0, teto), bins=bordas)
    pool_hist, _ = np.histogram(np.clip(dist_pool, 0, teto), bins=bordas)
    esperado_hist = pool_hist / len(dist_pool) * n

    # ---- por epicentro: distância e ponto mais próximo na falha (para desenhar)
    por_epicentro = [
        {"id": epicentros[i].get("id"), "id_externo": epicentros[i].get("id_externo"),
         "data_hora": epicentros[i].get("data_hora"),
         "lat": float(lat[i]), "lon": float(lon[i]),
         "magnitude": epicentros[i].get("magnitude"), "profundidade_km": epicentros[i].get("profundidade_km"),
         "dist_km": round(float(dist_obs[i]), 3), "falha_id": dono[i],
         "falha_nome": info_falha[dono[i]].get("nome"),
         "ponto_falha": [round(float(fim_lat[i]), 5), round(float(fim_lon[i]), 5)]}
        for i in range(n)
    ]

    # ---- área, avisos e interpretação
    area_estudo_km2 = area_poligono_km2(poligono) if poligono is not None else area_bbox_km2(bbox)
    if n_excluidos_intraplaca is not None:
        # Área que sobra longe dos limites de placa, estimada pela taxa de aceitação do sorteio
        tlon, tlat = pontos_aleatorios(bbox, 20_000, np.random.default_rng(semente + 1), poligono)
        area_estudo_km2 *= float(np.mean(aceitar(tlon, tlat)))
    extensao_km = extensao_bbox_km(bbox)
    avisos = list(avisos_previos)
    if n_excluidos_intraplaca is not None:
        avisos.append(f"Análise intraplaca: {n_excluidos_intraplaca} epicentros a menos de {_br(intraplaca_km, 0)} km "
                      "de um limite de placa foram descartados, junto com essas falhas; o acaso só sorteia "
                      "pontos longe dos limites.")
    if n < 30:
        avisos.append(f"Poucos epicentros ({n}): o teste tem pouco poder estatístico.")
    # Se parte da área não teve sismos importados, os pontos aleatórios caem onde não há
    # dados e a comparação fica enviesada.
    if cobertura_importada is not None:
        if cobertura_importada < 0.95:
            avisos.append(
                f"Só {round(100 * cobertura_importada)}% da área de estudo teve sismos importados. Os pontos "
                "aleatórios caem também onde não há dados, o que enviesa o resultado: use a opção "
                "'Área importada' ou importe sismos no restante da área.")
    else:
        # Sem registro de importação: estima pela extensão ocupada pelos próprios eventos
        cobertura = area_bbox_km2({"sul": float(lat.min()), "norte": float(lat.max()),
                                   "oeste": float(lon.min()), "leste": float(lon.max())}) / area_estudo_km2
        if cobertura < 0.25:
            avisos.append(
                f"Os epicentros ocupam só {round(100 * cobertura)}% da área de estudo. Se a área for maior que a "
                "região onde os sismos foram importados, os pontos aleatórios caem onde não há dados e o resultado "
                "fica enviesado: ajuste o mapa à área importada.")

    distancias_obs = _resumo(dist_obs)
    distancias_ale = _resumo(dist_pool)
    resultado = {
        "n_epicentros": n,
        "n_falhas": len(falhas),
        "area_km2": round(area_estudo_km2, 1),
        "extensao_km": round(extensao_km, 1),
        "parametros": {"buffers_km": buffers_km, "n_simulacoes": n_simulacoes, "semente": semente,
                       "tamanho_pool": tamanho_pool},
        "metodo_distancia": "geodésica (esfera de raio médio, 6.371 km)",
        "distancias": distancias_obs,
        "aleatorio": distancias_ale,
        "teste_mediana": {"p_valor": round(p_mediana, 4), "p_afastamento": round(p_afastamento, 4),
                          "mediana_obs_km": round(mediana_obs, 2),
                          "mediana_sim_media_km": round(float(np.mean(medianas_sim)), 2)},
        # KS detecta qualquer diferença de FORMA entre as distribuições (não só "mais perto");
        # por isso não entra na conclusão, serve como informação complementar.
        "ks": {"estatistica": round(float(ks.statistic), 4), "p_valor": float(f"{ks.pvalue:.3g}"),
               "significado": "Diferença de forma entre as distribuições observada e aleatória"},
        "buffers": buffers,
        "spearman_mag_dist": spearman,
        "histograma": {"bordas_km": [round(float(b), 2) for b in bordas],
                       "observado": obs_hist.tolist(),
                       "esperado": [round(float(v), 2) for v in esperado_hist]},
        "ranking_falhas": lista_ranking[:TOP_FALHAS],
        "por_categoria": por_categoria,
        "intraplaca_km": intraplaca_km,
        "n_excluidos_intraplaca": n_excluidos_intraplaca,
        "por_epicentro": por_epicentro,
        "avisos": avisos,
        "cobertura_importada_pct": None if cobertura_importada is None else round(100 * cobertura_importada, 1),
    }
    codigo, texto = interpretar(resultado)
    resultado.update(conclusao=codigo, conclusao_titulo=CONCLUSOES[codigo], interpretacao=texto)
    return resultado


def zona_buffer(falhas: Sequence[Dict], bbox: Dict, km: float, poligono=None) -> Optional[Dict]:
    """Área a até `km` das falhas, recortada à área de estudo, como geometria GeoJSON.

    Calculada na mesma projeção da análise, para coincidir com os buffers dela.
    """
    if not falhas:
        return None
    projetor = _projetor(bbox)
    inverso = Transformer.from_crs(proj_local(bbox), "EPSG:4326", always_xy=True)
    indice = IndiceFalhas(falhas, projetor)
    zona = shapely.union_all(shapely.buffer(indice.geoms, km * 1000, quad_segs=8))

    # Recorte: caixa de estudo densificada (as bordas viram curvas na projeção)
    lons = np.concatenate([np.linspace(bbox["oeste"], bbox["leste"], 50), np.full(50, bbox["leste"]),
                           np.linspace(bbox["leste"], bbox["oeste"], 50), np.full(50, bbox["oeste"])])
    lats = np.concatenate([np.full(50, bbox["sul"]), np.linspace(bbox["sul"], bbox["norte"], 50),
                           np.full(50, bbox["norte"]), np.linspace(bbox["norte"], bbox["sul"], 50)])
    cx, cy = projetor.transform(lons, lats)
    area = shapely.polygons(np.column_stack([cx, cy]))
    if poligono is not None:  # recorta ao território (ex.: Brasil ou uma UF)
        area = shapely.transform(poligono, lambda c: np.column_stack(projetor.transform(c[:, 0], c[:, 1])))
    zona = shapely.intersection(zona, area)
    # Tolerância (m) proporcional ao buffer e ao tamanho da área: num mapa do Brasil inteiro
    # detalhes de centenas de metros não aparecem e só pesariam no navegador.
    minx, miny, maxx, maxy = area.bounds
    zona = shapely.simplify(zona, tolerance=max(50.0, km * 20, max(maxx - minx, maxy - miny) / 4000))
    if zona.is_empty:
        return None

    def para_graus(coords):
        x, y = inverso.transform(coords[:, 0], coords[:, 1])
        return np.column_stack([np.round(x, 5), np.round(y, 5)])

    return shapely.geometry.mapping(shapely.transform(zona, para_graus))


def _br(valor: float, casas: int = 1) -> str:
    """Número com vírgula decimal (padrão brasileiro)."""
    return f"{valor:.{casas}f}".replace(".", ",")


# Tipos de falha que marcam limites de placas tectônicas (termos do GEM e em português)
TERMOS_LIMITE_PLACA = ("subduction", "spreading", "ridge", "transform", "subduccao", "dorsal", "transformante")


def eh_limite_placa(tipo: Optional[str]) -> bool:
    import unicodedata
    texto = unicodedata.normalize("NFKD", tipo or "").encode("ascii", "ignore").decode().lower()
    return any(t in texto for t in TERMOS_LIMITE_PLACA)


ALFA = 0.05

# Códigos de conclusão (o painel usa para escolher cor/ícone)
CONCLUSOES = {
    "associacao": "Associação espacial com as falhas",
    "proximidade_sem_excesso": "Mais perto que o acaso, mas sem excesso junto às falhas",
    "excesso_local": "Excesso de eventos junto às falhas",
    "sem_associacao": "Sem associação significativa",
    "afastamento": "Epicentros mais longe das falhas que o acaso",
}


def interpretar(r: Dict):
    """(código, texto) — resumo em linguagem simples para o painel e o relatório.

    Combina dois testes, porque eles respondem perguntas diferentes:
    - mediana: os eventos estão, no geral, mais perto das falhas que pontos aleatórios?
    - buffers: há MAIS eventos colados às falhas (até X km) do que o esperado?
    """
    p = r["teste_mediana"]["p_valor"]
    obs, ale = r["distancias"]["mediana_km"], r["aleatorio"]["mediana_km"]
    excesso = [b for b in r["buffers"] if b["p_ajustado"] < ALFA and (b["razao"] or 0) > 1]
    mediana_sig = p < ALFA and obs < ale
    forca = "fortemente significativa (p < 0,01)" if p < 0.01 else f"significativa (p = {_br(p, 3)})"

    abertura = (f"A mediana da distância epicentro–falha é {_br(obs)} km, contra {_br(ale)} km "
                f"esperados para pontos aleatórios na mesma área.")
    if excesso:
        b = excesso[0]
        detalhe = (f"Dentro de {_br(b['km'], 0)} km de uma falha estão {_br(b['observado_pct'])}% dos epicentros, "
                   f"contra {_br(b['esperado_pct'])}% esperados ao acaso ({_br(b['razao'], 2)}× o esperado, "
                   f"p ajustado = {_br(b['p_ajustado'], 3)}).")
    else:
        maior = r["buffers"][-1]
        detalhe = (f"Nenhum buffer tem mais eventos que o esperado: até {_br(maior['km'], 0)} km de uma falha "
                   f"estão {_br(maior['observado_pct'])}% dos epicentros, contra {_br(maior['esperado_pct'])}% ao acaso.")

    if r["teste_mediana"].get("p_afastamento", 1) < ALFA and not excesso:
        codigo = "afastamento"
        meio = "Os epicentros estão, em geral, mais LONGE das falhas do que o acaso explicaria."
    elif mediana_sig and excesso:
        codigo = "associacao"
        meio = f"A associação espacial é {forca}."
    elif mediana_sig:
        codigo = "proximidade_sem_excesso"
        p_txt = "p < 0,01" if p < 0.01 else f"p = {_br(p, 3)}"
        meio = (f"No geral os eventos estão mais perto das falhas que o acaso ({p_txt}), mas não se concentram "
                "junto a elas. Isso costuma indicar sismos ligados à falha em profundidade (plano inclinado, "
                "como em zonas de subducção, cujo traço em superfície fica longe dos epicentros) ou a "
                "estruturas não mapeadas.")
    elif excesso:
        codigo = "excesso_local"
        meio = (f"A mediana geral não difere do acaso (p = {_br(p, 3)}), mas há excesso de eventos junto às "
                "falhas: parte da sismicidade está associada a elas.")
    else:
        codigo = "sem_associacao"
        meio = f"A associação espacial não é significativa (p = {_br(p, 3)})."
    return codigo, f"{abertura} {meio} {detalhe}"
