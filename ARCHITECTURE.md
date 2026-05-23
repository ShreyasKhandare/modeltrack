# ModelTrack Architecture

## Overview

ModelTrack is a unified framework for managing data pipelines and ML models in production.

```
┌─────────────────────────────────────────────────────────┐
│                      Users                              │
├─────────────────────────────────────────────────────────┤
│  Dashboard (Streamlit)  │  REST API  │  CLI (Click)     │
├─────────────────────────────────────────────────────────┤
│              Unified Core (modeltrack/)                 │
├─────────────────┬──────────────────┬────────────────────┤
│  Pipelines      │  Models          │  Shared            │
│  - core         │  - registry      │  - database        │
│  - validators   │  - ab_test       │  - logger          │
│  - lineage      │  - promotion     │  - errors          │
│  - executor     │  - retraining    │  - utils           │
├─────────────────┴──────────────────┴────────────────────┤
│           Database (SQLite / PostgreSQL)                │
└─────────────────────────────────────────────────────────┘
```

## Components

### Pipelines
- Define DAGs as Python code (@pipeline decorator)
- Execute asynchronously with dependency resolution
- Validate data at each stage
- Track lineage (inputs/outputs)
- Checkpoint intermediate results
- Retry with exponential backoff

### Models
- Registry: version, store, retrieve models
- A/B Testing: compare models in production
- Promotion: safe stage gates (dev → staging → prod)
- Retraining: schedule-based or trigger-based
- Rollback: instant version rollback

### API & Dashboard
- REST: All operations via HTTP
- Streamlit: Real-time monitoring
- CLI: Command-line operations

## Database Schema

See modeltrack/shared/database.py for full schema.

Key tables:
- pipeline_runs, task_runs (execution history)
- lineage_nodes, lineage_edges (data lineage)
- model_records (model metadata)
- ab_test_records (A/B test state)
