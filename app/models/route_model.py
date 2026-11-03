import requests
from typing import Dict, Any, Optional

OSRM_BASE_URL = "http://router.project-osrm.org/route/v1/driving"

# Dicionário de tradução amigável para manobras do OSRM em Português
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

class RouteModel:
    """
    Model responsável pelo cálculo de rotas, distâncias,
    trajetos geográficos e instruções de navegação passo a passo (turn-by-turn).
    """

    @staticmethod
    def calculate_route(
        origin_lat: float, origin_lon: float,
        dest_lat: float, dest_lon: float
    ) -> Dict[str, Any]:
        """
        Calcula a rota rodoviária entre dois pontos usando o motor OSRM.
        """
        url = f"{OSRM_BASE_URL}/{origin_lon},{origin_lat};{dest_lon},{dest_lat}"
        params = {
            "overview": "full",
            "geometries": "geojson",
            "steps": "true"
        }

        try:
            response = requests.get(url, params=params, timeout=10)
            data = response.json()

            if data.get("code") != "Ok" or not data.get("routes"):
                return {
                    "success": False,
                    "error": "Não foi possível traçar uma rota entre estes dois locais."
                }

            best_route = data["routes"][0]
            distance_meters = best_route.get("distance", 0)
            duration_seconds = best_route.get("duration", 0)
            geometry = best_route.get("geometry", {}).get("coordinates", [])

            # Processa as instruções de direção passo a passo
            steps = []
            legs = best_route.get("legs", [])
            for leg in legs:
                for step in leg.get("steps", []):
                    instruction_text = RouteModel._format_instruction(step)
                    step_distance_m = step.get("distance", 0)
                    step_duration_s = step.get("duration", 0)
                    maneuver_loc = step.get("maneuver", {}).get("location", [])

                    steps.append({
                        "instruction": instruction_text,
                        "street_name": step.get("name") or "Via sem nome",
                        "distance_meters": round(step_distance_m),
                        "distance_formatted": RouteModel._format_distance(step_distance_m),
                        "duration_seconds": round(step_duration_s),
                        "location": [maneuver_loc[1], maneuver_loc[0]] if len(maneuver_loc) >= 2 else None
                    })

            # Inverte para [lat, lon] que é o padrão do Leaflet
            leaflet_coordinates = [[coord[1], coord[0]] for coord in geometry]

            return {
                "success": True,
                "distance_km": round(distance_meters / 1000, 2),
                "distance_formatted": RouteModel._format_distance(distance_meters),
                "duration_minutes": round(duration_seconds / 60),
                "duration_formatted": RouteModel._format_duration(duration_seconds),
                "coordinates": leaflet_coordinates,
                "steps": steps
            }

        except Exception as e:
            print(f"[RouteModel] Erro ao calcular rota: {e}")
            return {
                "success": False,
                "error": f"Erro de conexão com o serviço de rotas: {str(e)}"
            }

    @staticmethod
    def _format_instruction(step: Dict) -> str:
        """Gera um texto humanizado em português para cada manobra do caminho."""
        maneuver = step.get("maneuver", {})
        m_type = maneuver.get("type", "continue")
        modifier = maneuver.get("modifier", "")
        street_name = step.get("name")

        action = MANEUVER_TRANSLATIONS.get(m_type, "Siga em direção a")
        direction = MODIFIER_TRANSLATIONS.get(modifier, modifier)

        if m_type == "depart":
            return f"Inicie o percurso em {street_name or 'sua origem'}"
        if m_type == "arrive":
            return "Destino alcançado!"
        
        parts = [action]
        if direction:
            parts.append(direction)
        if street_name:
            parts.append(f"na {street_name}")

        return " ".join(parts)

    @staticmethod
    def _format_distance(meters: float) -> str:
        """Formata distância para metros ou quilômetros de maneira amigável."""
        if meters < 1000:
            return f"{round(meters)} m"
        return f"{meters / 1000:.1f} km"

    @staticmethod
    def _format_duration(seconds: float) -> str:
        """Formata duração em horas e minutos legíveis."""
        minutes = int(round(seconds / 60))
        if minutes < 60:
            return f"{minutes} min"
        hours = minutes // 60
        rem_min = minutes % 60
        if rem_min == 0:
            return f"{hours} h"
        return f"{hours} h {rem_min} min"
