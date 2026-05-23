# ModelTrack

**A unified data pipeline and model registry framework.**

---

## Why ModelTrack?

Every ML project eventually ends up with the same problems: ad-hoc scripts that
mutate data in unpredictable ways, model files scattered across team members'
laptops, and no clear answer to "which version of the model is in production
right now — and is it actually better than the previous one?"

ModelTrack was built to solve exactly those problems.  It is opinionated enough
to provide real guardrails, but flexible enough to slot into any Python-based
ML stack.  Write pipelines as plain Python functions, register models with a
one-liner, and let the framework handle versioning, lineage, A/B testing, and
promotion gates.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        ModelTrack                               │
│                                                                 │
│  ┌──────────────────────────┐  ┌──────────────────────────┐   │
│  │     Pipelines Module     │  │      Models Module        │   │
│  │                          │  │                           │   │
│  │  @pipeline decorator     │  │  ModelRegistry            │   │
│  │  Task (>> operator)      │  │  ├── save / get           │   │
│  │  DAGExecutor             │  │  ├── promote / delete     │   │
│  │  ├── run / run_sync      │  │  └── compare_versions     │   │
│  │  ├── retry / timeout     │  │                           │   │
│  │  └── checkpoints         │  │  ABTest                   │   │
│  │                          │  │  ├── start / record       │   │
│  │  Validators              │  │  ├── get_metrics          │   │
│  │  ├── NullChecker         │  │  └── winner / complete    │   │
│  │  ├── SchemaValidator     │  │                           │   │
│  │  ├── OutlierDetector     │  │  PromotionManager         │   │
│  │  ├── DuplicateChecker    │  │  ├── PromotionGate        │   │
│  │  └── DataValidator       │  │  └── audit trail          │   │
│  │                          │  │                           │   │
│  │  LineageTracker          │  │  RetrainingJob            │   │
│  └──────────────────────────┘  └──────────────────────────┘   │
│                                                                 │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │                    Shared Layer                           │  │
│  │  config (pydantic-settings) │ logger (JSON) │ utils      │  │
│  │  database (SQLAlchemy 2.0 ORM + SQLite / Postgres)       │  │
│  │  errors (typed exception hierarchy)                      │  │
│  └──────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

---

## Quick Start

### Installation

```bash
git clone https://github.com/example/modeltrack.git
cd modeltrack
pip install -e .
```

### Define and run a pipeline

```python
from modeltrack.pipelines import pipeline, Task, DAGExecutor

def load_data(path: str):
    import pandas as pd
    return pd.read_csv(path)

def clean_data(data):
    return data.dropna()

def train_model(data):
    from sklearn.linear_model import LogisticRegression
    X, y = data.drop("label", axis=1), data["label"]
    return LogisticRegression().fit(X, y)

@pipeline("churn_pipeline")
def churn_pipeline():
    load   = Task("load",   load_data,   inputs={"path": "data/churn.csv"})
    clean  = Task("clean",  clean_data)
    train  = Task("train",  train_model)
    load >> clean >> train
    return load

executor = DAGExecutor()
result = executor.run_sync(churn_pipeline)
print(result.status)       # "success"
print(result.results)      # {"load": <df>, "clean": <df>, "train": <model>}
```

### Validate data

```python
from modeltrack.pipelines.validators import DataValidator, NullChecker, SchemaValidator

report = (
    DataValidator()
    .add(NullChecker(["feature_1", "feature_2"], max_null_pct=0.05))
    .add(SchemaValidator({"feature_1": "float64", "label": "int64"}))
    .validate(df)
)

print(f"Valid: {report.is_valid}, {report.valid_pct:.1%} records passed")
```

### Register and promote a model

```python
from modeltrack.models import ModelRegistry, Model
from modeltrack.models.promotion import PromotionManager, PromotionGate
from modeltrack.shared.database import get_session, init_db

init_db()

with get_session() as session:
    registry = ModelRegistry(models_dir="./models_store", db_session=session)

    # Save
    model = Model(
        name="churn_predictor",
        version="1.0.0",
        model_binary=trained_clf,
        metrics={"accuracy": 0.92, "f1": 0.90},
    )
    registry.save(model)

    # Promote with gates
    manager = PromotionManager(registry, db_session=session)
    manager.promote(
        "churn_predictor", "1.0.0", "production",
        gates=[
            PromotionGate("accuracy", 0.90, ">="),
            PromotionGate("f1",       0.85, ">="),
        ],
    )
```

### Run an A/B test

```python
from modeltrack.models.ab_test import ABTest

test = ABTest(
    name="churn_v1_vs_v2",
    model_a="churn_predictor:1.0.0",
    model_b="churn_predictor:2.0.0",
    traffic_split=0.1,   # 10 % of traffic → model B
)
test_id = test.start()

# … for each incoming request …
test.record("model_a", prediction=0.82, actual=1.0, latency_ms=12)
test.record("model_b", prediction=0.91, actual=1.0, latency_ms=15)

print(test.get_metrics())
print(test.is_significant())   # True / False
print(test.winner())           # "model_a", "model_b", or None
```

---

## API Endpoints Table

| Component | Class / Function | Key Method(s) |
|---|---|---|
| Pipeline | `@pipeline(name)` | — |
| Task | `Task(name, func, inputs)` | `run(**kwargs)`, `>>` |
| Executor | `DAGExecutor` | `run_sync(pipeline, context)` |
| Validation | `DataValidator` | `.add(validator).validate(df)` |
| Null check | `NullChecker(cols, max_null_pct)` | `.check(df)` |
| Schema check | `SchemaValidator(schema_dict)` | `.validate(df)` |
| Outliers | `OutlierDetector(cols, method)` | `.detect(df)` |
| Duplicates | `DuplicateChecker(cols)` | `.check(df)` |
| Lineage | `LineageTracker(run_id, session)` | `record_task_start`, `add_edge`, `get_lineage_graph` |
| Registry | `ModelRegistry(models_dir, session)` | `save`, `get`, `promote`, `delete`, `compare_versions` |
| A/B Test | `ABTest(name, model_a, model_b)` | `start`, `record`, `get_metrics`, `winner`, `complete` |
| Promotion | `PromotionManager(registry)` | `promote`, `rollback`, `get_audit_trail` |
| Gate | `PromotionGate(metric, threshold)` | `check(metrics)` |
| Retraining | `RetrainingJob(name, train_func)` | `trigger(new_data)` |
| Checkpoint | `CheckpointManager(dir)` | `save`, `load`, `exists` |

---

## Configuration

All settings are loaded from environment variables (or a `.env` file):

| Variable | Default | Description |
|---|---|---|
| `DATABASE_URL` | `sqlite:///./modeltrack.db` | SQLAlchemy database URL |
| `API_HOST` | `0.0.0.0` | API server bind host |
| `API_PORT` | `8000` | API server port |
| `LOG_LEVEL` | `INFO` | Logging level |
| `MODELS_DIR` | `./models_store` | Model binary storage directory |
| `PIPELINES_DIR` | `./pipelines_store` | Pipeline definition storage directory |

---

## Dashboard (Streamlit)

Start the real-time dashboard for monitoring:

```bash
streamlit run dashboards/main.py
```

Navigate to `http://localhost:8501` and explore:
- **Pipelines Tab**: View pipeline runs, execution status, data quality metrics
- **Models Tab**: Browse model registry, view A/B test results, inspect promotion history
- **Settings Tab**: Configure database, API host/port, logging level

---

## Docker Deployment

### Local Development

```bash
docker-compose -f docker/docker-compose.yml up --build
```

This starts:
- API on `http://localhost:8000`
- Dashboard on `http://localhost:8501`
- PostgreSQL on `localhost:5432`

### Production Image

```bash
docker build -f docker/Dockerfile -t modeltrack:latest .
docker run -p 8000:8000 -e DATABASE_URL=postgresql://... modeltrack:latest
```

---

## Examples

All examples are in the `examples/` directory and can be run directly:

### 1. Simple Pipeline
```bash
python examples/01_simple_pipeline.py
```
Demonstrates basic pipeline definition with read → clean → aggregate.

### 2. Fab Data Pipeline
```bash
python examples/02_fab_data_pipeline.py
```
Realistic fab sensor data pipeline with built-in validation and anomaly detection.

### 3. Model Training
```bash
python examples/03_yield_model.py
```
Train and register a yield prediction model, compute metrics.

### 4. A/B Testing
```bash
python examples/05_ab_test_example.py
```
Run an A/B test between two model versions, compute winner.

---

## CI/CD with GitHub Actions

The repository includes a GitHub Actions workflow that runs on every push/PR:

```yaml
# .github/workflows/ci.yml

1. **Lint**: flake8 on all modules (max line length 127)
2. **Format**: black check on code
3. **Test**: pytest with coverage reporting
4. **Build**: Docker image build and test (on main branch only)
```

See `.github/workflows/ci.yml` for full configuration.

---

## REST API

The framework includes a FastAPI-based REST interface. Start the API server:

```bash
python -m modeltrack.api.main
```

### Key Endpoints

**Pipelines**
- `POST /pipelines/{name}/run` - Start a pipeline
- `GET /pipelines/{run_id}` - Get pipeline run status
- `GET /pipelines` - List recent runs

**Models**
- `POST /models/register` - Register a model
- `GET /models/{name}/{version}` - Get model metadata
- `POST /models/{name}/{version}/promote` - Promote to next stage
- `GET /models/{name}/history` - Version history

**A/B Tests**
- `POST /tests` - Create test
- `POST /tests/{test_id}/record` - Record observation
- `GET /tests/{test_id}` - Get results

See `modeltrack/api/` for endpoint implementations.

---

## Architecture Deep Dive

See `ARCHITECTURE.md` for detailed component descriptions, database schema, and design patterns.

---

## Development Checklist

- [x] Pipelines: DAG execution, validation, lineage
- [x] Models: Registry, versioning, promotion gates
- [x] A/B Tests: Statistical testing, winner determination
- [x] REST API: Full CRUD operations
- [x] CLI: Command-line interface
- [x] Dashboard: Real-time Streamlit monitoring
- [x] Examples: Real-world use cases
- [x] Docker: Production-ready containerization
- [x] CI/CD: GitHub Actions automation
- [x] Logging: Structured JSON logging
- [x] Error Handling: Typed exception hierarchy
- [x] Database: SQLAlchemy ORM with migrations

---

## Running Tests

```bash
pip install -e ".[dev]"
pytest tests/ -v --cov=modeltrack --cov-report=term-missing
```

**Key test files:**
- `tests/test_pipeline_core.py` - Pipeline DAG execution
- `tests/test_pipeline_validators.py` - Data validation
- `tests/test_pipeline_lineage.py` - Data lineage tracking
- `tests/test_model_registry.py` - Model versioning and storage
- `tests/test_model_ab_test.py` - A/B testing logic
- `tests/test_api_pipelines.py` - REST API endpoints
- `tests/test_api_models.py` - Model API endpoints

---

## Roadmap

Future enhancements:
- [ ] Distributed execution (Ray / Dask)
- [ ] ML observability integrations (Weights & Biases, MLflow)
- [ ] Auto-retraining triggers (drift detection)
- [ ] Web UI for model comparison
- [ ] Slack/email notifications
- [ ] Model explainability reports (SHAP)

---

## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/foo`)
3. Commit changes and push
4. Open a pull request

All PRs must:
- Pass pytest
- Pass flake8 (max 127 chars)
- Pass black formatting check
- Include docstrings

---

## Support

For issues, questions, or contributions:
- GitHub: [ShreyasKhandare/modeltrack](https://github.com/ShreyasKhandare/modeltrack)
- Email: khandareshreyas1@gmail.com

---

## License

MIT
