/**
 * src/pages/admin/AdminConfig.tsx
 * System configuration — uses env var defaults from api/config.py.
 * Sensitive values masked.
 */

import React, { useState } from 'react';
import { Eye, EyeOff } from 'lucide-react';
import { PageHeader } from '../../components/ui/PageHeader';

interface ConfigField {
  key: string;
  label: string;
  value: string;
  sensitive?: boolean;
  description?: string;
}

const CONFIG_FIELDS: ConfigField[] = [
  { key: 'api_host', label: 'API Host', value: '0.0.0.0', description: 'AYASKX_API_HOST' },
  { key: 'api_port', label: 'API Port', value: '8000', description: 'AYASKX_API_PORT' },
  { key: 'log_level', label: 'Log Level', value: 'INFO', description: 'AYASKX_LOG_LEVEL' },
  { key: 'cors_origins', label: 'CORS Origins', value: '*', description: 'AYASKX_CORS_ORIGINS' },
  { key: 'max_upload_mb', label: 'Max Upload (MB)', value: '200', description: 'AYASKX_MAX_UPLOAD_MB' },
  { key: 'checkpoint_root', label: 'Checkpoint Root', value: '.ayask_checkpoints', description: 'AYASKX_CHECKPOINT_ROOT' },
  { key: 'artifact_root', label: 'Artifact Root', value: '.ayask_artifacts', description: 'AYASKX_ARTIFACT_ROOT' },
  { key: 'upload_tmp_root', label: 'Upload Tmp Root', value: '.ayask_uploads', description: 'AYASKX_UPLOAD_TMP' },
  { key: 'store_root', label: 'Store Root', value: '.ayask_store', description: 'AYASKX_STORE_ROOT' },
  { key: 'audit_log_path', label: 'Audit Log Path', value: '.ayask_audit.jsonl', description: 'AYASKX_AUDIT_LOG' },
  { key: 'secret_key', label: 'Secret Key', value: '(not set)', sensitive: true, description: 'AYASKX_SECRET_KEY' },
];

function MaskedField({ value }: { value: string }) {
  const [shown, setShown] = useState(false);
  return (
    <span className="flex items-center gap-2">
      <span className="mono" style={{ color: 'var(--text-muted)' }}>
        {shown ? value : '••••••••••••'}
      </span>
      <button className="btn btn-ghost btn-icon" style={{ padding: 2 }} onClick={() => setShown((s) => !s)}>
        {shown ? <EyeOff size={12} /> : <Eye size={12} />}
      </button>
    </span>
  );
}

export default function AdminConfig() {
  return (
    <div className="flex flex-col h-full overflow-hidden">
      <PageHeader
        title="System Configuration"
        subtitle="Environment-sourced configuration (read-only — set via environment variables)"
        breadcrumbs={[{ label: 'Admin' }, { label: 'System Config' }]}
      />
      <div className="page-body">
        <div
          style={{
            padding: '8px 12px',
            marginBottom: 16,
            background: 'var(--status-info-dim)',
            border: '1px solid rgba(59,130,246,0.2)',
            borderRadius: 'var(--radius-sm)',
            fontSize: '0.77rem',
            color: 'var(--status-info)',
          }}
        >
          Configuration is read-only. Values reflect backend defaults and AYASKX_* environment
          variables. No runtime config update API is implemented.
        </div>

        <div style={{ maxWidth: 680 }}>
          <div className="panel" style={{ padding: 0 }}>
            <table className="data-table">
              <thead>
                <tr>
                  <th style={{ width: 200 }}>Setting</th>
                  <th>Value</th>
                  <th>Environment Variable</th>
                </tr>
              </thead>
              <tbody>
                {CONFIG_FIELDS.map((f) => (
                  <tr key={f.key}>
                    <td style={{ color: 'var(--text-primary)', fontWeight: 500 }}>{f.label}</td>
                    <td>
                      {f.sensitive ? (
                        <MaskedField value={f.value} />
                      ) : (
                        <span className="mono" style={{ color: 'var(--text-secondary)' }}>
                          {f.value}
                        </span>
                      )}
                    </td>
                    <td className="mono" style={{ color: 'var(--text-muted)', fontSize: '0.75rem' }}>
                      {f.description}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  );
}
