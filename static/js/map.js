document.addEventListener('DOMContentLoaded', () => {
    // ==========================================
    // 1. MAPA (Leaflet)
    // ==========================================
    const map = L.map('map', { zoomControl: false }).setView([-14.235, -51.925], 4);
    L.control.zoom({ position: 'bottomright' }).addTo(map);
    L.control.scale({ position: 'bottomright', imperial: false }).addTo(map);

    const camadasBase = {
        'Ruas': L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
            attribution: '&copy; OpenStreetMap contributors', maxZoom: 19
        }),
        'Relevo': L.tileLayer('https://{s}.tile.opentopomap.org/{z}/{x}/{y}.png', {
            attribution: '&copy; OpenStreetMap contributors, SRTM | &copy; OpenTopoMap (CC-BY-SA)', maxZoom: 17
        }),
        'Satélite': L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}', {
            attribution: 'Tiles &copy; Esri', maxZoom: 18
        })
    };
    camadasBase['Relevo'].addTo(map);

    // Mapa base OFFLINE: contornos dos países (Natural Earth, domínio público) servidos
    // pelo próprio sistema. Carregado só quando necessário (1,7 MB).
    const COR_OCEANO_OFFLINE = '#d6e6f2';
    // Painel próprio logo acima dos mosaicos (tilePane = 200) e abaixo de tudo o mais:
    // no painel padrão os países (preenchimento opaco) cobririam os epicentros.
    map.createPane('baseOffline').style.zIndex = 250;
    const camadaOffline = L.geoJSON(null, {
        pane: 'baseOffline',
        style: { color: '#8a8f95', weight: 0.8, fillColor: '#f4f1ea', fillOpacity: 1 },
        interactive: false,
        attribution: 'Contornos: Natural Earth (domínio público)'
    });
    let offlineCarregado = false;
    camadaOffline.on('add', async () => {
        map.getContainer().style.background = COR_OCEANO_OFFLINE;
        if (offlineCarregado) return;
        offlineCarregado = true;
        try {
            const resp = await fetch('/static/data/paises_ne50m.geojson');
            camadaOffline.addData(await resp.json());
        } catch {
            offlineCarregado = false;
        }
    });
    camadaOffline.on('remove', () => { map.getContainer().style.background = ''; });
    camadasBase['Offline (contornos)'] = camadaOffline;

    // Sem internet os mosaicos falham: troca sozinho para o mapa offline
    let falhasMosaico = 0, mosaicosOk = 0, trocouOffline = false;
    Object.entries(camadasBase).forEach(([nome, camada]) => {
        if (camada === camadaOffline) return;
        camada.on('tileload', () => { mosaicosOk++; });
        camada.on('tileerror', () => {
            falhasMosaico++;
            if (!trocouOffline && mosaicosOk === 0 && falhasMosaico >= 6 && map.hasLayer(camada)) {
                trocouOffline = true;
                map.removeLayer(camada);
                camadaOffline.addTo(map);
                window.SF?.showAlert('Sem conexão com o servidor de mapas: usando o mapa offline (contornos dos países).', 'info');
            }
        });
    });

    // Camadas de dados: preenchidas nas próximas fases (epicentros, falhas, buffers...)
    // Falhas ficam por cima dos epicentros (overlayPane = 400): linhas finas cobrem pouco
    // e ficariam escondidas sob os círculos.
    map.createPane('falhas').style.zIndex = 450;
    const camadasDados = {
        'Epicentros': L.layerGroup().addTo(map),
        'Falhas': L.layerGroup().addTo(map),
        // Densidade dos epicentros exibidos (peso pela magnitude); desligada por padrão
        'Densidade (calor)': L.heatLayer([], { radius: 20, blur: 18, maxZoom: 9, minOpacity: 0.25 })
    };
    L.control.layers(camadasBase, camadasDados, { position: 'bottomright' }).addTo(map);

    // Ganchos preenchidos por analise.js (mantém este arquivo independente da análise)
    const ganchos = {
        popupEpicentro: null,     // (e) => html extra no popup do epicentro
        abrirEpicentro: null,     // (e) => chamado ao abrir o popup
        fecharEpicentro: null,    // () => chamado ao fechar o popup
        mostrarView: null,        // (nome) => chamado ao trocar de aba
        abrirAnalise: null        // (id) => abre uma análise salva
    };

    let marcadorLocal = null;

    // ==========================================
    // 2. ELEMENTOS DO DOM
    // ==========================================
    const $ = (id) => document.getElementById(id);
    const regionInput = $('region-input');
    const regionSuggestions = $('region-suggestions');
    const alertBox = $('alert-box');
    const panel = $('maps-panel');
    const contextMenu = $('context-menu');
    const coordsReadout = $('coords-readout');

    // ==========================================
    // 3. UTILITÁRIOS
    // ==========================================
    let alertTimer = null;
    function showAlert(mensagem, tipo = 'error') {
        alertBox.className = `alert alert-${tipo}`;
        alertBox.textContent = mensagem;
        clearTimeout(alertTimer);
        alertTimer = setTimeout(() => alertBox.classList.add('hidden'), 4000);
    }

    async function api(url, opcoes = {}) {
        const res = await fetch(url, opcoes);
        let data;
        try {
            data = await res.json();
        } catch {
            throw new Error(`Resposta inesperada do servidor (HTTP ${res.status})`);
        }
        if (!data.sucesso) throw new Error(data.erro || 'Erro na requisição');
        return data;
    }

    // Quanto do mapa o painel cobre. No celular considera o painel recolhido
    // (max-height de .maps-panel.collapsed no CSS), pois é assim que o usuário vê o mapa.
    const ALTURA_PAINEL_RECOLHIDO = 112;
    function areaCobertaPeloPainel() {
        if (window.innerWidth > 768) return { esquerda: panel.getBoundingClientRect().right, topo: 0 };
        return { esquerda: 0, topo: ALTURA_PAINEL_RECOLHIDO };
    }

    const escapeHtml = (s) => String(s ?? '').replace(/[&<>"']/g, c => (
        { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]
    ));

    // ==========================================
    // 4. TROCA DE VIEWS (Dados / Análise / Histórico)
    // ==========================================
    const viewButtons = document.querySelectorAll('[data-view]');
    function mostrarView(nome) {
        document.querySelectorAll('.panel-view').forEach(v => v.classList.toggle('hidden', v.id !== `view-${nome}`));
        viewButtons.forEach(b => b.classList.toggle('active', b.dataset.view === nome));
        if (nome === 'historico') carregarHistorico();
        if (nome === 'dados') carregarStatus();
        ganchos.mostrarView?.(nome);
        toggleMobilePanel(false);
    }
    viewButtons.forEach(b => b.addEventListener('click', () => mostrarView(b.dataset.view)));

    // ==========================================
    // 5. STATUS DO BANCO
    // ==========================================
    async function carregarStatus() {
        try {
            const data = await api('/api/status');
            $('count-epicentros').textContent = data.contagens.epicentros.toLocaleString('pt-BR');
            $('count-falhas').textContent = data.contagens.falhas.toLocaleString('pt-BR');
            $('db-backend').textContent = data.banco;
            $('btn-apagar-epicentros').classList.toggle('hidden', data.contagens.epicentros === 0);

            const resumoEl = $('epi-resumo');
            if (data.contagens.epicentros > 0) {
                const r = await api('/api/epicentros/resumo');
                resumoEl.innerHTML = `<i class="fa-regular fa-calendar"></i> ${r.inicio} a ${r.fim} · M ${r.mag_min ?? '?'} a ${r.mag_max ?? '?'}`;
                resumoEl.classList.remove('hidden');
            } else {
                resumoEl.classList.add('hidden');
            }
            carregarFontesFalhas();
            carregarImportacoes();
        } catch (e) {
            showAlert(`Não foi possível consultar o banco: ${e.message}`);
        }
    }

    // ==========================================
    // 5b. EPICENTROS: IMPORTAÇÃO, CAMADA E LEGENDA
    // ==========================================
    const renderizador = L.canvas({ padding: 0.5 });
    const LIMITE_EXIBICAO = 5000;

    // Cores por profundidade (km): rasos em amarelo, profundos em azul-escuro
    const FAIXAS_PROF = [
        { max: 10, cor: '#f9c74f', rotulo: '0–10 km' },
        { max: 35, cor: '#f8961e', rotulo: '10–35 km' },
        { max: 70, cor: '#e63946', rotulo: '35–70 km' },
        { max: 300, cor: '#9d4edd', rotulo: '70–300 km' },
        { max: Infinity, cor: '#1d3557', rotulo: '> 300 km' }
    ];
    const corProfundidade = (p) => (p == null ? '#9aa0a6' : FAIXAS_PROF.find(f => p <= f.max).cor);
    const raioMagnitude = (m) => Math.max(2.5, Math.min(18, 2 + ((m ?? 0) - 1) * 1.9));

    // Categorias de falha (definidas no backend em modelo/falha.py)
    const CATEGORIAS_FALHA = {
        normal: { cor: '#1f78b4', rotulo: 'Normal' },
        reversa: { cor: '#c0392b', rotulo: 'Reversa / empurrão' },
        transcorrente: { cor: '#2a9d4b', rotulo: 'Transcorrente' },
        dorsal: { cor: '#e07b00', rotulo: 'Dorsal oceânica' },
        outra: { cor: '#6b2c91', rotulo: 'Outra / sem tipo' }
    };

    const legenda = L.control({ position: 'topright' });
    legenda.onAdd = () => {
        const div = L.DomUtil.create('div', 'map-legend');
        const mags = [3, 5, 7].map(m => {
            const d = raioMagnitude(m) * 2;
            return `<span class="leg-mag"><i style="width:${d}px;height:${d}px"></i>M${m}</span>`;
        }).join('');
        div.innerHTML = `
            <strong>Profundidade</strong>
            ${FAIXAS_PROF.map(f => `<span class="leg-item"><i style="background:${f.cor}"></i>${f.rotulo}</span>`).join('')}
            <strong>Magnitude</strong>
            <div class="leg-mags">${mags}</div>
            <strong>Falhas</strong>
            ${Object.values(CATEGORIAS_FALHA).map(c => `<span class="leg-item"><b class="leg-linha" style="background:${c.cor}"></b>${c.rotulo}</span>`).join('')}`;
        L.DomEvent.disableClickPropagation(div);
        return div;
    };
    legenda.addTo(map);

    // Área do mapa realmente visível: desconta a parte coberta pelo painel
    // e limita a coordenadas válidas (o mapa pode "dar a volta" no mundo).
    function bboxVisivel() {
        const tamanho = map.getSize();
        const { esquerda, topo } = areaCobertaPeloPainel();
        const x0 = Math.min(esquerda, tamanho.x - 1);
        const y0 = Math.min(topo, tamanho.y - 1);
        const no = map.containerPointToLatLng([x0, y0]);
        const se = map.containerPointToLatLng([tamanho.x, tamanho.y]);
        const lim = (v, a) => Math.max(-a, Math.min(a, v));
        return {
            sul: +lim(se.lat, 90).toFixed(4), norte: +lim(no.lat, 90).toFixed(4),
            oeste: +lim(no.lng, 180).toFixed(4), leste: +lim(se.lng, 180).toFixed(4)
        };
    }

    const bboxValido = (b) => b.sul < b.norte && b.oeste < b.leste;

    function atualizarTextoBbox() {
        const b = bboxVisivel();
        $('bbox-texto').textContent = `Lat ${b.sul.toFixed(2)} a ${b.norte.toFixed(2)} · Lon ${b.oeste.toFixed(2)} a ${b.leste.toFixed(2)}`;
    }

    const popupEpicentro = (e) => {
        const link = e.fonte === 'USGS'
            ? `<a href="https://earthquake.usgs.gov/earthquakes/eventpage/${encodeURIComponent(e.id_externo)}" target="_blank" rel="noopener">Ver na USGS</a>`
            : escapeHtml(e.fonte === 'USP' ? 'Centro de Sismologia USP' : e.fonte);
        return `<div class="popup-epi">
            <div class="popup-mag" style="background:${corProfundidade(e.profundidade_km)}">M ${e.magnitude?.toFixed(1) ?? '?'}</div>
            <div>
                <strong>${escapeHtml(e.local || 'Local não informado')}</strong>
                <span>${escapeHtml(e.data_hora)} UTC</span>
                <span>Profundidade: ${e.profundidade_km != null ? e.profundidade_km.toFixed(1) + ' km' : 'não determinada'} · ${escapeHtml(e.tipo_magnitude || '')}</span>
                <span>${e.lat.toFixed(4)}, ${e.lon.toFixed(4)} · ${link}</span>
                ${ganchos.popupEpicentro?.(e) || ''}
            </div></div>`;
    };

    let requisicaoAtual = 0;
    async function carregarEpicentros() {
        const id = ++requisicaoAtual;
        const b = bboxVisivel();
        if (!bboxValido(b)) return; // mapa ainda sem tamanho (página carregando)
        const minMag = $('filtro-mag').value;
        const qs = new URLSearchParams({ ...b, min_mag: minMag, limite: LIMITE_EXIBICAO });
        if ($('filtro-brasil').checked) qs.set('territorio', 'BR');
        try {
            const data = await api(`/api/epicentros?${qs}`);
            if (id !== requisicaoAtual) return; // resposta antiga: o mapa já mudou
            const camada = camadasDados['Epicentros'];
            camada.clearLayers();
            // Lista vem com maiores magnitudes primeiro; desenhar ao contrário as deixa por cima
            data.epicentros.slice().reverse().forEach(e => {
                L.circleMarker([e.lat, e.lon], {
                    renderer: renderizador,
                    radius: raioMagnitude(e.magnitude),
                    color: '#3c3c3c', weight: 0.6,
                    fillColor: corProfundidade(e.profundidade_km), fillOpacity: 0.8
                }).bindPopup(() => popupEpicentro(e))
                  .on('popupopen', () => ganchos.abrirEpicentro?.(e))
                  .on('popupclose', () => ganchos.fecharEpicentro?.())
                  .addTo(camada);
            });
            camadasDados['Densidade (calor)'].setLatLngs(data.epicentros.map(e =>
                [e.lat, e.lon, Math.max(0.15, Math.min(1, ((e.magnitude ?? 2) - 1) / 6))]));
            const n = data.epicentros.length;
            $('exibindo-texto').textContent = data.total === 0
                ? 'Nenhum epicentro na área visível.'
                : n < data.total
                    ? `Exibindo os ${n.toLocaleString('pt-BR')} maiores de ${data.total.toLocaleString('pt-BR')} epicentros na área visível.`
                    : `Exibindo ${n.toLocaleString('pt-BR')} epicentros na área visível.`;
        } catch (e) {
            showAlert(`Falha ao carregar epicentros: ${e.message}`);
        }
    }

    let debounceMapa = null;
    map.on('moveend', () => {
        atualizarTextoBbox();
        clearTimeout(debounceMapa);
        debounceMapa = setTimeout(() => { carregarEpicentros(); carregarFalhas(); }, 300);
    });

    $('filtro-brasil').addEventListener('change', () => carregarEpicentros());

    $('filtro-mag').addEventListener('input', (e) => {
        $('filtro-mag-valor').textContent = Number(e.target.value).toFixed(1);
        clearTimeout(debounceMapa);
        debounceMapa = setTimeout(carregarEpicentros, 250);
    });

    // Período padrão: últimos 10 anos
    const hoje = new Date();
    const isoData = (d) => d.toISOString().slice(0, 10);
    $('imp-fim').value = isoData(hoje);
    $('imp-fim').max = isoData(hoje);
    $('imp-inicio').value = isoData(new Date(hoje.getFullYear() - 10, hoje.getMonth(), hoje.getDate()));

    $('form-importar').addEventListener('submit', async (ev) => {
        ev.preventDefault();
        const botao = $('btn-importar');
        const original = botao.innerHTML;
        const bbox = bboxVisivel();
        if (!bboxValido(bbox)) {
            showAlert('Área visível inválida. Ajuste o mapa e tente novamente.');
            return;
        }
        botao.disabled = true;
        const fonte = $('imp-fonte').value;
        botao.innerHTML = `<i class="fa-solid fa-spinner fa-spin"></i> Consultando ${fonte === 'usp' ? 'a USP (pode levar 1 min)' : 'a USGS'}...`;
        try {
            const data = await api('/api/epicentros/importar', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    bbox,
                    fonte,
                    inicio: $('imp-inicio').value,
                    fim: $('imp-fim').value,
                    min_mag: $('imp-mag').value
                })
            });
            showAlert(data.mensagem, 'info');
            await Promise.all([carregarStatus(), carregarEpicentros()]);
        } catch (e) {
            showAlert(e.message);
        } finally {
            botao.disabled = false;
            botao.innerHTML = original;
        }
    });

    $('btn-apagar-epicentros').addEventListener('click', async () => {
        if (!confirm('Apagar todos os epicentros importados? Esta ação não pode ser desfeita.')) return;
        try {
            const data = await api('/api/epicentros', { method: 'DELETE' });
            showAlert(data.mensagem, 'info');
            await Promise.all([carregarStatus(), carregarEpicentros()]);
        } catch (e) {
            showAlert(e.message);
        }
    });

    // ==========================================
    // 5c. FALHAS: IMPORTAÇÃO (GEM / ARQUIVO) E CAMADA
    // ==========================================
    const ATRIBUICAO_GEM = 'Falhas: <a href="https://github.com/GEMScienceTools/gem-global-active-faults" target="_blank" rel="noopener">GEM GAF-DB</a> (CC-BY-SA 4.0)';
    let atribuicaoGemAtiva = false;
    // SVG (não canvas): um canvas por cima capturaria os cliques de toda a área e
    // bloquearia os popups dos epicentros. No SVG só o traçado recebe o clique
    // (o painel tem pointer-events: none no CSS). Um único renderizador para não
    // empilhar elementos a cada carga.
    const renderizadorFalhas = L.svg({ pane: 'falhas' });
    const corFalha = (f) => (CATEGORIAS_FALHA[f.properties.categoria] || CATEGORIAS_FALHA.outra).cor;

    const popupFalha = (p) => {
        const cat = CATEGORIAS_FALHA[p.categoria] || CATEGORIAS_FALHA.outra;
        // Mostra alguns atributos úteis do GEM / arquivo, sem despejar tudo
        const extras = Object.entries(p.atributos || {})
            .filter(([k, v]) => v !== null && v !== '' && !['name', 'nome', 'slip_type', 'tipo'].includes(k))
            .slice(0, 6)
            .map(([k, v]) => `<tr><th>${escapeHtml(k)}</th><td>${escapeHtml(v)}</td></tr>`).join('');
        return `<div class="popup-falha">
            <strong>${escapeHtml(p.nome || 'Falha sem nome')}</strong>
            <span class="falha-tag" style="background:${cat.cor}">${cat.rotulo}</span>
            ${p.tipo ? `<span>Tipo original: ${escapeHtml(p.tipo)}</span>` : ''}
            <span>Fonte: ${escapeHtml(p.fonte)}</span>
            ${extras ? `<table>${extras}</table>` : ''}
        </div>`;
    };

    let requisicaoFalhas = 0;
    async function carregarFalhas() {
        const id = ++requisicaoFalhas;
        const b = bboxVisivel();
        if (!bboxValido(b)) return;
        try {
            // Em escala pequena simplifica os traçados (~1 pixel): milhares de falhas ficam leves
            const grausPorPixel = (b.leste - b.oeste) / Math.max(map.getSize().x, 1);
            const params = { ...b, limite: LIMITE_EXIBICAO };
            if (map.getZoom() < 10) params.tolerancia = grausPorPixel.toFixed(5);
            const data = await api(`/api/falhas?${new URLSearchParams(params)}`);
            if (id !== requisicaoFalhas) return;
            const camada = camadasDados['Falhas'];
            camada.clearLayers();
            // Traço visível (fino, não clicável)...
            L.geoJSON(data.falhas, {
                pane: 'falhas', renderer: renderizadorFalhas, interactive: false,
                style: (f) => ({ color: corFalha(f), weight: 2.2, opacity: 0.95 })
            }).addTo(camada);
            // ...e traço invisível largo por cima, para facilitar o clique
            L.geoJSON(data.falhas, {
                pane: 'falhas', renderer: renderizadorFalhas,
                style: { color: '#000', weight: 12, opacity: 0 },
                onEachFeature: (f, layer) => layer.bindPopup(() => popupFalha(f.properties))
            }).addTo(camada);

            const temGem = data.falhas.features.some(f => f.properties.fonte === 'GEM GAF-DB');
            if (temGem !== atribuicaoGemAtiva) {
                map.attributionControl[temGem ? 'addAttribution' : 'removeAttribution'](ATRIBUICAO_GEM);
                atribuicaoGemAtiva = temGem;
            }

            const n = data.falhas.features.length;
            $('exibindo-falhas-texto').textContent = data.total === 0 ? ''
                : n < data.total
                    ? `Exibindo as ${n.toLocaleString('pt-BR')} maiores de ${data.total.toLocaleString('pt-BR')} falhas na área visível.`
                    : `Exibindo ${n.toLocaleString('pt-BR')} falhas na área visível.`;
        } catch (e) {
            showAlert(`Falha ao carregar as falhas: ${e.message}`);
        }
    }

    // Áreas consultadas em cada importação (desenhadas sob demanda)
    const camadaImportacao = L.layerGroup().addTo(map);
    async function carregarImportacoes() {
        try {
            const data = await api('/api/importacoes');
            const lista = $('importacoes-lista');
            $('importacoes-box').classList.toggle('hidden', data.importacoes.length === 0);
            lista.innerHTML = '';
            data.importacoes.slice(0, 8).forEach(imp => {
                const b = imp.bbox;
                const li = document.createElement('li');
                li.tabIndex = 0;
                const icone = imp.tipo === 'epicentros' ? 'fa-circle-dot' : 'fa-wave-square';
                const filtros = imp.tipo === 'epicentros' && imp.parametros.inicio
                    ? ` · ${imp.parametros.inicio.slice(0, 4)}–${imp.parametros.fim.slice(0, 4)} · M ≥ ${imp.parametros.min_mag}` : '';
                li.innerHTML = `<i class="fa-solid ${icone}"></i>
                    <span><strong>${escapeHtml(imp.fonte)} · ${imp.recebidos.toLocaleString('pt-BR')} ${imp.tipo}</strong>
                    <small>${escapeHtml(imp.criado_em.slice(0, 16))}${filtros}</small></span>`;
                const ver = () => {
                    camadaImportacao.clearLayers();
                    const limites = [[b.sul, b.oeste], [b.norte, b.leste]];
                    L.rectangle(limites, { color: '#202124', weight: 1.5, dashArray: '2 5', fillOpacity: 0.04, interactive: false })
                        .addTo(camadaImportacao);
                    const { esquerda, topo } = areaCobertaPeloPainel();
                    map.flyToBounds(limites, { paddingTopLeft: [esquerda + 30, topo + 30], paddingBottomRight: [30, 30] });
                    setTimeout(() => camadaImportacao.clearLayers(), 8000);
                };
                li.addEventListener('click', ver);
                li.addEventListener('keydown', (ev) => { if (ev.key === 'Enter') ver(); });
                lista.appendChild(li);
            });
        } catch (e) {
            showAlert(e.message);
        }
    }

    async function carregarFontesFalhas() {
        try {
            const data = await api('/api/falhas/fontes');
            const lista = $('fontes-falhas');
            $('fontes-falhas-box').classList.toggle('hidden', data.fontes.length === 0);
            lista.innerHTML = '';
            data.fontes.forEach(f => {
                const li = document.createElement('li');
                li.innerHTML = `<span><strong>${escapeHtml(f.fonte)}</strong><small>${f.total.toLocaleString('pt-BR')} ${f.total === 1 ? 'falha' : 'falhas'}</small></span>`;
                const btn = document.createElement('button');
                btn.className = 'btn-icon-danger';
                btn.title = `Apagar falhas de ${f.fonte}`;
                btn.innerHTML = '<i class="fa-regular fa-trash-can"></i>';
                btn.addEventListener('click', () => apagarFalhas(f.fonte));
                li.appendChild(btn);
                lista.appendChild(li);
            });
        } catch (e) {
            showAlert(e.message);
        }
    }

    async function apagarFalhas(fonte) {
        if (!confirm(`Apagar todas as falhas da fonte "${fonte}"? Esta ação não pode ser desfeita.`)) return;
        try {
            const data = await api(`/api/falhas?${new URLSearchParams({ fonte })}`, { method: 'DELETE' });
            showAlert(data.mensagem, 'info');
            await Promise.all([carregarStatus(), carregarFalhas()]);
        } catch (e) {
            showAlert(e.message);
        }
    }

    async function comCarregamento(botao, textoCarregando, acao) {
        const original = botao.innerHTML;
        botao.disabled = true;
        botao.innerHTML = `<i class="fa-solid fa-spinner fa-spin"></i> ${textoCarregando}`;
        try {
            await acao();
        } catch (e) {
            showAlert(e.message);
        } finally {
            botao.disabled = false;
            botao.innerHTML = original;
        }
    }

    const AREA_GRANDE_GRAUS = 20;
    $('btn-demo').addEventListener('click', () => {
        comCarregamento($('btn-demo'), '', async () => {
            const data = await api('/api/demo', { method: 'POST' });
            showAlert(data.mensagem, 'info');
            const b = data.bbox;
            const { esquerda, topo } = areaCobertaPeloPainel();
            map.flyToBounds([[b.sul, b.oeste], [b.norte, b.leste]],
                { paddingTopLeft: [esquerda + 30, topo + 30], paddingBottomRight: [30, 30] });
            await carregarStatus();
        });
    });

    const DICAS_FONTE = {
        usgs: ['Importar da USGS', 'Catálogo mundial. No Brasil registra só os sismos maiores: use o da USP.'],
        usp: ['Importar da USP', 'Rede Sismográfica Brasileira: sismos do Brasil desde 1724. Muitos têm profundidade não determinada.']
    };
    $('imp-fonte').addEventListener('change', (e) => {
        const [texto, dica] = DICAS_FONTE[e.target.value];
        $('btn-importar-texto').textContent = texto;
        $('imp-fonte-dica').textContent = dica;
        if (e.target.value === 'usp' && Number($('imp-mag').value) > 2) $('imp-mag').value = 2;
    });

    $('btn-importar-sgb').addEventListener('click', () => {
        const bbox = bboxVisivel();
        if (!bboxValido(bbox)) { showAlert('Área visível inválida. Ajuste o mapa e tente novamente.'); return; }
        comCarregamento($('btn-importar-sgb'), 'Buscando no SGB...', async () => {
            const data = await api('/api/falhas/importar-sgb', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ bbox, incluir_lineamentos: $('sgb-lineamentos').checked })
            });
            showAlert(data.mensagem, data.recebidos ? 'info' : 'error');
            await Promise.all([carregarStatus(), carregarFalhas()]);
        });
    });

    $('btn-importar-gem').addEventListener('click', () => {
        const bbox = bboxVisivel();
        if (!bboxValido(bbox)) { showAlert('Área visível inválida. Ajuste o mapa e tente novamente.'); return; }
        const largura = Math.max(bbox.norte - bbox.sul, bbox.leste - bbox.oeste);
        if (largura > AREA_GRANDE_GRAUS && !confirm(
            `A área visível é muito grande (${Math.round(largura)}° de largura) e pode trazer milhares de falhas. ` +
            'Importar mesmo assim?')) return;
        comCarregamento($('btn-importar-gem'), 'Buscando no GEM...', async () => {
            const data = await api('/api/falhas/importar-gem', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ bbox })
            });
            showAlert(data.mensagem, data.recebidos ? 'info' : 'error');
            await Promise.all([carregarStatus(), carregarFalhas()]);
        });
    });

    $('upload-arquivo').addEventListener('change', (e) => {
        const arquivo = e.target.files[0];
        $('upload-nome').innerHTML = arquivo
            ? `<i class="fa-regular fa-file"></i> ${escapeHtml(arquivo.name)}`
            : '<i class="fa-regular fa-folder-open"></i> Escolher arquivo...';
        if (arquivo && !$('upload-fonte').value) {
            $('upload-fonte').value = arquivo.name.replace(/\.[^.]+$/, '');
        }
    });

    $('form-upload').addEventListener('submit', (ev) => {
        ev.preventDefault();
        const arquivo = $('upload-arquivo').files[0];
        if (!arquivo) { showAlert('Escolha um arquivo.'); return; }
        comCarregamento($('btn-upload'), 'Enviando...', async () => {
            const form = new FormData();
            form.append('arquivo', arquivo);
            form.append('fonte', $('upload-fonte').value.trim());
            const data = await api('/api/falhas/upload', { method: 'POST', body: form });
            showAlert(data.mensagem, 'info');
            $('form-upload').reset();
            $('upload-nome').innerHTML = '<i class="fa-regular fa-folder-open"></i> Escolher arquivo...';
            await Promise.all([carregarStatus(), carregarFalhas()]);
        });
    });

    // ==========================================
    // 6. BUSCA DE REGIÃO (Nominatim)
    // ==========================================
    let debounce = null;
    regionInput.addEventListener('input', () => {
        clearTimeout(debounce);
        const termo = regionInput.value.trim();
        if (termo.length < 3) { regionSuggestions.classList.add('hidden'); return; }
        debounce = setTimeout(async () => {
            try {
                const data = await api(`/api/regioes?q=${encodeURIComponent(termo)}`);
                renderSugestoes(data.results || []);
            } catch (e) {
                showAlert('Falha na busca de regiões.');
            }
        }, 400);
    });

    function renderSugestoes(itens) {
        regionSuggestions.innerHTML = '';
        if (!itens.length) {
            regionSuggestions.innerHTML = '<div class="suggestion-item">Nenhum lugar encontrado</div>';
        }
        itens.forEach(item => {
            const div = document.createElement('div');
            div.className = 'suggestion-item';
            div.innerHTML = `<i class="fa-solid fa-location-dot"></i> <span>${escapeHtml(item.display_name)}</span>`;
            div.addEventListener('click', () => irPara(item));
            regionSuggestions.appendChild(div);
        });
        regionSuggestions.classList.remove('hidden');
    }

    function irPara(item) {
        regionInput.value = item.display_name.split(',').slice(0, 2).join(',');
        regionSuggestions.classList.add('hidden');
        // Enquadra a região na parte do mapa que o painel não cobre
        const { esquerda, topo } = areaCobertaPeloPainel();
        const opcoes = {
            maxZoom: 12,
            paddingTopLeft: [esquerda + 20, topo + 20],
            paddingBottomRight: [20, 20]
        };
        if (item.bbox) {
            const [sul, norte, oeste, leste] = item.bbox;
            map.flyToBounds([[sul, oeste], [norte, leste]], opcoes);
        } else {
            map.flyToBounds(L.latLng(item.lat, item.lon).toBounds(20000), opcoes);
        }
    }

    document.addEventListener('click', (e) => {
        if (!e.target.closest('.search-box')) regionSuggestions.classList.add('hidden');
        if (!e.target.closest('#context-menu')) contextMenu.classList.add('hidden');
    });

    // ==========================================
    // 7. MINHA LOCALIZAÇÃO (GPS com fallback por IP)
    // ==========================================
    const botoesLocal = [$('btn-my-location'), $('fab-my-location')];
    const setCarregandoLocal = (on) => botoesLocal.forEach(b => {
        b.innerHTML = on ? '<i class="fa-solid fa-spinner fa-spin"></i>' : '<i class="fa-solid fa-crosshairs"></i>';
    });

    function marcarLocal(lat, lon, rotulo) {
        if (marcadorLocal) map.removeLayer(marcadorLocal);
        marcadorLocal = L.circleMarker([lat, lon], {
            radius: 7, color: '#fff', weight: 2, fillColor: '#1a73e8', fillOpacity: 1
        }).addTo(map).bindTooltip(rotulo);
        map.flyTo([lat, lon], 9);
    }

    async function localizarPorIP() {
        try {
            const d = await api('/api/minha-localizacao');
            marcarLocal(d.lat, d.lon, `Aproximado: ${d.display_name}`);
            showAlert('Localização aproximada pela rede (o GPS exige HTTPS).', 'info');
        } catch (e) {
            showAlert('Não foi possível obter sua localização.');
        }
    }

    function minhaLocalizacao() {
        setCarregandoLocal(true);
        const fim = () => setCarregandoLocal(false);
        if (!navigator.geolocation || !window.isSecureContext) {
            localizarPorIP().finally(fim);
            return;
        }
        navigator.geolocation.getCurrentPosition(
            (pos) => { marcarLocal(pos.coords.latitude, pos.coords.longitude, 'Você está aqui'); fim(); },
            () => localizarPorIP().finally(fim),
            { enableHighAccuracy: true, timeout: 6000, maximumAge: 60000 }
        );
    }
    botoesLocal.forEach(b => b.addEventListener('click', minhaLocalizacao));

    // ==========================================
    // 8. COORDENADAS DO CURSOR E MENU DE CONTEXTO
    // ==========================================
    const fmt = (ll) => `${ll.lat.toFixed(5)}, ${ll.lng.toFixed(5)}`;
    map.on('mousemove', (e) => { coordsReadout.textContent = fmt(e.latlng); });

    let latlngContexto = null;
    map.on('contextmenu', (e) => {
        latlngContexto = e.latlng;
        contextMenu.style.top = `${e.originalEvent.clientY}px`;
        contextMenu.style.left = `${e.originalEvent.clientX}px`;
        contextMenu.classList.remove('hidden');
    });

    $('ctx-copy-coords').addEventListener('click', async () => {
        contextMenu.classList.add('hidden');
        if (!latlngContexto) return;
        try {
            await navigator.clipboard.writeText(fmt(latlngContexto));
            showAlert(`Coordenadas copiadas: ${fmt(latlngContexto)}`, 'info');
        } catch {
            showAlert(`Coordenadas: ${fmt(latlngContexto)}`, 'info');
        }
    });

    $('ctx-whats-here').addEventListener('click', async () => {
        contextMenu.classList.add('hidden');
        if (!latlngContexto) return;
        const ll = latlngContexto;
        try {
            const d = await api(`/api/reverso?lat=${ll.lat}&lon=${ll.lng}`);
            L.popup().setLatLng(ll)
                .setContent(`<strong>${escapeHtml(d.display_name)}</strong><br><small>${fmt(ll)}</small>`)
                .openOn(map);
        } catch (e) {
            showAlert(e.message);
        }
    });

    // ==========================================
    // 9. HISTÓRICO DE ANÁLISES
    // ==========================================
    async function carregarHistorico() {
        const lista = $('history-list');
        try {
            const data = await api('/api/analises');
            const itens = data.analises || [];
            $('btn-clear-history').classList.toggle('hidden', itens.length === 0);
            if (!itens.length) {
                lista.innerHTML = '<p class="empty-state">Nenhuma análise salva ainda.</p>';
                return;
            }
            const CLASSE_CONCLUSAO = {
                associacao: 'positiva', excesso_local: 'positiva', proximidade_sem_excesso: 'parcial'
            };
            lista.innerHTML = itens.map(a => `
                <div class="history-item" data-id="${a.id}" role="button" tabindex="0">
                    <div class="history-item-topo">
                        <div class="history-item-route">${escapeHtml(a.nome || `Análise #${a.id}`)}</div>
                        <button class="btn-icon-danger" data-apagar="${a.id}" title="Apagar esta análise"><i class="fa-regular fa-trash-can"></i></button>
                    </div>
                    ${a.conclusao_titulo ? `<span class="tag-conclusao ${CLASSE_CONCLUSAO[a.conclusao] || 'neutra'}">${escapeHtml(a.conclusao_titulo)}</span>` : ''}
                    <div class="history-item-meta">
                        <span>#${a.id}${a.n_epicentros != null ? ` · ${a.n_epicentros} eventos · ${a.n_falhas} falhas` : ''}</span>
                        <span>${escapeHtml(a.criado_em.split(' ')[0])}</span>
                    </div>
                </div>`).join('');
            lista.querySelectorAll('.history-item').forEach(el => {
                const abrir = () => ganchos.abrirAnalise?.(Number(el.dataset.id));
                el.addEventListener('click', abrir);
                el.addEventListener('keydown', (ev) => { if (ev.key === 'Enter' && ev.target === el) abrir(); });
            });
            lista.querySelectorAll('[data-apagar]').forEach(btn => btn.addEventListener('click', async (ev) => {
                ev.stopPropagation(); // não abre a análise
                if (!confirm(`Apagar a análise #${btn.dataset.apagar}? Esta ação não pode ser desfeita.`)) return;
                try {
                    await api(`/api/analises/${btn.dataset.apagar}`, { method: 'DELETE' });
                    carregarHistorico();
                } catch (e) {
                    showAlert(e.message);
                }
            }));
        } catch (e) {
            showAlert(e.message);
        }
    }

    $('btn-clear-history').addEventListener('click', async () => {
        if (!confirm('Apagar todas as análises salvas?')) return;
        await api('/api/analises', { method: 'DELETE' });
        carregarHistorico();
    });

    // ==========================================
    // 10. MOBILE: RECOLHER / EXPANDIR PAINEL
    // ==========================================
    const fabOpenPanel = $('fab-open-panel');
    const mobileToggleText = $('mobile-toggle-text');

    function toggleMobilePanel(forcar = null) {
        const recolhido = forcar !== null ? forcar : !panel.classList.contains('collapsed');
        panel.classList.toggle('collapsed', recolhido);
        fabOpenPanel.classList.toggle('hidden', !recolhido || window.innerWidth > 768);
        mobileToggleText.innerHTML = recolhido
            ? '<i class="fa-solid fa-chevron-down"></i> Expandir painel'
            : '<i class="fa-solid fa-chevron-up"></i> Recolher para ver o mapa';
    }
    $('mobile-toggle-btn').addEventListener('click', () => toggleMobilePanel());
    fabOpenPanel.addEventListener('click', () => toggleMobilePanel(false));

    // ==========================================
    // INICIALIZAÇÃO
    // ==========================================
    window.SF = {
        map, api, showAlert, escapeHtml, bboxVisivel, bboxValido, mostrarView,
        areaCobertaPeloPainel, camadasDados, CATEGORIAS_FALHA, ganchos, carregarHistorico
    };

    carregarStatus();
    atualizarTextoBbox();
    carregarEpicentros();
    carregarFalhas();
});
