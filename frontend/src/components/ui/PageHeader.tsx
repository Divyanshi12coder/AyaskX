/**
 * src/components/ui/PageHeader.tsx
 */

import React from 'react';

interface Crumb { label: string; href?: string; }

interface Props {
  title: string;
  subtitle?: string;
  breadcrumbs?: Crumb[];
  actions?: React.ReactNode;
}

export function PageHeader({ title, subtitle, breadcrumbs, actions }: Props) {
  return (
    <div className="page-header">
      <div className="page-header-left">
        {breadcrumbs && breadcrumbs.length > 0 && (
          <div className="breadcrumb">
            {breadcrumbs.map((c, i) => (
              <React.Fragment key={i}>
                {i > 0 && <span className="breadcrumb-sep">/</span>}
                <span style={{ color: c.href ? 'var(--accent)' : 'var(--text-muted)' }}>
                  {c.label}
                </span>
              </React.Fragment>
            ))}
          </div>
        )}
        <div className="page-header-title">{title}</div>
        {subtitle && <div className="page-header-sub">{subtitle}</div>}
      </div>
      {actions && (
        <div className="flex items-center gap-2">{actions}</div>
      )}
    </div>
  );
}
