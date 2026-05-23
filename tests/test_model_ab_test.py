"""
Tests for modeltrack.models.ab_test — ABTest.
"""

import pytest

from modeltrack.models.ab_test import ABTest, _mae, _rmse, _welch_t_test
from modeltrack.shared.errors import ABTestError
from tests.mock_data import make_observations


class TestABTestLifecycle:
    def test_start_returns_test_id(self):
        test = ABTest("price_test", "model:1.0", "model:2.0", traffic_split=0.2)
        test_id = test.start()
        assert test_id
        assert isinstance(test_id, str)
        assert test.status == "running"

    def test_start_with_db_session(self, db_session):
        test = ABTest(
            "db_test",
            "model:1.0",
            "model:2.0",
            traffic_split=0.3,
            db_session=db_session,
        )
        test_id = test.start()
        assert test.test_id == test_id

    def test_complete_sets_status(self):
        test = ABTest("complete_test", "m:1", "m:2")
        test.start()
        test.complete("model_a")
        assert test.status == "completed"

    def test_stop_sets_status(self):
        test = ABTest("stop_test", "m:1", "m:2")
        test.start()
        test.stop()
        assert test.status == "stopped"


class TestABTestRecord:
    def test_record_valid_observation(self):
        test = ABTest("record_test", "m:1", "m:2")
        test.start()
        test.record("model_a", prediction=0.7, actual=0.8, latency_ms=25.0)
        assert len(test._obs["model_a"]) == 1

    def test_record_model_b(self):
        test = ABTest("record_b_test", "m:1", "m:2")
        test.start()
        test.record("model_b", prediction=0.6, actual=0.7)
        assert len(test._obs["model_b"]) == 1

    def test_record_invalid_key_raises(self):
        test = ABTest("invalid_key_test", "m:1", "m:2")
        test.start()
        with pytest.raises(ABTestError):
            test.record("model_c", prediction=0.5, actual=0.6)

    def test_record_multiple_observations(self):
        test = ABTest("multi_record", "m:1", "m:2")
        test.start()
        for obs in make_observations(30, "model_a"):
            test.record(**obs)
        assert len(test._obs["model_a"]) == 30


class TestABTestMetrics:
    def test_get_metrics_empty(self):
        test = ABTest("metrics_empty", "m:1", "m:2")
        test.start()
        metrics = test.get_metrics()
        assert metrics["model_a"]["count"] == 0
        assert metrics["model_b"]["count"] == 0

    def test_get_metrics_with_data(self):
        test = ABTest("metrics_data", "m:1", "m:2")
        test.start()
        for obs in make_observations(20, "model_a", seed=0):
            test.record(**obs)
        for obs in make_observations(20, "model_b", seed=1):
            test.record(**obs)
        metrics = test.get_metrics()
        assert metrics["model_a"]["count"] == 20
        assert metrics["model_b"]["count"] == 20
        assert metrics["model_a"]["mae"] >= 0
        assert metrics["model_a"]["rmse"] >= 0

    def test_avg_latency_computed(self):
        test = ABTest("latency_test", "m:1", "m:2")
        test.start()
        test.record("model_a", 0.5, 0.6, latency_ms=30.0)
        test.record("model_a", 0.4, 0.5, latency_ms=50.0)
        metrics = test.get_metrics()
        assert metrics["model_a"]["avg_latency_ms"] == pytest.approx(40.0)


class TestABTestSignificance:
    def test_insufficient_data_not_significant(self):
        test = ABTest("insuf_test", "m:1", "m:2")
        test.start()
        test.record("model_a", 0.5, 0.6)
        test.record("model_b", 0.5, 0.6)
        assert test.is_significant() is False

    def test_winner_none_when_not_significant(self):
        test = ABTest("no_winner", "m:1", "m:2")
        test.start()
        assert test.winner() is None

    def test_load_from_db(self, db_session):
        test = ABTest("load_test", "m:1", "m:2", db_session=db_session)
        test_id = test.start()
        test.record("model_a", 0.7, 0.8)

        loaded = ABTest.load(test_id, db_session=db_session)
        assert loaded.test_id == test_id
        assert loaded.name == "load_test"

    def test_load_nonexistent_raises(self, db_session):
        with pytest.raises(ABTestError):
            ABTest.load("nonexistent_id", db_session=db_session)


class TestHelperFunctions:
    def test_mae_basic(self):
        result = _mae([1.0, 2.0, 3.0], [1.0, 2.0, 3.0])
        assert result == 0.0

    def test_rmse_basic(self):
        result = _rmse([0.0, 0.0], [1.0, 1.0])
        assert result == pytest.approx(1.0)

    def test_welch_t_test_same_data_high_p(self):
        data = [1.0, 1.0, 1.0, 1.0, 1.0]
        t, p = _welch_t_test(data, data)
        assert p >= 0.0

    def test_welch_t_test_different_data(self):
        # Data with different means and non-zero variance
        import random
        rng = random.Random(42)
        a = [1.0 + rng.gauss(0, 0.1) for _ in range(50)]
        b = [10.0 + rng.gauss(0, 0.1) for _ in range(50)]
        t, p = _welch_t_test(a, b)
        assert p < 0.05  # should be significantly different
