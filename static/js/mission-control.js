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

/**
 * Show a confirmation modal. Returns a Promise resolving true (confirmed) or
 * false (cancelled / dismissed). A single modal element is built lazily and
 * reused. This is the one confirmation primitive for every state-changing
 * action — never use the native window.confirm().
 *
 * opts: {
 *   title:        heading text         (default "Confirm action")
 *   body:         explanation text     (default "Are you sure?")
 *   confirmText:  confirm button label (default "Confirm")
 *   confirmClass: confirm button class (default "btn-danger")
 *   requireAck:   when true, an acknowledgement checkbox must be ticked
 *                 before the confirm button enables
 * }
 */
MC._confirmModal = null;
MC.confirm = (opts = {}) => {
  const {
    title = 'Confirm action',
    body = 'Are you sure?',
    confirmText = 'Confirm',
    confirmClass = 'btn-danger',
    requireAck = false,
  } = opts;

  if (!MC._confirmModal) {
    const wrap = document.createElement('div');
    wrap.innerHTML = `
      <div class="modal fade" id="mcConfirmModal" tabindex="-1" aria-hidden="true">
        <div class="modal-dialog modal-dialog-centered">
          <div class="modal-content">
            <div class="modal-header">
              <h5 class="modal-title" id="mcConfirmTitle"></h5>
              <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Close"></button>
            </div>
            <div class="modal-body">
              <p id="mcConfirmBody" class="mb-2" style="white-space:pre-line;"></p>
              <div class="form-check d-none" id="mcConfirmAckWrap">
                <input class="form-check-input" type="checkbox" id="mcConfirmAck">
                <label class="form-check-label" for="mcConfirmAck">
                  I understand this action cannot be undone.
                </label>
              </div>
            </div>
            <div class="modal-footer">
              <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">Cancel</button>
              <button type="button" class="btn btn-danger" id="mcConfirmOk">Confirm</button>
            </div>
          </div>
        </div>
      </div>`;
    document.body.appendChild(wrap.firstElementChild);
    MC._confirmModal = new bootstrap.Modal(document.getElementById('mcConfirmModal'));
  }

  const modalEl = document.getElementById('mcConfirmModal');
  modalEl.querySelector('#mcConfirmTitle').textContent = title;
  modalEl.querySelector('#mcConfirmBody').textContent = body;
  const okBtn = modalEl.querySelector('#mcConfirmOk');
  okBtn.textContent = confirmText;
  okBtn.className = `btn ${confirmClass}`;

  const ackWrap = modalEl.querySelector('#mcConfirmAckWrap');
  const ackBox = modalEl.querySelector('#mcConfirmAck');
  ackBox.checked = false;
  if (requireAck) {
    ackWrap.classList.remove('d-none');
    okBtn.disabled = true;
    ackBox.onchange = () => { okBtn.disabled = !ackBox.checked; };
  } else {
    ackWrap.classList.add('d-none');
    okBtn.disabled = false;
    ackBox.onchange = null;
  }

  return new Promise((resolve) => {
    let settled = false;
    const cleanup = () => {
      okBtn.removeEventListener('click', onOk);
      modalEl.removeEventListener('hidden.bs.modal', onHide);
    };
    const onOk = () => {
      settled = true;
      cleanup();
      MC._confirmModal.hide();
      resolve(true);
    };
    const onHide = () => {
      if (settled) return;
      cleanup();
      resolve(false);
    };
    okBtn.addEventListener('click', onOk);
    modalEl.addEventListener('hidden.bs.modal', onHide);
    MC._confirmModal.show();
  });
};

/**
 * Declarative confirmation guard. Any element carrying a `data-mc-confirm`
 * attribute has its click intercepted in the capture phase: the action only
 * proceeds once the user confirms in the MC.confirm() modal. Because it runs
 * at capture phase and stops propagation, it gates the element regardless of
 * which script (mission-control.js or a per-tab snippet) wired its handler.
 *
 *   data-mc-confirm        confirmation message            (required)
 *   data-mc-confirm-title  modal heading
 *   data-mc-confirm-btn    confirm button label
 *   data-mc-confirm-ack    "true" to require the acknowledgement checkbox
 */
document.addEventListener('click', (e) => {
  const el = e.target.closest('[data-mc-confirm]');
  if (!el) return;
  if (el.dataset.mcConfirmed === '1') {   // second pass — let the real handler run
    delete el.dataset.mcConfirmed;
    return;
  }
  if (el.disabled) return;
  e.preventDefault();
  e.stopImmediatePropagation();
  MC.confirm({
    title: el.dataset.mcConfirmTitle || 'Confirm action',
    body: el.dataset.mcConfirm || 'Are you sure?',
    confirmText: el.dataset.mcConfirmBtn || 'Confirm',
    requireAck: el.dataset.mcConfirmAck === 'true',
  }).then((ok) => {
    if (!ok) return;
    el.dataset.mcConfirmed = '1';
    el.click();
  });
}, true);

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
    'badge-slate';
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

/** True when the string looks like a real 15- or 18-char Salesforce record ID. */
MC.isSfId = (v) =>
  typeof v === 'string' && /^[a-zA-Z0-9]{15}([a-zA-Z0-9]{3})?$/.test(v);

/**
 * Build a Salesforce URL for a record ID, or null when unavailable
 * (no SF instance is set, or the value is not a real SF ID).
 * When objectApiName is given, builds the explicit Lightning record path;
 * otherwise uses the bare-ID URL, which Salesforce resolves to the right
 * record page regardless of object type.
 */
MC.sfLink = (id, objectApiName) => {
  const instance = document.querySelector('meta[name="sf-instance"]')?.content || '';
  if (!instance || instance === 'mock.salesforce.com') return null;
  if (!MC.isSfId(id)) return null;
  return objectApiName
    ? `https://${instance}/lightning/r/${objectApiName}/${id}/view`
    : `https://${instance}/${id}`;
};

/** Return an anchor tag linking to the SF record, or just the ID/label text if unavailable. */
MC.sfLinkTag = (id, objectApiName, label) => {
  const url = MC.sfLink(id, objectApiName);
  const display = MC._escHtml(label != null ? label : id);
  return url
    ? `<a href="${url}" target="_blank" rel="noopener" title="Open in Salesforce">${display} <span style="font-size:0.7em">↗</span></a>`
    : display;
};

/** Build a Salesforce object list-view URL, or null when no live instance. */
MC.sfObjectLink = (objectApiName) => {
  const instance = document.querySelector('meta[name="sf-instance"]')?.content || '';
  if (!instance || instance === 'mock.salesforce.com' || !objectApiName) return null;
  return `https://${instance}/lightning/o/${encodeURIComponent(objectApiName)}/list`;
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
    const wfIds = cat.workflow_ids || [];
    const sisHtml = sisIds.length > 0
      ? sisIds.map(id => `<div>${MC._escHtml(String(id))}</div>`).join('')
      : '<div class="text-muted">No sample IDs available.</div>';
    const escapedCode = MC._escHtml(code);
    const jsonCode = JSON.stringify(code);

    // Build requeue buttons for each workflow_id in this category
    const requeueBtns = wfIds.length > 0
      ? wfIds.slice(0, 5).map(batchId => `
          <button class="btn btn-sm btn-outline-warning no-print"
                  onclick="MC.reconciler.requeueBatch('${MC._escHtml(String(batchId))}')">
            &#8634; Requeue ${MC._escHtml(String(batchId))}
          </button>`).join('')
      : '';

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
          <div class="d-flex gap-1 flex-wrap">
            <button class="btn btn-sm btn-outline-warning no-print"
                    onclick="MC.reconciler.rerunCategory(${jsonCode})">
              Re-run
            </button>
          </div>
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

  async requeueBatch(batchId) {
    if (!confirm(`Requeue batch ${batchId}?`)) return;
    try {
      const data = await MC.api('/migration/errors/requeue', 'POST', {batch_id: batchId});
      MC.showToast(`Batch ${batchId}: ${data.message || data.status}`, 'success');
    } catch (err) {
      MC.showToast(`Requeue failed: ${err.message}`, 'danger');
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
      const sampleHtml = sampleIds
        .map(id => `<span class="font-monospace small me-1">${MC.sfLinkTag(String(id), 'Account')}</span>`)
        .join(' ');
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
        : records.map(r => {
            const rid = r.Id || r.id || '';
            return `<tr>
            <td class="font-monospace small">${rid ? MC.sfLinkTag(rid, objectName) : '—'}</td>
            <td>${MC._escHtml(r.Name || r.name || '—')}</td>
            <td class="text-muted small">${MC._escHtml(r.CreatedDate || r.created_date || '—')}</td>
          </tr>`;
          }).join('');
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
        sampleList.innerHTML = sampleIds
          .map(id => `<div class="font-monospace small">${MC.sfLinkTag(String(id), `ContactPoint${capT}`)}</div>`)
          .join('');
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
  _historyLoaded: false,
  _historyVisible: false,

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

    this._renderOperators();
    this.loadObjects();
    this.loadSavedQueries();
  },

  // ── Field & Operator Helper ─────────────────────────────────────────────────

  _OPERATORS: [
    'SELECT', 'FROM',
    '=', '!=', '<', '>', '<=', '>=', 'LIKE', 'IN (', 'NOT IN (', 'INCLUDES (',
    'AND', 'OR', 'NOT', 'NULL', 'TRUE', 'FALSE',
    'WHERE', 'ORDER BY', 'GROUP BY', 'HAVING', 'LIMIT', 'OFFSET',
    'ASC', 'DESC', 'NULLS LAST', 'COUNT()', 'TODAY', 'LAST_N_DAYS:',
  ],

  _renderOperators() {
    const el = document.getElementById('soqlOperators');
    if (!el) return;
    el.innerHTML = this._OPERATORS.map(op =>
      `<button type="button" class="btn btn-outline-secondary btn-sm py-0 px-1 font-monospace"
               style="font-size:0.72rem"
               onclick="MC.soql._insertText(' ${MC._escHtml(op)} ')">${MC._escHtml(op)}</button>`
    ).join('');
  },

  _insertText(text) {
    const editor = document.getElementById('soqlEditor');
    if (!editor) return;
    const start = editor.selectionStart ?? editor.value.length;
    const end = editor.selectionEnd ?? editor.value.length;
    editor.value = editor.value.slice(0, start) + text + editor.value.slice(end);
    const pos = start + text.length;
    editor.focus();
    editor.setSelectionRange(pos, pos);
  },

  toggleHelper() {
    const body = document.getElementById('soqlHelperBody');
    const toggle = document.getElementById('soqlHelperToggle');
    if (!body) return;
    const hidden = body.classList.toggle('d-none');
    if (toggle) toggle.innerHTML = hidden ? '&#9660;' : '&#9650;';
  },

  _renderHelperFields(objectName, fields) {
    const el = document.getElementById('soqlHelperFields');
    const label = document.getElementById('soqlHelperFieldsLabel');
    if (label) label.textContent = `Fields on ${objectName} — click to add to SELECT`;
    if (!el) return;
    el.innerHTML = fields.map(f => {
      const name = f.name || f;
      return `<button type="button" class="btn btn-outline-secondary btn-sm py-0 px-1 font-monospace"
               style="font-size:0.72rem"
               onclick="MC.soql._insertField('${MC._escHtml(name)}')">${MC._escHtml(name)}</button>`;
    }).join('');
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
      this._historyLoaded = false;
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
        // Cells holding a Salesforce record ID (the Id column and any lookup
        // field) link straight to the record. ID cells are not inline-editable.
        if (MC.isSfId(display)) {
          return `<td title="${MC._escHtml(display)}" class="font-monospace small">${MC.sfLinkTag(display)}</td>`;
        }
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
      this._renderHelperFields(objectName, fields);
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

  toggleHistory() {
    this._historyVisible = !this._historyVisible;
    document.getElementById('historyPanelBody')?.classList.toggle('d-none', !this._historyVisible);
    document.getElementById('historyToggleIcon').textContent = this._historyVisible ? '▲' : '▼';
    if (this._historyVisible && !this._historyLoaded) this.loadHistory();
  },

  async loadHistory() {
    const loading = document.getElementById('historyLoading');
    const empty   = document.getElementById('historyEmpty');
    const list    = document.getElementById('historyList');
    loading?.classList.remove('d-none');
    list?.classList.add('d-none');
    empty?.classList.add('d-none');
    try {
      const items = await MC.api('/soql/history');
      loading?.classList.add('d-none');
      if (!items || items.length === 0) {
        empty?.classList.remove('d-none');
        return;
      }
      list.innerHTML = items.map(h => `
        <li class="list-group-item list-group-item-action py-2 px-3 d-flex justify-content-between align-items-start"
            style="cursor:pointer" onclick="MC.soql._loadFromHistory(${MC._escHtml(JSON.stringify(h.query))})">
          <div class="font-monospace small text-truncate me-2" style="max-width:80%;"
               title="${MC._escHtml(h.query)}">${MC._escHtml(h.query)}</div>
          <div class="text-end text-muted" style="white-space:nowrap;font-size:0.75rem;">
            <span class="badge badge-slate me-1">${h.row_count ?? '?'} rows</span>
            <button class="btn btn-sm p-0 text-muted" style="font-size:0.75rem;"
                    onclick="event.stopPropagation(); MC.soql._deleteHistory(${h.id}, this)">✕</button>
          </div>
        </li>`).join('');
      list?.classList.remove('d-none');
      this._historyLoaded = true;
    } catch (err) {
      loading?.classList.add('d-none');
      MC.showToast('Failed to load history', 'danger');
    }
  },

  _loadFromHistory(query) {
    const editor = document.getElementById('soqlEditor');
    if (editor) { editor.value = query; editor.focus(); }
  },

  async _deleteHistory(id, btn) {
    try {
      await MC.api(`/soql/history/${id}`, 'DELETE');
      btn.closest('li')?.remove();
    } catch (err) {
      MC.showToast('Delete failed', 'danger');
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
  _defaultObjects: [
    'Account', 'ContactPointEmail', 'ContactPointPhone',
    'ContactPointAddress', 'IndividualApplication', 'Opportunity',
  ],
  _selectedObjects: [],

  init() {
    document.getElementById('btnRunDiff')?.addEventListener('click', () => this.run());
    document.getElementById('btnResetObjects')?.addEventListener('click', () => this._resetObjects());
    this._initTagInput();
  },

  _initTagInput() {
    this._selectedObjects = [...this._defaultObjects];
    this._renderTags();
    const input = document.getElementById('objectTagInput');
    if (!input) return;
    input.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' || e.key === ',') {
        e.preventDefault();
        const val = input.value.trim().replace(/,$/, '');
        if (val) this._addObject(val);
        input.value = '';
      } else if (e.key === 'Backspace' && input.value === '' && this._selectedObjects.length > 0) {
        this._selectedObjects.pop();
        this._renderTags();
      }
    });
  },

  _addObject(name) {
    const clean = name.trim();
    if (!clean || this._selectedObjects.includes(clean)) return;
    this._selectedObjects.push(clean);
    this._renderTags();
  },

  _removeObject(name) {
    this._selectedObjects = this._selectedObjects.filter(o => o !== name);
    this._renderTags();
  },

  _resetObjects() {
    this._selectedObjects = [...this._defaultObjects];
    this._renderTags();
    const input = document.getElementById('objectTagInput');
    if (input) input.value = '';
  },

  _renderTags() {
    const container = document.getElementById('objectTagContainer');
    const input = document.getElementById('objectTagInput');
    if (!container || !input) return;
    // Remove existing tags (everything except the input)
    Array.from(container.children).forEach(el => {
      if (el !== input) el.remove();
    });
    // Prepend tags before the input
    [...this._selectedObjects].reverse().forEach(obj => {
      const tag = document.createElement('span');
      tag.className = 'badge bg-secondary d-flex align-items-center gap-1';
      tag.style.fontSize = '0.75rem';
      tag.innerHTML = `${MC._escHtml(obj)}<button type="button" class="btn-close btn-close-white" style="font-size:0.55rem;" aria-label="Remove"></button>`;
      tag.querySelector('.btn-close').addEventListener('click', (e) => {
        e.stopPropagation();
        this._removeObject(obj);
      });
      container.insertBefore(tag, input);
    });
  },

  async run() {
    const rightOrg = document.getElementById('rightOrgSelect')?.value;
    // Flush any pending text in the tag input
    const tagInput = document.getElementById('objectTagInput');
    if (tagInput?.value.trim()) {
      this._addObject(tagInput.value.trim());
      tagInput.value = '';
    }
    const objects = [...this._selectedObjects];

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
  _sfObjects: [],
  _sqlTables: [],

  init() {
    document.getElementById('btnBuild')?.addEventListener('click', () => this.buildQuery());
    document.getElementById('btnRun')?.addEventListener('click', () => this.runPython());
    document.getElementById('btnCheckFields')?.addEventListener('click', () => this.checkFields());
    document.getElementById('btnCopy')?.addEventListener('click', () => {
      const sql = document.getElementById('generatedSql')?.textContent || '';
      MC.copyToClipboard(sql);
    });
    this._attachTypeahead('sfObject', 'sfObjectMenu', () => this._sfObjects);
    this._attachTypeahead('sqlTable', 'sqlTableMenu', () => this._sqlTables);
    this.loadSfObjects();
    this.loadSqlSchema();
  },

  // ── Typeahead ───────────────────────────────────────────────────────────────
  // A custom dropdown so the menu width matches the input. Native <datalist>
  // popups are browser-positioned and overflow the field, which looks off.

  _attachTypeahead(inputId, menuId, getItems) {
    const input = document.getElementById(inputId);
    const menu  = document.getElementById(menuId);
    if (!input || !menu) return;
    let activeIdx = -1;

    const render = () => {
      const q = input.value.trim().toLowerCase();
      const all = getItems() || [];
      const matches = (q ? all.filter(n => n.toLowerCase().includes(q)) : all).slice(0, 50);
      activeIdx = -1;
      if (matches.length === 0) {
        menu.classList.add('d-none');
        return;
      }
      menu.innerHTML = matches.map(n =>
        `<div class="mc-typeahead-item" data-val="${MC._escHtml(n)}">${MC._escHtml(n)}</div>`
      ).join('');
      menu.classList.remove('d-none');
    };

    const choose = (val) => {
      input.value = val;
      menu.classList.add('d-none');
      input.dispatchEvent(new Event('change', { bubbles: true }));
    };

    input.addEventListener('input', render);
    input.addEventListener('focus', render);
    input.addEventListener('blur', () => setTimeout(() => menu.classList.add('d-none'), 150));
    input.addEventListener('keydown', (e) => {
      const items = Array.from(menu.querySelectorAll('.mc-typeahead-item'));
      if (menu.classList.contains('d-none') || items.length === 0) return;
      if (e.key === 'ArrowDown') {
        e.preventDefault();
        activeIdx = Math.min(activeIdx + 1, items.length - 1);
      } else if (e.key === 'ArrowUp') {
        e.preventDefault();
        activeIdx = Math.max(activeIdx - 1, 0);
      } else if (e.key === 'Enter') {
        if (activeIdx >= 0) {
          e.preventDefault();
          choose(items[activeIdx].dataset.val);
        }
        return;
      } else if (e.key === 'Escape') {
        menu.classList.add('d-none');
        return;
      } else {
        return;
      }
      items.forEach((el, i) => el.classList.toggle('active', i === activeIdx));
      items[activeIdx]?.scrollIntoView({ block: 'nearest' });
    });
    // mousedown (not click) so it fires before the input's blur
    menu.addEventListener('mousedown', (e) => {
      const item = e.target.closest('.mc-typeahead-item');
      if (item) {
        e.preventDefault();
        choose(item.dataset.val);
      }
    });
  },

  // ── Typeahead data sources ──────────────────────────────────────────────────

  async loadSfObjects() {
    const status = document.getElementById('sfObjectStatus');
    try {
      const objects = await MC.api('/data-ops/sf-objects') || [];
      const names = objects.map(o => (typeof o === 'string' ? o : (o.name || ''))).filter(Boolean);
      this._sfObjects = names;
      if (status) status.textContent = `${names.length.toLocaleString()} objects — type to filter.`;
    } catch (err) {
      if (status) status.textContent = 'Could not load objects: ' + err.message;
    }
  },

  async loadSqlSchema() {
    const status = document.getElementById('sqlSchemaStatus');
    try {
      const d = await MC.api('/data-ops/sql-schema');
      this._sqlTables = d.tables || [];
      if (status) {
        if (d.table_count) {
          const when = d.captured_at ? new Date(d.captured_at).toLocaleString() : 'unknown';
          status.textContent = `${d.table_count.toLocaleString()} tables cached (${when}) — type to filter.`;
        } else {
          status.textContent = 'No SQL schema cached yet — refresh it from Settings → SQL Server Schema Cache.';
        }
      }
    } catch (err) {
      if (status) status.textContent = 'Could not load SQL schema: ' + err.message;
    }
  },

  // ── Field checker ───────────────────────────────────────────────────────────

  async checkFields() {
    const cfg = this._collectConfig();
    const box = document.getElementById('joinCheckResult');
    if (!box) return;
    box.className = 'mb-3';
    box.innerHTML = '<div class="text-muted small">Checking fields…</div>';
    const problems = [];
    const oks = [];

    // SF side — validate against the object's describe
    if (cfg.sf_object && cfg.sf_fields.length) {
      try {
        const fields = await MC.api(`/data-ops/sf-object-fields?object=${encodeURIComponent(cfg.sf_object)}`);
        const known = new Set((fields || []).map(f => (f.name || f).toLowerCase()));
        const bad = cfg.sf_fields.filter(f => !known.has(f.toLowerCase()));
        if (bad.length) problems.push(`Salesforce ${cfg.sf_object}: unknown field(s) — ${bad.join(', ')}`);
        else oks.push(`Salesforce ${cfg.sf_object}: all ${cfg.sf_fields.length} field(s) valid`);
      } catch (err) {
        problems.push(`Salesforce ${cfg.sf_object}: could not verify — ${err.message}`);
      }
    }

    // SQL side — validate against the cached schema
    if (cfg.sql_table && cfg.sql_fields.length) {
      try {
        const d = await MC.api(`/data-ops/sql-schema?table=${encodeURIComponent(cfg.sql_table)}`);
        const cols = d.columns || [];
        if (!cols.length) {
          problems.push(`SQL ${cfg.sql_table}: not in the cached schema — refresh, or check the name`);
        } else {
          const known = new Set(cols.map(c => c.toLowerCase()));
          const bad = cfg.sql_fields.filter(f => !known.has(f.toLowerCase()));
          if (bad.length) problems.push(`SQL ${cfg.sql_table}: unknown column(s) — ${bad.join(', ')}`);
          else oks.push(`SQL ${cfg.sql_table}: all ${cfg.sql_fields.length} column(s) valid`);
        }
      } catch (err) {
        problems.push(`SQL ${cfg.sql_table}: could not verify — ${err.message}`);
      }
    }

    if (!problems.length && !oks.length) {
      box.innerHTML = '<div class="alert alert-secondary mb-0 small">Enter an object/table and fields to check.</div>';
      return;
    }
    const okHtml = oks.map(o => `<div class="text-success small">&#10003; ${MC._escHtml(o)}</div>`).join('');
    const badHtml = problems.map(p => `<div class="text-danger small">&#10007; ${MC._escHtml(p)}</div>`).join('');
    box.className = `mb-3 alert ${problems.length ? 'alert-warning' : 'alert-success'}`;
    box.innerHTML = okHtml + badHtml;
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

    // SQL Server schema cache
    document.getElementById('btnRefreshSqlSchema')?.addEventListener('click', () => this.refreshSqlSchema());

    this.listCollections();
    this.loadSqlSchemaStatus();
  },

  async loadSqlSchemaStatus() {
    const status = document.getElementById('sqlSchemaCacheStatus');
    if (!status) return;
    try {
      const d = await MC.api('/data-ops/sql-schema');
      if (d.table_count) {
        const when = d.captured_at ? new Date(d.captured_at).toLocaleString() : 'unknown';
        status.textContent = `${d.table_count.toLocaleString()} tables cached (${when}).`;
      } else {
        status.textContent = 'No SQL schema cached yet — click Refresh to build it.';
      }
    } catch (err) {
      status.textContent = 'Could not read SQL schema cache: ' + err.message;
    }
  },

  async refreshSqlSchema() {
    const status = document.getElementById('sqlSchemaCacheStatus');
    if (status) status.textContent = 'Refreshing SQL schema…';
    try {
      const d = await MC.api('/data-ops/sql-schema/refresh', 'POST');
      MC.showToast(`SQL schema refreshed — ${d.table_count} tables`, 'success');
      await this.loadSqlSchemaStatus();
    } catch (err) {
      MC.showToast('Schema refresh failed: ' + err.message, 'danger');
      if (status) status.textContent = 'Refresh failed: ' + err.message;
    }
  },

  async testOrg(orgName) {
    const orgCap = orgName.charAt(0).toUpperCase() + orgName.slice(1);
    const statusEl = document.getElementById(`orgStatus${orgCap}`);
    const instanceEl = document.getElementById(`orgInstance${orgCap}`);
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
      if (ok && instanceEl) {
        instanceEl.textContent = data.instance_url || '–';
        instanceEl.className = data.instance_url ? 'small font-monospace' : 'text-muted small';
      }
    } catch (err) {
      toastMsg = `Test failed for ${orgName}: ${err.message}`;
    }
    if (statusEl) {
      statusEl.className = badgeCls;
      statusEl.textContent = badgeText;
    }
    MC.showToast(toastMsg, toastType);
  },

  async toggleBypass(enabled) {
    try {
      await MC.api('/settings/bypass-triggers', 'POST', { enabled });
      MC.showToast(`Bypass triggers ${enabled ? 'enabled' : 'disabled'}`, enabled ? 'warning' : 'success');
    } catch (err) {
      MC.showToast(`Failed to toggle bypass triggers: ${err.message}`, 'danger');
      const el = document.getElementById('bypassTriggersToggle');
      if (el) el.checked = !enabled;
    }
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
      // Reload so every server-rendered page and widget re-fetches for the new org.
      window.location.reload();
    } catch (err) {
      MC.showToast(`Failed to switch org: ${err.message}`, 'danger');
      // Revert picker to previous value
      e.target.value = MC.activeOrg();
    }
  });
});

// ── Mock-mode helpers ─────────────────────────────────────────────────────────

/** Return true when SHOW_MOCK=true on the server (everything is mocked). */
MC.isMock = () => document.querySelector('meta[name="show-mock"]')?.content === 'true';

// ── Popover / Tooltip init ────────────────────────────────────────────────────

document.addEventListener('DOMContentLoaded', () => {
  if (typeof bootstrap === 'undefined') return;
  document.querySelectorAll('[data-bs-toggle="popover"]').forEach(el => {
    new bootstrap.Popover(el, { trigger: el.dataset.bsTrigger || 'focus', html: false });
  });
  document.querySelectorAll('[data-bs-toggle="tooltip"]').forEach(el => {
    new bootstrap.Tooltip(el);
  });
});

// ── Mock-mode visual indicators ───────────────────────────────────────────────
// When SHOW_MOCK is on, every card header gets a loud amber "MOCK DATA" chip so
// nothing on the page can be mistaken for live data. The standards' Mock/Live
// Signal rule: never silent, never ambiguous.

function _mcMakeChip(text, title) {
  const chip = document.createElement('span');
  chip.className = 'mc-mock-chip ms-2';
  chip.title = title;
  chip.textContent = text;
  return chip;
}

document.addEventListener('DOMContentLoaded', () => {
  if (!MC.isMock()) return;
  document.querySelectorAll('.card-header h5').forEach(h5 => {
    h5.appendChild(_mcMakeChip('MOCK DATA', 'SHOW_MOCK=true — Salesforce / Conductor data is synthetic'));
  });
});

// ── Logs ──────────────────────────────────────────────────────────────────────

MC.logs = {
  _activeTab: 'apex',
  _autoRefreshTimer: null,

  init() {
    // Sub-tab switching
    document.querySelectorAll('[data-tab]').forEach(link => {
      link.addEventListener('click', (e) => {
        e.preventDefault();
        this._switchTab(e.currentTarget.dataset.tab);
      });
    });

    document.getElementById('btnRefreshApex')?.addEventListener('click', () => this.loadApexLogs());
    document.getElementById('btnRefreshFlows')?.addEventListener('click', () => this.loadFlowErrors());
    document.getElementById('btnRefreshCpuSummary')?.addEventListener('click', () => this.loadCpuSummary());
    document.getElementById('btnRefreshTraceFlags')?.addEventListener('click', () => this.loadTraceFlags());
    document.getElementById('btnDeleteExpired')?.addEventListener('click', () => this.deleteExpiredFlags());
    document.getElementById('btnCreateTraceFlag')?.addEventListener('click', () => this.createTraceFlag());
    document.getElementById('btnCloseDetail')?.addEventListener('click', () => this._closeDetail());

    // User search datalist population
    document.getElementById('traceFlagEntitySearch')?.addEventListener('input', (e) => {
      this._populateUserDatalist(e.target.value);
    });
    // Clear hidden entity ID when user types (requires re-selection)
    document.getElementById('traceFlagEntitySearch')?.addEventListener('change', (e) => {
      const val = e.target.value;
      const dl = document.getElementById('traceFlagUserList');
      const match = dl ? Array.from(dl.options).find(o => o.value === val) : null;
      document.getElementById('traceFlagEntityId').value = match ? match.dataset.id : '';
    });

    // Time-range toolbar
    document.getElementById('logTimeRange')?.addEventListener('change', (e) => {
      const showCustom = e.target.value === 'custom';
      document.getElementById('customRangeWrap')?.classList.toggle('d-none', !showCustom);
      if (!showCustom) this.loadApexLogs();
    });
    document.getElementById('logCustomSince')?.addEventListener('change', () => this.loadApexLogs());
    document.getElementById('autoRefreshToggle')?.addEventListener('change', (e) => {
      this._setAutoRefresh(e.target.checked);
    });
    document.getElementById('btnDeleteAllLogs')?.addEventListener('click', () => this.deleteAllLogs());

    // Load the default tab
    this.loadApexLogs();
  },

  _switchTab(tab) {
    this._activeTab = tab;
    document.querySelectorAll('[data-tab]').forEach(l => l.classList.remove('active'));
    document.querySelector(`[data-tab="${tab}"]`)?.classList.add('active');

    const showApex = tab === 'apex';
    const showFlows = tab === 'flows';
    const showCpu = tab === 'cpu';
    const showTrace = tab === 'trace';

    document.getElementById('panelApex')?.classList.toggle('d-none', !showApex);
    document.getElementById('panelFlows')?.classList.toggle('d-none', !showFlows);
    document.getElementById('panelCpuSummary')?.classList.toggle('d-none', !showCpu);
    document.getElementById('panelTrace')?.classList.toggle('d-none', !showTrace);

    if (tab === 'flows') this.loadFlowErrors();
    if (tab === 'cpu') this.loadCpuSummary();
    if (tab === 'trace') this.loadTraceFlags();
  },

  async loadApexLogs() {
    const loading = document.getElementById('apexLoading');
    const empty   = document.getElementById('apexEmpty');
    const table   = document.getElementById('apexTable');

    loading?.classList.remove('d-none');
    empty?.classList.add('d-none');
    table?.classList.add('d-none');
    this._closeDetail();

    try {
      const since = this._getSince();
      const url = since ? `/logs/apex?since=${encodeURIComponent(since)}` : '/logs/apex';
      const logs = await MC.api(url);
      if (!logs || logs.length === 0) {
        empty?.classList.remove('d-none');
        return;
      }
      this._renderApexTable(logs);
      table?.classList.remove('d-none');
    } catch (err) {
      MC.showToast(`Failed to load Apex logs: ${err.message}`, 'danger');
      empty?.classList.remove('d-none');
    } finally {
      loading?.classList.add('d-none');
    }
  },

  _getSince() {
    const range = document.getElementById('logTimeRange')?.value;
    if (!range || range === 'custom') {
      const custom = document.getElementById('logCustomSince')?.value;
      return custom ? new Date(custom).toISOString() : null;
    }
    const map = { '15m': 15, '1h': 60, '6h': 360, '24h': 1440 };
    const minutes = map[range];
    if (!minutes) return null;
    return new Date(Date.now() - minutes * 60 * 1000).toISOString();
  },

  _setAutoRefresh(enabled) {
    clearInterval(this._autoRefreshTimer);
    this._autoRefreshTimer = null;
    if (enabled) {
      this._autoRefreshTimer = setInterval(() => this.loadApexLogs(), 10000);
    }
  },

  async deleteAllLogs() {
    if (!confirm('Delete ALL Apex logs for this org? This cannot be undone.')) return;
    try {
      await MC.api('/logs/apex/delete-all', 'DELETE');
      MC.showToast('All logs deleted', 'success');
      this.loadApexLogs();
    } catch (err) {
      MC.showToast(`Delete failed: ${err.message}`, 'danger');
    }
  },

  _renderApexTable(logs) {
    const tbody = document.getElementById('apexBody');
    if (!tbody) return;
    tbody.innerHTML = logs.map(log => {
      const kb = (log.log_length / 1024).toFixed(1);
      const statusBadge = MC.statusBadge(log.status);
      return `<tr style="cursor:pointer" data-log-id="${MC._escHtml(log.id)}" onclick="MC.logs.showLogDetail('${MC._escHtml(log.id)}', '${MC._escHtml(log.operation)}')">
        <td>${MC._escHtml(log.user)}</td>
        <td><code class="small">${MC._escHtml(log.operation)}</code></td>
        <td>${statusBadge}</td>
        <td class="text-muted small">${kb} KB</td>
        <td class="text-muted small">${log.duration_ms} ms</td>
        <td class="text-muted small">${MC._fmtTime(log.last_modified)}</td>
        <td class="no-print">
          <button class="btn btn-outline-danger btn-sm py-0"
                  onclick="event.stopPropagation(); MC.logs.deleteLog('${MC._escHtml(log.id)}')">
            &times; Delete
          </button>
        </td>
      </tr>`;
    }).join('');
  },

  async showLogDetail(logId, operation) {
    const panel    = document.getElementById('apexDetailPanel');
    const loading  = document.getElementById('detailLoading');
    const title    = document.getElementById('detailTitle');

    panel?.classList.remove('d-none');
    loading?.classList.remove('d-none');
    if (title) title.textContent = `Log Detail — ${operation || logId}`;

    // Scroll to panel
    panel?.scrollIntoView({ behavior: 'smooth', block: 'start' });

    // Hide content sections while loading
    ['detailLimitsTable', 'detailLimitsEmpty', 'detailExceptionsList',
     'detailExceptionsEmpty', 'detailTimelineList', 'detailTimelineEmpty'].forEach(id => {
      document.getElementById(id)?.classList.add('d-none');
    });

    try {
      const parsed = await MC.api(`/logs/apex/${encodeURIComponent(logId)}`);
      this._renderDetail(parsed);
    } catch (err) {
      MC.showToast(`Failed to load log: ${err.message}`, 'danger');
    } finally {
      loading?.classList.add('d-none');
    }
  },

  _renderDetail(parsed) {
    // Limits
    const limitsBody  = document.getElementById('detailLimitsBody');
    const limitsTable = document.getElementById('detailLimitsTable');
    const limitsEmpty = document.getElementById('detailLimitsEmpty');
    const limits = parsed.limits || {};
    const limitKeys = Object.keys(limits);
    if (limitKeys.length === 0) {
      limitsEmpty?.classList.remove('d-none');
    } else {
      if (limitsBody) {
        limitsBody.innerHTML = limitKeys.map(label => {
          const l = limits[label];
          const pct = l.pct || 0;
          const barCls = pct >= 80 ? 'bg-danger' : pct >= 50 ? 'bg-warning' : 'bg-success';
          return `<tr>
            <td class="small">${MC._escHtml(label)}</td>
            <td class="small text-end">${l.used}</td>
            <td class="small text-end">${l.max}</td>
            <td style="min-width:120px">
              <div class="progress" style="height:8px">
                <div class="progress-bar ${barCls}" style="width:${Math.min(pct, 100)}%"></div>
              </div>
              <span class="small text-muted">${pct.toFixed(1)}%</span>
            </td>
          </tr>`;
        }).join('');
      }
      limitsTable?.classList.remove('d-none');
    }

    // Exceptions
    const excList  = document.getElementById('detailExceptionsList');
    const excEmpty = document.getElementById('detailExceptionsEmpty');
    const excs = parsed.exceptions || [];
    if (excs.length === 0) {
      excEmpty?.classList.remove('d-none');
    } else {
      if (excList) {
        excList.innerHTML = excs.map(ex => `
          <li class="list-group-item list-group-item-danger small">
            <strong>${MC._escHtml(ex.type)}</strong><br>
            <code>${MC._escHtml(ex.message)}</code>
          </li>`).join('');
      }
      excList?.classList.remove('d-none');
    }

    // Timeline
    const tmList  = document.getElementById('detailTimelineList');
    const tmEmpty = document.getElementById('detailTimelineEmpty');
    const timeline = parsed.timeline || [];
    if (timeline.length === 0) {
      tmEmpty?.classList.remove('d-none');
    } else {
      if (tmList) {
        tmList.innerHTML = timeline.map(ev => `
          <li class="list-group-item small py-1">
            <span class="badge badge-slate me-1">${MC._escHtml(ev.event)}</span>
            <span class="text-muted">${MC._escHtml(ev.detail)}</span>
          </li>`).join('');
      }
      tmList?.classList.remove('d-none');
    }
  },

  _closeDetail() {
    document.getElementById('apexDetailPanel')?.classList.add('d-none');
  },

  async deleteLog(logId) {
    if (!confirm('Delete this Apex log?')) return;
    try {
      await MC.api(`/logs/apex/${encodeURIComponent(logId)}`, 'DELETE');
      MC.showToast('Log deleted', 'success');
      // Remove row from table
      const row = document.querySelector(`[data-log-id="${logId}"]`);
      row?.remove();
      // If detail panel is open for this log, close it
      this._closeDetail();
    } catch (err) {
      MC.showToast(`Delete failed: ${err.message}`, 'danger');
    }
  },

  async loadCpuSummary() {
    const loading = document.getElementById('cpuLoading');
    const empty   = document.getElementById('cpuEmpty');
    const table   = document.getElementById('cpuTable');

    loading?.classList.remove('d-none');
    empty?.classList.add('d-none');
    table?.classList.add('d-none');

    try {
      const items = await MC.api('/logs/apex/cpu-summary');
      if (!items || items.length === 0) {
        empty?.classList.remove('d-none');
        return;
      }
      this._renderCpuSummary(items);
      table?.classList.remove('d-none');
    } catch (err) {
      MC.showToast(`Failed to load CPU summary: ${err.message}`, 'danger');
      empty?.classList.remove('d-none');
    } finally {
      loading?.classList.add('d-none');
    }
  },

  _renderCpuSummary(items) {
    const tbody = document.getElementById('cpuSummaryTbody');
    if (!tbody) return;

    // Sort by duration_ms descending
    const sorted = [...items].sort((a, b) => (b.duration_ms || 0) - (a.duration_ms || 0));

    tbody.innerHTML = sorted.map(item => {
      const duration = item.duration_ms || 0;
      const kb = ((item.log_length || 0) / 1024).toFixed(1);
      const status = item.status || '';

      // Duration color coding
      let durationCls = '';
      if (duration > 10000) {
        durationCls = 'text-danger fw-semibold';
      } else if (duration > 5000) {
        durationCls = 'text-warning fw-semibold';
      }

      // Row highlight based on status_flag
      let rowCls = '';
      if (item.status_flag === 'danger') {
        rowCls = 'table-danger';
      } else if (item.status_flag === 'warning') {
        rowCls = 'table-warning';
      }

      const statusBadge = MC.statusBadge(status || 'Success');
      const logId = item.log_id || '';

      // View Log action — links to apex tab detail if available
      const viewBtn = logId
        ? `<button class="btn btn-outline-secondary btn-sm py-0"
                   onclick="MC.logs._switchTab('apex'); MC.logs.showLogDetail('${MC._escHtml(logId)}', '${MC._escHtml(item.operation)}')">
             View Log
           </button>`
        : '—';

      return `<tr class="${rowCls}">
        <td>${MC._escHtml(item.user || '—')}</td>
        <td><code class="small">${MC._escHtml(item.operation || '—')}</code></td>
        <td class="${durationCls}">${duration.toLocaleString()} ms</td>
        <td class="text-muted small">${kb} KB</td>
        <td>${statusBadge}</td>
        <td class="no-print">${viewBtn}</td>
      </tr>`;
    }).join('');
  },

  async loadFlowErrors() {
    const flowsLoading = document.getElementById('flowsLoading');
    const flowsEmpty   = document.getElementById('flowsEmpty');
    const flowsTable   = document.getElementById('flowsTable');
    const procExEmpty  = document.getElementById('procExEmpty');
    const procExTable  = document.getElementById('procExTable');

    flowsLoading?.classList.remove('d-none');
    flowsEmpty?.classList.add('d-none');
    flowsTable?.classList.add('d-none');

    try {
      const [flows, procExs] = await Promise.all([
        MC.api('/logs/flows'),
        MC.api('/logs/process-exceptions'),
      ]);

      // Flow interviews
      if (!flows || flows.length === 0) {
        flowsEmpty?.classList.remove('d-none');
      } else {
        this._renderFlowsTable(flows);
        flowsTable?.classList.remove('d-none');
      }

      // Process exceptions
      if (!procExs || procExs.length === 0) {
        procExEmpty?.classList.remove('d-none');
      } else {
        this._renderProcExTable(procExs);
        procExTable?.classList.remove('d-none');
      }
    } catch (err) {
      MC.showToast(`Failed to load flow errors: ${err.message}`, 'danger');
      flowsEmpty?.classList.remove('d-none');
    } finally {
      flowsLoading?.classList.add('d-none');
    }
  },

  _renderFlowsTable(flows) {
    const tbody = document.getElementById('flowsBody');
    if (!tbody) return;
    tbody.innerHTML = flows.map(f => `<tr>
      <td class="small fw-semibold">${MC._escHtml(f.flow_label) || '—'}</td>
      <td><code class="small">${MC._escHtml(f.current_element) || '—'}</code></td>
      <td><span class="badge badge-red">${MC._escHtml(f.status)}</span></td>
      <td class="text-muted small">${MC._fmtTime(f.created_date)}</td>
    </tr>`).join('');
  },

  _renderProcExTable(exceptions) {
    const tbody = document.getElementById('procExBody');
    if (!tbody) return;
    tbody.innerHTML = exceptions.map(ex => `<tr>
      <td><span class="badge badge-red">${MC._escHtml(ex.exception_type)}</span></td>
      <td class="small">${MC._escHtml(ex.message)}</td>
      <td class="small text-muted">${MC._escHtml(ex.source_object)}</td>
      <td>${MC.statusBadge(ex.status)}</td>
      <td class="small text-muted">${MC._fmtTime(ex.created_date)}</td>
    </tr>`).join('');
  },

  // ── Trace Flags ─────────────────────────────────────────────────────────────

  _debugLevels: [],

  async loadTraceFlags() {
    const loading = document.getElementById('traceFlagsLoading');
    const empty   = document.getElementById('traceFlagsEmpty');
    const table   = document.getElementById('traceFlagsTable');

    loading?.classList.remove('d-none');
    empty?.classList.add('d-none');
    table?.classList.add('d-none');

    try {
      const [flags, levels] = await Promise.all([
        MC.api('/logs/trace-flags'),
        MC.api('/logs/trace-flags/debug-levels'),
      ]);

      // Populate debug level select
      this._debugLevels = levels || [];
      const levelSel = document.getElementById('traceFlagDebugLevel');
      if (levelSel && levels && levels.length > 0) {
        levelSel.innerHTML = levels.map(l =>
          `<option value="${MC._escHtml(l.id)}">${MC._escHtml(l.label || l.name)}</option>`
        ).join('');
      }

      // Populate also the user datalist with initial top users
      await this._populateUserDatalist('');

      if (!flags || flags.length === 0) {
        empty?.classList.remove('d-none');
      } else {
        this._renderTraceFlagsTable(flags);
        table?.classList.remove('d-none');
      }
    } catch (err) {
      MC.showToast(`Failed to load trace flags: ${err.message}`, 'danger');
      empty?.classList.remove('d-none');
    } finally {
      loading?.classList.add('d-none');
    }
  },

  _renderTraceFlagsTable(flags) {
    const tbody = document.getElementById('traceFlagsTbody');
    if (!tbody) return;
    tbody.innerHTML = flags.map(f => {
      const expired = f.expired;
      const rowCls = expired ? 'table-secondary text-muted' : '';
      let statusCell;
      if (expired) {
        statusCell = '<span class="badge bg-secondary">Expired</span>';
      } else {
        const mins = f.expires_in_minutes;
        const color = (mins !== null && mins < 5) ? 'text-warning fw-semibold' : 'text-success fw-semibold';
        statusCell = `<span class="${color}">${mins !== null ? mins + 'm remaining' : 'Active'}</span>`;
      }
      const deleteBtn = `<button class="btn btn-outline-danger btn-sm py-0"
                                 onclick="MC.logs.deleteTraceFlag('${MC._escHtml(f.id)}')">
                           &times; Delete
                         </button>`;
      return `<tr class="${rowCls}">
        <td class="small font-monospace">${MC.sfLinkTag(f.traced_entity_id, f.traced_entity_type)}</td>
        <td class="small">${MC._escHtml(f.traced_entity_type)}</td>
        <td class="small">${MC._escHtml(f.debug_level_name)}</td>
        <td class="small">${MC._escHtml(f.log_type)}</td>
        <td class="small text-muted">${MC._fmtTime(f.expiration_date)}</td>
        <td>${statusCell}</td>
        <td class="no-print">${deleteBtn}</td>
      </tr>`;
    }).join('');
  },

  async deleteTraceFlag(flagId) {
    if (!confirm('Delete this trace flag?')) return;
    try {
      await MC.api(`/logs/trace-flags/${encodeURIComponent(flagId)}`, 'DELETE');
      MC.showToast('Trace flag deleted', 'success');
      await this.loadTraceFlags();
    } catch (err) {
      MC.showToast(`Delete failed: ${err.message}`, 'danger');
    }
  },

  async deleteExpiredFlags() {
    try {
      const result = await MC.api('/logs/trace-flags/delete-expired', 'DELETE');
      const count = result ? result.deleted_count : 0;
      MC.showToast(`Deleted ${count} expired trace flag${count !== 1 ? 's' : ''}`, 'success');
      await this.loadTraceFlags();
    } catch (err) {
      MC.showToast(`Delete expired failed: ${err.message}`, 'danger');
    }
  },

  async createTraceFlag() {
    const entityId      = document.getElementById('traceFlagEntityId')?.value.trim();
    const entityType    = document.getElementById('traceFlagEntityType')?.value || 'User';
    const debugLevelId  = document.getElementById('traceFlagDebugLevel')?.value.trim();
    const durationSel   = document.getElementById('traceFlagDuration');
    let duration = parseInt(durationSel?.value, 10);

    // Handle "until midnight" option
    if (durationSel?.options[durationSel.selectedIndex]?.dataset?.dynamic === 'true') {
      const now = new Date();
      const midnight = new Date(now);
      midnight.setHours(24, 0, 0, 0);
      duration = Math.ceil((midnight - now) / 60000);
    }

    if (!entityId) {
      MC.showToast('Please select a user or class first', 'warning');
      return;
    }
    if (!debugLevelId) {
      MC.showToast('Please select a debug level', 'warning');
      return;
    }

    try {
      await MC.api('/logs/trace-flags', 'POST', {
        entity_id: entityId,
        entity_type: entityType,
        debug_level_id: debugLevelId,
        duration_minutes: duration,
      });
      MC.showToast('Trace flag created successfully', 'success');
      await this.loadTraceFlags();
    } catch (err) {
      MC.showToast(`Create failed: ${err.message}`, 'danger');
    }
  },

  async traceMe() {
    try {
      const [users, levels] = await Promise.all([
        MC.api('/logs/trace-flags/users'),
        MC.api('/logs/trace-flags/debug-levels'),
      ]);
      const user  = users && users.length > 0 ? users[0] : null;
      const level = levels && levels.length > 0 ? levels[0] : null;
      if (!user || !level) {
        MC.showToast('Could not find user or debug level to trace', 'warning');
        return;
      }
      await MC.api('/logs/trace-flags', 'POST', {
        entity_id: user.id,
        entity_type: 'User',
        debug_level_id: level.id,
        duration_minutes: 30,
      });
      MC.showToast('Trace flag active for 30 minutes — logs will appear in Apex Logs tab', 'success');
      await this.loadTraceFlags();
    } catch (err) {
      MC.showToast(`Trace Me failed: ${err.message}`, 'danger');
    }
  },

  async _populateUserDatalist(search) {
    try {
      const url = search ? `/logs/trace-flags/users?q=${encodeURIComponent(search)}` : '/logs/trace-flags/users';
      const users = await MC.api(url);
      const dl = document.getElementById('traceFlagUserList');
      if (dl && users) {
        dl.innerHTML = users.map(u =>
          `<option value="${MC._escHtml(u.name + ' <' + u.username + '>')}" data-id="${MC._escHtml(u.id)}">`
        ).join('');
      }
    } catch (_) {
      // ignore datalist population errors silently
    }
  },
};
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
              <span class="fw-semibold small" style="color:var(--doane-slate);">${MC._escHtml(lim.name)}</span>
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
};
'use strict';

MC.impact = {
  _assertionIdx: 0,

  init() {
    document.getElementById('btnFieldScan')?.addEventListener('click', () => this.scanField());
    document.getElementById('btnPermAudit')?.addEventListener('click', () => this.loadPermissions());
    document.getElementById('btnNewSuite')?.addEventListener('click', () => this.showNewSuiteModal());
    document.getElementById('btnAddAssertion')?.addEventListener('click', () => this.addAssertion());
    document.getElementById('btnSaveSuite')?.addEventListener('click', () => this.saveSuite());

    document.getElementById('permFilter')?.addEventListener('input', (e) => {
      this._filterPermTable(e.target.value);
    });

    // Load regression suites on tab activate
    document.getElementById('tab-regression-btn')?.addEventListener('shown.bs.tab', () => {
      this.listSuites();
    });

    this.listSuites();
  },

  // ── Field Impact ───────────────────────────────────────────────────────────

  async scanField() {
    const object = document.getElementById('fieldScanObject')?.value.trim();
    const field = document.getElementById('fieldScanField')?.value.trim();
    if (!object || !field) {
      MC.showToast('Enter both Object and Field name', 'warning');
      return;
    }

    document.getElementById('fieldScanEmpty')?.classList.add('d-none');
    document.getElementById('fieldScanResults')?.classList.add('d-none');
    document.getElementById('fieldScanLoading')?.classList.remove('d-none');

    try {
      const data = await MC.api(`/impact/field-scan?object=${encodeURIComponent(object)}&field=${encodeURIComponent(field)}`);
      this._renderFieldScan(data, field);
    } catch (err) {
      MC.showToast(`Scan failed: ${err.message}`, 'danger');
      document.getElementById('fieldScanEmpty')?.classList.remove('d-none');
    } finally {
      document.getElementById('fieldScanLoading')?.classList.add('d-none');
    }
  },

  _renderFieldScan(data, field) {
    const vr = data.validation_rules || [];
    const flows = data.flows || [];
    const reportsCount = data.reports_count || 0;

    document.getElementById('fieldScanSummary').textContent = data.summary || '';
    document.getElementById('vrCount').textContent = vr.length;
    document.getElementById('flowCount').textContent = flows.length;
    document.getElementById('reportCount').textContent = reportsCount;
    const flowRef = document.getElementById('flowFieldRef');
    if (flowRef) flowRef.textContent = field;

    // Validation rules table
    const vrBody = document.getElementById('vrTableBody');
    if (vrBody) {
      if (vr.length) {
        document.getElementById('vrEmpty')?.classList.add('d-none');
        vrBody.innerHTML = vr.map(r => `
          <tr>
            <td class="font-monospace small">${MC._escHtml(r.EntityDefinition?.QualifiedApiName || '')}</td>
            <td class="small">${MC._escHtml(r.ValidationName || '')}</td>
            <td class="small">${MC._escHtml(r.Description || '')}</td>
            <td class="small">${MC._escHtml(r.ErrorMessage || '')}</td>
          </tr>`).join('');
      } else {
        vrBody.innerHTML = '';
        document.getElementById('vrEmpty')?.classList.remove('d-none');
      }
    }

    // Flows table
    const flowBody = document.getElementById('flowTableBody');
    if (flowBody) {
      if (flows.length) {
        document.getElementById('flowEmpty')?.classList.add('d-none');
        flowBody.innerHTML = flows.map(f => `
          <tr>
            <td class="small">${MC._escHtml(f.MasterLabel || '')}</td>
            <td class="small">${MC._escHtml(f.ProcessType || '')}</td>
            <td class="small">${MC._escHtml(f.Description || '')}</td>
          </tr>`).join('');
      } else {
        flowBody.innerHTML = '';
        document.getElementById('flowEmpty')?.classList.remove('d-none');
      }
    }

    document.getElementById('fieldScanResults')?.classList.remove('d-none');
  },

  // ── Permission Audit ───────────────────────────────────────────────────────

  async loadPermissions() {
    const object = document.getElementById('permObject')?.value.trim();
    const field = document.getElementById('permField')?.value.trim();
    if (!object) {
      MC.showToast('Enter an object name', 'warning');
      return;
    }

    document.getElementById('permEmpty')?.classList.add('d-none');
    document.getElementById('permResults')?.classList.add('d-none');
    document.getElementById('permFieldResults')?.classList.add('d-none');
    document.getElementById('permLoading')?.classList.remove('d-none');

    try {
      const data = await MC.api(`/impact/permissions?object=${encodeURIComponent(object)}`);
      this._renderPermissions(data);

      if (field) {
        await this.loadFieldAccess(object, field);
      }
    } catch (err) {
      MC.showToast(`Audit failed: ${err.message}`, 'danger');
      document.getElementById('permEmpty')?.classList.remove('d-none');
    } finally {
      document.getElementById('permLoading')?.classList.add('d-none');
    }
  },

  _renderPermissions(data) {
    const raw = data.raw_records || [];
    const grouped = {};
    for (const rec of raw) {
      const field = rec.Field || '';
      if (!grouped[field]) grouped[field] = { read: [], edit: [] };
      if (rec.PermissionsRead) grouped[field].read.push(rec.Id);
      if (rec.PermissionsEdit) grouped[field].edit.push(rec.Id);
    }

    const rows = Object.entries(grouped);
    const body = document.getElementById('permTableBody');
    if (body) {
      body.innerHTML = rows.map(([field, perms]) => `
        <tr data-field="${MC._escHtml(field)}">
          <td class="font-monospace small">${MC._escHtml(field)}</td>
          <td class="small">${perms.read.length > 0 ? perms.read.length + ' pset(s)' : '<span class="text-muted">None</span>'}</td>
          <td class="small">${perms.edit.length > 0 ? perms.edit.length + ' pset(s)' : '<span class="text-muted">None</span>'}</td>
        </tr>`).join('');
    }

    const countEl = document.getElementById('permResultCount');
    if (countEl) countEl.textContent = `${rows.length} field(s)`;

    document.getElementById('permResults')?.classList.remove('d-none');
  },

  _filterPermTable(term) {
    const lower = term.toLowerCase();
    document.querySelectorAll('#permTableBody tr').forEach(row => {
      const field = (row.dataset.field || '').toLowerCase();
      row.style.display = field.includes(lower) ? '' : 'none';
    });
  },

  async loadFieldAccess(object, field) {
    try {
      const data = await MC.api(
        `/impact/permissions/field?object=${encodeURIComponent(object)}&field=${encodeURIComponent(field)}`
      );
      this._renderFieldAccess(data, field);
    } catch (err) {
      MC.showToast(`Field access lookup failed: ${err.message}`, 'danger');
    }
  },

  _renderFieldAccess(data, field) {
    const label = document.getElementById('permFieldLabel');
    if (label) label.textContent = field;

    const body = document.getElementById('permFieldTableBody');
    const access = data.access || [];
    if (body) {
      if (access.length) {
        body.innerHTML = access.map(a => {
          const users = (a.users || []).map(u => MC._escHtml(u.username || u.name || '')).join(', ') || '—';
          return `
            <tr>
              <td class="small font-monospace">${MC._escHtml(a.pset_name || a.pset_id || '')}</td>
              <td class="text-center">${a.can_read ? '&#10003;' : ''}</td>
              <td class="text-center">${a.can_edit ? '&#10003;' : ''}</td>
              <td class="small">${users}</td>
            </tr>`;
        }).join('');
      } else {
        body.innerHTML = '<tr><td colspan="4" class="text-center text-muted small py-2">No explicit field permissions found.</td></tr>';
      }
    }
    document.getElementById('permFieldResults')?.classList.remove('d-none');
  },

  // ── Regression Tester ──────────────────────────────────────────────────────

  async listSuites() {
    document.getElementById('regLoading')?.classList.remove('d-none');
    document.getElementById('regEmpty')?.classList.add('d-none');
    document.getElementById('regSuiteList')?.classList.add('d-none');

    try {
      const suites = await MC.api('/impact/regression');
      this._renderSuiteList(suites || []);
    } catch (_) {
      // DB may not be available in dev — show empty state
      this._renderSuiteList([]);
    } finally {
      document.getElementById('regLoading')?.classList.add('d-none');
    }
  },

  _renderSuiteList(suites) {
    const body = document.getElementById('regSuiteTable');
    if (!body) return;

    if (!suites || suites.length === 0) {
      document.getElementById('regEmpty')?.classList.remove('d-none');
      return;
    }

    body.innerHTML = suites.map(s => {
      const assertions = Array.isArray(s.assertions) ? s.assertions : [];
      const hasBaseline = s.baseline && Object.keys(s.baseline).length > 0;
      return `
        <tr>
          <td class="small fw-semibold">${MC._escHtml(s.name)}</td>
          <td class="small text-center">${assertions.length}</td>
          <td class="small">${MC._fmtTime(s.created_at)}</td>
          <td class="small">${hasBaseline ? '<span class="badge badge-green">Set</span>' : '<span class="badge badge-amber">None</span>'}</td>
          <td class="no-print">
            <button class="btn btn-outline-secondary btn-sm me-1"
                    onclick="MC.impact.runSuite(${s.id})">Run</button>
            <button class="btn btn-outline-secondary btn-sm"
                    onclick="MC.impact.setBaseline(${s.id}, '${MC._escHtml(s.name)}')">Set Baseline</button>
          </td>
        </tr>`;
    }).join('');

    document.getElementById('regSuiteList')?.classList.remove('d-none');
  },

  async runSuite(id) {
    MC.showSpinner();
    document.getElementById('regRunResults')?.classList.add('d-none');
    try {
      const data = await MC.api(`/impact/regression/${id}/run`, 'POST');
      this._renderRunResults(data);
      MC.showToast(`Suite run complete: ${data.summary?.pass}/${data.summary?.total} passed`, 'info');
    } catch (err) {
      MC.showToast(`Run failed: ${err.message}`, 'danger');
    } finally {
      MC.hideSpinner();
    }
  },

  _renderRunResults(data) {
    const nameEl = document.getElementById('regRunSuiteName');
    if (nameEl) nameEl.textContent = data.suite_name || '';

    const summaryEl = document.getElementById('regRunSummary');
    if (summaryEl) {
      const s = data.summary || {};
      summaryEl.innerHTML = `${s.pass ?? 0} pass / ${s.fail ?? 0} fail / ${s.error ?? 0} error`;
    }

    const body = document.getElementById('regRunTable');
    if (body) {
      const results = data.results || [];
      body.innerHTML = results.map(r => {
        const statusBadge = MC.statusBadge(r.status);
        const baseline = r.baseline_count != null ? r.baseline_count : '—';
        const actual = r.actual_count != null ? r.actual_count : r.error || '—';
        return `
          <tr>
            <td class="small fw-semibold">${MC._escHtml(r.label)}</td>
            <td class="font-monospace small" style="max-width:260px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap"
                title="${MC._escHtml(r.soql)}">${MC._escHtml(r.soql)}</td>
            <td class="small text-center">${baseline}</td>
            <td class="small text-center">${MC._escHtml(String(actual))}</td>
            <td>${statusBadge}</td>
          </tr>`;
      }).join('');
    }

    // Switch to regression tab and show results
    const tabEl = document.getElementById('tab-regression-btn');
    if (tabEl) bootstrap.Tab.getOrCreateInstance(tabEl).show();
    document.getElementById('regRunResults')?.classList.remove('d-none');
    document.getElementById('regRunResults')?.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  },

  async setBaseline(id, name) {
    if (!confirm(`Set current query counts as baseline for suite "${name}"?`)) return;
    MC.showSpinner();
    try {
      await MC.api(`/impact/regression/${id}/baseline`, 'POST');
      MC.showToast('Baseline saved', 'success');
      this.listSuites();
    } catch (err) {
      MC.showToast(`Baseline failed: ${err.message}`, 'danger');
    } finally {
      MC.hideSpinner();
    }
  },

  showNewSuiteModal() {
    this._assertionIdx = 0;
    const list = document.getElementById('assertionList');
    if (list) list.innerHTML = '';
    const nameInput = document.getElementById('newSuiteName');
    if (nameInput) nameInput.value = '';
    this.addAssertion();
    const modal = document.getElementById('newSuiteModal');
    if (modal) bootstrap.Modal.getOrCreateInstance(modal).show();
  },

  addAssertion() {
    const idx = this._assertionIdx++;
    const list = document.getElementById('assertionList');
    if (!list) return;
    const div = document.createElement('div');
    div.className = 'border rounded p-2 mb-2 position-relative';
    div.dataset.idx = idx;
    div.innerHTML = `
      <button type="button" class="btn-close position-absolute top-0 end-0 m-1"
              onclick="this.closest('[data-idx]').remove()" aria-label="Remove"></button>
      <div class="row g-2">
        <div class="col-sm-4">
          <label class="form-label small fw-semibold">Label</label>
          <input type="text" class="form-control form-control-sm assertion-label"
                 placeholder="e.g. PersonAccount count">
        </div>
        <div class="col-sm-5">
          <label class="form-label small fw-semibold">SOQL (COUNT query)</label>
          <input type="text" class="form-control form-control-sm assertion-soql font-monospace"
                 placeholder="SELECT COUNT() FROM Account WHERE IsPersonAccount = true">
        </div>
        <div class="col-sm-3">
          <label class="form-label small fw-semibold">Expected Count <span class="text-muted">(opt)</span></label>
          <input type="number" class="form-control form-control-sm assertion-expected"
                 placeholder="Leave blank to use baseline">
        </div>
      </div>`;
    list.appendChild(div);
  },

  async saveSuite() {
    const name = document.getElementById('newSuiteName')?.value.trim();
    if (!name) {
      MC.showToast('Suite name is required', 'warning');
      return;
    }
    const assertions = [];
    document.querySelectorAll('#assertionList [data-idx]').forEach(row => {
      const label = row.querySelector('.assertion-label')?.value.trim();
      const soql = row.querySelector('.assertion-soql')?.value.trim();
      const expectedRaw = row.querySelector('.assertion-expected')?.value.trim();
      if (label && soql) {
        assertions.push({
          label,
          soql,
          expected_count: expectedRaw !== '' ? parseInt(expectedRaw, 10) : null,
        });
      }
    });
    if (!assertions.length) {
      MC.showToast('Add at least one assertion', 'warning');
      return;
    }
    try {
      await MC.api('/impact/regression', 'POST', { name, assertions });
      bootstrap.Modal.getOrCreateInstance(document.getElementById('newSuiteModal')).hide();
      MC.showToast('Suite saved', 'success');
      this.listSuites();
    } catch (err) {
      MC.showToast(`Save failed: ${err.message}`, 'danger');
    }
  },
};
'use strict';

// ── Admin ─────────────────────────────────────────────────────────────────────
// Paste this object into mission-control.js after the last MC.* namespace block.

MC.admin = {
  _users: [],

  init() {
    document.getElementById('btnRefreshJobs')?.addEventListener('click', () => this.loadScheduledJobs());
    document.getElementById('btnRefreshCoverage')?.addEventListener('click', () => this.loadTestCoverage());
    document.getElementById('btnRefreshDeploys')?.addEventListener('click', () => this.loadDeployHistory());
    document.getElementById('btnRefreshUsers')?.addEventListener('click', () => this.loadUsers());

    document.getElementById('userFilter')?.addEventListener('input', (e) => {
      this._filterUsers(e.target.value.trim().toLowerCase());
    });

    // Load the default (first) tab on init
    this.loadScheduledJobs();

    // Lazy-load other tabs when first shown
    document.getElementById('tab-coverage')?.addEventListener('shown.bs.tab', () => {
      if (!document.getElementById('coverageCard')?.classList.contains('d-none')) return;
      if (!document.getElementById('coverageEmpty')?.classList.contains('d-none')) return;
      this.loadTestCoverage();
    });
    document.getElementById('tab-deploys')?.addEventListener('shown.bs.tab', () => {
      if (!document.getElementById('deploysCard')?.classList.contains('d-none')) return;
      if (!document.getElementById('deploysEmpty')?.classList.contains('d-none')) return;
      this.loadDeployHistory();
    });
    document.getElementById('tab-users')?.addEventListener('shown.bs.tab', () => {
      if (!document.getElementById('usersCard')?.classList.contains('d-none')) return;
      if (!document.getElementById('usersEmpty')?.classList.contains('d-none')) return;
      this.loadUsers();
    });
    document.getElementById('tab-anonymizer-btn')?.addEventListener('shown.bs.tab', () => {
      this.initAnonymizer();
    });
  },

  // ── Scheduled Jobs ──────────────────────────────────────────────────────────

  async loadScheduledJobs() {
    const loading = document.getElementById('jobsLoading');
    const empty   = document.getElementById('jobsEmpty');
    const card    = document.getElementById('jobsCard');
    loading?.classList.remove('d-none');
    empty?.classList.add('d-none');
    card?.classList.add('d-none');
    try {
      const jobs = await MC.api('/admin/scheduled-jobs');
      if (!jobs || jobs.length === 0) {
        empty?.classList.remove('d-none');
        return;
      }
      this._renderJobsTable(jobs);
      card?.classList.remove('d-none');
    } catch (err) {
      MC.showToast(`Failed to load scheduled jobs: ${err.message}`, 'danger');
      empty?.classList.remove('d-none');
    } finally {
      loading?.classList.add('d-none');
    }
  },

  _renderJobsTable(jobs) {
    const tbody = document.getElementById('jobsBody');
    if (!tbody) return;
    tbody.innerHTML = jobs.map(j => {
      const stateBadge = this._jobStateBadge(j.state);
      return `<tr>
        <td class="fw-semibold">${MC._escHtml(j.name)}</td>
        <td class="text-muted small">${MC._escHtml(j.job_type_label)}</td>
        <td>${stateBadge}</td>
        <td class="small">${MC._fmtTime(j.next_fire_time)}</td>
        <td class="text-muted small">${MC._fmtTime(j.previous_fire_time)}</td>
        <td class="text-end small">${MC._escHtml(j.times_triggered)}</td>
        <td><code class="small">${MC._escHtml(j.cron_expression)}</code></td>
      </tr>`;
    }).join('');
  },

  _jobStateBadge(state) {
    const s = (state || '').toUpperCase();
    const cls =
      s === 'WAITING'   ? 'badge-green' :
      s === 'EXECUTING' ? 'badge-green' :
      s === 'PAUSED'    ? 'badge-amber' :
      s === 'ERROR'     ? 'badge-red'   :
      'badge-slate';
    return `<span class="badge ${cls}">${MC._escHtml(s)}</span>`;
  },

  // ── Test Coverage ───────────────────────────────────────────────────────────

  async loadTestCoverage() {
    const loading = document.getElementById('coverageLoading');
    const empty   = document.getElementById('coverageEmpty');
    const card    = document.getElementById('coverageCard');
    const summary = document.getElementById('coverageSummary');
    loading?.classList.remove('d-none');
    empty?.classList.add('d-none');
    card?.classList.add('d-none');
    summary?.classList.add('d-none');
    try {
      const data = await MC.api('/admin/test-coverage');
      const classes = data?.classes || [];
      if (classes.length === 0) {
        empty?.classList.remove('d-none');
        return;
      }
      this._renderCoverageSummary(data.summary || {});
      this._renderCoverageTable(classes);
      card?.classList.remove('d-none');
      summary?.classList.remove('d-none');
    } catch (err) {
      MC.showToast(`Failed to load test coverage: ${err.message}`, 'danger');
      empty?.classList.remove('d-none');
    } finally {
      loading?.classList.add('d-none');
    }
  },

  _renderCoverageSummary(s) {
    const passing = s.passing ?? 0;
    const below   = s.below_threshold ?? 0;
    const failing = s.failing ?? 0;
    const passEl  = document.getElementById('covPassing');
    const belowEl = document.getElementById('covBelow');
    const failEl  = document.getElementById('covFailing');
    if (passEl)  passEl.textContent  = `${passing} passing`;
    if (belowEl) belowEl.textContent = `${below} below 75%`;
    if (failEl)  failEl.textContent  = `${failing} below 50%`;
  },

  _renderCoverageTable(classes) {
    const tbody = document.getElementById('coverageBody');
    if (!tbody) return;
    tbody.innerHTML = classes.map(c => {
      const pct = parseFloat(c.pct) || 0;
      const rowCls =
        pct >= 75 ? '' :
        pct >= 50 ? 'table-warning' :
        'table-danger';
      const barCls =
        pct >= 75 ? 'bg-success' :
        pct >= 50 ? 'bg-warning' :
        'bg-danger';
      const pctStr = `${pct.toFixed(1)}%`;
      return `<tr class="${rowCls}">
        <td class="fw-semibold">${MC._escHtml(c.name)}</td>
        <td class="text-end small">${MC._escHtml(c.num_lines_covered)}</td>
        <td class="text-end small">${MC._escHtml(c.num_lines_uncovered)}</td>
        <td>
          <div class="d-flex align-items-center gap-2">
            <div class="progress flex-grow-1" style="height:10px">
              <div class="progress-bar ${barCls}" role="progressbar"
                   style="width:${pct}%" aria-valuenow="${pct}"
                   aria-valuemin="0" aria-valuemax="100"></div>
            </div>
            <span class="small text-nowrap">${pctStr}</span>
          </div>
        </td>
      </tr>`;
    }).join('');
  },

  // ── Deployment History ──────────────────────────────────────────────────────

  async loadDeployHistory() {
    const loading = document.getElementById('deploysLoading');
    const empty   = document.getElementById('deploysEmpty');
    const card    = document.getElementById('deploysCard');
    loading?.classList.remove('d-none');
    empty?.classList.add('d-none');
    card?.classList.add('d-none');
    try {
      const deploys = await MC.api('/admin/deploy-history');
      if (!deploys || deploys.length === 0) {
        empty?.classList.remove('d-none');
        return;
      }
      this._renderDeploysTable(deploys);
      card?.classList.remove('d-none');
    } catch (err) {
      MC.showToast(`Failed to load deployments: ${err.message}`, 'danger');
      empty?.classList.remove('d-none');
    } finally {
      loading?.classList.add('d-none');
    }
  },

  _renderDeploysTable(deploys) {
    const tbody = document.getElementById('deploysBody');
    if (!tbody) return;
    tbody.innerHTML = deploys.map((d, idx) => {
      const statusBadge = MC.statusBadge(d.status);
      const duration = d.duration_seconds != null ? `${d.duration_seconds}s` : '—';
      const hasErrors = (d.num_component_errors > 0) || (d.num_test_errors > 0);
      const detailId  = `deployDetail-${idx}`;
      const expandBtn = hasErrors
        ? `<button class="btn btn-link btn-sm p-0 ms-1" type="button"
                   data-bs-toggle="collapse" data-bs-target="#${detailId}"
                   aria-expanded="false">detail</button>`
        : '';
      const detailRow = hasErrors && d.state_detail
        ? `<tr id="${detailId}" class="collapse">
             <td colspan="7" class="text-danger small ps-3">
               <code>${MC._escHtml(d.state_detail)}</code>
             </td>
           </tr>`
        : '';
      return `<tr>
        <td class="small">${MC._fmtTime(d.start_date)}</td>
        <td class="small">${MC._escHtml(d.created_by)}</td>
        <td class="text-end small">${MC._escHtml(d.num_components_total)}</td>
        <td class="text-end small ${d.num_component_errors > 0 ? 'text-danger fw-semibold' : ''}">${MC._escHtml(d.num_component_errors)}${expandBtn}</td>
        <td class="text-end small">${MC._escHtml(d.num_tests_completed)}</td>
        <td class="text-end small">${duration}</td>
        <td>${statusBadge}</td>
      </tr>${detailRow}`;
    }).join('');
  },

  // ── User Audit ──────────────────────────────────────────────────────────────

  async loadUsers() {
    const loading = document.getElementById('usersLoading');
    const empty   = document.getElementById('usersEmpty');
    const card    = document.getElementById('usersCard');
    const summary = document.getElementById('usersSummary');
    loading?.classList.remove('d-none');
    empty?.classList.add('d-none');
    card?.classList.add('d-none');
    summary?.classList.add('d-none');
    const filterEl = document.getElementById('userFilter');
    if (filterEl) filterEl.value = '';
    try {
      const data = await MC.api('/admin/users');
      this._users = data?.users || [];
      if (this._users.length === 0) {
        empty?.classList.remove('d-none');
        return;
      }
      this._renderUserSummary(data.summary || {});
      this._renderUsersTable(this._users);
      card?.classList.remove('d-none');
      summary?.classList.remove('d-none');
    } catch (err) {
      MC.showToast(`Failed to load user audit: ${err.message}`, 'danger');
      empty?.classList.remove('d-none');
    } finally {
      loading?.classList.add('d-none');
    }
  },

  _renderUserSummary(s) {
    const activeEl    = document.getElementById('sumActive');
    const inactive90El= document.getElementById('sumInactive90');
    const neverEl     = document.getElementById('sumNeverLogin');
    const sysEl       = document.getElementById('sumSysadmins');
    if (activeEl)     activeEl.textContent     = s.total_active ?? '—';
    if (inactive90El) inactive90El.textContent = s.inactive_90d ?? '—';
    if (neverEl)      neverEl.textContent      = s.never_logged_in ?? '—';
    if (sysEl)        sysEl.textContent        = s.sysadmins ?? '—';
  },

  _renderUsersTable(users) {
    const tbody = document.getElementById('usersBody');
    if (!tbody) return;
    tbody.innerHTML = users.map(u => {
      const rowCls =
        !u.is_active        ? 'text-muted'    :
        u.flag === 'never_logged_in' ? 'table-danger'  :
        u.flag === 'inactive_90d'    ? 'table-warning' :
        '';
      const loginText = u.last_login_date ? MC._fmtTime(u.last_login_date) : 'Never';
      const statusBadge = u.is_active
        ? (u.flag === 'never_logged_in' ? '<span class="badge badge-red">NEVER</span>'
         : u.flag === 'inactive_90d'    ? '<span class="badge badge-amber">STALE</span>'
         :                               '<span class="badge badge-green">ACTIVE</span>')
        : '<span class="badge badge-slate">INACTIVE</span>';
      return `<tr class="${rowCls}">
        <td>${MC._escHtml(u.name)}</td>
        <td class="small text-muted"><code>${MC._escHtml(u.username)}</code></td>
        <td class="small">${MC._escHtml(u.profile_name)}</td>
        <td class="small">${loginText}</td>
        <td>${statusBadge}</td>
      </tr>`;
    }).join('');
  },

  _filterUsers(q) {
    if (!q) {
      this._renderUsersTable(this._users);
      return;
    }
    const filtered = this._users.filter(u =>
      (u.name || '').toLowerCase().includes(q) ||
      (u.username || '').toLowerCase().includes(q)
    );
    this._renderUsersTable(filtered);
  },

  // ── Anonymizer ─────────────────────────────────────────────────────────────

  async initAnonymizer() {
    try {
      const objects = await MC.api('/admin/anonymizer/objects');
      const sel = document.getElementById('anonObjectSelect');
      if (sel) {
        (objects || []).forEach(o => {
          const opt = document.createElement('option');
          opt.value = o.object;
          opt.textContent = o.object;
          opt.dataset.fields = JSON.stringify(o.fields);
          sel.appendChild(opt);
        });
        sel.addEventListener('change', () => this._renderAnonFields(sel));
      }
    } catch (err) {
      MC.showToast(`Failed to load anonymizer objects: ${err.message}`, 'danger');
    }
    document.getElementById('btnAnonPreview')?.addEventListener('click', () => this.anonPreview());
    document.getElementById('btnAnonRun')?.addEventListener('click', () => this.anonRun());
  },

  _renderAnonFields(sel) {
    const fields = JSON.parse(sel.selectedOptions[0]?.dataset.fields || '[]');
    const wrap = document.getElementById('anonFieldsList');
    if (!wrap) return;
    if (!fields.length) {
      wrap.innerHTML = '<span class="text-muted small">No fields available</span>';
      return;
    }
    wrap.innerHTML = fields.map(f => `
      <div class="form-check">
        <input class="form-check-input anon-field-check" type="checkbox"
               id="anonField_${MC._escHtml(f)}" value="${MC._escHtml(f)}" checked>
        <label class="form-check-label small font-monospace" for="anonField_${MC._escHtml(f)}">${MC._escHtml(f)}</label>
      </div>`).join('');
    document.getElementById('btnAnonRun').disabled = false;
  },

  _getAnonSelection() {
    const object = document.getElementById('anonObjectSelect')?.value;
    const fields = Array.from(document.querySelectorAll('.anon-field-check:checked')).map(el => el.value);
    return { object, fields };
  },

  async anonPreview() {
    const { object, fields } = this._getAnonSelection();
    if (!object) { MC.showToast('Select an object first', 'warning'); return; }
    try {
      const data = await MC.api('/admin/anonymizer/preview', 'POST', { object, fields });
      document.getElementById('anonRecordCount').textContent = (data.record_count || 0).toLocaleString();
      document.getElementById('anonPreviewObject').textContent = data.object || object;
      document.getElementById('anonPreviewFields').textContent = (data.fields || fields).join(', ');
      document.getElementById('anonPreviewSoql').textContent = data.soql || '';
      document.getElementById('anonPreviewWrap')?.classList.remove('d-none');
      document.getElementById('anonResultWrap')?.classList.add('d-none');
    } catch (err) {
      MC.showToast(`Preview failed: ${err.message}`, 'danger');
    }
  },

  async anonRun() {
    const { object, fields } = this._getAnonSelection();
    const dryRun = document.getElementById('anonDryRun')?.checked ?? true;
    if (!object || !fields.length) { MC.showToast('Select object and at least one field', 'warning'); return; }
    if (!dryRun && !confirm(`Run LIVE anonymization on ${object}? This modifies real data.`)) return;
    MC.showSpinner();
    try {
      const data = await MC.api('/admin/anonymizer/run', 'POST', { object, fields, dry_run: dryRun });
      const alertEl = document.getElementById('anonResultAlert');
      if (alertEl) {
        alertEl.className = `alert py-2 small mb-0 alert-${data.status === 'stub' || data.status === 'dry_run' ? 'info' : 'success'}`;
        alertEl.textContent = data.message || JSON.stringify(data);
      }
      document.getElementById('anonResultWrap')?.classList.remove('d-none');
    } catch (err) {
      MC.showToast(`Run failed: ${err.message}`, 'danger');
    } finally {
      MC.hideSpinner();
    }
  },
};
'use strict';

// ── Deploy — Change Set Builder ───────────────────────────────────────────────
// Paste this object into mission-control.js after the last MC.* namespace block.

MC.deploy = {

  // Map<member, {type, member, label}> — source of truth for selected components
  _selected: new Map(),

  // Tracks which types have already been loaded (avoids redundant fetches)
  _loaded: new Set(),

  // Setup navigation paths shown in the checklist "Setup Path" column
  _setupPaths: {
    ApexClass:      'Setup → Apex Classes',
    ApexTrigger:    'Setup → Apex Classes (Triggers tab)',
    CustomField:    'Setup → Object Manager → {object} → Fields & Relationships',
    Flow:           'Setup → Flows',
    PermissionSet:  'Setup → Permission Sets',
    ValidationRule: 'Setup → Object Manager → {object} → Validation Rules',
  },

  // ── Bootstrap ────────────────────────────────────────────────────────────────

  init() {
    // "Load <Type>" buttons
    document.querySelectorAll('.deploy-load-btn').forEach(btn => {
      btn.addEventListener('click', () => this.loadType(btn.dataset.type));
    });

    // "Select All" links
    document.querySelectorAll('.deploy-select-all-link').forEach(a => {
      a.addEventListener('click', (e) => {
        e.preventDefault();
        this._selectAll(a.dataset.type);
      });
    });

    // "Clear" links
    document.querySelectorAll('.deploy-clear-link').forEach(a => {
      a.addEventListener('click', (e) => {
        e.preventDefault();
        this._clearType(a.dataset.type);
      });
    });

    // Filter inputs (client-side, no re-query)
    document.querySelectorAll('.deploy-filter-input').forEach(input => {
      input.addEventListener('input', () => {
        this._applyFilter(input.dataset.type, input.value.trim().toLowerCase());
      });
    });

    // Generate button
    document.getElementById('btnGenerate')?.addEventListener('click', () => this.generate());

    // Copy / Download / Print
    document.getElementById('btnCopyXml')?.addEventListener('click', () => this.copyXml());
    document.getElementById('btnDownloadXml')?.addEventListener('click', () => {
      const xml = document.getElementById('packageXmlPre')?.textContent || '';
      this.downloadXml(xml);
    });
    document.getElementById('btnPrint')?.addEventListener('click', () => this.printChecklist());

    // Lazy-load on tab shown
    document.querySelectorAll('#typeTabs button[data-deploy-type]').forEach(btn => {
      btn.addEventListener('shown.bs.tab', () => {
        const type = btn.dataset.deployType;
        if (!this._loaded.has(type)) {
          this.loadType(type);
        }
      });
    });

    // Auto-load the first tab (ApexClass) on page open
    this.loadType('ApexClass');
  },

  // ── Data loading ─────────────────────────────────────────────────────────────

  async loadType(type) {
    const loadingEl = document.getElementById(`loading-${type}`);
    const emptyEl   = document.getElementById(`empty-${type}`);
    const listEl    = document.getElementById(`list-${type}`);
    const filterEl  = document.querySelector(`.deploy-filter-input[data-type="${type}"]`);

    loadingEl?.classList.remove('d-none');
    emptyEl?.classList.add('d-none');
    if (listEl) listEl.style.display = 'none';

    try {
      const components = await MC.api(`/deploy/components?type=${encodeURIComponent(type)}`);
      if (!components || components.length === 0) {
        emptyEl?.classList.remove('d-none');
        this._loaded.add(type);
        return;
      }
      this._renderComponentList(type, components);
      if (listEl) listEl.style.display = '';
      if (filterEl) filterEl.style.display = '';
      this._loaded.add(type);
    } catch (err) {
      MC.showToast(`Failed to load ${type}: ${err.message}`, 'danger');
      emptyEl?.classList.remove('d-none');
    } finally {
      loadingEl?.classList.add('d-none');
    }
  },

  // ── Rendering ────────────────────────────────────────────────────────────────

  _renderComponentList(type, components) {
    const listEl = document.getElementById(`list-${type}`);
    if (!listEl) return;

    listEl.innerHTML = components.map(c => {
      const isChecked = this._selected.has(c.member) ? 'checked' : '';
      const safeId = `chk-${type}-${MC._escHtml(c.member).replace(/[^a-zA-Z0-9]/g, '_')}`;
      return `<div class="form-check border-bottom py-1 px-2 deploy-item" data-member="${MC._escHtml(c.member)}">
        <input class="form-check-input deploy-checkbox" type="checkbox"
               id="${safeId}"
               data-type="${MC._escHtml(type)}"
               data-member="${MC._escHtml(c.member)}"
               data-label="${MC._escHtml(c.label)}"
               ${isChecked}>
        <label class="form-check-label small w-100" for="${safeId}" style="cursor:pointer">
          ${MC._escHtml(c.label)}
        </label>
      </div>`;
    }).join('');

    // Wire checkbox change events
    listEl.querySelectorAll('.deploy-checkbox').forEach(cb => {
      cb.addEventListener('change', () => this._onCheckboxChange(cb));
    });
  },

  _onCheckboxChange(cb) {
    const { type, member, label } = cb.dataset;
    if (cb.checked) {
      this._selected.set(member, { type, member, label });
    } else {
      this._selected.delete(member);
    }
    this._updateSelection();
  },

  _updateSelection() {
    const count = this._selected.size;
    const countEl = document.getElementById('selectedCount');
    if (countEl) countEl.textContent = count;

    const btn = document.getElementById('btnGenerate');
    if (btn) btn.disabled = (count === 0);

    const listEl   = document.getElementById('selectionList');
    const emptyEl  = document.getElementById('selectionEmpty');
    if (!listEl) return;

    if (count === 0) {
      listEl.innerHTML = '';
      if (emptyEl) {
        emptyEl.style.display = '';
        listEl.appendChild(emptyEl);
      }
      return;
    }

    // Group by type for display
    const byType = {};
    for (const [, item] of this._selected) {
      if (!byType[item.type]) byType[item.type] = [];
      byType[item.type].push(item);
    }

    const _ORDER = ['ApexClass', 'ApexTrigger', 'CustomField', 'Flow', 'PermissionSet', 'ValidationRule'];
    let html = '';
    for (const type of _ORDER) {
      const items = byType[type];
      if (!items) continue;
      html += `<div class="list-group-item list-group-item-secondary px-2 py-1">
        <small class="fw-semibold text-uppercase">${MC._escHtml(type)}</small>
      </div>`;
      for (const item of items) {
        html += `<div class="list-group-item d-flex justify-content-between align-items-center px-2 py-1">
          <span class="small text-truncate me-2" style="max-width:80%" title="${MC._escHtml(item.label)}">${MC._escHtml(item.label)}</span>
          <button type="button" class="btn-close btn-sm flex-shrink-0 deploy-remove-btn"
                  data-member="${MC._escHtml(item.member)}" aria-label="Remove"></button>
        </div>`;
      }
    }
    listEl.innerHTML = html;

    // Wire remove buttons
    listEl.querySelectorAll('.deploy-remove-btn').forEach(btn => {
      btn.addEventListener('click', () => this._removeItem(btn.dataset.member));
    });
  },

  _removeItem(member) {
    this._selected.delete(member);
    // Uncheck the corresponding checkbox if visible
    const cb = document.querySelector(`.deploy-checkbox[data-member="${CSS.escape(member)}"]`);
    if (cb) cb.checked = false;
    this._updateSelection();
  },

  // ── Select All / Clear ───────────────────────────────────────────────────────

  _selectAll(type) {
    const listEl = document.getElementById(`list-${type}`);
    if (!listEl) return;
    listEl.querySelectorAll('.deploy-checkbox').forEach(cb => {
      if (!cb.closest('.deploy-item').classList.contains('d-none')) {
        cb.checked = true;
        this._selected.set(cb.dataset.member, {
          type: cb.dataset.type,
          member: cb.dataset.member,
          label: cb.dataset.label,
        });
      }
    });
    this._updateSelection();
  },

  _clearType(type) {
    const listEl = document.getElementById(`list-${type}`);
    if (!listEl) return;
    listEl.querySelectorAll('.deploy-checkbox').forEach(cb => {
      cb.checked = false;
      this._selected.delete(cb.dataset.member);
    });
    this._updateSelection();
  },

  // ── Client-side filter ───────────────────────────────────────────────────────

  _applyFilter(type, q) {
    const listEl = document.getElementById(`list-${type}`);
    if (!listEl) return;
    listEl.querySelectorAll('.deploy-item').forEach(item => {
      const label = (item.querySelector('label')?.textContent || '').toLowerCase();
      if (!q || label.includes(q)) {
        item.classList.remove('d-none');
      } else {
        item.classList.add('d-none');
      }
    });
  },

  // ── Generate ─────────────────────────────────────────────────────────────────

  async generate() {
    if (this._selected.size === 0) return;

    const btn = document.getElementById('btnGenerate');
    const origText = btn?.textContent || 'Generate Package';
    if (btn) { btn.disabled = true; btn.textContent = 'Generating…'; }

    const components = Array.from(this._selected.values()).map(({ type, member }) => ({ type, member }));

    try {
      const data = await MC.api('/deploy/generate', 'POST', { components });
      this._renderOutput(data);
      document.getElementById('outputArea')?.classList.remove('d-none');
      document.getElementById('outputArea')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
    } catch (err) {
      MC.showToast(`Generate failed: ${err.message}`, 'danger');
    } finally {
      if (btn) { btn.disabled = (this._selected.size === 0); btn.textContent = origText; }
    }
  },

  _renderOutput(data) {
    // package.xml
    const xmlEl = document.getElementById('packageXmlPre');
    if (xmlEl) xmlEl.textContent = data.package_xml || '';

    // Checklist table
    const tbody = document.getElementById('checklistBody');
    if (!tbody) return;
    const checklist = data.checklist || [];
    let html = '';
    for (const group of checklist) {
      for (const item of group.members) {
        html += `<tr>
          <td class="small fw-semibold">${MC._escHtml(group.type_label)}</td>
          <td class="small"><code>${MC._escHtml(item.member)}</code></td>
          <td class="small text-muted">${MC._escHtml(item.setup_path)}</td>
        </tr>`;
      }
    }
    tbody.innerHTML = html || '<tr><td colspan="3" class="text-muted text-center">No components</td></tr>';
  },

  // ── Clipboard / Download / Print ─────────────────────────────────────────────

  copyXml() {
    const xml = document.getElementById('packageXmlPre')?.textContent || '';
    navigator.clipboard.writeText(xml)
      .then(() => MC.showToast('Copied to clipboard', 'success'))
      .catch(() => MC.showToast('Copy failed — please select and copy manually', 'danger'));
  },

  downloadXml(xml) {
    if (!xml) return;
    const blob = new Blob([xml], { type: 'application/xml;charset=utf-8;' });
    const url  = URL.createObjectURL(blob);
    const a    = document.createElement('a');
    a.href     = url;
    a.download = 'package.xml';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  },

  printChecklist() {
    window.print();
  },
};
