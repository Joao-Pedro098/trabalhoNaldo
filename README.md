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
│   ├── falhas_controle.py     # Importação do GEM, upload de arquivo, consulta de falhas
│   └── respostas.py           # Respostas JSON padronizadas {sucesso, ...}
├── db/
│   └── database.py            # PostgreSQL ou SQLite; tabelas epicentros, falhas, analises
├── modelo/                    # MODEL
│   ├── geocodificacao.py      # Nominatim (busca/reverso) e localização por IP
│   ├── epicentro.py           # Persistência e consultas de epicentros
│   ├── falha.py               # Persistência, consulta e categoria (mecanismo) das falhas
│   ├── fontes/usgs.py         # Cliente do catálogo FDSN da USGS
│   ├── fontes/gem.py          # Base mundial de falhas ativas do GEM (com cache local)
│   ├── fontes/arquivo_falhas.py # Leitura de GeoJSON e shapefile (.zip) enviados
│   ├── fontes/geometria.py    # Normalização de linhas (2D, caixa, id estável)
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
| POST | `/api/falhas/importar-gem` | Importa falhas do GEM na área. Corpo: `{bbox:{sul,oeste,norte,leste}}` |
| POST | `/api/falhas/upload` | Envia arquivo (multipart: `arquivo` .geojson/.json/.zip, `fonte` opcional) |
| GET | `/api/falhas?sul=&oeste=&norte=&leste=&limite=` | Falhas que cruzam a área (FeatureCollection) + total |
| GET | `/api/falhas/fontes` | Quantidade de falhas por fonte |
| DELETE | `/api/falhas?fonte=` | Apaga as falhas de uma fonte (ou todas, sem `fonte`) |
| GET / DELETE | `/api/analises` | Lista / apaga análises salvas |

## 🗺️ Roteiro

| Fase | Entrega | Situação |
|---|---|---|
| 0 | Esqueleto, banco, interface base | ✅ |
| 1 | Importação de epicentros (USGS) e camada no mapa | ✅ |
| 2 | Importação de falhas (GEM / upload GeoJSON e shapefile) | ✅ |
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

## 🪨 Falhas (Fase 2)

- **GEM Global Active Faults** ([GEMScienceTools/gem-global-active-faults](https://github.com/GEMScienceTools/gem-global-active-faults), CC-BY-SA 4.0): ~13.700 falhas ativas no mundo. A base (10 MB) é baixada na primeira importação e guardada em `data/cache/` por 30 dias; importa só as falhas que cruzam a área visível.
  - ⚠️ **Não cobre o Brasil** (nenhuma falha no território; na América do Sul só os Andes).
- **Upload de arquivo** — para o Brasil e outras bases:
  - GeoJSON (`.geojson`/`.json`) ou shapefile compactado (`.zip` com `.shp`, `.shx`, `.dbf` e, se houver, `.prj`/`.cpg`).
  - Coordenadas **geográficas** (WGS84 / SIRGAS 2000). Arquivos em UTM são recusados com instrução para reprojetar no QGIS.
  - Só linhas (LineString/MultiLineString); pontos e polígonos são ignorados e contados.
  - Nome e tipo são lidos de colunas comuns (`name`/`nome`, `slip_type`/`tipo`...); os demais atributos ficam guardados.
  - Fontes sugeridas para o Brasil: GeoSGB / SGB-CPRM (falhas e zonas de cisalhamento dos mapas geológicos).
- **Categoria** pelo mecanismo principal: normal, reversa/empurrão, transcorrente, dorsal ou outra (termos em inglês e português).
- Reenviar o mesmo traçado **atualiza** em vez de duplicar. Cada fonte pode ser apagada separadamente.

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
