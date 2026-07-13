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
  _apiNameEdited: false, // once the user hand-edits the API name, stop auto-deriving
  _editIndex: null,      // index of the field being edited in place (null = adding new)
  _layoutXml: null,      // last-built modified layout XML (for download)
  _rtXml: null,          // last-built modified record-type XML (for download)

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
    // Label drives the API name (Setup-style) until the user hand-edits the API name.
    document.getElementById('cliLabel').addEventListener('input', () => this._syncApiName());
    document.getElementById('cliApiName').addEventListener('input', (e) => {
      this._apiNameEdited = e.target.value.trim() !== '';
    });
    document.getElementById('cliType').addEventListener('change', () => this._renderProps());
    document.getElementById('cliFieldMode').addEventListener('change', () => this._onModeChange());
    document.getElementById('cliObject').addEventListener('change', () => this._onObjectChange());
    document.getElementById('cliExistingField').addEventListener('change', () => this._prefillFlip());
    document.getElementById('btnAddField').addEventListener('click', () => this._addField());

    // Permission-set inputs affect generated snippets/members.
    ['psName', 'psLabel', 'psDescription'].forEach(id =>
      document.getElementById(id).addEventListener('input', () => this._refresh()));

    // Visibility clone: read FLS from a source org; human-permset inputs.
    document.getElementById('btnReadFls').addEventListener('click', () => this._readFls());
    ['hpsName', 'hpsLabel', 'cliExistingFields'].forEach(id =>
      document.getElementById(id).addEventListener('input', () => this._refresh()));
    ['hpsEditable', 'hpsReadonlyCompanion'].forEach(id =>
      document.getElementById(id).addEventListener('change', () => this._refresh()));
    document.getElementById('btnLoadExistingFields').addEventListener('click', () => this._loadExistingFields());
    // Default the FLS source org to a non-active org (e.g. EDA).
    const flsOrg = document.getElementById('cliFlsOrg');
    const other = Array.from(flsOrg.options).map(o => o.value).find(v => v !== MC.activeOrg());
    if (other) flsOrg.value = other;

    // Page layout card.
    document.getElementById('cliLayoutName').addEventListener('input', () => this._refresh());
    document.querySelectorAll('input[name="layoutMode"]').forEach(r =>
      r.addEventListener('change', () => this._onLayoutMode()));
    document.getElementById('btnLayoutSections').addEventListener('click', () => this._loadLayoutSections());
    document.getElementById('btnLayoutFillFields').addEventListener('click', () => this._fillLayoutFields());
    document.getElementById('btnBuildLayout').addEventListener('click', () => this._buildLayout());
    document.getElementById('btnDownloadLayout').addEventListener('click', () => this._downloadLayout());

    // Record type card.
    document.getElementById('cliRtName').addEventListener('input', () => this._refresh());
    document.getElementById('btnBuildRt').addEventListener('click', () => this._buildRt());
    document.getElementById('btnDownloadRt').addEventListener('click', () => this._downloadRt());

    // Command composer.
    document.getElementById('cliRecipeObject').addEventListener('change', () => this._onRecipeObjectChange());
    document.getElementById('cliRecipeFields').addEventListener('change', () => this._refreshRecipes());

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
      human_permset: this._humanPermset(),
      existing_fields: this._existingFields(),
      layout_name: document.getElementById('cliLayoutName').value.trim(),
      recordtype_name: document.getElementById('cliRtName').value.trim(),
    };
  },

  _existingFields() {
    return document.getElementById('cliExistingFields').value
      .split('\n').map(s => s.trim()).filter(Boolean);
  },

  _humanPermset() {
    const name = document.getElementById('hpsName').value.trim();
    if (!name) return {};
    return {
      api_name: name,
      label: document.getElementById('hpsLabel').value.trim(),
      editable: document.getElementById('hpsEditable').checked,
      readonly_companion: document.getElementById('hpsReadonlyCompanion').checked,
    };
  },

  async _loadExistingFields() {
    const obj = document.getElementById('cliExistingObj').value.trim();
    if (!obj) { MC.showToast('Enter an object first', 'warning'); return; }
    try {
      const data = await MC.api(`/cli/objects/${encodeURIComponent(obj)}/fields`);
      const custom = (data.fields || []).filter(f => f.custom).map(f => `${obj}.${f.name}`);
      if (!custom.length) { MC.showToast(`No custom fields found on ${obj}`, 'info'); return; }
      const ta = document.getElementById('cliExistingFields');
      const have = new Set(ta.value.split('\n').map(s => s.trim()).filter(Boolean));
      custom.forEach(c => have.add(c));
      ta.value = [...have].join('\n');
      this._refresh();
      MC.showToast(`Loaded ${custom.length} custom fields from ${obj}`, 'success');
    } catch (e) { MC.showToast(e.message, 'danger'); }
  },

  // ── Visibility: clone FLS from a source org ────────────────────────────────

  async _readFls() {
    const org = document.getElementById('cliFlsOrg').value;
    const object = document.getElementById('cliFlsObject').value.trim();
    const field = document.getElementById('cliFlsField').value.trim();
    if (!object || !field) { MC.showToast('Enter a reference object and field', 'warning'); return; }
    const loading = document.getElementById('flsLoading');
    loading.classList.remove('d-none');
    document.getElementById('flsContent').classList.add('d-none');
    try {
      const r = await MC.api(`/cli/fls?org=${encodeURIComponent(org)}`
        + `&object=${encodeURIComponent(object)}&field=${encodeURIComponent(field)}`);
      this._renderFls(r, org);
    } catch (e) {
      MC.showToast(`FLS read failed: ${e.message}`, 'danger');
    } finally { loading.classList.add('d-none'); }
  },

  _renderFls(r, org) {
    const s = r.summary || {};
    document.getElementById('flsContent').classList.remove('d-none');
    const profs = (s.read_profiles || []).join(', ') || '—';
    document.getElementById('flsSummary').innerHTML =
      `<code>${MC._escHtml(r.field)}</code> in <strong>${MC._escHtml(org)}</strong>: `
      + `visible to <strong>${s.read_count || 0}</strong> profile(s)/perm set(s), `
      + `<strong>${s.edit_count || 0}</strong> with edit. `
      + `<span class="text-muted">Assign the new set to users on: ${MC._escHtml(profs)}.</span>`;
    const parents = r.parents || [];
    document.getElementById('flsTbody').innerHTML = parents.length ? parents.map(p => `
      <tr><td>${MC._escHtml(p.name)}</td><td>${MC._escHtml(p.type)}</td>
      <td>${p.read ? '<span class="badge badge-green">read</span>' : ''}</td>
      <td>${p.edit ? '<span class="badge badge-amber">edit</span>' : ''}</td></tr>`).join('')
      : '<tr><td colspan="4" class="text-muted">No FLS found — the field may be hidden for everyone in that org.</td></tr>';
    // Match the human permset's edit level to the source field.
    document.getElementById('hpsEditable').checked = !!s.suggested_editable;
    this._refresh();
  },

  // ── Page layout: add fields to a pasted layout ─────────────────────────────

  _onLayoutMode() {
    const mode = document.querySelector('input[name="layoutMode"]:checked').value;
    document.getElementById('layoutNewWrap').style.display = mode === 'new' ? '' : 'none';
    document.getElementById('layoutExistingWrap').style.display = mode === 'existing' ? '' : 'none';
  },

  async _loadLayoutSections() {
    const xml = document.getElementById('cliLayoutXml').value;
    if (!xml.trim()) { MC.showToast('Paste the layout XML first', 'warning'); return; }
    try {
      const r = await MC.api('/cli/layout/sections', 'POST', { layout_xml: xml });
      const editable = (r.sections || []).filter(s => s.has_editable_column);
      document.getElementById('cliLayoutSection').innerHTML =
        '<option value="">Select a section…</option>' +
        editable.map(s => `<option value="${MC._escHtml(s.label)}">${MC._escHtml(s.label)}</option>`).join('');
      if (!editable.length) MC.showToast('No editable sections found in that layout', 'warning');
    } catch (e) { MC.showToast(e.message, 'danger'); }
  },

  _fillLayoutFields() {
    const names = this.fields.map(f => f.api_name)
      .concat(this._existingFields().map(ef => ef.split('.').pop()));
    document.getElementById('cliLayoutFields').value = [...new Set(names.filter(Boolean))].join('\n');
  },

  async _buildLayout() {
    const xml = document.getElementById('cliLayoutXml').value;
    if (!xml.trim()) { MC.showToast('Paste the layout XML first', 'warning'); return; }
    const fields = document.getElementById('cliLayoutFields').value
      .split('\n').map(s => s.trim()).filter(Boolean);
    if (!fields.length) { MC.showToast('Add fields to place (or click "fill from my fields")', 'warning'); return; }
    const mode = document.querySelector('input[name="layoutMode"]:checked').value;
    const body = { layout_xml: xml, fields, behavior: document.getElementById('cliLayoutBehavior').value };
    if (mode === 'new') body.new_section = document.getElementById('cliLayoutNewSection').value.trim() || 'New Fields';
    else body.section = document.getElementById('cliLayoutSection').value;
    MC.showSpinner();
    try {
      const r = await MC.api('/cli/layout', 'POST', body);
      this._layoutXml = r.xml;
      const res = document.getElementById('layoutResult');
      res.classList.remove('d-none');
      res.innerHTML = `<span class="badge badge-green">added ${r.added.length}</span> `
        + (r.skipped.length ? `<span class="badge badge-slate">skipped ${r.skipped.length} already on layout</span> ` : '')
        + `<span class="text-muted">${MC._escHtml(r.added.join(', '))}</span>`;
      document.getElementById('layoutDownloadWrap').classList.remove('d-none');
      MC.showToast('Layout built — download it', 'success');
    } catch (e) {
      MC.showToast(`Build failed: ${e.message}`, 'danger');
    } finally { MC.hideSpinner(); }
  },

  _downloadLayout() {
    if (!this._layoutXml) { MC.showToast('Build the layout first', 'info'); return; }
    const name = document.getElementById('cliLayoutName').value.trim() || 'Object-Layout';
    const blob = new Blob([this._layoutXml], { type: 'application/xml' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url; a.download = `${name}.layout-meta.xml`; a.click();
    URL.revokeObjectURL(url);
  },

  // ── Record type: picklist availability ─────────────────────────────────────

  async _buildRt() {
    const xml = document.getElementById('cliRtXml').value;
    if (!xml.trim()) { MC.showToast('Paste the record-type XML first', 'warning'); return; }
    const field = document.getElementById('cliRtField').value.trim();
    if (!field) { MC.showToast('Enter the picklist field', 'warning'); return; }
    const values = document.getElementById('cliRtValues').value
      .split('\n').map(s => s.trim()).filter(Boolean);
    if (!values.length) { MC.showToast('Add at least one value', 'warning'); return; }
    MC.showSpinner();
    try {
      const r = await MC.api('/cli/recordtype', 'POST', {
        rt_xml: xml, field, values,
        default: document.getElementById('cliRtDefault').value.trim(),
      });
      this._rtXml = r.xml;
      const res = document.getElementById('rtResult');
      res.classList.remove('d-none');
      res.innerHTML = `<span class="badge badge-green">added ${r.added.length}</span> `
        + (r.skipped.length ? `<span class="badge badge-slate">skipped ${r.skipped.length} already available</span> ` : '')
        + `<span class="text-muted">${MC._escHtml(r.field)}: ${MC._escHtml(r.added.join(', '))}</span>`;
      document.getElementById('rtDownloadWrap').classList.remove('d-none');
      MC.showToast('Record type built — download it', 'success');
    } catch (e) {
      MC.showToast(`Build failed: ${e.message}`, 'danger');
    } finally { MC.hideSpinner(); }
  },

  _downloadRt() {
    if (!this._rtXml) { MC.showToast('Build the record type first', 'info'); return; }
    const full = document.getElementById('cliRtName').value.trim() || 'Object.RecordType';
    const name = full.includes('.') ? full.split('.').pop() : full;  // file uses the RT dev name only
    const blob = new Blob([this._rtXml], { type: 'application/xml' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url; a.download = `${name}.recordType-meta.xml`; a.click();
    URL.revokeObjectURL(url);
  },

  // ── Command composer ───────────────────────────────────────────────────────

  async _onRecipeObjectChange() {
    const obj = document.getElementById('cliRecipeObject').value;
    const sel = document.getElementById('cliRecipeFields');
    sel.innerHTML = '';
    if (obj) {
      if (!this._fieldsCache[obj]) {
        try {
          const data = await MC.api(`/cli/objects/${encodeURIComponent(obj)}/fields`);
          this._fieldsCache[obj] = data.fields || [];
        } catch (e) { this._fieldsCache[obj] = []; }
      }
      sel.innerHTML = (this._fieldsCache[obj] || [])
        .map(f => `<option value="${MC._escHtml(f.name)}">${MC._escHtml(f.name)}</option>`).join('');
    }
    this._refreshRecipes();
  },

  async _refreshRecipes() {
    const obj = document.getElementById('cliRecipeObject').value;
    const fields = Array.from(document.getElementById('cliRecipeFields').selectedOptions).map(o => o.value);
    try {
      const r = await MC.api('/cli/recipes', 'POST',
        { object: obj, fields, alias: document.getElementById('cliAlias').value.trim() });
      const set = (id, v) => { const el = document.getElementById(id); if (el) el.textContent = v || ''; };
      set('rcpDescribe', r.describe);
      set('rcpQuery', r.query);
      set('rcpCount', r.count);
      set('rcpRetrieve', r.retrieve_object);
    } catch (e) { /* composer is best-effort; ignore */ }
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
      set('snpDeployDir', s.deploy_dir);
      set('snpLayoutRetrieve', s.layout_retrieve);
      set('snpLayoutDeploy', s.layout_deploy);
      set('snpRtRetrieve', s.recordtype_retrieve);
      set('snpRtDeploy', s.recordtype_deploy);
      document.getElementById('flipSection').classList.toggle('d-none', !s.has_flips);
      this._refreshRecipes();  // alias changes flow into the composer recipes too
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
      const optionsFor = (list) => '<option value="">Select an object…</option>' +
        list.map(o => `<option value="${MC._escHtml(o.name)}">${MC._escHtml(o.name)}${o.label && o.label !== o.name ? ` — ${MC._escHtml(o.label)}` : ''}</option>`).join('');
      // Field builder: only objects that accept custom fields (layoutable) —
      // hides ContentDocumentLink / ContentNote / *__Share, which reject custom
      // fields and only fail on deploy.
      sel.innerHTML = optionsFor(objs.filter(o => o.layoutable !== false));
      // Command composer describes/queries — any object is valid there, so it
      // keeps the full list.
      document.getElementById('cliRecipeObject').innerHTML = optionsFor(objs);
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
    else this._apiNameEdited = false;  // back to create → re-enable label→API auto-derive
  },

  // Derive an SF-style API name from a label: "Group Information" -> "Group_Information__c".
  // Collapses runs of non-alphanumerics to one underscore, trims edge underscores,
  // prefixes a leading digit with X, and appends the custom-field __c suffix.
  _deriveApiName(label) {
    let s = (label || '').trim().replace(/[^A-Za-z0-9]+/g, '_').replace(/^_+|_+$/g, '');
    if (!s) return '';
    if (/^[0-9]/.test(s)) s = 'X' + s;
    return s + '__c';
  },

  _syncApiName() {
    if (this._apiNameEdited) return;
    document.getElementById('cliApiName').value =
      this._deriveApiName(document.getElementById('cliLabel').value);
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
    this._apiNameEdited = true;  // flip uses the real existing API name — don't auto-derive over it
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
        <label class="form-label fw-semibold small mb-1">Values <span class="text-muted fw-normal">(one per line — sets the API value and label to that text; optional <code>CODE=Label</code> to differ them, prefix <code>-</code> to retire)</span></label>
        <textarea id="propPicklist" class="form-control form-control-sm" rows="4" placeholder="Freshman&#10;Sophomore&#10;Junior&#10;Senior"></textarea>
        <div class="form-check mt-2"><input class="form-check-input" type="checkbox" id="propRestricted" checked>
          <label class="form-check-label small" for="propRestricted">Restricted (reject values not in the set)</label></div>
      </div>`;
    } else if (type === 'Lookup') {
      html = `<div class="col-md-4">
          <label class="form-label fw-semibold small mb-1 d-block">Related object <span class="text-muted fw-normal">(must exist in the target)</span></label>
          <input type="text" id="propReferenceTo" data-mc-objpick="queryable" class="form-control form-control-sm" placeholder="e.g. Account" autocomplete="off">
        </div>
        <div class="col-auto">
          <label class="form-label fw-semibold small mb-1 d-block">On parent delete</label>
          <select id="propDeleteConstraint" class="form-select form-select-sm">
            <option value="SetNull">Clear the field (SetNull)</option>
            <option value="Restrict">Prevent deletion (Restrict)</option>
          </select>
        </div>`;
    }
    host.innerHTML = html;
    // Props are re-rendered dynamically, so autowire can't reach them — attach
    // the shared object picker to the Lookup target input by hand.
    if (type === 'Lookup') MC.objectPicker?.attach('propReferenceTo', { capability: 'queryable' });
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
    } else if (type === 'Lookup') {
      spec.referenceTo = g('propReferenceTo').value.trim();
      spec.deleteConstraint = g('propDeleteConstraint').value;
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
    if (spec.type === 'Lookup' && !spec.referenceTo) {
      MC.showToast('A Lookup needs a related object', 'warning'); return;
    }
    // Duplicate check — ignore the row currently being edited.
    const dup = this.fields.findIndex(f => f.object === spec.object && f.api_name === spec.api_name);
    if (dup !== -1 && dup !== this._editIndex) {
      MC.showToast(`${spec.object}.${spec.api_name} is already in the list`, 'warning'); return;
    }
    if (this._editIndex !== null) {
      this.fields[this._editIndex] = spec;   // update in place, keep position
      this._cancelEdit();
    } else {
      this.fields.push(spec);
    }
    this._renderFields();
    // Default the FLS reference object to the field's object (first add only).
    const flsObj = document.getElementById('cliFlsObject');
    if (flsObj && !flsObj.value.trim()) flsObj.value = spec.object;
    // Reset the field-identity inputs for the next add; keep object selected.
    ['cliApiName', 'cliLabel', 'cliDescription'].forEach(id => document.getElementById(id).value = '');
    this._apiNameEdited = false;  // next field re-links label → API name
    this._refresh();
  },

  // ── Edit an existing row ────────────────────────────────────────────────────

  _editField(i) {
    const f = this.fields[i];
    if (!f) return;
    this._editIndex = i;
    this._loadForm(f);
    const btn = document.getElementById('btnAddField');
    btn.textContent = 'Update field';
    btn.classList.remove('btn-doane');
    btn.classList.add('btn-slate');
    document.getElementById('cliObject').scrollIntoView({ behavior: 'smooth', block: 'center' });
  },

  _cancelEdit() {
    this._editIndex = null;
    const btn = document.getElementById('btnAddField');
    btn.textContent = '+ Add field';
    btn.classList.add('btn-doane');
    btn.classList.remove('btn-slate');
  },

  // Populate the whole builder form from a saved field spec.
  _loadForm(f) {
    const g = id => document.getElementById(id);
    const set = (id, v) => { const el = g(id); if (el) { if (el.type === 'checkbox') el.checked = !!v; else el.value = (v == null ? '' : v); } };
    g('cliObject').value = f.object;
    g('cliFieldMode').value = f.mode || 'create';
    this._onModeChange();
    set('cliApiName', f.api_name);
    set('cliLabel', f.label);
    g('cliType').value = f.type;
    this._apiNameEdited = true;   // keep the loaded API name; don't auto-derive over it
    this._renderProps();
    set('propLength', f.length);
    set('propVisibleLines', f.visibleLines);
    set('propPrecision', f.precision);
    set('propScale', f.scale);
    set('propExternalId', f.externalId);
    set('propUnique', f.unique);
    set('propCaseSensitive', f.caseSensitive);
    set('propDefaultValue', f.defaultValue);
    set('propReferenceTo', f.referenceTo);
    set('propDeleteConstraint', f.deleteConstraint || 'SetNull');
    if (f.picklist) {
      set('propRestricted', f.picklist.restricted);
      if (g('propPicklist')) {
        g('propPicklist').value = (f.picklist.values || []).map(v =>
          (v.active === false ? '-' : '') + (v.value === v.label ? v.value : `${v.value}=${v.label}`)
        ).join('\n');
      }
    }
    set('cliDescription', f.description);
    set('cliReadable', f.readable);
    set('cliEditable', f.editable);
  },

  _attrsSummary(f) {
    const bits = [];
    if (f.externalId) bits.push('ExtId');
    if (f.unique) bits.push('Unique');
    if (f.type === 'Text' || f.type === 'LongTextArea') bits.push(`len ${f.length}`);
    if (f.type === 'Number') bits.push(`${f.precision},${f.scale}`);
    if (f.type === 'Picklist') bits.push(`${(f.picklist.values || []).length} values`);
    if (f.type === 'Checkbox') bits.push(f.defaultValue ? 'default ✓' : 'default ✗');
    if (f.type === 'Lookup') bits.push(`→ ${f.referenceTo || '?'}`);
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
        <td class="text-end text-nowrap">
          <button class="btn btn-outline-secondary btn-sm" data-edit="${i}">Edit</button>
          <button class="btn btn-outline-danger btn-sm" data-del="${i}">&times;</button>
        </td>
      </tr>`).join('');
    tbody.querySelectorAll('[data-edit]').forEach(b =>
      b.addEventListener('click', () => this._editField(parseInt(b.dataset.edit, 10))));
    tbody.querySelectorAll('[data-del]').forEach(b =>
      b.addEventListener('click', () => {
        const i = parseInt(b.dataset.del, 10);
        // If we're editing a row, cancel/adjust so the pending edit index stays valid.
        if (this._editIndex !== null) {
          if (this._editIndex === i) this._cancelEdit();
          else if (i < this._editIndex) this._editIndex -= 1;
        }
        this.fields.splice(i, 1);
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

// ── Clone object → package ─────────────────────────────────────────────────
// Describe a source object and turn its custom fields into the same force-app
// package the builder produces. Self-contained: Preview → (clean) Download,
// re-locked on any input change so you never download a stale plan.
MC.cliClone = {
  _lastKey: null,

  init() {
    document.getElementById('btnClonePreview')?.addEventListener('click', () => this.preview());
    document.getElementById('btnClonePackage')?.addEventListener('click', () => this.download());
    ['cliCloneObject', 'cliCloneShell', 'cliClonePermset'].forEach(id => {
      const el = document.getElementById(id);
      el?.addEventListener('change', () => this._lock());
      el?.addEventListener('input', () => this._lock());
    });
  },

  _obj() { return (document.getElementById('cliCloneObject')?.value || '').trim(); },
  _shell() { return document.getElementById('cliCloneShell')?.checked || false; },
  _permset() { return document.getElementById('cliClonePermset')?.checked || false; },
  _key() { return `${this._obj()}|${this._shell()}|${this._permset()}`; },

  _lock() {
    const btn = document.getElementById('btnClonePackage');
    if (btn) btn.disabled = true;
  },

  async preview() {
    const obj = this._obj();
    if (!obj) { MC.showToast('Enter a source object', 'warning'); return; }
    MC.showSpinner();
    try {
      const data = await MC.api('/cli/clone-object/plan', 'POST',
        { object: obj, include_shell: this._shell() });
      this._render(data);
      const btn = document.getElementById('btnClonePackage');
      const nothing = data.fields.length === 0 && !data.shell;
      if (btn) btn.disabled = nothing;
      this._lastKey = nothing ? null : this._key();
      if (nothing) MC.showToast('Nothing to clone — no reproducible custom fields (tick “include the object definition” to at least create the shell).', 'warning');
    } catch (err) {
      MC.showToast('Preview failed: ' + err.message, 'danger');
    } finally { MC.hideSpinner(); }
  },

  _render(d) {
    const c = d.counts;
    document.getElementById('cliCloneSummary').innerHTML =
      `<span class="badge bg-success me-1">clone ${c.custom_fields} field(s)</span>`
      + `<span class="badge bg-${c.skipped ? 'warning' : 'secondary'} me-1">skip ${c.skipped}</span>`
      + `<span class="badge bg-secondary me-1">${c.standard_fields} standard</span>`
      + (d.shell ? '<span class="badge bg-info me-1">+ object shell</span>' : '');
    document.getElementById('cliCloneFieldCount').textContent = d.fields.length;
    document.getElementById('cliCloneSkipCount').textContent = d.skipped.length;
    document.getElementById('cliCloneFields').innerHTML = d.fields.map(f =>
      `<tr><td><code>${MC._escHtml(f.api_name)}</code></td><td>${MC._escHtml(f.type)}</td></tr>`).join('')
      || '<tr><td colspan="2" class="text-muted">None</td></tr>';
    document.getElementById('cliCloneSkipped').innerHTML = d.skipped.map(s =>
      `<tr><td><code>${MC._escHtml(s.api_name)}</code></td><td class="text-muted">${MC._escHtml(s.reason)}</td></tr>`).join('')
      || '<tr><td colspan="2" class="text-muted">None</td></tr>';
    const note = document.getElementById('cliCloneShellNote');
    if (d.shell) {
      note.classList.remove('d-none');
      note.innerHTML = '<strong>Object shell included (best-effort):</strong> '
        + (d.shell.notes || []).map(n => MC._escHtml(n)).join('; ') + '.';
    } else {
      note.classList.add('d-none');
    }
    document.getElementById('cliCloneResult').classList.remove('d-none');
  },

  async download() {
    if (this._lastKey === null || this._key() !== this._lastKey) {
      MC.showToast('Preview the object first (inputs changed).', 'warning');
      this._lock();
      return;
    }
    MC.showSpinner();
    try {
      const resp = await fetch('/cli/clone-object/package', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          object: this._obj(),
          include_shell: this._shell(),
          include_permset: this._permset(),
          project: (document.getElementById('cliProject')?.value || '').trim(),
          alias: (document.getElementById('cliAlias')?.value || '').trim(),
        }),
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

document.addEventListener('DOMContentLoaded', () => { MC.cli.init(); MC.cliClone.init(); });
