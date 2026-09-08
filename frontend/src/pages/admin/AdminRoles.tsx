/**
 * src/pages/admin/AdminRoles.tsx
 */

import React from 'react';
import { StatusBadge } from '../../components/ui/StatusBadge';
import { PageHeader } from '../../components/ui/PageHeader';

const ROLES = [
  {
    name: 'Admin',
    description: 'Full system access. Manage users, config, all operations.',
    permissions: ['view_datasets', 'upload_datasets', 'run_pipelines', 'manage_models', 'run_inference', 'view_self_healing', 'execute_recovery', 'view_audit', 'manage_system'],
  },
  {
    name: 'Researcher',
    description: 'Run experiments, view all results. No system config.',
    permissions: ['view_datasets', 'upload_datasets', 'run_pipelines', 'manage_models', 'run_inference', 'view_self_healing', 'view_audit'],
  },
  {
    name: 'Operator',
    description: 'Monitor pipelines, trigger recovery. No model management.',
    permissions: ['view_datasets', 'run_pipelines', 'view_self_healing', 'execute_recovery', 'view_audit'],
  },
  {
    name: 'Viewer',
    description: 'Read-only access to all data.',
    permissions: ['view_datasets', 'view_self_healing', 'view_audit'],
  },
];

const ALL_PERMISSIONS = [
  'view_datasets', 'upload_datasets', 'run_pipelines', 'manage_models',
  'run_inference', 'view_self_healing', 'execute_recovery', 'view_audit', 'manage_system',
];

export default function AdminRoles() {
  return (
    <div className="flex flex-col h-full overflow-hidden">
      <PageHeader
        title="Roles & Permissions"
        subtitle="Role-based access control architecture"
        breadcrumbs={[{ label: 'Admin' }, { label: 'Roles & Permissions' }]}
      />
      <div className="page-body">
        <div
          style={{
            padding: '10px 14px',
            marginBottom: 20,
            background: 'var(--status-warning-dim)',
            border: '1px solid rgba(245,158,11,0.25)',
            borderRadius: 'var(--radius-sm)',
            fontSize: '0.83rem',
            color: 'var(--status-warning)',
          }}
        >
          RBAC is not enforced by the current backend. This table shows the intended role
          architecture for future implementation. No backend permission checking occurs.
        </div>

        <div className="panel" style={{ padding: 0, overflow: 'auto' }}>
          <table className="data-table">
            <thead>
              <tr>
                <th style={{ width: 120 }}>Role</th>
                {ALL_PERMISSIONS.map((p) => (
                  <th key={p} style={{ textAlign: 'center', fontSize: '0.68rem' }}>
                    {p.replace(/_/g, ' ')}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {ROLES.map((role) => (
                <tr key={role.name}>
                  <td>
                    <div>
                      <div style={{ fontWeight: 600, color: 'var(--text-primary)', fontSize: '0.85rem' }}>
                        {role.name}
                      </div>
                      <div style={{ fontSize: '0.72rem', color: 'var(--text-muted)', marginTop: 2 }}>
                        {role.description}
                      </div>
                    </div>
                  </td>
                  {ALL_PERMISSIONS.map((p) => (
                    <td key={p} style={{ textAlign: 'center' }}>
                      {role.permissions.includes(p) ? (
                        <span style={{ color: 'var(--status-success)', fontWeight: 700, fontSize: '1rem' }}>✓</span>
                      ) : (
                        <span style={{ color: 'var(--text-disabled)' }}>—</span>
                      )}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
