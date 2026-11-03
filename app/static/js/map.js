document.addEventListener('DOMContentLoaded', () => {
    // ==========================================
    // 1. INICIALIZAÇÃO DO MAPA (Leaflet)
    // ==========================================
    // Centro inicial: São Paulo / Brasil
    const map = L.map('map', {
        zoomControl: false
    }).setView([-23.5505, -46.6333], 13);

    // Controles de zoom no canto inferior direito estilo Google Maps
    L.control.zoom({ position: 'bottomright' }).addTo(map);

    // Camada padrão: OpenStreetMap
    const osmLayer = L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
        maxZoom: 19
    }).addTo(map);

    // Camada Satélite (Esri World Imagery)
    const satelliteLayer = L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}', {
        attribution: 'Tiles &copy; Esri &mdash; Source: Esri, i-cubed, USDA, USGS, AEX, GeoEye, Getmapping, Aerogrid, IGN, IGP, UPR-EGP, and the GIS User Community',
        maxZoom: 18
    });

    // Seletor de Camadas (Mapa de Ruas vs Satélite)
    const baseLayers = {
        "Mapa de Ruas": osmLayer,
        "Satélite": satelliteLayer
    };
    L.control.layers(baseLayers, null, { position: 'bottomright' }).addTo(map);

    // ==========================================
    // 2. ESTADO DA APLICAÇÃO
    // ==========================================
    let origin = null; // { lat, lon, name }
    let dest = null;   // { lat, lon, name }

    let originMarker = null;
    let destMarker = null;
    let routeLayer = null;
    let stepMarker = null;

    let contextMenuLatLng = null;
    let searchDebounceTimer = null;

    // Ícones personalizados
    const createCustomIcon = (type) => {
        const className = type === 'origin' ? 'custom-pin-origin' : 'custom-pin-dest';
        const label = type === 'origin' ? 'A' : 'B';
        return L.divIcon({
            className: 'custom-pin-wrapper',
            html: `<div class="custom-pin ${className}">${label}</div>`,
            iconSize: [32, 32],
            iconAnchor: [16, 32],
            popupAnchor: [0, -32]
        });
    };

    // ==========================================
    // 3. ELEMENTOS DO DOM
    // ==========================================
    const originInput = document.getElementById('origin-input');
    const destInput = document.getElementById('dest-input');
    const originSuggestions = document.getElementById('origin-suggestions');
    const destSuggestions = document.getElementById('dest-suggestions');
    const btnCalculate = document.getElementById('btn-calculate-route');
    const btnClear = document.getElementById('btn-clear-route');
    const btnSwap = document.getElementById('btn-swap-locations');
    const btnMyLocation = document.getElementById('btn-my-location');
    const alertBox = document.getElementById('alert-box');
    const routeSummary = document.getElementById('route-summary');
    const summaryTime = document.getElementById('summary-time');
    const summaryDistance = document.getElementById('summary-distance');
    const btnToggleSteps = document.getElementById('btn-toggle-steps');
    const stepsList = document.getElementById('steps-list');
    const stepsChevron = document.getElementById('steps-chevron');
    const contextMenu = document.getElementById('context-menu');
    const ctxSetOrigin = document.getElementById('ctx-set-origin');
    const ctxSetDest = document.getElementById('ctx-set-dest');
    const btnToggleHistory = document.getElementById('btn-toggle-history');
    const historyPanel = document.getElementById('history-panel');
    const historyItems = document.getElementById('history-items');
    const btnClearHistoryDb = document.getElementById('btn-clear-history-db');

    // ==========================================
    // 4. FUNÇÕES DE UTILIDADE E ALERTAS
    // ==========================================
    function showAlert(message, type = 'error') {
        alertBox.className = `alert alert-${type}`;
        alertBox.textContent = message;
        alertBox.classList.remove('hidden');
        setTimeout(() => {
            alertBox.classList.add('hidden');
        }, 5000);
    }

    function hideAlert() {
        alertBox.classList.add('hidden');
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

        // Arrastar marcador atualiza coordenada
        originMarker.on('dragend', async (e) => {
            const newPos = e.target.getLatLng();
            const address = await reverseGeocode(newPos.lat, newPos.lng);
            setOriginPoint(newPos.lat, newPos.lng, address);
        });

        if (!dest) {
            map.flyTo([lat, lon], 14);
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

        // Arrastar marcador atualiza coordenada
        destMarker.on('dragend', async (e) => {
            const newPos = e.target.getLatLng();
            const address = await reverseGeocode(newPos.lat, newPos.lng);
            setDestPoint(newPos.lat, newPos.lng, address);
        });

        if (!origin) {
            map.flyTo([lat, lon], 14);
        }
    }

    // ==========================================
    // 6. BUSCA E AUTO-COMPLETAR (Nominatim)
    // ==========================================
    async function searchLocation(query) {
        if (!query || query.length < 2) return [];
        try {
            const response = await fetch(`/api/search?q=${encodeURIComponent(query)}`);
            const data = await response.json();
            return data.results || [];
        } catch (error) {
            console.error("Erro na busca:", error);
            return [];
        }
    }

    async function reverseGeocode(lat, lon) {
        try {
            const response = await fetch(`/api/reverse?lat=${lat}&lon=${lon}`);
            const data = await response.json();
            return data.display_name || `${lat.toFixed(5)}, ${lon.toFixed(5)}`;
        } catch (error) {
            return `${lat.toFixed(5)}, ${lon.toFixed(5)}`;
        }
    }

    function handleInputAutocomplete(inputElem, dropdownElem, setPointCallback) {
        inputElem.addEventListener('input', () => {
            clearTimeout(searchDebounceTimer);
            const query = inputElem.value.trim();

            if (query.length < 3) {
                dropdownElem.classList.add('hidden');
                return;
            }

            searchDebounceTimer = setTimeout(async () => {
                const results = await searchLocation(query);
                renderSuggestions(results, dropdownElem, setPointCallback);
            }, 350);
        });
    }

    function renderSuggestions(results, dropdownElem, setPointCallback) {
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
                setPointCallback(item.lat, item.lon, item.display_name);
                dropdownElem.classList.add('hidden');
            });
            dropdownElem.appendChild(div);
        });

        dropdownElem.classList.remove('hidden');
    }

    handleInputAutocomplete(originInput, originSuggestions, setOriginPoint);
    handleInputAutocomplete(destInput, destSuggestions, setDestPoint);

    // Fechar sugestões ao clicar fora
    document.addEventListener('click', (e) => {
        if (!e.target.closest('.input-wrapper')) {
            originSuggestions.classList.add('hidden');
            destSuggestions.classList.add('hidden');
        }
        if (!e.target.closest('#context-menu')) {
            contextMenu.classList.add('hidden');
        }
    });

    // ==========================================
    // 7. CALCULAR ROTA (OSRM)
    // ==========================================
    async function calculateRoute() {
        if (!origin || !dest) {
            showAlert("Defina o ponto de partida e o destino para calcular a rota.");
            return;
        }

        hideAlert();
        btnCalculate.disabled = true;
        btnCalculate.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Traçando...';

        try {
            const response = await fetch('/api/route', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    origin_lat: origin.lat,
                    origin_lon: origin.lon,
                    origin_name: origin.name,
                    dest_lat: dest.lat,
                    dest_lon: dest.lon,
                    dest_name: dest.name
                })
            });

            const data = await response.json();

            if (!data.success) {
                showAlert(data.error || "Não foi possível traçar a rota.");
                return;
            }

            // Desenha a linha da rota no mapa
            if (routeLayer) map.removeLayer(routeLayer);

            routeLayer = L.polyline(data.coordinates, {
                color: '#1a73e8',
                weight: 6,
                opacity: 0.85,
                lineJoin: 'round'
            }).addTo(map);

            // Ajusta o zoom do mapa para enquadrar toda a rota
            map.fitBounds(routeLayer.getBounds(), { padding: [50, 50] });

            // Atualiza resumo
            summaryTime.textContent = data.duration_formatted;
            summaryDistance.textContent = data.distance_formatted;
            routeSummary.classList.remove('hidden');

            // Renderiza passos
            renderSteps(data.steps);

        } catch (error) {
            console.error("Erro ao traçar rota:", error);
            showAlert("Falha de comunicação ao calcular a rota.");
        } finally {
            btnCalculate.disabled = false;
            btnCalculate.innerHTML = '<i class="fa-solid fa-route"></i> Traçar Rota';
        }
    }

    btnCalculate.addEventListener('click', calculateRoute);

    // ==========================================
    // 8. INSTRUÇÕES PASSO A PASSO
    // ==========================================
    function renderSteps(steps) {
        stepsList.innerHTML = '';
        if (!steps || steps.length === 0) {
            stepsList.innerHTML = '<p class="empty-state">Nenhuma manobra encontrada.</p>';
            return;
        }

        steps.forEach((step, index) => {
            const card = document.createElement('div');
            card.className = 'step-card';
            card.innerHTML = `
                <div class="step-icon"><i class="fa-solid fa-diamond-turn-right"></i></div>
                <div class="step-info">
                    <div class="step-instruction">${step.instruction}</div>
                    <div class="step-distance">${step.distance_formatted}</div>
                </div>
            `;

            // Ao clicar no passo, dá zoom na manobra correspondente
            card.addEventListener('click', () => {
                if (step.location) {
                    if (stepMarker) map.removeLayer(stepMarker);
                    stepMarker = L.circleMarker(step.location, {
                        radius: 8,
                        fillColor: '#fbbc04',
                        color: '#ffffff',
                        weight: 2,
                        fillOpacity: 0.9
                    }).addTo(map);
                    map.flyTo(step.location, 17);
                }
            });

            stepsList.appendChild(card);
        });
    }

    btnToggleSteps.addEventListener('click', () => {
        const isHidden = stepsList.classList.toggle('hidden');
        stepsChevron.className = isHidden ? 'fa-solid fa-chevron-down' : 'fa-solid fa-chevron-up';
    });

    // ==========================================
    // 9. INVERTER PONTOS E LIMPAR
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

    btnClear.addEventListener('click', () => {
        origin = null;
        dest = null;
        originInput.value = '';
        destInput.value = '';

        if (originMarker) map.removeLayer(originMarker);
        if (destMarker) map.removeLayer(destMarker);
        if (routeLayer) map.removeLayer(routeLayer);
        if (stepMarker) map.removeLayer(stepMarker);

        routeSummary.classList.add('hidden');
        stepsList.classList.add('hidden');
        hideAlert();
    });

    // ==========================================
    // 10. LOCALIZAÇÃO DO NAVEGADOR
    // ==========================================
    btnMyLocation.addEventListener('click', () => {
        if (!navigator.geolocation) {
            showAlert("Geolocalização não suportada pelo navegador.");
            return;
        }

        btnMyLocation.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i>';

        navigator.geolocation.getCurrentPosition(
            async (pos) => {
                const lat = pos.coords.latitude;
                const lon = pos.coords.longitude;
                const address = await reverseGeocode(lat, lon);
                setOriginPoint(lat, lon, `Minha Localização (${address.split(',')[0]})`);
                btnMyLocation.innerHTML = '<i class="fa-solid fa-crosshairs"></i>';
            },
            (err) => {
                showAlert("Não foi possível obter a sua localização atual.");
                btnMyLocation.innerHTML = '<i class="fa-solid fa-crosshairs"></i>';
            }
        );
    });

    // ==========================================
    // 11. MENU DE CONTEXTO (Botão Direito no Mapa)
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
        const address = await reverseGeocode(contextMenuLatLng.lat, contextMenuLatLng.lng);
        setOriginPoint(contextMenuLatLng.lat, contextMenuLatLng.lng, address);
    });

    ctxSetDest.addEventListener('click', async () => {
        if (!contextMenuLatLng) return;
        contextMenu.classList.add('hidden');
        const address = await reverseGeocode(contextMenuLatLng.lat, contextMenuLatLng.lng);
        setDestPoint(contextMenuLatLng.lat, contextMenuLatLng.lng, address);
    });

    // ==========================================
    // 12. HISTÓRICO DE ROTAS
    // ==========================================
    async function loadHistory() {
        try {
            const response = await fetch('/api/history');
            const data = await response.json();
            renderHistory(data.history || []);
        } catch (error) {
            console.error("Erro ao carregar histórico:", error);
        }
    }

    function renderHistory(items) {
        historyItems.innerHTML = '';
        if (items.length === 0) {
            historyItems.innerHTML = '<p class="empty-state">Nenhuma rota calculada ainda.</p>';
            return;
        }

        items.forEach(item => {
            const div = document.createElement('div');
            div.className = 'history-item';
            div.innerHTML = `
                <div class="history-item-route">
                    <span>${item.origin_name.split(',')[0]}</span>
                    <i class="fa-solid fa-arrow-right" style="font-size: 10px; color: #80868b;"></i>
                    <span>${item.dest_name.split(',')[0]}</span>
                </div>
                <div class="history-item-meta">
                    <span>${item.distance_km} km (${item.duration_minutes} min)</span>
                    <span>${item.created_at ? item.created_at.split(' ')[0] : ''}</span>
                </div>
            `;

            // Ao clicar no item do histórico, carrega no formulário e calcula rota
            div.addEventListener('click', () => {
                setOriginPoint(item.origin_lat, item.origin_lon, item.origin_name);
                setDestPoint(item.dest_lat, item.dest_lon, item.dest_name);
                historyPanel.classList.add('hidden');
                calculateRoute();
            });

            historyItems.appendChild(div);
        });
    }

    btnToggleHistory.addEventListener('click', () => {
        const isHidden = historyPanel.classList.toggle('hidden');
        if (!isHidden) {
            loadHistory();
        }
    });

    btnClearHistoryDb.addEventListener('click', async () => {
        if (confirm("Deseja realmente limpar todo o histórico de rotas?")) {
            await fetch('/api/history', { method: 'DELETE' });
            loadHistory();
        }
    });
});
