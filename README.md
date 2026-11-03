# Job Costing & Quotation Calculator

Cost a job, price it to your target margin, manage a job library, and generate professional quotes or tax invoices as PDF.

Two versions are included:

| Version | Best for | How to run |
|---------|----------|------------|
| **Desktop** (`job_costing_app.py`) | Daily use on your computer | `python job_costing_app.py` |
| **Web / Streamlit** (`streamlit_job_costing/`) | Share online, use in the browser | `streamlit run app.py` or Streamlit Cloud |

![Python](https://img.shields.io/badge/Python-3.9%2B-blue)
![License](https://img.shields.io/badge/License-MIT-green)
![Platform](https://img.shields.io/badge/Platform-Windows%20%7C%20macOS%20%7C%20Linux%20%7C%20Web-lightgrey)

## Features

- **Accurate job costing** — labour, travel (km + paid time), materials, other costs, overhead
- **Smart pricing** — target margin, minimum price, rounding, live “gut feel vs recommended”
- **Job library** — save, search, load, duplicate, delete
- **Professional documents** — quote or tax invoice, clean A4 PDF, email draft
- **Private** — desktop version stores everything on your computer; Streamlit version uses the browser session

## Desktop app

```bash
pip install reportlab
python job_costing_app.py
```

Data is saved in `~/.job_costing/data.json`.

## Streamlit web app

```bash
cd streamlit_job_costing
pip install -r requirements.txt
streamlit run app.py
```

### Deploy free on Streamlit Community Cloud

1. Go to [share.streamlit.io](https://share.streamlit.io) and sign in with GitHub.
2. **New app** → select this repository.
3. Set **Main file path** to:
   ```
   streamlit_job_costing/app.py
   ```
4. Click **Deploy**.

You will get a public URL such as `https://your-app.streamlit.app`.

## License

MIT — free to use, modify and share.
