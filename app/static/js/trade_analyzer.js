(function () {
    // ROSTER is injected by the template: { teamName: [{name, id, role}, ...], ... }
    // `id` is the stable CBS PlayerID (the trade token sent to the backend).
    const selectedTeam = { A: '', B: '' };

    function playerOptions(team) {
        const players = ROSTER[team] || [];
        const hitters = players.filter(p => p.role === 'H');
        const pitchers = players.filter(p => p.role === 'P');

        let html = '<option value="">-- Select Player --</option>';
        if (hitters.length) {
            html += '<optgroup label="Hitters">';
            hitters.forEach(p => { html += `<option value="${p.id}">${p.name}</option>`; });
            html += '</optgroup>';
        }
        if (pitchers.length) {
            html += '<optgroup label="Pitchers">';
            pitchers.forEach(p => { html += `<option value="${p.id}">${p.name}</option>`; });
            html += '</optgroup>';
        }
        return html;
    }

    function makePlayerRow(side) {
        const row = document.createElement('div');
        row.className = 'player-row';
        row.innerHTML = `
            <select class="form-select player-select">${playerOptions(selectedTeam[side])}</select>
            <button type="button" class="btn btn-sm btn-outline-danger remove-player" title="Remove">&times;</button>
        `;
        row.querySelector('.remove-player').addEventListener('click', () => {
            row.remove();
            refreshAnalyzeState();
        });
        row.querySelector('.player-select').addEventListener('change', refreshAnalyzeState);
        return row;
    }

    function getSelectedPlayers(side) {
        return Array.from(
            document.querySelectorAll(`.player-list[data-side="${side}"] .player-select`)
        ).map(s => s.value).filter(v => v);
    }

    function refreshAnalyzeState() {
        const bothTeams = selectedTeam.A && selectedTeam.B;
        const anyPlayers = getSelectedPlayers('A').length > 0 || getSelectedPlayers('B').length > 0;
        document.getElementById('analyze-btn').disabled = !(bothTeams && anyPlayers);
    }

    // Team selection
    document.querySelectorAll('.team-select').forEach(sel => {
        sel.addEventListener('change', function () {
            const side = this.dataset.side;
            selectedTeam[side] = this.value;
            // Reset that side's player rows
            const list = document.querySelector(`.player-list[data-side="${side}"]`);
            list.innerHTML = '';
            document.querySelector(`.add-player[data-side="${side}"]`).disabled = !this.value;
            // A trade needs at least one player per team, so start with one row
            if (this.value) {
                list.appendChild(makePlayerRow(side));
            }
            refreshAnalyzeState();
        });
    });

    // Add player
    document.querySelectorAll('.add-player').forEach(btn => {
        btn.addEventListener('click', function () {
            const side = this.dataset.side;
            if (!selectedTeam[side]) return;
            document.querySelector(`.player-list[data-side="${side}"]`).appendChild(makePlayerRow(side));
        });
    });

    // Rendering helpers
    function fmtWp(v) {
        if (v === null || v === undefined) return '—';
        const sign = v > 0 ? '+' : '';
        const cls = v > 0 ? 'wp-pos' : (v < 0 ? 'wp-neg' : '');
        return `<span class="${cls}">${sign}${v.toFixed(3)}</span>`;
    }

    function fmtWins(v) {
        if (v === null || v === undefined) return '';
        const sign = v > 0 ? '+' : '';
        const cls = v > 0 ? 'wp-pos' : (v < 0 ? 'wp-neg' : '');
        return `<span class="${cls}">${sign}${v.toFixed(2)} W</span>`;
    }

    function fmtStats(p) {
        const s = p.stats || {};
        if (p.role === 'H') return `PA ${s.PA} · E ${s.E} · RC ${s.RC}`;
        if (p.role === 'P') return `IP ${s.IP} · ERA ${s.ERA}`;
        return '';
    }

    function renderPool(containerId, players) {
        const el = document.getElementById(containerId);
        if (!players.length) {
            el.innerHTML = '<div class="text-muted small fst-italic">none</div>';
            return;
        }
        el.innerHTML = players.map(p => `
            <div class="player-line">
                <span class="player-name">${p.player}</span>
                <span class="player-stats ms-auto">${fmtStats(p)}</span>
                <span class="player-wp">${fmtWp(p.wp_delta)}</span>
                <span class="player-wins">${fmtWins(p.wins_delta)}</span>
            </div>
        `).join('');
    }

    function fmtWpPlain(v) {
        if (v === null || v === undefined) return '—';
        return v.toFixed(4);
    }

    function renderSide(suffix, sideData) {
        document.getElementById('result-title-' + suffix).textContent = sideData.name;
        renderPool('leaving-' + suffix, sideData.leaving);
        renderPool('joining-' + suffix, sideData.joining);
        document.getElementById('summary-' + suffix).innerHTML = `
            <div class="wp-line"><span>Current WP</span><span>${fmtWpPlain(sideData.current_wp)} &nbsp;(${fmtWpPlain(sideData.current_wins)} W)</span></div>
            <div class="wp-line"><span>Projected WP (entire trade)</span><span>${fmtWpPlain(sideData.projected_wp)} &nbsp;(${fmtWpPlain(sideData.projected_wins)} W)</span></div>
            <div class="wp-line net-line"><span>Net change</span><span>${fmtWp(sideData.net_wp_delta)} &nbsp; ${fmtWins(sideData.net_wins_delta)}</span></div>
        `;
    }

    // Analyze
    document.getElementById('analyze-btn').addEventListener('click', function () {
        const errBox = document.getElementById('trade-error');
        errBox.classList.add('d-none');

        const payload = {
            teamA: selectedTeam.A,
            teamB: selectedTeam.B,
            teamA_gives: getSelectedPlayers('A'),
            teamB_gives: getSelectedPlayers('B'),
        };

        fetch('/trade-analyzer/analyze', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
        })
            .then(r => r.json().then(j => ({ ok: r.ok, body: j })))
            .then(({ ok, body }) => {
                if (!ok) {
                    errBox.textContent = body.error || 'Unable to analyze trade.';
                    errBox.classList.remove('d-none');
                    return;
                }
                renderSide('A', body.teamA);
                renderSide('B', body.teamB);
                document.getElementById('results').style.display = 'flex';
            })
            .catch(() => {
                errBox.textContent = 'Request failed. Please try again.';
                errBox.classList.remove('d-none');
            });
    });
})();
