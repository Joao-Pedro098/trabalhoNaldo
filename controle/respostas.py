from flask import jsonify

def resposta_sucesso(dados=None, mensagem="Operação realizada com sucesso", status=200):
    """
    Padroniza respostas JSON de sucesso para o frontend.
    """
    payload = {
        "sucesso": True,
        "mensagem": mensagem
    }
    if dados is not None:
        if isinstance(dados, dict):
            payload.update(dados)
        else:
            payload["dados"] = dados
            
    return jsonify(payload), status

def resposta_erro(mensagem="Ocorreu um erro na requisição", status=400):
    """
    Padroniza respostas JSON de erro para o frontend.
    """
    return jsonify({
        "sucesso": False,
        "erro": mensagem
    }), status
