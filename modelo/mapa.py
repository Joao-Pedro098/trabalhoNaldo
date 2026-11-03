import requests
from typing import List, Dict, Any, Optional
from db.database import get_db_connection

NOMINATIM_URL = "https://nominatim.openstreetmap.org"
OSRM_URL = "http://router.project-osrm.org/route/v1/driving"
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
    def calcular_rota(origem_lat: float, origem_lon: float, dest_lat: float, dest_lon: float) -> Dict[str, Any]:
        """Calcula rota viária, distância, tempo e manobras com OSRM."""
        url = f"{OSRM_URL}/{origem_lon},{origem_lat};{dest_lon},{dest_lat}"
        params = {
            "overview": "full",
            "geometries": "geojson",
            "steps": "true"
        }

        try:
            resp = requests.get(url, params=params, timeout=10)
            data = resp.json()

            if data.get("code") != "Ok" or not data.get("routes"):
                return {"sucesso": False, "erro": "Nenhuma rota viária encontrada entre os pontos."}

            rota = data["routes"][0]
            distancia_m = rota.get("distance", 0)
            duracao_s = rota.get("duration", 0)
            geometria = rota.get("geometry", {}).get("coordinates", [])

            # Manobras passo a passo
            passos = []
            for leg in rota.get("legs", []):
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

            # Coordenadas [lat, lon] para Leaflet
            coordenadas = [[c[1], c[0]] for c in geometria]

            return {
                "sucesso": True,
                "distancia_km": round(distancia_m / 1000, 2),
                "distancia_formatada": MapaModelo._formatar_distancia(distancia_m),
                "duracao_minutos": round(duracao_s / 60),
                "duracao_formatada": MapaModelo._formatar_duracao(duracao_s),
                "coordenadas": coordenadas,
                "passos": passos
            }
        except Exception as e:
            return {"sucesso": False, "erro": f"Falha na comunicação com o serviço de rotas: {e}"}

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
        minutos = int(round(segundos / 60))
        if minutos < 60:
            return f"{minutos} min"
        horas = minutos // 60
        resto = minutos % 60
        return f"{horas} h {resto} min" if resto else f"{horas} h"
