// Interface da análise de correlação (Fase 4).
// Depende de window.SF, exposto por map.js.
document.addEventListener('DOMContentLoaded', () => {
    const SF = window.SF;
    if (!SF) return;
    const { map, api, showAlert, escapeHtml } = SF;
    const $ = (id) => document.getElementById(id);

    // Cores do gráfico validadas (dataviz validate_palette: todas as checagens passam)
    const COR_OBSERVADO = '#b5462a';
    const COR_ESPERADO = '#3a6ea5';

    const CONCLUSAO_VISUAL = {
        associacao: { classe: 'positiva', icone: 'fa-solid fa-circle-check' },
        excesso_local: { classe: 'positiva', icone: 'fa-solid fa-circle-check' },
        proximidade_sem_excesso: { classe: 'parcial', icone: 'fa-solid fa-circle-half-stroke' },
        sem_associacao: { classe: 'neutra', icone: 'fa-solid fa-circle-minus' },
        afastamento: { classe: 'neutra', icone: 'fa-solid fa-arrows-left-right' }
    };

    const br = (v, casas = 1) => (v == null ? '–' : Number(v).toLocaleString('pt-BR', {
        minimumFractionDigits: casas, maximumFractionDigits: casas
    }));
    const pTexto = (p) => (p < 0.001 ? '< 0,001' : br(p, 3));

    // Estado da análise aberta
    let atual = null;              // resultado completo
    let porEpicentro = new Map();  // id -> {dist_km, falha_id, ponto_falha}
    let grafico = null;
    let kmSelecionado = null;

    // Camadas da análise no mapa
    const camadaArea = L.layerGroup().addTo(map);
    const camadaBuffer = L.layerGroup().addTo(map);
    const camadaLigacao = L.layerGroup().addTo(map);
    const camadaDestaque = L.layerGroup().addTo(map);

    // ==========================================
    // FORMULÁRIO
    // ==========================================
    function atualizarBboxAnalise() {
        const b = SF.bboxVisivel();
        $('bbox-analise-texto').textContent = SF.bboxValido(b)
            ? `Lat ${b.sul.toFixed(2)} a ${b.norte.toFixed(2)} · Lon ${b.oeste.toFixed(2)} a ${b.leste.toFixed(2)}`
            : '--';
    }
    map.on('moveend', atualizarBboxAnalise);

    async function carregarFontes() {
        const box = $('an-fontes');
        try {
            const data = await api('/api/falhas/fontes');
            const marcadas = new Set([...box.querySelectorAll('input:checked')].map(i => i.value));
            const primeiraVez = !box.querySelector('input');
            box.innerHTML = '<legend>Fontes de falhas</legend>';
            if (!data.fontes.length) {
                box.insertAdjacentHTML('beforeend', '<small class="form-hint">Nenhuma falha importada.</small>');
                return;
            }
            data.fontes.forEach(f => {
                const marcado = primeiraVez || marcadas.has(f.fonte);
                box.insertAdjacentHTML('beforeend', `
                    <label class="check"><input type="checkbox" value="${escapeHtml(f.fonte)}" ${marcado ? 'checked' : ''}>
                    ${escapeHtml(f.fonte)} <small>(${f.total.toLocaleString('pt-BR')})</small></label>`);
            });
        } catch (e) {
            showAlert(e.message);
        }
    }

    // Territórios (Brasil e UFs) para a área de estudo
    let territoriosCarregados = false;
    async function carregarTerritorios() {
        if (territoriosCarregados) return;
        try {
            const data = await api('/api/territorios');
            $('an-territorio').innerHTML = data.territorios
                .map(t => `<option value="${t.codigo}">${escapeHtml(t.nome)}</option>`).join('');
            territoriosCarregados = true;
        } catch (e) {
            showAlert(e.message);
        }
    }

    async function desenharTerritorio(codigo, enquadrarMapa = false) {
        const data = await api(`/api/territorios/${encodeURIComponent(codigo)}`);
        camadaArea.clearLayers();
        L.geoJSON(data.geometria, {
            style: { color: COR_OBSERVADO, weight: 2, dashArray: '8 6', fill: false }, interactive: false
        }).addTo(camadaArea);
        if (enquadrarMapa) enquadrar(limitesBbox(data.bbox));
    }

    $('an-territorio').addEventListener('change', (e) => {
        document.querySelector('input[name="an-area"][value="territorio"]').checked = true;
        desenharTerritorio(e.target.value, true).catch(err => showAlert(err.message));
    });

    SF.ganchos.mostrarView = (nome) => {
        if (nome === 'analise') {
            atualizarBboxAnalise();
            carregarTerritorios();
            carregarFontes();
        }
    };

    function lerBuffers() {
        const valores = $('an-buffers').value.split(/[,;\s]+/).filter(Boolean).map(Number);
        if (!valores.length || valores.some(v => !(v > 0 && v <= 500))) {
            throw new Error('Buffers: informe distâncias em km entre 0 e 500, separadas por vírgula.');
        }
        return valores;
    }

    $('form-analise').addEventListener('submit', async (ev) => {
        ev.preventDefault();
        const bbox = SF.bboxVisivel();
        if (!SF.bboxValido(bbox)) { showAlert('Área visível inválida. Ajuste o mapa.'); return; }

        let buffers;
        try { buffers = lerBuffers(); } catch (e) { showAlert(e.message); return; }

        const todas = [...$('an-fontes').querySelectorAll('input')];
        const marcadas = todas.filter(i => i.checked).map(i => i.value);
        if (todas.length && !marcadas.length) { showAlert('Marque ao menos uma fonte de falhas.'); return; }

        const corpo = {
            bbox,
            // 'importada': o servidor usa a caixa exata das importações que cruzam a área visível
            area: document.querySelector('input[name="an-area"]:checked').value,
            territorio: document.querySelector('input[name="an-area"]:checked').value === 'territorio'
                ? $('an-territorio').value : null,
            incluir_sem_profundidade: $('an-sem-prof').checked,
            buffers_km: buffers,
            n_simulacoes: Number($('an-sims').value),
            prof_max_km: $('an-prof').value || null,
            min_mag: $('an-mag').value || null,
            inicio: $('an-inicio').value || null,
            fim: $('an-fim').value || null,
            nome: $('an-nome').value.trim() || null,
            // Todas marcadas = sem filtro (inclui fontes importadas depois)
            fontes_falhas: marcadas.length === todas.length ? null : marcadas
        };

        const botao = $('btn-analisar');
        const original = botao.innerHTML;
        botao.disabled = true;
        botao.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Calculando...';
        try {
            const data = await api('/api/analise', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(corpo)
            });
            mostrarResultado(data.resultado);
            showAlert(`Análise concluída em ${br(data.resultado.tempo_s, 1)} s e salva no histórico.`, 'info');
        } catch (e) {
            showAlert(e.message);
        } finally {
            botao.disabled = false;
            botao.innerHTML = original;
        }
    });

    // ==========================================
    // RESULTADO
    // ==========================================
    function mostrarResultado(r) {
        atual = r;
        porEpicentro = new Map(r.por_epicentro.map(p => [p.id, p]));
        $('resultado-analise').classList.remove('hidden');
        $('res-nome').textContent = r.nome ? `Resultado · ${r.nome}` : 'Resultado';

        // Conclusão
        const visual = CONCLUSAO_VISUAL[r.conclusao] || CONCLUSAO_VISUAL.sem_associacao;
        $('res-conclusao').className = `conclusao-card ${visual.classe}`;
        $('res-icone').className = visual.icone;
        $('res-titulo').textContent = r.conclusao_titulo;
        $('res-texto').textContent = r.interpretacao;

        // Números principais
        $('res-med-obs').textContent = `${br(r.distancias.mediana_km)} km`;
        $('res-med-ale').textContent = `${br(r.aleatorio.mediana_km)} km`;
        $('res-p').textContent = pTexto(r.teste_mediana.p_valor);

        const p = r.parametros;
        const filtros = [
            p.prof_max_km != null ? `prof. ≤ ${br(p.prof_max_km, 0)} km` : 'todas as profundidades',
            p.min_mag != null ? `M ≥ ${br(p.min_mag)}` : null,
            p.inicio || p.fim ? `${p.inicio || '…'} a ${p.fim || '…'}` : null
        ].filter(Boolean).join(' · ');
        const cobertura = r.cobertura_importada_pct != null ? ` · ${br(r.cobertura_importada_pct, 0)}% da área com sismos importados` : '';
        $('res-meta').textContent = `${r.n_epicentros.toLocaleString('pt-BR')} epicentros · ${r.n_falhas.toLocaleString('pt-BR')} falhas · ` +
            `${filtros} · ${p.n_simulacoes} simulações · área ${Math.round(r.area_km2).toLocaleString('pt-BR')} km²${cobertura}`;

        // Exportação (só para análises salvas)
        $('res-exportar').classList.toggle('hidden', !r.id);
        if (r.id) {
            ['csv', 'geojson', 'json'].forEach(f => { $(`exp-${f}`).href = `/api/analises/${r.id}/exportar?formato=${f}`; });
        }

        const avisos = $('res-avisos');
        avisos.innerHTML = (r.avisos || []).map(a => `<li><i class="fa-solid fa-triangle-exclamation"></i> ${escapeHtml(a)}</li>`).join('');
        avisos.classList.toggle('hidden', !(r.avisos || []).length);

        renderBuffers(r);
        renderGrafico(r);
        renderRanking(r);
        renderOutros(r);
        desenharNoMapa(r);
    }

    function renderBuffers(r) {
        const corpo = $('res-buffers').querySelector('tbody');
        corpo.innerHTML = r.buffers.map(b => {
            // p ajustado (Bonferroni); análises antigas não têm o campo
            const pAj = b.p_ajustado ?? Math.min(1, b.p_valor * r.buffers.length);
            const sig = pAj < 0.05 && (b.razao || 0) > 1;
            return `<tr data-km="${b.km}" tabindex="0" class="${sig ? 'sig' : ''}">
                <td>${br(b.km, 0)} km</td>
                <td><strong>${br(b.observado_pct)}%</strong> <small>(${b.n_observado})</small></td>
                <td>${br(b.esperado_pct)}%</td>
                <td>${b.razao == null ? '–' : br(b.razao, 2) + '×'}</td>
                <td>${pTexto(pAj)}${sig ? ' <i class="fa-solid fa-star" title="Excesso significativo"></i>' : ''}</td>
            </tr>`;
        }).join('');
        corpo.querySelectorAll('tr').forEach(tr => {
            const ver = () => mostrarBuffer(Number(tr.dataset.km));
            tr.addEventListener('click', ver);
            tr.addEventListener('keydown', (ev) => { if (ev.key === 'Enter') ver(); });
        });
    }

    function renderGrafico(r) {
        const h = r.histograma;
        // O último intervalo acumula tudo acima do teto calculado no backend
        const ultimo = h.observado.length - 1;
        const rotulos = h.observado.map((_, i) => i === ultimo
            ? `≥ ${br(h.bordas_km[i], 0)}`
            : `${br(h.bordas_km[i], 0)}–${br(h.bordas_km[i + 1], 0)}`);
        if (grafico) grafico.destroy();
        grafico = new Chart($('grafico-hist'), {
            data: {
                labels: rotulos,
                datasets: [
                    {
                        type: 'line', label: 'Esperado ao acaso', data: h.esperado,
                        borderColor: COR_ESPERADO, backgroundColor: COR_ESPERADO,
                        borderWidth: 2, borderDash: [6, 4], pointRadius: 0, pointHoverRadius: 5,
                        tension: 0.25, order: 0
                    },
                    {
                        type: 'bar', label: 'Observado', data: h.observado,
                        backgroundColor: COR_OBSERVADO, borderRadius: { topLeft: 4, topRight: 4 },
                        borderSkipped: 'bottom', categoryPercentage: 0.92, barPercentage: 0.94, order: 1
                    }
                ]
            },
            options: {
                responsive: true, maintainAspectRatio: false, animation: false,
                interaction: { mode: 'index', intersect: false },
                plugins: {
                    legend: { position: 'top', align: 'start', labels: { boxWidth: 14, boxHeight: 8, font: { size: 11 }, color: '#5f6368' } },
                    tooltip: {
                        callbacks: {
                            title: (itens) => `${itens[0].label} km da falha`,
                            label: (c) => `${c.dataset.label}: ${br(c.parsed.y, c.dataset.type === 'line' ? 1 : 0)} eventos`
                        }
                    }
                },
                scales: {
                    x: {
                        title: { display: true, text: 'Distância à falha mais próxima (km)', color: '#5f6368', font: { size: 11 } },
                        ticks: { color: '#80868b', font: { size: 10 }, maxRotation: 0, autoSkip: true, maxTicksLimit: 6 },
                        grid: { display: false }
                    },
                    y: {
                        beginAtZero: true,
                        title: { display: true, text: 'Nº de epicentros', color: '#5f6368', font: { size: 11 } },
                        ticks: { color: '#80868b', font: { size: 10 }, precision: 0 },
                        grid: { color: '#eeeeee' }, border: { display: false }
                    }
                }
            }
        });
    }

    function renderRanking(r) {
        const corpo = $('res-ranking').querySelector('tbody');
        if (!r.ranking_falhas.length) {
            corpo.innerHTML = `<tr><td colspan="4" class="vazio">Nenhum epicentro a até ${br(r.parametros.buffers_km.at(-1), 0)} km de uma falha.</td></tr>`;
            return;
        }
        corpo.innerHTML = r.ranking_falhas.map((f, i) => {
            const cat = SF.CATEGORIAS_FALHA[f.categoria] || SF.CATEGORIAS_FALHA.outra;
            return `<tr data-i="${i}" tabindex="0">
                <td><span class="falha-cor" style="background:${cat.cor}" title="${cat.rotulo}"></span>
                    ${escapeHtml(f.nome || 'Sem nome')}<small>${escapeHtml(f.tipo || cat.rotulo)}</small></td>
                <td>${f.eventos}</td>
                <td>${br(f.mag_max)}</td>
                <td>${f.eventos_por_100km == null ? '–' : br(f.eventos_por_100km, 1)}</td>
            </tr>`;
        }).join('');
        corpo.querySelectorAll('tr').forEach(tr => {
            const ver = () => destacarFalha(r.ranking_falhas[Number(tr.dataset.i)]);
            tr.addEventListener('click', ver);
            tr.addEventListener('keydown', (ev) => { if (ev.key === 'Enter') ver(); });
        });
    }

    function renderOutros(r) {
        const linhas = [
            ['Teste KS', `D = ${br(r.ks.estatistica, 3)}, p ${r.ks.p_valor < 0.001 ? '< 0,001' : '= ' + br(r.ks.p_valor, 3)}`,
             'Diferença de forma entre as distribuições observada e aleatória (não indica, sozinho, se os eventos estão mais perto).'],
            ['Magnitude × distância', r.spearman_mag_dist
                ? `ρ de Spearman = ${br(r.spearman_mag_dist.rho, 2)}, p = ${pTexto(r.spearman_mag_dist.p_valor)}`
                : 'Dados insuficientes',
             'ρ negativo: eventos maiores tendem a estar mais perto das falhas.'],
            ['Distâncias observadas', `quartis ${br(r.distancias.p25_km)} – ${br(r.distancias.p75_km)} km, mín. ${br(r.distancias.min_km, 2)} km`, ''],
        ];
        $('res-outros').innerHTML = linhas.map(([t, v, d]) =>
            `<dt>${t}</dt><dd>${v}${d ? `<small>${d}</small>` : ''}</dd>`).join('');
    }

    // ==========================================
    // MAPA
    // ==========================================
    function limitesBbox(b) { return [[b.sul, b.oeste], [b.norte, b.leste]]; }

    function desenharNoMapa(r) {
        camadaArea.clearLayers();
        if (r.parametros.territorio) {
            desenharTerritorio(r.parametros.territorio).catch(err => showAlert(err.message));
        } else {
            L.rectangle(limitesBbox(r.parametros.bbox), {
                color: COR_OBSERVADO, weight: 2, dashArray: '8 6', fill: false, interactive: false
            }).addTo(camadaArea);
        }
        // Zona padrão: o primeiro buffer com excesso significativo, senão o de 10 km (ou o 1º)
        const sig = r.buffers.find(b => (b.p_ajustado ?? b.p_valor * r.buffers.length) < 0.05 && (b.razao || 0) > 1);
        const padrao = sig || r.buffers.find(b => b.km === 10) || r.buffers[0];
        mostrarBuffer(padrao.km, false);
    }

    async function mostrarBuffer(km, enquadrar = true) {
        if (!atual?.id) return;
        kmSelecionado = km;
        $('res-buffers').querySelectorAll('tr').forEach(tr =>
            tr.classList.toggle('selecionada', Number(tr.dataset.km) === km));
        // Para áreas grandes (ex.: Brasil) a primeira vez leva alguns segundos
        const aviso = setTimeout(() => showAlert(`Calculando a zona de ${br(km, 0)} km em torno das falhas...`, 'info'), 1200);
        try {
            const data = await api(`/api/analises/${atual.id}/buffer?km=${km}`);
            clearTimeout(aviso);
            if (kmSelecionado !== km) return; // outro buffer foi escolhido enquanto carregava
            camadaBuffer.clearLayers();
            if (data.geometria) {
                L.geoJSON(data.geometria, {
                    style: { color: COR_ESPERADO, weight: 1, opacity: 0.6, fillColor: COR_ESPERADO, fillOpacity: 0.12 },
                    interactive: false
                }).addTo(camadaBuffer);
            }
            if (enquadrar) enquadrarArea();
        } catch (e) {
            clearTimeout(aviso);
            showAlert(`Não foi possível desenhar a zona de ${km} km: ${e.message}`);
        }
    }

    function enquadrar(limites) {
        const { esquerda, topo } = SF.areaCobertaPeloPainel();
        map.flyToBounds(limites, { paddingTopLeft: [esquerda + 30, topo + 30], paddingBottomRight: [30, 30], maxZoom: 11 });
    }
    const enquadrarArea = () => atual && enquadrar(limitesBbox(atual.parametros.bbox));

    function destacarFalha(f) {
        camadaDestaque.clearLayers();
        const [[s, o], [n, l]] = f.limites;
        L.rectangle([[s, o], [n, l]], { color: '#202124', weight: 1.5, dashArray: '3 4', fill: false, interactive: false })
            .addTo(camadaDestaque);
        enquadrar([[s, o], [n, l]]);
        setTimeout(() => camadaDestaque.clearLayers(), 6000);
    }

    // Popup do epicentro: distância à falha mais próxima e linha até ela
    SF.ganchos.popupEpicentro = (e) => {
        const info = porEpicentro.get(e.id);
        if (!info) return '';
        return `<span class="popup-dist"><i class="fa-solid fa-ruler"></i> ${br(info.dist_km, info.dist_km < 10 ? 2 : 1)} km da falha mais próxima</span>`;
    };
    SF.ganchos.abrirEpicentro = (e) => {
        camadaLigacao.clearLayers();
        const info = porEpicentro.get(e.id);
        if (!info) return;
        L.polyline([[e.lat, e.lon], info.ponto_falha], {
            color: '#202124', weight: 2, dashArray: '4 4', interactive: false
        }).addTo(camadaLigacao);
        L.circleMarker(info.ponto_falha, { radius: 4, color: '#202124', fillColor: '#fff', fillOpacity: 1, weight: 2, interactive: false })
            .addTo(camadaLigacao);
    };
    SF.ganchos.fecharEpicentro = () => camadaLigacao.clearLayers();

    function limparAnalise() {
        atual = null;
        porEpicentro = new Map();
        kmSelecionado = null;
        [camadaArea, camadaBuffer, camadaLigacao, camadaDestaque].forEach(c => c.clearLayers());
        if (grafico) { grafico.destroy(); grafico = null; }
        $('resultado-analise').classList.add('hidden');
    }
    $('btn-limpar-analise').addEventListener('click', limparAnalise);

    // ==========================================
    // HISTÓRICO -> abrir análise salva
    // ==========================================
    SF.ganchos.abrirAnalise = async (id) => {
        try {
            const data = await api(`/api/analises/${id}`);
            SF.mostrarView('analise');
            mostrarResultado(data.resultado);
            enquadrarArea();
            $('resultado-analise').scrollIntoView({ behavior: 'smooth', block: 'start' });
        } catch (e) {
            showAlert(e.message);
        }
    };

    atualizarBboxAnalise();
});
