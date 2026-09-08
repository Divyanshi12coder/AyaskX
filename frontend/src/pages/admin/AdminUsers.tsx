/**
 * src/pages/admin/AdminUsers.tsx
 * User management — no backend user API. Shows UI architecture with clear future-state note.
 */

import React from 'react';
import { PageHeader } from '../../components/ui/PageHeader';

export default function AdminUsers() {
  return (
    <div className="flex flex-col h-full overflow-hidden">
      <PageHeader
        title="Users"
        subtitle="User management"
        breadcrumbs={[{ label: 'Admin' }, { label: 'Users' }]}
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
          User management requires a backend authentication layer (JWT + user store). 
          No user management API is implemented in the current backend. This UI shows the
          intended architecture.
        </div>

        {/* Future-state UI architecture */}
        <div className="grid-2" style={{ alignItems: 'start' }}>
          <div className="panel" style={{ padding: 16, opacity: 0.5 }}>
            <h4 style={{ marginBottom: 12 }}>User Registry</h4>
            <table className="data-table">
              <thead>
                <tr>
                  <th>Username</th>
                  <th>Role</th>
                  <th>Status</th>
                  <th>Last Active</th>
                </tr>
              </thead>
              <tbody>
                <tr>
                  <td colSpan={4} style={{ textAlign: 'center', padding: 24, color: 'var(--text-muted)' }}>
                    No backend user API
                  </td>
                </tr>
              </tbody>
            </table>
          </div>

          <div className="panel" style={{ padding: 16 }}>
            <h4 style={{ marginBottom: 12 }}>Implementation Requirements</h4>
            <div style={{ fontSize: '0.83rem', color: 'var(--text-secondary)', lineHeight: 1.8 }}>
              <div>• POST /v1/auth/login — JWT issue</div>
              <div>• GET /v1/users — list users</div>
              <div>• POST /v1/users — create user</div>
              <div>• PUT /v1/users/:id — update user/role</div>
              <div>• DELETE /v1/users/:id — remove user</div>
              <div>• GET /v1/users/:id/sessions — active sessions</div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
