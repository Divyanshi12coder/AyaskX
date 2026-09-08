/**
 * src/pages/Geospatial.tsx
 * Geospatial workspace — no backend API endpoint currently available.
 * Shows an honest empty state with the conceptual workflow.
 */

import React from 'react';
import { Map } from 'lucide-react';
import { PageHeader } from '../components/ui/PageHeader';

export default function Geospatial() {
  const workflow = [
    'Whole Belt Definition',
    'Prospective Zone Identification',
    'Ranked Target Generation',
    'Drill Campaign Planning',
  ];

  return (
    <div className="flex flex-col h-full overflow-hidden">
      <PageHeader
        title="Geospatial Workspace"
        subtitle="Raster, terrain, satellite, vector, prospectivity analysis"
        breadcrumbs={[{ label: 'AyaskX' }, { label: 'Geospatial' }]}
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
          No geospatial API endpoint is currently exposed by the backend.
          The geospatial core modules exist but are not yet wired to an HTTP router.
        </div>

        <div className="grid-2" style={{ alignItems: 'start' }}>
          {/* Empty state */}
          <div className="panel" style={{ padding: 32, textAlign: 'center' }}>
            <Map
              size={48}
              style={{ color: 'var(--text-muted)', marginBottom: 16, opacity: 0.3 }}
            />
            <div
              style={{ fontSize: '0.92rem', fontWeight: 500, color: 'var(--text-secondary)', marginBottom: 8 }}
            >
              Geospatial Data Not Yet Available
            </div>
            <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>
              Connect the geospatial backend API to populate this workspace with raster
              layers, terrain data, satellite imagery, vector overlays, and prospectivity
              analysis.
            </div>
          </div>

          {/* Conceptual workflow */}
          <div className="panel" style={{ padding: 20 }}>
            <h4 style={{ marginBottom: 16 }}>Conceptual Workflow</h4>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 0 }}>
              {workflow.map((step, i) => (
                <div key={step} style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-start' }}>
                  <div
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: 12,
                      padding: '10px 12px',
                      borderRadius: 'var(--radius-sm)',
                      border: '1px solid var(--border)',
                      background: 'var(--bg-elevated)',
                      width: '100%',
                      opacity: 0.6,
                    }}
                  >
                    <span
                      style={{
                        width: 22,
                        height: 22,
                        borderRadius: '50%',
                        background: 'var(--bg-overlay)',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        fontSize: '0.72rem',
                        fontWeight: 700,
                        color: 'var(--text-muted)',
                        flexShrink: 0,
                      }}
                    >
                      {i + 1}
                    </span>
                    <span style={{ fontSize: '0.85rem', color: 'var(--text-secondary)' }}>
                      {step}
                    </span>
                  </div>
                  {i < workflow.length - 1 && (
                    <div
                      style={{
                        width: 1,
                        height: 14,
                        background: 'var(--border)',
                        marginLeft: 22,
                      }}
                    />
                  )}
                </div>
              ))}
            </div>

            <div
              style={{
                marginTop: 20,
                padding: '10px 12px',
                background: 'var(--bg-elevated)',
                borderRadius: 'var(--radius-sm)',
                fontSize: '0.77rem',
                color: 'var(--text-muted)',
              }}
            >
              Expected modules: raster/terrain/satellite/vector processing,
              prospectivity analysis, ranked target generation.
              Backend path: <code className="mono">core/geospatial/</code>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
