'use strict';

MC.observe = {
  _trendsChart: null,

  init() {
    document.getElementById('btnRefreshLimits')?.addEventListener('click', () => {
      const org = document.getElementById('limitsOrgSelect')?.value || MC.activeOrg();
      this.loadLimits(org);
    });

    document.getElementById('btnRefreshTrends')?.addEventListener('click', () => {
      const org = document.getElementById('trendsOrgSelect')?.value || MC.activeOrg();
      const days = document.getElementById('trendsDaysSelect')?.value || 30;
      this.loadTrends(org, parseInt(days, 10));
    });

    document.getElementById('trendsDaysSelect')?.addEventListener('change', () => {
      const org = document.getElementById('trendsOrgSelect')?.value || MC.activeOrg();
      const days = document.getElementById('trendsDaysSelect')?.value || 30;
      this.loadTrends(org, parseInt(days, 10));
    });

    document.getElementById('trendsOrgSelect')?.addEventListener('change', () => {
      const org = document.getElementById('trendsOrgSelect')?.value || MC.activeOrg();
      const days = document.getElementById('trendsDaysSelect')?.value || 30;
      this.loadTrends(org, parseInt(days, 10));
    });

    document.getElementById('btnRunCrossOrg')?.addEventListener('click', () => {
      const orgs = Array.from(document.querySelectorAll('.cross-org-check:checked'))
        .map(el => el.value);
      if (orgs.length === 0) {
        MC.showToast('Select at least one org', 'warning');
        return;
      }
      this.loadCrossOrg(orgs);
    });

    document.getElementById('btnRefreshRecordCounts')?.addEventListener('click', () => {
      const org = document.getElementById('recordCountsOrgSelect')?.value || MC.activeOrg();
      this.loadRecordCounts(org);
    });

    document.getElementById('recordCountsOrgSelect')?.addEventListener('change', () => {
      const org = document.getElementById('recordCountsOrgSelect')?.value || MC.activeOrg();
      this.loadRecordCounts(org);
    });

    document.getElementById('btnToggleThresholds')?.addEventListener('click', () => this._toggleThresholdEditor());
    document.getElementById('btnSaveThreshold')?.addEventListener('click', () => this._saveThreshold());
    document.getElementById('btnResetThreshold')?.addEventListener('click', () => this._resetThreshold());

    this._initDrift();

    // Auto-load on page open
    this.loadLimits(MC.activeOrg());
    this.loadTrends(MC.activeOrg(), 30);
    this.loadRecordCounts(MC.activeOrg());
  },

  async loadLimits(org) {
    const loadingEl = document.getElementById('limitsLoading');
    const emptyEl = document.getElementById('limitsEmpty');
    const gridEl = document.getElementById('limitsGrid');
    if (loadingEl) loadingEl.classList.remove('d-none');
    if (emptyEl) emptyEl.classList.add('d-none');
    if (gridEl) gridEl.classList.add('d-none');
    try {
      const data = await MC.api(`/observe/limits?org=${encodeURIComponent(org)}`);
      this.renderLimitCards(data.limits || []);
    } catch (err) {
      MC.showToast(`Failed to load limits: ${err.message}`, 'danger');
      if (emptyEl) {
        emptyEl.textContent = `Failed to load limits: ${err.message}`;
        emptyEl.classList.remove('d-none');
      }
    } finally {
      if (loadingEl) loadingEl.classList.add('d-none');
    }
  },

  renderLimitCards(limits) {
    const gridEl = document.getElementById('limitsGrid');
    const emptyEl = document.getElementById('limitsEmpty');
    if (!gridEl) return;
    if (!limits || limits.length === 0) {
      if (emptyEl) {
        emptyEl.textContent = 'No limit data returned.';
        emptyEl.classList.remove('d-none');
      }
      return;
    }
    gridEl.innerHTML = limits.map(lim => this._renderLimitCard(lim)).join('');
    gridEl.classList.remove('d-none');
    if (emptyEl) emptyEl.classList.add('d-none');
  },

  async loadTrends(org, days) {
    const loadingEl = document.getElementById('trendsLoading');
    const emptyEl = document.getElementById('trendsEmpty');
    const wrapEl = document.getElementById('trendsChartWrap');
    if (loadingEl) loadingEl.classList.remove('d-none');
    if (emptyEl) emptyEl.classList.add('d-none');
    if (wrapEl) wrapEl.style.opacity = '0.4';
    try {
      const data = await MC.api(`/observe/trends?org=${encodeURIComponent(org)}&days=${days}`);
      this.renderTrendsChart(data);
    } catch (err) {
      MC.showToast(`Failed to load trends: ${err.message}`, 'danger');
      if (emptyEl) {
        emptyEl.textContent = `Failed to load trends: ${err.message}`;
        emptyEl.classList.remove('d-none');
      }
    } finally {
      if (loadingEl) loadingEl.classList.add('d-none');
      if (wrapEl) wrapEl.style.opacity = '1';
    }
  },

  renderTrendsChart(data) {
    const emptyEl = document.getElementById('trendsEmpty');
    const canvas = document.getElementById('trendsChart');
    if (!canvas) return;

    const labels = data.labels || [];
    const series = data.series || [];

    if (!labels.length || !series.length) {
      if (emptyEl) emptyEl.classList.remove('d-none');
      return;
    }
    if (emptyEl) emptyEl.classList.add('d-none');

    const palette = [
      '#FF7900', '#0063B0', '#28a745', '#dc3545',
      '#ffc107', '#17a2b8', '#6610f2', '#e83e8c',
    ];

    const datasets = series.map((s, i) => ({
      label: s.name,
      data: s.values,
      borderColor: palette[i % palette.length],
      backgroundColor: palette[i % palette.length] + '22',
      tension: 0.3,
      pointRadius: labels.length > 14 ? 2 : 4,
      fill: false,
    }));

    if (this._trendsChart) {
      this._trendsChart.destroy();
      this._trendsChart = null;
    }

    const ctx = canvas.getContext('2d');
    this._trendsChart = new Chart(ctx, {
      type: 'line',
      data: { labels, datasets },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        interaction: { mode: 'index', intersect: false },
        plugins: {
          legend: { position: 'bottom', labels: { boxWidth: 12, font: { size: 11 } } },
          tooltip: {
            callbacks: {
              label: (ctx) => ` ${ctx.dataset.label}: ${ctx.parsed.y.toFixed(1)}%`,
            },
          },
        },
        scales: {
          x: {
            ticks: { maxTicksLimit: 10, font: { size: 10 } },
            grid: { display: false },
          },
          y: {
            min: 0,
            max: 100,
            ticks: { callback: (v) => v + '%', font: { size: 10 } },
            grid: { color: '#e9ecef' },
          },
        },
      },
    });
  },

  async loadCrossOrg(orgs) {
    const loadingEl = document.getElementById('crossOrgLoading');
    const emptyEl = document.getElementById('crossOrgEmpty');
    const tableWrap = document.getElementById('crossOrgTableWrap');
    if (loadingEl) loadingEl.classList.remove('d-none');
    if (emptyEl) emptyEl.classList.add('d-none');
    if (tableWrap) tableWrap.classList.add('d-none');
    try {
      const params = orgs.map(o => `orgs=${encodeURIComponent(o)}`).join('&');
      const data = await MC.api(`/observe/cross-org?${params}`);
      this.renderCrossOrgTable(data);
    } catch (err) {
      MC.showToast(`Comparison failed: ${err.message}`, 'danger');
      if (emptyEl) {
        emptyEl.textContent = `Comparison failed: ${err.message}`;
        emptyEl.classList.remove('d-none');
      }
    } finally {
      if (loadingEl) loadingEl.classList.add('d-none');
    }
  },

  renderCrossOrgTable(data) {
    const headEl = document.getElementById('crossOrgTableHead');
    const bodyEl = document.getElementById('crossOrgTableBody');
    const tableWrap = document.getElementById('crossOrgTableWrap');
    const emptyEl = document.getElementById('crossOrgEmpty');
    if (!headEl || !bodyEl) return;

    const queries = data.queries || [];
    const orgs = data.orgs || [];
    const counts = data.counts || {};

    if (!queries.length || !orgs.length) {
      if (emptyEl) {
        emptyEl.textContent = 'No data returned.';
        emptyEl.classList.remove('d-none');
      }
      return;
    }

    headEl.innerHTML = `<tr>
      <th style="background:var(--doane-slate);color:#fff;">Query</th>
      ${orgs.map(o => `<th style="background:var(--doane-slate);color:#fff;">${MC._escHtml(o.toUpperCase())}</th>`).join('')}
    </tr>`;

    bodyEl.innerHTML = queries.map(label => {
      const values = orgs.map(o => {
        const v = counts[o] ? counts[o][label] : null;
        return v == null ? null : parseInt(v, 10);
      });
      const baseline = values.find(v => v != null);

      const cells = values.map(v => {
        if (v == null) return `<td class="text-muted small text-center">—</td>`;
        const fmt = v.toLocaleString();
        if (baseline == null || baseline === 0) {
          return `<td class="text-center">${fmt}</td>`;
        }
        const diffPct = Math.abs((v - baseline) / baseline) * 100;
        let cellCls = '';
        if (v !== baseline) {
          cellCls = diffPct > 25 ? 'table-danger' : diffPct > 10 ? 'table-warning' : '';
        }
        return `<td class="text-center ${cellCls}">${fmt}</td>`;
      }).join('');

      return `<tr>
        <td class="small fw-semibold" style="color:var(--doane-slate);">${MC._escHtml(label)}</td>
        ${cells}
      </tr>`;
    }).join('');

    if (tableWrap) tableWrap.classList.remove('d-none');
    if (emptyEl) emptyEl.classList.add('d-none');
  },

  async loadRecordCounts(org) {
    const loadingEl = document.getElementById('recordCountsLoading');
    const emptyEl = document.getElementById('recordCountsEmpty');
    const tableWrap = document.getElementById('recordCountsTableWrap');
    if (loadingEl) loadingEl.classList.remove('d-none');
    if (emptyEl) emptyEl.classList.add('d-none');
    if (tableWrap) tableWrap.classList.add('d-none');
    try {
      const data = await MC.api(`/observe/record-counts?org=${encodeURIComponent(org)}`);
      this.renderRecordCounts(data || []);
    } catch (err) {
      MC.showToast(`Failed to load record counts: ${err.message}`, 'danger');
      if (emptyEl) {
        emptyEl.textContent = `Failed to load record counts: ${err.message}`;
        emptyEl.classList.remove('d-none');
      }
    } finally {
      if (loadingEl) loadingEl.classList.add('d-none');
    }
  },

  renderRecordCounts(rows) {
    const tbody = document.getElementById('recordCountsBody');
    const tableWrap = document.getElementById('recordCountsTableWrap');
    const emptyEl = document.getElementById('recordCountsEmpty');
    if (!tbody) return;
    if (!rows || rows.length === 0) {
      if (emptyEl) {
        emptyEl.textContent = 'No record count data returned.';
        emptyEl.classList.remove('d-none');
      }
      return;
    }
    tbody.innerHTML = rows.map(row => {
      const countFmt = row.count != null
        ? row.count.toLocaleString()
        : `<span class="text-danger small" title="${MC._escHtml(row.error || '')}">error</span>`;
      const sfUrl = MC.sfObjectLink(row.object);
      const actionCell = sfUrl
        ? `<a href="${sfUrl}" target="_blank" rel="noopener" class="btn btn-link btn-sm p-0 small">Open in SF &#8599;</a>`
        : `<a href="/soql?object=${encodeURIComponent(row.object)}" class="btn btn-link btn-sm p-0 small text-muted">SOQL</a>`;
      return `<tr>
        <td class="fw-semibold small" style="color:var(--doane-slate);">${MC._escHtml(row.label)}</td>
        <td class="text-end font-monospace">${countFmt}</td>
        <td class="text-center no-print">${actionCell}</td>
      </tr>`;
    }).join('');
    if (tableWrap) tableWrap.classList.remove('d-none');
    if (emptyEl) emptyEl.classList.add('d-none');
  },

  _renderLimitCard(lim) {
    const pct = Math.min(lim.pct, 100);
    const barCls =
      lim.status === 'green' ? 'bg-success' :
      lim.status === 'amber' ? 'bg-warning' : 'bg-danger';
    const badgeCls =
      lim.status === 'green' ? 'badge-green' :
      lim.status === 'amber' ? 'badge-amber' : 'badge-red';
    const usedFmt = (lim.used || 0).toLocaleString();
    const maxFmt = (lim.max || 0).toLocaleString();
    const remainFmt = (lim.remaining || 0).toLocaleString();
    const customBadge = lim.custom_threshold
      ? `<span class="badge badge-amber ms-1" title="Custom threshold">&#9881;</span>`
      : '';
    return `<div class="col-sm-6 col-lg-4 col-xl-3">
      <div class="card h-100 border-0 shadow-sm">
        <div class="card-body py-3 px-3">
          <div class="d-flex justify-content-between align-items-start mb-2">
            <span class="fw-semibold small" style="color:var(--doane-slate);">${MC._escHtml(lim.name)}${customBadge}</span>
            <span class="badge ${badgeCls}">${pct.toFixed(1)}%</span>
          </div>
          <div class="progress mb-2" style="height:8px;" title="${usedFmt} used of ${maxFmt}">
            <div class="progress-bar ${barCls}"
                 role="progressbar"
                 style="width:${pct}%"
                 aria-valuenow="${pct}"
                 aria-valuemin="0"
                 aria-valuemax="100"></div>
          </div>
          <div class="d-flex justify-content-between small text-muted">
            <span>${usedFmt} used</span>
            <span>${remainFmt} left / ${maxFmt}</span>
          </div>
        </div>
      </div>
    </div>`;
  },

  _toggleThresholdEditor() {
    const wrap = document.getElementById('thresholdEditorWrap');
    if (!wrap) return;
    const isHidden = wrap.classList.contains('d-none');
    wrap.classList.toggle('d-none', !isHidden);
    if (isHidden) {
      this._loadCurrentThresholds();
    }
  },

  async _saveThreshold() {
    const limitName = document.getElementById('thresholdLimitSelect')?.value || '';
    const amber = parseFloat(document.getElementById('thresholdAmber')?.value || '50');
    const red = parseFloat(document.getElementById('thresholdRed')?.value || '80');
    const msgEl = document.getElementById('thresholdSaveMsg');
    if (!limitName) {
      if (msgEl) { msgEl.className = 'small text-danger'; msgEl.textContent = 'Please select a limit.'; }
      return;
    }
    try {
      await MC.api('/observe/thresholds', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ limit_name: limitName, amber_pct: amber, red_pct: red }),
      });
      if (msgEl) { msgEl.className = 'small text-success'; msgEl.textContent = 'Threshold saved.'; }
      await this._loadCurrentThresholds();
      const org = document.getElementById('limitsOrgSelect')?.value || MC.activeOrg();
      this.loadLimits(org);
    } catch (err) {
      if (msgEl) { msgEl.className = 'small text-danger'; msgEl.textContent = `Save failed: ${err.message}`; }
    }
  },

  async _resetThreshold() {
    const limitName = document.getElementById('thresholdLimitSelect')?.value || '';
    const msgEl = document.getElementById('thresholdSaveMsg');
    if (!limitName) {
      if (msgEl) { msgEl.className = 'small text-danger'; msgEl.textContent = 'Please select a limit.'; }
      return;
    }
    try {
      await MC.api(`/observe/thresholds/${encodeURIComponent(limitName)}`, { method: 'DELETE' });
      if (msgEl) { msgEl.className = 'small text-success'; msgEl.textContent = 'Threshold reset to default.'; }
      await this._loadCurrentThresholds();
      const org = document.getElementById('limitsOrgSelect')?.value || MC.activeOrg();
      this.loadLimits(org);
    } catch (err) {
      if (msgEl) { msgEl.className = 'small text-danger'; msgEl.textContent = `Reset failed: ${err.message}`; }
    }
  },

  async _loadCurrentThresholds() {
    const listEl = document.getElementById('currentThresholdsList');
    if (!listEl) return;
    try {
      const data = await MC.api('/observe/thresholds');
      const entries = Object.entries(data || {});
      if (!entries.length) {
        listEl.textContent = 'No custom thresholds set — all limits use defaults (50% amber / 80% red).';
        return;
      }
      listEl.innerHTML = '<strong>Active overrides:</strong> ' +
        entries.map(([name, t]) =>
          `${MC._escHtml(name)}: amber=${t.amber_pct}%, red=${t.red_pct}%`
        ).join(' &nbsp;|&nbsp; ');
    } catch (_) {
      listEl.textContent = 'Could not load current thresholds.';
    }
  },

  _initDrift() {
    document.getElementById('btnRunDrift')?.addEventListener('click', () => this.runDrift());
  },

  async runDrift() {
    const baseline = document.getElementById('driftBaselineOrg')?.value || 'prod';
    const target = document.getElementById('driftTargetOrg')?.value || 'sandbox';
    const loadingEl = document.getElementById('driftLoading');
    const emptyEl = document.getElementById('driftEmpty');
    const summaryEl = document.getElementById('driftSummary');
    const tableWrap = document.getElementById('driftTableWrap');
    if (loadingEl) loadingEl.classList.remove('d-none');
    if (emptyEl) emptyEl.classList.add('d-none');
    if (summaryEl) summaryEl.classList.add('d-none');
    if (tableWrap) tableWrap.classList.add('d-none');
    try {
      const data = await MC.api(`/observe/sandbox-drift?baseline=${encodeURIComponent(baseline)}&target=${encodeURIComponent(target)}`);
      this._renderDrift(data);
    } catch (err) {
      MC.showToast(`Drift check failed: ${err.message}`, 'danger');
      if (emptyEl) {
        emptyEl.textContent = `Drift check failed: ${err.message}`;
        emptyEl.classList.remove('d-none');
      }
    } finally {
      if (loadingEl) loadingEl.classList.add('d-none');
    }
  },

  _renderDrift(data) {
    const summaryEl = document.getElementById('driftSummary');
    const tableWrap = document.getElementById('driftTableWrap');
    const tbody = document.getElementById('driftTableBody');
    const emptyEl = document.getElementById('driftEmpty');
    if (!tbody) return;

    const checks = data.checks || [];
    if (!checks.length) {
      if (emptyEl) {
        emptyEl.textContent = 'No checks returned.';
        emptyEl.classList.remove('d-none');
      }
      return;
    }

    // Summary badges
    const okCount = checks.filter(c => c.status === 'ok').length;
    const total = checks.length;
    const summaryBadgeCls = okCount === total ? 'badge-green' : okCount >= total * 0.8 ? 'badge-amber' : 'badge-red';
    if (summaryEl) {
      summaryEl.innerHTML = `<span class="badge ${summaryBadgeCls} fs-6">${okCount} of ${total} checks within tolerance</span>
        <span class="small text-muted ms-2">${MC._escHtml(data.baseline_org || '')} → ${MC._escHtml(data.target_org || '')}</span>`;
      summaryEl.classList.remove('d-none');
    }

    // Status badge map
    const statusBadge = {
      ok:       '<span class="badge badge-green">OK</span>',
      warning:  '<span class="badge badge-amber">WARNING</span>',
      critical: '<span class="badge badge-red">CRITICAL</span>',
      error:    '<span class="badge bg-secondary">ERROR</span>',
    };

    tbody.innerHTML = checks.map(c => {
      const baseFmt = c.baseline_count != null ? c.baseline_count.toLocaleString() : '—';
      const tgtFmt  = c.target_count  != null ? c.target_count.toLocaleString()  : '—';

      let deltaFmt = '—';
      if (c.delta != null) {
        const sign = c.delta > 0 ? '+' : '';
        const colorCls = c.delta > 0 ? 'text-success' : c.delta < 0 ? 'text-danger' : '';
        deltaFmt = `<span class="${colorCls}">${sign}${c.delta.toLocaleString()}</span>`;
      }

      const deltaPctFmt = (c.delta_pct != null && c.baseline_count !== 0)
        ? `${c.delta_pct > 0 ? '+' : ''}${c.delta_pct}%`
        : '';

      const badge = statusBadge[c.status] || `<span class="badge bg-secondary">${MC._escHtml(c.status || '')}</span>`;
      const title = c.error ? ` title="${MC._escHtml(c.error)}"` : '';

      return `<tr${title}>
        <td class="small fw-semibold" style="color:var(--doane-slate);">${MC._escHtml(c.label)}</td>
        <td class="text-end font-monospace">${baseFmt}</td>
        <td class="text-end font-monospace">${tgtFmt}</td>
        <td class="text-end font-monospace">${deltaFmt}</td>
        <td class="text-end font-monospace">${MC._escHtml(deltaPctFmt)}</td>
        <td class="text-center">${badge}</td>
      </tr>`;
    }).join('');

    if (tableWrap) tableWrap.classList.remove('d-none');
    if (emptyEl) emptyEl.classList.add('d-none');
  },
};
