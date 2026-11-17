# Dados de demonstração — Coquimbo, Chile

Usados pelo botão **"Carregar dados de demonstração"** (aba Dados) e por `python carregar_demo.py`,
para apresentar o sistema **sem internet**.

| Arquivo | Conteúdo | Fonte | Licença |
|---|---|---|---|
| `epicentros_coquimbo.geojson` | 984 epicentros, M ≥ 2,5, de 17/11/2016 a 17/11/2026, área lat −32,65 a −28,66 / lon −71,99 a −69,54 | [USGS — ANSS Comprehensive Catalog](https://earthquake.usgs.gov/fdsnws/event/1/) | Domínio público (dados do governo dos EUA) |
| `falhas_gem_coquimbo.geojson` | 13 falhas ativas que cruzam a área lat −32,6 a −28,7 / lon −72,3 a −68,5 | [GEM Global Active Faults Database](https://github.com/GEMScienceTools/gem-global-active-faults) | [CC-BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/) — Styron, R. & Pagani, M. (2020), *Earthquake Spectra* 36(1_suppl) |
| `demo.json` | Áreas e filtros de cada conjunto (registrados como importações) | — | — |

O arquivo de falhas é um recorte da base do GEM, distribuído sob a mesma licença CC-BY-SA 4.0.
Ao usar figuras ou resultados com essas falhas, cite: *Styron, R., & Pagani, M. (2020). The GEM Global
Active Faults Database. Earthquake Spectra, 36(1_suppl), 160–180.*
