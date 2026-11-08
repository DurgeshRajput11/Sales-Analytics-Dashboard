# 📊 Sales Analytics Dashboard (Streamlit)

An interactive Streamlit app for uploading, validating, cleaning, filtering,
and visualizing sales data.

## Features
- **Upload**: CSV, XLSX, or JSON (auto-detects delimiter for CSV/TSV).
- **Validation**: dimensions, column names/types, missing values, duplicate rows.
- **Cleaning**: configurable missing-value handling, duplicate removal, date
  parsing, text-casing normalization (e.g. `west` → `West`), and IQR-based
  outlier capping — all via reusable functions in `data_utils.py`.
- **Filters**: Region, Category, Segment, and Order Date range.
- **KPIs**: Total Sales, Total Profit, Total Orders (unique), Total Quantity
  Sold, Profit Margin (%).
- **Charts**: weekly sales trend, sales by category, profit share by region,
  sales-vs-profit scatter (Plotly, all interactive).
- Error handling throughout (bad file types, empty files, missing columns,
  chart failures) so the app degrades gracefully instead of crashing.

## Project structure
```
sales_dashboard/
├── app.py              # Streamlit UI (layout, filters, KPIs, charts)
├── data_utils.py        # Reusable, testable data functions (no Streamlit dependency)
├── requirements.txt
├── sample_data/
│   └── sample_sales_data.csv
└── README.md
```

## Run locally
```bash
pip install -r requirements.txt
streamlit run app.py
```
Then open the URL Streamlit prints (usually `http://localhost:8501`).

## Deploy to GitHub + Streamlit Community Cloud

These are the steps *you* run — Claude can't create accounts, push to your
GitHub, or click through Streamlit Cloud's UI on your behalf.

### 1. Push the code to GitHub
```bash
cd sales_dashboard
git init
git add .
git commit -m "Initial commit: Sales Analytics Dashboard"
git branch -M main
git remote add origin https://github.com/<your-username>/<your-repo>.git
git push -u origin main
```
(Create the empty repo on github.com first if you haven't.)

### 2. Deploy on Streamlit Community Cloud
1. Go to **https://share.streamlit.io** and sign in with GitHub.
2. Click **"New app"**.
3. Pick your repository, branch (`main`), and main file path (`app.py`).
4. Click **Deploy**. Streamlit Cloud installs `requirements.txt` automatically.
5. Wait for the build to finish — you'll get a public URL like
   `https://<your-app-name>.streamlit.app`.

### 3. Verify the deployed app
- Open the public URL and confirm the file uploader loads.
- Upload `sample_data/sample_sales_data.csv` (or your own CSV/XLSX/JSON) and
  confirm validation stats, cleaning log, filters, KPIs, and all four chart
  tabs render without errors.
- Share the public URL — that's the link to submit.

## Testing notes
Before packaging, this app was verified with:
- Unit tests of every `data_utils.py` function against the provided dataset
  (load, validate, clean, summarize, KPI calc, filter) — including CSV, XLSX,
  and JSON inputs, and bad-input/empty-file error paths.
- Streamlit's `AppTest` headless test harness, simulating a full user session
  (load data → clean → filter → KPIs → charts) with zero exceptions raised.
