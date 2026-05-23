"""Example: Train and register a yield prediction model"""

import pandas as pd
import numpy as np
from sklearn.ensemble import RandomForestRegressor
from sklearn.model_selection import train_test_split
from modeltrack.models.registry import ModelRegistry, Model


# Generate training data
def generate_fab_training_data(n_samples=500):
    return pd.DataFrame(
        {
            "temperature": np.random.normal(250, 20, n_samples),
            "pressure": np.random.normal(1e5, 5e3, n_samples),
            "humidity": np.random.uniform(30, 70, n_samples),
            "yield": np.random.uniform(85, 99, n_samples),
        }
    )


if __name__ == "__main__":
    # Generate and split data
    df = generate_fab_training_data(500)
    X = df[["temperature", "pressure", "humidity"]]
    y = df["yield"]
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2)

    # Train model
    model = RandomForestRegressor(n_estimators=100, random_state=42)
    model.fit(X_train, y_train)

    # Evaluate
    train_score = model.score(X_train, y_train)
    test_score = model.score(X_test, y_test)

    # Register
    registry = ModelRegistry()
    reg_model = Model(
        name="yield_predictor",
        version="1.0.0",
        model_binary=model,
        metrics={"train_r2": float(train_score), "test_r2": float(test_score)},
        hyperparameters={"n_estimators": 100},
        description="Random forest for fab yield prediction",
    )

    registry.save(reg_model)

    print("✓ Model registered: yield_predictor:1.0.0")
    print(f"  Train R²: {train_score:.3f}")
    print(f"  Test R²: {test_score:.3f}")
