/**
 * src/App.tsx
 * Root application router — all routes defined here.
 */

import React, { Suspense, lazy } from 'react';
import { Routes, Route, Navigate } from 'react-router-dom';
import { AppLayout } from './layouts/AppLayout';
import { LoadingState } from './components/ui/LoadingState';

// Lazy imports for code splitting
const CommandCenter = lazy(() => import('./pages/CommandCenter'));
const DatasetList = lazy(() => import('./pages/datasets/DatasetList'));
const DatasetDetail = lazy(() => import('./pages/datasets/DatasetDetail'));
const PipelineList = lazy(() => import('./pages/pipelines/PipelineList'));
const PipelineDetail = lazy(() => import('./pages/pipelines/PipelineDetail'));
const Models = lazy(() => import('./pages/Models'));
const Inference = lazy(() => import('./pages/Inference'));
const SelfHealing = lazy(() => import('./pages/SelfHealing'));
const Checkpoints = lazy(() => import('./pages/Checkpoints'));
const Geospatial = lazy(() => import('./pages/Geospatial'));
const Observability = lazy(() => import('./pages/Observability'));
const Integrity = lazy(() => import('./pages/Integrity'));
const Audit = lazy(() => import('./pages/Audit'));

// Admin
const AdminOverview = lazy(() => import('./pages/admin/AdminOverview'));
const AdminUsers = lazy(() => import('./pages/admin/AdminUsers'));
const AdminRoles = lazy(() => import('./pages/admin/AdminRoles'));
const AdminConfig = lazy(() => import('./pages/admin/AdminConfig'));
const AdminConnections = lazy(() => import('./pages/admin/AdminConnections'));
const AdminStorage = lazy(() => import('./pages/admin/AdminStorage'));
const AdminRuntime = lazy(() => import('./pages/admin/AdminRuntime'));
const AdminAuditPolicies = lazy(() => import('./pages/admin/AdminAuditPolicies'));

function PageFallback() {
  return (
    <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
      <LoadingState message="Loading page..." />
    </div>
  );
}

export default function App() {
  return (
    <Suspense fallback={<PageFallback />}>
      <Routes>
        <Route element={<AppLayout />}>
          {/* Operations */}
          <Route index element={<CommandCenter />} />
          <Route path="datasets" element={<DatasetList />} />
          <Route path="datasets/:datasetId" element={<DatasetDetail />} />
          <Route path="pipelines" element={<PipelineList />} />
          <Route path="pipelines/:executionId" element={<PipelineDetail />} />
          <Route path="models" element={<Models />} />
          <Route path="inference" element={<Inference />} />
          <Route path="self-healing" element={<SelfHealing />} />
          <Route path="checkpoints" element={<Checkpoints />} />
          <Route path="geospatial" element={<Geospatial />} />
          <Route path="observability" element={<Observability />} />
          <Route path="integrity" element={<Integrity />} />
          <Route path="audit" element={<Audit />} />

          {/* Administration */}
          <Route path="admin" element={<AdminOverview />} />
          <Route path="admin/users" element={<AdminUsers />} />
          <Route path="admin/roles" element={<AdminRoles />} />
          <Route path="admin/config" element={<AdminConfig />} />
          <Route path="admin/connections" element={<AdminConnections />} />
          <Route path="admin/storage" element={<AdminStorage />} />
          <Route path="admin/runtime" element={<AdminRuntime />} />
          <Route path="admin/audit-policies" element={<AdminAuditPolicies />} />

          {/* Fallback */}
          <Route path="*" element={<Navigate to="/" replace />} />
        </Route>
      </Routes>
    </Suspense>
  );
}
