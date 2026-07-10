/* mc-scenarios-snippet.js — Scenarios tab: index list + builder + run.
 * Companion to templates/scenarios/{index,builder}.html.
 *
 * Active on /scenarios* pages. Dispatches by which template was rendered:
 * the index template has #scenTbody, the builder has [data-scenario-id].
 */
MC.scenarios = {

  _all: [],
  _allTags: [],
  _activeTagFilter: null,

  init() {
    if (document.getElementById('scenTbody')) this._initIndex();
    if (document.querySelector('[data-scenario-id]')) this._initBuilder();
  },

  // ── Field schemas per step type ─────────────────────────────────────────

  _stepSchema(type) {
    const common = [
      {key: 'object', label: 'SF Object', placeholder: 'e.g. Account'},
      {key: 'where_clause', label: 'WHERE clause', placeholder: 'e.g. IsPersonAccount = true', textarea: true},
    ];
    switch (type) {
      case 'delete':      return common;
      case 'modify':      return [...common,
        {key: 'field', label: 'Field', placeholder: 'e.g. Status__c'},
        {key: 'value', label: 'New value'},
      ];
      case 'reassign':    return [...common,
        {key: 'new_owner_id', label: 'New owner ID', placeholder: '005...'},
      ];
      case 'bulk_update': return [...common,
        {key: 'field', label: 'Field'},
        {key: 'value', label: 'Value'},
        {key: 'dry_run', label: 'Dry run', type: 'checkbox'},
      ];
      case 'tune':        return [...common,
        {key: 'field_rules', label: 'Field rules (JSON)',
         placeholder: '{"FirstName": ["trim","title_case"]}', textarea: true, json: true},
      ];
      default:            return common;
    }
  },

  _stepLabel(type) {
    return ({delete: 'Delete', modify: 'Modify field', reassign: 'Reassign owner',
             bulk_update: 'Bulk update', tune: 'Tune (standardize)'}[type] || type);
  },

  // ── INDEX PAGE ──────────────────────────────────────────────────────────

  async _initIndex() {
    document.getElementById('btnNewTag')?.addEventListener('click', () =>
      bootstrap.Modal.getOrCreateInstance(document.getElementById('newTagModal')).show());
    document.getElementById('btnSaveTag')?.addEventListener('click', () => this._saveTag());
    document.getElementById('tagFilterClear')?.addEventListener('click', (e) => {
      e.preventDefault(); this._activeTagFilter = null; this._renderIndex();
    });
    await this._refreshIndex();
  },

  async _refreshIndex() {
    try {
      const [scenarios, tags] = await Promise.all([
        MC.api('/scenarios/list'),
        MC.api('/scenarios/tags'),
      ]);
      this._all = scenarios || [];
      this._allTags = tags || [];
      this._renderTagRail();
      this._renderIndex();
    } catch (err) {
      MC.showToast(`Failed to load scenarios: ${err.message}`, 'danger');
    }
  },

  _renderTagRail() {
    const list = document.getElementById('tagFilterList');
    if (!list) return;
    if (!this._allTags.length) {
      list.innerHTML = '<span class="text-muted small">No tags yet.</span>';
      return;
    }
    list.innerHTML = this._allTags.map(t => `
      <div class="d-flex align-items-center gap-2 mc-tag-row" data-tag-id="${t.id}">
        <a href="#" class="flex-grow-1 text-decoration-none" data-action="filter">
          <span class="badge badge-${MC._escHtml(t.color || 'slate')}">${MC._escHtml(t.name)}</span>
        </a>
        <button class="btn btn-link btn-sm text-muted p-0" data-action="delete"
                data-mc-confirm="Delete tag '${MC._escHtml(t.name)}'? It will be removed from every scenario it is attached to."
                data-mc-confirm-title="Delete tag"
                data-mc-confirm-btn="Delete tag" title="Delete tag">&times;</button>
      </div>`).join('');
    list.querySelectorAll('[data-action="filter"]').forEach(a => {
      a.addEventListener('click', (e) => {
        e.preventDefault();
        const id = parseInt(a.closest('[data-tag-id]').dataset.tagId, 10);
        this._activeTagFilter = (this._activeTagFilter === id) ? null : id;
        this._renderIndex();
      });
    });
    list.querySelectorAll('[data-action="delete"]').forEach(btn => {
      btn.addEventListener('click', async () => {
        const id = parseInt(btn.closest('[data-tag-id]').dataset.tagId, 10);
        try {
          await MC.api(`/scenarios/tags/${id}`, 'DELETE');
          if (this._activeTagFilter === id) this._activeTagFilter = null;
          await this._refreshIndex();
          MC.showToast('Tag deleted', 'success');
        } catch (err) { MC.showToast(err.message, 'danger'); }
      });
    });
  },

  _renderIndex() {
    const tbody = document.getElementById('scenTbody');
    const loading = document.getElementById('scenLoading');
    const empty = document.getElementById('scenEmpty');
    const table = document.getElementById('scenTable');
    loading.classList.add('d-none');

    const rows = this._activeTagFilter
      ? this._all.filter(s => (s.tags || []).some(t => t.id === this._activeTagFilter))
      : this._all;

    if (!rows.length) {
      table.classList.add('d-none');
      empty.classList.remove('d-none');
      return;
    }
    empty.classList.add('d-none');
    table.classList.remove('d-none');
    tbody.innerHTML = rows.map(s => this._rowHtml(s)).join('');
    tbody.querySelectorAll('[data-action="delete-scen"]').forEach(btn => {
      btn.addEventListener('click', () => this._deleteScenario(parseInt(btn.dataset.id, 10)));
    });
    tbody.querySelectorAll('[data-action="run-scen"]').forEach(btn => {
      btn.addEventListener('click', () => this._runFromIndex(parseInt(btn.dataset.id, 10)));
    });
  },

  _rowHtml(s) {
    const tagChips = (s.tags || []).map(t =>
      `<span class="badge badge-${MC._escHtml(t.color || 'slate')} me-1">${MC._escHtml(t.name)}</span>`).join('');
    const steps = (s.steps || []).length;
    return `
      <tr>
        <td>
          <a href="/scenarios/${s.id}" class="fw-semibold">${MC._escHtml(s.name)}</a>
          ${s.description ? `<div class="text-muted small">${MC._escHtml(s.description)}</div>` : ''}
        </td>
        <td>${steps}</td>
        <td>${tagChips || '<span class="text-muted small">—</span>'}</td>
        <td class="text-nowrap text-muted small">${MC._fmtTime(s.updated_at)}</td>
        <td class="text-end">
          <a href="/scenarios/${s.id}" class="btn btn-outline-secondary btn-sm">Edit</a>
          <button class="btn btn-danger btn-sm" data-action="run-scen" data-id="${s.id}"
                  data-mc-confirm="Run scenario '${MC._escHtml(s.name)}'? It runs ${steps} step(s) against Salesforce in order."
                  data-mc-confirm-title="Run scenario"
                  data-mc-confirm-btn="Run scenario"
                  data-mc-confirm-ack="true">Run</button>
          <button class="btn btn-outline-danger btn-sm" data-action="delete-scen" data-id="${s.id}"
                  data-mc-confirm="Delete scenario '${MC._escHtml(s.name)}'? This cannot be undone."
                  data-mc-confirm-title="Delete scenario"
                  data-mc-confirm-btn="Delete">&times;</button>
        </td>
      </tr>`;
  },

  async _deleteScenario(id) {
    try {
      await MC.api(`/scenarios/${id}`, 'DELETE');
      MC.showToast('Scenario deleted', 'success');
      this._refreshIndex();
    } catch (err) { MC.showToast(err.message, 'danger'); }
  },

  async _runFromIndex(id) {
    try {
      MC.showSpinner();
      const result = await MC.api(`/scenarios/${id}/run`, 'POST');
      const fails = (result.step_results || []).filter(r => r.status === 'failed').length;
      const type = result.status === 'success' ? 'success'
                   : result.status === 'partial' ? 'warning' : 'danger';
      MC.showToast(`Run ${result.status} — ${(result.step_results || []).length} step(s), ${fails} failed.`, type);
    } catch (err) {
      MC.showToast(err.message, 'danger');
    } finally { MC.hideSpinner(); }
  },

  async _saveTag() {
    const name = document.getElementById('newTagName').value.trim();
    const color = document.getElementById('newTagColor').value;
    if (!name) { MC.showToast('Tag name required', 'warning'); return; }
    try {
      await MC.api('/scenarios/tags', 'POST', {name, color});
      bootstrap.Modal.getInstance(document.getElementById('newTagModal'))?.hide();
      document.getElementById('newTagName').value = '';
      await this._refreshIndex();
    } catch (err) { MC.showToast(err.message, 'danger'); }
  },

  // ── BUILDER PAGE ────────────────────────────────────────────────────────

  _scenarioId: null,
  _steps: [],
  _scenarioTags: [],

  async _initBuilder() {
    const idRaw = document.querySelector('[data-scenario-id]').dataset.scenarioId;
    this._scenarioId = (idRaw === 'new') ? null : parseInt(idRaw, 10);
    document.getElementById('btnAddStep')?.addEventListener('click', () => this._addStep());
    document.getElementById('btnSaveScenario')?.addEventListener('click', () => this._save());
    document.getElementById('btnRunScenario')?.addEventListener('click', () => this._run());
    document.getElementById('btnManageTags')?.addEventListener('click', () => this._manageTags());
    document.getElementById('schedApproved')?.addEventListener('change', (e) => this._toggleApproved(e));
    document.getElementById('btnGenManifest')?.addEventListener('click', () => this._genManifest());
    document.getElementById('btnCopyManifest')?.addEventListener('click', () => {
      const t = document.getElementById('manifestText');
      MC.copyToClipboard(t.value);
    });

    if (this._scenarioId) {
      try {
        const s = await MC.api(`/scenarios/get/${this._scenarioId}`);
        document.getElementById('builderTitle').textContent = s.name;
        document.getElementById('scenName').value = s.name || '';
        document.getElementById('scenDescription').value = s.description || '';
        this._steps = s.steps || [];
        this._scenarioTags = s.tags || [];
        const appr = document.getElementById('schedApproved');
        if (appr) appr.checked = !!s.schedule_approved;
        document.getElementById('btnRunScenario').disabled = false;
      } catch (err) {
        MC.showToast(`Failed to load scenario: ${err.message}`, 'danger');
      }
    }
    this._renderSteps();
    this._renderScenarioTags();
  },

  _addStep() {
    const type = document.getElementById('stepTypeSelect').value;
    this._steps.push({type, params: {}, on_error: 'stop'});
    this._renderSteps();
  },

  _renderSteps() {
    const list = document.getElementById('stepList');
    const empty = document.getElementById('stepEmpty');
    if (!this._steps.length) {
      list.querySelectorAll('.mc-step-row').forEach(n => n.remove());
      empty.classList.remove('d-none');
      return;
    }
    empty.classList.add('d-none');
    list.querySelectorAll('.mc-step-row').forEach(n => n.remove());
    const tpl = document.getElementById('tplStepRow');
    this._steps.forEach((step, i) => {
      const node = tpl.content.firstElementChild.cloneNode(true);
      node.dataset.stepType = step.type;
      node.querySelector('.mc-step-index').textContent = i + 1;
      node.querySelector('.mc-step-title').textContent = this._stepLabel(step.type);
      node.querySelector('.mc-step-on-error').value = step.on_error || 'stop';
      node.querySelector('.mc-step-bypass').checked = !!(step.params && step.params.bypass_triggers);

      const paramsHost = node.querySelector('.mc-step-params');
      for (const field of this._stepSchema(step.type)) {
        const col = document.createElement('div');
        col.className = 'col-12';
        const id = `step${i}_${field.key}`;
        const label = `<label class="form-label fw-semibold small mb-1">${MC._escHtml(field.label)}</label>`;
        const val = (step.params && step.params[field.key] != null)
                    ? (field.json ? JSON.stringify(step.params[field.key]) : step.params[field.key])
                    : '';
        if (field.type === 'checkbox') {
          col.innerHTML = `
            <div class="form-check">
              <input id="${id}" type="checkbox" class="form-check-input" data-key="${field.key}" ${val ? 'checked' : ''}>
              <label class="form-check-label small" for="${id}">${MC._escHtml(field.label)}</label>
            </div>`;
        } else if (field.textarea) {
          col.innerHTML = `${label}
            <textarea id="${id}" data-key="${field.key}" rows="2" class="form-control form-control-sm"
                      placeholder="${MC._escHtml(field.placeholder || '')}">${MC._escHtml(val)}</textarea>`;
        } else {
          col.innerHTML = `${label}
            <input id="${id}" type="text" data-key="${field.key}" class="form-control form-control-sm"
                   value="${MC._escHtml(val)}" placeholder="${MC._escHtml(field.placeholder || '')}">`;
        }
        paramsHost.appendChild(col);
      }

      // Wiring
      paramsHost.querySelectorAll('[data-key]').forEach(input => {
        input.addEventListener('change', (e) => this._updateParam(i, e.target));
        input.addEventListener('blur', (e) => this._updateParam(i, e.target));
      });
      node.querySelector('.mc-step-on-error').addEventListener('change', (e) => {
        this._steps[i].on_error = e.target.value;
      });
      node.querySelector('.mc-step-bypass').addEventListener('change', (e) => {
        this._steps[i].params = this._steps[i].params || {};
        this._steps[i].params.bypass_triggers = e.target.checked;
      });
      node.querySelector('.mc-step-up').addEventListener('click', () => this._move(i, -1));
      node.querySelector('.mc-step-down').addEventListener('click', () => this._move(i, +1));
      node.querySelector('.mc-step-remove').addEventListener('click', () => {
        this._steps.splice(i, 1); this._renderSteps();
      });
      list.appendChild(node);
    });
  },

  _updateParam(stepIdx, inputEl) {
    const key = inputEl.dataset.key;
    const schema = this._stepSchema(this._steps[stepIdx].type).find(f => f.key === key);
    let value;
    if (schema?.type === 'checkbox') value = inputEl.checked;
    else if (schema?.json) {
      try { value = JSON.parse(inputEl.value || '{}'); inputEl.classList.remove('is-invalid'); }
      catch (e) { inputEl.classList.add('is-invalid'); return; }
    }
    else value = inputEl.value;
    this._steps[stepIdx].params = this._steps[stepIdx].params || {};
    this._steps[stepIdx].params[key] = value;
  },

  _move(i, dir) {
    const j = i + dir;
    if (j < 0 || j >= this._steps.length) return;
    [this._steps[i], this._steps[j]] = [this._steps[j], this._steps[i]];
    this._renderSteps();
  },

  _renderScenarioTags() {
    const host = document.getElementById('scenTags');
    if (!host) return;
    if (!this._scenarioTags.length) {
      host.innerHTML = '<span class="text-muted small">No tags attached.</span>';
      return;
    }
    host.innerHTML = this._scenarioTags.map(t => `
      <span class="badge badge-${MC._escHtml(t.color || 'slate')}">
        ${MC._escHtml(t.name)}
        <a href="#" class="text-white ms-1" data-detach="${t.id}" title="Detach">&times;</a>
      </span>`).join('');
    host.querySelectorAll('[data-detach]').forEach(a => {
      a.addEventListener('click', async (e) => {
        e.preventDefault();
        const id = parseInt(a.dataset.detach, 10);
        if (!this._scenarioId) {
          this._scenarioTags = this._scenarioTags.filter(t => t.id !== id);
          this._renderScenarioTags();
          return;
        }
        try {
          await MC.api(`/scenarios/${this._scenarioId}/tags/${id}`, 'DELETE');
          this._scenarioTags = this._scenarioTags.filter(t => t.id !== id);
          this._renderScenarioTags();
        } catch (err) { MC.showToast(err.message, 'danger'); }
      });
    });
  },

  async _manageTags() {
    if (!this._scenarioId) {
      MC.showToast('Save the scenario before attaching tags.', 'info');
      return;
    }
    const tags = await MC.api('/scenarios/tags');
    const attached = new Set(this._scenarioTags.map(t => t.id));
    const choice = prompt(
      'Type tag name to attach (existing tag will be reused, new tag will be created):\n\n' +
      'Existing: ' + (tags.map(t => t.name).join(', ') || '(none)')
    );
    if (!choice) return;
    const name = choice.trim();
    let tag = tags.find(t => t.name.toLowerCase() === name.toLowerCase());
    try {
      if (!tag) {
        tag = await MC.api('/scenarios/tags', 'POST', {name});
      }
      if (attached.has(tag.id)) {
        MC.showToast(`Tag '${tag.name}' already attached.`, 'info');
        return;
      }
      await MC.api(`/scenarios/${this._scenarioId}/tags/${tag.id}`, 'POST');
      this._scenarioTags.push({id: tag.id, name: tag.name, color: tag.color});
      this._renderScenarioTags();
    } catch (err) { MC.showToast(err.message, 'danger'); }
  },

  async _save() {
    const name = document.getElementById('scenName').value.trim();
    const description = document.getElementById('scenDescription').value.trim();
    if (!name) { MC.showToast('Name is required', 'warning'); return; }
    const body = {name, description, steps: this._steps};
    try {
      const url = this._scenarioId
        ? `/scenarios/update/${this._scenarioId}`
        : '/scenarios/create';
      const saved = await MC.api(url, 'POST', body);
      if (!this._scenarioId) {
        // Move to the canonical URL so further saves go through update.
        window.location.href = `/scenarios/${saved.id}`;
        return;
      }
      this._steps = saved.steps || [];
      document.getElementById('builderTitle').textContent = saved.name;
      MC.showToast('Scenario saved', 'success');
    } catch (err) { MC.showToast(err.message, 'danger'); }
  },

  async _run() {
    if (!this._scenarioId) {
      MC.showToast('Save the scenario before running.', 'info');
      return;
    }
    MC.showSpinner();
    try {
      const result = await MC.api(`/scenarios/${this._scenarioId}/run`, 'POST');
      this._renderRunResult(result);
      const fails = (result.step_results || []).filter(r => r.status === 'failed').length;
      const type = result.status === 'success' ? 'success'
                   : result.status === 'partial' ? 'warning' : 'danger';
      MC.showToast(`Run ${result.status} — ${(result.step_results || []).length} step(s), ${fails} failed.`, type);
    } catch (err) {
      MC.showToast(`Run failed: ${err.message}`, 'danger');
    } finally { MC.hideSpinner(); }
  },

  _renderRunResult(result) {
    const card = document.getElementById('runResultCard');
    const body = document.getElementById('runResultBody');
    const badge = document.getElementById('runStatusBadge');
    card.classList.remove('d-none');
    const status = result.status || 'unknown';
    const cls = status === 'success' ? 'badge-green' : status === 'partial' ? 'badge-amber' : 'badge-red';
    badge.innerHTML = `<span class="badge ${cls}">${MC._escHtml(status.toUpperCase())}</span>`;
    body.innerHTML = (result.step_results || []).map(r => {
      const rowCls = r.status === 'success' ? 'badge-green' : 'badge-red';
      const detail = typeof r.detail === 'object' ? JSON.stringify(r.detail) : (r.detail || '');
      return `<tr>
        <td>${r.step_index}</td>
        <td>${MC._escHtml(r.step_type)}</td>
        <td><span class="badge ${rowCls}">${MC._escHtml(r.status.toUpperCase())}</span></td>
        <td class="text-muted small">${MC._escHtml(detail).slice(0, 300)}</td>
      </tr>`;
    }).join('');
  },

  // ── Scheduling (Argo) ──────────────────────────────────────────────────

  async _toggleApproved(e) {
    const box = e.target;
    if (!this._scenarioId) {
      MC.showToast('Save the scenario before approving.', 'info');
      box.checked = false; return;
    }
    // Confirm only when turning approval ON (unattended writes).
    if (box.checked) {
      const ok = await MC.confirm({
        title: 'Approve for scheduled runs',
        body: 'Approving lets this scenario run unattended via Argo on a schedule — '
            + 'it performs its writes with no one watching. Only approve after '
            + 'testing it interactively.',
        confirmText: 'Approve',
        requireAck: true,
      });
      if (!ok) { box.checked = false; return; }
    }
    try {
      await MC.api(`/scenarios/${this._scenarioId}/approve`, 'POST',
                   {approved: box.checked});
      MC.showToast(box.checked ? 'Approved for scheduled runs' : 'Approval removed',
                   box.checked ? 'success' : 'info');
    } catch (err) {
      MC.showToast(err.message, 'danger');
      box.checked = !box.checked;  // revert on failure
    }
  },

  async _genManifest() {
    if (!this._scenarioId) { MC.showToast('Save the scenario first.', 'info'); return; }
    const schedule = document.getElementById('schedCron').value.trim();
    try {
      const data = await MC.api(`/scenarios/${this._scenarioId}/argo-manifest`,
                                'POST', {schedule});
      document.getElementById('manifestText').value = data.manifest;
      bootstrap.Modal.getOrCreateInstance(document.getElementById('manifestModal')).show();
    } catch (err) {
      MC.showToast(err.message, 'danger');
    }
  },
};

document.addEventListener('DOMContentLoaded', () => MC.scenarios.init());
