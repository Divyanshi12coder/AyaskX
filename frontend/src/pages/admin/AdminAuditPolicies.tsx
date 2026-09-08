/**
 * src/pages/admin/AdminAuditPolicies.tsx
 */
import React from 'react';
import { PageHeader } from '../../components/ui/PageHeader';

export default function AdminAuditPolicies() {
  return (
    <div className="flex flex-col h-full overflow-hidden">
      <PageHeader title="Audit Policies" subtitle="Audit configuration and retention policies" breadcrumbs={[{ label: 'Admin' }, { label: 'Audit Policies' }]} />
      <div className="page-body">
        <div style={{ maxWidth: 680 }}>
          <div className="panel" style={{ padding: 16 }}>
            <h4 style={{ marginBottom: 12 }}>Current Audit Configuration</h4>
            <div className="kv-grid">
              <div className="kv-key">Audit Log Format</div>
              <div className="kv-val mono">JSONL (.ayask_audit.jsonl)</div>
              <div className="kv-key">In-Memory Events</div>
              <div className="kv-val">Yes (SecurityAuditLogger)</div>
              <div className="kv-key">Persistent Log</div>
              <div className="kv-val">File-based JSONL</div>
              <div className="kv-key">API Endpoint</div>
              <div className="kv-val mono">GET /v1/audit/events</div>
              <div className="kv-key">Retention Policy</div>
              <div className="kv-val">Not configured (all events retained in-memory)</div>
              <div className="kv-key">Encryption</div>
              <div className="kv-val">Not implemented</div>
              <div className="kv-key">Export</div>
              <div className="kv-val">Not implemented</div>
            </div>
          </div>
          <div style={{ marginTop: 12, fontSize: '0.77rem', color: 'var(--text-muted)', padding: '10px 12px', background: 'var(--bg-elevated)', borderRadius: 'var(--radius-sm)' }}>
            Configurable retention, export, and encryption policies are not yet implemented in the backend.
            All audit events are stored in memory and in .ayask_audit.jsonl.
          </div>
        </div>
      </div>
    </div>
  );
}
