from flask import request

from controle.epicentros_controle import ErroValidacao, ler_bbox, ler_data, ler_magnitude
from controle.respostas import resposta_erro, resposta_sucesso
from modelo.analise import AnaliseModelo
from modelo.correlacao import ErroAnalise

BUFFERS_PADRAO = [5, 10, 20, 50]


def _ler_buffers(valor):
    if valor in (None, ""):
        return BUFFERS_PADRAO
    if isinstance(valor, str):
        valor = valor.split(",")
    try:
        buffers = sorted({float(v) for v in valor})
    except (TypeError, ValueError):
        raise ErroValidacao("Buffers devem ser números em km (ex.: [5, 10, 20, 50]).")
    if not buffers or len(buffers) > 8 or buffers[0] <= 0 or buffers[-1] > 500:
        raise ErroValidacao("Informe de 1 a 8 buffers entre 0 e 500 km.")
    return buffers


def _ler_numero(valor, nome, minimo, maximo, inteiro=False):
    if valor in (None, ""):
        return None
    try:
        numero = int(valor) if inteiro else float(valor)
    except (TypeError, ValueError):
        raise ErroValidacao(f"'{nome}' deve ser numérico.")
    if not minimo <= numero <= maximo:
        raise ErroValidacao(f"'{nome}' deve ficar entre {minimo} e {maximo}.")
    return numero


class AnaliseControle:

    @staticmethod
    def executar():
        dados = request.get_json(silent=True) or {}
        try:
            bbox = ler_bbox(dados.get("bbox") or {})
            fontes = dados.get("fontes_falhas") or None
            if fontes is not None and not (isinstance(fontes, list) and all(isinstance(f, str) for f in fontes)):
                raise ErroValidacao("'fontes_falhas' deve ser uma lista de nomes de fonte.")
            parametros = {
                "bbox": bbox,
                "buffers_km": _ler_buffers(dados.get("buffers_km")),
                "n_simulacoes": _ler_numero(dados.get("n_simulacoes"), "n_simulacoes", 99, 9999, inteiro=True) or 999,
                "min_mag": ler_magnitude(dados.get("min_mag")),
                "prof_max_km": _ler_numero(dados.get("prof_max_km"), "prof_max_km", 0, 800),
                "inicio": ler_data(dados["inicio"], "início") if dados.get("inicio") else None,
                "fim": ler_data(dados["fim"], "fim") if dados.get("fim") else None,
                "fontes_falhas": fontes,
                "semente": _ler_numero(dados.get("semente"), "semente", 0, 2**31 - 1, inteiro=True) or 42,
                "nome": (dados.get("nome") or "").strip()[:120] or None,
                "salvar": dados.get("salvar", True) is not False,
            }
        except ErroValidacao as e:
            return resposta_erro(str(e))

        try:
            resultado = AnaliseModelo.executar(**parametros)
        except ErroAnalise as e:
            return resposta_erro(str(e), status=422)
        return resposta_sucesso({"resultado": resultado}, mensagem="Análise concluída.")

    @staticmethod
    def zona_buffer(analise_id: int):
        try:
            km = _ler_numero(request.args.get("km"), "km", 0.1, 500)
        except ErroValidacao as e:
            return resposta_erro(str(e))
        if km is None:
            return resposta_erro("Informe 'km'.")
        zona = AnaliseModelo.zona_buffer(analise_id, km)
        if zona is None:
            return resposta_erro("Análise não encontrada.", status=404)
        return resposta_sucesso(zona)

    @staticmethod
    def obter(analise_id: int):
        resultado = AnaliseModelo.obter(analise_id)
        if resultado is None:
            return resposta_erro("Análise não encontrada.", status=404)
        return resposta_sucesso({"resultado": resultado})
