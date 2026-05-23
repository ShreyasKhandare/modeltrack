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

## Running Tests

```bash
pip install -e ".[dev]"
pytest tests/ -v --cov=modeltrack --cov-report=term-missing
```

---

## License

MIT
