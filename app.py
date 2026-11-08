"""
Streamlit Sales Analytics Dashboard
------------------------------------
Upload CSV / Excel / JSON sales data, validate & clean it, then explore
KPIs and interactive charts with live filters.

Run locally:
    streamlit run app.py
"""

import pandas as pd
import plotly.express as px
import streamlit as st

import data_utils as du

st.set_page_config(
    page_title="Sales Analytics Dashboard",
    page_icon="📊",
    layout="wide",
)


# --------------------------------------------------------------------------
# Helpers (UI-layer, call into data_utils for the actual logic)
# --------------------------------------------------------------------------
@st.cache_data(show_spinner=False)
def _load_cached(file_bytes: bytes, file_name: str) -> pd.DataFrame:
    """Cache wrapper around du.load_data so re-filtering doesn't re-parse the file."""
    import io

    class _Wrapped:
        def __init__(self, data, name):
            self._data = data
            self.name = name

        def read(self):
            return self._data

    return du.load_data(_Wrapped(file_bytes, file_name))


def render_validation_panel(df: pd.DataFrame) -> None:
    profile = du.validate_data(df)

    st.subheader("1 · Data Validation")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Rows", profile["n_rows"])
    c2.metric("Columns", profile["n_cols"])
    c3.metric("Missing cells", profile["total_missing_cells"])
    c4.metric("Duplicate rows", profile["duplicate_rows"])

    with st.expander("Column names & data types"):
        dtype_df = pd.DataFrame(
            {
                "Column": profile["columns"],
                "Data Type": [profile["dtypes"][c] for c in profile["columns"]],
                "Missing (#)": [profile["missing_counts"][c] for c in profile["columns"]],
                "Missing (%)": [profile["missing_pct"][c] for c in profile["columns"]],
            }
        )
        st.dataframe(dtype_df, width='stretch', hide_index=True)

    with st.expander("Raw data preview (first 20 rows)"):
        st.dataframe(df.head(20), width='stretch')


def render_cleaning_panel(df: pd.DataFrame) -> pd.DataFrame:
    st.subheader("2 · Preprocessing & Cleaning")

    col1, col2, col3 = st.columns(3)
    numeric_fill = col1.selectbox(
        "Fill missing numeric values with", ["median", "mean", "zero", "drop"], index=0
    )
    categorical_fill = col2.selectbox(
        "Fill missing text values with", ["mode", "unknown", "drop"], index=0
    )
    drop_duplicates = col3.checkbox("Remove duplicate rows", value=True)
    cap_outliers = st.checkbox(
        "Cap extreme outliers in Sales / Profit / Quantity (IQR method)", value=True
    )

    try:
        clean_df, report = du.clean_data(
            df,
            numeric_fill=numeric_fill,
            categorical_fill=categorical_fill,
            drop_duplicates=drop_duplicates,
            cap_outliers=cap_outliers,
        )
    except Exception as exc:
        st.error(f"Cleaning failed: {exc}")
        st.stop()

    with st.expander(f"Cleaning log ({len(report['steps'])} steps) · final shape {report['final_shape']}"):
        for step in report["steps"]:
            st.write("•", step)

    with st.expander("Statistical summary (numeric columns)"):
        st.dataframe(du.numeric_summary(clean_df), width='stretch')

    cat_options = [c for c in ["Region", "Category", "Segment", "Sub-Category"] if c in clean_df.columns]
    if cat_options:
        with st.expander("Categorical summary"):
            chosen = st.selectbox("Column", cat_options, key="cat_summary_col")
            st.dataframe(du.categorical_summary(clean_df, chosen), width='stretch')

    return clean_df


def render_filters(df: pd.DataFrame) -> pd.DataFrame:
    st.subheader("3 · Interactive Filters")
    f1, f2, f3, f4 = st.columns(4)

    regions = sorted(df["Region"].dropna().unique()) if "Region" in df.columns else []
    categories = sorted(df["Category"].dropna().unique()) if "Category" in df.columns else []
    segments = sorted(df["Segment"].dropna().unique()) if "Segment" in df.columns else []

    sel_regions = f1.multiselect("Region", regions, default=regions)
    sel_categories = f2.multiselect("Category", categories, default=categories)
    sel_segments = f3.multiselect("Segment", segments, default=segments)

    date_range = None
    if "Order Date" in df.columns and df["Order Date"].notna().any():
        min_d, max_d = df["Order Date"].min(), df["Order Date"].max()
        date_range = f4.date_input(
            "Order Date range",
            value=(min_d.date(), max_d.date()),
            min_value=min_d.date(),
            max_value=max_d.date(),
        )
        if isinstance(date_range, tuple) and len(date_range) != 2:
            date_range = None  # user is mid-selection; skip filtering until both picked

    try:
        filtered = du.filter_data(
            df,
            regions=sel_regions or None,
            categories=sel_categories or None,
            segments=sel_segments or None,
            date_range=date_range,
        )
    except Exception as exc:
        st.error(f"Filtering failed: {exc}")
        filtered = df

    if filtered.empty:
        st.warning("No records match the current filters. Showing unfiltered data instead.")
        return df

    return filtered


def render_kpis(df: pd.DataFrame) -> None:
    st.subheader("4 · Key Performance Indicators")
    kpis = du.compute_kpis(df)

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Total Sales", f"${kpis['Total Sales']:,.2f}")
    c2.metric("Total Profit", f"${kpis['Total Profit']:,.2f}")
    c3.metric("Total Orders", f"{kpis['Total Orders']:,}")
    c4.metric("Total Quantity Sold", f"{kpis['Total Quantity Sold']:,.0f}")
    c5.metric("Profit Margin", f"{kpis['Profit Margin (%)']:.2f}%")


def render_charts(df: pd.DataFrame) -> None:
    st.subheader("5 · Visualizations")

    if df.empty:
        st.info("No data available to chart.")
        return

    tab1, tab2, tab3, tab4 = st.tabs(
        ["Sales Trend", "Category Breakdown", "Region Performance", "Sales vs Profit"]
    )

    with tab1:
        try:
            if "Order Date" in df.columns and df["Order Date"].notna().any():
                trend = (
                    df.dropna(subset=["Order Date"])
                    .set_index("Order Date")
                    .resample("W")["Sales"]
                    .sum()
                    .reset_index()
                )
                fig = px.line(trend, x="Order Date", y="Sales", markers=True, title="Weekly Sales Trend")
                st.plotly_chart(fig, width='stretch')
            else:
                st.info("No valid 'Order Date' column available for a trend chart.")
        except Exception as exc:
            st.error(f"Could not render sales trend chart: {exc}")

    with tab2:
        try:
            if "Category" in df.columns and "Sales" in df.columns:
                by_cat = df.groupby("Category", as_index=False)["Sales"].sum().sort_values("Sales")
                fig = px.bar(
                    by_cat, x="Sales", y="Category", orientation="h", title="Total Sales by Category"
                )
                st.plotly_chart(fig, width='stretch')
            else:
                st.info("Need 'Category' and 'Sales' columns for this chart.")
        except Exception as exc:
            st.error(f"Could not render category chart: {exc}")

    with tab3:
        try:
            if "Region" in df.columns and "Profit" in df.columns:
                by_region = df.groupby("Region", as_index=False)["Profit"].sum()
                fig = px.pie(by_region, names="Region", values="Profit", title="Profit Share by Region")
                st.plotly_chart(fig, width='stretch')
            else:
                st.info("Need 'Region' and 'Profit' columns for this chart.")
        except Exception as exc:
            st.error(f"Could not render region chart: {exc}")

    with tab4:
        try:
            if {"Sales", "Profit"}.issubset(df.columns):
                color_col = "Category" if "Category" in df.columns else None
                fig = px.scatter(
                    df,
                    x="Sales",
                    y="Profit",
                    color=color_col,
                    hover_data=["Order ID"] if "Order ID" in df.columns else None,
                    title="Sales vs. Profit by Order",
                )
                st.plotly_chart(fig, width='stretch')
            else:
                st.info("Need 'Sales' and 'Profit' columns for this chart.")
        except Exception as exc:
            st.error(f"Could not render scatter chart: {exc}")


# --------------------------------------------------------------------------
# Main app
# --------------------------------------------------------------------------
def main() -> None:
    st.title("📊 Sales Analytics Dashboard")
    st.caption(
        "Upload a CSV, Excel, or JSON sales file to validate, clean, filter, "
        "and explore KPIs and interactive charts."
    )

    uploaded_file = st.file_uploader(
        "Upload data file", type=["csv", "xlsx", "xls", "json"], accept_multiple_files=False
    )

    if uploaded_file is None:
        st.info("👆 Upload a file to get started, or try the bundled sample dataset below.")
        if st.button("Load sample dataset"):
            st.session_state["use_sample"] = True

        if not st.session_state.get("use_sample"):
            st.stop()

        try:
            df = pd.read_csv("sample_data/sample_sales_data.csv")
        except Exception as exc:
            st.error(f"Could not load sample dataset: {exc}")
            st.stop()
    else:
        try:
            file_bytes = uploaded_file.getvalue()
            df = _load_cached(file_bytes, uploaded_file.name)
        except ValueError as exc:
            st.error(str(exc))
            st.stop()
        except Exception as exc:
            st.error(f"Unexpected error while reading the file: {exc}")
            st.stop()

    render_validation_panel(df)
    clean_df = render_cleaning_panel(df)
    filtered_df = render_filters(clean_df)
    render_kpis(filtered_df)
    render_charts(filtered_df)

    st.divider()
    with st.expander("Download cleaned & filtered data"):
        st.download_button(
            "Download as CSV",
            data=filtered_df.to_csv(index=False).encode("utf-8"),
            file_name="cleaned_filtered_sales_data.csv",
            mime="text/csv",
        )


if __name__ == "__main__":
    main()
