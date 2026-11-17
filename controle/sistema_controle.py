from flask import render_template, request

from controle.respostas import resposta_erro, resposta_sucesso
from modelo import demo
from modelo.geocodificacao import GeocodificacaoModelo
from modelo.sistema import SistemaModelo


class SistemaControle:
    """Página principal, busca de regiões, localização e estado do sistema."""

    @staticmethod
    def renderizar_pagina():
        return render_template("index.html")

    @staticmethod
    def buscar_regiao():
        termo = request.args.get("q", "")
        return resposta_sucesso({"results": GeocodificacaoModelo.buscar_regioes(termo)})

    @staticmethod
    def reverso():
        try:
            lat = float(request.args.get("lat", ""))
            lon = float(request.args.get("lon", ""))
        except (TypeError, ValueError):
            return resposta_erro("Parâmetros 'lat' e 'lon' são obrigatórios e numéricos.")
        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
            return resposta_erro("Coordenadas fora do intervalo válido.")
        return resposta_sucesso(GeocodificacaoModelo.geocodificar_reverso(lat, lon))

    @staticmethod
    def localizacao_atual():
        ip = request.headers.get("X-Forwarded-For", request.remote_addr) or ""
        ip = ip.split(",")[0].strip()
        return resposta_sucesso(GeocodificacaoModelo.localizar_por_ip(ip))

    @staticmethod
    def status():
        try:
            return resposta_sucesso(SistemaModelo.resumo())
        except Exception as e:
            return resposta_erro(f"Falha ao consultar o banco: {e}", status=500)

    @staticmethod
    def carregar_demo():
        try:
            r = demo.carregar()
        except FileNotFoundError:
            return resposta_erro("Arquivos de demonstração não encontrados em data/demo.", status=500)
        msg = (f"Demonstração carregada ({r['regiao']}): {r['epicentros']['recebidos']} epicentros e "
               f"{r['falhas']['recebidos']} falhas.")
        return resposta_sucesso(r, mensagem=msg)

    @staticmethod
    def listar_analises():
        return resposta_sucesso({"analises": SistemaModelo.listar_analises()})

    @staticmethod
    def apagar_analises():
        SistemaModelo.limpar_analises()
        from modelo.analise import AnaliseModelo
        AnaliseModelo.esquecer()
        return resposta_sucesso(mensagem="Histórico de análises apagado.")
