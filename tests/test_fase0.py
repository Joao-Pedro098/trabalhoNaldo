def test_pagina_principal(cliente):
    resp = cliente.get("/")
    assert resp.status_code == 200
    assert b"Falha Viva" in resp.data


def test_status_tabelas_vazias(cliente):
    data = cliente.get("/api/status").get_json()
    assert data["sucesso"] is True
    assert data["banco"] == "SQLite"
    assert data["contagens"] == {"epicentros": 0, "falhas": 0, "analises": 0}


def test_analises_lista_vazia_e_limpar(cliente):
    assert cliente.get("/api/analises").get_json()["analises"] == []
    assert cliente.delete("/api/analises").get_json()["sucesso"] is True


def test_reverso_valida_parametros(cliente):
    resp = cliente.get("/api/reverso?lat=abc&lon=1")
    assert resp.status_code == 400
    resp = cliente.get("/api/reverso?lat=95&lon=1")
    assert resp.status_code == 400


def test_busca_termo_curto_nao_chama_api(cliente):
    data = cliente.get("/api/regioes?q=a").get_json()
    assert data["results"] == []
