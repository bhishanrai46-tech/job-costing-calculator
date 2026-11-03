# Job Costing & Quotation Calculator (Streamlit)

Web version of the desktop app. Same costing engine, PDF quotes/invoices, and job library — runs in the browser.

## Run locally

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Deploy free on Streamlit Community Cloud

1. Push this folder (or the whole repo) to GitHub.
2. Go to [share.streamlit.io](https://share.streamlit.io) and sign in with GitHub.
3. **New app** → select the repo → set the main file path to `streamlit_job_costing/app.py` (or `app.py` if this folder is the repo root).
4. Deploy.

Your app will get a public URL like `https://your-app.streamlit.app`.

## Notes

- Data lives in the **browser session** (not a permanent server database). Use **Save to library** within a session; refresh clears it unless you add your own persistence later.
- PDF export needs `reportlab` (already in `requirements.txt`).
- For permanent multi-user storage you would add a database (e.g. Supabase, SQLite on a VPS, or Streamlit’s connection features).
