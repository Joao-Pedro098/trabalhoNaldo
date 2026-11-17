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
│   ├── analise_controle.py    # Validação e execução da análise de correlação
│   └── respostas.py           # Respostas JSON padronizadas {sucesso, ...}
├── db/
│   └── database.py            # PostgreSQL ou SQLite; tabelas epicentros, falhas, analises
├── modelo/                    # MODEL
│   ├── geocodificacao.py      # Nominatim (busca/reverso) e localização por IP
│   ├── epicentro.py           # Persistência e consultas de epicentros
│   ├── falha.py               # Persistência, consulta e categoria (mecanismo) das falhas
│   ├── correlacao.py          # MOTOR: distâncias, Monte Carlo, buffers, KS, ranking (sem banco)
│   ├── analise.py             # Carrega dados do banco, roda o motor e salva a análise
│   ├── fontes/usgs.py         # Cliente do catálogo FDSN da USGS
│   ├── fontes/gem.py          # Base mundial de falhas ativas do GEM (com cache local)
│   ├── fontes/arquivo_falhas.py # Leitura de GeoJSON e shapefile (.zip) enviados
│   ├── fontes/geometria.py    # Normalização de linhas (2D, caixa, id estável)
│   └── sistema.py             # Contagens e análises salvas
├── rotas/
│   └── rotas.py               # Endpoints HTTP (Blueprint)
├── static/                    # CSS e JS: map.js (mapa, dados) e analise.js (painel da análise)
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
| POST | `/api/analise` | Roda a análise (ver parâmetros abaixo) e salva |
| GET | `/api/analises/<id>` | Resultado completo de uma análise salva |
| GET | `/api/analises/<id>/buffer?km=` | Zona a até `km` das falhas da análise (GeoJSON, recortada à área) |
| GET / DELETE | `/api/analises` | Lista / apaga análises salvas |

## 🗺️ Roteiro

| Fase | Entrega | Situação |
|---|---|---|
| 0 | Esqueleto, banco, interface base | ✅ |
| 1 | Importação de epicentros (USGS) e camada no mapa | ✅ |
| 2 | Importação de falhas (GEM / upload GeoJSON e shapefile) | ✅ |
| 3 | Motor de correlação (distância, buffer, Monte Carlo, KS) | ✅ |
| 4 | Interface de análise (área, gráficos, mapa de calor) | ✅ |
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

## 📐 Análise de correlação (Fase 3)

**Pergunta:** os epicentros estão mais perto das falhas do que estariam por acaso?

1. **Projeção:** azimutal equidistante centrada na área (distâncias em km, pouca distorção em escala regional; aviso acima de 2.500 km).
2. **Distância observada:** de cada epicentro à falha mais próxima (índice espacial STRtree). Falhas até o maior buffer *fora* da área também contam.
3. **Hipótese nula:** epicentros uniformes na área de estudo (uniforme na esfera dentro da caixa).
4. **Monte Carlo** (padrão 999 simulações, semente fixa → reprodutível): catálogos aleatórios do mesmo tamanho.
   - *Mediana*: p = (1 + nº de simulações com mediana ≤ observada) / (n + 1).
   - *Buffers* (padrão 5, 10, 20, 50 km): % observada × esperada, razão e p-valor, **corrigido por Bonferroni** (p × nº de buffers) — testar vários buffers de uma vez inflaria o falso positivo.
   - *Afastamento*: cauda oposta da mediana; só se conclui "mais longe" com p < 0,05.
5. **Conclusão** combina os dois testes, porque respondem perguntas diferentes:

| Código | Situação |
|---|---|
| `associacao` | Mediana menor que o acaso **e** excesso de eventos junto às falhas |
| `proximidade_sem_excesso` | Mais perto no geral, mas nenhum excesso colado às falhas (típico de falha inclinada/subducção ou estrutura não mapeada) |
| `excesso_local` | Mediana igual ao acaso, mas excesso junto às falhas |
| `sem_associacao` | Nada significativo |
| `afastamento` | Epicentros mais longe que o acaso |

6. **Complementos:** teste KS (diferença de *forma* entre as distribuições — informativo, não entra na conclusão), Spearman magnitude × distância, ranking das falhas (eventos, magnitude máxima, energia `log E = 1,5M + 4,8`, eventos por 100 km), histograma observado × esperado e, por epicentro, a distância e o ponto mais próximo na falha.

**Parâmetros de `POST /api/analise`:** `bbox` (obrigatório), `buffers_km`, `n_simulacoes` (99–9999), `min_mag`, `prof_max_km`, `inicio`, `fim`, `fontes_falhas`, `semente`, `nome`, `salvar`.

> 💡 **Profundidade importa.** Falhas mapeadas são traços em superfície. Em zonas de subducção, sismos profundos ocorrem no plano inclinado, dezenas a centenas de km do traço. Use `prof_max_km` (ex.: 35) para analisar só a sismicidade crustal rasa.

## 🖥️ Interface da análise (Fase 4)

- **Aba Análise:** área de estudo = área visível do mapa; profundidade máxima (padrão ≤ 35 km), magnitude mínima, buffers, nº de simulações; em *Mais opções*: período, fontes de falhas e nome.
- **Resultado:** cartão de conclusão (verde = associação, amarelo = parcial, cinza = sem associação), medianas e p-valor, tabela de buffers (clique mostra a zona no mapa), histograma observado × esperado (Chart.js), falhas com mais eventos (clique enquadra a falha) e outros testes (KS, Spearman).
- **Mapa:** contorno da área de estudo, zona de buffer, e no popup de cada epicentro a distância e uma linha tracejada até o ponto mais próximo da falha.
- **Camada "Densidade (calor)"** no seletor de camadas (Leaflet.heat, peso pela magnitude).
- **Histórico:** clicar numa análise salva reabre o resultado e enquadra a área.
- **Avisos:** poucos eventos, área grande e quando os epicentros ocupam só uma pequena parte da área de estudo (sinal de área maior que a importada, o que enviesa a hipótese nula).

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
