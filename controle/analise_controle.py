from flask import Response, request

from controle.epicentros_controle import ErroValidacao, ler_bbox, ler_data, ler_magnitude
from controle.respostas import resposta_erro, resposta_sucesso
from modelo import exportacao, territorio as territorios
from modelo.analise import AnaliseModelo
from modelo.correlacao import ErroAnalise
from modelo.importacao import ImportacaoModelo
from modelo.sistema import SistemaModelo

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
            territorio = (dados.get("territorio") or "").strip().upper() or None
            if territorio:
                try:
                    territorios.poligono(territorio)
                except ValueError as e:
                    raise ErroValidacao(str(e))
                bbox = territorios.bbox(territorio)  # a caixa vem do território
            else:
                bbox = ler_bbox(dados.get("bbox") or {})
            if dados.get("area") == "importada" and not territorio:
                # Área exata das importações de sismos que cruzam a área visível
                bbox = ImportacaoModelo.area_importada("epicentros", bbox)
                if bbox is None:
                    raise ErroValidacao("Nenhuma importação de sismos registrada nesta região. "
                                        "Importe sismos ou use a área visível.")
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
                "territorio": territorio,
                "incluir_sem_profundidade": dados.get("incluir_sem_profundidade", True) is not False,
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
    def exportar(analise_id: int):
        formato = request.args.get("formato", "csv")
        resultado = AnaliseModelo.obter(analise_id)
        if resultado is None:
            return resposta_erro("Análise não encontrada.", status=404)
        if formato == "csv":
            corpo, tipo, ext = exportacao.csv_epicentros(resultado), "text/csv; charset=utf-8", "csv"
        elif formato == "geojson":
            corpo, tipo, ext = exportacao.geojson_texto(resultado), "application/geo+json; charset=utf-8", "geojson"
        elif formato == "json":
            corpo, tipo, ext = exportacao.json_completo(resultado), "application/json; charset=utf-8", "json"
        else:
            return resposta_erro("Formato inválido: use csv, geojson ou json.")
        nome = exportacao.nome_arquivo(resultado, ext)
        return Response(corpo, mimetype=tipo.split(";")[0], headers={
            "Content-Type": tipo, "Content-Disposition": f'attachment; filename="{nome}"'})

    @staticmethod
    def apagar(analise_id: int):
        if not SistemaModelo.apagar_analise(analise_id):
            return resposta_erro("Análise não encontrada.", status=404)
        return resposta_sucesso(mensagem="Análise apagada.")

    @staticmethod
    def territorios():
        return resposta_sucesso({"territorios": territorios.listar()})

    @staticmethod
    def contorno_territorio(codigo: str):
        try:
            return resposta_sucesso({"codigo": codigo.upper(), "nome": territorios.nome(codigo),
                                     "bbox": territorios.bbox(codigo), "geometria": territorios.geojson(codigo)})
        except (ValueError, KeyError):
            return resposta_erro("Território desconhecido.", status=404)

    @staticmethod
    def importacoes():
        tipo = request.args.get("tipo") or None
        return resposta_sucesso({"importacoes": ImportacaoModelo.listar(tipo)})

    @staticmethod
    def obter(analise_id: int):
        resultado = AnaliseModelo.obter(analise_id)
        if resultado is None:
            return resposta_erro("Análise não encontrada.", status=404)
        return resposta_sucesso({"resultado": resultado})
