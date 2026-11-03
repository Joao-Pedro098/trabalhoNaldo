import requests
from typing import List, Dict, Optional

NOMINATIM_BASE_URL = "https://nominatim.openstreetmap.org"
USER_AGENT = "MiniGoogleMapsPython/1.0 (TrabalhoAcademicoPython; contact=estudante@uf.br)"

class LocationModel:
    """
    Model responsável pela geocodificação (busca de locais por texto)
    e geocodificação reversa (coordenadas para endereço).
    """

    @staticmethod
    def search_address(query: str, limit: int = 5) -> List[Dict]:
        """
        Busca endereços a partir de um termo de pesquisa (texto).
        Retorna lista de locais com nome, latitude e longitude.
        """
        if not query or len(query.strip()) < 2:
            return []

        url = f"{NOMINATIM_BASE_URL}/search"
        params = {
            "q": query.strip(),
            "format": "json",
            "addressdetails": 1,
            "limit": limit
        }
        headers = {
            "User-Agent": USER_AGENT,
            "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8"
        }

        try:
            response = requests.get(url, params=params, headers=headers, timeout=6)
            if response.status_code == 200:
                results = response.json()
                parsed = []
                for item in results:
                    parsed.append({
                        "display_name": item.get("display_name"),
                        "lat": float(item.get("lat")),
                        "lon": float(item.get("lon")),
                        "type": item.get("type", "local"),
                        "address": item.get("address", {})
                    })
                return parsed
            return []
        except Exception as e:
            print(f"[LocationModel] Erro ao buscar endereço '{query}': {e}")
            return []

    @staticmethod
    def reverse_geocode(lat: float, lon: float) -> Optional[Dict]:
        """
        Converte coordenadas (latitude, longitude) no endereço legível mais próximo.
        """
        url = f"{NOMINATIM_BASE_URL}/reverse"
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
            response = requests.get(url, params=params, headers=headers, timeout=6)
            if response.status_code == 200:
                data = response.json()
                return {
                    "display_name": data.get("display_name", f"{lat:.5f}, {lon:.5f}"),
                    "lat": lat,
                    "lon": lon,
                    "address": data.get("address", {})
                }
            return {"display_name": f"{lat:.5f}, {lon:.5f}", "lat": lat, "lon": lon}
        except Exception as e:
            print(f"[LocationModel] Erro no reverse_geocode: {e}")
            return {"display_name": f"{lat:.5f}, {lon:.5f}", "lat": lat, "lon": lon}
