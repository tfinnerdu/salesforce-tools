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
