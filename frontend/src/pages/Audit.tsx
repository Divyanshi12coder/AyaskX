/**
 * src/pages/Audit.tsx
 * Complete audit log interface with filters and detail drawer.
 */

import React, { useState, useMemo } from 'react';
import { auditApi } from '../api/endpoints';
import type { AuditEvent } from '../types';
import { useApi } from '../hooks/useApi';
import { StatusBadge } from '../components/ui/StatusBadge';
import { LoadingState } from '../components/ui/LoadingState';
import { ErrorState } from '../components/ui/ErrorState';
import { EmptyState } from '../components/ui/EmptyState';
import { PageHeader } from '../components/ui/PageHeader';
import { DetailDrawer } from '../components/ui/DetailDrawer';

const SEVERITIES = ['all', 'info', 'warning', 'error', 'critical'];

export default function Audit() {
  const [selectedEvent, setSelectedEvent] = useState<AuditEvent | null>(null);
  const [search, setSearch] = useState('');
  const [sevFilter, setSevFilter] = useState('all');
  const [execFilter, setExecFilter] = useState('');

  const { data, loading, error, refetch } = useApi(() => auditApi.events());

  const events: AuditEvent[] = useMemo(() => {
    if (!data) return [];
    let list = [...data].sort(
      (a, b) =>
        new Date(b.timestamp ?? 0).getTime() - new Date(a.timestamp ?? 0).getTime()
    );
    if (sevFilter !== 'all') list = list.filter((e) => e.severity === sevFilter);
    if (execFilter) list = list.filter((e) => e.execution_id?.includes(execFilter));
    if (search)
      list = list.filter(
        (e) =>
          e.action?.toLowerCase().includes(search.toLowerCase()) ||
          e.resource?.toLowerCase().includes(search.toLowerCase()) ||
          e.event_id?.includes(search) ||
          e.actor?.toLowerCase().includes(search.toLowerCase())
      );
    return list;
  }, [data, sevFilter, execFilter, search]);

  return (
    <div className="flex flex-col h-full overflow-hidden">
      <PageHeader
        title="Audit Log"
        subtitle={`${data?.length ?? 0} total events`}
        breadcrumbs={[{ label: 'AyaskX' }, { label: 'Audit' }]}
      />

      {/* Filters */}
      <div className="filter-bar">
        <div style={{ display: 'flex', gap: 4 }}>
          {SEVERITIES.map((s) => (
            <button
              key={s}
              className={`btn btn-sm ${sevFilter === s ? 'btn-secondary' : 'btn-ghost'}`}
              onClick={() => setSevFilter(s)}
              style={{ textTransform: 'capitalize' }}
            >
              {s}
            </button>
          ))}
        </div>
        <input
          className="input"
          style={{ maxWidth: 200 }}
          placeholder="Search action, resource…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
        <input
          className="input"
          style={{ maxWidth: 180 }}
          placeholder="Filter by execution ID…"
          value={execFilter}
          onChange={(e) => setExecFilter(e.target.value)}
        />
        <span style={{ marginLeft: 'auto', fontSize: '0.77rem', color: 'var(--text-muted)' }}>
          {events.length} result{events.length !== 1 ? 's' : ''}
        </span>
      </div>

      <div style={{ flex: 1, overflow: 'auto' }}>
        {loading ? (
          <LoadingState />
        ) : error ? (
          <ErrorState message={error} onRetry={refetch} />
        ) : events.length === 0 ? (
          <EmptyState
            title="No audit events"
            message="Audit events are generated as the system executes pipelines and operations."
          />
        ) : (
          <table className="data-table">
            <thead>
              <tr>
                <th>Timestamp</th>
                <th>Actor</th>
                <th>Action</th>
                <th>Resource</th>
                <th>Resource ID</th>
                <th>Result</th>
                <th>Severity</th>
                <th>Execution</th>
              </tr>
            </thead>
            <tbody>
              {events.map((ev, i) => (
                <tr key={ev.event_id ?? i} onClick={() => setSelectedEvent(ev)}>
                  <td className="mono" style={{ fontSize: '0.77rem' }}>
                    {ev.timestamp ? new Date(ev.timestamp).toLocaleString() : '—'}
                  </td>
                  <td>{ev.actor ?? '—'}</td>
                  <td className="text-primary">{ev.action ?? '—'}</td>
                  <td>{ev.resource ?? '—'}</td>
                  <td className="mono" style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>
                    {ev.resource_id?.slice(0, 12) ?? '—'}
                  </td>
                  <td>{ev.result ?? '—'}</td>
                  <td>
                    <StatusBadge
                      value={ev.severity ?? 'info'}
                      variant={
                        ev.severity === 'error' || ev.severity === 'critical'
                          ? 'error'
                          : ev.severity === 'warning'
                          ? 'warning'
                          : 'info'
                      }
                    />
                  </td>
                  <td className="mono" style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>
                    {ev.execution_id?.slice(0, 12) ?? '—'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <DetailDrawer
        open={!!selectedEvent}
        onClose={() => setSelectedEvent(null)}
        title="Audit Event Detail"
      >
        {selectedEvent && (
          <div>
            <div className="kv-grid">
              <div className="kv-key">Event ID</div>
              <div className="kv-val mono">{selectedEvent.event_id ?? '—'}</div>
              <div className="kv-key">Timestamp</div>
              <div className="kv-val mono">
                {selectedEvent.timestamp
                  ? new Date(selectedEvent.timestamp).toLocaleString()
                  : '—'}
              </div>
              <div className="kv-key">Actor</div>
              <div className="kv-val">{selectedEvent.actor ?? '—'}</div>
              <div className="kv-key">Action</div>
              <div className="kv-val">{selectedEvent.action ?? '—'}</div>
              <div className="kv-key">Resource</div>
              <div className="kv-val">{selectedEvent.resource ?? '—'}</div>
              <div className="kv-key">Resource ID</div>
              <div className="kv-val mono">{selectedEvent.resource_id ?? '—'}</div>
              <div className="kv-key">Result</div>
              <div className="kv-val">{selectedEvent.result ?? '—'}</div>
              <div className="kv-key">Severity</div>
              <div className="kv-val">
                <StatusBadge
                  value={selectedEvent.severity ?? 'info'}
                  variant={
                    selectedEvent.severity === 'error' || selectedEvent.severity === 'critical'
                      ? 'error'
                      : selectedEvent.severity === 'warning'
                      ? 'warning'
                      : 'info'
                  }
                />
              </div>
              <div className="kv-key">Execution ID</div>
              <div className="kv-val mono">{selectedEvent.execution_id ?? '—'}</div>
            </div>

            {selectedEvent.metadata &&
              Object.keys(selectedEvent.metadata).length > 0 && (
                <div style={{ marginTop: 16 }}>
                  <div className="section-title" style={{ marginBottom: 8 }}>
                    Metadata
                  </div>
                  <div className="code-block">
                    {JSON.stringify(selectedEvent.metadata, null, 2)}
                  </div>
                </div>
              )}
          </div>
        )}
      </DetailDrawer>
    </div>
  );
}
