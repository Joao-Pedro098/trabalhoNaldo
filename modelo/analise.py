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

LIMITE_EPICENTROS = 250_000
# A zona de buffer é desenhada numa projeção plana: acima desta extensão ela só é
# calculada para a parte visível do mapa (e só se a parte visível também for menor).
EXTENSAO_MAX_ZONA_KM = 3000
# Acima disso o resultado devolvido à interface vem sem a lista por epicentro (fica salva
# para exportação; o popup busca a distância de um evento sob demanda).
LIMITE_POR_EPICENTRO_NA_RESPOSTA = 20_000
_CACHE_ZONAS: Dict = {}
_CACHE_RESULTADOS: Dict = {}


def resumo_analise(resultado: Dict) -> Dict:
    return {"conclusao": resultado.get("conclusao"), "conclusao_titulo": resultado.get("conclusao_titulo"),
            "n_epicentros": resultado.get("n_epicentros"), "n_falhas": resultado.get("n_falhas"),
            "p_valor": (resultado.get("teste_mediana") or {}).get("p_valor")}
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
                 territorio: Optional[str] = None, incluir_sem_profundidade: bool = True,
                 fontes_epicentros: Optional[List[str]] = None, intraplaca_km: Optional[float] = None) -> Dict:
        t0 = time.perf_counter()
        poligono = None
        if territorio:
            # Área de estudo = território (Brasil ou UF): a caixa passa a ser a que o envolve
            poligono = territorios.poligono(territorio)
            bbox = territorios.bbox(territorio)

        dados = EpicentroModelo.listar(bbox, min_mag, inicio, fim, limite=LIMITE_EPICENTROS, fontes=fontes_epicentros)
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

        cobertura = ImportacaoModelo.cobertura("epicentros", bbox, poligono, fontes_epicentros)
        catalogos = sorted({e["fonte"] for e in epicentros})
        resultado = correlacao.analisar(epicentros, falhas, bbox, buffers_km, n_simulacoes, semente,
                                        cobertura_importada=cobertura, poligono=poligono,
                                        intraplaca_km=intraplaca_km)
        if len(catalogos) > 1:
            resultado["avisos"].append(
                f"Catálogos misturados ({', '.join(catalogos)}): o mesmo sismo pode aparecer em mais de um, "
                "com ids diferentes, e ser contado duas vezes. Escolha um único catálogo de sismos.")
        resultado["catalogos_epicentros"] = catalogos
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
            "fontes_epicentros": fontes_epicentros,
            "intraplaca_km": intraplaca_km,
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
        if b["sul"] <= -89.9 and b["norte"] >= 89.9 and b["oeste"] <= -179.9 and b["leste"] >= 179.9:
            intra = " · intraplaca" if parametros.get("intraplaca_km") else ""
            return f"Mundo inteiro{intra} · {resultado['n_epicentros']} eventos · {resultado['n_falhas']} falhas"
        return (f"{resultado['n_epicentros']} eventos · {resultado['n_falhas']} falhas · "
                f"lat {b['sul']:.1f}/{b['norte']:.1f} lon {b['oeste']:.1f}/{b['leste']:.1f}")

    @staticmethod
    def salvar(nome: str, parametros: Dict, resultado: Dict) -> int:
        conn = get_db_connection()
        cursor = conn.cursor()
        valores = (nome, json.dumps(parametros), json.dumps(resultado), json.dumps(resumo_analise(resultado)))
        if is_using_postgres():
            cursor.execute(f"INSERT INTO analises (nome, parametros_json, resultado_json, resumo_json) "
                           f"VALUES ({ph()}, {ph()}, {ph()}, {ph()}) RETURNING id", valores)
            linha = cursor.fetchone()
            novo_id = linha["id"] if hasattr(linha, "keys") else linha[0]
        else:
            cursor.execute("INSERT INTO analises (nome, parametros_json, resultado_json, resumo_json) "
                           "VALUES (?, ?, ?, ?)", valores)
            novo_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return novo_id

    @staticmethod
    def zona_buffer(analise_id: int, km: float, vista: Optional[Dict] = None) -> Optional[Dict]:
        """Zona a até `km` das falhas usadas na análise (com as falhas atuais do banco).

        Para análises muito extensas (ex.: o mundo) a zona é calculada só para a `vista`
        (área visível do mapa). Guardada em memória; a chave inclui a "versão" da tabela de
        falhas, então importar ou apagar falhas invalida o cache.
        """
        analise_p = AnaliseModelo._parametros(analise_id)
        if analise_p is None:
            return None
        area = analise_p["bbox"]
        if correlacao.extensao_bbox_km(area) > EXTENSAO_MAX_ZONA_KM:
            if vista is None:
                return {"km": km, "geometria": None, "precisa_vista": True,
                        "mensagem": "Área grande: a zona é desenhada só para a região visível do mapa."}
            area = {"sul": max(area["sul"], vista["sul"]), "norte": min(area["norte"], vista["norte"]),
                    "oeste": max(area["oeste"], vista["oeste"]), "leste": min(area["leste"], vista["leste"])}
            if area["sul"] >= area["norte"] or area["oeste"] >= area["leste"]:
                return {"km": km, "geometria": None}
            if correlacao.extensao_bbox_km(area) > EXTENSAO_MAX_ZONA_KM:
                return {"km": km, "geometria": None, "precisa_vista": True,
                        "mensagem": "Aproxime o mapa para ver a zona em volta das falhas."}
            area = {k: round(v, 2) for k, v in area.items()}
        chave = (analise_id, float(km), tuple(sorted(area.items())), FalhaModelo.versao())
        if chave not in _CACHE_ZONAS:
            if len(_CACHE_ZONAS) >= 32:
                _CACHE_ZONAS.pop(next(iter(_CACHE_ZONAS)))
            _CACHE_ZONAS[chave] = AnaliseModelo._calcular_zona(analise_p, km, area)
        return _CACHE_ZONAS[chave]

    @staticmethod
    def _parametros(analise_id: int) -> Optional[Dict]:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(f"SELECT parametros_json FROM analises WHERE id = {ph()}", (analise_id,))
        linha = cursor.fetchone()
        conn.close()
        if not linha:
            return None
        return json.loads(linha["parametros_json"] if hasattr(linha, "keys") else linha[0])

    @staticmethod
    def _calcular_zona(p: Dict, km: float, area: Dict) -> Dict:
        falhas = FalhaModelo.para_analise(expandir_bbox(area, max(p["buffers_km"])), p.get("fontes_falhas"))
        poligono = territorios.poligono(p["territorio"]) if p.get("territorio") else None
        return {"km": km, "geometria": correlacao.zona_buffer(falhas, area, km, poligono)}

    @staticmethod
    def obter_para_interface(analise_id: int) -> Optional[Dict]:
        """Resultado para o navegador: sem a lista por epicentro quando ela é muito grande."""
        resultado = AnaliseModelo.obter(analise_id)
        if resultado is None:
            return None
        n = len(resultado.get("por_epicentro") or [])
        if n > LIMITE_POR_EPICENTRO_NA_RESPOSTA:
            resultado = {**resultado, "por_epicentro": [], "por_epicentro_omitido": n}
        return resultado

    @staticmethod
    def epicentro(analise_id: int, epicentro_id) -> Optional[Dict]:
        """Distância e ponto na falha de um epicentro da análise (para o popup)."""
        if analise_id not in _CACHE_RESULTADOS:
            if len(_CACHE_RESULTADOS) >= 2:
                _CACHE_RESULTADOS.pop(next(iter(_CACHE_RESULTADOS)))
            resultado = AnaliseModelo.obter(analise_id)
            if resultado is None:
                return None
            _CACHE_RESULTADOS[analise_id] = {str(p.get("id")): p for p in resultado.get("por_epicentro") or []}
        return _CACHE_RESULTADOS[analise_id].get(str(epicentro_id))

    @staticmethod
    def esquecer(analise_id: Optional[int] = None) -> None:
        """Limpa os caches de uma análise apagada (ou de todas)."""
        if analise_id is None:
            _CACHE_RESULTADOS.clear(); _CACHE_ZONAS.clear()
        else:
            _CACHE_RESULTADOS.pop(analise_id, None)
            for chave in [c for c in _CACHE_ZONAS if c[0] == analise_id]:
                _CACHE_ZONAS.pop(chave)

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
