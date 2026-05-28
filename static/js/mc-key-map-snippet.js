/* mc-key-map-snippet.js — Key Maps tab: index list, builder, run/preview.
 * Companion to templates/key_map/{index,builder,run}.html.
 * Dispatches by which template rendered (each sets a distinct anchor element).
 */
MC.keyMap = {

  init() {
    if (document.getElementById('kmTbody')) this._initIndex();
    const builder = document.querySelector('[data-key-map-id]');
    if (builder && document.getElementById('familyList')) this._initBuilder();
    if (builder && document.getElementById('btnPreview')) this._initRun();
  },

  // ── INDEX ────────────────────────────────────────────────────────────────

  async _initIndex() {
    try {
      const maps = await MC.api('/key-maps/list');
      const tbody = document.getElementById('kmTbody');
      document.getElementById('kmLoading').classList.add('d-none');
      if (!maps.length) {
        document.getElementById('kmEmpty').classList.remove('d-none');
        return;
      }
      document.getElementById('kmTable').classList.remove('d-none');
      tbody.innerHTML = maps.map(m => `
        <tr>
          <td><a href="/key-maps/${m.id}" class="fw-semibold">${MC._escHtml(m.name)}</a>
            ${m.description ? `<div class="text-muted small">${MC._escHtml(m.description)}</div>` : ''}</td>
          <td><code>${MC._escHtml(m.target_sobject)}</code></td>
          <td class="text-muted small text-nowrap">${MC._fmtTime(m.updated_at)}</td>
          <td class="text-end">
            <a href="/key-maps/${m.id}" class="btn btn-outline-secondary btn-sm">Edit</a>
            <a href="/key-maps/${m.id}/run" class="btn btn-doane btn-sm">Run</a>
            <button class="btn btn-outline-danger btn-sm" data-del="${m.id}"
                    data-mc-confirm="Delete key map '${MC._escHtml(m.name)}'? This cannot be undone."
                    data-mc-confirm-title="Delete key map" data-mc-confirm-btn="Delete">&times;</button>
          </td>
        </tr>`).join('');
      tbody.querySelectorAll('[data-del]').forEach(b =>
        b.addEventListener('click', async () => {
          try { await MC.api(`/key-maps/${b.dataset.del}`, 'DELETE');
                MC.showToast('Deleted', 'success'); this._initIndex(); }
          catch (e) { MC.showToast(e.message, 'danger'); }
        }));
    } catch (err) {
      MC.showToast(`Failed to load key maps: ${err.message}`, 'danger');
    }
  },

  // ── BUILDER ──────────────────────────────────────────────────────────────

  _kmId: null,

  async _initBuilder() {
    const raw = document.querySelector('[data-key-map-id]').dataset.keyMapId;
    this._kmId = (raw === 'new') ? null : parseInt(raw, 10);
    document.getElementById('btnSaveKm').addEventListener('click', () => this._saveKm());
    document.getElementById('btnAddFk').addEventListener('click', () => this._addFk());
    document.getElementById('btnAddFamily').addEventListener('click', () => this._openFamilyModal());
    document.getElementById('btnConfirmFamily').addEventListener('click', () => this._createFamily());
    document.getElementById('btnAddClause').addEventListener('click', () => this._addClauseRow());
    if (this._kmId) await this._loadBuilder();
  },

  async _loadBuilder() {
    const km = await MC.api(`/key-maps/get/${this._kmId}`);
    document.getElementById('kmTitle').textContent = km.name;
    document.getElementById('kmName').value = km.name || '';
    document.getElementById('kmTarget').value = km.target_sobject || '';
    document.getElementById('kmDescription').value = km.description || '';
    const run = document.getElementById('btnGoRun');
    run.href = `/key-maps/${this._kmId}/run`;
    run.classList.remove('d-none');
    this._renderFks(km.fk_lookups || []);
    this._renderFamilies(km.families || []);
  },

  async _saveKm() {
    const body = {
      name: document.getElementById('kmName').value.trim(),
      target_sobject: document.getElementById('kmTarget').value.trim(),
      description: document.getElementById('kmDescription').value.trim(),
    };
    if (!body.name || !body.target_sobject) {
      MC.showToast('Name and Target SObject are required', 'warning'); return;
    }
    try {
      if (this._kmId) {
        await MC.api(`/key-maps/update/${this._kmId}`, 'POST', body);
        MC.showToast('Saved', 'success');
      } else {
        const km = await MC.api('/key-maps/create', 'POST', body);
        window.location.href = `/key-maps/${km.id}`;
      }
    } catch (e) { MC.showToast(e.message, 'danger'); }
  },

  _renderFks(fks) {
    const tbody = document.getElementById('fkTbody');
    const table = document.getElementById('fkTable');
    const empty = document.getElementById('fkEmpty');
    if (!fks.length) { table.classList.add('d-none'); empty.classList.remove('d-none'); return; }
    empty.classList.add('d-none'); table.classList.remove('d-none');
    tbody.innerHTML = fks.map(f => `
      <tr>
        <td><code>${MC._escHtml(f.source_column)}</code></td>
        <td><code>${MC._escHtml(f.target_field)}</code></td>
        <td>${MC._escHtml(f.lookup_sobject)}</td>
        <td>${MC._escHtml(f.lookup_field)}</td>
        <td class="text-end"><button class="btn btn-outline-danger btn-sm" data-fk="${f.id}">&times;</button></td>
      </tr>`).join('');
    tbody.querySelectorAll('[data-fk]').forEach(b =>
      b.addEventListener('click', async () => {
        await MC.api(`/key-maps/fk-lookups/${b.dataset.fk}`, 'DELETE');
        this._loadBuilder();
      }));
  },

  async _addFk() {
    if (!this._kmId) { MC.showToast('Save the key map first', 'info'); return; }
    const body = {
      source_column: document.getElementById('fkSource').value.trim(),
      target_field: document.getElementById('fkTarget').value.trim(),
      lookup_sobject: document.getElementById('fkSobject').value.trim(),
      lookup_field: document.getElementById('fkField').value.trim() || 'SIS_ID__c',
    };
    try {
      await MC.api(`/key-maps/${this._kmId}/fk-lookups`, 'POST', body);
      ['fkSource', 'fkTarget', 'fkSobject'].forEach(id => document.getElementById(id).value = '');
      this._loadBuilder();
    } catch (e) { MC.showToast(e.message, 'danger'); }
  },

  _renderFamilies(families) {
    const host = document.getElementById('familyList');
    const empty = document.getElementById('famEmpty');
    host.querySelectorAll('.mc-family').forEach(n => n.remove());
    if (!families.length) { empty.classList.remove('d-none'); return; }
    empty.classList.add('d-none');
    const tpl = document.getElementById('tplFamily');
    for (const fam of families) {
      const node = tpl.content.firstElementChild.cloneNode(true);
      node.dataset.familyId = fam.id;
      node.querySelector('.mc-family-name').textContent = fam.name;
      const clauses = (fam.routing_json && fam.routing_json.match) || [];
      node.querySelector('.mc-family-routing').textContent = clauses.length
        ? 'when ' + clauses.map(c => `${c.source_column}=${c.equals}`).join(' AND ')
        : '(default — no routing)';
      node.querySelector('.mc-family-del').addEventListener('click', async () => {
        await MC.api(`/key-maps/families/${fam.id}`, 'DELETE'); this._loadBuilder();
      });
      const vbody = node.querySelector('.mc-variant-body');
      vbody.innerHTML = (fam.variants || []).map(v => `
        <tr>
          <td>${MC._escHtml(v.name)}</td>
          <td><code class="small">${MC._escHtml(JSON.stringify(v.overlay_json || {}))}</code></td>
          <td><code class="small text-muted">${MC._escHtml(JSON.stringify((v.applies_when && v.applies_when.match) ? v.applies_when : {}))}</code></td>
          <td class="text-end"><button class="btn btn-outline-danger btn-sm" data-var="${v.id}">&times;</button></td>
        </tr>`).join('');
      vbody.querySelectorAll('[data-var]').forEach(b =>
        b.addEventListener('click', async () => {
          await MC.api(`/key-maps/variants/${b.dataset.var}`, 'DELETE'); this._loadBuilder();
        }));
      node.querySelector('.mc-var-add').addEventListener('click', () => this._addVariant(node, fam.id));
      host.appendChild(node);
    }
  },

  async _addVariant(famNode, familyId) {
    const name = famNode.querySelector('.mc-var-name').value.trim();
    const overlayRaw = famNode.querySelector('.mc-var-overlay').value.trim() || '{}';
    if (!name) { MC.showToast('Variant name required', 'warning'); return; }
    let overlay;
    try { overlay = JSON.parse(overlayRaw); }
    catch (e) { MC.showToast('Overlay must be valid JSON', 'danger'); return; }
    try {
      await MC.api(`/key-maps/families/${familyId}/variants`, 'POST', {name, overlay});
      this._loadBuilder();
    } catch (e) { MC.showToast(e.message, 'danger'); }
  },

  _openFamilyModal() {
    if (!this._kmId) { MC.showToast('Save the key map first', 'info'); return; }
    const name = document.getElementById('famName').value.trim();
    if (!name) { MC.showToast('Family name required', 'warning'); return; }
    document.getElementById('routingClauses').innerHTML = '';
    bootstrap.Modal.getOrCreateInstance(document.getElementById('famRoutingModal')).show();
  },

  _addClauseRow() {
    const host = document.getElementById('routingClauses');
    const div = document.createElement('div');
    div.className = 'row g-1 mb-1 clause-row';
    div.innerHTML = `
      <div class="col"><input class="form-control form-control-sm clause-col" placeholder="source column"></div>
      <div class="col-auto align-self-center">=</div>
      <div class="col"><input class="form-control form-control-sm clause-val" placeholder="value"></div>`;
    host.appendChild(div);
  },

  async _createFamily() {
    const name = document.getElementById('famName').value.trim();
    const clauses = [];
    document.querySelectorAll('#routingClauses .clause-row').forEach(r => {
      const col = r.querySelector('.clause-col').value.trim();
      const val = r.querySelector('.clause-val').value.trim();
      if (col) clauses.push({source_column: col, equals: val});
    });
    const routing = clauses.length ? {match: clauses} : {};
    try {
      await MC.api(`/key-maps/${this._kmId}/families`, 'POST', {name, routing});
      bootstrap.Modal.getInstance(document.getElementById('famRoutingModal')).hide();
      document.getElementById('famName').value = '';
      this._loadBuilder();
    } catch (e) { MC.showToast(e.message, 'danger'); }
  },

  // ── RUN / PREVIEW ────────────────────────────────────────────────────────

  _lastSource: null,

  _initRun() {
    this._kmId = parseInt(document.querySelector('[data-key-map-id]').dataset.keyMapId, 10);
    document.querySelectorAll('input[name="srcMode"]').forEach(r =>
      r.addEventListener('change', () => this._switchPane(r.value)));
    document.getElementById('btnPreview').addEventListener('click', () => this._preview());
    document.getElementById('btnExport').addEventListener('click', () => this._export());
  },

  _switchPane(mode) {
    document.querySelectorAll('.src-pane').forEach(p => p.classList.add('d-none'));
    document.getElementById('pane' + mode.charAt(0).toUpperCase() + mode.slice(1)).classList.remove('d-none');
  },

  _buildSource() {
    const mode = document.querySelector('input[name="srcMode"]:checked').value;
    if (mode === 'sql') return {mode: 'sql', query: document.getElementById('srcSql').value};
    if (mode === 'csv') return {mode: 'csv', data: document.getElementById('srcCsv').value};
    const spec = {mode: 'json', data: document.getElementById('srcJson').value};
    const path = document.getElementById('srcJsonPath').value.trim();
    if (path) spec.records_path = path;
    return spec;
  },

  async _preview() {
    const source = this._buildSource();
    this._lastSource = source;
    MC.showSpinner();
    try {
      const data = await MC.api(`/key-maps/${this._kmId}/preview`, 'POST', {source});
      this._renderPreview(data);
      document.getElementById('btnExport').disabled = false;
    } catch (e) {
      MC.showToast(`Preview failed: ${e.message}`, 'danger');
    } finally { MC.hideSpinner(); }
  },

  _renderPreview(data) {
    document.getElementById('previewEmpty').classList.add('d-none');
    document.getElementById('previewBody').classList.remove('d-none');
    const s = data.summary || {};
    const cls = (data.unresolved_fks || []).length ? 'badge-amber' : 'badge-green';
    document.getElementById('previewBadge').innerHTML =
      `<span class="badge ${cls}">${s.output_count} rows from ${s.source_count} source</span>`;

    const card = (label, val) => `<div class="col-auto"><div class="metric-card py-2 px-3">
        <span class="metric-number" style="font-size:1.4rem">${val}</span>
        <span class="metric-label">${label}</span></div></div>`;
    document.getElementById('previewSummary').innerHTML =
      card('Source rows', s.source_count ?? 0) +
      card('Output rows', s.output_count ?? 0) +
      card('Unresolved FKs', s.unresolved_count ?? 0) +
      card('Skipped (no family)', s.skipped_no_family ?? 0);

    // Output rows table
    const rows = data.sample_rows || [];
    const head = document.getElementById('rowsHead');
    const body = document.getElementById('rowsBody');
    document.getElementById('rowsNote').textContent = data.sample_truncated
      ? `Showing first ${rows.length} of ${s.output_count} rows — export for the full set.` : '';
    if (rows.length) {
      const cols = Object.keys(rows[0]);
      head.innerHTML = '<tr>' + cols.map(c => `<th>${MC._escHtml(c)}</th>`).join('') + '</tr>';
      body.innerHTML = rows.map(r => '<tr>' + cols.map(c =>
        `<td class="small">${MC._escHtml(r[c] == null ? '' : String(r[c]))}</td>`).join('') + '</tr>').join('');
    } else { head.innerHTML = ''; body.innerHTML = '<tr><td class="text-muted">No output rows.</td></tr>'; }

    // Unresolved tab
    const unresolved = data.unresolved_fks || [];
    document.getElementById('unresolvedCount').textContent = s.unresolved_count || 0;
    document.getElementById('unresolvedNote').textContent = data.unresolved_truncated
      ? `Showing first ${unresolved.length} of ${s.unresolved_count}.` : '';
    document.getElementById('unresolvedBody').innerHTML = unresolved.map(u => `
      <tr><td>${u.row_idx}</td><td><code>${MC._escHtml(u.source_column)}</code></td>
          <td>${MC._escHtml(String(u.value))}</td>
          <td class="text-muted small">${MC._escHtml(u.lookup_sobject)}.${MC._escHtml(u.lookup_field)}</td></tr>`).join('')
      || '<tr><td colspan="4" class="text-muted">None — every FK resolved.</td></tr>';
  },

  async _export() {
    const source = this._lastSource || this._buildSource();
    try {
      const resp = await fetch(`/key-maps/${this._kmId}/export`, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({source}),
      });
      if (!resp.ok) {
        let msg = 'Export failed';
        try { msg = (await resp.json()).error || msg; } catch (_) {}
        MC.showToast(msg, 'danger'); return;
      }
      const blob = await resp.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url; a.download = 'key_map_preview.csv'; a.click();
      URL.revokeObjectURL(url);
    } catch (e) { MC.showToast(e.message, 'danger'); }
  },
};

document.addEventListener('DOMContentLoaded', () => MC.keyMap.init());
