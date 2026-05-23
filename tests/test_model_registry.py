"""
Tests for modeltrack.models.registry — ModelRegistry and Model.
"""

import os
import pytest

from modeltrack.models.registry import Model, ModelRegistry
from modeltrack.shared.errors import ModelAlreadyExistsError, ModelNotFoundError
from tests.mock_data import make_model, make_model_v2, make_sklearn_classifier


class TestModelSave:
    def test_save_returns_id(self, db_session, temp_dir):
        registry = ModelRegistry(models_dir=temp_dir, db_session=db_session)
        model = make_model()
        model_id = registry.save(model)
        assert model_id
        assert isinstance(model_id, str)

    def test_save_creates_binary_on_disk(self, db_session, temp_dir):
        registry = ModelRegistry(models_dir=temp_dir, db_session=db_session)
        model = make_model(name="disk_test", version="1.0.0")
        registry.save(model)
        assert model.model_path is not None
        assert os.path.exists(model.model_path)

    def test_save_duplicate_raises(self, db_session, temp_dir):
        registry = ModelRegistry(models_dir=temp_dir, db_session=db_session)
        model = make_model(name="dup_model", version="1.0.0")
        registry.save(model)
        model2 = make_model(name="dup_model", version="1.0.0")
        with pytest.raises(ModelAlreadyExistsError):
            registry.save(model2)

    def test_save_different_versions(self, db_session, temp_dir):
        registry = ModelRegistry(models_dir=temp_dir, db_session=db_session)
        m1 = make_model(name="versioned", version="1.0.0")
        m2 = make_model(name="versioned", version="2.0.0")
        id1 = registry.save(m1)
        id2 = registry.save(m2)
        assert id1 != id2


class TestModelGet:
    def test_get_by_version(self, db_session, temp_dir):
        registry = ModelRegistry(models_dir=temp_dir, db_session=db_session)
        model = make_model(name="get_test", version="1.0.0")
        registry.save(model)
        loaded = registry.get("get_test", version="1.0.0")
        assert loaded.name == "get_test"
        assert loaded.version == "1.0.0"

    def test_get_by_stage(self, db_session, temp_dir):
        registry = ModelRegistry(models_dir=temp_dir, db_session=db_session)
        model = make_model(name="stage_test", version="1.0.0", stage="staging")
        registry.save(model)
        loaded = registry.get("stage_test", stage="staging")
        assert loaded.stage == "staging"

    def test_get_not_found_raises(self, db_session, temp_dir):
        registry = ModelRegistry(models_dir=temp_dir, db_session=db_session)
        with pytest.raises(ModelNotFoundError):
            registry.get("nonexistent_model")

    def test_get_production(self, db_session, temp_dir):
        registry = ModelRegistry(models_dir=temp_dir, db_session=db_session)
        model = make_model(name="prod_test", version="1.0.0", stage="production")
        registry.save(model)
        loaded = registry.get_production("prod_test")
        assert loaded.stage == "production"

    def test_get_loads_binary(self, db_session, temp_dir):
        registry = ModelRegistry(models_dir=temp_dir, db_session=db_session)
        clf = make_sklearn_classifier()
        model = make_model(name="binary_test", version="1.0.0", model_binary=clf)
        registry.save(model)
        loaded = registry.get("binary_test", version="1.0.0")
        assert loaded.model_binary is not None


class TestModelList:
    def test_list_versions(self, db_session, temp_dir):
        registry = ModelRegistry(models_dir=temp_dir, db_session=db_session)
        m1 = make_model(name="list_test", version="1.0.0")
        m2 = make_model(name="list_test", version="2.0.0")
        registry.save(m1)
        registry.save(m2)
        versions = registry.list_versions("list_test")
        assert len(versions) == 2

    def test_list_all(self, db_session, temp_dir):
        registry = ModelRegistry(models_dir=temp_dir, db_session=db_session)
        registry.save(make_model(name="alpha", version="1.0.0"))
        registry.save(make_model(name="beta", version="1.0.0"))
        all_models = registry.list_all()
        names = [m["name"] for m in all_models]
        assert "alpha" in names
        assert "beta" in names

    def test_list_empty_registry(self, db_session, temp_dir):
        registry = ModelRegistry(models_dir=temp_dir, db_session=db_session)
        assert registry.list_all() == []


class TestModelPromote:
    def test_promote_changes_stage(self, db_session, temp_dir):
        registry = ModelRegistry(models_dir=temp_dir, db_session=db_session)
        model = make_model(name="promote_me", version="1.0.0", stage="dev")
        registry.save(model)
        result = registry.promote("promote_me", "1.0.0", "production")
        assert result is True
        loaded = registry.get("promote_me", stage="production")
        assert loaded.stage == "production"

    def test_promote_invalid_stage_raises(self, db_session, temp_dir):
        registry = ModelRegistry(models_dir=temp_dir, db_session=db_session)
        model = make_model(name="bad_stage", version="1.0.0")
        registry.save(model)
        with pytest.raises(ValueError):
            registry.promote("bad_stage", "1.0.0", "invalid_stage")

    def test_promote_nonexistent_raises(self, db_session, temp_dir):
        registry = ModelRegistry(models_dir=temp_dir, db_session=db_session)
        with pytest.raises(ModelNotFoundError):
            registry.promote("ghost", "9.9.9", "production")


class TestModelDelete:
    def test_delete_soft_deletes(self, db_session, temp_dir):
        registry = ModelRegistry(models_dir=temp_dir, db_session=db_session)
        model = make_model(name="to_delete", version="1.0.0")
        registry.save(model)
        result = registry.delete("to_delete", "1.0.0")
        assert result is True
        with pytest.raises(ModelNotFoundError):
            registry.get("to_delete", version="1.0.0")

    def test_delete_nonexistent_returns_false(self, db_session, temp_dir):
        registry = ModelRegistry(models_dir=temp_dir, db_session=db_session)
        result = registry.delete("ghost", "0.0.0")
        assert result is False


class TestModelCompare:
    def test_compare_versions(self, db_session, temp_dir):
        registry = ModelRegistry(models_dir=temp_dir, db_session=db_session)
        m1 = make_model(
            name="compare_me",
            version="1.0.0",
            metrics={"accuracy": 0.80, "f1": 0.78},
        )
        m2 = make_model(
            name="compare_me",
            version="2.0.0",
            metrics={"accuracy": 0.90, "f1": 0.88},
        )
        registry.save(m1)
        registry.save(m2)
        comparison = registry.compare_versions("compare_me", "1.0.0", "2.0.0")
        assert "diff" in comparison
        assert "accuracy" in comparison["diff"]
        delta = comparison["diff"]["accuracy"]["delta"]
        assert abs(delta - 0.10) < 1e-6
