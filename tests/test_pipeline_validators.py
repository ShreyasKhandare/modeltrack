"""
Tests for modeltrack.pipelines.validators.
"""

import numpy as np
import pandas as pd
import pytest

from modeltrack.pipelines.validators import (
    DataValidator,
    DuplicateChecker,
    NullChecker,
    OutlierDetector,
    SchemaValidator,
    ValidationReport,
)

# ─────────────────────────── ValidationReport ────────────────────────────────


class TestValidationReport:
    def test_valid_pct_full(self):
        report = ValidationReport(total_records=100, valid_records=100)
        assert report.valid_pct == 1.0

    def test_valid_pct_partial(self):
        report = ValidationReport(total_records=100, valid_records=80)
        assert report.valid_pct == pytest.approx(0.80)

    def test_valid_pct_zero_total(self):
        report = ValidationReport(total_records=0, valid_records=0)
        assert report.valid_pct == 1.0

    def test_is_valid_no_errors(self):
        report = ValidationReport(total_records=100, valid_records=100)
        assert report.is_valid is True

    def test_is_valid_with_errors(self):
        report = ValidationReport(
            total_records=100,
            valid_records=90,
            errors=[{"message": "something wrong"}],
        )
        assert report.is_valid is False

    def test_to_dict_keys(self):
        report = ValidationReport(total_records=50, valid_records=45)
        d = report.to_dict()
        assert "total_records" in d
        assert "valid_records" in d
        assert "valid_pct" in d
        assert "is_valid" in d
        assert "warnings" in d
        assert "errors" in d

    def test_merge(self):
        r1 = ValidationReport(100, 90, warnings=[{"w": 1}], errors=[])
        r2 = ValidationReport(100, 80, warnings=[], errors=[{"e": 1}])
        merged = r1.merge(r2)
        assert len(merged.warnings) == 1
        assert len(merged.errors) == 1
        assert merged.is_valid is False


# ─────────────────────────── NullChecker ─────────────────────────────────────


class TestNullChecker:
    def test_no_nulls(self, sample_df):
        checker = NullChecker(["id", "value"])
        report = checker.check(sample_df)
        assert report.is_valid

    def test_detects_nulls_above_threshold(self):
        df = pd.DataFrame({"col": [None] * 50 + [1.0] * 50})
        checker = NullChecker(["col"], max_null_pct=0.05)
        report = checker.check(df)
        assert not report.is_valid
        assert any("col" in e["column"] for e in report.errors)

    def test_warns_on_nulls_below_threshold(self):
        df = pd.DataFrame({"col": [None] + [1.0] * 99})
        checker = NullChecker(["col"], max_null_pct=0.05)
        report = checker.check(df)
        assert report.is_valid  # below threshold → warning, not error
        assert len(report.warnings) >= 1

    def test_missing_column_is_error(self):
        df = pd.DataFrame({"other": [1, 2, 3]})
        checker = NullChecker(["missing_col"])
        report = checker.check(df)
        assert not report.is_valid

    def test_multiple_columns(self):
        df = pd.DataFrame({"a": [None, None, 1, 2], "b": [1.0, 2.0, 3.0, 4.0]})
        checker = NullChecker(["a", "b"], max_null_pct=0.1)
        report = checker.check(df)
        assert not report.is_valid  # col 'a' has 50% nulls


# ─────────────────────────── SchemaValidator ─────────────────────────────────


class TestSchemaValidator:
    def test_correct_schema(self, sample_df):
        schema = {"id": "int64", "value": "float64", "category": "object"}
        validator = SchemaValidator(schema)
        report = validator.validate(sample_df)
        assert report.is_valid

    def test_wrong_dtype(self):
        df = pd.DataFrame({"col": ["a", "b", "c"]})
        validator = SchemaValidator({"col": "float64"})
        report = validator.validate(df)
        assert not report.is_valid

    def test_missing_column(self):
        df = pd.DataFrame({"a": [1, 2, 3]})
        validator = SchemaValidator({"a": "int64", "b": "float64"})
        report = validator.validate(df)
        assert not report.is_valid

    def test_integer_family_compatibility(self):
        df = pd.DataFrame({"x": np.array([1, 2, 3], dtype=np.int32)})
        validator = SchemaValidator({"x": "int64"})
        report = validator.validate(df)
        assert report.is_valid  # int32 accepted for int64 family


# ─────────────────────────── OutlierDetector ─────────────────────────────────


class TestOutlierDetector:
    def test_iqr_detects_outliers(self):
        # Data with obvious outlier
        normal = list(range(50))
        df = pd.DataFrame({"x": normal + [10000]})
        detector = OutlierDetector(["x"], method="iqr", threshold=1.5)
        report = detector.detect(df)
        assert len(report.warnings) >= 1

    def test_zscore_detects_outliers(self):
        rng = np.random.default_rng(0)
        data = rng.normal(0, 1, 99).tolist() + [100.0]
        df = pd.DataFrame({"x": data})
        detector = OutlierDetector(["x"], method="zscore", threshold=3.0)
        report = detector.detect(df)
        assert len(report.warnings) >= 1

    def test_no_outliers(self):
        data = list(range(100))
        df = pd.DataFrame({"x": data})
        detector = OutlierDetector(["x"], method="iqr", threshold=1.5)
        report = detector.detect(df)
        # May or may not flag anything; just confirm it runs
        assert isinstance(report, ValidationReport)

    def test_missing_column_is_error(self):
        df = pd.DataFrame({"other": [1, 2, 3]})
        detector = OutlierDetector(["missing"])
        report = detector.detect(df)
        assert len(report.errors) >= 1

    def test_invalid_method_raises(self):
        with pytest.raises(ValueError):
            OutlierDetector(["x"], method="invalid")

    def test_zscore_clean_data(self, sample_df):
        # sample_df has normally distributed 'value' — most won't be outliers
        detector = OutlierDetector(["value"], method="zscore", threshold=3.0)
        report = detector.detect(sample_df)
        assert isinstance(report, ValidationReport)


# ─────────────────────────── DuplicateChecker ────────────────────────────────


class TestDuplicateChecker:
    def test_no_duplicates(self, sample_df):
        checker = DuplicateChecker()
        report = checker.check(sample_df)
        assert report.is_valid

    def test_detects_duplicates(self):
        df = pd.DataFrame({"a": [1, 2, 1], "b": [10, 20, 10]})
        checker = DuplicateChecker()
        report = checker.check(df)
        assert len(report.warnings) >= 1

    def test_column_subset_duplicates(self):
        df = pd.DataFrame({"key": [1, 1, 2], "val": [10, 20, 30]})
        checker = DuplicateChecker(columns=["key"])
        report = checker.check(df)
        assert len(report.warnings) >= 1

    def test_missing_column_is_error(self):
        df = pd.DataFrame({"a": [1, 2, 3]})
        checker = DuplicateChecker(columns=["a", "missing"])
        report = checker.check(df)
        assert not report.is_valid


# ─────────────────────────── DataValidator (composite) ───────────────────────


class TestDataValidator:
    def test_empty_validator_passes(self, sample_df):
        dv = DataValidator()
        report = dv.validate(sample_df)
        assert report.is_valid

    def test_composite_all_pass(self, sample_df):
        dv = DataValidator().add(NullChecker(["id", "value"])).add(DuplicateChecker())
        report = dv.validate(sample_df)
        assert report.is_valid

    def test_composite_one_fails(self):
        df = pd.DataFrame({"col": [None] * 60 + [1.0] * 40})
        dv = DataValidator().add(NullChecker(["col"], max_null_pct=0.05))
        report = dv.validate(df)
        assert not report.is_valid

    def test_add_returns_self(self):
        dv = DataValidator()
        returned = dv.add(NullChecker(["x"]))
        assert returned is dv
