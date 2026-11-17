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

    // Camadas de dados: preenchidas nas próximas fases (epicentros, falhas, buffers...)
    const camadasDados = {
        'Epicentros': L.layerGroup().addTo(map),
        'Falhas': L.layerGroup().addTo(map)
    };
    L.control.layers(camadasBase, camadasDados, { position: 'bottomright' }).addTo(map);

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
        const data = await res.json();
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
            <div class="leg-mags">${mags}</div>`;
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
            ? `<a href="https://earthquake.usgs.gov/earthquakes/eventpage/${encodeURIComponent(e.id_externo)}" target="_blank" rel="noopener">Ver na USGS</a>` : '';
        return `<div class="popup-epi">
            <div class="popup-mag" style="background:${corProfundidade(e.profundidade_km)}">M ${e.magnitude?.toFixed(1) ?? '?'}</div>
            <div>
                <strong>${escapeHtml(e.local || 'Local não informado')}</strong>
                <span>${escapeHtml(e.data_hora)} UTC</span>
                <span>Profundidade: ${e.profundidade_km != null ? e.profundidade_km.toFixed(1) + ' km' : '?'} · ${escapeHtml(e.tipo_magnitude || '')}</span>
                <span>${e.lat.toFixed(4)}, ${e.lon.toFixed(4)} · ${link}</span>
            </div></div>`;
    };

    let requisicaoAtual = 0;
    async function carregarEpicentros() {
        const id = ++requisicaoAtual;
        const b = bboxVisivel();
        if (!bboxValido(b)) return; // mapa ainda sem tamanho (página carregando)
        const minMag = $('filtro-mag').value;
        const qs = new URLSearchParams({ ...b, min_mag: minMag, limite: LIMITE_EXIBICAO });
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
                }).bindPopup(() => popupEpicentro(e)).addTo(camada);
            });
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
        debounceMapa = setTimeout(carregarEpicentros, 300);
    });

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
        botao.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Consultando a USGS...';
        try {
            const data = await api('/api/epicentros/importar', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    bbox,
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
            lista.innerHTML = itens.map(a => `
                <div class="history-item">
                    <div class="history-item-route">${escapeHtml(a.nome || `Análise #${a.id}`)}</div>
                    <div class="history-item-meta"><span>#${a.id}</span><span>${escapeHtml(a.criado_em.split(' ')[0])}</span></div>
                </div>`).join('');
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
    carregarStatus();
    atualizarTextoBbox();
    carregarEpicentros();
});
