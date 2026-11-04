document.addEventListener('DOMContentLoaded', () => {
    // ==========================================
    // 1. INICIALIZAÇÃO DO MAPA (Leaflet)
    // ==========================================
    const map = L.map('map', {
        zoomControl: false
    }).setView([-23.5505, -46.6333], 13);

    L.control.zoom({ position: 'bottomright' }).addTo(map);

    const osmLayer = L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        attribution: '&copy; OpenStreetMap contributors',
        maxZoom: 19
    }).addTo(map);

    const satelliteLayer = L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}', {
        attribution: 'Tiles &copy; Esri',
        maxZoom: 18
    });

    L.control.layers({ "Ruas": osmLayer, "Satélite": satelliteLayer }, null, { position: 'bottomright' }).addTo(map);

    // ==========================================
    // 2. ESTADO DA APLICAÇÃO
    // ==========================================
    let origin = null; // { lat, lon, name }
    let dest = null;   // { lat, lon, name }
    let activeMode = 'carro'; // 'melhor', 'carro', 'moto', 'transporte', 'a_pe', 'bicicleta'

    let originMarker = null;
    let destMarker = null;
    let stepMarker = null;

    let routeLayers = []; // armazena polylines das rotas alternativas
    let currentRoutesData = []; // dados das rotas retornadas pelo backend
    let activeRouteIndex = 0;

    let contextMenuLatLng = null;
    let searchDebounceTimer = null;

    const createCustomIcon = (type) => {
        const className = type === 'origin' ? 'custom-pin-origin' : 'custom-pin-dest';
        const label = type === 'origin' ? 'A' : 'B';
        return L.divIcon({
            className: 'custom-pin-wrapper',
            html: `<div class="custom-pin ${className}">${label}</div>`,
            iconSize: [30, 30],
            iconAnchor: [15, 30],
            popupAnchor: [0, -30]
        });
    };

    // ==========================================
    // 3. ELEMENTOS DO DOM
    // ==========================================
    const originInput = document.getElementById('origin-input');
    const destInput = document.getElementById('dest-input');
    const originSuggestions = document.getElementById('origin-suggestions');
    const destSuggestions = document.getElementById('dest-suggestions');
    const btnSwap = document.getElementById('btn-swap');
    const btnMyLocation = document.getElementById('btn-my-location');
    const btnClearAll = document.getElementById('btn-clear-all');
    const alertBox = document.getElementById('alert-box');

    const modeTabs = document.querySelectorAll('.mode-tab');
    const badgeCarro = document.getElementById('badge-carro');
    const badgeMoto = document.getElementById('badge-moto');
    const badgeTransporte = document.getElementById('badge-transporte');
    const badgeAPe = document.getElementById('badge-a_pe');
    const badgeBicicleta = document.getElementById('badge-bicicleta');

    const quickShareBar = document.getElementById('quick-share-bar');
    const btnCopyLink = document.getElementById('btn-copy-link');

    const routesContainer = document.getElementById('routes-container');
    const routesList = document.getElementById('routes-list');

    const stepsDrawer = document.getElementById('steps-drawer');
    const btnBackToRoutes = document.getElementById('btn-back-to-routes');
    const drawerRouteTitle = document.getElementById('drawer-route-title');
    const drawerRouteMeta = document.getElementById('drawer-route-meta');
    const stepsDrawerBody = document.getElementById('steps-drawer-body');

    const historyDrawer = document.getElementById('history-drawer');
    const historyDrawerBody = document.getElementById('history-drawer-body');
    const btnClearHistoryDb = document.getElementById('btn-clear-history-db');
    const btnDockHistory = document.getElementById('btn-dock-history');
    const btnDockRoutes = document.getElementById('btn-dock-routes');

    const contextMenu = document.getElementById('context-menu');
    const ctxSetOrigin = document.getElementById('ctx-set-origin');
    const ctxSetDest = document.getElementById('ctx-set-dest');

    // ==========================================
    // 4. FUNÇÕES DE UTILIDADE E ALERTAS
    // ==========================================
    function showAlert(message, type = 'error') {
        alertBox.className = `alert alert-${type}`;
        alertBox.textContent = message;
        alertBox.classList.remove('hidden');
        setTimeout(() => alertBox.classList.add('hidden'), 4000);
    }

    function hideAlert() {
        alertBox.classList.add('hidden');
    }

    function getModeIconHtml(mode) {
        switch (mode) {
            case 'moto': return '<i class="fa-solid fa-motorcycle"></i>';
            case 'bicicleta': return '<i class="fa-solid fa-person-biking"></i>';
            case 'a_pe': return '<i class="fa-solid fa-person-walking"></i>';
            case 'transporte': return '<i class="fa-solid fa-bus-simple"></i>';
            default: return '<i class="fa-solid fa-car"></i>';
        }
    }

    // ==========================================
    // 5. MARCADORES NO MAPA
    // ==========================================
    function setOriginPoint(lat, lon, name) {
        origin = { lat, lon, name };
        originInput.value = name;
        originSuggestions.classList.add('hidden');

        if (originMarker) map.removeLayer(originMarker);
        originMarker = L.marker([lat, lon], {
            icon: createCustomIcon('origin'),
            draggable: true
        }).addTo(map);

        originMarker.bindPopup(`<b>Ponto de Partida (A)</b><br>${name}`).openPopup();

        originMarker.on('dragend', async (e) => {
            const pos = e.target.getLatLng();
            const addr = await reverseGeocode(pos.lat, pos.lng);
            setOriginPoint(pos.lat, pos.lng, addr);
            if (dest) calculateRoute();
        });

        if (!dest) {
            map.flyTo([lat, lon], 14);
        } else {
            calculateRoute();
        }
    }

    function setDestPoint(lat, lon, name) {
        dest = { lat, lon, name };
        destInput.value = name;
        destSuggestions.classList.add('hidden');

        if (destMarker) map.removeLayer(destMarker);
        destMarker = L.marker([lat, lon], {
            icon: createCustomIcon('dest'),
            draggable: true
        }).addTo(map);

        destMarker.bindPopup(`<b>Destino (B)</b><br>${name}`).openPopup();

        destMarker.on('dragend', async (e) => {
            const pos = e.target.getLatLng();
            const addr = await reverseGeocode(pos.lat, pos.lng);
            setDestPoint(pos.lat, pos.lng, addr);
            if (origin) calculateRoute();
        });

        if (!origin) {
            map.flyTo([lat, lon], 14);
        } else {
            calculateRoute();
        }
    }

    // ==========================================
    // 6. BUSCA E AUTO-COMPLETAR (Nominatim)
    // ==========================================
    async function searchLocation(query) {
        if (!query || query.length < 2) return [];
        try {
            const res = await fetch(`/api/search?q=${encodeURIComponent(query)}`);
            const data = await res.json();
            return data.results || (data.dados && data.dados.results) || [];
        } catch (e) {
            return [];
        }
    }

    async function reverseGeocode(lat, lon) {
        try {
            const res = await fetch(`/api/reverse?lat=${lat}&lon=${lon}`);
            const data = await res.json();
            return data.display_name || `${lat.toFixed(5)}, ${lon.toFixed(5)}`;
        } catch (e) {
            return `${lat.toFixed(5)}, ${lon.toFixed(5)}`;
        }
    }

    function setupAutocomplete(inputElem, dropdownElem, setPointFn) {
        inputElem.addEventListener('input', () => {
            clearTimeout(searchDebounceTimer);
            const query = inputElem.value.trim();
            if (query.length < 3) {
                dropdownElem.classList.add('hidden');
                return;
            }
            searchDebounceTimer = setTimeout(async () => {
                const results = await searchLocation(query);
                dropdownElem.innerHTML = '';
                if (results.length === 0) {
                    dropdownElem.classList.add('hidden');
                    return;
                }
                results.forEach(item => {
                    const div = document.createElement('div');
                    div.className = 'suggestion-item';
                    div.innerHTML = `<i class="fa-solid fa-location-dot"></i> <span>${item.display_name}</span>`;
                    div.addEventListener('click', () => {
                        setPointFn(item.lat, item.lon, item.display_name);
                        dropdownElem.classList.add('hidden');
                    });
                    dropdownElem.appendChild(div);
                });
                dropdownElem.classList.remove('hidden');
            }, 300);
        });
    }

    setupAutocomplete(originInput, originSuggestions, setOriginPoint);
    setupAutocomplete(destInput, destSuggestions, setDestPoint);

    document.addEventListener('click', (e) => {
        if (!e.target.closest('.input-container')) {
            originSuggestions.classList.add('hidden');
            destSuggestions.classList.add('hidden');
        }
        if (!e.target.closest('#context-menu')) {
            contextMenu.classList.add('hidden');
        }
    });

    // ==========================================
    // 7. CÁLCULO DE ROTAS E MODAIS (OSRM)
    // ==========================================
    async function calculateRoute() {
        if (!origin || !dest) return;

        hideAlert();
        stepsDrawer.classList.add('hidden');

        try {
            const effectiveMode = activeMode === 'melhor' ? 'carro' : activeMode;
            const res = await fetch('/api/route', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    origin_lat: origin.lat,
                    origin_lon: origin.lon,
                    origin_name: origin.name,
                    dest_lat: dest.lat,
                    dest_lon: dest.lon,
                    dest_name: dest.name,
                    modo: effectiveMode
                })
            });

            const data = await res.json();
            const isSuccess = data.sucesso !== undefined ? data.sucesso : data.success;

            if (!isSuccess) {
                showAlert(data.erro || data.error || "Não foi possível traçar a rota.");
                return;
            }

            // Atualiza os badges de tempo nas abas superiores
            const estimativas = data.tempos_modais || {};
            if (badgeCarro && estimativas.carro) badgeCarro.textContent = estimativas.carro;
            if (badgeMoto && estimativas.moto) badgeMoto.textContent = estimativas.moto;
            if (badgeTransporte && estimativas.transporte) badgeTransporte.textContent = estimativas.transporte;
            if (badgeAPe && estimativas.a_pe) badgeAPe.textContent = estimativas.a_pe;
            if (badgeBicicleta && estimativas.bicicleta) badgeBicicleta.textContent = estimativas.bicicleta;

            currentRoutesData = data.rotas || [data.melhor_rota || data];
            activeRouteIndex = 0;

            renderRouteCards(currentRoutesData);
            drawRoutesOnMap(currentRoutesData, activeRouteIndex);

            quickShareBar.classList.remove('hidden');
            routesContainer.classList.remove('hidden');

        } catch (e) {
            console.error(e);
            showAlert("Erro de comunicação ao calcular a rota.");
        }
    }

    // ==========================================
    // 8. RENDERIZAÇÃO DOS CARDS DE ROTAS
    // ==========================================
    function renderRouteCards(routes) {
        routesList.innerHTML = '';

        routes.forEach((route, idx) => {
            const card = document.createElement('div');
            card.className = `route-card ${idx === activeRouteIndex ? 'active' : ''}`;
            card.dataset.index = idx;

            const modeIcon = getModeIconHtml(route.modo || activeMode);

            card.innerHTML = `
                <div class="route-card-top">
                    <div class="route-card-icon">${modeIcon}</div>
                    <div class="route-card-content">
                        <div class="route-card-header">
                            <span class="route-card-title">${route.via || 'Opção ' + (idx + 1)}</span>
                            <span class="route-card-time">${route.duracao_formatada}</span>
                        </div>
                        <div class="route-card-sub">
                            <span>${route.descricao || 'Rota calculada'}</span>
                            <span class="route-card-distance">${route.distancia_formatada}</span>
                        </div>
                    </div>
                </div>
                <div class="route-card-actions">
                    <button class="card-link-btn btn-details" data-index="${idx}">Detalhes</button>
                    <button class="card-link-btn btn-view" data-index="${idx}">Visualizar</button>
                </div>
            `;

            // Clique no card seleciona esta rota
            card.addEventListener('click', (e) => {
                if (e.target.classList.contains('btn-details')) {
                    openStepsDrawer(route);
                    return;
                }
                selectRoute(idx);
            });

            routesList.appendChild(card);
        });
    }

    function selectRoute(index) {
        activeRouteIndex = index;
        document.querySelectorAll('.route-card').forEach((c, idx) => {
            c.classList.toggle('active', idx === index);
        });
        drawRoutesOnMap(currentRoutesData, index);
    }

    function drawRoutesOnMap(routes, selectedIndex) {
        // Remove camadas antigas
        routeLayers.forEach(l => map.removeLayer(l));
        routeLayers = [];

        if (!routes || routes.length === 0) return;

        // Desenha primeiro as rotas alternativas em cinza
        routes.forEach((route, idx) => {
            if (idx !== selectedIndex) {
                const altLine = L.polyline(route.coordenadas, {
                    color: '#9aa0a6',
                    weight: 5,
                    opacity: 0.7,
                    lineJoin: 'round'
                }).addTo(map);

                altLine.on('click', () => selectRoute(idx));
                routeLayers.push(altLine);
            }
        });

        // Desenha a rota selecionada em Azul do Google Maps por cima
        const mainRoute = routes[selectedIndex];
        if (mainRoute) {
            const mainLine = L.polyline(mainRoute.coordenadas, {
                color: '#1a73e8',
                weight: 6,
                opacity: 0.9,
                lineJoin: 'round'
            }).addTo(map);

            routeLayers.push(mainLine);
            const padding = window.innerWidth <= 768 ? [25, 25] : [60, 60];
            map.fitBounds(mainLine.getBounds(), { padding });
        }
    }

    // ==========================================
    // 9. DETALHES PASSO A PASSO (DRAWER)
    // ==========================================
    function openStepsDrawer(route) {
        drawerRouteTitle.textContent = route.via || "Percurso";
        drawerRouteMeta.textContent = `${route.duracao_formatada} (${route.distancia_formatada})`;
        stepsDrawerBody.innerHTML = '';

        const steps = route.passos || [];
        if (steps.length === 0) {
            stepsDrawerBody.innerHTML = '<p class="empty-state">Sem manobras disponíveis.</p>';
        } else {
            steps.forEach(step => {
                const card = document.createElement('div');
                card.className = 'step-card';
                card.innerHTML = `
                    <div class="step-icon"><i class="fa-solid fa-diamond-turn-right"></i></div>
                    <div class="step-info">
                        <div class="step-instruction">${step.instrucao}</div>
                        <div class="step-distance">${step.distancia_formatada}</div>
                    </div>
                `;

                if (step.localizacao) {
                    card.addEventListener('click', () => {
                        if (stepMarker) map.removeLayer(stepMarker);
                        stepMarker = L.circleMarker(step.localizacao, {
                            radius: 8,
                            fillColor: '#fbbc04',
                            color: '#ffffff',
                            weight: 2,
                            fillOpacity: 0.95
                        }).addTo(map);
                        map.flyTo(step.localizacao, 17);
                    });
                }

                stepsDrawerBody.appendChild(card);
            });
        }

        routesContainer.classList.add('hidden');
        stepsDrawer.classList.remove('hidden');
    }

    btnBackToRoutes.addEventListener('click', () => {
        stepsDrawer.classList.add('hidden');
        routesContainer.classList.remove('hidden');
        if (stepMarker) map.removeLayer(stepMarker);
    });

    // ==========================================
    // 10. ABAS DE MODOS DE TRANSPORTE
    // ==========================================
    modeTabs.forEach(tab => {
        tab.addEventListener('click', () => {
            modeTabs.forEach(t => t.classList.remove('active'));
            tab.classList.add('active');
            activeMode = tab.dataset.mode;
            if (origin && dest) {
                calculateRoute();
            }
        });
    });

    // ==========================================
    // 11. INVERSÃO, LOCALIZAÇÃO E LIMPAR
    // ==========================================
    btnSwap.addEventListener('click', () => {
        if (!origin && !dest) return;
        const temp = origin;
        origin = dest;
        dest = temp;

        originInput.value = origin ? origin.name : '';
        destInput.value = dest ? dest.name : '';

        if (origin) setOriginPoint(origin.lat, origin.lon, origin.name);
        if (dest) setDestPoint(dest.lat, dest.lon, dest.name);

        if (origin && dest) calculateRoute();
    });

    btnClearAll.addEventListener('click', () => {
        origin = null;
        dest = null;
        originInput.value = '';
        destInput.value = '';

        if (originMarker) map.removeLayer(originMarker);
        if (destMarker) map.removeLayer(destMarker);
        if (stepMarker) map.removeLayer(stepMarker);

        routeLayers.forEach(l => map.removeLayer(l));
        routeLayers = [];

        routesContainer.classList.add('hidden');
        stepsDrawer.classList.add('hidden');
        quickShareBar.classList.add('hidden');

        // Reset badges
        ['carro', 'moto', 'transporte', 'a_pe', 'bicicleta'].forEach(m => {
            const b = document.getElementById(`badge-${m}`);
            if (b) b.textContent = '--';
        });

        hideAlert();
    });

    // ==========================================
    // GEOLOCALIZAÇÃO ROBUSTA (GPS + FALLBACK IP)
    // ==========================================
    async function getMyLocation() {
        btnMyLocation.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i>';
        const fabLocation = document.getElementById('fab-my-location');
        if (fabLocation) fabLocation.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i>';

        const applyLocation = async (lat, lon, label) => {
            const addr = await reverseGeocode(lat, lon);
            const display = label || `Minha Localização (${addr.split(',')[0]})`;
            setOriginPoint(lat, lon, display);
            map.flyTo([lat, lon], 15);
            btnMyLocation.innerHTML = '<i class="fa-solid fa-crosshairs"></i>';
            if (fabLocation) fabLocation.innerHTML = '<i class="fa-solid fa-crosshairs"></i>';
        };

        const tryFallbackIP = async () => {
            try {
                const res = await fetch('/api/my-location');
                const data = await res.json();
                const d = data.dados || data;
                if (d && d.lat && d.lon) {
                    await applyLocation(d.lat, d.lon, `Minha Localização (${d.cidade || 'Rede'})`);
                    showAlert("Localização obtida pela rede IP (HTTPS desativado no navegador).", "info");
                    return;
                }
            } catch (e) {
                console.error("Erro no fallback IP:", e);
            }
            showAlert("Não foi possível obter sua localização. Clique no mapa para definir o ponto de partida.");
            btnMyLocation.innerHTML = '<i class="fa-solid fa-crosshairs"></i>';
            if (fabLocation) fabLocation.innerHTML = '<i class="fa-solid fa-crosshairs"></i>';
        };

        // Se o navegador não suportar ou estiver bloqueando em conexões HTTP
        if (!navigator.geolocation) {
            await tryFallbackIP();
            return;
        }

        navigator.geolocation.getCurrentPosition(
            async (pos) => {
                await applyLocation(pos.coords.latitude, pos.coords.longitude);
            },
            async (err) => {
                console.warn("GPS do navegador bloqueado ou falhou. Usando IP fallback.", err);
                await tryFallbackIP();
            },
            { enableHighAccuracy: true, timeout: 6000, maximumAge: 60000 }
        );
    }

    btnMyLocation.addEventListener('click', getMyLocation);

    const fabLocation = document.getElementById('fab-my-location');
    if (fabLocation) {
        fabLocation.addEventListener('click', getMyLocation);
    }

    // ==========================================
    // CONTROLES DE RECOLHER / EXPANDIR NO MOBILE
    // ==========================================
    const mapsPanel = document.getElementById('maps-panel');
    const mobileToggleBtn = document.getElementById('mobile-toggle-btn');
    const mobileToggleText = document.getElementById('mobile-toggle-text');
    const fabOpenPanel = document.getElementById('fab-open-panel');

    function toggleMobilePanel(forceState = null) {
        if (!mapsPanel) return;
        const isCollapsed = forceState !== null ? forceState : !mapsPanel.classList.contains('collapsed');
        mapsPanel.classList.toggle('collapsed', isCollapsed);
        if (fabOpenPanel) fabOpenPanel.classList.toggle('hidden', !isCollapsed);

        if (mobileToggleText) {
            mobileToggleText.innerHTML = isCollapsed 
                ? '<i class="fa-solid fa-chevron-down"></i> Expandir opções de rotas' 
                : '<i class="fa-solid fa-chevron-up"></i> Recolher para ver o mapa';
        }
    }

    if (mobileToggleBtn) {
        mobileToggleBtn.addEventListener('click', () => toggleMobilePanel());
    }
    if (fabOpenPanel) {
        fabOpenPanel.addEventListener('click', () => toggleMobilePanel(false));
    }

    // Inicialização: detecta a cidade inicial por IP para não começar longe
    fetch('/api/my-location')
        .then(r => r.json())
        .then(data => {
            const d = data.dados || data;
            if (d && d.lat && d.lon && !origin && !dest) {
                map.setView([d.lat, d.lon], 13);
            }
        })
        .catch(() => {});


    btnCopyLink.addEventListener('click', () => {
        if (!origin || !dest) return;
        const url = `${window.location.origin}/?origem=${origin.lat},${origin.lon}&destino=${dest.lat},${dest.lon}&modo=${activeMode}`;
        navigator.clipboard.writeText(url).then(() => {
            showAlert("Link da rota copiado para a área de transferência!", "info");
        });
    });

    // ==========================================
    // 12. MENU DE CONTEXTO (Botão Direito)
    // ==========================================
    map.on('contextmenu', (e) => {
        contextMenuLatLng = e.latlng;
        contextMenu.style.top = `${e.originalEvent.clientY}px`;
        contextMenu.style.left = `${e.originalEvent.clientX}px`;
        contextMenu.classList.remove('hidden');
    });

    ctxSetOrigin.addEventListener('click', async () => {
        if (!contextMenuLatLng) return;
        contextMenu.classList.add('hidden');
        const addr = await reverseGeocode(contextMenuLatLng.lat, contextMenuLatLng.lng);
        setOriginPoint(contextMenuLatLng.lat, contextMenuLatLng.lng, addr);
    });

    ctxSetDest.addEventListener('click', async () => {
        if (!contextMenuLatLng) return;
        contextMenu.classList.add('hidden');
        const addr = await reverseGeocode(contextMenuLatLng.lat, contextMenuLatLng.lng);
        setDestPoint(contextMenuLatLng.lat, contextMenuLatLng.lng, addr);
    });

    // ==========================================
    // 13. DRAWER DE HISTÓRICO
    // ==========================================
    async function loadHistory() {
        try {
            const res = await fetch('/api/history');
            const data = await res.json();
            const list = data.history || (data.dados && data.dados.history) || [];
            renderHistory(list);
        } catch (e) {
            console.error(e);
        }
    }

    function renderHistory(items) {
        historyDrawerBody.innerHTML = '';
        if (items.length === 0) {
            historyDrawerBody.innerHTML = '<p class="empty-state">Nenhuma rota calculada ainda.</p>';
            return;
        }

        items.forEach(item => {
            const div = document.createElement('div');
            div.className = 'history-item';
            const oNome = (item.origem_nome || item.origin_name || '').split(',')[0];
            const dNome = (item.destino_nome || item.dest_name || '').split(',')[0];
            const dist = item.distancia_km || item.distance_km || 0;
            const dur = item.duracao_minutos || item.duration_minutes || 0;
            const criado = (item.criado_em || item.created_at || '').split(' ')[0];

            div.innerHTML = `
                <div class="history-item-route">
                    <span>${oNome}</span>
                    <i class="fa-solid fa-arrow-right" style="font-size: 10px; color: #80868b;"></i>
                    <span>${dNome}</span>
                </div>
                <div class="history-item-meta">
                    <span>${dist} km (${dur} min)</span>
                    <span>${criado}</span>
                </div>
            `;

            div.addEventListener('click', () => {
                setOriginPoint(item.origem_lat || item.origin_lat, item.origem_lon || item.origin_lon, item.origem_nome || item.origin_name);
                setDestPoint(item.destino_lat || item.dest_lat, item.destino_lon || item.dest_lon, item.destino_nome || item.dest_name);
                historyDrawer.classList.add('hidden');
            });

            historyDrawerBody.appendChild(div);
        });
    }

    btnDockHistory.addEventListener('click', () => {
        const isHidden = historyDrawer.classList.toggle('hidden');
        if (!isHidden) {
            routesContainer.classList.add('hidden');
            stepsDrawer.classList.add('hidden');
            loadHistory();
        } else {
            if (currentRoutesData.length > 0) routesContainer.classList.remove('hidden');
        }
    });

    btnDockRoutes.addEventListener('click', () => {
        historyDrawer.classList.add('hidden');
        if (currentRoutesData.length > 0) {
            routesContainer.classList.remove('hidden');
        }
    });

    btnClearHistoryDb.addEventListener('click', async () => {
        if (confirm("Deseja realmente limpar todo o histórico de rotas salvas?")) {
            await fetch('/api/history', { method: 'DELETE' });
            loadHistory();
        }
    });
});
