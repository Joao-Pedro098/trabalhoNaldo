# 🌋 SismoFalhas — Correlação espacial entre falhas e epicentros

Sistema web que cruza **falhas geológicas mapeadas** com **epicentros de sismos registrados** para responder à pergunta: *os sismos ocorrem mais perto das falhas do que o acaso explicaria?*

Feito sobre a mesma stack e o mesmo padrão MVC do PyMaps (trabalhoNaldo): Flask, Leaflet, PostgreSQL com fallback para SQLite, executado numa VM Ubuntu Server e acessado pelo navegador do Windows.

---

## 🏛️ Arquitetura

```text
sismoFalhas/
├── controle/                  # CONTROLLER
│   ├── sistema_controle.py    # Página, busca de região, localização, status, análises
│   └── respostas.py           # Respostas JSON padronizadas {sucesso, ...}
├── db/
│   └── database.py            # PostgreSQL ou SQLite; tabelas epicentros, falhas, analises
├── modelo/                    # MODEL
│   ├── geocodificacao.py      # Nominatim (busca/reverso) e localização por IP
│   └── sistema.py             # Contagens e análises salvas
├── rotas/
│   └── rotas.py               # Endpoints HTTP (Blueprint)
├── static/                    # CSS e JS (Leaflet)
├── templates/index.html       # VIEW
├── tests/                     # pytest
├── app.py                     # Ponto de entrada (porta 5000)
├── setup_vm.sh                # Instalação no Ubuntu Server
└── requirements.txt
```

## 🔌 Endpoints (Fase 0)

| Método | Rota | Descrição |
|---|---|---|
| GET | `/` | Interface web |
| GET | `/api/regioes?q=` | Busca de lugares (com caixa da região) |
| GET | `/api/reverso?lat=&lon=` | Nome do lugar nas coordenadas |
| GET | `/api/minha-localizacao` | Localização aproximada por IP |
| GET | `/api/status` | Banco em uso e contagem de registros |
| GET / DELETE | `/api/analises` | Lista / apaga análises salvas |

## 🗺️ Roteiro

| Fase | Entrega | Situação |
|---|---|---|
| 0 | Esqueleto, banco, interface base | ✅ |
| 1 | Importação de epicentros (USGS) e camada no mapa | ⏳ |
| 2 | Importação de falhas (GEM / upload GeoJSON) | ⏳ |
| 3 | Motor de correlação (distância, buffer, Monte Carlo, KS) | ⏳ |
| 4 | Interface de análise (área, gráficos, mapa de calor) | ⏳ |
| 5 | Análises salvas e exportação CSV/GeoJSON | ⏳ |
| 6 | Acabamento, dados de demonstração offline | ⏳ |

---

## 🚀 Como executar

### Ubuntu Server (VM)
```bash
chmod +x setup_vm.sh && ./setup_vm.sh
./venv/bin/python3 app.py
```

### Windows (desenvolvimento)
```bash
python -m venv venv
venv\Scripts\pip install -r requirements.txt
venv\Scripts\python app.py
```

Acesse **http://localhost:5000** (ou `http://<IP-da-VM>:5000`).

### Variáveis de ambiente (opcionais)

| Variável | Padrão | Uso |
|---|---|---|
| `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASS` | `localhost`, `5432`, `sismo_db`, `postgres`, `postgres` | PostgreSQL |
| `DB_BACKEND=sqlite` | — | Força SQLite sem tentar o Postgres |
| `DB_CONNECT_TIMEOUT` | `3` | Segundos esperando o Postgres antes do fallback |
| `SECRET_KEY` | aleatória | Chave do Flask |
| `FLASK_DEBUG=1` | desligado | Modo debug |
| `PORT` | `5000` | Porta HTTP |

### Testes
```bash
python -m pytest -q
```
