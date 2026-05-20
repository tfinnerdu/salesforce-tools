'use strict';

// ── Admin ─────────────────────────────────────────────────────────────────────
// Paste this object into mission-control.js after the last MC.* namespace block.

MC.admin = {
  _users: [],

  init() {
    document.getElementById('btnRefreshJobs')?.addEventListener('click', () => this.loadScheduledJobs());
    document.getElementById('btnRefreshCoverage')?.addEventListener('click', () => this.loadTestCoverage());
    document.getElementById('btnRefreshDeploys')?.addEventListener('click', () => this.loadDeployHistory());
    document.getElementById('btnRefreshUsers')?.addEventListener('click', () => this.loadUsers());

    document.getElementById('userFilter')?.addEventListener('input', (e) => {
      this._filterUsers(e.target.value.trim().toLowerCase());
    });

    // Load the default (first) tab on init
    this.loadScheduledJobs();

    // Lazy-load other tabs when first shown
    document.getElementById('tab-coverage')?.addEventListener('shown.bs.tab', () => {
      if (!document.getElementById('coverageCard')?.classList.contains('d-none')) return;
      if (!document.getElementById('coverageEmpty')?.classList.contains('d-none')) return;
      this.loadTestCoverage();
    });
    document.getElementById('tab-deploys')?.addEventListener('shown.bs.tab', () => {
      if (!document.getElementById('deploysCard')?.classList.contains('d-none')) return;
      if (!document.getElementById('deploysEmpty')?.classList.contains('d-none')) return;
      this.loadDeployHistory();
    });
    document.getElementById('tab-users')?.addEventListener('shown.bs.tab', () => {
      if (!document.getElementById('usersCard')?.classList.contains('d-none')) return;
      if (!document.getElementById('usersEmpty')?.classList.contains('d-none')) return;
      this.loadUsers();
    });
    document.getElementById('tab-anonymizer-btn')?.addEventListener('shown.bs.tab', () => {
      this.initAnonymizer();
    });
    document.getElementById('tab-integrations-btn')?.addEventListener('shown.bs.tab', () => {
      this.loadIntegrations();
    });
    document.getElementById('tab-platform-events-btn')?.addEventListener('shown.bs.tab', () => {
      this.loadPlatformEvents();
    });
    document.getElementById('btnRefreshPlatformEvents')?.addEventListener('click', () => {
      this.loadPlatformEvents();
    });

    // Wire all Refresh buttons inside the integrations tab
    document.querySelectorAll('.integ-refresh-btn').forEach(btn => {
      btn.addEventListener('click', () => this.loadIntegrations());
    });
  },

  // ── Scheduled Jobs ──────────────────────────────────────────────────────────

  async loadScheduledJobs() {
    const loading = document.getElementById('jobsLoading');
    const empty   = document.getElementById('jobsEmpty');
    const card    = document.getElementById('jobsCard');
    loading?.classList.remove('d-none');
    empty?.classList.add('d-none');
    card?.classList.add('d-none');
    try {
      const jobs = await MC.api('/admin/scheduled-jobs');
      if (!jobs || jobs.length === 0) {
        empty?.classList.remove('d-none');
        return;
      }
      this._renderJobsTable(jobs);
      card?.classList.remove('d-none');
    } catch (err) {
      MC.showToast(`Failed to load scheduled jobs: ${err.message}`, 'danger');
      empty?.classList.remove('d-none');
    } finally {
      loading?.classList.add('d-none');
    }
  },

  _renderJobsTable(jobs) {
    const tbody = document.getElementById('jobsBody');
    if (!tbody) return;
    tbody.innerHTML = jobs.map(j => {
      const stateBadge = this._jobStateBadge(j.state);
      return `<tr>
        <td class="fw-semibold">${MC._escHtml(j.name)}</td>
        <td class="text-muted small">${MC._escHtml(j.job_type_label)}</td>
        <td>${stateBadge}</td>
        <td class="small">${MC._fmtTime(j.next_fire_time)}</td>
        <td class="text-muted small">${MC._fmtTime(j.previous_fire_time)}</td>
        <td class="text-end small">${MC._escHtml(j.times_triggered)}</td>
        <td><code class="small">${MC._escHtml(j.cron_expression)}</code></td>
      </tr>`;
    }).join('');
  },

  _jobStateBadge(state) {
    const s = (state || '').toUpperCase();
    const cls =
      s === 'WAITING'   ? 'badge-green' :
      s === 'EXECUTING' ? 'badge-green' :
      s === 'PAUSED'    ? 'badge-amber' :
      s === 'ERROR'     ? 'badge-red'   :
      'badge-navy';
    return `<span class="badge ${cls}">${MC._escHtml(s)}</span>`;
  },

  // ── Test Coverage ───────────────────────────────────────────────────────────

  async loadTestCoverage() {
    const loading = document.getElementById('coverageLoading');
    const empty   = document.getElementById('coverageEmpty');
    const card    = document.getElementById('coverageCard');
    const summary = document.getElementById('coverageSummary');
    loading?.classList.remove('d-none');
    empty?.classList.add('d-none');
    card?.classList.add('d-none');
    summary?.classList.add('d-none');
    try {
      const data = await MC.api('/admin/test-coverage');
      const classes = data?.classes || [];
      if (classes.length === 0) {
        empty?.classList.remove('d-none');
        return;
      }
      this._renderCoverageSummary(data.summary || {});
      this._renderCoverageTable(classes);
      card?.classList.remove('d-none');
      summary?.classList.remove('d-none');
    } catch (err) {
      MC.showToast(`Failed to load test coverage: ${err.message}`, 'danger');
      empty?.classList.remove('d-none');
    } finally {
      loading?.classList.add('d-none');
    }
  },

  _renderCoverageSummary(s) {
    const passing = s.passing ?? 0;
    const below   = s.below_threshold ?? 0;
    const failing = s.failing ?? 0;
    const passEl  = document.getElementById('covPassing');
    const belowEl = document.getElementById('covBelow');
    const failEl  = document.getElementById('covFailing');
    if (passEl)  passEl.textContent  = `${passing} passing`;
    if (belowEl) belowEl.textContent = `${below} below 75%`;
    if (failEl)  failEl.textContent  = `${failing} below 50%`;
  },

  _renderCoverageTable(classes) {
    const tbody = document.getElementById('coverageBody');
    if (!tbody) return;
    tbody.innerHTML = classes.map(c => {
      const pct = parseFloat(c.pct) || 0;
      const rowCls =
        pct >= 75 ? '' :
        pct >= 50 ? 'table-warning' :
        'table-danger';
      const barCls =
        pct >= 75 ? 'bg-success' :
        pct >= 50 ? 'bg-warning' :
        'bg-danger';
      const pctStr = `${pct.toFixed(1)}%`;
      return `<tr class="${rowCls}">
        <td class="fw-semibold">${MC._escHtml(c.name)}</td>
        <td class="text-end small">${MC._escHtml(c.num_lines_covered)}</td>
        <td class="text-end small">${MC._escHtml(c.num_lines_uncovered)}</td>
        <td>
          <div class="d-flex align-items-center gap-2">
            <div class="progress flex-grow-1" style="height:10px">
              <div class="progress-bar ${barCls}" role="progressbar"
                   style="width:${pct}%" aria-valuenow="${pct}"
                   aria-valuemin="0" aria-valuemax="100"></div>
            </div>
            <span class="small text-nowrap">${pctStr}</span>
          </div>
        </td>
      </tr>`;
    }).join('');
  },

  // ── Deployment History ──────────────────────────────────────────────────────

  async loadDeployHistory() {
    const loading = document.getElementById('deploysLoading');
    const empty   = document.getElementById('deploysEmpty');
    const card    = document.getElementById('deploysCard');
    loading?.classList.remove('d-none');
    empty?.classList.add('d-none');
    card?.classList.add('d-none');
    try {
      const deploys = await MC.api('/admin/deploy-history');
      if (!deploys || deploys.length === 0) {
        empty?.classList.remove('d-none');
        return;
      }
      this._renderDeploysTable(deploys);
      card?.classList.remove('d-none');
    } catch (err) {
      MC.showToast(`Failed to load deployments: ${err.message}`, 'danger');
      empty?.classList.remove('d-none');
    } finally {
      loading?.classList.add('d-none');
    }
  },

  _renderDeploysTable(deploys) {
    const tbody = document.getElementById('deploysBody');
    if (!tbody) return;
    tbody.innerHTML = deploys.map((d, idx) => {
      const statusBadge = MC.statusBadge(d.status);
      const duration = d.duration_seconds != null ? `${d.duration_seconds}s` : '—';
      const hasErrors = (d.num_component_errors > 0) || (d.num_test_errors > 0);
      const detailId  = `deployDetail-${idx}`;
      const expandBtn = hasErrors
        ? `<button class="btn btn-link btn-sm p-0 ms-1" type="button"
                   data-bs-toggle="collapse" data-bs-target="#${detailId}"
                   aria-expanded="false">detail</button>`
        : '';
      const detailRow = hasErrors && d.state_detail
        ? `<tr id="${detailId}" class="collapse">
             <td colspan="7" class="text-danger small ps-3">
               <code>${MC._escHtml(d.state_detail)}</code>
             </td>
           </tr>`
        : '';
      return `<tr>
        <td class="small">${MC._fmtTime(d.start_date)}</td>
        <td class="small">${MC._escHtml(d.created_by)}</td>
        <td class="text-end small">${MC._escHtml(d.num_components_total)}</td>
        <td class="text-end small ${d.num_component_errors > 0 ? 'text-danger fw-semibold' : ''}">${MC._escHtml(d.num_component_errors)}${expandBtn}</td>
        <td class="text-end small">${MC._escHtml(d.num_tests_completed)}</td>
        <td class="text-end small">${duration}</td>
        <td>${statusBadge}</td>
      </tr>${detailRow}`;
    }).join('');
  },

  // ── User Audit ──────────────────────────────────────────────────────────────

  async loadUsers() {
    const loading = document.getElementById('usersLoading');
    const empty   = document.getElementById('usersEmpty');
    const card    = document.getElementById('usersCard');
    const summary = document.getElementById('usersSummary');
    loading?.classList.remove('d-none');
    empty?.classList.add('d-none');
    card?.classList.add('d-none');
    summary?.classList.add('d-none');
    const filterEl = document.getElementById('userFilter');
    if (filterEl) filterEl.value = '';
    try {
      const data = await MC.api('/admin/users');
      this._users = data?.users || [];
      if (this._users.length === 0) {
        empty?.classList.remove('d-none');
        return;
      }
      this._renderUserSummary(data.summary || {});
      this._renderUsersTable(this._users);
      card?.classList.remove('d-none');
      summary?.classList.remove('d-none');
    } catch (err) {
      MC.showToast(`Failed to load user audit: ${err.message}`, 'danger');
      empty?.classList.remove('d-none');
    } finally {
      loading?.classList.add('d-none');
    }
  },

  _renderUserSummary(s) {
    const activeEl    = document.getElementById('sumActive');
    const inactive90El= document.getElementById('sumInactive90');
    const neverEl     = document.getElementById('sumNeverLogin');
    const sysEl       = document.getElementById('sumSysadmins');
    if (activeEl)     activeEl.textContent     = s.total_active ?? '—';
    if (inactive90El) inactive90El.textContent = s.inactive_90d ?? '—';
    if (neverEl)      neverEl.textContent      = s.never_logged_in ?? '—';
    if (sysEl)        sysEl.textContent        = s.sysadmins ?? '—';
  },

  _renderUsersTable(users) {
    const tbody = document.getElementById('usersBody');
    if (!tbody) return;
    tbody.innerHTML = users.map(u => {
      const rowCls =
        !u.is_active        ? 'text-muted'    :
        u.flag === 'never_logged_in' ? 'table-danger'  :
        u.flag === 'inactive_90d'    ? 'table-warning' :
        '';
      const loginText = u.last_login_date ? MC._fmtTime(u.last_login_date) : 'Never';
      const statusBadge = u.is_active
        ? (u.flag === 'never_logged_in' ? '<span class="badge badge-red">NEVER</span>'
         : u.flag === 'inactive_90d'    ? '<span class="badge badge-amber">STALE</span>'
         :                               '<span class="badge badge-green">ACTIVE</span>')
        : '<span class="badge badge-navy">INACTIVE</span>';
      return `<tr class="${rowCls}">
        <td>${MC._escHtml(u.name)}</td>
        <td class="small text-muted"><code>${MC._escHtml(u.username)}</code></td>
        <td class="small">${MC._escHtml(u.profile_name)}</td>
        <td class="small">${loginText}</td>
        <td>${statusBadge}</td>
      </tr>`;
    }).join('');
  },

  _filterUsers(q) {
    if (!q) {
      this._renderUsersTable(this._users);
      return;
    }
    const filtered = this._users.filter(u =>
      (u.name || '').toLowerCase().includes(q) ||
      (u.username || '').toLowerCase().includes(q)
    );
    this._renderUsersTable(filtered);
  },

  // ── Anonymizer ─────────────────────────────────────────────────────────────

  async initAnonymizer() {
    try {
      const objects = await MC.api('/admin/anonymizer/objects');
      const sel = document.getElementById('anonObjectSelect');
      if (sel) {
        (objects || []).forEach(o => {
          const opt = document.createElement('option');
          opt.value = o.object;
          opt.textContent = o.object;
          opt.dataset.fields = JSON.stringify(o.fields);
          sel.appendChild(opt);
        });
        sel.addEventListener('change', () => this._renderAnonFields(sel));
      }
    } catch (err) {
      MC.showToast(`Failed to load anonymizer objects: ${err.message}`, 'danger');
    }
    document.getElementById('btnAnonPreview')?.addEventListener('click', () => this.anonPreview());
    document.getElementById('btnAnonRun')?.addEventListener('click', () => this.anonRun());
  },

  _renderAnonFields(sel) {
    const fields = JSON.parse(sel.selectedOptions[0]?.dataset.fields || '[]');
    const wrap = document.getElementById('anonFieldsList');
    if (!wrap) return;
    if (!fields.length) {
      wrap.innerHTML = '<span class="text-muted small">No fields available</span>';
      return;
    }
    wrap.innerHTML = fields.map(f => `
      <div class="form-check">
        <input class="form-check-input anon-field-check" type="checkbox"
               id="anonField_${MC._escHtml(f)}" value="${MC._escHtml(f)}" checked>
        <label class="form-check-label small font-monospace" for="anonField_${MC._escHtml(f)}">${MC._escHtml(f)}</label>
      </div>`).join('');
    document.getElementById('btnAnonRun').disabled = false;
  },

  _getAnonSelection() {
    const object = document.getElementById('anonObjectSelect')?.value;
    const fields = Array.from(document.querySelectorAll('.anon-field-check:checked')).map(el => el.value);
    return { object, fields };
  },

  async anonPreview() {
    const { object, fields } = this._getAnonSelection();
    if (!object) { MC.showToast('Select an object first', 'warning'); return; }
    try {
      const data = await MC.api('/admin/anonymizer/preview', 'POST', { object, fields });
      document.getElementById('anonRecordCount').textContent = (data.record_count || 0).toLocaleString();
      document.getElementById('anonPreviewObject').textContent = data.object || object;
      document.getElementById('anonPreviewFields').textContent = (data.fields || fields).join(', ');
      document.getElementById('anonPreviewSoql').textContent = data.soql || '';
      document.getElementById('anonPreviewWrap')?.classList.remove('d-none');
      document.getElementById('anonResultWrap')?.classList.add('d-none');
    } catch (err) {
      MC.showToast(`Preview failed: ${err.message}`, 'danger');
    }
  },

  async anonRun() {
    const { object, fields } = this._getAnonSelection();
    const dryRun = document.getElementById('anonDryRun')?.checked ?? true;
    if (!object || !fields.length) { MC.showToast('Select object and at least one field', 'warning'); return; }
    if (!dryRun && !confirm(`Run LIVE anonymization on ${object}? This modifies real data.`)) return;
    MC.showSpinner();
    try {
      const data = await MC.api('/admin/anonymizer/run', 'POST', { object, fields, dry_run: dryRun });
      const alertEl = document.getElementById('anonResultAlert');
      if (alertEl) {
        alertEl.className = `alert py-2 small mb-0 alert-${data.status === 'stub' || data.status === 'dry_run' ? 'info' : 'success'}`;
        alertEl.textContent = data.message || JSON.stringify(data);
      }
      document.getElementById('anonResultWrap')?.classList.remove('d-none');
    } catch (err) {
      MC.showToast(`Run failed: ${err.message}`, 'danger');
    } finally {
      MC.hideSpinner();
    }
  },

  // ── Integrations ────────────────────────────────────────────────────────────

  async loadIntegrations() {
    // Show spinners, hide tables and empty states
    ['namedCreds', 'remoteSites', 'connectedApps'].forEach(key => {
      document.getElementById(`${key}Loading`)?.classList.remove('d-none');
      document.getElementById(`${key}Empty`)?.classList.add('d-none');
      document.getElementById(`${key}CardBody`)?.classList.add('d-none');
    });
    try {
      const data = await MC.api('/admin/integrations');
      this._renderNamedCreds(data.named_credentials || []);
      this._renderRemoteSites(data.remote_sites || []);
      this._renderConnectedApps(data.connected_apps || []);
    } catch (err) {
      MC.showToast(`Failed to load integrations: ${err.message}`, 'danger');
      ['namedCreds', 'remoteSites', 'connectedApps'].forEach(key => {
        document.getElementById(`${key}Empty`)?.classList.remove('d-none');
      });
    } finally {
      ['namedCreds', 'remoteSites', 'connectedApps'].forEach(key => {
        document.getElementById(`${key}Loading`)?.classList.add('d-none');
      });
    }
  },

  _renderNamedCreds(items) {
    const tbody = document.getElementById('namedCredsTbody');
    const empty = document.getElementById('namedCredsEmpty');
    const body  = document.getElementById('namedCredsCardBody');
    if (!tbody) return;
    if (!items.length) {
      empty?.classList.remove('d-none');
      body?.classList.add('d-none');
      return;
    }
    tbody.innerHTML = items.map(nc => {
      const endpoint = nc.endpoint || '';
      const truncated = endpoint.length > 50 ? endpoint.slice(0, 50) + '…' : endpoint;
      const labelCell = nc.master_label !== nc.developer_name
        ? MC._escHtml(nc.master_label)
        : '<span class="text-muted">—</span>';
      return `<tr>
        <td class="fw-semibold font-monospace small">${MC._escHtml(nc.developer_name)}</td>
        <td class="small">${labelCell}</td>
        <td class="small"><code title="${MC._escHtml(endpoint)}">${MC._escHtml(truncated)}</code></td>
        <td class="small">${MC._escHtml(nc.protocol)}</td>
      </tr>`;
    }).join('');
    empty?.classList.add('d-none');
    body?.classList.remove('d-none');
  },

  _renderRemoteSites(items) {
    const tbody = document.getElementById('remoteSitesTbody');
    const empty = document.getElementById('remoteSitesEmpty');
    const body  = document.getElementById('remoteSitesCardBody');
    if (!tbody) return;
    if (!items.length) {
      empty?.classList.remove('d-none');
      body?.classList.add('d-none');
      return;
    }
    tbody.innerHTML = items.map(rs => {
      const activeBadge = rs.is_active
        ? '<span class="badge badge-green">ACTIVE</span>'
        : '<span class="badge badge-amber">INACTIVE</span>';
      const secProtocol = rs.disable_protocol_security
        ? '<span class="text-warning small">Disabled</span>'
        : '<span class="text-muted small">Enforced</span>';
      return `<tr>
        <td class="fw-semibold small">${MC._escHtml(rs.site_name)}</td>
        <td class="small"><code>${MC._escHtml(rs.url)}</code></td>
        <td>${activeBadge}</td>
        <td>${secProtocol}</td>
      </tr>`;
    }).join('');
    empty?.classList.add('d-none');
    body?.classList.remove('d-none');
  },

  _renderConnectedApps(items) {
    const tbody = document.getElementById('connectedAppsTbody');
    const empty = document.getElementById('connectedAppsEmpty');
    const body  = document.getElementById('connectedAppsCardBody');
    if (!tbody) return;
    if (!items.length) {
      empty?.classList.remove('d-none');
      body?.classList.add('d-none');
      return;
    }
    tbody.innerHTML = items.map(ca => {
      return `<tr>
        <td class="fw-semibold small">${MC._escHtml(ca.master_label)}</td>
        <td class="small font-monospace">${MC._escHtml(ca.developer_name)}</td>
        <td class="small text-muted">${MC._escHtml(ca.description || '—')}</td>
      </tr>`;
    }).join('');
    empty?.classList.add('d-none');
    body?.classList.remove('d-none');
  },

  // ── Platform Events ─────────────────────────────────────────────────────────

  async loadPlatformEvents() {
    ['eventChannels', 'eventMembers'].forEach(key => {
      document.getElementById(`${key}Loading`)?.classList.remove('d-none');
      document.getElementById(`${key}Empty`)?.classList.add('d-none');
      document.getElementById(`${key}CardBody`)?.classList.add('d-none');
    });
    try {
      const data = await MC.api('/admin/platform-events');
      this._renderEventChannels(data.events || []);
      this._renderEventMembers(data.members || []);
    } catch (err) {
      MC.showToast(`Failed to load platform events: ${err.message}`, 'danger');
      ['eventChannels', 'eventMembers'].forEach(key => {
        document.getElementById(`${key}Empty`)?.classList.remove('d-none');
      });
    } finally {
      ['eventChannels', 'eventMembers'].forEach(key => {
        document.getElementById(`${key}Loading`)?.classList.add('d-none');
      });
    }
  },

  _renderEventChannels(items) {
    const tbody = document.getElementById('eventChannelsTbody');
    const empty = document.getElementById('eventChannelsEmpty');
    const body  = document.getElementById('eventChannelsCardBody');
    if (!tbody) return;
    if (!items.length) {
      empty?.classList.remove('d-none');
      body?.classList.add('d-none');
      return;
    }
    tbody.innerHTML = items.map(ev => `<tr>
      <td class="fw-semibold small">${MC._escHtml(ev.label)}</td>
      <td class="small font-monospace">${MC._escHtml(ev.developer_name)}</td>
      <td class="small text-muted">${MC._escHtml(ev.description || '—')}</td>
    </tr>`).join('');
    empty?.classList.add('d-none');
    body?.classList.remove('d-none');
  },

  _renderEventMembers(items) {
    const tbody = document.getElementById('eventMembersTbody');
    const empty = document.getElementById('eventMembersEmpty');
    const body  = document.getElementById('eventMembersCardBody');
    if (!tbody) return;
    if (!items.length) {
      empty?.classList.remove('d-none');
      body?.classList.add('d-none');
      return;
    }
    tbody.innerHTML = items.map(m => {
      const typeBadge = this._eventTypeBadge(m.type);
      return `<tr>
        <td class="fw-semibold small font-monospace">${MC._escHtml(m.developer_name)}</td>
        <td class="small font-monospace">${MC._escHtml(m.channel)}</td>
        <td>${typeBadge}</td>
      </tr>`;
    }).join('');
    empty?.classList.add('d-none');
    body?.classList.remove('d-none');
  },

  _eventTypeBadge(type) {
    const t = (type || '').trim();
    const cls =
      t === 'Flow'          ? 'badge-navy'  :
      t === 'ApexTrigger'   ? 'badge-blue'  :
      t === 'WorkflowAlert' ? 'badge-amber' :
      'badge-secondary';
    return `<span class="badge ${cls}">${MC._escHtml(t || '—')}</span>`;
  },
};
