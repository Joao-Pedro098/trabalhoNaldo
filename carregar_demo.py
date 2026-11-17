"""Carrega os dados de demonstração (Coquimbo, Chile) sem precisar de internet.

Uso:  python carregar_demo.py      (ou ./venv/bin/python3 carregar_demo.py na VM)
"""
from db.database import init_db, nome_backend
from modelo import demo

if __name__ == "__main__":
    init_db()
    r = demo.carregar()
    print(f"Banco: {nome_backend()}")
    print(f"Região: {r['regiao']}")
    print(f"Epicentros: {r['epicentros']['recebidos']} ({r['epicentros']['novos']} novos)")
    print(f"Falhas: {r['falhas']['recebidos']} ({r['falhas']['novos']} novas)")
    print("Pronto. Abra o sistema, vá à aba Análise e rode com 'Área importada'.")
