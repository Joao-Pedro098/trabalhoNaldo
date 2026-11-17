from datetime import date

from flask import request

from controle.respostas import resposta_erro, resposta_sucesso
from modelo.epicentro import EpicentroModelo
from modelo.fontes import usgs
from modelo.importacao import ImportacaoModelo


class ErroValidacao(ValueError):
    pass


def ler_bbox(fonte) -> dict:
    """Lê sul/oeste/norte/leste de um dict (JSON ou query string) e valida."""
    try:
        bbox = {k: float(fonte.get(k)) for k in ("sul", "oeste", "norte", "leste")}
    except (TypeError, ValueError):
        raise ErroValidacao("Área inválida: informe sul, oeste, norte e leste numéricos.")
    if not (-90 <= bbox["sul"] < bbox["norte"] <= 90):
        raise ErroValidacao("Latitudes inválidas (sul deve ser menor que norte, entre -90 e 90).")
    if not (-180 <= bbox["oeste"] < bbox["leste"] <= 180):
        raise ErroValidacao("Longitudes inválidas (oeste deve ser menor que leste, entre -180 e 180).")
    return bbox


def ler_data(valor, nome: str) -> str:
    try:
        return date.fromisoformat(str(valor)).isoformat()
    except ValueError:
        raise ErroValidacao(f"Data '{nome}' inválida; use AAAA-MM-DD.")


def ler_magnitude(valor, padrao=None):
    if valor in (None, ""):
        return padrao
    try:
        mag = float(valor)
    except (TypeError, ValueError):
        raise ErroValidacao("Magnitude mínima deve ser numérica.")
    if not (-2 <= mag <= 10):
        raise ErroValidacao("Magnitude mínima fora do intervalo (-2 a 10).")
    return mag


class EpicentrosControle:

    @staticmethod
    def importar_usgs():
        dados = request.get_json(silent=True) or {}
        try:
            bbox = ler_bbox(dados.get("bbox") or {})
            inicio = ler_data(dados.get("inicio"), "início")
            fim = ler_data(dados.get("fim"), "fim")
            min_mag = ler_magnitude(dados.get("min_mag"), padrao=2.5)
        except ErroValidacao as e:
            return resposta_erro(str(e))
        if inicio > fim:
            return resposta_erro("A data de início é posterior à data de fim.")
        if fim > date.today().isoformat():
            fim = date.today().isoformat()

        total = usgs.contar(bbox, inicio, fim, min_mag)
        if total is not None and total > usgs.LIMITE_USGS:
            return resposta_erro(
                f"A consulta retornaria {total:,} eventos (limite da USGS: {usgs.LIMITE_USGS:,}). "
                "Aumente a magnitude mínima, reduza o período ou a área.".replace(",", ".")
            )

        try:
            registros = usgs.buscar(bbox, inicio, fim, min_mag)
        except usgs.ErroFonte as e:
            return resposta_erro(str(e), status=502)

        resultado = EpicentroModelo.salvar_lote(registros)
        # Registra a área consultada mesmo sem eventos: "nenhum sismo aqui" também é dado
        ImportacaoModelo.registrar("epicentros", "USGS", bbox,
                                   {"inicio": inicio, "fim": fim, "min_mag": min_mag}, len(registros))
        resultado["recebidos"] = len(registros)
        resultado["truncado"] = len(registros) >= usgs.LIMITE_USGS
        msg = (f"{len(registros)} eventos recebidos da USGS: "
               f"{resultado['novos']} novos, {resultado['atualizados']} já existiam.")
        return resposta_sucesso(resultado, mensagem=msg)

    @staticmethod
    def listar():
        args = request.args
        try:
            bbox = ler_bbox(args) if args.get("sul") is not None else None
            min_mag = ler_magnitude(args.get("min_mag"))
            inicio = ler_data(args["inicio"], "início") if args.get("inicio") else None
            fim = ler_data(args["fim"], "fim") if args.get("fim") else None
            limite = min(max(int(args.get("limite", 5000)), 1), 20000)
        except ErroValidacao as e:
            return resposta_erro(str(e))
        except ValueError:
            return resposta_erro("Parâmetro 'limite' deve ser inteiro.")
        return resposta_sucesso(EpicentroModelo.listar(bbox, min_mag, inicio, fim, limite))

    @staticmethod
    def resumo():
        return resposta_sucesso(EpicentroModelo.resumo())

    @staticmethod
    def apagar():
        apagados = EpicentroModelo.apagar_todos()
        return resposta_sucesso({"apagados": apagados}, mensagem=f"{apagados} epicentros apagados.")
