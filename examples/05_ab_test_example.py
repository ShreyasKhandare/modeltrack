"""Example: Run an A/B test between two model versions"""

import numpy as np
from modeltrack.models.ab_test import ABTest
from modeltrack.models.registry import ModelRegistry

if __name__ == "__main__":
    # Create test
    test = ABTest(
        name="v1.0_vs_v1.1",
        model_a="yield_predictor:1.0.0",
        model_b="yield_predictor:1.1.0",
        traffic_split=0.2,
    )
    test_id = test.start()
    print(f"✓ A/B test started: {test_id}")

    # Simulate observations
    np.random.seed(42)
    for i in range(200):
        # Simulate both models making predictions and actual outcome
        pred_a = np.random.uniform(85, 99)
        pred_b = np.random.uniform(85, 99)
        actual = np.random.uniform(85, 99)

        # Record
        if i % 5 == 0:
            test.record("model_a", pred_a, actual, latency_ms=10)
        else:
            test.record("model_b", pred_b, actual, latency_ms=12)

    # Get results
    metrics = test.get_metrics()
    winner = test.winner()

    print(f"Model A metrics: {metrics['model_a']}")
    print(f"Model B metrics: {metrics['model_b']}")
    print(f"Winner: {winner}")

    # Complete
    test.complete(winner=winner)
    print(f"✓ A/B test completed")
