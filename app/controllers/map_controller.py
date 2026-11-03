from flask import Blueprint, render_template

map_blueprint = Blueprint('map_views', __name__)

@map_blueprint.route('/')
def index():
    """
    Controller que renderiza a View principal do sistema (estilo Google Maps).
    """
    return render_template('index.html')
