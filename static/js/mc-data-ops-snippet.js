'use strict';

// ── Bulk DML module ───────────────────────────────────────────────────────────

MC.bulkDml = {
  _lastPreview: null,

  init() {
    document.getElementById('btnBulkPreview')?.addEventListener('click', () => this.preview());
    document.getElementById('btnBulkExecute')?.addEventListener('click', () => this.execute());
    document.getElementById('bulkDryRun')?.addEventListener('change', (e) => {
      const btn = document.getElementById('btnBulkExecute');
      if (btn) btn.textContent = e.target.checked ? '▶ Execute (Dry Run)' : '▶ Execute (LIVE)';
      if (btn && !e.target.checked) btn.classList.replace('btn-doane', 'btn-danger');
      else if (btn) btn.classList.replace('btn-danger', 'btn-doane');
    });
  },

  async preview() {
    const sobject = document.getElementById('bulkSobject')?.value.trim();
    const whereClause = document.getElementById('bulkWhere')?.value.trim();
    if (!sobject || !whereClause) {
      MC.showToast('SObject name and WHERE clause are required.', 'warning');
      return;
    }

    const btn = document.getElementById('btnBulkPreview');
    if (btn) btn.disabled = true;
    MC.showSpinner();

    try {
      const data = await MC.api('/data-ops/bulk-update/preview', 'POST', {
        sobject,
        where_clause: whereClause,
      });

      this._lastPreview = data;

      // Populate preview panel
      document.getElementById('previewSobject').textContent = data.sobject;
      document.getElementById('previewWhere').textContent = data.where_clause;
      document.getElementById('previewCount').textContent = data.count.toLocaleString();

      // Limit warning
      const limitWarn = document.getElementById('previewLimitWarning');
      if (data.exceeds_limit) {
        limitWarn?.classList.remove('d-none');
      } else {
        limitWarn?.classList.add('d-none');
      }

      // Sample IDs
      const sampleWrap = document.getElementById('previewSampleWrap');
      const sampleBody = document.getElementById('previewSampleBody');
      if (data.sample_ids && data.sample_ids.length > 0) {
        sampleBody.innerHTML = data.sample_ids.map(id => {
          const link = MC.sfLinkHtml(id, data.sobject);
          return `<tr><td><code class="small">${MC._escHtml(id)}</code></td><td>${link}</td></tr>`;
        }).join('');
        sampleWrap?.classList.remove('d-none');
      } else {
        sampleBody.innerHTML = '<tr><td colspan="2" class="text-muted small">No records found.</td></tr>';
        sampleWrap?.classList.remove('d-none');
      }

      // Enable/disable execute button
      const execBtn = document.getElementById('btnBulkExecute');
      if (execBtn) {
        execBtn.disabled = data.count === 0 || data.exceeds_limit;
      }

      // Show preview panel, hide results panel
      document.getElementById('bulkPreviewWrap')?.classList.remove('d-none');
      document.getElementById('bulkResultsWrap')?.classList.add('d-none');

    } catch (err) {
      MC.showToast(`Preview failed: ${err.message}`, 'danger');
    } finally {
      if (btn) btn.disabled = false;
      MC.hideSpinner();
    }
  },

  async execute() {
    const sobject = document.getElementById('bulkSobject')?.value.trim();
    const whereClause = document.getElementById('bulkWhere')?.value.trim();
    const field = document.getElementById('bulkField')?.value.trim();
    const value = document.getElementById('bulkValue')?.value;
    const dryRun = document.getElementById('bulkDryRun')?.checked ?? true;

    if (!sobject || !whereClause || !field) {
      MC.showToast('SObject, WHERE clause, and Field Name are required.', 'warning');
      return;
    }

    if (!dryRun) {
      const confirmed = window.confirm(
        `LIVE execution: update ${field} on all matching ${sobject} records.\n\nThis cannot be undone. Proceed?`
      );
      if (!confirmed) return;
    }

    const btn = document.getElementById('btnBulkExecute');
    if (btn) btn.disabled = true;
    MC.showSpinner();

    try {
      const data = await MC.api('/data-ops/bulk-update/execute', 'POST', {
        sobject,
        where_clause: whereClause,
        field,
        value,
        dry_run: dryRun,
      });

      // Status badge
      const badge = document.getElementById('bulkStatusBadge');
      if (badge) {
        if (data.status === 'dry_run') {
          badge.textContent = 'DRY RUN';
          badge.className = 'badge fs-6 bg-secondary';
        } else if (data.status === 'ok') {
          badge.textContent = 'SUCCESS';
          badge.className = 'badge fs-6 bg-success';
        } else if (data.status === 'partial') {
          badge.textContent = 'PARTIAL';
          badge.className = 'badge fs-6 bg-warning text-dark';
        } else {
          badge.textContent = data.status.toUpperCase();
          badge.className = 'badge fs-6 bg-danger';
        }
      }

      document.getElementById('resultQueried').textContent = (data.records_queried ?? 0).toLocaleString();
      document.getElementById('resultUpdated').textContent = (data.records_updated ?? 0).toLocaleString();
      document.getElementById('resultFailed').textContent = (data.records_failed ?? 0).toLocaleString();

      // Errors table
      const errorsWrap = document.getElementById('bulkErrorsWrap');
      const errorsBody = document.getElementById('bulkErrorsBody');
      if (data.errors && data.errors.length > 0) {
        errorsBody.innerHTML = data.errors.map(e =>
          `<tr><td><code class="small">${MC._escHtml(e.id || '')}</code></td><td class="text-danger small">${MC._escHtml(e.error || '')}</td></tr>`
        ).join('');
        errorsWrap?.classList.remove('d-none');
      } else {
        errorsWrap?.classList.add('d-none');
      }

      document.getElementById('bulkResultsWrap')?.classList.remove('d-none');
      const toastType = data.status === 'ok' ? 'success' : data.status === 'dry_run' ? 'info' : 'warning';
      MC.showToast(
        `${data.status === 'dry_run' ? 'Dry run complete' : 'Execute complete'}: ${(data.records_updated ?? 0).toLocaleString()} updated.`,
        toastType
      );

    } catch (err) {
      MC.showToast(`Execute failed: ${err.message}`, 'danger');
    } finally {
      if (btn) btn.disabled = false;
      MC.hideSpinner();
    }
  },
};

// ── Record Locks module ───────────────────────────────────────────────────────

MC.recordLocks = {

  init() {
    document.getElementById('btnRefreshLocks')?.addEventListener('click', () => this.load());
    document.getElementById('lockObjectFilter')?.addEventListener('change', () => this.load());
    this.load();
  },

  async load() {
    const filter = document.getElementById('lockObjectFilter')?.value || '';
    const url = '/data-ops/api/record-locks' + (filter ? `?object=${encodeURIComponent(filter)}` : '');

    const loading = document.getElementById('lockLoading');
    const resultsWrap = document.getElementById('lockResultsWrap');
    const emptyState = document.getElementById('lockEmptyState');
    const summary = document.getElementById('lockSummary');

    loading?.classList.remove('d-none');
    resultsWrap?.classList.add('d-none');
    emptyState?.classList.add('d-none');
    summary?.classList.add('d-none');

    try {
      const resp = await MC.api(url, 'GET');
      const data = resp;

      // Summary
      const total = data.total_locked ?? 0;
      const objCount = (data.objects_checked ?? []).length;
      const summaryText = document.getElementById('lockSummaryText');
      if (summaryText) {
        summaryText.textContent = `${total.toLocaleString()} record${total !== 1 ? 's' : ''} locked across ${objCount} object${objCount !== 1 ? 's' : ''} checked.`;
      }
      summary?.classList.remove('d-none');

      if (total === 0) {
        emptyState?.classList.remove('d-none');
        loading?.classList.add('d-none');
        return;
      }

      // Build per-object tables
      resultsWrap.innerHTML = '';
      const byObj = data.by_object ?? {};
      const now = Date.now();

      for (const [obj, records] of Object.entries(byObj)) {
        if (!records || records.length === 0) continue;

        const tableHtml = `
          <div class="card shadow-sm mb-3">
            <div class="card-header fw-semibold" style="background-color: var(--doane-navy); color:#fff;">
              ${MC._escHtml(obj)} <span class="badge bg-light text-dark ms-1">${records.length}</span>
            </div>
            <div class="card-body p-0">
              <div class="table-responsive">
                <table class="table table-sm table-striped results-table mb-0">
                  <thead>
                    <tr>
                      <th>ProcessInstance ID</th>
                      <th>Target Record ID</th>
                      <th>Created Date</th>
                      <th>Days Pending</th>
                      <th>Status</th>
                    </tr>
                  </thead>
                  <tbody>
                    ${records.map(r => {
                      const created = r.CreatedDate ? new Date(r.CreatedDate) : null;
                      const daysPending = created ? Math.floor((now - created.getTime()) / 86400000) : '—';
                      const createdStr = created ? created.toLocaleDateString() : '—';
                      const sfLink = r.TargetObjectId
                        ? MC.sfLinkHtml(r.TargetObjectId, obj)
                        : MC._escHtml(r.TargetObjectId || '');
                      return `<tr>
                        <td><code class="small">${MC._escHtml(r.Id || '')}</code></td>
                        <td>${sfLink}</td>
                        <td>${createdStr}</td>
                        <td>${typeof daysPending === 'number' ? daysPending : daysPending}</td>
                        <td><span class="badge bg-warning text-dark">${MC._escHtml(r.Status || '')}</span></td>
                      </tr>`;
                    }).join('')}
                  </tbody>
                </table>
              </div>
            </div>
          </div>`;
        resultsWrap.insertAdjacentHTML('beforeend', tableHtml);
      }

      resultsWrap?.classList.remove('d-none');

    } catch (err) {
      MC.showToast(`Record locks failed: ${err.message}`, 'danger');
    } finally {
      loading?.classList.add('d-none');
    }
  },
};

// ── Bulk Jobs module ──────────────────────────────────────────────────────────

MC.bulkJobs = {
  _timer: null,

  init() {
    document.getElementById('btnRefreshBulkJobs')?.addEventListener('click', () => this.load());
    document.getElementById('bulkJobsAutoRefresh')?.addEventListener('change', (e) => {
      this._setAutoRefresh(e.target.checked);
    });
    this.load();
  },

  async load() {
    const loading = document.getElementById('bulkJobsLoading');
    const tableWrap = document.getElementById('bulkJobsTableWrap');
    const emptyState = document.getElementById('bulkJobsEmpty');
    const summary = document.getElementById('bulkJobsSummary');

    loading?.classList.remove('d-none');
    tableWrap?.classList.add('d-none');
    emptyState?.classList.add('d-none');

    try {
      const resp = await MC.api('/data-ops/api/bulk-jobs', 'GET');
      const jobs = resp;

      // Summary stats
      const totalJobs = jobs.length;
      const totalProcessed = jobs.reduce((s, j) => s + (j.numberRecordsProcessed ?? 0), 0);
      const totalFailed = jobs.reduce((s, j) => s + (j.numberRecordsFailed ?? 0), 0);
      const inProgress = jobs.filter(j => j.state === 'InProgress').length;

      const bjTotalJobs = document.getElementById('bjTotalJobs');
      const bjTotalProcessed = document.getElementById('bjTotalProcessed');
      const bjTotalFailed = document.getElementById('bjTotalFailed');
      const bjInProgress = document.getElementById('bjInProgress');

      if (bjTotalJobs) bjTotalJobs.textContent = totalJobs.toLocaleString();
      if (bjTotalProcessed) bjTotalProcessed.textContent = totalProcessed.toLocaleString();
      if (bjTotalFailed) bjTotalFailed.textContent = totalFailed.toLocaleString();
      if (bjInProgress) bjInProgress.textContent = inProgress.toLocaleString();
      summary?.classList.remove('d-none');

      const countEl = document.getElementById('bulkJobsCount');
      if (countEl) countEl.textContent = `${totalJobs} job${totalJobs !== 1 ? 's' : ''}`;

      if (totalJobs === 0) {
        emptyState?.classList.remove('d-none');
        loading?.classList.add('d-none');
        return;
      }

      const tbody = document.getElementById('bulkJobsBody');
      if (tbody) {
        tbody.innerHTML = jobs.map(j => {
          const stateBadge = MC.bulkJobs._stateBadge(j.state);
          const opBadge = `<span class="badge bg-secondary">${MC._escHtml(j.operation || '')}</span>`;
          const failedCell = (j.numberRecordsFailed > 0)
            ? `<td class="text-danger fw-semibold">${(j.numberRecordsFailed ?? 0).toLocaleString()}</td>`
            : `<td>${(j.numberRecordsFailed ?? 0).toLocaleString()}</td>`;
          const procTime = j.totalProcessingTime != null
            ? MC.bulkJobs._fmtMs(j.totalProcessingTime)
            : '—';
          const created = j.createdDate ? new Date(j.createdDate).toLocaleString() : '—';
          return `<tr>
            <td><code class="small">${MC._escHtml(j.id || '')}</code></td>
            <td>${opBadge}</td>
            <td>${MC._escHtml(j.object || '')}</td>
            <td>${stateBadge}</td>
            <td>${(j.numberRecordsProcessed ?? 0).toLocaleString()}</td>
            ${failedCell}
            <td>${procTime}</td>
            <td><small>${created}</small></td>
          </tr>`;
        }).join('');
      }

      tableWrap?.classList.remove('d-none');

    } catch (err) {
      MC.showToast(`Bulk jobs failed: ${err.message}`, 'danger');
    } finally {
      loading?.classList.add('d-none');
    }
  },

  _stateBadge(state) {
    const s = state || '';
    if (s === 'JobComplete') return `<span class="badge bg-success">${MC._escHtml(s)}</span>`;
    if (s === 'InProgress') return `<span class="badge bg-warning text-dark">${MC._escHtml(s)}</span>`;
    if (s === 'Failed') return `<span class="badge bg-danger">${MC._escHtml(s)}</span>`;
    return `<span class="badge bg-secondary">${MC._escHtml(s)}</span>`;
  },

  _fmtMs(ms) {
    if (ms == null) return '—';
    if (ms < 1000) return `${ms}ms`;
    if (ms < 60000) return `${(ms / 1000).toFixed(1)}s`;
    return `${(ms / 60000).toFixed(1)}m`;
  },

  _setAutoRefresh(checked) {
    if (this._timer) {
      clearInterval(this._timer);
      this._timer = null;
    }
    if (checked) {
      this._timer = setInterval(() => this.load(), 15000);
    }
  },
};
