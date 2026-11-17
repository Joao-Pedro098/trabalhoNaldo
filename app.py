import os
import secrets
import sys

from flask import Flask

from controle.respostas import resposta_erro
from db.database import init_db, nome_backend
from rotas.rotas import rotas_bp

# Consoles do Windows (cp1252) quebram com acentos fora da tabela; evita o crash.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(errors="replace")


def criar_app() -> Flask:
    app = Flask(__name__, template_folder="templates", static_folder="static")
    # Defina SECRET_KEY no ambiente em produção; sem ela, gera uma chave por execução.
    app.secret_key = os.getenv("SECRET_KEY") or secrets.token_hex(32)
    # Limite de upload (arquivos de falhas): 50 MB
    app.config["MAX_CONTENT_LENGTH"] = 50 * 1024 * 1024
    init_db()
    app.register_blueprint(rotas_bp)

    @app.errorhandler(413)
    def arquivo_grande(_erro):
        return resposta_erro("Arquivo maior que o limite de 50 MB.", status=413)

    return app


app = criar_app()

if __name__ == "__main__":
    porta = int(os.getenv("PORT", "5000"))
    debug = os.getenv("FLASK_DEBUG", "0") == "1"
    print("=" * 60)
    print("SismoFalhas - correlacao entre falhas e epicentros")
    print(f"Banco: {nome_backend()}")
    print(f"Acesse: http://localhost:{porta} (ou http://<IP-da-VM>:{porta})")
    print("=" * 60)
    app.run(host="0.0.0.0", port=porta, debug=debug)
