import numpy as np
import pytest

from modelo import correlacao
from modelo.analise import expandir_bbox
from modelo.correlacao import ErroAnalise, analisar, energia_joules, pontos_aleatorios

BBOX = {"sul": -2.0, "oeste": -2.0, "norte": 2.0, "leste": 2.0}

# Falha norte-sul no meio da área (lon = 0)
FALHA_CENTRAL = {"id": 1, "nome": "Central", "tipo": "Normal", "categoria": "normal",
                 "geometria": {"type": "LineString", "coordinates": [[0.0, -1.5], [0.0, 1.5]]}}
FALHA_LESTE = {"id": 2, "nome": "Leste", "tipo": "Reverse", "categoria": "reversa",
               "geometria": {"type": "LineString", "coordinates": [[1.5, -1.0], [1.5, 1.0]]}}


def epis(coords, mag=4.0, prof=10.0):
    return [{"id": i, "lon": lon, "lat": lat, "magnitude": mag, "profundidade_km": prof}
            for i, (lon, lat) in enumerate(coords)]


def aleatorios(n, semente):
    lon, lat = pontos_aleatorios(BBOX, n, np.random.default_rng(semente))
    return epis(zip(lon, lat))


# ---------------- geometria ----------------

def test_distancia_em_km_correta():
    # 0,1° de longitude no equador = 11,132 km (geodésica)
    r = analisar(epis([(0.1, 0.0)] * 10), [FALHA_CENTRAL], BBOX, n_simulacoes=99)
    assert r["distancias"]["mediana_km"] == pytest.approx(11.13, rel=0.005)
    # ponto mais próximo fica sobre a falha (lon 0, mesma latitude)
    lat, lon = r["por_epicentro"][0]["ponto_falha"]
    assert lon == pytest.approx(0.0, abs=1e-4) and lat == pytest.approx(0.0, abs=1e-3)


def test_area_da_caixa():
    # 4°x4° no equador ≈ 197.900 km² (esfera)
    assert correlacao.area_bbox_km2(BBOX) == pytest.approx(197_900, rel=0.01)


def test_energia():
    assert energia_joules(5.0) == pytest.approx(10 ** 12.3)
    assert energia_joules(None) == 0


# ---------------- estatística ----------------

def test_eventos_sobre_a_falha_sao_significativos():
    rng = np.random.default_rng(1)
    lat = rng.uniform(-1.4, 1.4, 60)
    lon = rng.normal(0, 0.01, 60)  # ~1 km da falha
    r = analisar(epis(zip(lon, lat)), [FALHA_CENTRAL], BBOX, n_simulacoes=999)
    assert r["teste_mediana"]["p_valor"] == pytest.approx(0.001)  # mínimo possível com 999
    b5 = r["buffers"][0]
    assert b5["km"] == 5 and b5["observado_pct"] == 100.0 and b5["razao"] > 5
    assert r["ks"]["p_valor"] < 1e-6
    assert r["conclusao"] == "associacao"
    assert "fortemente significativa" in r["interpretacao"]


def test_eventos_longe_da_falha_nao_indicam_associacao():
    rng = np.random.default_rng(2)
    lon = rng.uniform(1.6, 1.95, 40) * rng.choice([-1, 1], 40)  # perto das bordas
    lat = rng.uniform(-1.9, 1.9, 40)
    r = analisar(epis(zip(lon, lat)), [FALHA_CENTRAL], BBOX, n_simulacoes=499)
    assert r["teste_mediana"]["p_valor"] > 0.5
    assert r["conclusao"] == "afastamento" and "LONGE" in r["interpretacao"]


def test_proximidade_sem_excesso_tipo_subducao():
    """Eventos numa faixa a ~60 km do traço (como sismos no plano inclinado de uma
    subducção): mais perto que o acaso na mediana, mas nenhum colado à falha."""
    rng = np.random.default_rng(4)
    lat = rng.uniform(-1.4, 1.4, 80)
    lon = rng.normal(0.55, 0.03, 80) * rng.choice([-1, 1], 80)  # ~61 km da falha
    r = analisar(epis(zip(lon, lat)), [FALHA_CENTRAL], BBOX, n_simulacoes=499)
    assert r["teste_mediana"]["p_valor"] < 0.01
    assert all(b["observado_pct"] == 0 for b in r["buffers"])
    assert r["conclusao"] == "proximidade_sem_excesso"
    assert "não se concentram" in r["interpretacao"]


def test_taxa_de_falso_positivo_calibrada():
    """Com epicentros realmente aleatórios, ~5% das análises dão p < 0,05."""
    significativas = 0
    for semente in range(40):
        r = analisar(aleatorios(50, 1000 + semente), [FALHA_CENTRAL], BBOX,
                     n_simulacoes=199, semente=semente)
        significativas += r["teste_mediana"]["p_valor"] < 0.05
    assert significativas <= 6  # esperado ~2; 6 de 40 já seria improvável (p ≈ 0,05)


def test_resultado_reprodutivel_com_mesma_semente():
    dados = aleatorios(40, 7)
    a = analisar(dados, [FALHA_CENTRAL], BBOX, n_simulacoes=199, semente=3)
    b = analisar(dados, [FALHA_CENTRAL], BBOX, n_simulacoes=199, semente=3)
    assert a["teste_mediana"] == b["teste_mediana"] and a["buffers"] == b["buffers"]


def test_histograma_soma_n():
    r = analisar(aleatorios(30, 5), [FALHA_CENTRAL], BBOX, n_simulacoes=99)
    h = r["histograma"]
    assert sum(h["observado"]) == 30
    assert sum(h["esperado"]) == pytest.approx(30, abs=0.5)
    assert len(h["bordas_km"]) == len(h["observado"]) + 1


# ---------------- ranking ----------------

def test_ranking_por_falha():
    perto_central = [(0.01, y) for y in np.linspace(-1, 1, 8)]
    perto_leste = [(1.51, y) for y in np.linspace(-0.5, 0.5, 3)]
    dados = epis(perto_central) + [
        {"id": 100 + i, "lon": x, "lat": y, "magnitude": 6.0, "profundidade_km": 5}
        for i, (x, y) in enumerate(perto_leste)]
    r = analisar(dados, [FALHA_CENTRAL, FALHA_LESTE], BBOX, n_simulacoes=99)
    rank = r["ranking_falhas"]
    assert [x["nome"] for x in rank] == ["Central", "Leste"]
    assert (rank[0]["eventos"], rank[1]["eventos"], rank[1]["mag_max"]) == (8, 3, 6.0)
    assert rank[1]["energia_j"] == pytest.approx(3 * 10 ** 13.8)
    assert rank[0]["comprimento_km"] == pytest.approx(333.9, rel=0.01)  # 3° de meridiano


def test_spearman_magnitude_distancia():
    # magnitude cai com a distância -> rho negativo
    dados = [{"id": i, "lon": 0.02 * (i + 1), "lat": 0.0, "magnitude": 7 - 0.1 * i, "profundidade_km": 5}
             for i in range(20)]
    r = analisar(dados, [FALHA_CENTRAL], BBOX, n_simulacoes=99)
    assert r["spearman_mag_dist"]["rho"] == pytest.approx(-1.0)


# ---------------- validações ----------------

def test_erros_de_entrada():
    with pytest.raises(ErroAnalise, match="pelo menos 10"):
        analisar(aleatorios(5, 1), [FALHA_CENTRAL], BBOX)
    with pytest.raises(ErroAnalise, match="Não há falhas"):
        analisar(aleatorios(20, 1), [], BBOX)
    with pytest.raises(ErroAnalise, match="simulações"):
        analisar(aleatorios(20, 1), [FALHA_CENTRAL], BBOX, n_simulacoes=10)


def test_expandir_bbox():
    e = expandir_bbox(BBOX, 111.32)
    assert e["sul"] == pytest.approx(-3.0) and e["norte"] == pytest.approx(3.0)
    assert e["leste"] > 3.0  # longitude cresce mais longe do equador
    polo = expandir_bbox({"sul": 85, "oeste": 179, "norte": 89.5, "leste": 179.9}, 200)
    assert polo["norte"] == 90 and polo["leste"] == 180


# ---------------- API ----------------

def _popular(cliente, monkeypatch):
    """Insere epicentros e uma falha pelo próprio sistema."""
    from modelo.epicentro import EpicentroModelo
    from modelo.falha import FalhaModelo
    from modelo.fontes.geometria import normalizar

    rng = np.random.default_rng(9)
    regs = [{"id_externo": f"e{i}", "fonte": "teste", "data_hora": "2020-01-01 00:00:00",
             "lat": float(rng.uniform(-1, 1)), "lon": float(rng.normal(0, 0.02)),
             "profundidade_km": 10.0 if i % 4 else 150.0, "magnitude": 4.0, "tipo_magnitude": "mb",
             "local": "x"} for i in range(40)]
    EpicentroModelo.salvar_lote(regs)
    # Falha um pouco a OESTE da área pedida: só entra pela expansão da caixa
    FalhaModelo.salvar_lote([normalizar(
        {"type": "LineString", "coordinates": [[-0.03, -1.2], [-0.03, 1.2]]}, {"nome": "F"}, "teste")])


def test_api_analise_salva_e_recupera(cliente, monkeypatch):
    _popular(cliente, monkeypatch)
    corpo = {"bbox": {"sul": -1.1, "oeste": 0.0, "norte": 1.1, "leste": 1.0},
             "n_simulacoes": 199, "prof_max_km": 70, "nome": "Teste API"}
    # só os epicentros a leste de lon 0 entram; a falha (lon -0,03) vem pela expansão
    resp = cliente.post("/api/analise", json=corpo)
    assert resp.status_code == 200, resp.get_json()
    r = resp.get_json()["resultado"]
    assert r["n_falhas"] == 1
    assert all(e["dist_km"] < 15 for e in r["por_epicentro"])
    assert r["parametros"]["prof_max_km"] == 70

    salvo = cliente.get(f"/api/analises/{r['id']}").get_json()["resultado"]
    assert salvo["nome"] == "Teste API" and salvo["teste_mediana"] == r["teste_mediana"]
    lista = cliente.get("/api/analises").get_json()["analises"]
    assert lista[0]["id"] == r["id"] and lista[0]["parametros"]["prof_max_km"] == 70


def test_api_analise_erros(cliente, monkeypatch):
    bbox = {"sul": -1, "oeste": -1, "norte": 1, "leste": 1}
    assert cliente.post("/api/analise", json={"bbox": bbox, "buffers_km": [0]}).status_code == 400
    assert cliente.post("/api/analise", json={"bbox": bbox, "n_simulacoes": 5}).status_code == 400
    resp = cliente.post("/api/analise", json={"bbox": bbox})  # banco vazio
    assert resp.status_code == 422 and "pelo menos 10" in resp.get_json()["erro"]
    assert cliente.get("/api/analises/999").status_code == 404
