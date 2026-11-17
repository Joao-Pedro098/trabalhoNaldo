import os
from typing import Dict, List, Optional

import requests

NOMINATIM_URL = "https://nominatim.openstreetmap.org"
IP_API_URL = "http://ip-api.com/json"
USER_AGENT = os.getenv("APP_USER_AGENT", "SismoFalhas/0.1 (trabalho academico)")
HEADERS = {"User-Agent": USER_AGENT, "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8"}

# Ponto inicial quando não for possível localizar o usuário (centro do Brasil)
LOCAL_PADRAO = {"lat": -14.235, "lon": -51.925, "cidade": "Brasil", "display_name": "Brasil"}


class GeocodificacaoModelo:
    """Busca de regiões (para navegar o mapa) e localização aproximada por IP."""

    @staticmethod
    def buscar_regioes(termo: str, limite: int = 5) -> List[Dict]:
        """Busca lugares pelo nome no Nominatim. Inclui a caixa (bbox) da região."""
        if not termo or len(termo.strip()) < 2:
            return []
        params = {"q": termo.strip(), "format": "json", "limit": limite}
        try:
            resp = requests.get(f"{NOMINATIM_URL}/search", params=params, headers=HEADERS, timeout=6)
            resp.raise_for_status()
        except Exception as e:
            print(f"[Geocodificacao] Erro na busca: {e}")
            return []

        resultados = []
        for item in resp.json():
            bbox = item.get("boundingbox")  # [sul, norte, oeste, leste] como strings
            resultados.append({
                "display_name": item.get("display_name"),
                "lat": float(item["lat"]),
                "lon": float(item["lon"]),
                "bbox": [float(v) for v in bbox] if bbox and len(bbox) == 4 else None,
            })
        return resultados

    @staticmethod
    def geocodificar_reverso(lat: float, lon: float) -> Dict:
        """Nome do lugar a partir de coordenadas. Sempre retorna um dicionário."""
        padrao = {"display_name": f"{lat:.5f}, {lon:.5f}", "lat": lat, "lon": lon}
        params = {"lat": lat, "lon": lon, "format": "json", "zoom": 10}
        try:
            resp = requests.get(f"{NOMINATIM_URL}/reverse", params=params, headers=HEADERS, timeout=6)
            if resp.status_code == 200:
                nome = resp.json().get("display_name")
                if nome:
                    return {**padrao, "display_name": nome}
        except Exception as e:
            print(f"[Geocodificacao] Erro no reverso: {e}")
        return padrao

    @staticmethod
    def localizar_por_ip(ip: Optional[str] = None) -> Dict:
        """Localização aproximada pela rede (funciona sem HTTPS, ao contrário do GPS)."""
        local = ip and ip not in ("127.0.0.1", "localhost", "::1")
        url = f"{IP_API_URL}/{ip}" if local else f"{IP_API_URL}/"
        try:
            data = requests.get(url, timeout=5).json()
            if data.get("status") == "success":
                cidade = data.get("city") or "Minha região"
                regiao = data.get("regionName", "")
                return {
                    "lat": float(data["lat"]),
                    "lon": float(data["lon"]),
                    "cidade": cidade,
                    "display_name": f"{cidade}, {regiao}".strip(", "),
                    "aproximado": True,
                }
        except Exception as e:
            print(f"[Geocodificacao] Erro no IP-API: {e}")
        return {**LOCAL_PADRAO, "aproximado": True}
