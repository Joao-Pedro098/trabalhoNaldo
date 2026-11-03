from flask import Blueprint, request, jsonify
from app.models.location_model import LocationModel
from app.models.route_model import RouteModel
from app.models.history_model import HistoryModel

api_blueprint = Blueprint('api', __name__, url_prefix='/api')

@api_blueprint.route('/search', methods=['GET'])
def search_location():
    """
    Busca endereços e coordenadas baseados no termo de pesquisa.
    Ex: /api/search?q=Avenida+Paulista
    """
    query = request.args.get('q', '')
    if not query:
        return jsonify({"results": []}), 200
    
    results = LocationModel.search_address(query, limit=5)
    return jsonify({"results": results}), 200


@api_blueprint.route('/reverse', methods=['GET'])
def reverse_geocode():
    """
    Obtém o endereço a partir de latitude e longitude.
    Ex: /api/reverse?lat=-23.5505&lon=-46.6333
    """
    try:
        lat = float(request.args.get('lat', ''))
        lon = float(request.args.get('lon', ''))
    except (ValueError, TypeError):
        return jsonify({"error": "Parâmetros 'lat' e 'lon' inválidos."}), 400

    result = LocationModel.reverse_geocode(lat, lon)
    return jsonify(result), 200


@api_blueprint.route('/route', methods=['POST'])
def calculate_route():
    """
    Calcula o trajeto entre o ponto de origem e destino,
    retornando as coordenadas, tempo, distância e direções passo a passo.
    """
    data = request.get_json() or {}

    try:
        origin_lat = float(data.get('origin_lat'))
        origin_lon = float(data.get('origin_lon'))
        dest_lat = float(data.get('dest_lat'))
        dest_lon = float(data.get('dest_lon'))
    except (TypeError, ValueError):
        return jsonify({
            "success": False,
            "error": "Coordenadas de origem ou destino inválidas."
        }), 400

    origin_name = data.get('origin_name') or f"{origin_lat:.4f}, {origin_lon:.4f}"
    dest_name = data.get('dest_name') or f"{dest_lat:.4f}, {dest_lon:.4f}"

    # Chama o Model responsável pela rota
    route_result = RouteModel.calculate_route(origin_lat, origin_lon, dest_lat, dest_lon)

    if route_result.get("success"):
        # Salva a rota calculada no banco de dados
        try:
            HistoryModel.save_route(
                origin_name=origin_name,
                origin_lat=origin_lat,
                origin_lon=origin_lon,
                dest_name=dest_name,
                dest_lat=dest_lat,
                dest_lon=dest_lon,
                distance_km=route_result.get("distance_km", 0),
                duration_minutes=route_result.get("duration_minutes", 0)
            )
        except Exception as e:
            print(f"[ApiController] Aviso ao salvar histórico: {e}")

    return jsonify(route_result), 200 if route_result.get("success") else 400


@api_blueprint.route('/history', methods=['GET'])
def get_history():
    """Retorna as últimas rotas calculadas."""
    history = HistoryModel.get_recent_routes(limit=10)
    return jsonify({"history": history}), 200


@api_blueprint.route('/history', methods=['DELETE'])
def clear_history():
    """Limpa todo o histórico gravado."""
    HistoryModel.clear_history()
    return jsonify({"success": True, "message": "Histórico limpo com sucesso."}), 200
