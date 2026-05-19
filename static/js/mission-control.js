'use strict';
const MC = {};

// ── Core utilities ────────────────────────────────────────────────────────────

MC.activeOrg = () =>
  document.querySelector('meta[name="active-org"]')?.content || 'dev';

/**
 * Fetch wrapper. Returns parsed JSON.
 * Throws an Error with the server's error message on non-ok or success:false.
 */
MC.api = async (path, method = 'GET', body = null) => {
  const opts = {
    method,
    headers: { 'Content-Type': 'application/json' },
  };
  if (body !== null) {
    opts.body = JSON.stringify(body);
  }
  const res = await fetch(path, opts);
  let data;
  try {
    data = await res.json();
  } catch (_) {
    if (!res.ok) throw new Error(`HTTP ${res.status} ${res.statusText}`);
    return null;
  }
  if (!res.ok) {
    throw new Error(data?.error || data?.message || `HTTP ${res.status}`);
  }
  if (data && data.success === false) {
    throw new Error(data.error || data.message || 'Request failed');
  }
  // Unwrap the standard {success, data} envelope used by most routes.
  if (data !== null && typeof data === 'object' && 'success' in data && 'data' in data) {
    return data.data;
  }
  return data;
};

/** Bootstrap toast, auto-dismissed after 4 s. type: 'success' | 'danger' | 'warning' | 'info' */
MC.showToast = (message, type = 'success') => {
  const container = document.getElementById('mcToastContainer');
  if (!container) return;
  const id = `toast-${Date.now()}`;
  const bgMap = { success: 'text-bg-success', danger: 'text-bg-danger', warning: 'text-bg-warning', info: 'text-bg-info' };
  const bg = bgMap[type] || 'text-bg-secondary';
  const html = `
    <div id="${id}" class="toast align-items-center ${bg} border-0" role="alert"
         aria-live="assertive" aria-atomic="true" data-bs-delay="4000">
      <div class="d-flex">
        <div class="toast-body">${MC._escHtml(message)}</div>
        <button type="button" class="btn-close btn-close-white me-2 m-auto"
                data-bs-dismiss="toast" aria-label="Close"></button>
      </div>
    </div>`;
  container.insertAdjacentHTML('beforeend', html);
  const el = document.getElementById(id);
  if (typeof bootstrap === 'undefined' || !el) return;
  const t = new bootstrap.Toast(el);
  t.show();
  el.addEventListener('hidden.bs.toast', () => el.remove());
};

MC.showSpinner = () =>
  document.getElementById('mcSpinnerOverlay')?.classList.remove('d-none');

MC.hideSpinner = () =>
  document.getElementById('mcSpinnerOverlay')?.classList.add('d-none');

/** Convert an HTML table to CSV and trigger a download. */
MC.exportTableCSV = (tableId, filename = 'export.csv') => {
  const table = document.getElementById(tableId);
  if (!table) return;
  const rows = Array.from(table.querySelectorAll('tr'));
  const csv = rows.map(row =>
    Array.from(row.querySelectorAll('th, td'))
      .map(cell => {
        const text = cell.innerText.replace(/"/g, '""');
        return `"${text}"`;
      })
      .join(',')
  ).join('\r\n');
  const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
};

MC.copyToClipboard = (text) => {
  navigator.clipboard.writeText(text)
    .then(() => MC.showToast('Copied to clipboard', 'success'))
    .catch(() => MC.showToast('Copy failed', 'danger'));
};

/** Returns a <span class="badge …"> string. */
MC.statusBadge = (status) => {
  const s = (status || '').toString().toLowerCase();
  const cls =
    s === 'success' || s === 'ok' || s === 'green' || s === 'pass' || s === 'passed' ? 'badge-green' :
    s === 'warning' || s === 'warn' || s === 'amber' || s === 'partial' ? 'badge-amber' :
    s === 'error' || s === 'fail' || s === 'failed' || s === 'red' ? 'badge-red' :
    'badge-navy';
  return `<span class="badge ${cls}">${MC._escHtml(status?.toString().toUpperCase() || '')}</span>`;
};

/** Returns a % badge colored by threshold. */
MC.pctBadge = (pct) => {
  const n = parseFloat(pct) || 0;
  const cls = n >= 100 ? 'badge-green' : n >= 90 ? 'badge-amber' : 'badge-red';
  return `<span class="badge ${cls}">${n.toFixed(1)}%</span>`;
};

/** Escape HTML for safe insertion. */
MC._escHtml = (s) => {
  if (s == null) return '';
  return String(s)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
};

/** Format an ISO timestamp to a locale string. */
MC._fmtTime = (ts) => {
  if (!ts) return 'Never';
  try { return new Date(ts).toLocaleString(); } catch (_) { return ts; }
};


// ── Readiness ─────────────────────────────────────────────────────────────────

MC.readiness = {
  init() {
    this.load();
    document.getElementById('btnRunReadiness')?.addEventListener('click', () => this.run());
  },

  async load() {
    try {
      const data = await MC.api('/migration/readiness/history');
      const history = Array.isArray(data) ? data : (data && data.results) || [];
      if (!history || history.length === 0) return;
      const latest = history[0];
      // DB row: {id, org, run_at, results: <JSONB run dict>, overall_pct}
      const runResult = (latest.results && typeof latest.results === 'object') ? latest.results : latest;
      const tsEl = document.getElementById('lastRunTime');
      if (tsEl) tsEl.textContent = MC._fmtTime(runResult.timestamp || latest.run_at);
      this.renderScorecard(runResult.checks || []);
      const pct = latest.overall_pct ?? runResult.overall_pct ?? runResult.overall_score ?? 0;
      this.renderOverallBanner(pct, runResult.status || (pct >= 90 ? 'PASS' : pct >= 70 ? 'WARN' : 'FAIL'));
    } catch (err) {
      // No history yet — stay in empty state
    }
  },

  async run() {
    MC.showSpinner();
    const loadingEl = document.getElementById('scorecardLoading');
    const emptyEl = document.getElementById('scorecardEmpty');
    const tableEl = document.getElementById('scorecardTable');
    if (loadingEl) { loadingEl.classList.remove('d-none'); }
    if (emptyEl) { emptyEl.classList.add('d-none'); }
    if (tableEl) { tableEl.classList.add('d-none'); }
    try {
      const data = await MC.api('/migration/readiness/run', 'POST');
      const tsEl = document.getElementById('lastRunTime');
      if (tsEl) tsEl.textContent = MC._fmtTime(data.timestamp || new Date().toISOString());
      this.renderScorecard(data.checks || []);
      const pct = data.overall_pct ?? data.overall_score ?? 0;
      this.renderOverallBanner(pct, data.status || (pct >= 90 ? 'PASS' : pct >= 70 ? 'WARN' : 'FAIL'));
      MC.showToast('Readiness check complete', 'success');
    } catch (err) {
      MC.showToast(`Readiness check failed: ${err.message}`, 'danger');
    } finally {
      MC.hideSpinner();
      if (loadingEl) loadingEl.classList.add('d-none');
    }
  },

  renderScorecard(checks) {
    const tbody = document.getElementById('scorecardBody');
    const tableEl = document.getElementById('scorecardTable');
    const emptyEl = document.getElementById('scorecardEmpty');
    if (!tbody) return;
    if (!checks || checks.length === 0) {
      if (emptyEl) emptyEl.classList.remove('d-none');
      if (tableEl) tableEl.classList.add('d-none');
      return;
    }
    tbody.innerHTML = checks.map(c => {
      const scoreVal = c.score != null ? `${c.score}%` : '—';
      const statusClass =
        (c.status || '').toLowerCase() === 'pass' || (c.score >= 90) ? 'status-green' :
        (c.status || '').toLowerCase() === 'warn' || (c.score >= 70) ? 'status-amber' :
        'status-red';
      return `<tr class="${statusClass}">
        <td>${MC._escHtml(c.check || c.name || '—')}</td>
        <td><strong>${MC._escHtml(scoreVal)}</strong></td>
        <td class="text-muted small">${MC._escHtml(c.detail || c.message || '')}</td>
      </tr>`;
    }).join('');
    if (tableEl) tableEl.classList.remove('d-none');
    if (emptyEl) emptyEl.classList.add('d-none');
  },

  renderOverallBanner(pct, status) {
    const banner = document.getElementById('overallBanner');
    const text = document.getElementById('bannerText');
    if (!banner) return;
    banner.classList.remove('d-none', 'banner-green', 'banner-amber', 'banner-red');
    const n = parseFloat(pct) || 0;
    const cls = n >= 90 ? 'banner-green' : n >= 70 ? 'banner-amber' : 'banner-red';
    banner.classList.add(cls);
    if (text) text.textContent = `${n.toFixed(1)}% — ${(status || '').toUpperCase()}`;
  },
};


// ── Batch Tracker ─────────────────────────────────────────────────────────────

MC.batch = {
  _timer: null,

  init() {
    document.getElementById('btnLoadStatus')?.addEventListener('click', () => this.load());
    const toggle = document.getElementById('autoRefresh');
    if (toggle) {
      toggle.addEventListener('change', (e) => {
        if (e.target.checked) {
          this.startAutoRefresh();
        } else {
          this.stopAutoRefresh();
        }
      });
    }
    document.getElementById('btnRerunAll')?.addEventListener('click', () => {
      // Collect all SIS IDs from failure table
      const ids = Array.from(document.querySelectorAll('[data-sis-ids]'))
        .flatMap(el => {
          try { return JSON.parse(el.dataset.sisIds); } catch (_) { return []; }
        });
      this.rerun(ids);
    });
    document.getElementById('btnExportFailures')?.addEventListener('click', () => {
      MC.exportTableCSV('failureTableBody', 'batch_failures.csv');
    });
  },

  async load() {
    const wfName = document.getElementById('wfName')?.value?.trim();
    const startTime = document.getElementById('wfStartTime')?.value;
    if (!wfName) {
      MC.showToast('Please enter a workflow name', 'warning');
      return;
    }
    MC.showSpinner();
    try {
      const params = new URLSearchParams({ workflow_name: wfName });
      if (startTime) params.set('start_time_ms', startTime);
      const data = await MC.api(`/migration/batch/status?${params.toString()}`);
      this.renderProgress(data.status || data);
      if (data.failures && data.failures.length > 0) {
        this.renderFailures(data.failures);
      }
    } catch (err) {
      MC.showToast(`Failed to load batch status: ${err.message}`, 'danger');
    } finally {
      MC.hideSpinner();
    }
  },

  startAutoRefresh() {
    this.stopAutoRefresh();
    this._timer = setInterval(() => this.load(), 15000);
  },

  stopAutoRefresh() {
    if (this._timer) {
      clearInterval(this._timer);
      this._timer = null;
    }
  },

  renderProgress(data) {
    const section = document.getElementById('progressSection');
    if (section) section.classList.remove('d-none');

    const completed = data.completed ?? 0;
    const failed = data.failed ?? 0;
    const running = data.running ?? 0;
    const queued = data.queued ?? 0;
    const total = completed + failed + running + queued;
    const pct = total > 0 ? Math.round(((completed + failed) / total) * 100) : 0;

    const bar = document.getElementById('progressBar');
    const pctEl = document.getElementById('progressPct');
    if (bar) {
      bar.style.width = `${pct}%`;
      bar.setAttribute('aria-valuenow', pct);
      // Colour the bar based on failure rate
      bar.classList.remove('bg-warning', 'bg-success', 'bg-danger');
      const failRate = total > 0 ? failed / total : 0;
      bar.classList.add(failRate > 0.1 ? 'bg-danger' : pct === 100 ? 'bg-success' : 'bg-warning');
    }
    if (pctEl) pctEl.textContent = `${pct}%`;

    const set = (id, val) => {
      const el = document.getElementById(id);
      if (el) el.textContent = val != null ? val.toLocaleString() : '—';
    };
    set('metricCompleted', completed);
    set('metricFailed', failed);
    set('metricRunning', running);
    set('metricQueued', queued);

    const etaEl = document.getElementById('etaText');
    if (etaEl) {
      const eta = data.eta_minutes != null ? `${data.eta_minutes} min` : '—';
      const rate = data.rate_per_min != null ? `${data.rate_per_min}/min` : '—';
      etaEl.textContent = `ETA: ${eta} | Rate: ${rate}`;
    }
  },

  renderFailures(failures) {
    const wrap = document.getElementById('failureTable');
    const tbody = document.getElementById('failureTbody');
    if (!tbody) return;
    tbody.innerHTML = failures.map(f => {
      const sisIds = f.sample_sis_ids || f.sis_ids || [];
      const sisJson = JSON.stringify(sisIds);
      const sample = sisIds.slice(0, 3).map(MC._escHtml).join(', ');
      const more = sisIds.length > 3 ? ` <span class="text-muted">+${sisIds.length - 3} more</span>` : '';
      return `<tr data-sis-ids='${MC._escHtml(sisJson)}'>
        <td>${MC._escHtml(f.error_type || f.type || '—')}</td>
        <td><strong>${(f.count || 0).toLocaleString()}</strong></td>
        <td class="font-monospace small">${sample}${more}</td>
        <td class="no-print">
          <button class="btn btn-sm btn-outline-warning"
                  onclick='MC.batch.rerun(${JSON.stringify(sisIds)})'>
            Re-run
          </button>
        </td>
      </tr>`;
    }).join('');
    if (wrap) wrap.classList.remove('d-none');
  },

  async rerun(workflowIds) {
    if (!workflowIds || workflowIds.length === 0) {
      MC.showToast('No IDs to re-run', 'warning');
      return;
    }
    MC.showSpinner();
    try {
      const data = await MC.api('/migration/batch/rerun', 'POST', { ids: workflowIds });
      MC.showToast(`Re-queued ${data.queued ?? workflowIds.length} records`, 'success');
      setTimeout(() => this.load(), 2000);
    } catch (err) {
      MC.showToast(`Re-run failed: ${err.message}`, 'danger');
    } finally {
      MC.hideSpinner();
    }
  },
};


// ── Error Reconciler ──────────────────────────────────────────────────────────

MC.reconciler = {
  _categories: [],

  init() {
    document.getElementById('btnRefreshReconciler')?.addEventListener('click', () => this.load());
    this.load();
  },

  async load() {
    const wfName = document.getElementById('wfName')?.value?.trim() || 'EDA_Person_Sync';
    const hoursBack = document.getElementById('hoursBack')?.value || '6';
    const loadingEl = document.getElementById('errorCardsLoading');
    const emptyEl = document.getElementById('errorCardsEmpty');
    const cardsEl = document.getElementById('errorCards');
    const summaryEl = document.getElementById('errorSummary');

    if (loadingEl) { loadingEl.classList.remove('d-none'); }
    if (emptyEl) { emptyEl.classList.add('d-none'); }
    if (cardsEl) { cardsEl.innerHTML = ''; }
    if (summaryEl) { summaryEl.classList.add('d-none'); }

    try {
      const params = new URLSearchParams({ workflow_name: wfName, hours_back: hoursBack });
      const data = await MC.api(`/migration/reconciler/errors?${params.toString()}`);
      this._categories = data.categories || data || [];
      if (this._categories.length === 0) {
        if (emptyEl) {
          emptyEl.textContent = 'No errors found for this workflow in the selected time range.';
          emptyEl.classList.remove('d-none');
        }
      } else {
        this.renderErrors(this._categories);
        if (summaryEl) {
          const total = this._categories.reduce((s, c) => s + (c.count || 0), 0);
          summaryEl.textContent = `${total.toLocaleString()} failure${total !== 1 ? 's' : ''} across ${this._categories.length} error type${this._categories.length !== 1 ? 's' : ''}`;
          summaryEl.classList.remove('d-none');
        }
      }
    } catch (err) {
      if (emptyEl) {
        emptyEl.textContent = `Failed to load errors: ${err.message}`;
        emptyEl.classList.remove('d-none');
      }
      MC.showToast(`Failed to load reconciler data: ${err.message}`, 'danger');
    } finally {
      if (loadingEl) loadingEl.classList.add('d-none');
    }
  },

  renderErrors(categories) {
    const container = document.getElementById('errorCards');
    if (!container) return;
    container.innerHTML = categories.map(cat => this.buildCard(cat)).join('');
  },

  buildCard(cat) {
    const code = cat.error_code || cat.code || cat.type || 'UNKNOWN';
    const count = (cat.count || 0).toLocaleString();
    const cause = MC._escHtml(cat.cause || cat.description || 'No cause description available.');
    const fix = MC._escHtml(cat.suggested_fix || cat.fix || 'Review the affected records manually.');
    const severity = (cat.severity || 'medium').toLowerCase();
    const sisIds = cat.sis_ids || cat.sample_sis_ids || [];
    const sisHtml = sisIds.length > 0
      ? sisIds.map(id => `<div>${MC._escHtml(String(id))}</div>`).join('')
      : '<div class="text-muted">No sample IDs available.</div>';
    const escapedCode = MC._escHtml(code);
    const jsonCode = JSON.stringify(code);

    return `<div class="error-card severity-${severity}">
      <div class="card-body">
        <div class="error-card-header">
          <div class="d-flex align-items-center gap-2">
            <span class="fw-bold font-monospace">${escapedCode}</span>
            <span class="badge badge-red">${count}</span>
            ${severity === 'high'
              ? '<span class="badge badge-red">HIGH</span>'
              : severity === 'medium'
              ? '<span class="badge badge-amber">MEDIUM</span>'
              : '<span class="badge badge-green">LOW</span>'}
          </div>
          <button class="btn btn-sm btn-outline-warning no-print"
                  onclick="MC.reconciler.rerunCategory(${jsonCode})">
            Re-run
          </button>
        </div>
        <div class="error-card-cause"><strong>Cause:</strong> ${cause}</div>
        <div class="error-card-fix"><strong>Suggested fix:</strong> ${fix}</div>
        ${sisIds.length > 0 ? `
        <div class="mt-2">
          <button class="btn btn-link btn-sm p-0 text-muted small"
                  onclick="MC.reconciler.toggleSisIds(${jsonCode}, this)">
            Show ${sisIds.length} SIS ID${sisIds.length !== 1 ? 's' : ''} &#9660;
          </button>
          <div id="sisids-${escapedCode}" class="error-sis-ids d-none">
            ${sisHtml}
          </div>
        </div>` : ''}
      </div>
    </div>`;
  },

  toggleSisIds(errorCode, btn) {
    const el = document.getElementById(`sisids-${errorCode}`);
    if (!el) return;
    const hidden = el.classList.toggle('d-none');
    if (btn) {
      const count = el.children.length;
      btn.innerHTML = hidden
        ? `Show ${count} SIS ID${count !== 1 ? 's' : ''} &#9660;`
        : `Hide SIS IDs &#9650;`;
    }
  },

  async rerunCategory(errorCode) {
    const cat = this._categories.find(
      c => (c.error_code || c.code || c.type) === errorCode
    );
    const sisIds = cat ? (cat.sis_ids || cat.sample_sis_ids || []) : [];
    MC.showSpinner();
    try {
      const data = await MC.api('/migration/reconciler/rerun', 'POST', {
        error_code: errorCode,
        sis_ids: sisIds,
      });
      MC.showToast(`Re-queued ${data.queued ?? sisIds.length} records for ${errorCode}`, 'success');
    } catch (err) {
      MC.showToast(`Re-run failed: ${err.message}`, 'danger');
    } finally {
      MC.hideSpinner();
    }
  },
};


// ── Duplicates ────────────────────────────────────────────────────────────────

MC.duplicates = {
  _mergeModal: null,

  init() {
    document.getElementById('btnScan')?.addEventListener('click', () => this.scan());

    const modalEl = document.getElementById('mergeModal');
    if (modalEl) {
      this._mergeModal = new bootstrap.Modal(modalEl);
    }

    const confirmCb = document.getElementById('mergeConfirm');
    const confirmBtn = document.getElementById('btnConfirmMerge');
    if (confirmCb && confirmBtn) {
      confirmCb.addEventListener('change', () => {
        confirmBtn.disabled = !confirmCb.checked;
      });
    }
    document.getElementById('btnConfirmMerge')?.addEventListener('click', () => this.merge());
  },

  async scan() {
    const loadingEl = document.getElementById('scanLoading');
    const emptyEl = document.getElementById('scanEmpty');
    const resultsEl = document.getElementById('scanResults');
    if (loadingEl) loadingEl.classList.remove('d-none');
    if (emptyEl) emptyEl.classList.add('d-none');
    if (resultsEl) resultsEl.classList.add('d-none');

    MC.showSpinner();
    try {
      const data = await MC.api('/validation/duplicates/scan', 'POST');
      const tsEl = document.getElementById('lastScanTime');
      if (tsEl) tsEl.textContent = MC._fmtTime(data.timestamp || new Date().toISOString());
      this.renderResults(data);
    } catch (err) {
      MC.showToast(`Scan failed: ${err.message}`, 'danger');
      if (emptyEl) {
        emptyEl.textContent = `Scan failed: ${err.message}`;
        emptyEl.classList.remove('d-none');
      }
    } finally {
      MC.hideSpinner();
      if (loadingEl) loadingEl.classList.add('d-none');
    }
  },

  renderResults(data) {
    const tbody = document.getElementById('resultsTable');
    const resultsEl = document.getElementById('scanResults');
    const emptyEl = document.getElementById('scanEmpty');
    if (!tbody) return;
    const strategies = data.strategies || data || [];
    if (strategies.length === 0) {
      if (emptyEl) {
        emptyEl.textContent = 'No duplicates detected.';
        emptyEl.classList.remove('d-none');
      }
      if (resultsEl) resultsEl.classList.add('d-none');
      return;
    }
    tbody.innerHTML = strategies.map(s => {
      const sampleIds = (s.sample_ids || []).slice(0, 4);
      const sampleHtml = sampleIds.map(id => `<code class="small">${MC._escHtml(String(id))}</code>`).join(' ');
      const masterId = sampleIds[0] || '';
      const victimId = sampleIds[1] || '';
      return `<tr>
        <td>${MC._escHtml(s.strategy || s.name || '—')}</td>
        <td><strong>${(s.count || s.duplicates_found || 0).toLocaleString()}</strong></td>
        <td>${sampleHtml}</td>
        <td>${MC.statusBadge(s.status || (s.count > 0 ? 'warn' : 'pass'))}</td>
        <td class="no-print">
          <button class="btn btn-sm btn-outline-secondary me-1"
                  onclick="MC.duplicates.openMergeModal('${MC._escHtml(masterId)}','${MC._escHtml(victimId)}')">
            Merge
          </button>
        </td>
      </tr>`;
    }).join('');
    if (resultsEl) resultsEl.classList.remove('d-none');
    if (emptyEl) emptyEl.classList.add('d-none');
  },

  openMergeModal(masterId, victimId) {
    const masterInput = document.getElementById('mergeIdMaster');
    const victimInput = document.getElementById('mergeIdVictim');
    const confirmCb = document.getElementById('mergeConfirm');
    const confirmBtn = document.getElementById('btnConfirmMerge');
    if (masterInput) masterInput.value = masterId;
    if (victimInput) victimInput.value = victimId;
    if (confirmCb) confirmCb.checked = false;
    if (confirmBtn) confirmBtn.disabled = true;
    if (this._mergeModal) this._mergeModal.show();
  },

  async merge() {
    const masterId = document.getElementById('mergeIdMaster')?.value?.trim();
    const victimId = document.getElementById('mergeIdVictim')?.value?.trim();
    if (!masterId || !victimId) {
      MC.showToast('Both master and victim IDs are required', 'warning');
      return;
    }
    MC.showSpinner();
    try {
      await MC.api('/validation/duplicates/merge', 'POST', { master_id: masterId, victim_id: victimId });
      MC.showToast(`Merged ${victimId} into ${masterId}`, 'success');
      if (this._mergeModal) this._mergeModal.hide();
      await this.scan();
    } catch (err) {
      MC.showToast(`Merge failed: ${err.message}`, 'danger');
    } finally {
      MC.hideSpinner();
    }
  },
};


// ── External IDs ──────────────────────────────────────────────────────────────

MC.externalIds = {
  init() {
    document.getElementById('btnRun')?.addEventListener('click', () => this.run());
    document.getElementById('btnCloseDrill')?.addEventListener('click', () => {
      document.getElementById('drillPanel')?.classList.add('d-none');
    });
    document.getElementById('btnExportDrill')?.addEventListener('click', () => {
      MC.exportTableCSV('drillTableBody', 'missing_external_ids.csv');
    });
  },

  async run() {
    const loadEl = document.getElementById('coverageLoading');
    const emptyEl = document.getElementById('coverageEmpty');
    const wrapEl = document.getElementById('coverageTableWrap');
    if (loadEl) loadEl.classList.remove('d-none');
    if (emptyEl) emptyEl.classList.add('d-none');
    if (wrapEl) wrapEl.classList.add('d-none');
    MC.showSpinner();
    try {
      const data = await MC.api('/validation/external-ids/run');
      this.renderTable(data.objects || data || []);
    } catch (err) {
      MC.showToast(`Report failed: ${err.message}`, 'danger');
      if (emptyEl) {
        emptyEl.textContent = `Failed: ${err.message}`;
        emptyEl.classList.remove('d-none');
      }
    } finally {
      MC.hideSpinner();
      if (loadEl) loadEl.classList.add('d-none');
    }
  },

  renderTable(objects) {
    const tbody = document.getElementById('coverageTable');
    const wrapEl = document.getElementById('coverageTableWrap');
    const emptyEl = document.getElementById('coverageEmpty');
    if (!tbody) return;
    if (!objects || objects.length === 0) {
      if (emptyEl) {
        emptyEl.textContent = 'No objects found.';
        emptyEl.classList.remove('d-none');
      }
      return;
    }

    tbody.innerHTML = objects.map(obj => {
      const sisPct = obj.sis_id_pct ?? obj.sis_coverage ?? 0;
      const ethosPct = obj.ethos_guid_pct ?? obj.ethos_coverage ?? 0;
      const sisBar = this._coverageBarHtml(sisPct);
      const ethosBar = this._coverageBarHtml(ethosPct);
      return `<tr style="cursor:pointer"
               onclick="MC.externalIds.drillDown('${MC._escHtml(obj.object || obj.name)}','SIS_ID__c')">
        <td><strong>${MC._escHtml(obj.object || obj.name || '—')}</strong></td>
        <td>${(obj.total || 0).toLocaleString()}</td>
        <td>${sisBar}</td>
        <td>${ethosBar}</td>
      </tr>`;
    }).join('');
    if (wrapEl) wrapEl.classList.remove('d-none');
    if (emptyEl) emptyEl.classList.add('d-none');
  },

  _coverageBarHtml(pct) {
    const n = parseFloat(pct) || 0;
    const fill = n >= 100 ? 'fill-green' : n >= 90 ? 'fill-amber' : 'fill-red';
    const badge = MC.pctBadge(n);
    return `<div class="coverage-bar-wrap">
      <div class="coverage-bar"><div class="coverage-bar-fill ${fill}" style="width:${Math.min(n,100)}%"></div></div>
      ${badge}
    </div>`;
  },

  async drillDown(objectName, field) {
    const panel = document.getElementById('drillPanel');
    const titleEl = document.getElementById('drillPanelTitle');
    const summaryEl = document.getElementById('drillSummary');
    const tbody = document.getElementById('drillTableBody');
    if (!panel || !tbody) return;

    if (titleEl) titleEl.textContent = `Missing ${field} — ${objectName}`;
    panel.classList.remove('d-none');
    tbody.innerHTML = `<tr><td colspan="3" class="text-center py-3">
      <span class="spinner-border spinner-border-sm text-warning"></span> Loading…
    </td></tr>`;

    try {
      const params = new URLSearchParams({ object: objectName, field });
      const data = await MC.api(`/validation/external-ids/run?${params.toString()}&drill=1`);
      const records = data.missing || data.records || [];
      if (summaryEl) summaryEl.textContent = `${records.length.toLocaleString()} records missing ${field}`;
      tbody.innerHTML = records.length === 0
        ? '<tr><td colspan="3" class="text-center text-muted py-3">No missing records found.</td></tr>'
        : records.map(r => `<tr>
            <td class="font-monospace small">${MC._escHtml(r.Id || r.id || '—')}</td>
            <td>${MC._escHtml(r.Name || r.name || '—')}</td>
            <td class="text-muted small">${MC._escHtml(r.CreatedDate || r.created_date || '—')}</td>
          </tr>`).join('');
    } catch (err) {
      tbody.innerHTML = `<tr><td colspan="3" class="text-danger small">Failed: ${MC._escHtml(err.message)}</td></tr>`;
    }
  },
};


// ── ContactPoints ─────────────────────────────────────────────────────────────

MC.contactpoints = {
  init() {
    document.getElementById('btnScan')?.addEventListener('click', () => this.scan());
  },

  async scan() {
    const loadEl = document.getElementById('cpLoading');
    const emptyEl = document.getElementById('cpEmpty');
    const resultsEl = document.getElementById('cpResults');
    const bannerEl = document.getElementById('cpBanner');
    if (loadEl) loadEl.classList.remove('d-none');
    if (emptyEl) emptyEl.classList.add('d-none');
    if (resultsEl) resultsEl.classList.add('d-none');
    MC.showSpinner();
    try {
      const data = await MC.api('/validation/contactpoints/scan');
      this.renderCards(data);
    } catch (err) {
      MC.showToast(`Scan failed: ${err.message}`, 'danger');
      if (emptyEl) {
        emptyEl.textContent = `Scan failed: ${err.message}`;
        emptyEl.classList.remove('d-none');
      }
    } finally {
      MC.hideSpinner();
      if (loadEl) loadEl.classList.add('d-none');
    }
  },

  renderCards(data) {
    const resultsEl = document.getElementById('cpResults');
    const bannerEl = document.getElementById('cpBanner');
    const emptyEl = document.getElementById('cpEmpty');

    const types = ['email', 'phone', 'address'];
    let totalIssues = 0;

    types.forEach(t => {
      const key = `contact_point_${t}` in data ? `contact_point_${t}` : t;
      const info = data[key] || data[`ContactPoint${t.charAt(0).toUpperCase() + t.slice(1)}`] || {};
      const missingParent = info.missing_parent ?? info.missingParent ?? 0;
      const missingIndividual = info.missing_individual ?? info.missingIndividual ?? 0;
      const total = info.total ?? info.total_records ?? 0;
      totalIssues += missingParent + missingIndividual;

      const capT = t.charAt(0).toUpperCase() + t.slice(1);
      const setVal = (id, val) => {
        const el = document.getElementById(id);
        if (el) el.textContent = val.toLocaleString();
      };
      const setBadge = (id, val) => {
        const el = document.getElementById(id);
        if (!el) return;
        el.textContent = val.toLocaleString();
        el.className = `badge ${val > 0 ? 'badge-red' : 'badge-green'}`;
      };
      setBadge(`cp${capT}MissingParent`, missingParent);
      setBadge(`cp${capT}MissingIndividual`, missingIndividual);
      setVal(`cp${capT}Total`, total);

      // Sample IDs
      const sampleIds = info.sample_ids || info.samples || [];
      const samplesDiv = document.getElementById(`cp${capT}Samples`);
      const sampleList = document.getElementById(`cp${capT}SampleList`);
      if (sampleList && sampleIds.length > 0) {
        sampleList.innerHTML = sampleIds.map(id => `<div>${MC._escHtml(String(id))}</div>`).join('');
        if (samplesDiv) samplesDiv.classList.remove('d-none');
      }
    });

    if (resultsEl) resultsEl.classList.remove('d-none');
    if (emptyEl) emptyEl.classList.add('d-none');

    if (bannerEl) {
      const textEl = document.getElementById('cpBannerText');
      bannerEl.classList.remove('d-none', 'banner-green', 'banner-amber', 'banner-red');
      bannerEl.classList.add(totalIssues === 0 ? 'banner-green' : totalIssues < 10 ? 'banner-amber' : 'banner-red');
      if (textEl) textEl.textContent = `${totalIssues.toLocaleString()} issue${totalIssues !== 1 ? 's' : ''}`;
    }
  },

  toggleSamples(listId, btn) {
    const el = document.getElementById(listId);
    if (!el) return;
    const hidden = el.classList.toggle('d-none');
    if (btn) btn.innerHTML = hidden ? 'Show sample IDs &#9660;' : 'Hide sample IDs &#9650;';
  },
};


// ── SOQL Workbench ────────────────────────────────────────────────────────────

MC.soql = {
  _objects: [],
  _currentPage: 0,
  _allRows: [],
  _pageSize: 200,
  _currentObject: null,
  _selectedSavedId: null,

  init() {
    document.getElementById('btnRun')?.addEventListener('click', () => this.run(false));
    document.getElementById('btnRunAll')?.addEventListener('click', () => this.run(true));
    document.getElementById('btnExplain')?.addEventListener('click', () => this.explain());
    document.getElementById('btnExport')?.addEventListener('click', () => {
      MC.exportTableCSV('resultsTable', 'soql_results.csv');
    });
    document.getElementById('btnSave')?.addEventListener('click', () => this.saveQuery());

    const savedSelect = document.getElementById('savedQueriesSelect');
    if (savedSelect) {
      savedSelect.addEventListener('change', (e) => {
        const opt = e.target.selectedOptions[0];
        if (opt && opt.dataset.soql) {
          document.getElementById('soqlEditor').value = opt.dataset.soql;
          this._selectedSavedId = opt.value || null;
          const delBtn = document.getElementById('btnDeleteSaved');
          if (delBtn) delBtn.classList.toggle('d-none', !this._selectedSavedId);
        }
      });
    }
    document.getElementById('btnDeleteSaved')?.addEventListener('click', async () => {
      if (!this._selectedSavedId) return;
      if (!confirm('Delete this saved query?')) return;
      try {
        await MC.api(`/soql/saved/${this._selectedSavedId}`, 'DELETE');
        MC.showToast('Query deleted', 'success');
        this._selectedSavedId = null;
        await this.loadSavedQueries();
      } catch (err) {
        MC.showToast(`Delete failed: ${err.message}`, 'danger');
      }
    });

    const searchInput = document.getElementById('objectSearch');
    if (searchInput) {
      searchInput.addEventListener('input', (e) => {
        const q = e.target.value.toLowerCase();
        document.querySelectorAll('.object-explorer-item').forEach(item => {
          const match = item.dataset.name.toLowerCase().includes(q);
          item.style.display = match ? '' : 'none';
        });
      });
    }

    document.getElementById('btnInsertAllFields')?.addEventListener('click', () => {
      if (!this._currentObject) return;
      const items = document.querySelectorAll('.fields-list-item');
      const fieldNames = Array.from(items).map(i => i.dataset.name).filter(Boolean);
      if (fieldNames.length === 0) return;
      const editor = document.getElementById('soqlEditor');
      const existing = editor.value.trim();
      if (!existing || existing.toUpperCase().startsWith('SELECT')) {
        editor.value = `SELECT ${fieldNames.join(', ')}\nFROM ${this._currentObject}\nLIMIT 200`;
      } else {
        editor.value = existing;
      }
    });

    document.getElementById('btnPrevPage')?.addEventListener('click', () => {
      if (this._currentPage > 0) {
        this._currentPage--;
        this._renderPage();
      }
    });
    document.getElementById('btnNextPage')?.addEventListener('click', () => {
      const maxPage = Math.ceil(this._allRows.length / this._pageSize) - 1;
      if (this._currentPage < maxPage) {
        this._currentPage++;
        this._renderPage();
      }
    });

    this.loadObjects();
    this.loadSavedQueries();
  },

  async run(allPages = false) {
    const soql = document.getElementById('soqlEditor')?.value?.trim();
    if (!soql) {
      MC.showToast('Enter a SOQL query first', 'warning');
      return;
    }
    const emptyEl = document.getElementById('resultsEmpty');
    const contentEl = document.getElementById('resultsContent');
    if (emptyEl) emptyEl.classList.add('d-none');
    if (contentEl) contentEl.classList.add('d-none');
    MC.showSpinner();
    try {
      const data = await MC.api('/soql/run', 'POST', { soql, all_pages: allPages });
      this.renderResults(data.data || data);
    } catch (err) {
      MC.showToast(`Query failed: ${err.message}`, 'danger');
      if (emptyEl) {
        emptyEl.textContent = `Error: ${err.message}`;
        emptyEl.classList.remove('d-none');
      }
    } finally {
      MC.hideSpinner();
    }
  },

  renderResults(data) {
    const records = data.records || data || [];
    const countEl = document.getElementById('resultCount');
    const headEl = document.getElementById('resultsTableHead');
    const bodyEl = document.getElementById('resultsTableBody');
    const contentEl = document.getElementById('resultsContent');
    const emptyEl = document.getElementById('resultsEmpty');
    const explainEl = document.getElementById('explainResult');
    if (explainEl) explainEl.classList.add('d-none');

    if (!headEl || !bodyEl) return;

    if (!records || records.length === 0) {
      if (countEl) countEl.textContent = 'No records returned.';
      headEl.innerHTML = '';
      bodyEl.innerHTML = '';
      if (contentEl) contentEl.classList.remove('d-none');
      if (emptyEl) emptyEl.classList.add('d-none');
      return;
    }

    // Detect column names from first record, exclude 'attributes'
    const columns = Object.keys(records[0]).filter(k => k !== 'attributes');
    headEl.innerHTML = `<tr>${columns.map(c => `<th>${MC._escHtml(c)}</th>`).join('')}</tr>`;

    this._allRows = records;
    this._columns = columns;
    this._currentPage = 0;

    const total = data.totalSize ?? data.total_size ?? data.total ?? records.length;
    const allFetched = data.done !== false;
    if (countEl) {
      countEl.textContent = `${total.toLocaleString()} record${total !== 1 ? 's' : ''}${allFetched ? '' : ' (partial — use Run All Pages for complete set)'}`;
    }

    this._renderPage();
    if (contentEl) contentEl.classList.remove('d-none');
    if (emptyEl) emptyEl.classList.add('d-none');
  },

  _renderPage() {
    const bodyEl = document.getElementById('resultsTableBody');
    const paginationBar = document.getElementById('paginationBar');
    const pageInfoEl = document.getElementById('pageInfo');
    if (!bodyEl) return;

    const columns = this._columns || [];
    const start = this._currentPage * this._pageSize;
    const pageRows = this._allRows.slice(start, start + this._pageSize);
    const objectName = this._currentObject || '';
    const totalPages = Math.ceil(this._allRows.length / this._pageSize);

    bodyEl.innerHTML = pageRows.map(record => {
      const recordId = record.Id || record.id || '';
      const cells = columns.map(col => {
        const val = record[col];
        const display = val == null ? '' : (typeof val === 'object' ? JSON.stringify(val) : String(val));
        return `<td title="${MC._escHtml(display)}"
                    ondblclick="MC.soql.enableInlineEdit(this,'${MC._escHtml(objectName)}','${MC._escHtml(recordId)}','${MC._escHtml(col)}')"
                >${MC._escHtml(display)}</td>`;
      }).join('');
      return `<tr>${cells}</tr>`;
    }).join('');

    if (paginationBar) {
      if (totalPages > 1) {
        paginationBar.classList.remove('d-none');
        const prevBtn = document.getElementById('btnPrevPage');
        const nextBtn = document.getElementById('btnNextPage');
        if (prevBtn) prevBtn.disabled = this._currentPage === 0;
        if (nextBtn) nextBtn.disabled = this._currentPage >= totalPages - 1;
        if (pageInfoEl) pageInfoEl.textContent = `Page ${this._currentPage + 1} of ${totalPages}`;
      } else {
        paginationBar.classList.add('d-none');
      }
    }
  },

  async explain() {
    const soql = document.getElementById('soqlEditor')?.value?.trim();
    if (!soql) {
      MC.showToast('Enter a SOQL query first', 'warning');
      return;
    }
    MC.showSpinner();
    try {
      const data = await MC.api('/soql/run', 'POST', { soql, explain: true });
      const explainEl = document.getElementById('explainResult');
      const contentEl = document.getElementById('resultsContent');
      const emptyEl = document.getElementById('resultsEmpty');
      const headEl = document.getElementById('resultsTableHead');
      const bodyEl = document.getElementById('resultsTableBody');
      const inner = data.data || data;
      const plan = inner.plans?.[0] || inner.plan || inner;
      if (explainEl) {
        explainEl.textContent = JSON.stringify(plan, null, 2);
        explainEl.classList.remove('d-none');
      }
      if (headEl) headEl.innerHTML = '';
      if (bodyEl) bodyEl.innerHTML = '';
      if (contentEl) contentEl.classList.remove('d-none');
      if (emptyEl) emptyEl.classList.add('d-none');
    } catch (err) {
      MC.showToast(`Explain failed: ${err.message}`, 'danger');
    } finally {
      MC.hideSpinner();
    }
  },

  async loadObjects() {
    const listEl = document.getElementById('objectList');
    const loadingEl = document.getElementById('objectListLoading');
    if (loadingEl) loadingEl.classList.remove('d-none');
    try {
      const data = await MC.api('/soql/objects');
      this._objects = (data.sobjects || data || []).map(o =>
        typeof o === 'string' ? { name: o, label: o } : o
      );
      if (listEl) {
        listEl.innerHTML = this._objects.map(o =>
          `<div class="object-explorer-item" data-name="${MC._escHtml(o.name)}"
                onclick="MC.soql.loadFields('${MC._escHtml(o.name)}')"
                title="${MC._escHtml(o.label || o.name)}">
            ${MC._escHtml(o.label || o.name)}
          </div>`
        ).join('');
      }
    } catch (err) {
      if (listEl) listEl.innerHTML = `<p class="text-danger small px-2">Failed to load objects: ${MC._escHtml(err.message)}</p>`;
    } finally {
      if (loadingEl) loadingEl.classList.add('d-none');
    }
  },

  async loadFields(objectName) {
    this._currentObject = objectName;
    // Highlight selected item
    document.querySelectorAll('.object-explorer-item').forEach(el => {
      el.classList.toggle('selected', el.dataset.name === objectName);
    });
    const panelWrap = document.getElementById('fieldsPanelWrap');
    const fieldsEl = document.getElementById('fieldsList');
    const labelEl = document.getElementById('fieldsObjectLabel');
    if (panelWrap) panelWrap.classList.remove('d-none');
    if (labelEl) labelEl.textContent = objectName;
    if (fieldsEl) fieldsEl.innerHTML = `<div class="text-center py-2"><span class="spinner-border spinner-border-sm text-warning"></span></div>`;
    try {
      const data = await MC.api(`/soql/objects/${encodeURIComponent(objectName)}/fields`);
      const fields = data.fields || data || [];
      if (fieldsEl) {
        fieldsEl.innerHTML = fields.map(f => {
          const name = f.name || f;
          const type = f.type || '';
          return `<div class="fields-list-item" data-name="${MC._escHtml(name)}"
                       onclick="MC.soql._insertField('${MC._escHtml(name)}')">
            <span>${MC._escHtml(name)}</span>
            ${type ? `<span class="field-type-badge">${MC._escHtml(type)}</span>` : ''}
          </div>`;
        }).join('');
      }
    } catch (err) {
      if (fieldsEl) fieldsEl.innerHTML = `<p class="text-danger small px-2">Failed: ${MC._escHtml(err.message)}</p>`;
    }
  },

  _insertField(fieldName) {
    const editor = document.getElementById('soqlEditor');
    if (!editor) return;
    const q = editor.value;
    // Try to insert into SELECT clause
    const selectMatch = q.match(/^(SELECT\s+)(.*?)(\s+FROM\s+)/is);
    if (selectMatch) {
      const existing = selectMatch[2].split(',').map(s => s.trim());
      if (!existing.includes(fieldName)) {
        editor.value = `${selectMatch[1]}${[...existing, fieldName].join(', ')}${selectMatch[3]}${q.slice(selectMatch[0].length)}`;
      }
    } else {
      // Append at cursor
      const start = editor.selectionStart;
      editor.value = q.slice(0, start) + fieldName + q.slice(start);
    }
    editor.focus();
  },

  async saveQuery() {
    const soql = document.getElementById('soqlEditor')?.value?.trim();
    if (!soql) {
      MC.showToast('No query to save', 'warning');
      return;
    }
    const name = prompt('Enter a name for this query:');
    if (!name || !name.trim()) return;
    try {
      await MC.api('/soql/saved', 'POST', { name: name.trim(), soql });
      MC.showToast(`Query "${name.trim()}" saved`, 'success');
      await this.loadSavedQueries();
    } catch (err) {
      MC.showToast(`Save failed: ${err.message}`, 'danger');
    }
  },

  async loadSavedQueries() {
    const select = document.getElementById('savedQueriesSelect');
    if (!select) return;
    try {
      const data = await MC.api('/soql/saved');
      const queries = data.queries || data || [];
      const current = select.value;
      select.innerHTML = '<option value="">-- Saved queries --</option>' +
        queries.map(q =>
          `<option value="${MC._escHtml(String(q.id || ''))}"
                   data-soql="${MC._escHtml(q.soql || q.query || '')}"
                   ${String(q.id) === current ? 'selected' : ''}>
            ${MC._escHtml(q.name || q.label || 'Unnamed')}
          </option>`
        ).join('');
    } catch (_) {
      // Saved queries are optional — fail silently
    }
  },

  enableInlineEdit(td, objectName, recordId, fieldName) {
    if (!objectName || !recordId || !fieldName) return;
    if (td.querySelector('.inline-edit-input')) return; // already editing
    const originalText = td.innerText;
    const input = document.createElement('input');
    input.type = 'text';
    input.value = originalText;
    input.className = 'inline-edit-input';
    td.textContent = '';
    td.appendChild(input);
    input.focus();
    input.select();

    const cancel = () => {
      td.textContent = originalText;
    };
    const save = async () => {
      const newValue = input.value;
      if (newValue === originalText) { cancel(); return; }
      td.textContent = newValue;
      await this.commitEdit(objectName, recordId, fieldName, newValue);
    };

    input.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') { e.preventDefault(); save(); }
      if (e.key === 'Escape') { e.preventDefault(); cancel(); }
    });
    input.addEventListener('blur', () => save());
  },

  async commitEdit(objectName, recordId, fieldName, value) {
    try {
      await MC.api('/soql/update', 'POST', {
        object: objectName,
        id: recordId,
        field: fieldName,
        value,
      });
      MC.showToast(`Updated ${fieldName}`, 'success');
    } catch (err) {
      MC.showToast(`Update failed: ${err.message}`, 'danger');
    }
  },
};


// ── Crosswalk Diff ────────────────────────────────────────────────────────────

MC.crosswalk = {
  _mappings: [],
  _rowCount: 0,

  init() {
    // Upload area
    const uploadArea = document.getElementById('uploadArea');
    const fileInput = document.getElementById('csvFileInput');
    if (uploadArea) {
      uploadArea.addEventListener('click', (e) => {
        if (e.target !== document.getElementById('btnUploadCsv')) {
          fileInput?.click();
        }
      });
      uploadArea.addEventListener('dragover', (e) => {
        e.preventDefault();
        uploadArea.classList.add('drag-over');
      });
      uploadArea.addEventListener('dragleave', () => uploadArea.classList.remove('drag-over'));
      uploadArea.addEventListener('drop', (e) => {
        e.preventDefault();
        uploadArea.classList.remove('drag-over');
        const file = e.dataTransfer.files[0];
        if (file) this.uploadFile(file);
      });
    }
    document.getElementById('btnUploadCsv')?.addEventListener('click', (e) => {
      e.stopPropagation();
      fileInput?.click();
    });
    fileInput?.addEventListener('change', (e) => {
      const file = e.target.files[0];
      if (file) this.uploadFile(file);
    });

    document.getElementById('btnAddRow')?.addEventListener('click', () => this.addMappingRow());
    document.getElementById('btnRun')?.addEventListener('click', () => this.runCheck());
    document.getElementById('btnRunCheck')?.addEventListener('click', () => this.runCheck());
    document.getElementById('btnRunCheckFooter')?.addEventListener('click', () => this.runCheck());

    document.getElementById('btnCloseCwDrill')?.addEventListener('click', () => {
      document.getElementById('crosswalkDrillPanel')?.classList.add('d-none');
    });
  },

  async uploadFile(file) {
    const formData = new FormData();
    formData.append('file', file);
    MC.showSpinner();
    try {
      const res = await fetch('/schema/crosswalk/upload', { method: 'POST', body: formData });
      const data = await res.json();
      if (!res.ok || data.success === false) throw new Error(data.error || `HTTP ${res.status}`);
      const mappings = data.data || data.mappings || [];
      mappings.forEach(m => this.addMappingRow(m));
      this._showMappingTable();
      MC.showToast(`Imported ${mappings.length} mapping${mappings.length !== 1 ? 's' : ''}`, 'success');
    } catch (err) {
      MC.showToast(`Upload failed: ${err.message}`, 'danger');
    } finally {
      MC.hideSpinner();
    }
  },

  addMappingRow(mapping = {}) {
    const tbody = document.getElementById('mappingTableBody');
    if (!tbody) return;
    const id = ++this._rowCount;
    const row = document.createElement('tr');
    row.id = `map-row-${id}`;
    row.innerHTML = `
      <td><input type="text" class="form-control form-control-sm" placeholder="hed__Application__c"
                 value="${MC._escHtml(mapping.eda_object || '')}" data-field="eda_object"></td>
      <td><input type="text" class="form-control form-control-sm font-monospace" placeholder="hed__Applicant__c"
                 value="${MC._escHtml(mapping.eda_field || '')}" data-field="eda_field"></td>
      <td><input type="text" class="form-control form-control-sm" placeholder="Application__c"
                 value="${MC._escHtml(mapping.ec_object || '')}" data-field="ec_object"></td>
      <td><input type="text" class="form-control form-control-sm font-monospace" placeholder="Applicant__c"
                 value="${MC._escHtml(mapping.ec_field || '')}" data-field="ec_field"></td>
      <td><span class="badge badge-amber small" id="map-status-${id}">Pending</span></td>
      <td><button class="btn btn-sm btn-outline-danger" onclick="MC.crosswalk.deleteRow(${id})">&#10005;</button></td>
    `;
    tbody.appendChild(row);
    this._showMappingTable();
  },

  deleteRow(id) {
    document.getElementById(`map-row-${id}`)?.remove();
    const tbody = document.getElementById('mappingTableBody');
    if (tbody && tbody.children.length === 0) {
      document.getElementById('mappingTableWrap')?.classList.add('d-none');
    }
  },

  _showMappingTable() {
    document.getElementById('mappingTableWrap')?.classList.remove('d-none');
  },

  _collectMappings() {
    const rows = document.querySelectorAll('#mappingTableBody tr');
    return Array.from(rows).map(row => {
      const obj = {};
      row.querySelectorAll('input[data-field]').forEach(inp => {
        obj[inp.dataset.field] = inp.value.trim();
      });
      return obj;
    }).filter(m => m.eda_field && m.ec_field);
  },

  async runCheck() {
    const mappings = this._collectMappings();
    if (mappings.length === 0) {
      MC.showToast('Add at least one mapping row first', 'warning');
      return;
    }
    const resultsWrap = document.getElementById('crosswalkResultsWrap');
    const loadEl = document.getElementById('crosswalkLoading');
    if (resultsWrap) resultsWrap.classList.remove('d-none');
    if (loadEl) loadEl.classList.remove('d-none');
    MC.showSpinner();
    try {
      const data = await MC.api('/schema/crosswalk/run', 'POST', { mappings });
      this.renderResults(data.results || data || []);
    } catch (err) {
      MC.showToast(`Check failed: ${err.message}`, 'danger');
    } finally {
      MC.hideSpinner();
      if (loadEl) loadEl.classList.add('d-none');
    }
  },

  renderResults(results) {
    const tbody = document.getElementById('resultsTable');
    if (!tbody) return;
    tbody.innerHTML = results.map(r => {
      const edaCov = r.eda_coverage ?? r.eda_pct ?? 0;
      const ecCov = r.ec_coverage ?? r.ec_pct ?? 0;
      const gap = ecCov - edaCov;
      const gapCls = gap >= 0 ? 'gap-positive' : 'gap-negative';
      const gapStr = `${gap >= 0 ? '+' : ''}${gap.toFixed(1)}%`;
      const rowStatus = (r.status || r.row_status || '').toLowerCase();
      const rowCls =
        rowStatus === 'ok' || rowStatus === 'match' ? '' :
        rowStatus === 'left_only' || rowStatus === 'eda_only' ? 'diff-left-only' :
        rowStatus === 'right_only' || rowStatus === 'ec_only' ? 'diff-right-only' :
        rowStatus === 'mismatch' || rowStatus === 'gap' ? 'diff-mismatch' : '';
      return `<tr class="${rowCls}" style="cursor:pointer"
                  onclick="MC.crosswalk.showDrill(${JSON.stringify(r)})">
        <td class="font-monospace small">${MC._escHtml(r.eda_field || '—')}</td>
        <td class="font-monospace small">${MC._escHtml(r.ec_field || '—')}</td>
        <td>${MC.pctBadge(edaCov)}</td>
        <td>${MC.pctBadge(ecCov)}</td>
        <td class="${gapCls} fw-semibold">${gapStr}</td>
        <td class="small">${MC._escHtml(r.direction || '—')}</td>
        <td>${MC.statusBadge(r.status || r.row_status || 'ok')}</td>
      </tr>`;
    }).join('');
  },

  showDrill(r) {
    const panel = document.getElementById('crosswalkDrillPanel');
    const title = document.getElementById('cwDrillTitle');
    const content = document.getElementById('cwDrillContent');
    if (!panel) return;
    if (title) title.textContent = `Detail: ${r.eda_field} → ${r.ec_field}`;
    const records = r.sample_ids || r.missing_ids || r.records || [];
    if (content) {
      if (records.length === 0) {
        content.innerHTML = '<span class="text-muted">No record-level detail available.</span>';
      } else {
        content.innerHTML = records.map(id => `<div>${MC._escHtml(String(id))}</div>`).join('');
      }
    }
    panel.classList.remove('d-none');
    panel.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  },
};


// ── Org Diff ──────────────────────────────────────────────────────────────────

MC.orgDiff = {
  init() {
    document.getElementById('btnRunDiff')?.addEventListener('click', () => this.run());
  },

  async run() {
    const rightOrg = document.getElementById('rightOrgSelect')?.value;
    const objectsRaw = document.getElementById('objectMultiSelect')?.value?.trim();
    const objects = objectsRaw ? objectsRaw.split(',').map(s => s.trim()).filter(Boolean) : [];

    const diffEmpty = document.getElementById('diffEmpty');
    const diffLoading = document.getElementById('diffLoading');
    const accordion = document.getElementById('diffAccordion');
    const legend = document.getElementById('diffLegend');

    if (diffEmpty) diffEmpty.classList.add('d-none');
    if (diffLoading) diffLoading.classList.remove('d-none');
    if (accordion) accordion.innerHTML = '';
    if (legend) legend.classList.add('d-none');
    MC.showSpinner();
    try {
      const data = await MC.api('/schema/org-diff/run', 'POST', { right_org: rightOrg, objects });
      this.renderResults(data.objects || data.diff || data || {});
      if (legend) legend.classList.remove('d-none');
    } catch (err) {
      MC.showToast(`Diff failed: ${err.message}`, 'danger');
      if (diffEmpty) {
        diffEmpty.textContent = `Diff failed: ${err.message}`;
        diffEmpty.classList.remove('d-none');
      }
    } finally {
      MC.hideSpinner();
      if (diffLoading) diffLoading.classList.add('d-none');
    }
  },

  renderResults(diff) {
    const accordion = document.getElementById('diffAccordion');
    if (!accordion) return;
    const objectNames = Object.keys(diff);
    if (objectNames.length === 0) {
      const diffEmpty = document.getElementById('diffEmpty');
      if (diffEmpty) {
        diffEmpty.textContent = 'No differences found between orgs.';
        diffEmpty.classList.remove('d-none');
      }
      return;
    }
    accordion.innerHTML = objectNames.map((name, i) =>
      this.buildObjectPanel(name, diff[name], i)
    ).join('');
  },

  buildObjectPanel(objName, diff, idx) {
    const id = `diffObj${idx}`;
    const leftOnly = diff.left_only || [];
    const rightOnly = diff.right_only || [];
    const typeMismatches = diff.type_mismatches || [];
    const requiredMismatches = diff.required_mismatches || [];
    const picklistMismatches = diff.picklist_mismatches || [];
    const totalIssues = leftOnly.length + rightOnly.length + typeMismatches.length + requiredMismatches.length + picklistMismatches.length;
    const leftCount = diff.left_field_count ?? diff.left_count ?? '?';
    const rightCount = diff.right_field_count ?? diff.right_count ?? '?';

    const sectionHtml = (title, items, rowClass) => {
      if (!items || items.length === 0) return '';
      return `<div class="diff-section-title">${MC._escHtml(title)}</div>
        <table class="table table-sm mb-2">
          <tbody>
            ${items.map(item => {
              const name = item.field || item.name || (typeof item === 'string' ? item : JSON.stringify(item));
              const detail = item.left && item.right
                ? ` <span class="text-muted small">(left: ${MC._escHtml(String(item.left))}, right: ${MC._escHtml(String(item.right))})</span>`
                : '';
              return `<tr class="${rowClass}"><td class="font-monospace small py-1">${MC._escHtml(name)}${detail}</td></tr>`;
            }).join('')}
          </tbody>
        </table>`;
    };

    return `
      <div class="accordion-item">
        <h2 class="accordion-header" id="h-${id}">
          <button class="accordion-button ${totalIssues === 0 ? 'collapsed' : ''} d-flex justify-content-between align-items-center"
                  type="button" data-bs-toggle="collapse" data-bs-target="#c-${id}"
                  aria-expanded="${totalIssues > 0}" aria-controls="c-${id}">
            <span class="font-monospace fw-bold">${MC._escHtml(objName)}</span>
            <span class="d-flex gap-2 ms-auto me-3 small">
              <span class="text-muted">L: ${leftCount} fields</span>
              <span class="text-muted">R: ${rightCount} fields</span>
              ${totalIssues > 0 ? `<span class="badge badge-red">${totalIssues} diff${totalIssues !== 1 ? 's' : ''}</span>` : '<span class="badge badge-green">Match</span>'}
            </span>
          </button>
        </h2>
        <div id="c-${id}" class="accordion-collapse collapse ${totalIssues > 0 ? 'show' : ''}"
             aria-labelledby="h-${id}" data-bs-parent="#diffAccordion">
          <div class="accordion-body">
            ${sectionHtml('Left-only fields (in active org, not in right org)', leftOnly, 'diff-left-only')}
            ${sectionHtml('Right-only fields (in right org, not in active org)', rightOnly, 'diff-right-only')}
            ${sectionHtml('Type mismatches', typeMismatches, 'diff-mismatch')}
            ${sectionHtml('Required mismatches', requiredMismatches, 'diff-mismatch')}
            ${sectionHtml('Picklist mismatches', picklistMismatches, 'diff-mismatch')}
            ${totalIssues === 0 ? '<p class="text-muted small mb-0">No differences found for this object.</p>' : ''}
          </div>
        </div>
      </div>`;
  },
};


// ── Join Builder ──────────────────────────────────────────────────────────────

MC.joinBuilder = {
  init() {
    document.getElementById('btnBuild')?.addEventListener('click', () => this.buildQuery());
    document.getElementById('btnRun')?.addEventListener('click', () => this.runPython());
    document.getElementById('btnCopy')?.addEventListener('click', () => {
      const sql = document.getElementById('generatedSql')?.textContent || '';
      MC.copyToClipboard(sql);
    });
  },

  _collectConfig() {
    const sqlTable = document.getElementById('sqlTable')?.value?.trim() || '';
    const sqlFields = (document.getElementById('sqlFields')?.value || '')
      .split('\n').map(s => s.trim()).filter(Boolean);
    const joinFieldSql = document.getElementById('joinFieldSql')?.value?.trim() || '';
    const sfObject = document.getElementById('sfObject')?.value || '';
    const sfFields = (document.getElementById('sfFields')?.value || '')
      .split('\n').map(s => s.trim()).filter(Boolean);
    const joinFieldSf = document.getElementById('joinFieldSf')?.value?.trim() || '';
    return { sql_table: sqlTable, sql_fields: sqlFields, join_field_sql: joinFieldSql, sf_object: sfObject, sf_fields: sfFields, join_field_sf: joinFieldSf };
  },

  async buildQuery() {
    const config = this._collectConfig();
    if (!config.sql_table || !config.sf_object) {
      MC.showToast('Enter both a SQL table name and a Salesforce object', 'warning');
      return;
    }
    MC.showSpinner();
    try {
      const data = await MC.api('/data-ops/join/build', 'POST', config);
      const sqlEl = document.getElementById('generatedSql');
      if (sqlEl) sqlEl.textContent = data.openquery_sql || data.sql || data.query || '-- No SQL generated';
      MC.showToast('Query built', 'success');
    } catch (err) {
      MC.showToast(`Build failed: ${err.message}`, 'danger');
    } finally {
      MC.hideSpinner();
    }
  },

  async runPython() {
    const config = this._collectConfig();
    if (!config.sql_table || !config.sf_object) {
      MC.showToast('Enter both a SQL table name and a Salesforce object', 'warning');
      return;
    }
    const resultsWrap = document.getElementById('joinResultsWrap');
    const loadEl = document.getElementById('joinLoading');
    const headEl = document.getElementById('joinResultsHead');
    const bodyEl = document.getElementById('resultsTable');
    const countEl = document.getElementById('joinResultCount');

    if (resultsWrap) resultsWrap.classList.remove('d-none');
    if (loadEl) loadEl.classList.remove('d-none');
    if (headEl) headEl.innerHTML = '';
    if (bodyEl) bodyEl.innerHTML = '';
    MC.showSpinner();

    try {
      const data = await MC.api('/data-ops/join/run', 'POST', config);
      const odbcEl = document.getElementById('odbcInfoBox');
      if (data.odbc_required && odbcEl) odbcEl.classList.remove('d-none');
      this.renderResults(data);
    } catch (err) {
      const odbcEl = document.getElementById('odbcInfoBox');
      if (err.message?.toLowerCase().includes('odbc') && odbcEl) odbcEl.classList.remove('d-none');
      MC.showToast(`Run failed: ${err.message}`, 'danger');
    } finally {
      MC.hideSpinner();
      if (loadEl) loadEl.classList.add('d-none');
    }
  },

  renderResults(data) {
    const headEl = document.getElementById('joinResultsHead');
    const bodyEl = document.getElementById('resultsTable');
    const countEl = document.getElementById('joinResultCount');
    const records = data.records || data.rows || data || [];
    if (!headEl || !bodyEl) return;

    if (!records || records.length === 0) {
      if (countEl) countEl.textContent = 'No records returned.';
      headEl.innerHTML = '';
      bodyEl.innerHTML = '<tr><td class="text-center text-muted py-3">No results.</td></tr>';
      return;
    }

    const columns = Object.keys(records[0]);
    headEl.innerHTML = `<tr>${columns.map(c => `<th>${MC._escHtml(c)}</th>`).join('')}</tr>`;
    bodyEl.innerHTML = records.map(row =>
      `<tr>${columns.map(c => {
        const v = row[c];
        const display = v == null ? '' : String(v);
        return `<td title="${MC._escHtml(display)}">${MC._escHtml(display)}</td>`;
      }).join('')}</tr>`
    ).join('');

    if (countEl) countEl.textContent = `${records.length.toLocaleString()} row${records.length !== 1 ? 's' : ''}`;
  },
};


// ── Settings ──────────────────────────────────────────────────────────────────

MC.settings = {
  _runModal: null,

  init() {
    // Wire test buttons in the static org rows
    ['dev', 'prod', 'sandbox'].forEach(org => {
      // Buttons use inline onclick — no extra wiring needed for those
    });

    document.getElementById('btnTestConductor')?.addEventListener('click', async () => {
      const resultEl = document.getElementById('conductorTestResult');
      if (resultEl) resultEl.innerHTML = '<span class="spinner-border spinner-border-sm text-warning"></span>';
      try {
        const data = await MC.api('/settings/org/dev/test');
        if (resultEl) resultEl.innerHTML = `<span class="badge badge-green">Connected</span>`;
      } catch (err) {
        if (resultEl) resultEl.innerHTML = `<span class="badge badge-red">${MC._escHtml(err.message)}</span>`;
      }
    });

    // Collection import
    document.getElementById('btnImportCollection')?.addEventListener('click', () => {
      const fileInput = document.getElementById('collectionFileInput');
      const file = fileInput?.files[0];
      if (!file) {
        MC.showToast('Choose a JSON file first', 'warning');
        return;
      }
      this.importCollection(file);
    });

    // Run modal
    const modalEl = document.getElementById('runModal');
    if (modalEl) {
      this._runModal = new bootstrap.Modal(modalEl);
    }
    document.getElementById('btnRunCollection')?.addEventListener('click', () => {
      const colId = document.getElementById('runModalCollectionId')?.value;
      if (colId) this.runCollection(colId);
    });

    this.listCollections();
  },

  async testOrg(orgName) {
    const statusEl = document.getElementById(`orgStatus${orgName.charAt(0).toUpperCase() + orgName.slice(1)}`);
    if (statusEl) {
      statusEl.className = 'badge badge-amber';
      statusEl.textContent = 'Testing…';
    }
    let badgeCls = 'badge badge-red';
    let badgeText = 'Error';
    let toastMsg = `Test failed for ${orgName}`;
    let toastType = 'danger';
    try {
      const data = await MC.api(`/settings/org/${encodeURIComponent(orgName)}/test`);
      const ok = data && data.success !== false && !data.error;
      badgeCls = `badge ${ok ? 'badge-green' : 'badge-red'}`;
      badgeText = ok ? 'Connected' : 'Failed';
      toastMsg = `${orgName.toUpperCase()} — ${(data && data.message) || 'Connection tested'}`;
      toastType = ok ? 'success' : 'danger';
    } catch (err) {
      toastMsg = `Test failed for ${orgName}: ${err.message}`;
    }
    if (statusEl) {
      statusEl.className = badgeCls;
      statusEl.textContent = badgeText;
    }
    MC.showToast(toastMsg, toastType);
  },

  async importCollection(file) {
    const formData = new FormData();
    formData.append('file', file);
    MC.showSpinner();
    try {
      const res = await fetch('/settings/collections', { method: 'POST', body: formData });
      const data = await res.json();
      if (!res.ok || data.success === false) throw new Error(data.error || `HTTP ${res.status}`);
      MC.showToast(`Collection "${data.name || file.name}" imported`, 'success');
      await this.listCollections();
    } catch (err) {
      MC.showToast(`Import failed: ${err.message}`, 'danger');
    } finally {
      MC.hideSpinner();
    }
  },

  async listCollections() {
    const tbody = document.getElementById('collectionsTbody');
    const emptyEl = document.getElementById('collectionsEmpty');
    const loadEl = document.getElementById('collectionsLoading');
    if (!tbody) return;
    if (loadEl) loadEl.classList.remove('d-none');
    try {
      const data = await MC.api('/settings/collections');
      const collections = data.collections || data || [];
      if (emptyEl) emptyEl.classList.toggle('d-none', collections.length > 0);
      tbody.innerHTML = collections.map(col => {
        const colId = MC._escHtml(String(col.id || col.name || ''));
        const lastStatus = col.last_status || col.status || '—';
        return `<tr>
          <td><strong>${MC._escHtml(col.name || '—')}</strong></td>
          <td>${(col.request_count || col.requests || 0).toLocaleString()}</td>
          <td class="text-muted small">${MC._escHtml(MC._fmtTime(col.last_run))}</td>
          <td>${MC.statusBadge(lastStatus)}</td>
          <td class="no-print">
            <button class="btn btn-sm btn-doane me-1"
                    onclick="MC.settings.openRunModal('${colId}','${MC._escHtml(col.name || '')}')">
              &#9654; Run
            </button>
            <button class="btn btn-sm btn-outline-danger"
                    onclick="MC.settings.deleteCollection('${colId}')">
              Delete
            </button>
          </td>
        </tr>`;
      }).join('');
    } catch (err) {
      if (tbody) tbody.innerHTML = `<tr><td colspan="5" class="text-danger small">Failed to load: ${MC._escHtml(err.message)}</td></tr>`;
    } finally {
      if (loadEl) loadEl.classList.add('d-none');
    }
  },

  openRunModal(colId, colName) {
    const idEl = document.getElementById('runModalCollectionId');
    const labelEl = document.getElementById('runModalLabel');
    const resultsWrap = document.getElementById('runResultsWrap');
    const resultsList = document.getElementById('runResultsList');
    const envOverrides = document.getElementById('runModalEnvOverrides');
    if (idEl) idEl.value = colId;
    if (labelEl) labelEl.textContent = `Run Collection: ${colName}`;
    if (resultsWrap) resultsWrap.classList.add('d-none');
    if (resultsList) resultsList.innerHTML = '';
    if (envOverrides) envOverrides.value = '';
    if (this._runModal) this._runModal.show();
  },

  async runCollection(colId) {
    const runBtn = document.getElementById('btnRunCollection');
    const resultsWrap = document.getElementById('runResultsWrap');
    const resultsList = document.getElementById('runResultsList');
    const envRaw = document.getElementById('runModalEnvOverrides')?.value || '';
    const envOverrides = {};
    envRaw.split('\n').forEach(line => {
      const idx = line.indexOf('=');
      if (idx > 0) {
        const k = line.slice(0, idx).trim();
        const v = line.slice(idx + 1).trim();
        if (k) envOverrides[k] = v;
      }
    });

    if (runBtn) { runBtn.disabled = true; runBtn.textContent = 'Running…'; }
    if (resultsWrap) resultsWrap.classList.add('d-none');
    if (resultsList) resultsList.innerHTML = '';
    MC.showSpinner();
    try {
      const data = await MC.api(`/settings/collections/${encodeURIComponent(colId)}/run`, 'POST', { env_overrides: envOverrides });
      const requests = data.results || data.requests || data || [];
      if (resultsList) {
        resultsList.innerHTML = requests.map(req => {
          const ok = req.status === 'pass' || req.status === 'success' || (req.status_code >= 200 && req.status_code < 300);
          return `<div class="list-group-item d-flex justify-content-between align-items-center py-2">
            <span>${MC._escHtml(req.name || req.request || '—')}</span>
            <span class="badge ${ok ? 'badge-green' : 'badge-red'}">${MC._escHtml(String(req.status_code || req.status || '—'))}</span>
          </div>`;
        }).join('');
      }
      if (resultsWrap) resultsWrap.classList.remove('d-none');
      const passed = requests.filter(r => r.status === 'pass' || r.status === 'success' || (r.status_code >= 200 && r.status_code < 300)).length;
      MC.showToast(`Collection ran: ${passed}/${requests.length} passed`, passed === requests.length ? 'success' : 'warning');
      await this.listCollections();
    } catch (err) {
      MC.showToast(`Run failed: ${err.message}`, 'danger');
    } finally {
      MC.hideSpinner();
      if (runBtn) { runBtn.disabled = false; runBtn.textContent = '▶ Run Collection'; }
    }
  },

  async deleteCollection(colId) {
    if (!confirm('Delete this collection? This cannot be undone.')) return;
    MC.showSpinner();
    try {
      await MC.api(`/settings/collections/${encodeURIComponent(colId)}`, 'DELETE');
      MC.showToast('Collection deleted', 'success');
      await this.listCollections();
    } catch (err) {
      MC.showToast(`Delete failed: ${err.message}`, 'danger');
    } finally {
      MC.hideSpinner();
    }
  },
};


// ── Org Switcher (navbar) ─────────────────────────────────────────────────────

document.addEventListener('DOMContentLoaded', () => {
  document.getElementById('orgPicker')?.addEventListener('change', async (e) => {
    const org = e.target.value;
    try {
      await MC.api('/settings/org/switch', 'POST', { org });
      const badgeEl = document.getElementById('activeOrgBadge');
      if (badgeEl) badgeEl.textContent = org.toUpperCase();
      // Update meta tag so MC.activeOrg() returns correct value
      const metaEl = document.querySelector('meta[name="active-org"]');
      if (metaEl) metaEl.setAttribute('content', org);
      MC.showToast(`Switched to ${org.toUpperCase()} org`, 'success');
    } catch (err) {
      MC.showToast(`Failed to switch org: ${err.message}`, 'danger');
      // Revert picker to previous value
      e.target.value = MC.activeOrg();
    }
  });
});
