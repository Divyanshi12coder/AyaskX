/**
 * src/components/Sidebar.tsx
 * Enterprise sidebar navigation.
 */

import React from 'react';
import { NavLink } from 'react-router-dom';
import {
  Activity,
  Archive,
  BarChart2,
  Cpu,
  Database,
  FileText,
  FlaskConical,
  Globe,
  Heart,
  Key,
  Lock,
  Map,
  PlayCircle,
  Server,
  Settings,
  Shield,
  Users,
  Zap,
} from 'lucide-react';

interface NavItem {
  to: string;
  icon: React.ReactNode;
  label: string;
}

function SidebarSection({ label, items }: { label: string; items: NavItem[] }) {
  return (
    <div className="sidebar-section">
      <div className="sidebar-section-label">{label}</div>
      {items.map((item) => (
        <NavLink
          key={item.to}
          to={item.to}
          className={({ isActive }) =>
            `sidebar-item${isActive ? ' active' : ''}`
          }
        >
          {item.icon}
          <span>{item.label}</span>
        </NavLink>
      ))}
    </div>
  );
}

export function Sidebar() {
  const opsItems: NavItem[] = [
    { to: '/', icon: <Activity />, label: 'Command Center' },
    { to: '/datasets', icon: <Database />, label: 'Datasets' },
    { to: '/pipelines', icon: <PlayCircle />, label: 'Pipelines' },
    { to: '/models', icon: <FlaskConical />, label: 'Models' },
    { to: '/inference', icon: <Cpu />, label: 'Inference' },
    { to: '/self-healing', icon: <Heart />, label: 'Self-Healing' },
    { to: '/checkpoints', icon: <Archive />, label: 'Checkpoints' },
    { to: '/geospatial', icon: <Map />, label: 'Geospatial' },
    { to: '/observability', icon: <BarChart2 />, label: 'Observability' },
    { to: '/integrity', icon: <Shield />, label: 'Integrity' },
    { to: '/audit', icon: <FileText />, label: 'Audit' },
  ];

  const adminItems: NavItem[] = [
    { to: '/admin', icon: <Server />, label: 'Overview' },
    { to: '/admin/users', icon: <Users />, label: 'Users' },
    { to: '/admin/roles', icon: <Lock />, label: 'Roles & Permissions' },
    { to: '/admin/config', icon: <Settings />, label: 'System Config' },
    { to: '/admin/connections', icon: <Key />, label: 'API / Connections' },
    { to: '/admin/storage', icon: <Globe />, label: 'Storage' },
    { to: '/admin/runtime', icon: <Zap />, label: 'Runtime' },
    { to: '/admin/audit-policies', icon: <Shield />, label: 'Audit Policies' },
  ];

  return (
    <aside className="sidebar">
      <div className="sidebar-logo">
        <div className="sidebar-logo-mark">AX</div>
        <span className="sidebar-logo-text">
          Ayask<span>X</span>
        </span>
      </div>

      <nav className="sidebar-nav">
        <SidebarSection label="Operations" items={opsItems} />
        <SidebarSection label="Administration" items={adminItems} />
      </nav>

      <div className="sidebar-bottom">
        <div
          className="sidebar-item"
          style={{ cursor: 'default', fontSize: '0.75rem' }}
        >
          <Server size={13} />
          <span>AyaskX v1.0.0</span>
        </div>
      </div>
    </aside>
  );
}
