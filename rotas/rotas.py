from flask import Blueprint
from controle.mapa_controle import MapaControle

rotas_bp = Blueprint('rotas', __name__)

# Rota principal para carregar o mapa
@rotas_bp.route('/', methods=['GET'])
def index():
    return MapaControle.renderizar_pagina()

# Endpoints da API REST
@rotas_bp.route('/api/search', methods=['GET'])
def buscar():
    return MapaControle.pesquisar()

@rotas_bp.route('/api/reverse', methods=['GET'])
def reverso():
    return MapaControle.reverso()

@rotas_bp.route('/api/route', methods=['POST'])
def rota():
    return MapaControle.tracar_rota()

@rotas_bp.route('/api/history', methods=['GET'])
def get_historico():
    return MapaControle.consultar_historico()

@rotas_bp.route('/api/history', methods=['DELETE'])
def delete_historico():
    return MapaControle.apagar_historico()

@rotas_bp.route('/api/my-location', methods=['GET'])
def localizacao_atual():
    return MapaControle.obter_localizacao_atual()

