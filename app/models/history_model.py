from typing import List, Dict, Any
from app.models.database import get_db_connection

class HistoryModel:
    """
    Model para persistência e consulta do histórico de buscas e rotas calculadas.
    """

    @staticmethod
    def save_route(
        origin_name: str, origin_lat: float, origin_lon: float,
        dest_name: str, dest_lat: float, dest_lon: float,
        distance_km: float, duration_minutes: float
    ) -> int:
        """Salva uma rota recém-calculada no histórico."""
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO route_history 
            (origin_name, origin_lat, origin_lon, dest_name, dest_lat, dest_lon, distance_km, duration_minutes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            origin_name, origin_lat, origin_lon,
            dest_name, dest_lat, dest_lon,
            distance_km, duration_minutes
        ))
        
        route_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return route_id

    @staticmethod
    def get_recent_routes(limit: int = 10) -> List[Dict[str, Any]]:
        """Recupera as últimas rotas calculadas."""
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT id, origin_name, origin_lat, origin_lon,
                   dest_name, dest_lat, dest_lon,
                   distance_km, duration_minutes, created_at
            FROM route_history
            ORDER BY id DESC
            LIMIT ?
        ''', (limit,))
        
        rows = cursor.fetchall()
        conn.close()
        
        return [dict(row) for row in rows]

    @staticmethod
    def clear_history() -> bool:
        """Limpa todo o histórico de rotas."""
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('DELETE FROM route_history')
        conn.commit()
        conn.close()
        return True
