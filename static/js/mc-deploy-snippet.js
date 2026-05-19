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
