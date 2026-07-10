/* mc-cli-snippet.js — CLI tab: guided sf-CLI script + metadata-package builder.
 * Companion to templates/cli/index.html.
 *
 * Flow: setup inputs (alias/project) + a describe-driven field builder feed an
 * in-memory plan. A debounced call to POST /cli/generate re-renders every
 * command box from the server (single source of truth for the generated
 * scripts); POST /cli/package streams the force-app zip. The app only composes
 * commands — nothing here runs sf.
 */
MC.cli = {

  fields: [],            // list of field specs the user has added
  _fieldsCache: {},      // object name -> describe fields (for flip prefill)
  _refreshTimer: null,

  // SF describe type (lowercase) -> our builder type.
  _TYPE_MAP: {
    string: 'Text', textarea: 'LongTextArea', picklist: 'Picklist',
    boolean: 'Checkbox', double: 'Number', int: 'Number', currency: 'Number',
    percent: 'Number', date: 'Date', datetime: 'DateTime', email: 'Email',
    phone: 'Phone', url: 'Url',
  },

  init() {
    const root = document.getElementById('cliRoot');
    if (!root) return;
    document.getElementById('cliInstanceUrl').value = root.dataset.defaultInstanceUrl || '';
    document.getElementById('cliBasePath').value = root.dataset.defaultBasePath || '';

    // Copy buttons for every command box.
    document.querySelectorAll('#cliRoot .mc-code').forEach(box => {
      const btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'btn btn-outline-light btn-sm mc-copy-btn';
      btn.textContent = 'Copy';
      btn.addEventListener('click', () => {
        const target = document.getElementById(box.dataset.copy);
        const text = target ? target.textContent : '';
        if (text.trim()) MC.copyToClipboard(text);
        else MC.showToast('Nothing to copy yet', 'info');
      });
      box.appendChild(btn);
    });

    // Setup inputs → debounced snippet refresh.
    ['cliAlias', 'cliInstanceUrl', 'cliProject', 'cliBasePath'].forEach(id =>
      document.getElementById(id).addEventListener('input', () => this._refresh()));

    // Field builder wiring.
    document.getElementById('cliType').addEventListener('change', () => this._renderProps());
    document.getElementById('cliFieldMode').addEventListener('change', () => this._onModeChange());
    document.getElementById('cliObject').addEventListener('change', () => this._onObjectChange());
    document.getElementById('cliExistingField').addEventListener('change', () => this._prefillFlip());
    document.getElementById('btnAddField').addEventListener('click', () => this._addField());

    // Permission-set inputs affect generated snippets/members.
    ['psName', 'psLabel', 'psDescription'].forEach(id =>
      document.getElementById(id).addEventListener('input', () => this._refresh()));

    document.getElementById('btnPackage').addEventListener('click', () => this._package());

    this._renderProps();
    this._loadObjects();
    this._refresh();
  },

  // ── Setup / snippet refresh ────────────────────────────────────────────────

  _plan() {
    const fieldPerms = this.fields.map(f => ({
      field: `${f.object}.${f.api_name}`,
      readable: f.readable, editable: f.editable,
    }));
    const psName = document.getElementById('psName').value.trim();
    return {
      alias: document.getElementById('cliAlias').value.trim(),
      instance_url: document.getElementById('cliInstanceUrl').value.trim(),
      project: document.getElementById('cliProject').value.trim(),
      base_path: document.getElementById('cliBasePath').value.trim(),
      fields: this.fields,
      permset: psName ? {
        api_name: psName,
        label: document.getElementById('psLabel').value.trim(),
        description: document.getElementById('psDescription').value.trim(),
        field_perms: fieldPerms,
      } : {},
    };
  },

  _refresh() {
    clearTimeout(this._refreshTimer);
    this._refreshTimer = setTimeout(() => this._doRefresh(), 350);
  },

  async _doRefresh() {
    try {
      const s = await MC.api('/cli/generate', 'POST', this._plan());
      const set = (id, val) => { const el = document.getElementById(id); if (el) el.textContent = val || ''; };
      set('snpInstall', s.install);
      set('snpLogin', s.login);
      set('snpProject', s.project);
      set('snpRetrieve', s.retrieve);
      set('snpBackup', s.backup);
      set('snpVerify', s.verify);
      set('snpDeployDry', s.deploy_dry_run);
      set('snpDeployFull', s.deploy_full);
      set('snpAssign', s.assign);
      document.getElementById('flipSection').classList.toggle('d-none', !s.has_flips);
      const proj = document.getElementById('cliProject').value.trim();
      const base = document.getElementById('cliBasePath').value.trim().replace(/[\\/]+$/, '');
      document.getElementById('projPathHint').textContent = proj ? `${base}\\${proj}` : 'your project';
    } catch (err) {
      // Validation errors (e.g. bad field) are expected while editing — surface quietly.
      MC.showToast(err.message, 'warning');
    }
  },

  // ── Objects / fields (describe-driven) ─────────────────────────────────────

  async _loadObjects() {
    const sel = document.getElementById('cliObject');
    try {
      const objs = await MC.api('/cli/objects');
      sel.innerHTML = '<option value="">Select an object…</option>' +
        objs.map(o => `<option value="${MC._escHtml(o.name)}">${MC._escHtml(o.name)}${o.label && o.label !== o.name ? ` — ${MC._escHtml(o.label)}` : ''}</option>`).join('');
    } catch (err) {
      sel.innerHTML = '<option value="">Failed to load objects</option>';
      MC.showToast(`Could not load objects: ${err.message}`, 'danger');
    }
  },

  async _onObjectChange() {
    const obj = document.getElementById('cliObject').value;
    if (obj && !this._fieldsCache[obj]) {
      try {
        const data = await MC.api(`/cli/objects/${encodeURIComponent(obj)}/fields`);
        this._fieldsCache[obj] = data.fields || [];
      } catch (err) {
        this._fieldsCache[obj] = [];
        MC.showToast(`Could not describe ${obj}: ${err.message}`, 'danger');
      }
    }
    this._populateExistingFields();
  },

  _populateExistingFields() {
    const obj = document.getElementById('cliObject').value;
    const sel = document.getElementById('cliExistingField');
    const fields = (this._fieldsCache[obj] || []).filter(f => f.custom);
    sel.innerHTML = '<option value="">Select a field…</option>' +
      fields.map(f => `<option value="${MC._escHtml(f.name)}">${MC._escHtml(f.name)}${f.externalId ? ' (already External ID)' : ''}</option>`).join('');
  },

  _onModeChange() {
    const flip = document.getElementById('cliFieldMode').value === 'flip';
    document.getElementById('existingFieldWrap').style.display = flip ? '' : 'none';
    if (flip) this._populateExistingFields();
  },

  _prefillFlip() {
    const obj = document.getElementById('cliObject').value;
    const name = document.getElementById('cliExistingField').value;
    const field = (this._fieldsCache[obj] || []).find(f => f.name === name);
    if (!field) return;
    const type = this._TYPE_MAP[field.type] || 'Text';
    if (!Array.from(document.getElementById('cliType').options).some(o => o.value === type)) {
      MC.showToast(`Field type "${field.type}" can't be flipped here — External ID needs Text/Number/Email.`, 'warning');
      return;
    }
    document.getElementById('cliApiName').value = field.name;
    document.getElementById('cliLabel').value = field.label || field.name;
    document.getElementById('cliType').value = type;
    this._renderProps();
    // Prefill from the existing spec so a redeploy preserves attributes; force External ID on.
    const setVal = (id, v) => { const el = document.getElementById(id); if (el) { if (el.type === 'checkbox') el.checked = !!v; else el.value = v; } };
    setVal('propLength', field.length || 255);
    setVal('propExternalId', true);
    setVal('propUnique', field.unique);
    setVal('propCaseSensitive', false);
  },

  // ── Type-specific property inputs ──────────────────────────────────────────

  _renderProps() {
    const type = document.getElementById('cliType').value;
    const host = document.getElementById('cliProps');
    const col = (inner) => `<div class="col-auto">${inner}</div>`;
    const num = (id, label, val, w = 90) =>
      `<label class="form-label fw-semibold small mb-1 d-block">${label}</label>
       <input type="number" id="${id}" class="form-control form-control-sm" value="${val}" style="width:${w}px">`;
    const chk = (id, label, checked) =>
      `<div class="form-check mt-4"><input class="form-check-input" type="checkbox" id="${id}"${checked ? ' checked' : ''}>
       <label class="form-check-label small" for="${id}">${label}</label></div>`;
    let html = '';
    if (type === 'Text') {
      html = col(num('propLength', 'Length', 255)) + col(chk('propExternalId', 'External ID', false)) +
             col(chk('propUnique', 'Unique', false)) + col(chk('propCaseSensitive', 'Case sensitive', false));
    } else if (type === 'TextArea') {
      html = '';
    } else if (type === 'LongTextArea') {
      html = col(num('propLength', 'Length', 32768, 110)) + col(num('propVisibleLines', 'Visible lines', 3, 110));
    } else if (type === 'Number') {
      html = col(num('propPrecision', 'Precision', 18)) + col(num('propScale', 'Scale', 0)) +
             col(chk('propExternalId', 'External ID', false)) + col(chk('propUnique', 'Unique', false));
    } else if (type === 'Email') {
      html = col(chk('propExternalId', 'External ID', false)) + col(chk('propUnique', 'Unique', false));
    } else if (type === 'Checkbox') {
      html = col(chk('propDefaultValue', 'Default checked', false));
    } else if (type === 'Picklist') {
      html = `<div class="col-12">
        <label class="form-label fw-semibold small mb-1">Values <span class="text-muted fw-normal">(one per line — <code>CODE=Label</code>; prefix <code>-</code> to retire/deactivate)</span></label>
        <textarea id="propPicklist" class="form-control form-control-sm" rows="4" placeholder="MAJ=Major, Faculty&#10;MIN=Minor, Faculty&#10;-Major=Major"></textarea>
        <div class="form-check mt-2"><input class="form-check-input" type="checkbox" id="propRestricted" checked>
          <label class="form-check-label small" for="propRestricted">Restricted (reject values not in the set)</label></div>
      </div>`;
    }
    host.innerHTML = html;
  },

  _parsePicklist(text) {
    const values = [];
    (text || '').split('\n').forEach(line => {
      let raw = line.trim();
      if (!raw) return;
      let active = true;
      if (raw.startsWith('-')) { active = false; raw = raw.slice(1).trim(); }
      const eq = raw.indexOf('=');
      const value = (eq >= 0 ? raw.slice(0, eq) : raw).trim();
      const label = (eq >= 0 ? raw.slice(eq + 1) : raw).trim();
      if (value) values.push({ value, label: label || value, default: false, active });
    });
    return values;
  },

  // ── Add / remove fields ────────────────────────────────────────────────────

  _readForm() {
    const g = id => document.getElementById(id);
    const chk = id => { const el = g(id); return el ? el.checked : false; };
    const numv = (id, d) => { const el = g(id); return el && el.value !== '' ? parseInt(el.value, 10) : d; };
    const type = g('cliType').value;
    const spec = {
      object: g('cliObject').value.trim(),
      api_name: g('cliApiName').value.trim(),
      label: g('cliLabel').value.trim(),
      type,
      mode: g('cliFieldMode').value,
      description: g('cliDescription').value.trim(),
      readable: chk('cliReadable'),
      editable: chk('cliEditable'),
    };
    if (type === 'Text') {
      spec.length = numv('propLength', 255);
      spec.externalId = chk('propExternalId');
      spec.unique = chk('propUnique');
      spec.caseSensitive = chk('propCaseSensitive');
    } else if (type === 'LongTextArea') {
      spec.length = numv('propLength', 32768);
      spec.visibleLines = numv('propVisibleLines', 3);
    } else if (type === 'Number') {
      spec.precision = numv('propPrecision', 18);
      spec.scale = numv('propScale', 0);
      spec.externalId = chk('propExternalId');
      spec.unique = chk('propUnique');
    } else if (type === 'Email') {
      spec.externalId = chk('propExternalId');
      spec.unique = chk('propUnique');
    } else if (type === 'Checkbox') {
      spec.defaultValue = chk('propDefaultValue');
    } else if (type === 'Picklist') {
      spec.picklist = { restricted: chk('propRestricted'), sorted: false, values: this._parsePicklist(g('propPicklist').value) };
    }
    return spec;
  },

  _addField() {
    const spec = this._readForm();
    if (!spec.object) { MC.showToast('Pick an object first', 'warning'); return; }
    if (!spec.api_name) { MC.showToast('Field API name is required', 'warning'); return; }
    if (!spec.api_name.endsWith('__c')) { MC.showToast('Custom field API name must end with "__c"', 'warning'); return; }
    if (spec.type === 'Picklist' && !(spec.picklist.values || []).length) {
      MC.showToast('Add at least one picklist value', 'warning'); return;
    }
    if (this.fields.some(f => f.object === spec.object && f.api_name === spec.api_name)) {
      MC.showToast(`${spec.object}.${spec.api_name} is already in the list`, 'warning'); return;
    }
    this.fields.push(spec);
    this._renderFields();
    // Reset the field-identity inputs for the next add; keep object selected.
    ['cliApiName', 'cliLabel', 'cliDescription'].forEach(id => document.getElementById(id).value = '');
    this._refresh();
  },

  _attrsSummary(f) {
    const bits = [];
    if (f.externalId) bits.push('ExtId');
    if (f.unique) bits.push('Unique');
    if (f.type === 'Text' || f.type === 'LongTextArea') bits.push(`len ${f.length}`);
    if (f.type === 'Number') bits.push(`${f.precision},${f.scale}`);
    if (f.type === 'Picklist') bits.push(`${(f.picklist.values || []).length} values`);
    if (f.type === 'Checkbox') bits.push(f.defaultValue ? 'default ✓' : 'default ✗');
    return bits.join(' · ') || '—';
  },

  _renderFields() {
    const tbody = document.getElementById('fieldTbody');
    const table = document.getElementById('fieldTable');
    const empty = document.getElementById('fieldEmpty');
    if (!this.fields.length) { table.classList.add('d-none'); empty.classList.remove('d-none'); return; }
    empty.classList.add('d-none'); table.classList.remove('d-none');
    tbody.innerHTML = this.fields.map((f, i) => `
      <tr>
        <td>${MC._escHtml(f.object)}</td>
        <td><code>${MC._escHtml(f.api_name)}</code></td>
        <td>${MC._escHtml(f.type)}</td>
        <td>${f.mode === 'flip' ? '<span class="badge badge-amber">flip</span>' : '<span class="badge badge-slate">create</span>'}</td>
        <td class="small text-muted">${MC._escHtml(this._attrsSummary(f))}</td>
        <td class="small">${f.readable ? 'R' : ''}${f.editable ? 'W' : ''}${!f.readable && !f.editable ? '—' : ''}</td>
        <td class="text-end"><button class="btn btn-outline-danger btn-sm" data-del="${i}">&times;</button></td>
      </tr>`).join('');
    tbody.querySelectorAll('[data-del]').forEach(b =>
      b.addEventListener('click', () => {
        this.fields.splice(parseInt(b.dataset.del, 10), 1);
        this._renderFields();
        this._refresh();
      }));
  },

  // ── Package download ───────────────────────────────────────────────────────

  async _package() {
    if (!this.fields.length && !document.getElementById('psName').value.trim()) {
      MC.showToast('Add at least one field (or a permission set) to package', 'warning'); return;
    }
    MC.showSpinner();
    try {
      const resp = await fetch('/cli/package', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(this._plan()),
      });
      if (!resp.ok) {
        let msg = 'Package build failed';
        try { msg = (await resp.json()).error || msg; } catch (_) {}
        MC.showToast(msg, 'danger'); return;
      }
      const blob = await resp.blob();
      const disp = resp.headers.get('Content-Disposition') || '';
      const m = disp.match(/filename="?([^"]+)"?/);
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url; a.download = m ? m[1] : 'sf-cli-package.zip'; a.click();
      URL.revokeObjectURL(url);
      MC.showToast('Package downloaded', 'success');
    } catch (err) {
      MC.showToast(err.message, 'danger');
    } finally { MC.hideSpinner(); }
  },
};

document.addEventListener('DOMContentLoaded', () => MC.cli.init());
