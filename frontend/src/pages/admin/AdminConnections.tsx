/**
 * src/pages/admin/AdminConnections.tsx
 */
import React from 'react';
import { PageHeader } from '../../components/ui/PageHeader';
import { StatusBadge } from '../../components/ui/StatusBadge';

export default function AdminConnections() {
  return (
    <div className="flex flex-col h-full overflow-hidden">
      <PageHeader title="API / Connections" subtitle="External integration configuration" breadcrumbs={[{ label: 'Admin' }, { label: 'API / Connections' }]} />
      <div className="page-body">
        <div style={{ maxWidth: 680 }}>
          <div className="panel" style={{ padding: 16 }}>
            <h4 style={{ marginBottom: 12 }}>API Endpoints</h4>
            <div className="kv-grid">
              <div className="kv-key">Backend API</div>
              <div className="kv-val"><span className="mono">http://localhost:8000</span> <StatusBadge value="connected" /></div>
              <div className="kv-key">API Docs</div>
              <div className="kv-val"><a href="http://localhost:8000/docs" target="_blank" style={{ color: 'var(--accent)' }}>http://localhost:8000/docs</a></div>
              <div className="kv-key">ReDoc</div>
              <div className="kv-val"><a href="http://localhost:8000/redoc" target="_blank" style={{ color: 'var(--accent)' }}>http://localhost:8000/redoc</a></div>
            </div>
          </div>
          <div style={{ marginTop: 16, padding: '10px 12px', background: 'var(--bg-elevated)', borderRadius: 'var(--radius-sm)', fontSize: '0.77rem', color: 'var(--text-muted)' }}>
            No external integration API (MLflow, Weights & Biases, cloud storage) is configured in the current backend.
          </div>
        </div>
      </div>
    </div>
  );
}
