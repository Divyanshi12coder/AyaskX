# AyaskX implementation status

Audit date: 2026-09-08

## Current architecture

AyaskX is a Python research-platform foundation with a React/Vite operations UI.

- `core/` contains dataset characterization and discovery, task and feature-role
  detection, leakage heuristics, preprocessing recommendations, validation
  selection/splitting, sklearn model candidates/training, inference, checkpoint
  and artifact-integrity primitives, fault/recovery/self-healing modules,
  observability, and geospatial input/feature-preparation utilities.
- `core.platform.AyaskXOrchestrator` is the intended end-to-end coordinator:
  characterize -> detect task -> detect roles/leakage -> recommend preprocessing
  -> select validation -> generate/train candidates -> save artifact -> support
  inference and failure analysis.
- `api/` exposes FastAPI routes and filesystem-backed dataset/execution stores.
  A separate SQLAlchemy persistence layer records core pipeline/recovery events.
- `frontend/` is a Vite React application. Its typed client calls the API through
  the development `/api` proxy.

There are two overlapping pipeline/checkpoint designs:

- the active platform path (`core.platform`, `core.pipeline`, and
  `core.pipeline.checkpoints`), and
- the older `core.pipeline_legacy.AyaskPipeline` and `core.checkpoints` package.

The legacy path remains tested but is not the API orchestration path. It should
not be extended until migration/deprecation ownership is decided.

## Working features

- CSV, TSV, and Parquet upload registration, metadata storage, profiling,
  target/task inspection, feature-role inspection, and leakage inspection.
- Tabular task detection, feature-role and leakage heuristics, validation strategy
  selection, validation splitting, sklearn candidate generation/training, and
  fitted-artifact inference.
- Dataset-aware preprocessing is incorporated in the trainer's sklearn pipeline;
  inference uses the stored fitted pipeline and validates feature columns.
- Checkpoint metadata/artifact storage, SHA-256 manifest verification, artifact
  integrity checks, and checkpoint trust selection.
- Fault detection/localization, root-cause analysis, recovery decisioning,
  sandboxed repair planning, rollback/rerun controls, and structured event output
  are implemented and covered by tests. Their actions are local process/filesystem
  actions, not infrastructure remediation.
- FastAPI dataset, pipeline, model, inference, recovery, audit, health, system,
  observability, and artifact-integrity routes are registered.
- The operational frontend compiles against the current API client. `npm run build`
  succeeds.
- Geospatial modules genuinely read and validate raster/vector inputs, validate
  CRS compatibility, derive terrain statistics/slope, inspect satellite rasters,
  and align/stack raster features.

## Partial features

- Pipeline execution is asynchronous only within an in-process daemon thread.
  Records are filesystem JSON and are not safe for multi-process workers or
  durable job recovery. Cancellation, queue control, resource limits, and job
  ownership are absent.
- The SQLAlchemy execution/recovery-event store and API JSON execution store are
  separate sources of truth. The API reads the JSON store; core orchestration also
  writes SQL records. There is no transaction or reconciliation between them.
- Self-healing analyzes and acts on pipeline-node/checkpoint state, but it cannot
  safely repair deployed services, external data sources, environments, or model
  quality. The recovery API only has meaningful results after a persisted failed
  execution is explicitly triggered.
- Geospatial support is ingestion/analysis/feature preparation only. There are no
  geospatial API routes, dataset registration flow, map tiles, spatial-model
  training path, label management, or prospectivity prediction/raster export.
- Observability is derived from stored execution records; it is not a metrics,
  tracing, or log aggregation system.
- The frontend includes honest unavailable-state pages for user/role management,
  external connections, runtime configuration mutation, and geospatial work.
  Those pages are not backed by those capabilities.

## Broken features and structural issues corrected in this audit

The following obvious structural defects were corrected without redesigning the
architecture:

- Pipeline node status was serialized with `Enum.__str__` (for example,
  `NodeStatus.FAILED`) while recovery expected a wire value. The service now
  writes enum `.value` and accepts legacy stored records safely.
- Recovery reconstruction referenced a non-existent `NodeStatus.UNKNOWN`. Unknown
  persisted node status now fails closed as `NodeStatus.FAILED`.
- SQLAlchemy is used by `core.database` and API readiness/status endpoints but was
  not declared in `pyproject.toml`; it is now declared as a runtime dependency.

Remaining defects/risk areas:

- `AYASKX_CORS_ORIGINS` defaults to `*` while credentialed CORS is enabled. This
  is unsuitable for a browser deployment; production must use explicit origins
  and an authentication design.
- All API routes currently have no authentication, authorization, tenancy,
  request audit identity, rate limiting, or CSRF/session policy. The frontend
  correctly reports that endpoint access is open.
- Uploads are parsed after buffering the entire request body and raw upload files
  stay in local storage indefinitely. There is no malware/content scanning,
  retention policy, quota accounting, encryption/key management, or object store.
- Model artifacts are joblib/pickle-based. Integrity manifests detect alteration
  after creation but do not make untrusted deserialization safe. Serving needs a
  trusted artifact boundary and allowlisted provenance.
- The orchestration pipeline has no experiment tracking, reproducible environment
  capture, deterministic seeds across all estimators, hyperparameter search,
  calibration/fairness/uncertainty analysis, drift monitoring, or model registry.
- The API pipeline loader treats TSV as CSV (it does not pass `sep="\t"`), while
  the dataset service handles TSV correctly. This is an API/core integration bug
  that should be fixed with a regression test before TSV pipeline runs are relied
  on.
- Frontend API types deliberately generalize several backend payloads. Candidate
  objects, lifecycle statuses, and dataset profile fields are not a fully enforced
  generated/shared contract. Add contract tests or generated OpenAPI types before
  broadening the UI.
- The UI calls the local Vite proxy by default; a production deployment requires a
  configured API base URL/reverse proxy and an authenticated CORS policy.

## Missing features

- Identity, RBAC, tenancy, secrets management, provenance/approval workflow, and
  production deployment controls.
- Database migrations, a durable job queue/worker model, object storage, model
  registry, experiment tracking, scheduled retraining, and deployment/rollback
  workflow.
- Full data contracts/versioning, lineage across uploads/training/artifacts,
  quality gates, quarantine/retention procedures, and reproducibility manifests.
- Geospatial APIs, STAC/catalog ingestion, labelled spatial training datasets,
  spatial cross-validation at scale, prospectivity model execution, and output
  raster/vector publication.
- A genuine monitoring system for latency, resource use, data/model drift, alert
  delivery, and operator acknowledgement.

## Test baseline

Before changes:

- Exact requested command, `python -m pytest -q`, could not start because the
  system Python has no `pytest` installed: `No module named pytest`.
- The repository virtual environment initially reported `333 passed, 22 failed,
  198 errors, 1 warning in 53.46s` inside the sandbox. The errors were dominated
  by Windows access denial on the default pytest/tempfile directory, so that
  result was not a reliable product-code baseline.

After the structural fixes, the existing repository virtual environment was run
outside that sandbox limitation:

```
.\\.venv\\Scripts\\python.exe -m pytest -q
552 passed, 1 skipped, 6 warnings in 26.28s
```

Warnings comprise one pytest collection warning for a dataclass named
`TestContext`, one Starlette/AnyIO deprecation warning, and four uses of the
deprecated Starlette 422 status constant. The frontend build passes; Vite warns
that `__dirname` in `vite.config.ts` will not be supported by its future native
config loader.

## Recommended implementation order

1. Establish production security boundaries: authentication/RBAC, explicit CORS,
   secrets handling, upload policy, artifact trust policy, and audit identity.
2. Consolidate persistence and execution ownership: database migrations, one
   execution state model, transactional lifecycle/events, and durable workers.
3. Repair and test API/core seams, beginning with TSV execution loading; introduce
   OpenAPI contract tests/shared frontend types.
4. Make ML runs reproducible and reviewable: dataset/artifact lineage, versioned
   configurations, seeds, experiment tracking, evaluation reports, and a model
   registry.
5. Extend the real self-healing boundary only after the execution model is
   durable; add approval gates and make external remediation integrations explicit.
6. Build geospatial integration end-to-end: registered inputs, CRS/metadata
   validation, labelled training flow, spatial validation, prospectivity outputs,
   and then API/UI endpoints.
7. Add operational monitoring, alert delivery, capacity limits, and deployment
   controls after the platform can persist and authenticate its state safely.
