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

    // Auto-load on page open
    this.loadLimits(MC.activeOrg());
    this.loadTrends(MC.activeOrg(), 30);
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
    gridEl.innerHTML = limits.map(lim => {
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
      return `<div class="col-sm-6 col-lg-4 col-xl-3">
        <div class="card h-100 border-0 shadow-sm">
          <div class="card-body py-3 px-3">
            <div class="d-flex justify-content-between align-items-start mb-2">
              <span class="fw-semibold small" style="color:var(--doane-navy);">${MC._escHtml(lim.name)}</span>
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
    }).join('');
    gridEl.classList.remove('d-none');
    const emptyEl = document.getElementById('limitsEmpty');
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
      '#FF7900', '#1F3864', '#28a745', '#dc3545',
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
      <th style="background:var(--doane-navy);color:#fff;">Query</th>
      ${orgs.map(o => `<th style="background:var(--doane-navy);color:#fff;">${MC._escHtml(o.toUpperCase())}</th>`).join('')}
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
        <td class="small fw-semibold" style="color:var(--doane-navy);">${MC._escHtml(label)}</td>
        ${cells}
      </tr>`;
    }).join('');

    if (tableWrap) tableWrap.classList.remove('d-none');
    if (emptyEl) emptyEl.classList.add('d-none');
  },
};
