from flask import render_template, request
from modelo.mapa import MapaModelo
from controle.respostas import resposta_sucesso, resposta_erro

class MapaControle:
    """
    Camada de Controle: gerencia as requisições, orquestra o modelo e formata a resposta.
    """

    @staticmethod
    def renderizar_pagina():
        """Renderiza a View principal do sistema."""
        return render_template('index.html')

    @staticmethod
    def pesquisar():
        """Busca locais com base no termo digitado."""
        termo = request.args.get('q', '')
        if not termo:
            return resposta_sucesso({"results": []})
        
        resultados = MapaModelo.buscar_enderecos(termo)
        return resposta_sucesso({"results": resultados})

    @staticmethod
    def reverso():
        """Obtém endereço a partir de latitude e longitude."""
        try:
            lat = float(request.args.get('lat', ''))
            lon = float(request.args.get('lon', ''))
        except (ValueError, TypeError):
            return resposta_erro("Coordenadas 'lat' e 'lon' são obrigatórias e devem ser numéricas.")

        resultado = MapaModelo.geocodificar_reverso(lat, lon)
        return resposta_sucesso(resultado)

    @staticmethod
    def tracar_rota():
        """Calcula rota entre origem e destino e grava no histórico."""
        dados = request.get_json() or {}

        try:
            origem_lat = float(dados.get('origin_lat'))
            origem_lon = float(dados.get('origin_lon'))
            dest_lat = float(dados.get('dest_lat'))
            dest_lon = float(dados.get('dest_lon'))
        except (TypeError, ValueError):
            return resposta_erro("Coordenadas de origem ou destino inválidas.")

        origem_nome = dados.get('origin_name') or f"{origem_lat:.4f}, {origem_lon:.4f}"
        dest_nome = dados.get('dest_name') or f"{dest_lat:.4f}, {dest_lon:.4f}"
        modo = dados.get('modo', 'carro')

        resultado = MapaModelo.calcular_rota(origem_lat, origem_lon, dest_lat, dest_lon, modo=modo)

        if not resultado.get("sucesso"):
            return resposta_erro(resultado.get("erro", "Não foi possível traçar a rota."))

        # Salva a rota no banco SQLite
        try:
            MapaModelo.salvar_historico(
                origem_nome=origem_nome,
                origem_lat=origem_lat,
                origem_lon=origem_lon,
                dest_nome=dest_nome,
                dest_lat=dest_lat,
                dest_lon=dest_lon,
                distancia_km=resultado.get("distancia_km", 0),
                duracao_minutos=resultado.get("duracao_minutos", 0)
            )
        except Exception as e:
            print(f"[MapaControle] Aviso ao persistir histórico: {e}")

        return resposta_sucesso(resultado)

    @staticmethod
    def consultar_historico():
        """Retorna as últimas rotas pesquisadas."""
        historico = MapaModelo.listar_historico(limite=10)
        return resposta_sucesso({"history": historico})

    @staticmethod
    def apagar_historico():
        """Limpa o histórico de rotas salvas."""
        MapaModelo.limpar_historico()
        return resposta_sucesso(mensagem="Histórico apagado com sucesso.")

    @staticmethod
    def obter_localizacao_atual():
        """Obtém a localização atual por IP (garante funcionamento sem HTTPS)."""
        ip = request.headers.get('X-Forwarded-For', request.remote_addr)
        if ip and ',' in ip:
            ip = ip.split(',')[0].strip()
        resultado = MapaModelo.obter_localizacao_ip(ip)
        return resposta_sucesso(resultado)

