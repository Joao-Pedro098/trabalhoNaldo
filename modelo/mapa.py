import requests
from typing import List, Dict, Any, Optional
from db.database import get_db_connection

NOMINATIM_URL = "https://nominatim.openstreetmap.org"
OSRM_BASE_URL = "http://router.project-osrm.org/route/v1"
USER_AGENT = "MiniGoogleMapsPython/1.0 (TrabalhoNaldo; contact=estudante@uf.br)"

MANEUVER_TRANSLATIONS = {
    "depart": "Partida",
    "arrive": "Você chegou ao seu destino",
    "turn": "Vire",
    "new name": "Continue na",
    "continue": "Continue em frente",
    "merge": "Acesse a via",
    "on ramp": "Pegue a alça de acesso",
    "off ramp": "Pegue a saída",
    "fork": "Na bifurcação, mantenha-se à",
    "end of road": "No final da rua, vire à",
    "roundabout": "Na rotatória, pegue a saída",
    "rotary": "Na rotatória, pegue a saída",
    "roundabout turn": "Na rotatória, vire",
    "notification": "Atenção"
}

MODIFIER_TRANSLATIONS = {
    "left": "à esquerda",
    "right": "à direita",
    "sharp left": "acentuadamente à esquerda",
    "sharp right": "acentuadamente à direita",
    "slight left": "ligeiramente à esquerda",
    "slight right": "ligeiramente à direita",
    "straight": "em frente",
    "uturn": "faça retorno"
}

class MapaModelo:
    """
    Camada de Modelo (Regras de negócio, cálculos e persistência).
    """

    @staticmethod
    def buscar_enderecos(termo: str, limite: int = 5) -> List[Dict]:
        """Busca endereços pelo texto usando a API Nominatim."""
        if not termo or len(termo.strip()) < 2:
            return []

        url = f"{NOMINATIM_URL}/search"
        params = {
            "q": termo.strip(),
            "format": "json",
            "addressdetails": 1,
            "limit": limite
        }
        headers = {
            "User-Agent": USER_AGENT,
            "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8"
        }

        try:
            resp = requests.get(url, params=params, headers=headers, timeout=6)
            if resp.status_code == 200:
                itens = resp.json()
                resultados = []
                for item in itens:
                    resultados.append({
                        "display_name": item.get("display_name"),
                        "lat": float(item.get("lat")),
                        "lon": float(item.get("lon"))
                    })
                return resultados
            return []
        except Exception as e:
            print(f"[MapaModelo] Erro na busca de endereços: {e}")
            return []

    @staticmethod
    def geocodificar_reverso(lat: float, lon: float) -> Dict:
        """Converte coordenadas para o endereço correspondente."""
        url = f"{NOMINATIM_URL}/reverse"
        params = {
            "lat": lat,
            "lon": lon,
            "format": "json",
            "addressdetails": 1
        }
        headers = {
            "User-Agent": USER_AGENT,
            "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8"
        }

        try:
            resp = requests.get(url, params=params, headers=headers, timeout=6)
            if resp.status_code == 200:
                data = resp.json()
                return {
                    "display_name": data.get("display_name", f"{lat:.5f}, {lon:.5f}"),
                    "lat": lat,
                    "lon": lon
                }
            return {"display_name": f"{lat:.5f}, {lon:.5f}", "lat": lat, "lon": lon}
        except Exception as e:
            print(f"[MapaModelo] Erro na geocodificação reversa: {e}")
            return {"display_name": f"{lat:.5f}, {lon:.5f}", "lat": lat, "lon": lon}

    @staticmethod
    def calcular_rota(origem_lat: float, origem_lon: float,
                      dest_lat: float, dest_lon: float,
                      modo: str = "carro") -> Dict[str, Any]:
        """
        Calcula rotas (incluindo alternativas e diferentes modais:
        carro, moto, transporte público, a pé, bicicleta).
        """
        # Mapeamento do modal para o perfil do OSRM
        perfil_osrm = "driving"
        fator_tempo = 1.0

        if modo in ("bicicleta", "bike"):
            perfil_osrm = "bike"
        elif modo in ("a_pe", "walk", "pe"):
            perfil_osrm = "foot"
        elif modo == "moto":
            perfil_osrm = "driving"
            fator_tempo = 0.85  # Motos no Brasil são ~15% mais ágeis no trânsito urbano
        elif modo == "transporte":
            perfil_osrm = "driving"
            fator_tempo = 1.40  # Ônibus com paradas e embarque

        url = f"{OSRM_BASE_URL}/{perfil_osrm}/{origem_lon},{origem_lat};{dest_lon},{dest_lat}"
        params = {
            "overview": "full",
            "geometries": "geojson",
            "steps": "true",
            "alternatives": "true"
        }

        try:
            resp = requests.get(url, params=params, timeout=10)
            data = resp.json()

            if data.get("code") != "Ok" or not data.get("routes"):
                return {"sucesso": False, "erro": "Nenhuma rota encontrada para este meio de transporte."}

            rotas_formatadas = []
            for idx, r in enumerate(data["routes"]):
                distancia_m = r.get("distance", 0)
                duracao_s = r.get("duration", 0) * fator_tempo
                geometria = r.get("geometry", {}).get("coordinates", [])

                # Resumo da rota (ex: "via Rod. Dr. Faisal Salmen")
                leg = r.get("legs", [{}])[0]
                summary_raw = leg.get("summary", "")
                if summary_raw:
                    via_nome = f"via {summary_raw}"
                else:
                    via_nome = f"Opção {idx + 1}"

                # Manobras passo a passo
                passos = []
                for step in leg.get("steps", []):
                    instrucao = MapaModelo._formatar_manobra(step)
                    m_dist = step.get("distance", 0)
                    maneuver_loc = step.get("maneuver", {}).get("location", [])

                    passos.append({
                        "instrucao": instrucao,
                        "rua": step.get("name") or "Via sem nome",
                        "distancia_formatada": MapaModelo._formatar_distancia(m_dist),
                        "localizacao": [maneuver_loc[1], maneuver_loc[0]] if len(maneuver_loc) >= 2 else None
                    })

                coordenadas = [[c[1], c[0]] for c in geometria]

                rotas_formatadas.append({
                    "id": idx,
                    "modo": modo,
                    "via": via_nome,
                    "descricao": "Rota mais rápida, com trânsito normal" if idx == 0 else "Rota alternativa",
                    "distancia_km": round(distancia_m / 1000, 2),
                    "distancia_formatada": MapaModelo._formatar_distancia(distancia_m),
                    "duracao_minutos": max(1, round(duracao_s / 60)),
                    "duracao_formatada": MapaModelo._formatar_duracao(duracao_s),
                    "coordenadas": coordenadas,
                    "passos": passos
                })

            # Calcula estimativa rápida dos outros modos para exibir nas abas do topo
            tempos_modos = MapaModelo._obter_estimativas_modais(origem_lat, origem_lon, dest_lat, dest_lon)

            # Rota principal é a primeira
            melhor_rota = rotas_formatadas[0]

            return {
                "sucesso": True,
                "modo_selecionado": modo,
                "melhor_rota": melhor_rota,
                "rotas": rotas_formatadas,
                "tempos_modais": tempos_modos,
                # Mantém retrocompatibilidade direta
                "distancia_km": melhor_rota["distancia_km"],
                "distancia_formatada": melhor_rota["distancia_formatada"],
                "duracao_minutos": melhor_rota["duracao_minutos"],
                "duracao_formatada": melhor_rota["duracao_formatada"],
                "coordenadas": melhor_rota["coordenadas"],
                "passos": melhor_rota["passos"]
            }
        except Exception as e:
            return {"sucesso": False, "erro": f"Falha na comunicação com o serviço de rotas: {e}"}

    @staticmethod
    def _obter_estimativas_modais(origem_lat: float, origem_lon: float,
                                  dest_lat: float, dest_lon: float) -> Dict[str, str]:
        """Obtém tempos estimados rápidos para exibir nos botões de modal do topo."""
        estimativas = {}
        try:
            # Consulta base de carro
            url = f"{OSRM_BASE_URL}/driving/{origem_lon},{origem_lat};{dest_lon},{dest_lat}?overview=false"
            r = requests.get(url, timeout=4).json()
            if r.get("routes"):
                segundos_carro = r["routes"][0].get("duration", 0)
                distancia_m = r["routes"][0].get("distance", 0)

                estimativas["carro"] = MapaModelo._formatar_duracao(segundos_carro)
                estimativas["moto"] = MapaModelo._formatar_duracao(segundos_carro * 0.85)
                estimativas["transporte"] = MapaModelo._formatar_duracao(segundos_carro * 1.40 + 300)
                
                # Velocidade média bicicleta: ~15 km/h
                segundos_bike = (distancia_m / 1000) / 15 * 3600
                estimativas["bicicleta"] = MapaModelo._formatar_duracao(segundos_bike)

                # Velocidade média a pé: ~4.5 km/h
                segundos_pe = (distancia_m / 1000) / 4.5 * 3600
                estimativas["a_pe"] = MapaModelo._formatar_duracao(segundos_pe)
        except Exception:
            pass
        return estimativas

    @staticmethod
    def salvar_historico(origem_nome: str, origem_lat: float, origem_lon: float,
                         dest_nome: str, dest_lat: float, dest_lon: float,
                         distancia_km: float, duracao_minutos: float) -> int:
        """Salva a rota no banco SQLite."""
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO historico_rotas 
            (origem_nome, origem_lat, origem_lon, destino_nome, destino_lat, destino_lon, distancia_km, duracao_minutos)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (origem_nome, origem_lat, origem_lon, dest_nome, dest_lat, dest_lon, distancia_km, duracao_minutos))
        novo_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return novo_id

    @staticmethod
    def listar_historico(limite: int = 10) -> List[Dict]:
        """Obtém as últimas rotas calculadas."""
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT id, origem_nome, origem_lat, origem_lon, destino_nome, destino_lat, destino_lon,
                   distancia_km, duracao_minutos, criado_em
            FROM historico_rotas
            ORDER BY id DESC LIMIT ?
        ''', (limite,))
        linhas = cursor.fetchall()
        conn.close()
        return [dict(l) for l in linhas]

    @staticmethod
    def limpar_historico() -> bool:
        """Apaga todo o histórico de rotas."""
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('DELETE FROM historico_rotas')
        conn.commit()
        conn.close()
        return True

    @staticmethod
    def _formatar_manobra(step: Dict) -> str:
        maneuver = step.get("maneuver", {})
        m_type = maneuver.get("type", "continue")
        modifier = maneuver.get("modifier", "")
        rua = step.get("name")

        acao = MANEUVER_TRANSLATIONS.get(m_type, "Siga em direção a")
        direcao = MODIFIER_TRANSLATIONS.get(modifier, modifier)

        if m_type == "depart":
            return f"Inicie o percurso em {rua or 'sua origem'}"
        if m_type == "arrive":
            return "Destino alcançado!"

        partes = [acao]
        if direcao: partes.append(direcao)
        if rua: partes.append(f"na {rua}")
        return " ".join(partes)

    @staticmethod
    def _formatar_distancia(metros: float) -> str:
        if metros < 1000:
            return f"{round(metros)} m"
        return f"{metros / 1000:.1f} km"

    @staticmethod
    def _formatar_duracao(segundos: float) -> str:
        minutos = max(1, int(round(segundos / 60)))
        if minutos < 60:
            return f"{minutos} min"
        horas = minutos // 60
        resto = minutos % 60
        return f"{horas} h {resto} min" if resto else f"{horas} h"
