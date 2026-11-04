from flask import Flask
from db.database import init_db
from rotas.rotas import rotas_bp

# Criação da aplicação Flask com templates e static na raiz (conforme padrão do projeto)
app = Flask(__name__, template_folder='templates', static_folder='static')
app.secret_key = 'mini-google-maps-naldo-key'

# Inicialização do banco de dados SQLite
init_db()

# Registro do Blueprint de rotas
app.register_blueprint(rotas_bp)

if __name__ == '__main__':
    print("=" * 60)
    print("📍 Mini Google Maps (Padrão Naldo) inicializado!")
    print("🌐 Acesse no seu navegador: https://192.168.0.147:5000")
    print("⚙️  Executando em 0.0.0.0:5000")
    print("=" * 60)
    app.run(host='0.0.0.0', port=5000, debug=True)
