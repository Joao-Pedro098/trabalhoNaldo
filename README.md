# 🌋 SismoFalhas — Correlação espacial entre falhas e epicentros

Sistema web que cruza **falhas geológicas mapeadas** com **epicentros de sismos registrados** para responder à pergunta: *os sismos ocorrem mais perto das falhas do que o acaso explicaria?*

Feito sobre a mesma stack e o mesmo padrão MVC do PyMaps (trabalhoNaldo): Flask, Leaflet, PostgreSQL com fallback para SQLite, executado numa VM Ubuntu Server e acessado pelo navegador do Windows.

---

## 🏛️ Arquitetura

```text
sismoFalhas/
├── controle/                  # CONTROLLER
│   ├── sistema_controle.py    # Página, busca de região, localização, status, análises
│   ├── epicentros_controle.py # Importação/consulta de epicentros (com validação)
│   └── respostas.py           # Respostas JSON padronizadas {sucesso, ...}
├── db/
│   └── database.py            # PostgreSQL ou SQLite; tabelas epicentros, falhas, analises
├── modelo/                    # MODEL
│   ├── geocodificacao.py      # Nominatim (busca/reverso) e localização por IP
│   ├── epicentro.py           # Persistência e consultas de epicentros
│   ├── fontes/usgs.py         # Cliente do catálogo FDSN da USGS
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

## 🔌 Endpoints

| Método | Rota | Descrição |
|---|---|---|
| GET | `/` | Interface web |
| GET | `/api/regioes?q=` | Busca de lugares (com caixa da região) |
| GET | `/api/reverso?lat=&lon=` | Nome do lugar nas coordenadas |
| GET | `/api/minha-localizacao` | Localização aproximada por IP |
| GET | `/api/status` | Banco em uso e contagem de registros |
| POST | `/api/epicentros/importar` | Importa da USGS. Corpo: `{bbox:{sul,oeste,norte,leste}, inicio, fim, min_mag}` |
| GET | `/api/epicentros?sul=&oeste=&norte=&leste=&min_mag=&inicio=&fim=&limite=` | Epicentros filtrados (maiores magnitudes primeiro) + total |
| GET | `/api/epicentros/resumo` | Total, faixa de magnitude e período no banco |
| DELETE | `/api/epicentros` | Apaga todos os epicentros |
| GET / DELETE | `/api/analises` | Lista / apaga análises salvas |

## 🗺️ Roteiro

| Fase | Entrega | Situação |
|---|---|---|
| 0 | Esqueleto, banco, interface base | ✅ |
| 1 | Importação de epicentros (USGS) e camada no mapa | ✅ |
| 2 | Importação de falhas (GEM / upload GeoJSON) | ⏳ |
| 3 | Motor de correlação (distância, buffer, Monte Carlo, KS) | ⏳ |
| 4 | Interface de análise (área, gráficos, mapa de calor) | ⏳ |
| 5 | Análises salvas e exportação CSV/GeoJSON | ⏳ |
| 6 | Acabamento, dados de demonstração offline | ⏳ |

---

## 🌎 Epicentros (Fase 1)

- **Fonte:** [USGS FDSN Event API](https://earthquake.usgs.gov/fdsnws/event/1/), sem chave. Até 20.000 eventos por importação; acima disso o sistema pede para aumentar a magnitude mínima ou reduzir área/período.
- **Área importada:** a parte do mapa que o painel não cobre.
- **Reimportar** a mesma área atualiza os eventos (pelo id da USGS) em vez de duplicar.
- **No mapa:** cor = profundidade (0–10, 10–35, 35–70, 70–300, > 300 km), tamanho = magnitude. Exibe até 5.000 eventos da área visível, priorizando os maiores.

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
