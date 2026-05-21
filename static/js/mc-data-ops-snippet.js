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
          const link = MC.sfLinkTag(id, data.sobject);
          return `<tr><td><code class="small">${MC._escHtml(id)}</code></td><td class="font-monospace small">${link}</td></tr>`;
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
                        ? MC.sfLinkTag(r.TargetObjectId, obj)
                        : MC._escHtml(r.TargetObjectId || '');
                      return `<tr>
                        <td><code class="small">${MC._escHtml(r.Id || '')}</code></td>
                        <td class="font-monospace small">${sfLink}</td>
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

// ── Importer (Import Wizard) ──────────────────────────────────────────────────

MC.importer = {
  _step: 1,
  _csvText: '',
  _csvHeaders: [],
  _csvRows: [],
  _sfFields: [],
  _fieldMapping: {},
  _validationResult: null,
  _errorCsv: '',

  init() {
    document.getElementById('importOperation')?.addEventListener('change', e => {
      document.getElementById('extIdFieldWrap')?.classList.toggle('d-none', e.target.value !== 'upsert');
    });
    document.getElementById('importCsvFile')?.addEventListener('change', e => this._loadCsv(e.target.files[0]));
    document.getElementById('btnImportStep1Next')?.addEventListener('click', () => this._step1Next());
    document.getElementById('btnImportStep2Back')?.addEventListener('click', () => this.goStep(1));
    document.getElementById('btnImportStep2Next')?.addEventListener('click', () => this._step2Next());
    document.getElementById('btnImportStep3Back')?.addEventListener('click', () => this.goStep(2));
    document.getElementById('btnRunValidation')?.addEventListener('click', () => this._runValidation());
    document.getElementById('btnImportStep3Next')?.addEventListener('click', () => this.goStep(4));
    document.getElementById('btnImportStep4Back')?.addEventListener('click', () => this.goStep(3));
    document.getElementById('btnExecuteImport')?.addEventListener('click', () => this._executeImport());
    document.getElementById('btnDownloadErrors')?.addEventListener('click', () => this._downloadErrors());
    document.getElementById('validationErrorFilter')?.addEventListener('input', e =>
      MC.permissions._filterTable('validationErrorTbody', e.target.value));
  },

  goStep(n) {
    this._step = n;
    for (let i = 1; i <= 4; i++) {
      document.getElementById(`importStep${i}`)?.classList.toggle('d-none', i !== n);
      document.getElementById(`stepBtn${i}`)?.classList.toggle('active', i === n);
    }
  },

  _loadCsv(file) {
    if (!file) return;
    const reader = new FileReader();
    reader.onload = e => {
      this._csvText = e.target.result;
      const lines = this._csvText.split('\n').filter(l => l.trim());
      if (lines.length < 2) return;
      const parse = line => line.split(',').map(c => c.trim().replace(/^"|"$/g, ''));
      this._csvHeaders = parse(lines[0]);
      this._csvRows = lines.slice(1, 6).map(parse);
      this._renderCsvPreview();
    };
    reader.readAsText(file);
  },

  _renderCsvPreview() {
    const head = document.getElementById('csvPreviewHead');
    const body = document.getElementById('csvPreviewBody');
    const wrap = document.getElementById('csvPreviewWrap');
    const empty = document.getElementById('csvPreviewEmpty');
    if (!head || !body) return;
    head.innerHTML = `<tr>${this._csvHeaders.map(h => `<th class="small">${MC._escHtml(h)}</th>`).join('')}</tr>`;
    body.innerHTML = this._csvRows.map(row =>
      `<tr>${row.map(v => `<td class="small">${MC._escHtml(v)}</td>`).join('')}</tr>`
    ).join('');
    wrap?.classList.remove('d-none');
    empty?.classList.add('d-none');
  },

  async _step1Next() {
    const obj = document.getElementById('importObject')?.value.trim();
    if (!obj) { MC.showToast('Enter a Salesforce object name', 'warning'); return; }
    if (!this._csvText) { MC.showToast('Upload a CSV file', 'warning'); return; }
    try {
      this._sfFields = await MC.api('/data-ops/import/fields', 'POST', { object: obj });
      this._buildMappingUI();
      this.goStep(2);
    } catch (err) {
      MC.showToast('Could not load object fields: ' + err.message, 'danger');
    }
  },

  _buildMappingUI() {
    const wrap = document.getElementById('fieldMappingWrap');
    if (!wrap) return;
    const sfOptions = this._sfFields
      .map(f => `<option value="${MC._escHtml(f.name)}">${MC._escHtml(f.label)} (${MC._escHtml(f.name)})</option>`)
      .join('');
    wrap.innerHTML = `
      <p class="text-muted small mb-3">Map each CSV column to a Salesforce field. Unmapped columns are ignored.</p>
      <table class="table table-sm">
        <thead class="table-light"><tr><th>CSV Column</th><th>Salesforce Field</th></tr></thead>
        <tbody>
          ${this._csvHeaders.map(col => {
            const autoMatch = this._sfFields.find(f =>
              f.name.toLowerCase() === col.toLowerCase() ||
              f.label.toLowerCase() === col.toLowerCase()
            );
            return `<tr>
              <td class="small font-monospace align-middle">${MC._escHtml(col)}</td>
              <td>
                <select class="form-select form-select-sm mapping-select" data-csv-col="${MC._escHtml(col)}">
                  <option value="">(skip)</option>
                  ${sfOptions}
                </select>
              </td>
            </tr>`;
          }).join('')}
        </tbody>
      </table>`;
    // Apply auto-match
    if (autoMatch) {
      document.querySelectorAll('.mapping-select').forEach(sel => {
        const col = sel.dataset.csvCol;
        const match = this._sfFields.find(f =>
          f.name.toLowerCase() === col.toLowerCase() ||
          f.label.toLowerCase() === col.toLowerCase()
        );
        if (match) sel.value = match.name;
      });
    }
  },

  autoMap() {
    document.querySelectorAll('.mapping-select').forEach(sel => {
      const col = sel.dataset.csvCol || '';
      const match = this._sfFields.find(f =>
        f.name.toLowerCase() === col.toLowerCase() ||
        f.label.toLowerCase() === col.toLowerCase()
      );
      if (match) sel.value = match.name;
    });
  },

  _collectMapping() {
    const mapping = {};
    document.querySelectorAll('.mapping-select').forEach(sel => {
      if (sel.value) mapping[sel.dataset.csvCol] = sel.value;
    });
    this._fieldMapping = mapping;
    return mapping;
  },

  _step2Next() {
    const mapping = this._collectMapping();
    if (Object.keys(mapping).length === 0) {
      MC.showToast('Map at least one column before continuing', 'warning'); return;
    }
    this.goStep(3);
  },

  async _runValidation() {
    const loading = document.getElementById('validationLoading');
    const results = document.getElementById('validationResults');
    const nextBtn = document.getElementById('btnImportStep3Next');
    loading?.classList.remove('d-none');
    results?.classList.add('d-none');

    const formData = new FormData();
    formData.append('object', document.getElementById('importObject')?.value.trim() || '');
    formData.append('operation', document.getElementById('importOperation')?.value || 'insert');
    formData.append('field_mapping', JSON.stringify(this._collectMapping()));
    formData.append('csv_file', new Blob([this._csvText], {type:'text/csv'}), 'upload.csv');

    try {
      const res = await fetch('/data-ops/import/validate', { method: 'POST', body: formData });
      const json = await res.json();
      if (!json.success) throw new Error(json.error || 'Validation failed');
      const d = json.data;
      this._validationResult = d;
      loading?.classList.add('d-none');
      results?.classList.remove('d-none');
      this._renderValidationStats(d);
      if (d.errors && d.errors.length > 0) this._renderValidationErrors(d.errors);
      nextBtn?.classList.toggle('d-none', d.error_rows > 0);
      this._renderImportConfirm(d);
    } catch (err) {
      loading?.classList.add('d-none');
      MC.showToast('Validation error: ' + err.message, 'danger');
    }
  },

  _renderValidationStats(d) {
    const stats = document.getElementById('validationStats');
    if (!stats) return;
    const cards = [
      {label: 'Total Rows', value: d.total_rows, cls: 'primary'},
      {label: 'Clean', value: d.clean_rows, cls: 'success'},
      {label: 'Warnings', value: d.warning_rows, cls: 'warning'},
      {label: 'Errors', value: d.error_rows, cls: 'danger'},
    ];
    stats.innerHTML = cards.map(c =>
      `<div class="col-6 col-md-3">
         <div class="card border-${c.cls}">
           <div class="card-body text-center py-2">
             <div class="text-muted small">${c.label}</div>
             <div class="fw-bold fs-5 text-${c.cls}">${c.value.toLocaleString()}</div>
           </div>
         </div>
       </div>`
    ).join('');
  },

  _renderValidationErrors(errors) {
    const wrap = document.getElementById('validationErrorWrap');
    const tbody = document.getElementById('validationErrorTbody');
    if (!wrap || !tbody) return;
    wrap.classList.remove('d-none');
    tbody.innerHTML = errors.map(e =>
      `<tr>
        <td class="small">${e.row}</td>
        <td class="small font-monospace">${MC._escHtml(e.field)}</td>
        <td><span class="badge ${e.severity === 'error' ? 'badge-red' : 'badge-amber'}">${MC._escHtml(e.severity)}</span></td>
        <td class="small">${MC._escHtml(e.message)}</td>
      </tr>`
    ).join('');
  },

  _renderImportConfirm(d) {
    const el = document.getElementById('importConfirmSummary');
    if (el) el.textContent = ` ${d.total_rows.toLocaleString()} rows via ${d.operation.toUpperCase()} to ${d.object_name}. ${d.warning_rows} warnings, ${d.error_rows} errors.`;
  },

  async _executeImport() {
    const loading = document.getElementById('importLoading');
    const confirm = document.getElementById('importConfirmWrap');
    const results = document.getElementById('importResultsWrap');
    loading?.classList.remove('d-none');
    confirm?.classList.add('d-none');
    results?.classList.add('d-none');

    const formData = new FormData();
    formData.append('object', document.getElementById('importObject')?.value.trim() || '');
    formData.append('operation', document.getElementById('importOperation')?.value || 'insert');
    formData.append('external_id_field', document.getElementById('importExtIdField')?.value.trim() || '');
    formData.append('bypass_triggers', document.getElementById('importBypassTriggers')?.checked ? 'true' : 'false');
    formData.append('field_mapping', JSON.stringify(this._fieldMapping));
    formData.append('csv_file', new Blob([this._csvText], {type:'text/csv'}), 'upload.csv');

    try {
      const res = await fetch('/data-ops/import/execute', { method: 'POST', body: formData });
      const json = await res.json();
      if (!json.success) throw new Error(json.error || 'Import failed');
      const d = json.data;
      this._errorCsv = d.error_csv || '';
      loading?.classList.add('d-none');
      results?.classList.remove('d-none');
      this._renderImportResults(d);
    } catch (err) {
      loading?.classList.add('d-none');
      confirm?.classList.remove('d-none');
      MC.showToast('Import error: ' + err.message, 'danger');
    }
  },

  _renderImportResults(d) {
    const stats = document.getElementById('importResultStats');
    if (stats) {
      stats.innerHTML = `
        <div class="col-4"><div class="card border-primary"><div class="card-body text-center py-2">
          <div class="text-muted small">Total</div><div class="fw-bold fs-5 text-primary">${d.total.toLocaleString()}</div>
        </div></div></div>
        <div class="col-4"><div class="card border-success"><div class="card-body text-center py-2">
          <div class="text-muted small">Succeeded</div><div class="fw-bold fs-5 text-success">${d.success_count.toLocaleString()}</div>
        </div></div></div>
        <div class="col-4"><div class="card border-danger"><div class="card-body text-center py-2">
          <div class="text-muted small">Failed</div><div class="fw-bold fs-5 text-danger">${d.error_count.toLocaleString()}</div>
        </div></div></div>`;
    }
    if (d.error_count > 0 && d.results) {
      const wrap = document.getElementById('importErrorWrap');
      const tbody = document.getElementById('importErrorTbody');
      wrap?.classList.remove('d-none');
      if (tbody) {
        tbody.innerHTML = d.results.filter(r => !r.success).map(r =>
          `<tr>
            <td class="small">${r.row}</td>
            <td class="small font-monospace">${r.sf_id ? MC.sfLinkTag(r.sf_id) : '—'}</td>
            <td class="small text-danger">${MC._escHtml(r.errors)}</td>
          </tr>`
        ).join('');
      }
    }
  },

  _downloadErrors() {
    if (!this._errorCsv) return;
    const form = document.createElement('form');
    form.method = 'POST';
    form.action = '/data-ops/import/download-errors';
    const addField = (name, val) => {
      const inp = document.createElement('input');
      inp.type = 'hidden'; inp.name = name; inp.value = val;
      form.appendChild(inp);
    };
    addField('error_csv', this._errorCsv);
    addField('filename', 'import_errors.csv');
    document.body.appendChild(form);
    form.submit();
    document.body.removeChild(form);
  },
};

// ── Bulk Delete ───────────────────────────────────────────────────────────────

MC.bulkDelete = {
  _previewData: null,

  init() {
    document.getElementById('btnDeletePreview')?.addEventListener('click', () => this.preview());
    document.getElementById('btnDeleteExecute')?.addEventListener('click', () => this.execute());
  },

  async preview() {
    const obj   = document.getElementById('deleteObject')?.value.trim();
    const where = document.getElementById('deleteWhere')?.value.trim();
    if (!obj || !where) { MC.showToast('Object and WHERE clause required', 'warning'); return; }
    const body = document.getElementById('deletePreviewBody');
    if (body) body.innerHTML = '<div class="text-center py-4"><div class="spinner-border text-warning"></div></div>';
    document.getElementById('btnDeleteExecute')?.classList.add('d-none');
    try {
      const d = await MC.api('/data-ops/delete/preview', 'POST', {object: obj, where_clause: where});
      this._previewData = d;
      if (body) body.innerHTML = this._renderPreviewTable(d);
      document.getElementById('btnDeleteExecute')?.classList.remove('d-none');
    } catch (err) {
      if (body) body.innerHTML = `<div class="alert alert-danger m-3">${MC._escHtml(err.message)}</div>`;
    }
  },

  async execute() {
    if (!confirm(`Delete ${this._previewData?.total || 'matching'} records? This cannot be undone easily.`)) return;
    const obj   = document.getElementById('deleteObject')?.value.trim();
    const where = document.getElementById('deleteWhere')?.value.trim();
    const bypass = document.getElementById('deleteBypass')?.checked;
    try {
      const d = await MC.api('/data-ops/delete/execute', 'POST', {object: obj, where_clause: where, bypass_triggers: bypass});
      const alert = document.getElementById('deleteResultAlert');
      const wrap = document.getElementById('deleteResultWrap');
      if (alert) alert.innerHTML = `<div class="alert alert-${d.errors > 0 ? 'warning' : 'success'}">Deleted <strong>${d.deleted}</strong> records. Errors: ${d.errors}.</div>`;
      wrap?.classList.remove('d-none');
      document.getElementById('btnDeleteExecute')?.classList.add('d-none');
    } catch (err) {
      MC.showToast('Delete failed: ' + err.message, 'danger');
    }
  },

  _renderPreviewTable(d) {
    if (!d.rows || !d.rows.length) return '<div class="text-muted text-center py-5 small">No records match the WHERE clause.</div>';
    const cols = d.columns.filter(c => c !== 'attributes');
    return `<div class="p-2 small text-muted">Showing first ${d.rows.length} of <strong>${d.total.toLocaleString()}</strong> matching records.</div>
      <div style="overflow-x:auto">
        <table class="table table-sm table-hover mb-0">
          <thead class="table-light"><tr>${cols.map(c => `<th>${MC._escHtml(c)}</th>`).join('')}</tr></thead>
          <tbody>${d.rows.map(r => `<tr>${cols.map(c => {
            const val = r[c];
            if (MC.isSfId(val)) return `<td class="font-monospace small">${MC.sfLinkTag(val)}</td>`;
            return `<td class="small">${MC._escHtml(val ?? '')}</td>`;
          }).join('')}</tr>`).join('')}</tbody>
        </table>
      </div>`;
  },
};

// ── Bulk Modify ───────────────────────────────────────────────────────────────

MC.bulkModify = {
  _previewData: null,

  init() {
    document.getElementById('btnModifyPreview')?.addEventListener('click', () => this.preview());
    document.getElementById('btnModifyExecute')?.addEventListener('click', () => this.execute());
  },

  addField() {
    const list = document.getElementById('modifyFieldsList');
    if (!list) return;
    const row = document.createElement('div');
    row.className = 'input-group mb-2 modify-field-row';
    row.innerHTML = `<input type="text" class="form-control font-monospace modify-field-name" placeholder="Field API name">
      <input type="text" class="form-control modify-field-value" placeholder="New value">
      <button class="btn btn-outline-secondary" onclick="MC.bulkModify.removeField(this)">✕</button>`;
    list.appendChild(row);
  },

  removeField(btn) {
    btn.closest('.modify-field-row')?.remove();
  },

  _collectFields() {
    const updates = {};
    document.querySelectorAll('.modify-field-row').forEach(row => {
      const name = row.querySelector('.modify-field-name')?.value.trim();
      const val  = row.querySelector('.modify-field-value')?.value;
      if (name) updates[name] = val;
    });
    return updates;
  },

  async preview() {
    const obj   = document.getElementById('modifyObject')?.value.trim();
    const where = document.getElementById('modifyWhere')?.value.trim();
    if (!obj || !where) { MC.showToast('Object and WHERE clause required', 'warning'); return; }
    const body = document.getElementById('modifyPreviewBody');
    if (body) body.innerHTML = '<div class="text-center py-4"><div class="spinner-border text-warning"></div></div>';
    document.getElementById('btnModifyExecute')?.classList.add('d-none');
    const fields = this._collectFields();
    const firstField = Object.keys(fields)[0] || 'Id';
    try {
      const d = await MC.api('/data-ops/modify/preview', 'POST', {object: obj, where_clause: where, field: firstField, value: fields[firstField]});
      this._previewData = d;
      if (body) body.innerHTML = MC.bulkDelete._renderPreviewTable(d);
      document.getElementById('btnModifyExecute')?.classList.remove('d-none');
    } catch (err) {
      if (body) body.innerHTML = `<div class="alert alert-danger m-3">${MC._escHtml(err.message)}</div>`;
    }
  },

  async execute() {
    const obj   = document.getElementById('modifyObject')?.value.trim();
    const where = document.getElementById('modifyWhere')?.value.trim();
    const bypass = document.getElementById('modifyBypass')?.checked;
    const field_updates = this._collectFields();
    if (!Object.keys(field_updates).length) { MC.showToast('Add at least one field to update', 'warning'); return; }
    try {
      const d = await MC.api('/data-ops/modify/execute', 'POST', {object: obj, where_clause: where, field_updates, bypass_triggers: bypass});
      const alert = document.getElementById('modifyResultAlert');
      document.getElementById('modifyResultWrap')?.classList.remove('d-none');
      if (alert) alert.innerHTML = `<div class="alert alert-${d.errors > 0 ? 'warning' : 'success'}">Updated <strong>${d.updated}</strong> records. Errors: ${d.errors}.</div>`;
      document.getElementById('btnModifyExecute')?.classList.add('d-none');
    } catch (err) {
      MC.showToast('Modify failed: ' + err.message, 'danger');
    }
  },
};

// ── Bulk Reassign ─────────────────────────────────────────────────────────────

MC.bulkReassign = {
  _previewData: null,

  init() {
    document.getElementById('btnReassignUserSearch')?.addEventListener('click', () => this.searchUsers());
    document.getElementById('reassignOwnerSearch')?.addEventListener('keydown', e => {
      if (e.key === 'Enter') this.searchUsers();
    });
    document.getElementById('btnReassignPreview')?.addEventListener('click', () => this.preview());
    document.getElementById('btnReassignExecute')?.addEventListener('click', () => this.execute());
  },

  async searchUsers() {
    const q = document.getElementById('reassignOwnerSearch')?.value.trim() || '';
    const results = document.getElementById('reassignUserResults');
    if (!results) return;
    try {
      const users = await MC.api(`/data-ops/reassign/users?q=${encodeURIComponent(q)}`);
      results.innerHTML = (users || []).map(u =>
        `<button class="list-group-item list-group-item-action py-2"
                 onclick="MC.bulkReassign.selectUser('${MC._escHtml(u.id)}', '${MC._escHtml(u.name)}')">
          <span class="small fw-semibold">${MC._escHtml(u.name)}</span>
          <span class="small text-muted ms-2">${MC._escHtml(u.username)}</span>
        </button>`
      ).join('') || '<div class="list-group-item text-muted small">No users found.</div>';
    } catch (err) {
      MC.showToast('User search failed: ' + err.message, 'danger');
    }
  },

  selectUser(id, name) {
    document.getElementById('reassignOwnerId').value = id;
    const badge = document.getElementById('reassignOwnerBadge');
    if (badge) badge.textContent = name;
    document.getElementById('reassignSelectedOwner')?.classList.remove('d-none');
    document.getElementById('reassignUserResults').innerHTML = '';
  },

  async preview() {
    const obj   = document.getElementById('reassignObject')?.value.trim();
    const where = document.getElementById('reassignWhere')?.value.trim();
    if (!obj || !where) { MC.showToast('Object and WHERE clause required', 'warning'); return; }
    const body = document.getElementById('reassignPreviewBody');
    if (body) body.innerHTML = '<div class="text-center py-4"><div class="spinner-border text-warning"></div></div>';
    document.getElementById('btnReassignExecute')?.classList.add('d-none');
    try {
      const d = await MC.api('/data-ops/reassign/preview', 'POST', {object: obj, where_clause: where});
      this._previewData = d;
      if (body) body.innerHTML = MC.bulkDelete._renderPreviewTable(d);
      document.getElementById('btnReassignExecute')?.classList.remove('d-none');
    } catch (err) {
      if (body) body.innerHTML = `<div class="alert alert-danger m-3">${MC._escHtml(err.message)}</div>`;
    }
  },

  async execute() {
    const obj   = document.getElementById('reassignObject')?.value.trim();
    const where = document.getElementById('reassignWhere')?.value.trim();
    const newOwnerId = document.getElementById('reassignOwnerId')?.value.trim();
    const bypass = document.getElementById('reassignBypass')?.checked;
    if (!newOwnerId) { MC.showToast('Select a new owner first', 'warning'); return; }
    try {
      const d = await MC.api('/data-ops/reassign/execute', 'POST', {object: obj, where_clause: where, new_owner_id: newOwnerId, bypass_triggers: bypass});
      const alert = document.getElementById('reassignResultAlert');
      document.getElementById('reassignResultWrap')?.classList.remove('d-none');
      if (alert) alert.innerHTML = `<div class="alert alert-${d.errors > 0 ? 'warning' : 'success'}">Reassigned <strong>${d.reassigned}</strong> records. Errors: ${d.errors}.</div>`;
      document.getElementById('btnReassignExecute')?.classList.add('d-none');
    } catch (err) {
      MC.showToast('Reassign failed: ' + err.message, 'danger');
    }
  },
};

// ── Exporter ──────────────────────────────────────────────────────────────────

MC.exporter = {
  init() {
    document.getElementById('btnExport')?.addEventListener('click', () => this.run());
  },

  run() {
    const soql = document.getElementById('exportSoql')?.value.trim();
    const filename = document.getElementById('exportFilename')?.value.trim() || 'export.csv';
    const allPages = document.getElementById('exportAllPages')?.checked;
    if (!soql) { MC.showToast('Enter a SOQL query', 'warning'); return; }

    // Use form submit for file download — avoids CORS/blob issues
    const form = document.createElement('form');
    form.method = 'POST';
    form.action = '/data-ops/export/run';
    const addField = (name, val) => {
      const inp = document.createElement('input');
      inp.type = 'hidden'; inp.name = name; inp.value = val;
      form.appendChild(inp);
    };
    addField('soql', soql);
    addField('filename', filename);
    addField('all_pages', allPages ? 'true' : 'false');
    document.body.appendChild(form);
    form.submit();
    document.body.removeChild(form);
  },
};

// ── Tuner (Data Standardization) ──────────────────────────────────────────────

MC.tuner = {
  _rules: [],
  _rowSeq: 0,

  async init() {
    document.getElementById('btnTunePreview')?.addEventListener('click', () => this.preview());
    document.getElementById('btnTuneExecute')?.addEventListener('click', () => this.execute());
    try {
      this._rules = await MC.api('/data-ops/tune/rules') || [];
    } catch (err) {
      MC.showToast('Could not load tune rules: ' + err.message, 'danger');
    }
    this.addField();
  },

  addField() {
    const list = document.getElementById('tuneFieldsList');
    if (!list) return;
    const seq = ++this._rowSeq;
    const opts = this._rules
      .map(r => `<option value="${MC._escHtml(r.name)}">${MC._escHtml(r.label)}</option>`)
      .join('');
    const row = document.createElement('div');
    row.className = 'tune-field-row border rounded p-2 mb-2';
    row.innerHTML = `
      <div class="d-flex gap-2 align-items-start">
        <input type="text" class="form-control form-control-sm font-monospace tune-field-name"
               placeholder="Field API name" style="max-width:45%">
        <select multiple class="form-select form-select-sm tune-field-rules" size="4">${opts}</select>
        <button class="btn btn-outline-secondary btn-sm" onclick="MC.tuner.removeField(this)">✕</button>
      </div>`;
    list.appendChild(row);
  },

  removeField(btn) {
    btn.closest('.tune-field-row')?.remove();
  },

  _collectFieldRules() {
    const fieldRules = {};
    document.querySelectorAll('.tune-field-row').forEach(row => {
      const name = row.querySelector('.tune-field-name')?.value.trim();
      const sel = row.querySelector('.tune-field-rules');
      const rules = sel ? Array.from(sel.selectedOptions).map(o => o.value) : [];
      if (name && rules.length) fieldRules[name] = rules;
    });
    return fieldRules;
  },

  async preview() {
    const obj = document.getElementById('tuneObject')?.value.trim();
    const where = document.getElementById('tuneWhere')?.value.trim();
    const fieldRules = this._collectFieldRules();
    if (!obj || !where) { MC.showToast('Object and WHERE clause required', 'warning'); return; }
    if (!Object.keys(fieldRules).length) {
      MC.showToast('Add at least one field with a rule selected', 'warning'); return;
    }
    const body = document.getElementById('tunePreviewBody');
    if (body) body.innerHTML = '<div class="text-center py-4"><div class="spinner-border text-warning"></div></div>';
    document.getElementById('btnTuneExecute')?.classList.add('d-none');
    try {
      const d = await MC.api('/data-ops/tune/preview', 'POST',
        {object: obj, where_clause: where, field_rules: fieldRules});
      if (body) body.innerHTML = this._renderPreview(d);
      if (d.changed_in_sample > 0) {
        document.getElementById('btnTuneExecute')?.classList.remove('d-none');
      }
    } catch (err) {
      if (body) body.innerHTML = `<div class="alert alert-danger m-3">${MC._escHtml(err.message)}</div>`;
    }
  },

  _renderPreview(d) {
    if (!d.changed || !d.changed.length) {
      return `<div class="text-muted text-center py-5 small">
        Scanned ${d.sample_size} of ${d.total_matching.toLocaleString()} matching records —
        nothing needs standardizing.</div>`;
    }
    const rows = d.changed.flatMap(rec =>
      rec.changes.map((c, i) => `<tr>
        ${i === 0 ? `<td class="font-monospace small" rowspan="${rec.changes.length}">${MC.sfLinkTag(rec.id)}</td>` : ''}
        <td class="small font-monospace">${MC._escHtml(c.field)}</td>
        <td class="small text-muted">${MC._escHtml(c.before)}</td>
        <td class="small text-success fw-semibold">${MC._escHtml(c.after)}</td>
      </tr>`)
    ).join('');
    return `<div class="p-2 small text-muted">
        <strong>${d.changed_in_sample}</strong> of ${d.sample_size} sampled records would change
        (${d.total_matching.toLocaleString()} match the filter).</div>
      <div style="max-height:420px;overflow-y:auto">
        <table class="table table-sm table-hover mb-0">
          <thead class="table-light"><tr><th>Record</th><th>Field</th><th>Before</th><th>After</th></tr></thead>
          <tbody>${rows}</tbody>
        </table>
      </div>`;
  },

  async execute() {
    const obj = document.getElementById('tuneObject')?.value.trim();
    const where = document.getElementById('tuneWhere')?.value.trim();
    const fieldRules = this._collectFieldRules();
    const bypass = document.getElementById('tuneBypass')?.checked;
    if (!Object.keys(fieldRules).length) {
      MC.showToast('Add at least one field with a rule', 'warning'); return;
    }
    try {
      const d = await MC.api('/data-ops/tune/execute', 'POST',
        {object: obj, where_clause: where, field_rules: fieldRules, bypass_triggers: bypass});
      const alert = document.getElementById('tuneResultAlert');
      document.getElementById('tuneResultWrap')?.classList.remove('d-none');
      const mockNote = d.mock ? ' <span class="badge badge-secondary">mock — not written</span>' : '';
      if (alert) {
        alert.innerHTML = `<div class="alert alert-${d.errors > 0 ? 'warning' : 'success'}">
          Standardized <strong>${d.updated}</strong> record(s).
          ${d.unchanged} already clean. Errors: ${d.errors}.${mockNote}</div>`;
      }
      document.getElementById('btnTuneExecute')?.classList.add('d-none');
    } catch (err) {
      MC.showToast('Tune failed: ' + err.message, 'danger');
    }
  },
};

// ── Matcher (Fuzzy Duplicate Detection) ───────────────────────────────────────

MC.matcher = {
  init() {
    const slider = document.getElementById('matchThreshold');
    const out = document.getElementById('matchThresholdVal');
    slider?.addEventListener('input', () => { if (out) out.textContent = slider.value; });
    document.getElementById('btnMatchRun')?.addEventListener('click', () => this.run());
  },

  async run() {
    const obj = document.getElementById('matchObject')?.value.trim();
    const where = document.getElementById('matchWhere')?.value.trim();
    const blockField = document.getElementById('matchBlockField')?.value.trim();
    const compareFields = (document.getElementById('matchCompareFields')?.value || '')
      .split(',').map(s => s.trim()).filter(Boolean);
    const threshold = parseFloat(document.getElementById('matchThreshold')?.value || '0.85');

    if (!obj || !where) { MC.showToast('Object and WHERE clause required', 'warning'); return; }
    if (!blockField) { MC.showToast('A blocking field is required', 'warning'); return; }
    if (!compareFields.length) { MC.showToast('Enter at least one compare field', 'warning'); return; }

    const loading = document.getElementById('matchLoading');
    const summary = document.getElementById('matchSummary');
    const body = document.getElementById('matchBody');
    loading?.classList.remove('d-none');
    summary?.classList.add('d-none');
    if (body) body.innerHTML = '';

    try {
      const d = await MC.api('/data-ops/match/run', 'POST', {
        object: obj, where_clause: where, compare_fields: compareFields,
        block_field: blockField, threshold,
      });
      loading?.classList.add('d-none');
      this._renderSummary(d);
      this._renderCandidates(d);
    } catch (err) {
      loading?.classList.add('d-none');
      if (body) body.innerHTML = `<div class="alert alert-danger m-3">${MC._escHtml(err.message)}</div>`;
    }
  },

  _renderSummary(d) {
    const el = document.getElementById('matchSummary');
    if (!el) return;
    const trunc = d.truncated_blocks > 0
      ? ` <span class="text-warning">(${d.truncated_blocks} large block(s) capped)</span>` : '';
    el.innerHTML = `<p class="small text-muted mb-2">
      Scanned <strong>${d.records_scanned.toLocaleString()}</strong> records in
      <strong>${d.block_count}</strong> Soundex block(s),
      <strong>${d.comparisons.toLocaleString()}</strong> comparison(s) &rarr;
      <strong>${d.candidate_count}</strong> candidate pair(s) at threshold ${d.threshold}.${trunc}</p>`;
    el.classList.remove('d-none');
  },

  _renderCandidates(d) {
    const body = document.getElementById('matchBody');
    if (!body) return;
    if (!d.candidates.length) {
      body.innerHTML = '<div class="text-muted text-center py-5 small">No near-duplicate pairs found above the threshold.</div>';
      return;
    }
    const fields = d.compare_fields;
    const recCell = (rec, fieldScores) => {
      const vals = fields.map(f => {
        const s = fieldScores[f];
        const cls = s != null && s < 0.7 ? 'text-danger' : 'text-muted';
        return `<div class="small"><span class="${cls}">${MC._escHtml(f)}:</span>
                ${MC._escHtml(rec.values[f] ?? '')}</div>`;
      }).join('');
      return `<div class="font-monospace small mb-1">${MC.sfLinkTag(rec.id)}</div>${vals}`;
    };
    const rows = d.candidates.map(c => {
      const pct = Math.round(c.score * 100);
      const cls = c.score >= 0.95 ? 'badge-red' : c.score >= 0.85 ? 'badge-amber' : 'badge-secondary';
      return `<tr>
        <td class="text-center"><span class="badge ${cls}">${pct}%</span></td>
        <td>${recCell(c.a, c.field_scores)}</td>
        <td>${recCell(c.b, c.field_scores)}</td>
      </tr>`;
    }).join('');
    body.innerHTML = `<div style="max-height:540px;overflow-y:auto">
      <table class="table table-sm table-hover mb-0">
        <thead class="table-light"><tr><th class="text-center">Score</th><th>Record A</th><th>Record B</th></tr></thead>
        <tbody>${rows}</tbody>
      </table></div>
      <div class="p-2 small text-muted">Review pairs and merge via
        <a href="/validation/duplicates">Validation &rsaquo; Duplicate Radar</a>.</div>`;
  },
};
