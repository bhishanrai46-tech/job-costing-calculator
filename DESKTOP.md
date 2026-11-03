# Desktop app (Windows / macOS / Linux)

This is the full **Tkinter** version with the original professional UI.

## Windows (easiest)

1. Install [Python 3.9+](https://www.python.org/downloads/) and tick **Add python.exe to PATH**.
2. Download `job_costing_app.py` and `Job Costing.bat` into the same folder.
3. Double-click **Job Costing.bat**.
   - First run installs `reportlab` automatically.
   - The app opens with no black console window.

## macOS / Linux

```bash
pip install reportlab
python3 job_costing_app.py
```

## Data

Saved locally at `~/.job_costing/data.json` (nothing is sent online).
