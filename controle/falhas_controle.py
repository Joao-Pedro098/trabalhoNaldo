import os

from flask import request

from controle.epicentros_controle import ErroValidacao, ler_bbox
from controle.respostas import resposta_erro, resposta_sucesso
from modelo.falha import FalhaModelo
from modelo.fontes import arquivo_falhas, gem
from modelo.fontes.geometria import ErroArquivo
from modelo.fontes.usgs import ErroFonte
from modelo.importacao import ImportacaoModelo

TAMANHO_MAX_FONTE = 80


def _plural(n: int, singular: str, plural: str) -> str:
    return f"{n} {singular if n == 1 else plural}"


class FalhasControle:

    @staticmethod
    def importar_gem():
        dados = request.get_json(silent=True) or {}
        try:
            bbox = ler_bbox(dados.get("bbox") or {})
        except ErroValidacao as e:
            return resposta_erro(str(e))
        try:
            registros = gem.buscar(bbox)
        except ErroFonte as e:
            return resposta_erro(str(e), status=502)

        ImportacaoModelo.registrar("falhas", gem.FONTE, bbox, None, len(registros))
        if not registros:
            return resposta_sucesso(
                {"novos": 0, "atualizados": 0, "recebidos": 0},
                mensagem="O GEM não tem falhas mapeadas nesta área. Para o Brasil, envie um "
                         "arquivo de falhas (ex.: SGB/CPRM) pelo upload.",
            )
        resultado = FalhaModelo.salvar_lote(registros)
        resultado["recebidos"] = len(registros)
        msg = (f"{len(registros)} falhas do GEM na área: "
               f"{resultado['novos']} novas, {resultado['atualizados']} já existiam.")
        return resposta_sucesso(resultado, mensagem=msg)

    @staticmethod
    def enviar_arquivo():
        arquivo = request.files.get("arquivo")
        if arquivo is None or not arquivo.filename:
            return resposta_erro("Nenhum arquivo enviado.")

        nome_base = os.path.splitext(os.path.basename(arquivo.filename))[0]
        fonte = (request.form.get("fonte") or nome_base).strip()[:TAMANHO_MAX_FONTE]
        if fonte == gem.FONTE:
            return resposta_erro(f"O nome de fonte '{gem.FONTE}' é reservado para a base do GEM.")

        try:
            registros, ignoradas = arquivo_falhas.ler(arquivo.filename, arquivo.read(), fonte)
        except ErroArquivo as e:
            return resposta_erro(str(e))

        resultado = FalhaModelo.salvar_lote(registros)
        extensao = {"sul": min(r["min_lat"] for r in registros), "norte": max(r["max_lat"] for r in registros),
                    "oeste": min(r["min_lon"] for r in registros), "leste": max(r["max_lon"] for r in registros)}
        ImportacaoModelo.registrar("falhas", fonte, extensao, {"arquivo": arquivo.filename}, len(registros))
        resultado.update(recebidos=len(registros), ignoradas=ignoradas, fonte=fonte)
        msg = (f"{_plural(len(registros), 'falha lida', 'falhas lidas')} de '{fonte}': "
               f"{resultado['novos']} novas, {resultado['atualizados']} já existiam.")
        if ignoradas:
            msg += f" {_plural(ignoradas, 'feição que não é linha foi ignorada', 'feições que não são linhas foram ignoradas')}."
        return resposta_sucesso(resultado, mensagem=msg)

    @staticmethod
    def listar():
        args = request.args
        try:
            bbox = ler_bbox(args) if args.get("sul") is not None else None
            limite = min(max(int(args.get("limite", 5000)), 1), 20000)
        except ErroValidacao as e:
            return resposta_erro(str(e))
        except ValueError:
            return resposta_erro("Parâmetro 'limite' deve ser inteiro.")
        return resposta_sucesso(FalhaModelo.listar(bbox, limite))

    @staticmethod
    def fontes():
        return resposta_sucesso({"fontes": FalhaModelo.fontes(), "atribuicao_gem": gem.ATRIBUICAO})

    @staticmethod
    def apagar():
        fonte = request.args.get("fonte") or None
        apagadas = FalhaModelo.apagar(fonte)
        alvo = f" da fonte '{fonte}'" if fonte else ""
        texto = _plural(apagadas, "falha apagada", "falhas apagadas")
        return resposta_sucesso({"apagadas": apagadas}, mensagem=f"{texto}{alvo}.")
