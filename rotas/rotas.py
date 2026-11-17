from flask import Blueprint

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


# ---- Estado do sistema ----
@rotas_bp.route("/api/status", methods=["GET"])
def status():
    return SistemaControle.status()


# ---- Análises salvas (preenchidas a partir da Fase 5) ----
@rotas_bp.route("/api/analises", methods=["GET"])
def listar_analises():
    return SistemaControle.listar_analises()


@rotas_bp.route("/api/analises", methods=["DELETE"])
def apagar_analises():
    return SistemaControle.apagar_analises()
