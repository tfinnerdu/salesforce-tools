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
