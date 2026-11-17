import json
import math
import time
from typing import Dict, List, Optional

from db.database import get_db_connection, is_using_postgres, ph
import shapely

from modelo import correlacao, territorio as territorios
from modelo.epicentro import EpicentroModelo
from modelo.falha import FalhaModelo
from modelo.importacao import ImportacaoModelo

LIMITE_EPICENTROS = 50_000
_CACHE_ZONAS: Dict = {}
KM_POR_GRAU_LAT = 111.32


def expandir_bbox(bbox: Dict, km: float) -> Dict:
    """Aumenta a caixa em `km` para incluir falhas logo fora da área de estudo."""
    dlat = km / KM_POR_GRAU_LAT
    lat_ref = max(abs(bbox["sul"]), abs(bbox["norte"]))
    dlon = km / (KM_POR_GRAU_LAT * max(math.cos(math.radians(lat_ref)), 0.05))
    return {
        "sul": max(-90.0, bbox["sul"] - dlat), "norte": min(90.0, bbox["norte"] + dlat),
        "oeste": max(-180.0, bbox["oeste"] - dlon), "leste": min(180.0, bbox["leste"] + dlon),
    }


class AnaliseModelo:

    @staticmethod
    def executar(bbox: Dict, buffers_km: List[float], n_simulacoes: int,
                 min_mag: Optional[float] = None, prof_max_km: Optional[float] = None,
                 inicio: Optional[str] = None, fim: Optional[str] = None,
                 fontes_falhas: Optional[List[str]] = None, semente: int = 42,
                 nome: Optional[str] = None, salvar: bool = True,
                 territorio: Optional[str] = None, incluir_sem_profundidade: bool = True) -> Dict:
        t0 = time.perf_counter()
        poligono = None
        if territorio:
            # Área de estudo = território (Brasil ou UF): a caixa passa a ser a que o envolve
            poligono = territorios.poligono(territorio)
            bbox = territorios.bbox(territorio)

        dados = EpicentroModelo.listar(bbox, min_mag, inicio, fim, limite=LIMITE_EPICENTROS)
        if dados["total"] > LIMITE_EPICENTROS:
            raise correlacao.ErroAnalise(
                f"A área tem {dados['total']} epicentros (limite {LIMITE_EPICENTROS}). "
                "Aumente a magnitude mínima ou reduza a área/período.")
        epicentros = dados["epicentros"]
        if poligono is not None and epicentros:
            dentro = shapely.contains_xy(poligono, [e["lon"] for e in epicentros], [e["lat"] for e in epicentros])
            epicentros = [e for e, d in zip(epicentros, dentro) if d]
        n_sem_prof = 0
        if prof_max_km is not None:
            n_sem_prof = sum(1 for e in epicentros if e["profundidade_km"] is None)
            # Sismos intraplaca (ex.: Brasil) costumam ter profundidade não determinada; são rasos
            epicentros = [e for e in epicentros
                          if (e["profundidade_km"] is None and incluir_sem_profundidade)
                          or (e["profundidade_km"] is not None and e["profundidade_km"] <= prof_max_km)]

        # Falhas logo fora da área também contam como "a mais próxima"
        falhas = FalhaModelo.para_analise(expandir_bbox(bbox, max(buffers_km)), fontes_falhas)

        cobertura = ImportacaoModelo.cobertura("epicentros", bbox, poligono)
        resultado = correlacao.analisar(epicentros, falhas, bbox, buffers_km, n_simulacoes, semente,
                                        cobertura_importada=cobertura, poligono=poligono)
        if n_sem_prof:
            if incluir_sem_profundidade:
                resultado["avisos"].append(f"{n_sem_prof} epicentros sem profundidade determinada foram tratados "
                                           "como rasos (comum em sismos intraplaca).")
            else:
                resultado["avisos"].append(f"{n_sem_prof} epicentros sem profundidade foram excluídos pelo filtro de profundidade.")

        parametros = {
            "bbox": bbox, "buffers_km": resultado["parametros"]["buffers_km"],
            "n_simulacoes": n_simulacoes, "semente": semente, "min_mag": min_mag,
            "prof_max_km": prof_max_km, "inicio": inicio, "fim": fim, "fontes_falhas": fontes_falhas,
            "territorio": territorio.upper() if territorio else None,
            "incluir_sem_profundidade": incluir_sem_profundidade,
        }
        resultado["parametros"].update(parametros)
        resultado["tempo_s"] = round(time.perf_counter() - t0, 2)

        if salvar:
            resultado["id"] = AnaliseModelo.salvar(nome or AnaliseModelo.nome_padrao(parametros, resultado),
                                                   parametros, resultado)
        return resultado

    @staticmethod
    def nome_padrao(parametros: Dict, resultado: Dict) -> str:
        if parametros.get("territorio"):
            return (f"{territorios.nome(parametros['territorio'])} · {resultado['n_epicentros']} eventos · "
                    f"{resultado['n_falhas']} falhas")
        b = parametros["bbox"]
        return (f"{resultado['n_epicentros']} eventos · {resultado['n_falhas']} falhas · "
                f"lat {b['sul']:.1f}/{b['norte']:.1f} lon {b['oeste']:.1f}/{b['leste']:.1f}")

    @staticmethod
    def salvar(nome: str, parametros: Dict, resultado: Dict) -> int:
        conn = get_db_connection()
        cursor = conn.cursor()
        valores = (nome, json.dumps(parametros), json.dumps(resultado))
        if is_using_postgres():
            cursor.execute(f"INSERT INTO analises (nome, parametros_json, resultado_json) "
                           f"VALUES ({ph()}, {ph()}, {ph()}) RETURNING id", valores)
            linha = cursor.fetchone()
            novo_id = linha["id"] if hasattr(linha, "keys") else linha[0]
        else:
            cursor.execute("INSERT INTO analises (nome, parametros_json, resultado_json) VALUES (?, ?, ?)", valores)
            novo_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return novo_id

    @staticmethod
    def zona_buffer(analise_id: int, km: float) -> Optional[Dict]:
        """Zona a até `km` das falhas usadas na análise (com as falhas atuais do banco).

        Guardada em memória: para o Brasil inteiro o cálculo leva ~10 s. A chave inclui a
        "versão" da tabela de falhas, então importar ou apagar falhas invalida o cache.
        """
        chave = (analise_id, float(km), FalhaModelo.versao())
        if chave not in _CACHE_ZONAS:
            if len(_CACHE_ZONAS) >= 32:
                _CACHE_ZONAS.pop(next(iter(_CACHE_ZONAS)))
            _CACHE_ZONAS[chave] = AnaliseModelo._calcular_zona(analise_id, km)
        return _CACHE_ZONAS[chave]

    @staticmethod
    def _calcular_zona(analise_id: int, km: float) -> Optional[Dict]:
        analise = AnaliseModelo.obter(analise_id)
        if analise is None:
            return None
        p = analise["parametros"]
        falhas = FalhaModelo.para_analise(expandir_bbox(p["bbox"], max(p["buffers_km"])), p.get("fontes_falhas"))
        poligono = territorios.poligono(p["territorio"]) if p.get("territorio") else None
        return {"km": km, "geometria": correlacao.zona_buffer(falhas, p["bbox"], km, poligono)}

    @staticmethod
    def obter(analise_id: int) -> Optional[Dict]:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(f"SELECT id, nome, resultado_json, criado_em FROM analises WHERE id = {ph()}", (analise_id,))
        linha = cursor.fetchone()
        conn.close()
        if not linha:
            return None
        linha = dict(linha)
        resultado = json.loads(linha["resultado_json"])
        resultado.update(id=linha["id"], nome=linha["nome"], criado_em=str(linha["criado_em"]))
        return resultado
