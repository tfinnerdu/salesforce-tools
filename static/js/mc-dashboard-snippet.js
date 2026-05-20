'use strict';

// ── Dashboard ─────────────────────────────────────────────────────────────────
// Paste this object into mission-control.js after the last MC.* namespace block,
// or load as a standalone script after mission-control.js.

MC.dashboard = {
  _widgets: ['readiness', 'limits', 'validation', 'batches', 'coverage', 'preflight', 'audit', 'health'],

  init() {
    document.getElementById('btnDashRefresh')?.addEventListener('click', () => this.loadAll());
    this.loadAll();
  },

  async loadAll() {
    const el = document.getElementById('dashLastUpdated');
    if (el) el.textContent = 'Loading…';
    await Promise.allSettled([
      this.loadReadiness(),
      this.loadLimits(),
      this.loadValidation(),
      this.loadBatches(),
      this.loadCoverage(),
      this.loadPreflight(),
      this.loadAudit(),
      this.loadHealth(),
    ]);
    if (el) el.textContent = 'Updated ' + new Date().toLocaleTimeString();
  },

  // ── Widget 1: Readiness Score ───────────────────────────────────────────────
  async loadReadiness() {
    try {
      const data = await MC.api('/migration/readiness/history');
      const latest = Array.isArray(data) && data.length ? data[0] : null;
      const pct = latest ? latest.overall_pct : null;

      if (pct === null || pct === undefined) {
        this._setWidgetBody('dashWidget1Body',
          '<div class="text-center text-muted py-3 small">No readiness runs yet.<br>' +
          '<a href="/migration/readiness" class="btn btn-doane btn-sm mt-2">Run Check</a></div>');
      } else {
        const rounded = Math.round(pct);
        const cls = this._colorByPct(rounded);
        const ts = latest.run_at ? new Date(latest.run_at).toLocaleString() : '';
        this._setWidgetBody('dashWidget1Body',
          `<div class="text-center">
            <div class="dash-score-num ${cls}">${rounded}%</div>
            <div class="small text-muted mt-1">last checked</div>
            <div class="small text-muted">${ts}</div>
          </div>`);
      }
      this._setAge('dashWidget1Age', 'just now');
    } catch (err) {
      this._setError('dashWidget1Body', () => this.loadReadiness());
    }
  },

  // ── Widget 2: API Limits ────────────────────────────────────────────────────
  async loadLimits() {
    const org = MC.activeOrg();
    // Update title with org name
    const titleEl = document.getElementById('dashWidget2Title');
    if (titleEl) titleEl.textContent = `API Limits — ${org}`;
    try {
      const data = await MC.api(`/observe/limits?org=${encodeURIComponent(org)}`);
      const limits = Array.isArray(data) ? data : (data && Array.isArray(data.limits) ? data.limits : []);

      if (!limits.length) {
        this._setWidgetBody('dashWidget2Body', '<div class="text-muted small text-center py-3">No limit data available.</div>');
        this._setAge('dashWidget2Age', 'just now');
        return;
      }

      // Calculate usage pct for each limit and take top 3 by usage
      const withPct = limits
        .filter(l => l.Max && l.Max > 0)
        .map(l => ({ ...l, usedPct: Math.round(((l.Max - (l.Remaining ?? l.Max)) / l.Max) * 100) }))
        .sort((a, b) => b.usedPct - a.usedPct)
        .slice(0, 3);

      if (!withPct.length) {
        this._setWidgetBody('dashWidget2Body', '<div class="text-muted small text-center py-3">No consumable limits found.</div>');
        this._setAge('dashWidget2Age', 'just now');
        return;
      }

      const rows = withPct.map(l => {
        const barCls = l.usedPct >= 90 ? 'bg-danger' : l.usedPct >= 70 ? 'bg-warning' : 'bg-success';
        const name = l.name || l.Name || 'Unknown';
        return `<div class="mb-2">
          <div class="d-flex justify-content-between small mb-1">
            <span class="text-truncate" style="max-width:70%">${MC._escHtml(name)}</span>
            <span class="fw-semibold">${l.usedPct}%</span>
          </div>
          <div class="progress" style="height:6px;">
            <div class="progress-bar ${barCls}" style="width:${l.usedPct}%"></div>
          </div>
        </div>`;
      }).join('');

      this._setWidgetBody('dashWidget2Body', rows);
      this._setAge('dashWidget2Age', 'just now');
    } catch (err) {
      this._setError('dashWidget2Body', () => this.loadLimits());
    }
  },

  // ── Widget 3: Data Validation ───────────────────────────────────────────────
  async loadValidation() {
    // Static links — no persistent last-run tracking per check
    const checks = [
      { name: 'Duplicate Radar', href: '/validation/duplicates' },
      { name: 'External IDs', href: '/validation/external-ids' },
      { name: 'Contact Points', href: '/validation/contactpoints' },
      { name: 'Field Completeness', href: '/validation/completeness' },
      { name: 'Orphaned Records', href: '/validation/orphans' },
    ];

    const rows = checks.map(c =>
      `<div class="d-flex align-items-center justify-content-between py-1 border-bottom">
        <a href="${c.href}" class="small text-decoration-none text-dark">${MC._escHtml(c.name)}</a>
        <span class="badge bg-secondary small">Never run</span>
      </div>`
    ).join('');

    this._setWidgetBody('dashWidget3Body', rows);
    this._setAge('dashWidget3Age', 'just now');
  },

  // ── Widget 4: Migration Batches ─────────────────────────────────────────────
  async loadBatches() {
    try {
      const data = await MC.api('/migration/batches/recent');
      const batches = Array.isArray(data) ? data : [];

      const total = batches.length;
      const completed = batches.filter(b => b.status === 'Completed').length;
      const inProgress = batches.filter(b => b.status === 'Running' || b.status === 'InProgress').length;
      const failed = batches.filter(b => b.status === 'Failed' || b.status === 'Error').length;

      this._setWidgetBody('dashWidget4Body',
        `<div class="row g-2">
          <div class="col-6"><div class="dash-stat-box border rounded">
            <div class="dash-stat-num">${total}</div>
            <div class="dash-stat-label">Total</div>
          </div></div>
          <div class="col-6"><div class="dash-stat-box border rounded">
            <div class="dash-stat-num text-success">${completed}</div>
            <div class="dash-stat-label">Completed</div>
          </div></div>
          <div class="col-6"><div class="dash-stat-box border rounded">
            <div class="dash-stat-num text-warning">${inProgress}</div>
            <div class="dash-stat-label">In Progress</div>
          </div></div>
          <div class="col-6"><div class="dash-stat-box border rounded">
            <div class="dash-stat-num text-danger">${failed}</div>
            <div class="dash-stat-label">Failed</div>
          </div></div>
        </div>`);
      this._setAge('dashWidget4Age', 'just now');
    } catch (err) {
      // 404 or no batch endpoint: show graceful fallback
      this._setWidgetBody('dashWidget4Body',
        '<div class="text-muted small text-center py-3">No batch data available.<br>' +
        '<a href="/migration/batches" class="small">View Batches →</a></div>');
      this._setAge('dashWidget4Age', 'just now');
    }
  },

  // ── Widget 5: Apex Test Coverage ────────────────────────────────────────────
  async loadCoverage() {
    try {
      const data = await MC.api('/admin/test-coverage');
      const summary = data && data.summary ? data.summary : data;
      const passing = summary?.passing ?? summary?.classes_above_threshold ?? '—';
      const total = summary?.total ?? summary?.total_classes ?? '—';
      const below = summary?.below_threshold ?? 0;

      const belowHtml = below > 0
        ? `<div class="text-warning small mt-2">&#9888; ${below} class${below !== 1 ? 'es' : ''} below threshold</div>`
        : '<div class="text-success small mt-2">&#10003; All classes passing</div>';

      this._setWidgetBody('dashWidget5Body',
        `<div class="text-center">
          <div class="dash-score-num text-dark">${passing}<span class="fs-5 text-muted"> / ${total}</span></div>
          <div class="small text-muted">classes &ge;75% coverage</div>
          ${belowHtml}
        </div>`);
      this._setAge('dashWidget5Age', 'just now');
    } catch (err) {
      this._setError('dashWidget5Body', () => this.loadCoverage());
    }
  },

  // ── Widget 6: Pre-flight Checklist ──────────────────────────────────────────
  async loadPreflight() {
    try {
      const data = await MC.api('/migration/preflight/progress');
      const checked = data?.checked ?? data?.completed ?? 0;
      const total = data?.total ?? 0;
      const pct = total > 0 ? Math.round((checked / total) * 100) : 0;

      const barCls = pct >= 90 ? 'bg-success' : pct >= 60 ? 'bg-warning' : 'bg-danger';

      const categories = data?.categories || data?.by_category || {};
      const catKeys = ['Data Quality', 'Integrations', 'Permissions', 'Testing', 'Go-Live'];
      const catRows = catKeys.map(k => {
        const val = categories[k] ?? categories[k.toLowerCase().replace(/\s+/g, '_')];
        const display = val !== undefined ? val : '—';
        return `<div class="d-flex justify-content-between small py-1 border-bottom">
          <span>${MC._escHtml(k)}</span>
          <span class="text-muted">${display}</span>
        </div>`;
      }).join('');

      this._setWidgetBody('dashWidget6Body',
        `<div class="progress mb-2" style="height:10px;">
          <div class="progress-bar ${barCls}" style="width:${pct}%"></div>
        </div>
        <div class="small text-center text-muted mb-2">${checked} of ${total} items complete</div>
        ${catRows}`);
      this._setAge('dashWidget6Age', 'just now');
    } catch (err) {
      this._setError('dashWidget6Body', () => this.loadPreflight());
    }
  },

  // ── Widget 7: Recent Audit Trail ────────────────────────────────────────────
  async loadAudit() {
    try {
      const data = await MC.api('/admin/audit-trail?days=1');
      const entries = Array.isArray(data) ? data : (data?.entries ?? []);

      if (!entries.length) {
        this._setWidgetBody('dashWidget7Body',
          '<div class="text-success small text-center py-3">&#10003; No changes in last 24h</div>');
        this._setAge('dashWidget7Age', 'just now');
        return;
      }

      const top5 = entries.slice(0, 5);
      const rows = top5.map(e => {
        const section = MC._escHtml(e.Section || e.section || '');
        const action = MC._escHtml(e.Action || e.action || e.Display || '');
        const ts = e.CreatedDate || e.created_date || e.timestamp || '';
        const ago = ts ? this._timeAgo(ts) : '';
        return `<div class="d-flex gap-2 align-items-start py-1 border-bottom">
          <span class="dash-timeline-dot mt-1"></span>
          <div class="flex-grow-1 small">
            <span class="badge bg-secondary me-1">${section}</span>
            <span class="text-truncate d-inline-block" style="max-width:160px;vertical-align:middle">${action}</span>
          </div>
          <span class="small text-muted text-nowrap">${ago}</span>
        </div>`;
      }).join('');

      this._setWidgetBody('dashWidget7Body', rows);
      this._setAge('dashWidget7Age', 'just now');
    } catch (err) {
      this._setError('dashWidget7Body', () => this.loadAudit());
    }
  },

  // ── Widget 8: Org Health Score ──────────────────────────────────────────────
  async loadHealth() {
    try {
      const summary = await MC.api('/dashboard/summary');
      const readinessPct = summary?.readiness_pct;
      const preflightPct = summary?.preflight_pct;
      const mock = summary?.mock;

      // Compute composite score — weighted average of available signals
      let score = null;
      const signals = [];
      if (readinessPct !== null && readinessPct !== undefined) signals.push(readinessPct);
      if (preflightPct !== null && preflightPct !== undefined) signals.push(preflightPct);
      if (signals.length) {
        score = Math.round(signals.reduce((a, b) => a + b, 0) / signals.length);
      }

      let grade, gradeCls, concern;
      if (score === null) {
        grade = '?'; gradeCls = 'text-secondary';
        concern = 'Run readiness check to compute score';
      } else if (score >= 90) {
        grade = 'A'; gradeCls = 'text-success';
        concern = 'Org is in excellent shape';
      } else if (score >= 75) {
        grade = 'B'; gradeCls = 'text-primary';
        concern = 'Minor gaps detected — review readiness';
      } else if (score >= 60) {
        grade = 'C'; gradeCls = 'text-warning';
        concern = 'Significant gaps — action required before go-live';
      } else {
        grade = 'D'; gradeCls = 'text-danger';
        concern = 'Critical readiness issues — do not go live';
      }

      const modeBadge = mock
        ? '<span class="badge badge-amber ms-1">MOCK</span>'
        : '<span class="badge badge-green ms-1">LIVE</span>';

      const bullets = [
        `<li>${concern}</li>`,
        `<li>Readiness: ${readinessPct !== null && readinessPct !== undefined ? readinessPct + '%' : 'Not run'}</li>`,
        `<li>Data mode: ${modeBadge}</li>`,
      ].join('');

      this._setWidgetBody('dashWidget8Body',
        `<div class="text-center mb-2">
          <div class="dash-grade ${gradeCls}">${grade}</div>
          ${score !== null ? `<div class="small text-muted">composite score: ${score}%</div>` : ''}
        </div>
        <ul class="small ps-3 mb-0">${bullets}</ul>`);
      this._setAge('dashWidget8Age', 'just now');
    } catch (err) {
      this._setError('dashWidget8Body', () => this.loadHealth());
    }
  },

  // ── Helpers ─────────────────────────────────────────────────────────────────

  _setWidgetBody(id, html) {
    const el = document.getElementById(id);
    if (el) el.innerHTML = html;
  },

  _setAge(id, text) {
    const el = document.getElementById(id);
    if (el) el.textContent = text;
  },

  _colorByPct(pct) {
    return pct >= 90 ? 'text-success' : pct >= 70 ? 'text-warning' : 'text-danger';
  },

  _setError(bodyId, retryFn) {
    this._setWidgetBody(bodyId,
      '<div class="text-warning small text-center py-3">' +
      '&#9888; Failed to load &nbsp;' +
      '<a href="#" class="small">Retry</a></div>');
    // Wire retry link
    const el = document.getElementById(bodyId);
    el?.querySelector('a')?.addEventListener('click', (e) => {
      e.preventDefault();
      this._setWidgetBody(bodyId,
        '<div class="text-center py-3"><div class="spinner-border spinner-border-sm text-warning"></div></div>');
      retryFn();
    });
  },

  _timeAgo(isoString) {
    try {
      const ms = Date.now() - new Date(isoString).getTime();
      const mins = Math.round(ms / 60000);
      if (mins < 1) return 'just now';
      if (mins < 60) return `${mins}m ago`;
      const hrs = Math.round(mins / 60);
      if (hrs < 24) return `${hrs}h ago`;
      return `${Math.round(hrs / 24)}d ago`;
    } catch (_) {
      return '';
    }
  },
};
