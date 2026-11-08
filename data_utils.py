"""
data_utils.py
Reusable, Streamlit-independent functions for loading, validating,
cleaning, summarizing, and filtering the sales dataset.
Kept separate from app.py so the logic can be unit tested without
spinning up a Streamlit server.
"""

from __future__ import annotations
import io
import json
from typing import Optional

import numpy as np
import pandas as pd

# Columns we try to coerce to numeric if present
NUMERIC_CANDIDATES = ["Sales", "Profit", "Quantity", "Discount"]
DATE_CANDIDATES = ["Order Date", "Ship Date"]
# Free-text category columns that often have inconsistent casing (west/West/WEST)
CATEGORICAL_NORMALIZE = ["Region", "Segment", "Category", "Sub-Category", "Ship Mode", "Country", "State", "City"]


# --------------------------------------------------------------------------
# 1. LOADING
# --------------------------------------------------------------------------
def load_data(uploaded_file) -> pd.DataFrame:
    """
    Load a CSV, XLSX, or JSON file (a Streamlit UploadedFile or any
    file-like/path object) into a DataFrame. Raises ValueError with a
    human-readable message on failure.
    """
    if uploaded_file is None:
        raise ValueError("No file provided.")

    name = getattr(uploaded_file, "name", str(uploaded_file))
    ext = name.lower().rsplit(".", 1)[-1] if "." in name else ""

    try:
        if ext == "csv":
            # Sniff common delimiters (comma, tab, semicolon)
            raw = uploaded_file.read()
            if isinstance(raw, bytes):
                raw = raw.decode("utf-8", errors="replace")
            sample = raw[:5000]
            sep = "\t" if sample.count("\t") > sample.count(",") else ","
            df = pd.read_csv(io.StringIO(raw), sep=sep)
        elif ext in ("xlsx", "xls"):
            raw = uploaded_file.read()
            df = pd.read_excel(io.BytesIO(raw))
        elif ext == "json":
            raw = uploaded_file.read()
            if isinstance(raw, bytes):
                raw = raw.decode("utf-8", errors="replace")
            parsed = json.loads(raw)
            # Accept either a list of records or {"data": [...]}
            if isinstance(parsed, dict) and "data" in parsed:
                parsed = parsed["data"]
            df = pd.json_normalize(parsed)
        else:
            raise ValueError(
                f"Unsupported file type '.{ext}'. Please upload a .csv, .xlsx, or .json file."
            )
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError(f"Could not read '{name}': {exc}") from exc

    if df.empty:
        raise ValueError(f"'{name}' was read successfully but contains no rows.")

    df.columns = [str(c).strip() for c in df.columns]
    return df


# --------------------------------------------------------------------------
# 2. VALIDATION / PROFILING
# --------------------------------------------------------------------------
def validate_data(df: pd.DataFrame) -> dict:
    """
    Return a profile dict describing dimensions, column dtypes,
    missing values, and duplicate record counts.
    """
    missing = df.isnull().sum()
    missing_pct = (missing / len(df) * 100).round(2)

    profile = {
        "n_rows": int(df.shape[0]),
        "n_cols": int(df.shape[1]),
        "columns": list(df.columns),
        "dtypes": {c: str(t) for c, t in df.dtypes.items()},
        "missing_counts": missing.to_dict(),
        "missing_pct": missing_pct.to_dict(),
        "total_missing_cells": int(missing.sum()),
        "duplicate_rows": int(df.duplicated().sum()),
    }
    return profile


# --------------------------------------------------------------------------
# 3. CLEANING / PREPROCESSING
# --------------------------------------------------------------------------
def clean_data(
    df: pd.DataFrame,
    numeric_fill: str = "median",       # "median" | "mean" | "zero" | "drop"
    categorical_fill: str = "mode",     # "mode" | "unknown" | "drop"
    drop_duplicates: bool = True,
    parse_dates: bool = True,
    cap_outliers: bool = True,
) -> tuple[pd.DataFrame, dict]:
    """
    Clean the dataframe: fix dtypes, parse dates, handle missing values,
    drop duplicates, strip whitespace/inconsistent casing in text columns.
    Returns (clean_df, report) where report logs what was done.
    """
    df = df.copy()
    report = {"steps": []}

    # --- Standardize text columns (strip whitespace, consistent case for IDs) ---
    text_cols = df.select_dtypes(include="object").columns
    for col in text_cols:
        df[col] = df[col].astype(str).str.strip()
        df[col] = df[col].replace({"nan": np.nan, "None": np.nan, "": np.nan})
    report["steps"].append(f"Trimmed whitespace / normalized blanks in {len(text_cols)} text column(s).")

    # --- Normalize inconsistent casing in key categorical columns (e.g. "west" / "WEST" / "West") ---
    normalized_cols = []
    for col in CATEGORICAL_NORMALIZE:
        if col in df.columns:
            before_unique = df[col].nunique(dropna=True)
            df[col] = df[col].apply(lambda v: v.title() if isinstance(v, str) else v)
            after_unique = df[col].nunique(dropna=True)
            if after_unique < before_unique:
                normalized_cols.append(col)
    if normalized_cols:
        report["steps"].append(
            f"Standardized text casing (e.g. 'west' -> 'West') in: {', '.join(normalized_cols)}."
        )

    # --- Coerce numeric-looking columns ---
    for col in NUMERIC_CANDIDATES:
        if col in df.columns:
            before_na = df[col].isnull().sum()
            df[col] = pd.to_numeric(
                df[col].astype(str).str.replace(r"[^0-9.\-]", "", regex=True),
                errors="coerce",
            )
            after_na = df[col].isnull().sum()
            if after_na > before_na:
                report["steps"].append(
                    f"Column '{col}': {after_na - before_na} value(s) could not be parsed as numeric and were set to NaN."
                )

    # --- Parse dates ---
    if parse_dates:
        for col in DATE_CANDIDATES:
            if col in df.columns:
                parsed = pd.to_datetime(df[col], errors="coerce", format="mixed")
                n_bad = parsed.isnull().sum() - df[col].isnull().sum()
                df[col] = parsed
                if n_bad > 0:
                    report["steps"].append(
                        f"Column '{col}': {n_bad} value(s) had inconsistent/unparseable date formats and were set to NaN."
                    )
        report["steps"].append("Parsed date columns to a consistent datetime format.")

    # --- Duplicates ---
    n_dupes = int(df.duplicated().sum())
    if drop_duplicates and n_dupes > 0:
        df = df.drop_duplicates().reset_index(drop=True)
        report["steps"].append(f"Removed {n_dupes} duplicate row(s).")
    elif n_dupes > 0:
        report["steps"].append(f"{n_dupes} duplicate row(s) found but not removed (option disabled).")

    # --- Missing values: numeric ---
    num_cols = [c for c in NUMERIC_CANDIDATES if c in df.columns]
    if numeric_fill == "drop":
        before = len(df)
        df = df.dropna(subset=num_cols)
        report["steps"].append(f"Dropped {before - len(df)} row(s) with missing numeric values.")
    else:
        for col in num_cols:
            n_missing = df[col].isnull().sum()
            if n_missing == 0:
                continue
            if numeric_fill == "median":
                fill_val = df[col].median()
            elif numeric_fill == "mean":
                fill_val = df[col].mean()
            else:  # zero
                fill_val = 0
            df[col] = df[col].fillna(fill_val)
            report["steps"].append(
                f"Filled {n_missing} missing value(s) in '{col}' with {numeric_fill} ({round(fill_val, 2) if isinstance(fill_val, (int, float)) else fill_val})."
            )

    # --- Missing values: categorical/text ---
    cat_cols = [c for c in df.select_dtypes(include="object").columns]
    if categorical_fill == "drop":
        before = len(df)
        df = df.dropna(subset=cat_cols)
        report["steps"].append(f"Dropped {before - len(df)} row(s) with missing categorical values.")
    else:
        for col in cat_cols:
            n_missing = df[col].isnull().sum()
            if n_missing == 0:
                continue
            if categorical_fill == "mode" and not df[col].mode().empty:
                fill_val = df[col].mode().iloc[0]
            else:
                fill_val = "Unknown"
            df[col] = df[col].fillna(fill_val)
            report["steps"].append(f"Filled {n_missing} missing value(s) in '{col}' with '{fill_val}'.")

    # --- Outlier handling (IQR capping on Sales / Profit / Quantity) ---
    if cap_outliers:
        capped_cols = []
        for col in ["Sales", "Profit", "Quantity"]:
            if col not in df.columns:
                continue
            q1, q3 = df[col].quantile(0.25), df[col].quantile(0.75)
            iqr = q3 - q1
            if iqr == 0:
                continue
            lower, upper = q1 - 3 * iqr, q3 + 3 * iqr
            n_outliers = int(((df[col] < lower) | (df[col] > upper)).sum())
            if n_outliers > 0:
                df[col] = df[col].clip(lower=lower, upper=upper)
                capped_cols.append(f"{col} ({n_outliers})")
        if capped_cols:
            report["steps"].append(
                "Capped extreme outlier value(s) using the IQR method in: " + ", ".join(capped_cols) + "."
            )

    report["final_shape"] = df.shape
    return df, report


# --------------------------------------------------------------------------
# 4. STATISTICAL SUMMARIES (reusable)
# --------------------------------------------------------------------------
def numeric_summary(df: pd.DataFrame, columns: Optional[list[str]] = None) -> pd.DataFrame:
    """Return describe()-style stats (count, mean, std, min, quartiles, max) for numeric columns."""
    cols = columns or df.select_dtypes(include=np.number).columns.tolist()
    cols = [c for c in cols if c in df.columns]
    if not cols:
        return pd.DataFrame()
    return df[cols].describe().T.round(2)


def categorical_summary(df: pd.DataFrame, column: str, top_n: int = 10) -> pd.DataFrame:
    """Return value counts + percentage share for a categorical column."""
    if column not in df.columns:
        return pd.DataFrame()
    counts = df[column].value_counts().head(top_n)
    pct = (counts / len(df) * 100).round(2)
    return pd.DataFrame({"Count": counts, "Percent": pct})


# --------------------------------------------------------------------------
# 5. KPI CALCULATIONS
# --------------------------------------------------------------------------
def compute_kpis(df: pd.DataFrame) -> dict:
    """Compute the five required KPIs from a (filtered) dataframe."""
    total_sales = float(df["Sales"].sum()) if "Sales" in df.columns else 0.0
    total_profit = float(df["Profit"].sum()) if "Profit" in df.columns else 0.0
    total_orders = int(df["Order ID"].nunique()) if "Order ID" in df.columns else len(df)
    total_quantity = float(df["Quantity"].sum()) if "Quantity" in df.columns else 0.0
    profit_margin = (total_profit / total_sales * 100) if total_sales else 0.0

    return {
        "Total Sales": total_sales,
        "Total Profit": total_profit,
        "Total Orders": total_orders,
        "Total Quantity Sold": total_quantity,
        "Profit Margin (%)": profit_margin,
    }


# --------------------------------------------------------------------------
# 6. FILTERING
# --------------------------------------------------------------------------
def filter_data(
    df: pd.DataFrame,
    regions: Optional[list[str]] = None,
    categories: Optional[list[str]] = None,
    segments: Optional[list[str]] = None,
    date_range: Optional[tuple] = None,
    date_col: str = "Order Date",
) -> pd.DataFrame:
    """Apply region / category / segment / date-range filters. Any filter left
    as None or empty is skipped (i.e. 'no filter applied')."""
    out = df.copy()

    if regions and "Region" in out.columns:
        out = out[out["Region"].isin(regions)]
    if categories and "Category" in out.columns:
        out = out[out["Category"].isin(categories)]
    if segments and "Segment" in out.columns:
        out = out[out["Segment"].isin(segments)]
    if date_range and date_col in out.columns and len(date_range) == 2:
        start, end = date_range
        if start is not None and end is not None:
            mask = (out[date_col] >= pd.Timestamp(start)) & (out[date_col] <= pd.Timestamp(end))
            out = out[mask]

    return out
