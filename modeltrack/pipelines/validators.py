"""
Data validation utilities for ModelTrack pipelines.
"""

from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

from modeltrack.shared.logger import get_logger

logger = get_logger(__name__)


# ─────────────────────────── ValidationReport ────────────────────────────────


class ValidationReport:
    """Aggregated result of one or more validation checks."""

    def __init__(
        self,
        total_records: int,
        valid_records: int,
        warnings: Optional[List[dict]] = None,
        errors: Optional[List[dict]] = None,
    ):
        self.total_records = total_records
        self.valid_records = valid_records
        self.warnings: List[dict] = warnings or []
        self.errors: List[dict] = errors or []

    @property
    def valid_pct(self) -> float:
        """Fraction of records that passed validation (0.0–1.0)."""
        if self.total_records == 0:
            return 1.0
        return self.valid_records / self.total_records

    @property
    def is_valid(self) -> bool:
        """True when there are no *errors* (warnings are acceptable)."""
        return len(self.errors) == 0

    def merge(self, other: "ValidationReport") -> "ValidationReport":
        """Return a new report combining self and *other*."""
        return ValidationReport(
            total_records=max(self.total_records, other.total_records),
            valid_records=min(self.valid_records, other.valid_records),
            warnings=self.warnings + other.warnings,
            errors=self.errors + other.errors,
        )

    def to_dict(self) -> dict:
        return {
            "total_records": self.total_records,
            "valid_records": self.valid_records,
            "valid_pct": round(self.valid_pct, 4),
            "is_valid": self.is_valid,
            "warning_count": len(self.warnings),
            "error_count": len(self.errors),
            "warnings": self.warnings,
            "errors": self.errors,
        }

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<ValidationReport total={self.total_records} "
            f"valid={self.valid_records} "
            f"errors={len(self.errors)} warnings={len(self.warnings)}>"
        )


# ─────────────────────────── NullChecker ─────────────────────────────────────


class NullChecker:
    """Check that specified columns do not exceed a null threshold."""

    def __init__(self, columns: List[str], max_null_pct: float = 0.05):
        self.columns = columns
        self.max_null_pct = max_null_pct

    def check(self, df: pd.DataFrame) -> ValidationReport:
        n = len(df)
        errors: List[dict] = []
        warnings: List[dict] = []

        for col in self.columns:
            if col not in df.columns:
                errors.append(
                    {
                        "check": "null_check",
                        "column": col,
                        "message": f"Column '{col}' not found in DataFrame",
                    }
                )
                continue

            null_count = int(df[col].isna().sum())
            null_pct = null_count / n if n > 0 else 0.0

            if null_pct > self.max_null_pct:
                errors.append(
                    {
                        "check": "null_check",
                        "column": col,
                        "null_count": null_count,
                        "null_pct": round(null_pct, 4),
                        "threshold": self.max_null_pct,
                        "message": (
                            f"Column '{col}' has {null_pct:.1%} nulls "
                            f"(threshold {self.max_null_pct:.1%})"
                        ),
                    }
                )
            elif null_count > 0:
                warnings.append(
                    {
                        "check": "null_check",
                        "column": col,
                        "null_count": null_count,
                        "null_pct": round(null_pct, 4),
                        "message": f"Column '{col}' has {null_count} null(s)",
                    }
                )

        valid_records = n - sum(e.get("null_count", 0) for e in errors)
        valid_records = max(0, valid_records)

        return ValidationReport(
            total_records=n,
            valid_records=valid_records,
            warnings=warnings,
            errors=errors,
        )


# ─────────────────────────── SchemaValidator ─────────────────────────────────

_DTYPE_MAP: Dict[str, Any] = {
    "int": "int64",
    "int8": "int8",
    "int16": "int16",
    "int32": "int32",
    "int64": "int64",
    "float": "float64",
    "float32": "float32",
    "float64": "float64",
    "str": "object",
    "object": "object",
    "string": "object",
    "bool": "bool",
    "boolean": "bool",
    "datetime": "datetime64[ns]",
    "datetime64": "datetime64[ns]",
    "category": "category",
}


class SchemaValidator:
    """Validate that DataFrame columns match expected dtypes."""

    def __init__(self, schema: Dict[str, str]):
        """
        Parameters
        ----------
        schema:
            Mapping of ``{column_name: dtype_string}``.
            Supported dtype strings: int, int64, float, float64, str, object,
            bool, datetime, category, etc.
        """
        self.schema = schema

    def validate(self, df: pd.DataFrame) -> ValidationReport:
        n = len(df)
        errors: List[dict] = []
        warnings: List[dict] = []

        for col, expected_dtype_str in self.schema.items():
            if col not in df.columns:
                errors.append(
                    {
                        "check": "schema_validate",
                        "column": col,
                        "message": f"Expected column '{col}' is missing",
                    }
                )
                continue

            actual_dtype = str(df[col].dtype)
            expected_canonical = _DTYPE_MAP.get(
                expected_dtype_str.lower(), expected_dtype_str
            )

            # Allow loose numeric compatibility
            ok = self._dtypes_compatible(actual_dtype, expected_canonical)
            if not ok:
                errors.append(
                    {
                        "check": "schema_validate",
                        "column": col,
                        "expected": expected_canonical,
                        "actual": actual_dtype,
                        "message": (
                            f"Column '{col}' has dtype '{actual_dtype}', "
                            f"expected '{expected_canonical}'"
                        ),
                    }
                )

        return ValidationReport(
            total_records=n,
            valid_records=n if not errors else 0,
            warnings=warnings,
            errors=errors,
        )

    @staticmethod
    def _dtypes_compatible(actual: str, expected: str) -> bool:
        """Return True if *actual* dtype satisfies *expected*."""
        if actual == expected:
            return True
        # Numeric families
        int_types = {
            "int8",
            "int16",
            "int32",
            "int64",
            "uint8",
            "uint16",
            "uint32",
            "uint64",
        }
        float_types = {"float16", "float32", "float64"}
        if expected in int_types and actual in int_types:
            return True
        if expected in float_types and actual in float_types:
            return True
        if expected == "float64" and actual in int_types:
            return True
        # String / object
        if expected == "object" and actual in ("object", "string", "StringDtype"):
            return True
        # Datetime
        if expected.startswith("datetime64") and actual.startswith("datetime64"):
            return True
        return False


# ─────────────────────────── OutlierDetector ─────────────────────────────────


class OutlierDetector:
    """Detect outliers in numeric columns using IQR or Z-score method."""

    def __init__(
        self,
        columns: List[str],
        method: str = "iqr",
        threshold: float = 3.0,
    ):
        """
        Parameters
        ----------
        columns:
            Numeric columns to inspect.
        method:
            ``"iqr"`` or ``"zscore"``.
        threshold:
            For IQR: multiplier (default 1.5).
            For Z-score: number of standard deviations (default 3.0).
        """
        if method not in ("iqr", "zscore"):
            raise ValueError(f"method must be 'iqr' or 'zscore', got {method!r}")
        self.columns = columns
        self.method = method
        self.threshold = threshold

    def detect(self, df: pd.DataFrame) -> ValidationReport:
        n = len(df)
        warnings: List[dict] = []
        errors: List[dict] = []
        total_outliers = 0

        for col in self.columns:
            if col not in df.columns:
                errors.append(
                    {
                        "check": "outlier_detect",
                        "column": col,
                        "message": f"Column '{col}' not found",
                    }
                )
                continue

            series = df[col].dropna()
            if len(series) == 0:
                continue

            if self.method == "iqr":
                # Use 1.5 * IQR by default (threshold overrides multiplier)
                multiplier = self.threshold if self.threshold != 3.0 else 1.5
                q1 = series.quantile(0.25)
                q3 = series.quantile(0.75)
                iqr = q3 - q1
                lower = q1 - multiplier * iqr
                upper = q3 + multiplier * iqr
                mask = (df[col] < lower) | (df[col] > upper)
            else:  # zscore
                mean = series.mean()
                std = series.std()
                if std == 0:
                    continue
                z_scores = (df[col] - mean).abs() / std
                mask = z_scores > self.threshold

            outlier_count = int(mask.sum())
            total_outliers += outlier_count

            if outlier_count > 0:
                warnings.append(
                    {
                        "check": "outlier_detect",
                        "column": col,
                        "method": self.method,
                        "outlier_count": outlier_count,
                        "outlier_pct": round(outlier_count / n, 4),
                        "message": (
                            f"Column '{col}' has {outlier_count} outlier(s) "
                            f"({self.method} method)"
                        ),
                    }
                )

        valid_records = max(0, n - total_outliers)
        return ValidationReport(
            total_records=n,
            valid_records=valid_records,
            warnings=warnings,
            errors=errors,
        )


# ─────────────────────────── DuplicateChecker ────────────────────────────────


class DuplicateChecker:
    """Detect duplicate rows, optionally scoped to a subset of columns."""

    def __init__(self, columns: Optional[List[str]] = None):
        """
        Parameters
        ----------
        columns:
            Columns to check. If ``None``, all columns are used.
        """
        self.columns = columns

    def check(self, df: pd.DataFrame) -> ValidationReport:
        n = len(df)
        subset = self.columns if self.columns else None

        # Validate columns exist
        errors: List[dict] = []
        if subset:
            missing = [c for c in subset if c not in df.columns]
            if missing:
                for col in missing:
                    errors.append(
                        {
                            "check": "duplicate_check",
                            "column": col,
                            "message": f"Column '{col}' not found in DataFrame",
                        }
                    )
                return ValidationReport(
                    total_records=n,
                    valid_records=n,
                    warnings=[],
                    errors=errors,
                )

        dup_mask = df.duplicated(subset=subset, keep="first")
        dup_count = int(dup_mask.sum())
        warnings: List[dict] = []

        if dup_count > 0:
            warnings.append(
                {
                    "check": "duplicate_check",
                    "duplicate_count": dup_count,
                    "duplicate_pct": round(dup_count / n, 4),
                    "columns": subset or "all",
                    "message": f"Found {dup_count} duplicate row(s)",
                }
            )

        return ValidationReport(
            total_records=n,
            valid_records=n - dup_count,
            warnings=warnings,
            errors=errors,
        )


# ─────────────────────────── DataValidator (composite) ───────────────────────


class DataValidator:
    """
    Composite validator that aggregates multiple individual validators.

    Usage::

        dv = (
            DataValidator()
            .add(NullChecker(["col_a", "col_b"]))
            .add(SchemaValidator({"col_a": "int64"}))
            .add(OutlierDetector(["col_a"]))
        )
        report = dv.validate(df)
    """

    def __init__(self):
        self._validators: List[Any] = []

    def add(self, validator: Any) -> "DataValidator":
        """Add a validator and return *self* for fluent chaining."""
        self._validators.append(validator)
        return self

    def validate(self, df: pd.DataFrame) -> ValidationReport:
        """Run all validators and return a merged :class:`ValidationReport`."""
        if not self._validators:
            return ValidationReport(total_records=len(df), valid_records=len(df))

        reports: List[ValidationReport] = []
        for v in self._validators:
            if hasattr(v, "check"):
                report = v.check(df)
            elif hasattr(v, "validate"):
                report = v.validate(df)
            elif hasattr(v, "detect"):
                report = v.detect(df)
            else:
                logger.warning(
                    "Validator has no check/validate/detect method",
                    extra={"validator": str(v)},
                )
                continue
            reports.append(report)

        combined = reports[0]
        for r in reports[1:]:
            combined = combined.merge(r)
        return combined
