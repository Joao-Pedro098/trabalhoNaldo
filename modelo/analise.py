import json
import math
import time
from typing import Dict, List, Optional

from db.database import get_db_connection, is_using_postgres, ph
from modelo import correlacao
from modelo.epicentro import EpicentroModelo
from modelo.falha import FalhaModelo

LIMITE_EPICENTROS = 50_000
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
                 nome: Optional[str] = None, salvar: bool = True) -> Dict:
        t0 = time.perf_counter()

        dados = EpicentroModelo.listar(bbox, min_mag, inicio, fim, limite=LIMITE_EPICENTROS)
        if dados["total"] > LIMITE_EPICENTROS:
            raise correlacao.ErroAnalise(
                f"A área tem {dados['total']} epicentros (limite {LIMITE_EPICENTROS}). "
                "Aumente a magnitude mínima ou reduza a área/período.")
        epicentros = dados["epicentros"]
        n_sem_prof = 0
        if prof_max_km is not None:
            n_sem_prof = sum(1 for e in epicentros if e["profundidade_km"] is None)
            epicentros = [e for e in epicentros
                          if e["profundidade_km"] is not None and e["profundidade_km"] <= prof_max_km]

        # Falhas logo fora da área também contam como "a mais próxima"
        falhas = FalhaModelo.para_analise(expandir_bbox(bbox, max(buffers_km)), fontes_falhas)

        resultado = correlacao.analisar(epicentros, falhas, bbox, buffers_km, n_simulacoes, semente)
        if n_sem_prof:
            resultado["avisos"].append(f"{n_sem_prof} epicentros sem profundidade foram excluídos pelo filtro de profundidade.")

        parametros = {
            "bbox": bbox, "buffers_km": resultado["parametros"]["buffers_km"],
            "n_simulacoes": n_simulacoes, "semente": semente, "min_mag": min_mag,
            "prof_max_km": prof_max_km, "inicio": inicio, "fim": fim, "fontes_falhas": fontes_falhas,
        }
        resultado["parametros"].update(parametros)
        resultado["tempo_s"] = round(time.perf_counter() - t0, 2)

        if salvar:
            resultado["id"] = AnaliseModelo.salvar(nome or AnaliseModelo.nome_padrao(parametros, resultado),
                                                   parametros, resultado)
        return resultado

    @staticmethod
    def nome_padrao(parametros: Dict, resultado: Dict) -> str:
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
