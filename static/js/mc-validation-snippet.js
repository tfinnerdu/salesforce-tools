'use strict';

MC.validation = {
  init() {
    document.getElementById('btnRunCompleteness')?.addEventListener('click', () => {
      this.runCompleteness();
    });
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
