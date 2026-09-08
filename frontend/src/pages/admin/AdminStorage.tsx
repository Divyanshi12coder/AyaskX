/**
 * src/pages/admin/AdminStorage.tsx
 */
import React from 'react';
import { PageHeader } from '../../components/ui/PageHeader';

export default function AdminStorage() {
  const paths = [
    { label: 'Checkpoints', path: '.ayask_checkpoints/', env: 'AYASKX_CHECKPOINT_ROOT' },
    { label: 'Artifacts', path: '.ayask_artifacts/', env: 'AYASKX_ARTIFACT_ROOT' },
    { label: 'Uploads', path: '.ayask_uploads/', env: 'AYASKX_UPLOAD_TMP' },
    { label: 'Store (JSON)', path: '.ayask_store/', env: 'AYASKX_STORE_ROOT' },
    { label: 'Audit Log', path: '.ayask_audit.jsonl', env: 'AYASKX_AUDIT_LOG' },
    { label: 'Database', path: 'ayaskx.db', env: 'N/A' },
  ];

  return (
    <div className="flex flex-col h-full overflow-hidden">
      <PageHeader title="Storage" subtitle="File system storage paths" breadcrumbs={[{ label: 'Admin' }, { label: 'Storage' }]} />
      <div className="page-body">
        <div style={{ maxWidth: 680 }}>
          <div className="panel" style={{ padding: 0 }}>
            <table className="data-table">
              <thead>
                <tr><th>Store</th><th>Path</th><th>Environment Variable</th></tr>
              </thead>
              <tbody>
                {paths.map(p => (
                  <tr key={p.label}>
                    <td style={{ color: 'var(--text-primary)', fontWeight: 500 }}>{p.label}</td>
                    <td className="mono">{p.path}</td>
                    <td className="mono" style={{ color: 'var(--text-muted)', fontSize: '0.75rem' }}>{p.env}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div style={{ marginTop: 12, fontSize: '0.77rem', color: 'var(--text-muted)' }}>
            No remote storage (S3, GCS, Azure) is configured. All data is stored on the local filesystem.
          </div>
        </div>
      </div>
    </div>
  );
}
