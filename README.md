# Job Costing & Quotation Calculator

A clean desktop app for service businesses (cleaning, trades, maintenance, etc.).

**Cost a job → price it to your target margin → manage a job library → generate a professional quote or tax invoice as PDF.**

![Python](https://img.shields.io/badge/Python-3.9%2B-blue)
![License](https://img.shields.io/badge/License-MIT-green)
![Platform](https://img.shields.io/badge/Platform-Windows%20%7C%20macOS%20%7C%20Linux-lightgrey)

## Features

- **Accurate job costing**
  - Labour (people × hours)
  - Travel (km + paid travel time for every person)
  - Materials & supplies
  - Other costs (hire, tip fees, subcontractors…)
  - Overhead (percentage of direct costs **or** per labour hour)
- **Smart pricing**
  - Target profit margin
  - Minimum job price
  - Round up to nearest $5 / $10 / etc.
  - Live “gut feel vs recommended” comparison
- **Job library**
  - Save, search, load, duplicate and delete jobs
  - Nothing is lost when you start a new job
- **Professional documents**
  - Quote or Tax Invoice
  - Clean A4 PDF (via ReportLab)
  - Live preview, email draft, copy as text
  - Itemised lines (overhead & profit stay hidden)
- **Fully local**
  - Data saved in `~/.job_costing/data.json`
  - No account, no internet required, nothing is sent anywhere
- **Keyboard shortcuts**
  - `Ctrl+N` New job · `Ctrl+S` Save to library · `Ctrl+L` Library  
  - `Ctrl+P` PDF · `Ctrl+E` Email · `Ctrl+,` Settings

## Requirements

- Python 3.9 or newer
- [ReportLab](https://pypi.org/project/reportlab/) (only needed for PDF export)

```bash
pip install reportlab
```

## Run

```bash
python job_costing_app.py
```

On first launch the app creates `~/.job_costing/data.json` and loads a sample job so you can explore immediately.

## Data

Everything is stored on your computer:

```
~/.job_costing/data.json
```

Use **File → Export backup…** to keep a safe copy.

Old v1 data files are automatically migrated to the new format.

## Screenshots / Tips

1. Open the app → the sample “End-of-lease clean” is already loaded.
2. Change labour, travel or materials and watch the recommended price update live.
3. Click **Save to library** (or `Ctrl+S`) to keep the job.
4. Switch to **Quote & invoice**, choose Quote or Invoice, then **Save as PDF**.

## License

MIT — free to use, modify and share.
