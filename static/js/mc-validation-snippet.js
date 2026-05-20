'use strict';

MC.validation = {
  init() {
    document.getElementById('btnRunCompleteness')?.addEventListener('click', () => {
      this.runCompleteness();
    });
    if (document.getElementById('btnRunOrphanScan')) {
      this.initOrphans();
    }
  },

  initOrphans() {
    document.getElementById('btnRunOrphanScan').addEventListener('click', () => {
      this.runOrphanScan();
    });
  },

  async runOrphanScan() {
    const loadingEl = document.getElementById('orphanLoading');
    const emptyEl = document.getElementById('orphanEmpty');
    const summaryRow = document.getElementById('orphanSummaryRow');
    const resultsEl = document.getElementById('orphanResults');
    if (loadingEl) loadingEl.classList.remove('d-none');
    if (emptyEl) emptyEl.classList.add('d-none');
    if (summaryRow) summaryRow.classList.add('d-none');
    if (resultsEl) resultsEl.innerHTML = '';
    try {
      const checks = await MC.api('/validation/orphans/scan');
      this._renderOrphanResults(checks || []);
    } catch (err) {
      MC.showToast(`Orphan scan failed: ${err.message}`, 'danger');
      if (emptyEl) {
        emptyEl.textContent = `Scan failed: ${err.message}`;
        emptyEl.classList.remove('d-none');
      }
    } finally {
      if (loadingEl) loadingEl.classList.add('d-none');
    }
  },

  _orphanObjectType(key) {
    if (key.startsWith('cpe_')) return 'ContactPointEmail';
    if (key.startsWith('cpp_')) return 'ContactPointPhone';
    if (key.startsWith('cpa_')) return 'ContactPointAddress';
    if (key.startsWith('pa_')) return 'Account';
    return 'Account';
  },

  _renderOrphanResults(checks) {
    const resultsEl = document.getElementById('orphanResults');
    const emptyEl = document.getElementById('orphanEmpty');
    const summaryRow = document.getElementById('orphanSummaryRow');
    const summaryOk = document.getElementById('orphanSummaryOk');
    const summaryWarn = document.getElementById('orphanSummaryWarn');

    if (!resultsEl) return;

    if (!checks || checks.length === 0) {
      if (emptyEl) {
        emptyEl.textContent = 'No check data returned.';
        emptyEl.classList.remove('d-none');
      }
      return;
    }

    const nOk = checks.filter(c => c.status === 'ok').length;
    const nWarn = checks.filter(c => c.status === 'warning').length;
    if (summaryOk) summaryOk.textContent = `${nOk} check${nOk !== 1 ? 's' : ''} clean`;
    if (summaryWarn) summaryWarn.textContent = `${nWarn} check${nWarn !== 1 ? 's' : ''} with orphans`;
    if (summaryRow) summaryRow.classList.remove('d-none');

    const cards = checks.map(check => {
      const isOk = check.status === 'ok';
      const isError = check.status === 'error';
      const badgeCls = isOk ? 'badge-green' : isError ? 'badge-navy' : 'badge-amber';
      const badgeText = isOk ? 'OK' : isError ? 'ERROR' : `${(check.count || 0).toLocaleString()} orphans`;
      const collapseId = `orphanCollapse_${MC._escHtml(check.key)}`;
      const objectType = this._orphanObjectType(check.key);

      let sampleHtml = '';
      if (!isOk && !isError && check.samples && check.samples.length > 0) {
        const rows = check.samples.map(s => {
          const id = s.Id || '';
          return `<tr><td>${MC.sfLinkHtml(id, objectType)}</td></tr>`;
        }).join('');
        sampleHtml = `
          <div class="table-responsive mt-2">
            <table class="table table-sm table-striped results-table mb-0">
              <thead><tr><th>Record ID</th></tr></thead>
              <tbody>${rows}</tbody>
            </table>
          </div>`;
      }

      const bodyContent = `
        <p class="text-muted small mb-2">${MC._escHtml(check.description)}</p>
        ${isError ? `<div class="alert alert-secondary small py-1 px-2">Error: ${MC._escHtml(check.error || '')}</div>` : ''}
        ${sampleHtml}`;

      return `
        <div class="card shadow-sm mb-3">
          <div class="card-header d-flex justify-content-between align-items-center"
               role="button"
               data-bs-toggle="collapse"
               data-bs-target="#${collapseId}"
               aria-expanded="${isOk ? 'false' : 'true'}"
               style="cursor:pointer;">
            <span class="fw-semibold">${MC._escHtml(check.label)}</span>
            <span class="badge ${badgeCls}">${badgeText}</span>
          </div>
          <div class="collapse${isOk ? '' : ' show'}" id="${collapseId}">
            <div class="card-body">
              ${bodyContent}
            </div>
          </div>
        </div>`;
    }).join('');

    resultsEl.innerHTML = cards;
  },

  async runCompleteness() {
    const loadingEl = document.getElementById('completenessLoading');
    const emptyEl = document.getElementById('completenessEmpty');
    const tableWrap = document.getElementById('completenessTableWrap');
    const summaryEl = document.getElementById('completenessSummary');
    if (loadingEl) loadingEl.classList.remove('d-none');
    if (emptyEl) emptyEl.classList.add('d-none');
    if (tableWrap) tableWrap.classList.add('d-none');
    if (summaryEl) summaryEl.classList.add('d-none');
    try {
      const data = await MC.api('/validation/completeness/run');
      this.renderCompleteness(data || []);
    } catch (err) {
      MC.showToast(`Field completeness check failed: ${err.message}`, 'danger');
      if (emptyEl) {
        emptyEl.textContent = `Check failed: ${err.message}`;
        emptyEl.classList.remove('d-none');
      }
    } finally {
      if (loadingEl) loadingEl.classList.add('d-none');
    }
  },

  renderCompleteness(rows) {
    const tbody = document.getElementById('completenessBody');
    const tableWrap = document.getElementById('completenessTableWrap');
    const emptyEl = document.getElementById('completenessEmpty');
    const summaryEl = document.getElementById('completenessSummary');
    if (!tbody) return;

    if (!rows || rows.length === 0) {
      if (emptyEl) {
        emptyEl.textContent = 'No completeness data returned.';
        emptyEl.classList.remove('d-none');
      }
      return;
    }

    // Sort: red first, then amber, then green, then error
    const order = { red: 0, amber: 1, green: 2, error: 3 };
    const sorted = [...rows].sort((a, b) => (order[a.status] ?? 99) - (order[b.status] ?? 99));

    // Summary counts
    const nGreen = rows.filter(r => r.status === 'green').length;
    const nAmber = rows.filter(r => r.status === 'amber').length;
    const nRed = rows.filter(r => r.status === 'red').length;
    const summaryGreen = document.getElementById('summaryGreen');
    const summaryAmber = document.getElementById('summaryAmber');
    const summaryRed = document.getElementById('summaryRed');
    if (summaryGreen) summaryGreen.textContent = `${nGreen} green`;
    if (summaryAmber) summaryAmber.textContent = `${nAmber} amber`;
    if (summaryRed) summaryRed.textContent = `${nRed} red`;
    if (summaryEl) summaryEl.classList.remove('d-none');

    tbody.innerHTML = sorted.map(row => {
      const pct = parseFloat(row.pct) || 0;
      const barCls =
        row.status === 'green' ? 'bg-success' :
        row.status === 'amber' ? 'bg-warning' :
        row.status === 'error' ? 'bg-secondary' : 'bg-danger';
      const badgeCls =
        row.status === 'green' ? 'badge-green' :
        row.status === 'amber' ? 'badge-amber' :
        row.status === 'error' ? 'badge-navy' : 'badge-red';
      const totalFmt = (row.total || 0).toLocaleString();
      const populatedFmt = (row.populated || 0).toLocaleString();
      const missingFmt = (row.missing || 0).toLocaleString();
      const progressCell = row.status === 'error'
        ? `<span class="text-muted small" title="${MC._escHtml(row.error || '')}">error</span>`
        : `<div class="d-flex align-items-center gap-2">
            <div class="progress flex-grow-1" style="height:10px;" title="${pct.toFixed(2)}%">
              <div class="progress-bar ${barCls}"
                   role="progressbar"
                   style="width:${Math.min(pct, 100)}%"
                   aria-valuenow="${pct}"
                   aria-valuemin="0"
                   aria-valuemax="100"></div>
            </div>
            <span class="small fw-semibold" style="min-width:48px;">${pct.toFixed(1)}%</span>
          </div>`;
      return `<tr>
        <td class="small font-monospace">${MC._escHtml(row.object)}</td>
        <td class="small font-monospace">${MC._escHtml(row.field)}</td>
        <td class="small">${MC._escHtml(row.label)}</td>
        <td class="text-end small">${totalFmt}</td>
        <td class="text-end small">${populatedFmt}</td>
        <td class="text-end small">${missingFmt}</td>
        <td>${progressCell}</td>
        <td><span class="badge ${badgeCls}">${MC._escHtml((row.status || '').toUpperCase())}</span></td>
      </tr>`;
    }).join('');

    if (tableWrap) tableWrap.classList.remove('d-none');
    if (emptyEl) emptyEl.classList.add('d-none');
  },
};
