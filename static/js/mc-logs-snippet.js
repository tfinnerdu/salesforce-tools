'use strict';

// ── Logs ──────────────────────────────────────────────────────────────────────
// Paste this object into mission-control.js after the last MC.* namespace block.

MC.logs = {
  _activeTab: 'apex',
  _autoRefreshTimer: null,

  init() {
    // Sub-tab switching
    document.querySelectorAll('[data-tab]').forEach(link => {
      link.addEventListener('click', (e) => {
        e.preventDefault();
        this._switchTab(e.currentTarget.dataset.tab);
      });
    });

    document.getElementById('btnRefreshApex')?.addEventListener('click', () => this.loadApexLogs());
    document.getElementById('btnRefreshFlows')?.addEventListener('click', () => this.loadFlowErrors());
    document.getElementById('btnRefreshCpuSummary')?.addEventListener('click', () => this.loadCpuSummary());
    document.getElementById('btnRefreshTraceFlags')?.addEventListener('click', () => this.loadTraceFlags());
    document.getElementById('btnDeleteExpired')?.addEventListener('click', () => this.deleteExpiredFlags());
    document.getElementById('btnCreateTraceFlag')?.addEventListener('click', () => this.createTraceFlag());

    // User search datalist population
    document.getElementById('traceFlagEntitySearch')?.addEventListener('input', (e) => {
      this._populateUserDatalist(e.target.value);
    });
    // Clear hidden entity ID when user types (requires re-selection)
    document.getElementById('traceFlagEntitySearch')?.addEventListener('change', (e) => {
      const val = e.target.value;
      const dl = document.getElementById('traceFlagUserList');
      const match = dl ? Array.from(dl.options).find(o => o.value === val) : null;
      document.getElementById('traceFlagEntityId').value = match ? match.dataset.id : '';
    });
    document.getElementById('btnCloseDetail')?.addEventListener('click', () => this._closeDetail());

    // Time-range toolbar
    document.getElementById('logTimeRange')?.addEventListener('change', (e) => {
      const showCustom = e.target.value === 'custom';
      document.getElementById('customRangeWrap')?.classList.toggle('d-none', !showCustom);
      if (!showCustom) this.loadApexLogs();
    });
    document.getElementById('logCustomSince')?.addEventListener('change', () => this.loadApexLogs());
    document.getElementById('autoRefreshToggle')?.addEventListener('change', (e) => {
      this._setAutoRefresh(e.target.checked);
    });
    document.getElementById('btnDeleteAllLogs')?.addEventListener('click', () => this.deleteAllLogs());

    // Load the default tab
    this.loadApexLogs();
  },

  _switchTab(tab) {
    this._activeTab = tab;
    document.querySelectorAll('[data-tab]').forEach(l => l.classList.remove('active'));
    document.querySelector(`[data-tab="${tab}"]`)?.classList.add('active');

    const showApex = tab === 'apex';
    const showFlows = tab === 'flows';
    const showCpu = tab === 'cpu';
    const showTrace = tab === 'trace';

    document.getElementById('panelApex')?.classList.toggle('d-none', !showApex);
    document.getElementById('panelFlows')?.classList.toggle('d-none', !showFlows);
    document.getElementById('panelCpuSummary')?.classList.toggle('d-none', !showCpu);
    document.getElementById('panelTrace')?.classList.toggle('d-none', !showTrace);

    if (tab === 'flows') this.loadFlowErrors();
    if (tab === 'cpu') this.loadCpuSummary();
    if (tab === 'trace') this.loadTraceFlags();
  },

  async loadCpuSummary() {
    const loading = document.getElementById('cpuLoading');
    const empty   = document.getElementById('cpuEmpty');
    const table   = document.getElementById('cpuTable');

    loading?.classList.remove('d-none');
    empty?.classList.add('d-none');
    table?.classList.add('d-none');

    try {
      const items = await MC.api('/logs/apex/cpu-summary');
      if (!items || items.length === 0) {
        empty?.classList.remove('d-none');
        return;
      }
      this._renderCpuSummary(items);
      table?.classList.remove('d-none');
    } catch (err) {
      MC.showToast(`Failed to load CPU summary: ${err.message}`, 'danger');
      empty?.classList.remove('d-none');
    } finally {
      loading?.classList.add('d-none');
    }
  },

  _renderCpuSummary(items) {
    const tbody = document.getElementById('cpuSummaryTbody');
    if (!tbody) return;

    // Sort by duration_ms descending
    const sorted = [...items].sort((a, b) => (b.duration_ms || 0) - (a.duration_ms || 0));

    tbody.innerHTML = sorted.map(item => {
      const duration = item.duration_ms || 0;
      const kb = ((item.log_length || 0) / 1024).toFixed(1);
      const status = item.status || '';

      // Duration color coding
      let durationCls = '';
      if (duration > 10000) {
        durationCls = 'text-danger fw-semibold';
      } else if (duration > 5000) {
        durationCls = 'text-warning fw-semibold';
      }

      // Row highlight based on status_flag
      let rowCls = '';
      if (item.status_flag === 'danger') {
        rowCls = 'table-danger';
      } else if (item.status_flag === 'warning') {
        rowCls = 'table-warning';
      }

      const statusBadge = MC.statusBadge(status || 'Success');
      const logId = item.log_id || '';

      // View Log action — links to apex tab detail if available
      const viewBtn = logId
        ? `<button class="btn btn-outline-secondary btn-sm py-0"
                   onclick="MC.logs._switchTab('apex'); MC.logs.showLogDetail('${MC._escHtml(logId)}', '${MC._escHtml(item.operation)}')">
             View Log
           </button>`
        : '—';

      return `<tr class="${rowCls}">
        <td>${MC._escHtml(item.user || '—')}</td>
        <td><code class="small">${MC._escHtml(item.operation || '—')}</code></td>
        <td class="${durationCls}">${duration.toLocaleString()} ms</td>
        <td class="text-muted small">${kb} KB</td>
        <td>${statusBadge}</td>
        <td class="no-print">${viewBtn}</td>
      </tr>`;
    }).join('');
  },

  async loadApexLogs() {
    const loading = document.getElementById('apexLoading');
    const empty   = document.getElementById('apexEmpty');
    const table   = document.getElementById('apexTable');

    loading?.classList.remove('d-none');
    empty?.classList.add('d-none');
    table?.classList.add('d-none');
    this._closeDetail();

    try {
      const since = this._getSince();
      const url = since ? `/logs/apex?since=${encodeURIComponent(since)}` : '/logs/apex';
      const logs = await MC.api(url);
      if (!logs || logs.length === 0) {
        empty?.classList.remove('d-none');
        return;
      }
      this._renderApexTable(logs);
      table?.classList.remove('d-none');
    } catch (err) {
      MC.showToast(`Failed to load Apex logs: ${err.message}`, 'danger');
      empty?.classList.remove('d-none');
    } finally {
      loading?.classList.add('d-none');
    }
  },

  _getSince() {
    const range = document.getElementById('logTimeRange')?.value;
    if (!range || range === 'custom') {
      const custom = document.getElementById('logCustomSince')?.value;
      return custom ? new Date(custom).toISOString() : null;
    }
    const map = { '15m': 15, '1h': 60, '6h': 360, '24h': 1440 };
    const minutes = map[range];
    if (!minutes) return null;
    return new Date(Date.now() - minutes * 60 * 1000).toISOString();
  },

  _setAutoRefresh(enabled) {
    clearInterval(this._autoRefreshTimer);
    this._autoRefreshTimer = null;
    if (enabled) {
      this._autoRefreshTimer = setInterval(() => this.loadApexLogs(), 10000);
    }
  },

  async deleteAllLogs() {
    // Confirmation is handled declaratively by the data-mc-confirm attribute
    // on #btnDeleteAllLogs (see MC.confirm in mission-control.js).
    try {
      await MC.api('/logs/apex/delete-all', 'DELETE');
      MC.showToast('All logs deleted', 'success');
      this.loadApexLogs();
    } catch (err) {
      MC.showToast(`Delete failed: ${err.message}`, 'danger');
    }
  },

  _renderApexTable(logs) {
    const tbody = document.getElementById('apexBody');
    if (!tbody) return;
    tbody.innerHTML = logs.map(log => {
      const kb = (log.log_length / 1024).toFixed(1);
      const statusBadge = MC.statusBadge(log.status);
      return `<tr style="cursor:pointer" data-log-id="${MC._escHtml(log.id)}" onclick="MC.logs.showLogDetail('${MC._escHtml(log.id)}', '${MC._escHtml(log.operation)}')">
        <td>${MC._escHtml(log.user)}</td>
        <td><code class="small">${MC._escHtml(log.operation)}</code></td>
        <td>${statusBadge}</td>
        <td class="text-muted small">${kb} KB</td>
        <td class="text-muted small">${log.duration_ms} ms</td>
        <td class="text-muted small">${MC._fmtTime(log.last_modified)}</td>
        <td class="no-print">
          <button class="btn btn-outline-danger btn-sm py-0"
                  onclick="event.stopPropagation(); MC.logs.deleteLog('${MC._escHtml(log.id)}')">
            &times; Delete
          </button>
        </td>
      </tr>`;
    }).join('');
  },

  async showLogDetail(logId, operation) {
    const panel    = document.getElementById('apexDetailPanel');
    const loading  = document.getElementById('detailLoading');
    const title    = document.getElementById('detailTitle');

    panel?.classList.remove('d-none');
    loading?.classList.remove('d-none');
    if (title) title.textContent = `Log Detail — ${operation || logId}`;

    // Scroll to panel
    panel?.scrollIntoView({ behavior: 'smooth', block: 'start' });

    // Hide content sections while loading
    ['detailLimitsTable', 'detailLimitsEmpty', 'detailExceptionsList',
     'detailExceptionsEmpty', 'detailTimelineList', 'detailTimelineEmpty'].forEach(id => {
      document.getElementById(id)?.classList.add('d-none');
    });

    try {
      const parsed = await MC.api(`/logs/apex/${encodeURIComponent(logId)}`);
      this._renderDetail(parsed);
    } catch (err) {
      MC.showToast(`Failed to load log: ${err.message}`, 'danger');
    } finally {
      loading?.classList.add('d-none');
    }
  },

  _renderDetail(parsed) {
    // Limits
    const limitsBody  = document.getElementById('detailLimitsBody');
    const limitsTable = document.getElementById('detailLimitsTable');
    const limitsEmpty = document.getElementById('detailLimitsEmpty');
    const limits = parsed.limits || {};
    const limitKeys = Object.keys(limits);
    if (limitKeys.length === 0) {
      limitsEmpty?.classList.remove('d-none');
    } else {
      if (limitsBody) {
        limitsBody.innerHTML = limitKeys.map(label => {
          const l = limits[label];
          const pct = l.pct || 0;
          const barCls = pct >= 80 ? 'bg-danger' : pct >= 50 ? 'bg-warning' : 'bg-success';
          return `<tr>
            <td class="small">${MC._escHtml(label)}</td>
            <td class="small text-end">${l.used}</td>
            <td class="small text-end">${l.max}</td>
            <td style="min-width:120px">
              <div class="progress" style="height:8px">
                <div class="progress-bar ${barCls}" style="width:${Math.min(pct, 100)}%"></div>
              </div>
              <span class="small text-muted">${pct.toFixed(1)}%</span>
            </td>
          </tr>`;
        }).join('');
      }
      limitsTable?.classList.remove('d-none');
    }

    // Exceptions
    const excList  = document.getElementById('detailExceptionsList');
    const excEmpty = document.getElementById('detailExceptionsEmpty');
    const excs = parsed.exceptions || [];
    if (excs.length === 0) {
      excEmpty?.classList.remove('d-none');
    } else {
      if (excList) {
        excList.innerHTML = excs.map(ex => `
          <li class="list-group-item list-group-item-danger small">
            <strong>${MC._escHtml(ex.type)}</strong><br>
            <code>${MC._escHtml(ex.message)}</code>
          </li>`).join('');
      }
      excList?.classList.remove('d-none');
    }

    // Timeline
    const tmList  = document.getElementById('detailTimelineList');
    const tmEmpty = document.getElementById('detailTimelineEmpty');
    const timeline = parsed.timeline || [];
    if (timeline.length === 0) {
      tmEmpty?.classList.remove('d-none');
    } else {
      if (tmList) {
        tmList.innerHTML = timeline.map(ev => `
          <li class="list-group-item small py-1">
            <span class="badge badge-slate me-1">${MC._escHtml(ev.event)}</span>
            <span class="text-muted">${MC._escHtml(ev.detail)}</span>
          </li>`).join('');
      }
      tmList?.classList.remove('d-none');
    }
  },

  _closeDetail() {
    document.getElementById('apexDetailPanel')?.classList.add('d-none');
  },

  async deleteLog(logId) {
    if (!confirm('Delete this Apex log?')) return;
    try {
      await MC.api(`/logs/apex/${encodeURIComponent(logId)}`, 'DELETE');
      MC.showToast('Log deleted', 'success');
      // Remove row from table
      const row = document.querySelector(`[data-log-id="${logId}"]`);
      row?.remove();
      // If detail panel is open for this log, close it
      this._closeDetail();
    } catch (err) {
      MC.showToast(`Delete failed: ${err.message}`, 'danger');
    }
  },

  async loadFlowErrors() {
    const flowsLoading = document.getElementById('flowsLoading');
    const flowsEmpty   = document.getElementById('flowsEmpty');
    const flowsTable   = document.getElementById('flowsTable');
    const procExEmpty  = document.getElementById('procExEmpty');
    const procExTable  = document.getElementById('procExTable');

    flowsLoading?.classList.remove('d-none');
    flowsEmpty?.classList.add('d-none');
    flowsTable?.classList.add('d-none');

    try {
      const [flows, procExs] = await Promise.all([
        MC.api('/logs/flows'),
        MC.api('/logs/process-exceptions'),
      ]);

      // Flow interviews
      if (!flows || flows.length === 0) {
        flowsEmpty?.classList.remove('d-none');
      } else {
        this._renderFlowsTable(flows);
        flowsTable?.classList.remove('d-none');
      }

      // Process exceptions
      if (!procExs || procExs.length === 0) {
        procExEmpty?.classList.remove('d-none');
      } else {
        this._renderProcExTable(procExs);
        procExTable?.classList.remove('d-none');
      }
    } catch (err) {
      MC.showToast(`Failed to load flow errors: ${err.message}`, 'danger');
      flowsEmpty?.classList.remove('d-none');
    } finally {
      flowsLoading?.classList.add('d-none');
    }
  },

  _renderFlowsTable(flows) {
    const tbody = document.getElementById('flowsBody');
    if (!tbody) return;
    tbody.innerHTML = flows.map(f => `<tr>
      <td class="small fw-semibold">${MC._escHtml(f.flow_label) || '—'}</td>
      <td><code class="small">${MC._escHtml(f.current_element) || '—'}</code></td>
      <td><span class="badge badge-red">${MC._escHtml(f.status)}</span></td>
      <td class="text-muted small">${MC._fmtTime(f.created_date)}</td>
    </tr>`).join('');
  },

  _renderProcExTable(exceptions) {
    const tbody = document.getElementById('procExBody');
    if (!tbody) return;
    tbody.innerHTML = exceptions.map(ex => `<tr>
      <td><span class="badge badge-red">${MC._escHtml(ex.exception_type)}</span></td>
      <td class="small">${MC._escHtml(ex.message)}</td>
      <td class="small text-muted">${MC._escHtml(ex.source_object)}</td>
      <td>${MC.statusBadge(ex.status)}</td>
      <td class="small text-muted">${MC._fmtTime(ex.created_date)}</td>
    </tr>`).join('');
  },

  // ── Trace Flags ─────────────────────────────────────────────────────────────

  _debugLevels: [],

  async loadTraceFlags() {
    const loading = document.getElementById('traceFlagsLoading');
    const empty   = document.getElementById('traceFlagsEmpty');
    const table   = document.getElementById('traceFlagsTable');

    loading?.classList.remove('d-none');
    empty?.classList.add('d-none');
    table?.classList.add('d-none');

    try {
      const [flags, levels] = await Promise.all([
        MC.api('/logs/trace-flags'),
        MC.api('/logs/trace-flags/debug-levels'),
      ]);

      // Populate debug level select
      this._debugLevels = levels || [];
      const levelSel = document.getElementById('traceFlagDebugLevel');
      if (levelSel && levels && levels.length > 0) {
        levelSel.innerHTML = levels.map(l =>
          `<option value="${MC._escHtml(l.id)}">${MC._escHtml(l.label || l.name)}</option>`
        ).join('');
      }

      // Populate also the user datalist with initial top users
      await this._populateUserDatalist('');

      if (!flags || flags.length === 0) {
        empty?.classList.remove('d-none');
      } else {
        this._renderTraceFlagsTable(flags);
        table?.classList.remove('d-none');
      }
    } catch (err) {
      MC.showToast(`Failed to load trace flags: ${err.message}`, 'danger');
      empty?.classList.remove('d-none');
    } finally {
      loading?.classList.add('d-none');
    }
  },

  _renderTraceFlagsTable(flags) {
    const tbody = document.getElementById('traceFlagsTbody');
    if (!tbody) return;
    tbody.innerHTML = flags.map(f => {
      const expired = f.expired;
      const rowCls = expired ? 'table-secondary text-muted' : '';
      let statusCell;
      if (expired) {
        statusCell = '<span class="badge bg-secondary">Expired</span>';
      } else {
        const mins = f.expires_in_minutes;
        const color = (mins !== null && mins < 5) ? 'text-warning fw-semibold' : 'text-success fw-semibold';
        statusCell = `<span class="${color}">${mins !== null ? mins + 'm remaining' : 'Active'}</span>`;
      }
      const deleteBtn = `<button class="btn btn-outline-danger btn-sm py-0"
                                 onclick="MC.logs.deleteTraceFlag('${MC._escHtml(f.id)}')">
                           &times; Delete
                         </button>`;
      return `<tr class="${rowCls}">
        <td class="small font-monospace">${MC.sfLinkTag(f.traced_entity_id, f.traced_entity_type)}</td>
        <td class="small">${MC._escHtml(f.traced_entity_type)}</td>
        <td class="small">${MC._escHtml(f.debug_level_name)}</td>
        <td class="small">${MC._escHtml(f.log_type)}</td>
        <td class="small text-muted">${MC._fmtTime(f.expiration_date)}</td>
        <td>${statusCell}</td>
        <td class="no-print">${deleteBtn}</td>
      </tr>`;
    }).join('');
  },

  async deleteTraceFlag(flagId) {
    if (!confirm('Delete this trace flag?')) return;
    try {
      await MC.api(`/logs/trace-flags/${encodeURIComponent(flagId)}`, 'DELETE');
      MC.showToast('Trace flag deleted', 'success');
      // Remove row from table
      await this.loadTraceFlags();
    } catch (err) {
      MC.showToast(`Delete failed: ${err.message}`, 'danger');
    }
  },

  async deleteExpiredFlags() {
    try {
      const result = await MC.api('/logs/trace-flags/delete-expired', 'DELETE');
      const count = result ? result.deleted_count : 0;
      MC.showToast(`Deleted ${count} expired trace flag${count !== 1 ? 's' : ''}`, 'success');
      await this.loadTraceFlags();
    } catch (err) {
      MC.showToast(`Delete expired failed: ${err.message}`, 'danger');
    }
  },

  async createTraceFlag() {
    const entityId      = document.getElementById('traceFlagEntityId')?.value.trim();
    const entityType    = document.getElementById('traceFlagEntityType')?.value || 'User';
    const debugLevelId  = document.getElementById('traceFlagDebugLevel')?.value.trim();
    const durationSel   = document.getElementById('traceFlagDuration');
    let duration = parseInt(durationSel?.value, 10);

    // Handle "until midnight" option
    if (durationSel?.options[durationSel.selectedIndex]?.dataset?.dynamic === 'true') {
      const now = new Date();
      const midnight = new Date(now);
      midnight.setHours(24, 0, 0, 0);
      duration = Math.ceil((midnight - now) / 60000);
    }

    if (!entityId) {
      MC.showToast('Please select a user or class first', 'warning');
      return;
    }
    if (!debugLevelId) {
      MC.showToast('Please select a debug level', 'warning');
      return;
    }

    try {
      await MC.api('/logs/trace-flags', 'POST', {
        entity_id: entityId,
        entity_type: entityType,
        debug_level_id: debugLevelId,
        duration_minutes: duration,
      });
      MC.showToast('Trace flag created successfully', 'success');
      await this.loadTraceFlags();
    } catch (err) {
      MC.showToast(`Create failed: ${err.message}`, 'danger');
    }
  },

  async traceMe() {
    try {
      const [users, levels] = await Promise.all([
        MC.api('/logs/trace-flags/users'),
        MC.api('/logs/trace-flags/debug-levels'),
      ]);
      const user  = users && users.length > 0 ? users[0] : null;
      const level = levels && levels.length > 0 ? levels[0] : null;
      if (!user || !level) {
        MC.showToast('Could not find user or debug level to trace', 'warning');
        return;
      }
      await MC.api('/logs/trace-flags', 'POST', {
        entity_id: user.id,
        entity_type: 'User',
        debug_level_id: level.id,
        duration_minutes: 30,
      });
      MC.showToast('Trace flag active for 30 minutes — logs will appear in Apex Logs tab', 'success');
      await this.loadTraceFlags();
    } catch (err) {
      MC.showToast(`Trace Me failed: ${err.message}`, 'danger');
    }
  },

  async _populateUserDatalist(search) {
    try {
      const url = search ? `/logs/trace-flags/users?q=${encodeURIComponent(search)}` : '/logs/trace-flags/users';
      const users = await MC.api(url);
      const dl = document.getElementById('traceFlagUserList');
      if (dl && users) {
        dl.innerHTML = users.map(u =>
          `<option value="${MC._escHtml(u.name + ' <' + u.username + '>')}" data-id="${MC._escHtml(u.id)}">`
        ).join('');
      }
    } catch (_) {
      // ignore datalist population errors silently
    }
  },
};
