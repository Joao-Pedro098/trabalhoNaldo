from app import create_app

app = create_app()

if __name__ == '__main__':
    # 0.0.0.0 é fundamental para permitir acesso externo ou via Port Forwarding do VirtualBox
    print("=" * 60)
    print("📍 Mini Google Maps (Python + MVC) inicializado!")
    print("🌐 Acesse no seu navegador: http://localhost:5000")
    print("⚙️  Executando em 0.0.0.0:5000")
    print("=" * 60)
    app.run(host='0.0.0.0', port=5000, debug=True)
