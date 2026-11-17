# 🌋 SismoFalhas — Correlação espacial entre falhas mapeadas e epicentros registrados

Sistema web que cruza **falhas geológicas mapeadas** com **epicentros de sismos registrados** e responde, com teste estatístico, à pergunta:

> *Os sismos ocorrem mais perto das falhas do que o acaso explicaria?*

Construído sobre a mesma stack e o mesmo padrão MVC do PyMaps (trabalhoNaldo): **Flask + Leaflet + PostgreSQL** (com fallback para SQLite), executado numa VM Ubuntu Server e acessado pelo navegador do Windows. **Funciona sem internet** com os dados de demonstração.

---

## ⚡ Início rápido

### Na VM (Ubuntu Server)
```bash
chmod +x setup_vm.sh
./setup_vm.sh --demo            # instala, roda os testes e carrega a demonstração
./venv/bin/python3 app.py
```
Com `--servico`, o sistema passa a iniciar sozinho junto com a VM (systemd). Acesse **http://&lt;IP-da-VM&gt;:5000** no navegador do Windows (o script mostra o IP no final).

### No Windows (desenvolvimento)
```bash
python -m venv venv
venv\Scripts\pip install -r requirements.txt
venv\Scripts\python carregar_demo.py
venv\Scripts\python app.py
```
Acesse **http://localhost:5000**.

Requisitos: Python 3.10+. PostgreSQL é opcional (sem ele, o sistema usa SQLite em `db/sismo.db`).

---

## 🧭 Como usar (passo a passo)

1. **Dados → Dados de demonstração → Carregar** (ou importe os seus):
   - **Epicentros:** posicione o mapa e clique em *Importar da USGS* (período e magnitude mínima ajustáveis).
   - **Falhas:** *Importar falhas do GEM* (base mundial, **não cobre o Brasil**) ou *Enviar arquivo* (GeoJSON ou shapefile .zip, ex.: SGB/CPRM).
2. **Análise:** mantenha **Área importada** e **profundidade até 35 km**, e clique em **Rodar análise**.
3. Leia o **cartão de conclusão** e confira a tabela de buffers, o histograma e as falhas com mais eventos. Clique numa linha da tabela para ver a zona no mapa; clique num epicentro para ver a distância e a linha até a falha.
4. **Exporte** em CSV (Excel), GeoJSON (QGIS) ou JSON. A análise fica salva no **Histórico**.

### Resultado de referência (demonstração)
Coquimbo, Chile — 984 sismos M ≥ 2,5 (2016–2026), 13 falhas do GEM, sismos ≤ 35 km, 999 simulações:

| Medida | Observado | Esperado ao acaso |
|---|---|---|
| Mediana da distância à falha | 65,5 km | 108,8 km (p = 0,001) |
| Eventos a até 50 km de uma falha | 11,0% | 7,4% (1,49×, p ajustado = 0,016) |

**Conclusão: associação espacial significativa.** A semente fixa torna o resultado reprodutível (verificado nos testes automáticos).

---

## 📐 Metodologia

1. **Projeção:** azimutal equidistante centrada na área de estudo — distâncias em km com pouca distorção em escala regional (aviso acima de 2.500 km).
2. **Distância observada:** de cada epicentro até a falha mais próxima (índice espacial STRtree). Falhas logo *fora* da área também contam.
3. **Hipótese nula:** epicentros distribuídos uniformemente (na esfera) dentro da área de estudo.
4. **Monte Carlo** (padrão 999 catálogos aleatórios do mesmo tamanho; semente fixa):
   - **Mediana:** p = (1 + nº de simulações com mediana ≤ observada) / (n + 1).
   - **Buffers** (5, 10, 20, 50 km): % observada × esperada e p-valor **com correção de Bonferroni** (p × nº de buffers), porque testar várias distâncias ao mesmo tempo inflaria o falso positivo.
   - **Afastamento:** cauda oposta — só se conclui "mais longe" com p < 0,05.
5. **Conclusão** (combina os dois testes, que respondem perguntas diferentes):

| Conclusão | Quando |
|---|---|
| 🟢 Associação | Mediana menor que o acaso **e** excesso de eventos junto às falhas |
| 🟢 Excesso local | Mediana igual ao acaso, mas excesso junto às falhas |
| 🟡 Mais perto, sem excesso | Mais perto no geral, mas nada colado às falhas (típico de falha inclinada/subducção ou estrutura não mapeada) |
| ⚪ Sem associação | Nada significativo |
| ⚪ Afastamento | Epicentros significativamente mais longe que o acaso |

6. **Complementos:** teste KS (diferença de *forma* das distribuições; informativo), Spearman magnitude × distância, ranking das falhas (eventos, magnitude máxima, energia `log₁₀E = 1,5M + 4,8`, eventos por 100 km).

**Calibração verificada nos testes:** com epicentros realmente aleatórios, a taxa de falso positivo fica próxima dos 5% esperados (40 sementes), tanto para a mediana quanto para os buffers.

---

## ⚠️ Limitações e cuidados de interpretação

- **Área de estudo muda o resultado.** A hipótese nula só é justa onde houve coleta de dados. Por isso o padrão é a **área importada** e toda análise informa a **cobertura** (% da área com sismos importados), com aviso abaixo de 95%. Exemplo real: em Coquimbo, uma área 36% maior que a importada levava a "mais perto, sem excesso"; com a área exata, "associação significativa".
- **Falhas são traços em superfície.** Sismos profundos acontecem no plano inclinado da falha, longe do traço — use o filtro de profundidade (padrão ≤ 35 km). A distância é medida em 2D (epicentro × traço).
- **Hipótese nula uniforme.** Não considera variações de detecção da rede sismográfica (ex.: oceano × continente).
- **Bases incompletas.** O GEM não tem falhas no Brasil; falhas não mapeadas não aparecem na análise. Magnitudes de tipos diferentes (mb, Mw, ML) são tratadas igualmente na energia, que é aproximada.
- **Correlação ≠ causalidade.** Proximidade estatística não prova qual falha gerou cada sismo.

---

## 🗂️ Dados e fontes

| Dado | Fonte | Licença |
|---|---|---|
| Epicentros | [USGS FDSN Event API](https://earthquake.usgs.gov/fdsnws/event/1/) (até 20.000 eventos por importação) | Domínio público |
| Falhas ativas | [GEM Global Active Faults](https://github.com/GEMScienceTools/gem-global-active-faults) — cache local de 30 dias em `data/cache/` | CC-BY-SA 4.0 (citar Styron & Pagani, 2020) |
| Falhas do Brasil | Upload de arquivo (ex.: [GeoSGB / SGB-CPRM](https://geosgb.sgb.gov.br)) em coordenadas geográficas | Conforme a fonte |
| Mapa offline | [Natural Earth](https://www.naturalearthdata.com) 1:50m (contornos dos países) | Domínio público |
| Mapas online | OpenTopoMap, OpenStreetMap, Esri | Conforme cada serviço |
| Busca de lugares | Nominatim (OpenStreetMap) | ODbL |

Detalhes da demonstração em [`data/demo/LEIA-ME.md`](data/demo/LEIA-ME.md); bibliotecas de terceiros em [`static/vendor/LICENCAS.md`](static/vendor/LICENCAS.md).

### Sem internet
- Leaflet, Chart.js, Leaflet.heat e Font Awesome são servidos localmente (`static/vendor/`).
- Se os mosaicos do mapa não carregarem, o sistema troca sozinho para **"Offline (contornos)"**.
- A demonstração é carregada de `data/demo/`. Só a busca de lugares, a importação da USGS/GEM e os mapas de fundo online precisam de internet.

---

## 🏛️ Arquitetura (MVC)

```text
sismoFalhas/
├── controle/                    # CONTROLLER — validação e orquestração
│   ├── sistema_controle.py      # Página, busca de região, status, demonstração, histórico
│   ├── epicentros_controle.py   # Importação/consulta de epicentros
│   ├── falhas_controle.py       # GEM, upload de arquivo, consulta de falhas
│   ├── analise_controle.py      # Análise, zona de buffer, exportação, importações
│   └── respostas.py             # Respostas JSON padronizadas {sucesso, ...}
├── modelo/                      # MODEL — regras, cálculos e persistência
│   ├── correlacao.py            # MOTOR estatístico (sem banco nem rede)
│   ├── analise.py               # Carrega do banco, roda o motor, salva
│   ├── importacao.py            # Registro das áreas importadas e cobertura
│   ├── exportacao.py            # CSV, GeoJSON e JSON
│   ├── epicentro.py / falha.py  # Persistência; categoria da falha pelo mecanismo
│   ├── demo.py                  # Dados de demonstração offline
│   ├── geocodificacao.py        # Nominatim e localização por IP
│   ├── sistema.py               # Contagens e histórico
│   └── fontes/                  # usgs.py, gem.py, arquivo_falhas.py, geometria.py
├── db/database.py               # PostgreSQL ou SQLite: epicentros, falhas, analises, importacoes
├── rotas/rotas.py               # Endpoints HTTP (Blueprint)
├── templates/index.html         # VIEW
├── static/
│   ├── js/map.js                # Mapa, camadas, importação, histórico
│   ├── js/analise.js            # Painel da análise
│   ├── css/style.css
│   ├── vendor/                  # Bibliotecas locais (offline)
│   └── data/                    # Contornos dos países (mapa offline)
├── data/demo/                   # Dados de demonstração + LEIA-ME
├── tests/                       # 75 testes (pytest)
├── app.py                       # Ponto de entrada (porta 5000)
├── carregar_demo.py             # Carrega a demonstração pela linha de comando
└── setup_vm.sh                  # Instalação no Ubuntu Server (--demo, --servico)
```

## 🔌 API

| Método | Rota | Descrição |
|---|---|---|
| GET | `/` | Interface web |
| GET | `/api/status` | Banco em uso e contagens |
| POST | `/api/demo` | Carrega os dados de demonstração (offline) |
| GET | `/api/regioes?q=` · `/api/reverso?lat=&lon=` · `/api/minha-localizacao` | Navegação no mapa |
| POST | `/api/epicentros/importar` | USGS. Corpo: `{bbox:{sul,oeste,norte,leste}, inicio, fim, min_mag}` |
| GET / DELETE | `/api/epicentros` | Consulta (`sul, oeste, norte, leste, min_mag, inicio, fim, limite`) / apaga todos |
| GET | `/api/epicentros/resumo` | Total, faixa de magnitude e período |
| POST | `/api/falhas/importar-gem` | GEM na área. Corpo: `{bbox}` |
| POST | `/api/falhas/upload` | Multipart: `arquivo` (.geojson/.json/.zip), `fonte` |
| GET / DELETE | `/api/falhas` | Consulta por área (FeatureCollection) / apaga (`?fonte=`) |
| GET | `/api/falhas/fontes` | Falhas por fonte |
| GET | `/api/importacoes?tipo=` | Áreas consultadas em cada importação |
| POST | `/api/analise` | Roda e salva a análise (parâmetros abaixo) |
| GET / DELETE | `/api/analises` | Lista com conclusão / apaga todas |
| GET / DELETE | `/api/analises/<id>` | Resultado completo / apaga uma |
| GET | `/api/analises/<id>/buffer?km=` | Zona a até `km` das falhas (GeoJSON) |
| GET | `/api/analises/<id>/exportar?formato=` | `csv`, `geojson` ou `json` (download) |

**`POST /api/analise`:** `bbox` (obrigatório), `area` (`"importada"` usa a caixa exata das importações de sismos que cruzam `bbox`), `buffers_km`, `n_simulacoes` (99–9999), `min_mag`, `prof_max_km`, `inicio`, `fim`, `fontes_falhas`, `semente`, `nome`, `salvar`.

## ⚙️ Configuração (variáveis de ambiente, opcionais)

| Variável | Padrão | Uso |
|---|---|---|
| `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASS` | `localhost`, `5432`, `sismo_db`, `postgres`, `postgres` | PostgreSQL |
| `DB_BACKEND=sqlite` | — | Força SQLite sem tentar o Postgres |
| `DB_CONNECT_TIMEOUT` | `3` | Segundos esperando o Postgres antes do fallback |
| `SECRET_KEY` | aleatória | Chave do Flask |
| `FLASK_DEBUG=1` | desligado | Modo debug |
| `PORT` | `5000` | Porta HTTP |

Para usar PostgreSQL na VM:
```bash
sudo apt-get install -y postgresql
sudo -u postgres psql -c "CREATE DATABASE sismo_db;"
sudo -u postgres psql -c "ALTER USER postgres PASSWORD 'postgres';"
```

## ✅ Testes
```bash
python -m pytest -q
```
75 testes: validação das entradas, leitura de GeoJSON/shapefile, distâncias geodésicas, calibração estatística, exportação, registro de importações, demonstração offline e API.

## 🗺️ Roteiro

| Fase | Entrega | |
|---|---|---|
| 0 | Esqueleto, banco, interface base | ✅ |
| 1 | Epicentros da USGS no mapa | ✅ |
| 2 | Falhas: GEM e upload GeoJSON/shapefile | ✅ |
| 3 | Motor de correlação (distâncias, Monte Carlo, buffers, KS) | ✅ |
| 4 | Interface da análise (conclusão, gráfico, zonas, calor) | ✅ |
| 5 | Registro de importações, área importada, exportação | ✅ |
| 6 | Funcionamento offline, demonstração, instalação e documentação | ✅ |
