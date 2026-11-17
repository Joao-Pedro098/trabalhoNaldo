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
            $('dados-vazio').classList.toggle('hidden', data.contagens.epicentros + data.contagens.falhas > 0);
        } catch (e) {
            showAlert(`Não foi possível consultar o banco: ${e.message}`);
        }
    }

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
        if (item.bbox) {
            const [sul, norte, oeste, leste] = item.bbox;
            map.flyToBounds([[sul, oeste], [norte, leste]], { maxZoom: 12 });
        } else {
            map.flyTo([item.lat, item.lon], 10);
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
});
