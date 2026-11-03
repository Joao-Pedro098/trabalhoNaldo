# 🗺️ PyMaps - Mini Google Maps em Python (Padrão MVC Naldo)

Sistema interativo de mapas, busca de endereços e cálculo de rotas em tempo real com direções passo a passo (turn-by-turn), desenvolvido para rodar dentro de uma Máquina Virtual (**Ubuntu Server**) e ser acessado através do navegador no computador hospedeiro (**Windows**).

---

## 🏛️ Arquitetura do Projeto

Estruturado exatamente no padrão requerido:

```text
TrabalhoNaldo/
│
├── controle/                 # CONTROLLER: Gerenciamento e orquestração das requisições
│   ├── mapa_controle.py      # Lógica de controle do mapa, busca e rotas
│   └── respostas.py          # Padronização de respostas JSON (sucesso/erro)
│
├── db/                       # BANCO DE DADOS: Persistência SQLite
│   └── database.py           # Conexão e criação das tabelas
│
├── modelo/                   # MODEL: Regras de negócio, cálculos e integrações
│   └── mapa.py               # Geocodificação (Nominatim), rotas (OSRM) e histórico
│
├── rotas/                    # ROTAS: Mapeamento dos endpoints HTTP (Blueprint)
│   └── rotas.py              # Definição das rotas e delegação para o controle
│
├── static/                   # ARQUIVOS ESTÁTICOS
│   ├── css/
│   │   └── style.css         # Estilização estilo Google Maps
│   ├── img/                  # Imagens e ícones
│   └── js/
│       └── map.js            # Lógica do Leaflet.js no navegador
│
├── templates/                # VIEW: Telas HTML
│   └── index.html            # Interface web completa
│
├── app.py                    # Ponto de entrada da aplicação (executa na porta 5000)
├── setup_vm.sh               # Script para instalar dependências no Ubuntu Server
├── requirements.txt          # Dependências Python (Flask, requests, geopy)
└── README.md
```

---

## 🚀 Como Atualizar e Executar no Ubuntu Server

### 1. Parar o servidor atual na VM
No PowerShell onde o servidor está rodando, pressione:
`Ctrl + C`

### 2. Puxar as atualizações do GitHub
```bash
git pull origin main
```

### 3. Iniciar a aplicação
```bash
./venv/bin/python3 app.py
```

---

## 🌐 Acesso no Navegador (Windows)
Acesse: 👉 **[http://localhost:5000](http://localhost:5000)**
