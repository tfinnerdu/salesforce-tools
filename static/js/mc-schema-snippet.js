/**
 * MC.snapshots — Schema Snapshot + Change Tracker
 * Appended to mc-schema-snippet.js per project convention.
 */

MC.snapshots = {
  _selected: [],   // array of {id, label} — max 2

  init() {
    document.getElementById('btnTakeSnapshot')?.addEventListener('click', () => this.takeSnapshot());
    document.getElementById('btnRefreshSnapshots')?.addEventListener('click', () => this.loadList());
    document.getElementById('btnFilterSnapshots')?.addEventListener('click', () => this.loadList());
    document.getElementById('btnCompareSelected')?.addEventListener('click', () => this.diffSelected());
    document.getElementById('btnCloseDiff')?.addEventListener('click', () => {
      document.getElementById('snapDiffPanel').classList.add('d-none');
    });

    // Allow Enter in filter inputs to trigger filter
    document.getElementById('filterSobject')?.addEventListener('keydown', e => {
      if (e.key === 'Enter') this.loadList();
    });

    // Load the list on page init
    this.loadList();
  },

  async loadList() {
    const org = document.getElementById('filterOrg')?.value || '';
    const sobject = (document.getElementById('filterSobject')?.value || '').trim();

    const params = new URLSearchParams();
    if (org) params.set('org', org);
    if (sobject) params.set('sobject', sobject);

    document.getElementById('snapListEmpty').classList.add('d-none');
    document.getElementById('snapTableWrap').classList.add('d-none');
    document.getElementById('snapListLoading').classList.remove('d-none');

    try {
      const resp = await fetch('/schema/snapshots/list?' + params.toString());
      const json = await resp.json();
      document.getElementById('snapListLoading').classList.add('d-none');

      if (!json.success) {
        alert('Error loading snapshots: ' + (json.error || 'Unknown error'));
        document.getElementById('snapListEmpty').classList.remove('d-none');
        return;
      }

      this._renderList(json.data || []);
    } catch (err) {
      document.getElementById('snapListLoading').classList.add('d-none');
      document.getElementById('snapListEmpty').classList.remove('d-none');
      alert('Request failed: ' + err.message);
    }
  },

  _renderList(rows) {
    const tbody = document.getElementById('snapTableBody');
    tbody.innerHTML = '';

    if (!rows || rows.length === 0) {
      document.getElementById('snapTableWrap').classList.add('d-none');
      document.getElementById('snapListEmpty').classList.remove('d-none');
      return;
    }

    document.getElementById('snapListEmpty').classList.add('d-none');
    document.getElementById('snapTableWrap').classList.remove('d-none');

    for (const row of rows) {
      const tr = document.createElement('tr');
      tr.dataset.snapId = row.id;
      tr.dataset.snapLabel = row.snapshot_label || String(row.id);

      const isSelected = this._selected.some(s => s.id === row.id);
      if (isSelected) tr.classList.add('table-warning');

      const capturedDisplay = row.captured_at
        ? String(row.captured_at).replace('T', ' ').replace('Z', ' UTC').substring(0, 23)
        : '—';

      const sizeDisplay = row.size != null ? Number(row.size).toLocaleString() : '—';

      tr.innerHTML = `
        <td class="font-monospace">${MC._esc(String(row.id))}</td>
        <td><span class="badge mc-org-badge">${MC._esc(String(row.org || '').toUpperCase())}</span></td>
        <td><code class="small">${MC._esc(String(row.sobject || ''))}</code></td>
        <td>${MC._esc(String(row.snapshot_label || ''))}</td>
        <td class="small text-nowrap">${MC._esc(capturedDisplay)}</td>
        <td class="text-end font-monospace small">${sizeDisplay}</td>
        <td class="no-print">
          <button class="btn btn-sm btn-outline-primary btn-diff me-1" data-id="${row.id}" data-label="${MC._esc(String(row.snapshot_label || row.id))}">
            Diff
          </button>
          <button class="btn btn-sm btn-outline-danger btn-delete" data-id="${row.id}">
            Delete
          </button>
        </td>
      `;
      tbody.appendChild(tr);
    }

    // Wire Diff buttons
    tbody.querySelectorAll('.btn-diff').forEach(btn => {
      btn.addEventListener('click', () => {
        const id = Number(btn.dataset.id);
        const label = btn.dataset.label;
        const idx = this._selected.findIndex(s => s.id === id);

        if (idx >= 0) {
          // Deselect
          this._selected.splice(idx, 1);
        } else {
          if (this._selected.length >= 2) {
            // Replace oldest
            this._selected.shift();
          }
          this._selected.push({ id, label });
        }

        this._updateSelectionUI();
      });
    });

    // Wire Delete buttons
    tbody.querySelectorAll('.btn-delete').forEach(btn => {
      btn.addEventListener('click', () => {
        const id = Number(btn.dataset.id);
        this.deleteSnapshot(id);
      });
    });

    this._updateSelectionUI();
  },

  _updateSelectionUI() {
    const count = this._selected.length;
    const compareBtn = document.getElementById('btnCompareSelected');
    const countSpan = document.getElementById('compareCount');

    if (countSpan) countSpan.textContent = count;

    if (count === 2) {
      compareBtn?.classList.remove('d-none');
    } else {
      compareBtn?.classList.add('d-none');
    }

    // Update row highlights
    document.querySelectorAll('#snapTableBody tr').forEach(tr => {
      const id = Number(tr.dataset.snapId);
      if (this._selected.some(s => s.id === id)) {
        tr.classList.add('table-warning');
      } else {
        tr.classList.remove('table-warning');
      }
    });
  },

  async takeSnapshot() {
    const org = (document.getElementById('snapOrg')?.value || 'dev').trim();
    const sobject = (document.getElementById('snapSobject')?.value || '').trim();
    const label = (document.getElementById('snapLabel')?.value || '').trim();

    if (!sobject) {
      alert('Please enter an SObject name.');
      return;
    }

    const loadingEl = document.getElementById('snapTakeLoading');
    const toastEl = document.getElementById('snapTakeToast');
    const toastMsg = document.getElementById('snapTakeToastMsg');
    const btn = document.getElementById('btnTakeSnapshot');

    loadingEl?.classList.remove('d-none');
    toastEl?.classList.add('d-none');
    if (btn) btn.disabled = true;

    try {
      const resp = await fetch('/schema/snapshots/take', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ sobject, label: label || null }),
      });
      const json = await resp.json();
      loadingEl?.classList.add('d-none');
      if (btn) btn.disabled = false;

      if (!json.success) {
        alert('Error: ' + (json.error || 'Unknown error'));
        return;
      }

      const d = json.data;
      if (toastMsg) {
        toastMsg.textContent = `Snapshot #${d.id} captured — ${MC._esc(d.sobject)} (${d.field_count} fields) labeled "${MC._esc(d.label)}"`;
      }
      toastEl?.classList.remove('d-none');

      // Clear label field and reload list
      const labelInput = document.getElementById('snapLabel');
      if (labelInput) labelInput.value = '';
      this.loadList();
    } catch (err) {
      loadingEl?.classList.add('d-none');
      if (btn) btn.disabled = false;
      alert('Request failed: ' + err.message);
    }
  },

  async diffSelected() {
    if (this._selected.length < 2) {
      alert('Please select exactly 2 snapshots to compare.');
      return;
    }

    const [snapA, snapB] = this._selected;

    const panel = document.getElementById('snapDiffPanel');
    const loadingEl = document.getElementById('snapDiffLoading');
    const contentEl = document.getElementById('snapDiffContent');

    panel?.classList.remove('d-none');
    loadingEl?.classList.remove('d-none');
    contentEl?.classList.add('d-none');

    // Scroll to panel
    panel?.scrollIntoView({ behavior: 'smooth', block: 'start' });

    try {
      const resp = await fetch(`/schema/snapshots/diff?a=${snapA.id}&b=${snapB.id}`);
      const json = await resp.json();
      loadingEl?.classList.add('d-none');

      if (!json.success) {
        alert('Error: ' + (json.error || 'Unknown error'));
        panel?.classList.add('d-none');
        return;
      }

      this._renderDiff(json.data);
      contentEl?.classList.remove('d-none');
    } catch (err) {
      loadingEl?.classList.add('d-none');
      panel?.classList.add('d-none');
      alert('Request failed: ' + err.message);
    }
  },

  _renderDiff(diff) {
    const summary = diff.summary || {};
    const added = diff.added || [];
    const removed = diff.removed || [];
    const changed = diff.changed || [];

    // Title
    const titleEl = document.getElementById('snapDiffTitle');
    if (titleEl) {
      const aLabel = diff.snap_a?.label || String(diff.snap_a?.id || 'A');
      const bLabel = diff.snap_b?.label || String(diff.snap_b?.id || 'B');
      titleEl.textContent = `Schema Diff: ${diff.sobject || ''} — "${aLabel}" vs "${bLabel}"`;
    }

    // Summary badges
    const summaryEl = document.getElementById('snapDiffSummary');
    if (summaryEl) {
      summaryEl.innerHTML = `
        <span class="badge bg-success px-3 py-2 fs-6">${summary.added ?? 0} added</span>
        <span class="badge bg-danger px-3 py-2 fs-6">${summary.removed ?? 0} removed</span>
        <span class="badge bg-warning text-dark px-3 py-2 fs-6">${summary.changed ?? 0} changed</span>
      `;
    }

    // Badge counts in accordion headers
    const addedBadge = document.getElementById('snapAddedBadge');
    const removedBadge = document.getElementById('snapRemovedBadge');
    const changedBadge = document.getElementById('snapChangedBadge');
    if (addedBadge) addedBadge.textContent = summary.added ?? 0;
    if (removedBadge) removedBadge.textContent = summary.removed ?? 0;
    if (changedBadge) changedBadge.textContent = summary.changed ?? 0;

    // Added table
    const addedTbody = document.getElementById('snapAddedTableBody');
    if (addedTbody) {
      if (added.length === 0) {
        addedTbody.innerHTML = '<tr><td colspan="4" class="text-muted text-center py-3">No added fields.</td></tr>';
      } else {
        addedTbody.innerHTML = added.map(f => `
          <tr class="table-success">
            <td><code class="small">${MC._esc(f.name || '')}</code></td>
            <td>${MC._esc(f.label || '')}</td>
            <td><span class="badge rounded-pill bg-light text-dark border font-monospace" style="font-size:0.7em;">${MC._esc(f.type || '')}</span></td>
            <td class="text-end">${f.length != null ? MC._esc(String(f.length)) : '—'}</td>
          </tr>
        `).join('');
      }
    }

    // Removed table
    const removedTbody = document.getElementById('snapRemovedTableBody');
    if (removedTbody) {
      if (removed.length === 0) {
        removedTbody.innerHTML = '<tr><td colspan="4" class="text-muted text-center py-3">No removed fields.</td></tr>';
      } else {
        removedTbody.innerHTML = removed.map(f => `
          <tr class="table-danger">
            <td><code class="small">${MC._esc(f.name || '')}</code></td>
            <td>${MC._esc(f.label || '')}</td>
            <td><span class="badge rounded-pill bg-light text-dark border font-monospace" style="font-size:0.7em;">${MC._esc(f.type || '')}</span></td>
            <td class="text-end">${f.length != null ? MC._esc(String(f.length)) : '—'}</td>
          </tr>
        `).join('');
      }
    }

    // Changed table
    const changedTbody = document.getElementById('snapChangedTableBody');
    if (changedTbody) {
      if (changed.length === 0) {
        changedTbody.innerHTML = '<tr><td colspan="3" class="text-muted text-center py-3">No changed fields.</td></tr>';
      } else {
        changedTbody.innerHTML = changed.map(c => `
          <tr class="table-warning">
            <td><code class="small">${MC._esc(c.name || '')}</code></td>
            <td><pre class="mb-0 small font-monospace" style="white-space:pre-wrap;">${MC._esc(JSON.stringify(c.before, null, 2))}</pre></td>
            <td><pre class="mb-0 small font-monospace" style="white-space:pre-wrap;">${MC._esc(JSON.stringify(c.after, null, 2))}</pre></td>
          </tr>
        `).join('');
      }
    }
  },

  async deleteSnapshot(id) {
    if (!confirm(`Delete snapshot #${id}? This cannot be undone.`)) return;

    try {
      const resp = await fetch(`/schema/snapshots/${id}`, { method: 'DELETE' });
      const json = await resp.json();
      if (!json.success) {
        alert('Error deleting snapshot: ' + (json.error || 'Unknown error'));
        return;
      }

      // Remove from selected if present
      this._selected = this._selected.filter(s => s.id !== id);
      this._updateSelectionUI();
      this.loadList();
    } catch (err) {
      alert('Request failed: ' + err.message);
    }
  },
};

// Simple HTML escaping helper (fallback if MC._esc not defined globally)
if (!MC._esc) {
  MC._esc = function(str) {
    return String(str ?? '')
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  };
}

/* ============================================================================
 * MC.metadataDiff — Org-to-Org Metadata Diff
 * ==========================================================================*/
MC.metadataDiff = {
  init() {
    document.getElementById('btnRunMetaDiff')?.addEventListener('click', () => this.run());
  },

  async run() {
    const rightOrg = document.getElementById('rightOrgSelect')?.value;
    const types = Array.from(document.querySelectorAll('.meta-type-check:checked'))
      .map(c => c.value);
    if (types.length === 0) {
      MC.showToast('Select at least one metadata type', 'warning');
      return;
    }
    const empty = document.getElementById('metaDiffEmpty');
    const loading = document.getElementById('metaDiffLoading');
    const accordion = document.getElementById('metaDiffAccordion');
    const legend = document.getElementById('metaDiffLegend');
    const summary = document.getElementById('metaDiffSummary');

    if (empty) empty.classList.add('d-none');
    if (loading) loading.classList.remove('d-none');
    if (accordion) accordion.innerHTML = '';
    if (legend) legend.classList.add('d-none');
    if (summary) summary.classList.add('d-none');
    MC.showSpinner?.();
    try {
      const data = await MC.api('/schema/metadata-diff/run', 'POST',
        { right_org: rightOrg, types });
      this.renderResults(data || {});
    } catch (err) {
      MC.showToast('Diff failed: ' + err.message, 'danger');
      if (empty) {
        empty.textContent = 'Diff failed: ' + err.message;
        empty.classList.remove('d-none');
      }
    } finally {
      MC.hideSpinner?.();
      if (loading) loading.classList.add('d-none');
    }
  },

  renderResults(data) {
    const accordion = document.getElementById('metaDiffAccordion');
    const summary = document.getElementById('metaDiffSummary');
    const legend = document.getElementById('metaDiffLegend');
    const types = data.types || [];
    if (!accordion) return;
    if (types.length === 0) {
      const empty = document.getElementById('metaDiffEmpty');
      if (empty) {
        empty.textContent = 'No metadata types compared.';
        empty.classList.remove('d-none');
      }
      return;
    }
    const total = data.total_differences || 0;
    const left = String(data.left_org || '').toUpperCase();
    const right = String(data.right_org || '').toUpperCase();
    if (summary) {
      summary.className = 'alert mb-2 ' + (total > 0 ? 'alert-warning' : 'alert-success');
      summary.textContent = total > 0
        ? `${total} difference${total !== 1 ? 's' : ''} between ${left} and ${right} `
          + `across ${types.length} metadata type${types.length !== 1 ? 's' : ''}.`
        : `${left} and ${right} match across ${types.length} `
          + `metadata type${types.length !== 1 ? 's' : ''}.`;
      summary.classList.remove('d-none');
    }
    if (legend) legend.classList.remove('d-none');
    accordion.innerHTML = types.map((t, i) => this.buildPanel(t, i)).join('');
  },

  buildPanel(diff, idx) {
    const id = `metaDiff${idx}`;
    if (diff.error) {
      return `<div class="accordion-item">
        <h2 class="accordion-header"><button class="accordion-button collapsed" type="button"
          data-bs-toggle="collapse" data-bs-target="#c-${id}">
          <span class="fw-bold">${MC._esc(diff.label)}</span>
          <span class="badge badge-red ms-auto me-3">error</span></button></h2>
        <div id="c-${id}" class="accordion-collapse collapse" data-bs-parent="#metaDiffAccordion">
          <div class="accordion-body small text-danger">${MC._esc(diff.error)}</div></div></div>`;
    }
    const leftOnly = diff.left_only || [];
    const rightOnly = diff.right_only || [];
    const modified = diff.modified || [];
    const count = diff.difference_count || 0;

    const listSection = (title, items, rowClass) => {
      if (!items.length) return '';
      return `<div class="diff-section-title">${MC._esc(title)}</div>
        <table class="table table-sm mb-2"><tbody>
        ${items.map(it => `<tr class="${rowClass}">
          <td class="font-monospace small py-1">${MC._esc(it.name)}</td>
          <td class="small text-muted py-1">${MC._esc(it.detail || '')}</td></tr>`).join('')}
        </tbody></table>`;
    };
    const modSection = () => {
      if (!modified.length) return '';
      return `<div class="diff-section-title">Modified (configured differently)</div>
        <table class="table table-sm mb-2"><tbody>
        ${modified.map(m => `<tr class="diff-mismatch">
          <td class="font-monospace small py-1">${MC._esc(m.name)}</td>
          <td class="small py-1"><span class="text-muted">left:</span> ${MC._esc(m.left_detail || '')}<br>
            <span class="text-muted">right:</span> ${MC._esc(m.right_detail || '')}</td></tr>`).join('')}
        </tbody></table>`;
    };

    return `<div class="accordion-item">
      <h2 class="accordion-header" id="h-${id}">
        <button class="accordion-button ${count === 0 ? 'collapsed' : ''}" type="button"
          data-bs-toggle="collapse" data-bs-target="#c-${id}" aria-expanded="${count > 0}">
          <span class="fw-bold">${MC._esc(diff.label)}</span>
          <span class="d-flex gap-2 ms-auto me-3 small align-items-center">
            <span class="text-muted">L: ${diff.left_total ?? '?'}</span>
            <span class="text-muted">R: ${diff.right_total ?? '?'}</span>
            ${count > 0 ? `<span class="badge badge-red">${count} diff${count !== 1 ? 's' : ''}</span>`
                        : '<span class="badge badge-green">Match</span>'}
          </span>
        </button>
      </h2>
      <div id="c-${id}" class="accordion-collapse collapse ${count > 0 ? 'show' : ''}"
           aria-labelledby="h-${id}" data-bs-parent="#metaDiffAccordion">
        <div class="accordion-body">
          ${listSection('Left-only (in active org, not in right org)', leftOnly, 'diff-left-only')}
          ${listSection('Right-only (in right org, not in active org)', rightOnly, 'diff-right-only')}
          ${modSection()}
          ${count === 0 ? '<p class="text-muted small mb-0">No differences for this metadata type.</p>' : ''}
        </div>
      </div>
    </div>`;
  },
};
