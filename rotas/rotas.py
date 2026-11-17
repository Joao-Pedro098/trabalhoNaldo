from flask import Blueprint

from controle.analise_controle import AnaliseControle
from controle.epicentros_controle import EpicentrosControle
from controle.falhas_controle import FalhasControle
from controle.sistema_controle import SistemaControle

rotas_bp = Blueprint("rotas", __name__)


@rotas_bp.route("/", methods=["GET"])
def index():
    return SistemaControle.renderizar_pagina()


# ---- Navegação no mapa ----
@rotas_bp.route("/api/regioes", methods=["GET"])
def buscar_regiao():
    return SistemaControle.buscar_regiao()


@rotas_bp.route("/api/reverso", methods=["GET"])
def reverso():
    return SistemaControle.reverso()


@rotas_bp.route("/api/minha-localizacao", methods=["GET"])
def minha_localizacao():
    return SistemaControle.localizacao_atual()


# ---- Dados de demonstração (offline) ----
@rotas_bp.route("/api/demo", methods=["POST"])
def carregar_demo():
    return SistemaControle.carregar_demo()


# ---- Estado do sistema ----
@rotas_bp.route("/api/status", methods=["GET"])
def status():
    return SistemaControle.status()


# ---- Epicentros ----
@rotas_bp.route("/api/epicentros/importar", methods=["POST"])
def importar_epicentros():
    return EpicentrosControle.importar_usgs()


@rotas_bp.route("/api/epicentros", methods=["GET"])
def listar_epicentros():
    return EpicentrosControle.listar()


@rotas_bp.route("/api/epicentros/fontes", methods=["GET"])
def fontes_epicentros():
    return EpicentrosControle.fontes()


@rotas_bp.route("/api/epicentros/resumo", methods=["GET"])
def resumo_epicentros():
    return EpicentrosControle.resumo()


@rotas_bp.route("/api/epicentros", methods=["DELETE"])
def apagar_epicentros():
    return EpicentrosControle.apagar()


# ---- Falhas ----
@rotas_bp.route("/api/falhas/importar-gem", methods=["POST"])
def importar_falhas_gem():
    return FalhasControle.importar_gem()


@rotas_bp.route("/api/falhas/importar-sgb", methods=["POST"])
def importar_falhas_sgb():
    return FalhasControle.importar_sgb()


@rotas_bp.route("/api/falhas/upload", methods=["POST"])
def enviar_falhas():
    return FalhasControle.enviar_arquivo()


@rotas_bp.route("/api/falhas", methods=["GET"])
def listar_falhas():
    return FalhasControle.listar()


@rotas_bp.route("/api/falhas/fontes", methods=["GET"])
def fontes_falhas():
    return FalhasControle.fontes()


@rotas_bp.route("/api/falhas", methods=["DELETE"])
def apagar_falhas():
    return FalhasControle.apagar()


# ---- Análise de correlação ----
@rotas_bp.route("/api/analise", methods=["POST"])
def executar_analise():
    return AnaliseControle.executar()


@rotas_bp.route("/api/analises/<int:analise_id>", methods=["GET"])
def obter_analise(analise_id):
    return AnaliseControle.obter(analise_id)


@rotas_bp.route("/api/analises/<int:analise_id>", methods=["DELETE"])
def apagar_analise(analise_id):
    return AnaliseControle.apagar(analise_id)


@rotas_bp.route("/api/analises/<int:analise_id>/epicentros/<epicentro_id>", methods=["GET"])
def epicentro_da_analise(analise_id, epicentro_id):
    return AnaliseControle.epicentro(analise_id, epicentro_id)


@rotas_bp.route("/api/analises/<int:analise_id>/exportar", methods=["GET"])
def exportar_analise(analise_id):
    return AnaliseControle.exportar(analise_id)


@rotas_bp.route("/api/territorios", methods=["GET"])
def listar_territorios():
    return AnaliseControle.territorios()


@rotas_bp.route("/api/territorios/<codigo>", methods=["GET"])
def contorno_territorio(codigo):
    return AnaliseControle.contorno_territorio(codigo)


@rotas_bp.route("/api/importacoes", methods=["GET"])
def listar_importacoes():
    return AnaliseControle.importacoes()


@rotas_bp.route("/api/analises/<int:analise_id>/buffer", methods=["GET"])
def zona_buffer_analise(analise_id):
    return AnaliseControle.zona_buffer(analise_id)


# ---- Análises salvas (preenchidas a partir da Fase 5) ----
@rotas_bp.route("/api/analises", methods=["GET"])
def listar_analises():
    return SistemaControle.listar_analises()


@rotas_bp.route("/api/analises", methods=["DELETE"])
def apagar_analises():
    return SistemaControle.apagar_analises()
