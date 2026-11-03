#!/usr/bin/env python3
"""
Job Costing & Quotation Calculator  v2.0  (desktop app)

Cost a job, price it to your target margin, manage a job library,
then produce a professional quote or tax invoice as PDF.

Requires:  Python 3.9+   and   pip install reportlab
Run:       python job_costing_app.py
Data:      ~/.job_costing/data.json   (auto-migrates from v1)

Keyboard shortcuts:
  Ctrl+N   New blank job
  Ctrl+S   Save current job to library
  Ctrl+L   Go to Job library
  Ctrl+P   Save PDF
  Ctrl+E   Open email draft
  Ctrl+,   Business settings
"""

from __future__ import annotations

import datetime as dt
import json
import math
import os
import re
import sys
import uuid
import webbrowser
from copy import deepcopy
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import quote

import tkinter as tk
from tkinter import filedialog, font as tkfont, messagebox, ttk

# ---------------------------------------------------------------------------
# Paths & constants
# ---------------------------------------------------------------------------

APP_DIR = os.path.join(os.path.expanduser("~"), ".job_costing")
DATA_FILE = os.path.join(APP_DIR, "data.json")
APP_VERSION = "2.0"

SYMBOLS = {
    "AUD": "$", "NZD": "$", "USD": "$", "CAD": "$",
    "GBP": "£", "EUR": "€", "JPY": "¥", "SGD": "$",
    "HKD": "$", "CHF": "CHF ", "INR": "₹",
}

NUMERIC_KEYS = {
    "labourRate", "overheadPct", "overheadHourly", "margin", "minPrice",
    "roundTo", "travelRate", "taxRate", "validDays", "depositPct",
    "payTerms", "people", "hours", "km", "travelHours", "gut", "paid",
}

SEG_COLORS = [
    ("labour", "#2457E6"),
    ("travel", "#0E8A8A"),
    ("materials", "#C27A0E"),
    ("other", "#7A4FBF"),
    ("overhead", "#8393A3"),
    ("profit", "#12A266"),
]

# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------

def today_stamp() -> str:
    return dt.date.today().strftime("%Y%m%d")


def now_iso() -> str:
    return dt.datetime.now().replace(microsecond=0).isoformat()


def new_id() -> str:
    return str(uuid.uuid4())


def num(v: Any) -> float:
    try:
        x = float(str(v).replace(",", "").replace("$", "").replace("£", "").replace("€", "").strip())
        return x if math.isfinite(x) else 0.0
    except (TypeError, ValueError):
        return 0.0


def pos(v: Any) -> float:
    return max(0.0, num(v))


def r2(x: float) -> float:
    return math.floor(x * 100 + 0.5) / 100


def clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def lines_of(text: Any) -> List[str]:
    return [x.strip() for x in str(text or "").splitlines() if x.strip()]


def parse_date(text: Any) -> dt.date:
    """Accept YYYY-MM-DD, DD/MM/YYYY, DD-MM-YYYY, or fall back to today."""
    s = str(text or "").strip()
    if not s:
        return dt.date.today()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y", "%Y/%m/%d"):
        try:
            return dt.datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    try:
        return dt.date.fromisoformat(s)
    except ValueError:
        return dt.date.today()


def fmt_date(d: dt.date) -> str:
    return f"{d.day} {d.strftime('%B %Y')}"


def money(s: Dict, v: float) -> str:
    sym = SYMBOLS.get(str(s.get("currency", "AUD")).upper(), "$")
    return ("-" if v < 0 else "") + sym + f"{abs(v):,.2f}"


# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

def default_settings() -> Dict:
    return {
        "bizName": "Example Cleaning Co.",
        "abn": "00 000 000 000",
        "phone": "0400 000 000",
        "bizEmail": "accounts@example.com.au",
        "address": "1 Example Street\nSydney NSW 2000",
        "currency": "AUD",
        "labourRate": 38.0,
        "overheadMode": "percent",
        "overheadPct": 15.0,
        "overheadHourly": 6.0,
        "margin": 25.0,
        "minPrice": 150.0,
        "roundTo": 5.0,
        "travelRate": 0.88,
        "taxOn": True,
        "taxName": "GST",
        "taxRate": 10.0,
        "validDays": 30,
        "depositPct": 20.0,
        "payTerms": 14,
        "payDetails": (
            "Account name: Example Cleaning Co.\n"
            "BSB: 000-000\n"
            "Account number: 0000 0000"
        ),
        "docNote": "Thank you for your business.",
    }


def doc_defaults() -> Dict:
    return {
        "docType": "quote",
        "quoteNo": "Q-" + today_stamp(),
        "invoiceNo": "INV-" + today_stamp(),
        "issueDate": dt.date.today().isoformat(),
        "paid": 0.0,
        "custEmail": "",
        "custAddress": "",
        "itemised": False,
        "emailEdited": False,
        "emailSubject": "",
        "emailBody": "",
    }


def sample_job() -> Dict:
    j = doc_defaults()
    j.update({
        "id": new_id(),
        "sample": True,
        "title": "End-of-lease clean, 3-bed unit",
        "client": "Sample Customer",
        "custEmail": "customer@example.com",
        "custAddress": "12 Sample Road\nSydney NSW 2000",
        "scope": (
            "Full interior clean to bond-return standard: kitchen, bathrooms, floors, "
            "windows (inside) and wardrobes.\nCarpet steam cleaning is not included."
        ),
        "people": 2,
        "hours": 3.0,
        "km": 18.0,
        "travelHours": 0.5,
        "materials": [
            {"d": "Cleaning products", "q": 1, "c": 18},
            {"d": "Consumables (cloths, bags, sponges)", "q": 1, "c": 12},
        ],
        "other": [],
        "gut": 250.0,
        "saved_at": now_iso(),
        "library_name": "",
    })
    return j


def blank_job() -> Dict:
    j = doc_defaults()
    j.update({
        "id": new_id(),
        "sample": False,
        "title": "",
        "client": "",
        "scope": "",
        "people": 1,
        "hours": 0.0,
        "km": 0.0,
        "travelHours": 0.0,
        "materials": [],
        "other": [],
        "gut": 0.0,
        "saved_at": now_iso(),
        "library_name": "",
    })
    return j

# NOTE: Full application continues below. This is a placeholder notice for the tool call size limit.
# The complete file is available at the local path and will be uploaded completely.
print('This is a truncated placeholder - full file upload required')
"""
PLACEHOLDER - The full 2879-line application will be uploaded in the next step.
"""
