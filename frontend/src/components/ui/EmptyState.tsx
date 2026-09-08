/**
 * src/components/ui/EmptyState.tsx
 */

import React from 'react';
import { Inbox } from 'lucide-react';

interface Props {
  title?: string;
  message?: string;
  action?: React.ReactNode;
  icon?: React.ReactNode;
}

export function EmptyState({
  title = 'No data',
  message,
  action,
  icon,
}: Props) {
  return (
    <div className="state-container">
      <div style={{ opacity: 0.3 }}>
        {icon ?? <Inbox size={40} />}
      </div>
      <p className="state-title">{title}</p>
      {message && <p className="state-sub">{message}</p>}
      {action && <div style={{ marginTop: 8 }}>{action}</div>}
    </div>
  );
}
