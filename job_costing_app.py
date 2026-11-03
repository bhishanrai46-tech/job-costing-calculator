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


# ---------------------------------------------------------------------------
# Costing engine (pure)
# ---------------------------------------------------------------------------

def calc(s: Dict, j: Dict) -> Dict:
    """Return a full cost/price breakdown. All values are non-negative where sensible."""
    people = pos(j.get("people"))
    hours = pos(j.get("hours"))
    rate = pos(s.get("labourRate"))

    on_site = people * hours
    travel_hours = pos(j.get("travelHours")) * people
    paid_hours = on_site + travel_hours

    labour = on_site * rate
    vehicle = pos(j.get("km")) * pos(s.get("travelRate"))
    travel_time = travel_hours * rate
    travel = vehicle + travel_time

    materials = sum(pos(r.get("q")) * pos(r.get("c")) for r in j.get("materials", []) or [])
    other = sum(pos(r.get("a")) for r in j.get("other", []) or [])
    direct = labour + travel + materials + other

    if s.get("overheadMode") == "hourly":
        overhead = paid_hours * pos(s.get("overheadHourly"))
    else:
        overhead = direct * pos(s.get("overheadPct")) / 100.0

    cost = direct + overhead
    target = clamp(num(s.get("margin")), 0.0, 90.0) / 100.0
    raw = cost / (1.0 - target) if cost > 0 else 0.0

    price = raw
    rounded = False
    min_applied = False

    step = pos(s.get("roundTo"))
    if step > 0 and price > 0:
        rp = math.ceil(price / step - 1e-9) * step
        rounded = rp > price + 0.004
        price = rp

    min_p = pos(s.get("minPrice"))
    if cost > 0 and min_p > price:
        price = min_p
        min_applied = True
        rounded = False

    price = r2(price)
    profit = price - cost
    tax_rate = pos(s.get("taxRate")) if s.get("taxOn") else 0.0
    tax = r2(price * tax_rate / 100.0)
    total = r2(price + tax)

    return {
        "labour": labour,
        "vehicle": vehicle,
        "travel_time": travel_time,
        "travel": travel,
        "materials": materials,
        "other": other,
        "direct": direct,
        "overhead": overhead,
        "cost": cost,
        "target": target,
        "raw": raw,
        "price": price,
        "rounded": rounded,
        "min_applied": min_applied,
        "profit": profit,
        "margin": (profit / price if price > 0 else 0.0),
        "tax": tax,
        "tax_rate": tax_rate,
        "total": total,
        "on_site": on_site,
        "paid_hours": paid_hours,
        "pph": (profit / paid_hours if paid_hours > 0 else 0.0),
    }


def doc_lines(j: Dict, r: Dict) -> List[Tuple[str, float]]:
    title = j.get("title") or "Job"
    if not j.get("itemised") or r["direct"] <= 0:
        return [(title, r["price"])]

    parts = [
        ("Labour and travel", r["labour"] + r["travel"]),
        ("Materials and supplies", r["materials"]),
        ("Other costs", r["other"]),
    ]
    parts = [p for p in parts if p[1] > 1e-5]
    out: List[Tuple[str, float]] = []
    total = 0.0
    for i, (name, val) in enumerate(parts):
        if i == len(parts) - 1:
            a = r2(r["price"] - total)
        else:
            a = r2(r["price"] * val / r["direct"])
        total += a
        out.append((name, a))
    return out


# ---------------------------------------------------------------------------
# Document model & PDF
# ---------------------------------------------------------------------------

def build_model(s: Dict, j: Dict, r: Dict) -> Dict:
    inv = j.get("docType") == "invoice"
    tn = s.get("taxName") or "Tax"
    cc = str(s.get("currency", "AUD")).upper()
    issue = parse_date(j.get("issueDate"))
    due = issue + dt.timedelta(days=int(round(pos(s.get("payTerms")))))
    until = issue + dt.timedelta(days=int(round(pos(s.get("validDays")))))
    paid = pos(j.get("paid")) if inv else 0.0

    m: Dict[str, Any] = {"inv": inv, "currency": cc}
    m["title"] = ("Tax invoice" if s.get("taxOn") else "Invoice") if inv else "Quote"
    m["number"] = (j.get("invoiceNo") if inv else j.get("quoteNo")) or ""
    m["bizName"] = s.get("bizName") or "Your business"

    biz = []
    if s.get("abn"):
        biz.append("ABN " + str(s["abn"]))
    biz += lines_of(s.get("address"))
    if s.get("phone"):
        biz.append(str(s["phone"]))
    if s.get("bizEmail"):
        biz.append(str(s["bizEmail"]))
    m["bizLines"] = biz

    m["billLabel"] = "Bill to" if inv else "Prepared for"
    m["billName"] = j.get("client") or "Customer"
    m["billLines"] = lines_of(j.get("custAddress"))
    if j.get("custEmail"):
        m["billLines"].append(str(j["custEmail"]))

    if inv:
        m["meta"] = [
            ("Invoice date", fmt_date(issue)),
            ("Due date", fmt_date(due)),
        ]
    else:
        m["meta"] = [
            ("Quote date", fmt_date(issue)),
            ("Valid until", fmt_date(until) if pos(s.get("validDays")) > 0 else "No expiry"),
        ]

    m["jobTitle"] = j.get("title") or "Untitled job"
    m["scope"] = j.get("scope") or ""
    m["lines"] = [(d, money(s, a)) for d, a in doc_lines(j, r)]

    tot = []
    if s.get("taxOn"):
        tot.append((f"Subtotal (excl. {tn})", money(s, r["price"]), False))
        tot.append((f"{tn} ({r['tax_rate']:g}%)", money(s, r["tax"]), False))
        tot.append((f"Total (incl. {tn})", money(s, r["total"]), True))
    else:
        tot.append(("Total", money(s, r["total"]), True))

    hl = None
    if inv:
        if paid > 0:
            tot.append(("Less amount received", "-" + money(s, paid), False))
        hl = (
            "Balance due" if paid > 0 else "Amount due",
            money(s, max(0.0, r["total"] - paid)),
        )
    elif pos(s.get("depositPct")) > 0:
        hl = (
            f"Deposit to book ({pos(s.get('depositPct')):g}%)",
            money(s, r["total"] * pos(s.get("depositPct")) / 100.0),
        )
    m["totals"], m["highlight"] = tot, hl
    m["payment"] = s.get("payDetails") if (inv and s.get("payDetails")) else None

    notes = []
    if inv:
        notes.append(
            f"Payment is due within {round(pos(s.get('payTerms')))} days, by {fmt_date(due)}."
        )
    else:
        if pos(s.get("depositPct")) > 0:
            notes.append(
                "A deposit is requested to book the job, with the balance due on completion."
            )
        if pos(s.get("validDays")) > 0:
            notes.append(
                f"This quote is valid for {round(pos(s.get('validDays')))} days, "
                f"until {fmt_date(until)}."
            )
    notes.append(f"All amounts are in {cc}.")
    if s.get("docNote"):
        notes.append(str(s["docNote"]))
    m["notes"] = notes
    return m


def model_text(m: Dict) -> str:
    L = [f"{m['title'].upper()} {m['number']}", m["bizName"]] + m["bizLines"] + [""]
    L.append(f"{m['billLabel']}: {m['billName']}")
    L += [f"{k}: {v}" for k, v in m["meta"]]
    L += ["", m["jobTitle"]]
    if m["scope"]:
        L.append(m["scope"])
    L.append("")
    L += [f"{d}: {a}" for d, a in m["lines"]]
    L += [f"{a}: {b}" for a, b, _ in m["totals"]]
    if m["highlight"]:
        L.append(f"{m['highlight'][0]}: {m['highlight'][1]}")
    if m["payment"]:
        L += ["", "Payment details:", m["payment"]]
    L.append("")
    L += m["notes"]
    return "\n".join(L)


def email_template(s: Dict, j: Dict, m: Dict) -> Tuple[str, str]:
    b = [("Hi %s," % j["client"]) if j.get("client") else "Hi,", ""]
    if m["inv"]:
        b.append(
            f"Please find attached {m['title'].lower()} {m['number']} for {m['jobTitle']}."
        )
        b.append("")
        b.append(f"{m['highlight'][0]}: {m['highlight'][1]}")
        b.append(f"Due date: {m['meta'][1][1]}")
        if s.get("payDetails"):
            b += ["", "Payment details:", str(s["payDetails"])]
        b += ["", "Please let me know if you have any questions."]
    else:
        strong = [t for t in m["totals"] if t[2]][0]
        b.append(
            f"Thanks for the opportunity to quote. Please find attached quote "
            f"{m['number']} for {m['jobTitle']}."
        )
        b.append("")
        b.append(f"{strong[0]}: {strong[1]}")
        b.append(f"{m['meta'][1][0]}: {m['meta'][1][1]}")
        b += [
            "",
            "If you are happy to go ahead, just reply to this email and we will lock in a date.",
        ]
    b += ["", "Kind regards,", m["bizName"]]
    if s.get("phone"):
        b.append(str(s["phone"]))
    subject = f"{m['title']} {m['number']} from {m['bizName']}"
    return subject, "\n".join(b)


def make_pdf(m: Dict, path: str) -> None:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.lib.utils import simpleSplit
    from reportlab.pdfgen import canvas

    W, H = A4
    ML, MR = 18, 192
    ACC = (36 / 255, 87 / 255, 230 / 255)
    INK = (15 / 255, 27 / 255, 45 / 255)
    MUT = (95 / 255, 110 / 255, 128 / 255)
    RULE = (221 / 255, 227 / 255, 235 / 255)
    SOFT = (244 / 255, 246 / 255, 249 / 255)

    c = canvas.Canvas(path, pagesize=A4)
    c.setTitle(f"{m['title']} {m['number']}")
    state = {"y": 0.0, "page": 1}

    def Y(y: float) -> float:
        return H - y * mm

    def font(name: str, size: float, color=INK) -> None:
        c.setFont(name, size)
        c.setFillColorRGB(*color)

    def wrap(text: str, width_mm: float, name: str = "Helvetica", size: float = 10) -> List[str]:
        out: List[str] = []
        for para in str(text).split("\n"):
            out += simpleSplit(para, name, size, width_mm * mm) or [""]
        return out

    def hr(y: float) -> None:
        c.setStrokeColorRGB(*RULE)
        c.setLineWidth(0.7)
        c.line(ML * mm, Y(y), MR * mm, Y(y))

    def top_band() -> None:
        c.setFillColorRGB(*ACC)
        c.rect(0, H - 5 * mm, W, 5 * mm, stroke=0, fill=1)

    def need(h: float) -> None:
        if state["y"] + h > 272:
            footer()
            c.showPage()
            state["page"] += 1
            top_band()
            state["y"] = 20

    def footer() -> None:
        font("Helvetica", 8, MUT)
        c.drawString(ML * mm, Y(288), f"{m['bizName']}  |  {m['title']} {m['number']}")
        c.drawRightString(MR * mm, Y(288), f"Page {state['page']}")

    def text_block(
        lines: List[str],
        x: float,
        lh: float,
        name: str = "Helvetica",
        size: float = 10,
        color=INK,
    ) -> None:
        for ln in lines:
            need(lh)
            font(name, size, color)
            c.drawString(x * mm, Y(state["y"]), ln)
            state["y"] += lh

    top_band()
    state["y"] = 22
    top_y = state["y"]
    text_block(wrap(m["bizName"], 100, "Helvetica-Bold", 17), ML, 7, "Helvetica-Bold", 17)
    for ln in m["bizLines"]:
        text_block(wrap(ln, 95, "Helvetica", 9.5), ML, 4.6, "Helvetica", 9.5, MUT)
    left_end = state["y"]

    font("Helvetica-Bold", 22)
    c.drawRightString(MR * mm, Y(top_y + 1), m["title"].upper())
    font("Helvetica", 10.5, MUT)
    c.drawRightString(MR * mm, Y(top_y + 8), m["number"])
    state["y"] = max(left_end, top_y + 14) + 6
    hr(state["y"])
    state["y"] += 9

    col_top = state["y"]
    font("Helvetica-Bold", 8, MUT)
    c.drawString(ML * mm, Y(state["y"]), m["billLabel"].upper())
    state["y"] += 5.5
    text_block(wrap(m["billName"], 85, "Helvetica-Bold", 11.5), ML, 5.5, "Helvetica-Bold", 11.5)
    for ln in m["billLines"]:
        text_block(wrap(ln, 85, "Helvetica", 9.5), ML, 4.7, "Helvetica", 9.5, MUT)
    left_y = state["y"]

    ry = col_top
    for k, v in m["meta"]:
        font("Helvetica", 9.5, MUT)
        c.drawString(128 * mm, Y(ry), k)
        font("Helvetica-Bold", 9.5)
        c.drawRightString(MR * mm, Y(ry), v)
        ry += 6
    state["y"] = max(left_y, ry) + 8

    need(20)
    text_block(wrap(m["jobTitle"], 174, "Helvetica-Bold", 12.5), ML, 6, "Helvetica-Bold", 12.5)
    if m["scope"]:
        state["y"] += 1
        text_block(wrap(m["scope"], 174, "Helvetica", 9.5), ML, 4.7, "Helvetica", 9.5, MUT)
    state["y"] += 6

    need(24)
    c.setFillColorRGB(*SOFT)
    c.rect(ML * mm, Y(state["y"] + 3), (MR - ML) * mm, 8.5 * mm, stroke=0, fill=1)
    font("Helvetica-Bold", 8, MUT)
    c.drawString((ML + 3) * mm, Y(state["y"]), "DESCRIPTION")
    c.drawRightString((MR - 3) * mm, Y(state["y"]), f"AMOUNT ({m['currency']})")
    state["y"] += 7

    for desc, amt in m["lines"]:
        dl = wrap(desc, 140)
        need(len(dl) * 5 + 6)
        font("Helvetica", 10)
        for i, ln in enumerate(dl):
            c.drawString((ML + 3) * mm, Y(state["y"] + i * 5), ln)
        font("Helvetica-Bold", 10)
        c.drawRightString((MR - 3) * mm, Y(state["y"]), amt)
        state["y"] += len(dl) * 5 - 1
        hr(state["y"])
        state["y"] += 6.5
    state["y"] += 2

    need(len(m["totals"]) * 7.5 + 30)
    for label, val, strong in m["totals"]:
        if strong:
            c.setStrokeColorRGB(*RULE)
            c.line(118 * mm, Y(state["y"] - 4.5), MR * mm, Y(state["y"] - 4.5))
            font("Helvetica-Bold", 11.5)
        else:
            font("Helvetica", 10, MUT)
        c.drawString(118 * mm, Y(state["y"]), label)
        font("Helvetica-Bold" if strong else "Helvetica", 11.5 if strong else 10)
        c.drawRightString(MR * mm, Y(state["y"]), val)
        state["y"] += 7.5

    if m["highlight"]:
        state["y"] += 1
        need(16)
        c.setFillColorRGB(*ACC)
        c.roundRect(118 * mm, Y(state["y"] + 6), (MR - 118) * mm, 12 * mm, 1.5 * mm, stroke=0, fill=1)
        c.setFillColorRGB(1, 1, 1)
        c.setFont("Helvetica", 10)
        c.drawString(122 * mm, Y(state["y"] + 1.3), m["highlight"][0])
        c.setFont("Helvetica-Bold", 13)
        c.drawRightString((MR - 4) * mm, Y(state["y"] + 1.8), m["highlight"][1])
        state["y"] += 14
    state["y"] += 4

    if m["payment"]:
        need(22)
        font("Helvetica-Bold", 8, MUT)
        c.drawString(ML * mm, Y(state["y"]), "PAYMENT DETAILS")
        state["y"] += 5.5
        text_block(wrap(m["payment"], 120), ML, 5)
        state["y"] += 3

    if m["notes"]:
        need(12)
        hr(state["y"])
        state["y"] += 6
        for n in m["notes"]:
            text_block(wrap(n, 174, "Helvetica", 9), ML, 4.6, "Helvetica", 9, MUT)
            state["y"] += 1

    footer()
    c.save()


# ---------------------------------------------------------------------------
# Storage (v2 with library + migration)
# ---------------------------------------------------------------------------

def load_data() -> Tuple[Dict, Dict, List[Dict]]:
    """Return (settings, current_job, library). Migrates v1 data automatically."""
    s = default_settings()
    j = sample_job()
    library: List[Dict] = []

    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            d = json.load(f)
    except (OSError, ValueError, json.JSONDecodeError):
        return s, j, library

    if not isinstance(d, dict):
        return s, j, library

    # Settings
    if "S" in d and isinstance(d["S"], dict):
        s.update(d["S"])

    # v2 shape
    if "version" in d and d.get("version", 1) >= 2:
        if "current" in d and isinstance(d["current"], dict):
            j = blank_job()
            j.update(d["current"])
        if "library" in d and isinstance(d["library"], list):
            library = []
            for item in d["library"]:
                if isinstance(item, dict) and "job" in item:
                    library.append(item)
                elif isinstance(item, dict):  # tolerate flat jobs
                    entry = {
                        "id": item.get("id") or new_id(),
                        "saved_at": item.get("saved_at") or now_iso(),
                        "name": item.get("library_name") or item.get("title") or "Untitled",
                        "job": item,
                    }
                    library.append(entry)
    else:
        # v1 migration
        if "J" in d and isinstance(d["J"], dict):
            j = blank_job()
            j.update(d["J"])
            j.setdefault("id", new_id())
            j.setdefault("saved_at", now_iso())
            # Put the old current job into the library so nothing is lost
            if j.get("title") or j.get("client"):
                library.append({
                    "id": j.get("id") or new_id(),
                    "saved_at": j.get("saved_at") or now_iso(),
                    "name": j.get("title") or "Migrated job",
                    "job": deepcopy(j),
                })

    j.setdefault("materials", [])
    j.setdefault("other", [])
    j.setdefault("id", new_id())
    return s, j, library


def save_data(s: Dict, j: Dict, library: List[Dict]) -> None:
    try:
        os.makedirs(APP_DIR, exist_ok=True)
        payload = {
            "version": 2,
            "S": s,
            "current": j,
            "library": library,
        }
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
    except OSError:
        pass


# ---------------------------------------------------------------------------
# UI colours & fonts
# ---------------------------------------------------------------------------

C = dict(
    side="#0F1B2D",
    side_hover="#18283F",
    side_active="#1F3453",
    side_fg="#C5D0E0",
    side_muted="#7D8EA6",
    bg="#F3F5F9",
    card="#FFFFFF",
    line="#DDE3EC",
    field="#C3CDDA",
    ink="#111C2E",
    muted="#66758A",
    accent="#2457E6",
    accent_dark="#1B47C4",
    soft="#F6F8FB",
    good="#0F7A4B",
    warn="#8F5200",
    bad="#B3261E",
    good_bg="#DCF3E7",
    warn_bg="#FBEBCF",
    bad_bg="#FBE0DD",
    neutral_bg="#EEF2F8",
)

if sys.platform.startswith("win"):
    FONT, MONO = "Segoe UI", "Consolas"
elif sys.platform == "darwin":
    FONT, MONO = "Helvetica Neue", "Menlo"
else:
    FONT, MONO = "DejaVu Sans", "DejaVu Sans Mono"

SC = 1.0


def px(n: float) -> int:
    return int(round(n * SC))


# ---------------------------------------------------------------------------
# Widgets
# ---------------------------------------------------------------------------

def autowrap(label: tk.Label, pad: int = 4) -> tk.Label:
    label.bind("<Configure>", lambda e: label.config(wraplength=max(80, e.width - pad)))
    return label


class Btn(tk.Label):
    """Flat button that looks the same on Windows, macOS and Linux."""

    def __init__(self, parent, text, command, kind="secondary"):
        look = {
            "primary": (C["accent"], "#FFFFFF", C["accent_dark"], C["accent"]),
            "secondary": (C["card"], C["ink"], C["soft"], C["field"]),
            "danger": (C["card"], C["bad"], C["bad_bg"], C["field"]),
        }[kind]
        self.look, self.command = look, command
        super().__init__(
            parent,
            text=text,
            bg=look[0],
            fg=look[1],
            font=(FONT, 10, "bold"),
            padx=px(16),
            pady=px(7),
            cursor="hand2",
            highlightthickness=1,
            highlightbackground=look[3],
            bd=0,
        )
        self.bind("<Enter>", lambda e: self.config(bg=self.look[2]))
        self.bind("<Leave>", lambda e: self.config(bg=self.look[0]))
        self.bind("<ButtonRelease-1>", self._click)

    def _click(self, e):
        if 0 <= e.x <= self.winfo_width() and 0 <= e.y <= self.winfo_height():
            self.command()


class Seg(tk.Frame):
    """Segmented control bound to a StringVar."""

    def __init__(self, parent, var, options):
        super().__init__(parent, bg=C["neutral_bg"], padx=3, pady=3)
        self.var, self.items = var, {}
        for value, text in options:
            b = tk.Label(
                self,
                text=text,
                font=(FONT, 10, "bold"),
                padx=px(16),
                pady=px(6),
                cursor="hand2",
                bd=0,
            )
            b.pack(side="left", padx=(0, 3))
            b.bind("<Button-1>", lambda e, v=value: var.set(v))
            self.items[value] = b
        var.trace_add("write", lambda *_: self.paint())
        self.paint()

    def paint(self):
        for value, b in self.items.items():
            on = self.var.get() == value
            b.config(
                bg=C["card"] if on else C["neutral_bg"],
                fg=C["ink"] if on else C["muted"],
            )


class ScrollFrame(tk.Frame):
    def __init__(self, parent, bg):
        super().__init__(parent, bg=bg)
        self.canvas = tk.Canvas(self, bg=bg, highlightthickness=0, bd=0)
        self.sb = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.inner = tk.Frame(self.canvas, bg=bg)
        self.win = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.inner.bind(
            "<Configure>",
            lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")),
        )
        self.canvas.bind(
            "<Configure>",
            lambda e: self.canvas.itemconfigure(self.win, width=e.width),
        )
        self.canvas.configure(yscrollcommand=self.sb.set)
        self.sb.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)


# ---------------------------------------------------------------------------
# Main application
# ---------------------------------------------------------------------------

class App(tk.Tk):
    def __init__(self):
        if sys.platform.startswith("win"):
            try:
                import ctypes
                ctypes.windll.shcore.SetProcessDpiAwareness(1)
            except Exception:
                pass

        super().__init__()
        global SC
        SC = max(1.0, self.winfo_fpixels("1i") / 96.0)

        self.title(f"Job Costing & Quotation Calculator  v{APP_VERSION}")
        self.configure(bg=C["bg"])
        w, h = px(1280), px(840)
        self.geometry(
            f"{w}x{h}+{max(0, (self.winfo_screenwidth() - w) // 2)}+"
            f"{max(0, (self.winfo_screenheight() - h) // 3)}"
        )
        self.minsize(px(1080), px(720))

        self.S, self.J, self.library = load_data()
        self.vars: Dict[Tuple[str, str], Tuple[Any, str]] = {}
        self.pages: Dict[str, tk.Frame] = {}
        self.navs: Dict[str, Tuple] = {}
        self._busy = False
        self.r: Optional[Dict] = None
        self.model: Optional[Dict] = None
        self.current = "job"
        self._lib_filter = ""
        self._cur_labels: List[tk.Label] = []

        self._ttk_style()
        self._menu()
        self._shell()
        self.fill_all()
        self.refresh()
        self.show("job")

        self.bind_all("<MouseWheel>", self._wheel)
        self.bind_all("<Button-4>", self._wheel)
        self.bind_all("<Button-5>", self._wheel)

        # Keyboard shortcuts
        self.bind_all("<Control-n>", lambda e: self.new_blank())
        self.bind_all("<Control-N>", lambda e: self.new_blank())
        self.bind_all("<Control-s>", lambda e: self.save_to_library())
        self.bind_all("<Control-S>", lambda e: self.save_to_library())
        self.bind_all("<Control-l>", lambda e: self.show("lib"))
        self.bind_all("<Control-L>", lambda e: self.show("lib"))
        self.bind_all("<Control-p>", lambda e: self.save_pdf())
        self.bind_all("<Control-P>", lambda e: self.save_pdf())
        self.bind_all("<Control-e>", lambda e: self.open_email())
        self.bind_all("<Control-E>", lambda e: self.open_email())
        self.bind_all("<Control-comma>", lambda e: self.show("set"))

    # ----- styling ---------------------------------------------------------

    def _ttk_style(self):
        st = ttk.Style(self)
        try:
            st.theme_use("clam")
        except tk.TclError:
            pass
        st.configure(
            "Treeview",
            rowheight=px(30),
            font=(FONT, 10),
            background=C["card"],
            fieldbackground=C["card"],
            foreground=C["ink"],
            borderwidth=0,
            relief="flat",
        )
        st.configure(
            "Treeview.Heading",
            font=(FONT, 9, "bold"),
            background=C["soft"],
            foreground=C["muted"],
            relief="flat",
            borderwidth=0,
            padding=(8, 6),
        )
        st.map(
            "Treeview",
            background=[("selected", "#E3EBFC")],
            foreground=[("selected", C["ink"])],
        )
        st.map("Treeview.Heading", background=[("active", C["soft"])])
        st.layout("Treeview", [("Treeview.treearea", {"sticky": "nswe"})])
        st.configure(
            "Vertical.TScrollbar",
            background="#C9D2DE",
            troughcolor=C["bg"],
            bordercolor=C["bg"],
            arrowcolor=C["bg"],
            lightcolor="#C9D2DE",
            darkcolor="#C9D2DE",
            gripcount=0,
            relief="flat",
            arrowsize=px(12),
        )
        st.map("Vertical.TScrollbar", background=[("active", "#AEB9C8")])
        st.configure(
            "Card.TCheckbutton",
            background=C["card"],
            foreground=C["ink"],
            font=(FONT, 10),
        )
        st.map("Card.TCheckbutton", background=[("active", C["card"])])

    def _menu(self):
        mb = tk.Menu(self)

        f = tk.Menu(mb, tearoff=0)
        f.add_command(label="New blank job", command=self.new_blank, accelerator="Ctrl+N")
        f.add_command(label="Load sample job", command=self.load_sample)
        f.add_separator()
        f.add_command(
            label="Save current job to library…",
            command=self.save_to_library,
            accelerator="Ctrl+S",
        )
        f.add_command(label="Job library", command=lambda: self.show("lib"), accelerator="Ctrl+L")
        f.add_separator()
        f.add_command(
            label="Save quote or invoice as PDF…",
            command=self.save_pdf,
            accelerator="Ctrl+P",
        )
        f.add_separator()
        f.add_command(label="Export backup…", command=self.export_backup)
        f.add_command(label="Import backup…", command=self.import_backup)
        f.add_command(label="Open data folder", command=self.open_data_folder)
        f.add_separator()
        f.add_command(label="Exit", command=self.destroy)
        mb.add_cascade(label="File", menu=f)

        h = tk.Menu(mb, tearoff=0)
        h.add_command(label="Where is my data stored?", command=self.where_data)
        h.add_command(
            label="About",
            command=lambda: messagebox.showinfo(
                "About",
                f"Job Costing & Quotation Calculator  v{APP_VERSION}\n\n"
                "Cost a job, price it to your target margin, manage a job library,\n"
                "then send a quote or tax invoice as a PDF.\n\n"
                "Data stays on this computer. Nothing is sent over the internet.",
            ),
        )
        mb.add_cascade(label="Help", menu=h)
        self.config(menu=mb)

    # ----- shell -----------------------------------------------------------

    def _shell(self):
        status = tk.Frame(self, bg=C["card"], highlightthickness=1, highlightbackground=C["line"])
        status.pack(side="bottom", fill="x")
        self.lbl_saved = tk.Label(
            status, text="", bg=C["card"], fg=C["muted"], font=(FONT, 9), padx=px(14), pady=px(5)
        )
        self.lbl_saved.pack(side="left")
        tk.Label(
            status,
            text="Data:  " + DATA_FILE,
            bg=C["card"],
            fg=C["muted"],
            font=(FONT, 9),
            padx=px(14),
        ).pack(side="right")

        side = tk.Frame(self, bg=C["side"], width=px(232))
        side.pack(side="left", fill="y")
        side.pack_propagate(False)

        brand = tk.Frame(side, bg=C["side"])
        brand.pack(fill="x", padx=px(18), pady=(px(24), px(26)))
        mark = tk.Canvas(brand, width=px(34), height=px(34), bg=C["side"], highlightthickness=0)
        mark.pack(side="left")
        mark.create_rectangle(0, 0, px(34), px(34), fill=C["accent"], outline="")
        for i, wd in enumerate((18, 12, 7)):
            y = px(10 + i * 7)
            mark.create_line(px(9), y, px(9 + wd), y, fill="white", width=px(2.4))
        tx = tk.Frame(brand, bg=C["side"])
        tx.pack(side="left", padx=(px(10), 0))
        tk.Label(tx, text="Job Costing", bg=C["side"], fg="white", font=(FONT, 12, "bold")).pack(
            anchor="w"
        )
        tk.Label(
            tx, text="Quotation Calculator", bg=C["side"], fg=C["side_muted"], font=(FONT, 9)
        ).pack(anchor="w")

        for key, label in (
            ("job", "Job costing"),
            ("doc", "Quote & invoice"),
            ("lib", "Job library"),
            ("set", "Business settings"),
        ):
            item = tk.Frame(side, bg=C["side"], cursor="hand2")
            item.pack(fill="x")
            bar = tk.Frame(item, bg=C["side"], width=px(4))
            bar.pack(side="left", fill="y")
            lab = tk.Label(
                item,
                text=label,
                bg=C["side"],
                fg=C["side_fg"],
                font=(FONT, 11, "bold"),
                anchor="w",
                padx=px(18),
                pady=px(12),
                cursor="hand2",
            )
            lab.pack(side="left", fill="x", expand=True)
            for wdg in (item, lab, bar):
                wdg.bind("<Button-1>", lambda e, k=key: self.show(k))
                wdg.bind("<Enter>", lambda e, k=key: self._nav_hover(k, True))
                wdg.bind("<Leave>", lambda e, k=key: self._nav_hover(k, False))
            self.navs[key] = (item, lab, bar)

        foot = tk.Frame(side, bg=C["side"])
        foot.pack(side="bottom", fill="x", padx=px(18), pady=px(18))
        tk.Frame(foot, bg="#1E3049", height=1).pack(fill="x", pady=(0, px(12)))
        self.lbl_side_biz = tk.Label(
            foot,
            text="",
            bg=C["side"],
            fg="white",
            font=(FONT, 10, "bold"),
            anchor="w",
            wraplength=px(190),
            justify="left",
        )
        self.lbl_side_biz.pack(anchor="w")
        self.lbl_side_lib = tk.Label(
            foot, text="", bg=C["side"], fg=C["side_muted"], font=(FONT, 9)
        )
        self.lbl_side_lib.pack(anchor="w")

        self.content = tk.Frame(self, bg=C["bg"])
        self.content.pack(side="left", fill="both", expand=True)

        self.pages["job"] = self._page_job(self.content)
        self.pages["doc"] = self._page_doc(self.content)
        self.pages["lib"] = self._page_library(self.content)
        self.pages["set"] = self._page_settings(self.content)

    def _nav_hover(self, key, on):
        if key == self.current:
            return
        bg = C["side_hover"] if on else C["side"]
        item, lab, bar = self.navs[key]
        for w in (item, lab):
            w.config(bg=bg)

    def show(self, key):
        self.current = key
        for k, page in self.pages.items():
            page.pack_forget()
            item, lab, bar = self.navs[k]
            on = k == key
            for w in (item, lab):
                w.config(bg=C["side_active"] if on else C["side"])
            lab.config(fg="white" if on else C["side_fg"])
            bar.config(bg=C["accent"] if on else C["side"])
        self.pages[key].pack(fill="both", expand=True, padx=px(28), pady=(px(22), px(14)))
        if key == "lib":
            self.refresh_library()

    def _wheel(self, e):
        w = self.winfo_containing(e.x_root, e.y_root)
        while w is not None and not isinstance(w, ScrollFrame):
            w = w.master
        if w is None:
            return
        lo, hi = w.canvas.yview()
        if lo <= 0.0 and hi >= 1.0:
            return
        step = -1 if (e.num == 4 or getattr(e, "delta", 0) > 0) else 1
        w.canvas.yview_scroll(step * 2, "units")

    # ----- building blocks -------------------------------------------------

    def head(self, parent, crumb, title, buttons=()):
        h = tk.Frame(parent, bg=C["bg"])
        h.pack(fill="x", pady=(0, px(16)))
        left = tk.Frame(h, bg=C["bg"])
        left.pack(side="left")
        tk.Label(
            left, text=crumb.upper(), bg=C["bg"], fg=C["accent"], font=(FONT, 9, "bold")
        ).pack(anchor="w")
        lbl = tk.Label(left, text=title, bg=C["bg"], fg=C["ink"], font=(FONT, 20, "bold"))
        lbl.pack(anchor="w")
        right = tk.Frame(h, bg=C["bg"])
        right.pack(side="right", anchor="s")
        for b in buttons:
            b(right).pack(side="left", padx=(px(8), 0))
        return lbl

    def card(self, parent, title, sub=None, chip=False, pad_bottom=14):
        outer = tk.Frame(
            parent, bg=C["card"], highlightthickness=1, highlightbackground=C["line"]
        )
        outer.pack(fill="x", pady=(0, px(pad_bottom)))
        top = tk.Frame(outer, bg=C["card"])
        top.pack(fill="x", padx=px(20), pady=(px(16), 0))
        tk.Label(top, text=title, bg=C["card"], fg=C["ink"], font=(FONT, 12, "bold")).pack(
            side="left"
        )
        chip_lbl = None
        if chip:
            chip_lbl = tk.Label(
                top,
                text="",
                bg=C["neutral_bg"],
                fg=C["ink"],
                font=(FONT, 10, "bold"),
                padx=px(10),
                pady=px(2),
            )
            chip_lbl.pack(side="right")
        if sub:
            sub_lbl = tk.Label(
                outer,
                text=sub,
                bg=C["card"],
                fg=C["muted"],
                font=(FONT, 9),
                anchor="w",
                justify="left",
            )
            sub_lbl.pack(anchor="w", padx=px(20), pady=(px(2), 0))
        body = tk.Frame(outer, bg=C["card"])
        body.pack(fill="x", padx=px(20), pady=(px(12), px(18)))
        body.chip = chip_lbl
        body.sub = sub_lbl if sub else None
        return body

    def bind_var(self, store, key):
        v = tk.StringVar()
        self.vars[(store, key)] = (v, "str")
        if key == "emailSubject":
            v.trace_add(
                "write",
                lambda *_: None
                if self._busy
                else (self.J.__setitem__("emailEdited", True), self.on_change()),
            )
        else:
            v.trace_add("write", lambda *_: self.on_change())
        return v

    def field(
        self,
        parent,
        store,
        key,
        label,
        unit="",
        prefix="",
        hint="",
        width=10,
        text=False,
        height=3,
    ):
        f = tk.Frame(parent, bg=C["card"])
        tk.Label(
            f, text=label, bg=C["card"], fg=C["ink"], font=(FONT, 9, "bold"), anchor="w"
        ).pack(anchor="w", pady=(0, px(4)))
        box = tk.Frame(f, bg=C["card"], highlightthickness=1, highlightbackground=C["field"])
        box.pack(fill="x")
        if text:
            t = tk.Text(
                box,
                height=height,
                width=width,
                wrap="word",
                font=(FONT, 10),
                relief="flat",
                bd=0,
                bg=C["card"],
                fg=C["ink"],
                insertbackground=C["ink"],
                highlightthickness=0,
                padx=px(8),
                pady=px(6),
                undo=True,
            )
            t.pack(fill="x")
            t.bind("<KeyRelease>", lambda e: self.on_text(key))
            t.bind("<FocusIn>", lambda e: box.config(highlightbackground=C["accent"]))
            t.bind("<FocusOut>", lambda e: box.config(highlightbackground=C["field"]))
            self.vars[(store, key)] = (t, "text")
        else:
            if prefix:
                pl = tk.Label(
                    box, text=prefix, bg=C["soft"], fg=C["muted"], font=(FONT, 10), padx=px(10)
                )
                pl.pack(side="left", fill="y")
                self._cur_labels.append(pl)
            v = self.bind_var(store, key)
            e = tk.Entry(
                box,
                textvariable=v,
                relief="flat",
                bd=0,
                font=(FONT, 11),
                bg=C["card"],
                fg=C["ink"],
                insertbackground=C["ink"],
                highlightthickness=0,
                width=width,
            )
            e.pack(side="left", fill="x", expand=True, ipady=px(6), padx=px(8))
            if unit:
                tk.Label(
                    box,
                    text=unit,
                    bg=C["soft"],
                    fg=C["muted"],
                    font=(FONT, 9, "bold"),
                    padx=px(10),
                ).pack(side="right", fill="y")
            e.bind(
                "<FocusIn>",
                lambda ev, b=box, en=e: (
                    b.config(highlightbackground=C["accent"]),
                    en.after_idle(lambda: en.select_range(0, "end")),
                ),
            )
            e.bind("<FocusOut>", lambda ev, b=box: b.config(highlightbackground=C["field"]))
        if hint:
            autowrap(
                tk.Label(
                    f,
                    text=hint,
                    bg=C["card"],
                    fg=C["muted"],
                    font=(FONT, 9),
                    justify="left",
                    anchor="w",
                )
            ).pack(fill="x", pady=(px(4), 0))
        return f

    def frow(self, body, specs, last=False):
        row = tk.Frame(body, bg=C["card"])
        row.pack(fill="x", pady=(0, 0 if last else px(12)))
        for i, sp in enumerate(specs):
            self.field(row, **sp).pack(
                side="left",
                fill="x",
                expand=True,
                padx=(0 if i == 0 else px(14), 0),
                anchor="n",
            )
        return row

    def make_list(self, parent, title, sub, key, cols):
        body = self.card(parent, title, sub, chip=True)
        tree = ttk.Treeview(
            body, columns=[c[0] for c in cols], show="headings", height=3, selectmode="browse"
        )
        for cid, head, w, anc in cols:
            tree.heading(cid, text=head, anchor=anc)
            tree.column(cid, width=px(w), anchor=anc, stretch=(cid == "d"))
        tree.pack(fill="x")
        form = tk.Frame(body, bg=C["card"])
        form.pack(fill="x", pady=(px(12), 0))
        ents = {}
        for cid, head, w, anc in cols:
            fr = tk.Frame(form, bg=C["card"])
            fr.pack(side="left", padx=(0, px(8)), fill="x", expand=(cid == "d"))
            tk.Label(fr, text=head, bg=C["card"], fg=C["muted"], font=(FONT, 9, "bold")).pack(
                anchor="w"
            )
            box = tk.Frame(
                fr, bg=C["card"], highlightthickness=1, highlightbackground=C["field"]
            )
            box.pack(fill="x")
            e = tk.Entry(
                box,
                relief="flat",
                bd=0,
                font=(FONT, 10),
                bg=C["card"],
                fg=C["ink"],
                highlightthickness=0,
                width=(20 if cid == "d" else 9),
            )
            e.pack(fill="x", ipady=px(5), padx=px(8))
            e.bind("<FocusIn>", lambda ev, b=box: b.config(highlightbackground=C["accent"]))
            e.bind("<FocusOut>", lambda ev, b=box: b.config(highlightbackground=C["field"]))
            e.bind("<Return>", lambda ev, k=key, es=ents: self.add_row(k, es))
            ents[cid] = e
        btns = tk.Frame(form, bg=C["card"])
        btns.pack(side="left", anchor="s")
        Btn(btns, "Add", lambda k=key, es=ents: self.add_row(k, es), "primary").pack(
            side="left", padx=(0, px(6))
        )
        Btn(btns, "Remove", lambda k=key, t=tree: self.remove_row(k, t)).pack(side="left")
        return tree, body.chip

    # ----- pages -----------------------------------------------------------

    def _page_job(self, parent):
        page = tk.Frame(parent, bg=C["bg"])
        self.lbl_jobhead = self.head(
            page,
            "Job costing",
            "New job",
            [
                lambda p: Btn(p, "New blank job", self.new_blank),
                lambda p: Btn(p, "Save to library", self.save_to_library, "primary"),
                lambda p: Btn(p, "Load sample", self.load_sample),
            ],
        )
        self.banner = tk.Label(
            page,
            text=(
                "Sample job loaded. A two-person end-of-lease clean that a gut-feel quote "
                "would underprice. Change any figure to cost your own job."
            ),
            bg="#E8EEFD",
            fg=C["ink"],
            font=(FONT, 10),
            anchor="w",
            padx=px(14),
            pady=px(8),
            justify="left",
        )
        autowrap(self.banner, 28)

        body = tk.Frame(page, bg=C["bg"])
        body.pack(fill="both", expand=True)
        body.columnconfigure(0, weight=1)
        body.columnconfigure(1, minsize=px(390))
        body.rowconfigure(0, weight=1)

        left = ScrollFrame(body, C["bg"])
        left.grid(row=0, column=0, sticky="nsew")
        rscroll = ScrollFrame(body, C["bg"])
        rscroll.grid(row=0, column=1, sticky="nsew", padx=(px(20), 0))
        right = rscroll.inner
        L = left.inner

        b = self.card(L, "Job details", "Shown on the quote and invoice.")
        self.frow(
            b,
            [
                dict(store="J", key="title", label="Job title", width=22),
                dict(store="J", key="client", label="Customer", width=16),
            ],
        )
        self.frow(
            b,
            [dict(store="J", key="scope", label="Scope of work", text=True, height=3, width=30)],
            last=True,
        )

        b = self.card(L, "Labour", None, chip=True)
        self.chip_labour = b.chip
        self.frow(
            b,
            [
                dict(store="J", key="people", label="People on the job", unit="people", width=6),
                dict(store="J", key="hours", label="Hours on site, each", unit="hrs", width=6),
            ],
        )
        self.lbl_labour = tk.Label(
            b, text="", bg=C["card"], fg=C["muted"], font=(FONT, 9), anchor="w"
        )
        self.lbl_labour.pack(anchor="w")

        b = self.card(L, "Travel", None, chip=True)
        self.chip_travel = b.chip
        self.frow(
            b,
            [
                dict(store="J", key="km", label="Distance, return trip", unit="km", width=6),
                dict(
                    store="J",
                    key="travelHours",
                    label="Travel time, return trip",
                    unit="hrs",
                    width=6,
                ),
            ],
        )
        self.lbl_travel = autowrap(
            tk.Label(
                b, text="", bg=C["card"], fg=C["muted"], font=(FONT, 9), anchor="w", justify="left"
            )
        )
        self.lbl_travel.pack(fill="x")

        self.tree_mat, self.chip_mat = self.make_list(
            L,
            "Materials & supplies",
            "Everything you buy for this job.",
            "materials",
            [
                ("d", "Item", 260, "w"),
                ("q", "Qty", 70, "e"),
                ("c", "Unit cost", 100, "e"),
            ],
        )
        self.tree_oth, self.chip_oth = self.make_list(
            L,
            "Other costs",
            "Equipment hire, subcontractors, tip fees and permits.",
            "other",
            [("d", "Description", 330, "w"), ("a", "Amount", 110, "e")],
        )

        # summary hero
        hero = tk.Frame(right, bg=C["side"])
        hero.pack(fill="x", pady=(0, px(14)))
        hi = tk.Frame(hero, bg=C["side"])
        hi.pack(fill="x", padx=px(22), pady=px(18))
        self.lbl_priceLab = tk.Label(
            hi, text="", bg=C["side"], fg="#93A4BB", font=(FONT, 9, "bold")
        )
        self.lbl_priceLab.pack(anchor="w")
        self.lbl_price = tk.Label(
            hi, text="", bg=C["side"], fg="white", font=(FONT, 34, "bold")
        )
        self.lbl_price.pack(anchor="w")
        self.lbl_taxline = tk.Label(hi, text="", bg=C["side"], fg="#93A4BB", font=(FONT, 10))
        self.lbl_taxline.pack(anchor="w")
        self.lbl_flag = autowrap(
            tk.Label(
                hi, text="", bg=C["side"], fg="#F0B25C", font=(FONT, 9), justify="left", anchor="w"
            )
        )
        self.lbl_flag.pack(fill="x")
        tk.Frame(hi, bg="#263A52", height=1).pack(fill="x", pady=(px(12), px(10)))
        grid = tk.Frame(hi, bg=C["side"])
        grid.pack(fill="x")
        grid.columnconfigure(0, weight=1)
        grid.columnconfigure(1, weight=1)
        self.stat = {}
        for i, (k, lab) in enumerate(
            (
                ("cost", "TOTAL COST"),
                ("profit", "PROFIT"),
                ("margin", "MARGIN"),
                ("pph", "PROFIT PER HOUR"),
            )
        ):
            cell = tk.Frame(grid, bg=C["side"])
            cell.grid(row=i // 2, column=i % 2, sticky="w", pady=px(4))
            tk.Label(cell, text=lab, bg=C["side"], fg="#93A4BB", font=(FONT, 8, "bold")).pack(
                anchor="w"
            )
            self.stat[k] = tk.Label(
                cell, text="", bg=C["side"], fg="white", font=(FONT, 14, "bold")
            )
            self.stat[k].pack(anchor="w")

        b = self.card(right, "Compare with your usual quote")
        self.frow(
            b, [dict(store="J", key="gut", label="Your usual quote, before tax", prefix="$", width=10)]
        )
        self.verd = tk.Frame(b, bg=C["neutral_bg"])
        self.verd.pack(fill="x")
        self.lbl_vhead = tk.Label(
            self.verd,
            text="",
            bg=C["neutral_bg"],
            fg=C["ink"],
            font=(FONT, 10, "bold"),
            anchor="w",
            justify="left",
        )
        autowrap(self.lbl_vhead)
        self.lbl_vhead.pack(fill="x", padx=px(12), pady=(px(10), 0))
        self.lbl_vbody = tk.Label(
            self.verd,
            text="",
            bg=C["neutral_bg"],
            fg=C["ink"],
            font=(FONT, 10),
            anchor="w",
            justify="left",
        )
        autowrap(self.lbl_vbody)
        self.lbl_vbody.pack(fill="x", padx=px(12), pady=(px(2), px(10)))

        b = self.card(right, "Where the price goes", pad_bottom=0)
        self.bar = tk.Canvas(b, height=px(14), bg=C["card"], highlightthickness=0)
        self.bar.pack(fill="x", pady=(0, px(8)))
        self.bar.bind("<Configure>", lambda e: self.draw_bar())
        tbl = tk.Frame(b, bg=C["card"])
        tbl.pack(fill="x")
        tbl.columnconfigure(1, weight=1)
        self.brk = {}
        rows = [
            ("labour", "Labour", "#2457E6"),
            ("travel", "Travel", "#0E8A8A"),
            ("materials", "Materials & supplies", "#C27A0E"),
            ("other", "Other costs", "#7A4FBF"),
            ("direct", "Direct costs", None),
            ("overhead", "Overhead", "#8393A3"),
            ("cost", "Total cost", None),
            ("profit", "Profit", "#12A266"),
            ("price", "Quote price", None),
        ]
        for i, (k, lab, col) in enumerate(rows):
            strong = col is None
            if strong:
                tk.Frame(tbl, bg=C["line"], height=1).grid(
                    row=i * 2, column=0, columnspan=4, sticky="ew"
                )
            else:
                tk.Frame(tbl, bg=col, width=px(10), height=px(10)).grid(
                    row=i * 2 + 1, column=0, sticky="w", padx=(0, px(8))
                )
            f = (FONT, 10, "bold") if strong else (FONT, 10)
            tk.Label(tbl, text=lab, bg=C["card"], fg=C["ink"], font=f, anchor="w").grid(
                row=i * 2 + 1, column=1, sticky="w", pady=px(3)
            )
            a = tk.Label(tbl, text="", bg=C["card"], fg=C["ink"], font=f, anchor="e")
            a.grid(row=i * 2 + 1, column=2, sticky="e", padx=(px(10), 0))
            p = tk.Label(
                tbl, text="", bg=C["card"], fg=C["muted"], font=(FONT, 9), width=6, anchor="e"
            )
            p.grid(row=i * 2 + 1, column=3, sticky="e")
            self.brk[k] = (a, p)

        return page

    def _page_doc(self, parent):
        page = tk.Frame(parent, bg=C["bg"])
        self.lbl_dochead = self.head(
            page,
            "Quote & invoice",
            "Quote",
            [
                lambda p: Btn(p, "Copy as text", self.copy_doc),
                lambda p: Btn(p, "Save as PDF…", self.save_pdf, "primary"),
            ],
        )
        body = tk.Frame(page, bg=C["bg"])
        body.pack(fill="both", expand=True)
        body.columnconfigure(0, weight=1)
        body.columnconfigure(1, minsize=px(380))
        body.rowconfigure(0, weight=1)

        left = ScrollFrame(body, C["bg"])
        left.grid(row=0, column=0, sticky="nsew")
        self.doc_left = left
        self._doc_w = 0
        left.canvas.bind("<Configure>", self._doc_resized, add="+")
        right = ScrollFrame(body, C["bg"])
        right.grid(row=0, column=1, sticky="nsew", padx=(px(20), 0))

        paper = tk.Frame(
            left.inner, bg=C["card"], highlightthickness=1, highlightbackground=C["line"]
        )
        paper.pack(anchor="n", pady=(0, px(14)))
        tk.Frame(paper, bg=C["accent"], height=px(6)).pack(fill="x")
        self.pw = px(520)
        self.meas = tkfont.Font(family=FONT, size=10).measure("0")
        self.preview = tk.Text(
            paper,
            wrap="word",
            font=(FONT, 10),
            bg=C["card"],
            fg=C["ink"],
            relief="flat",
            bd=0,
            highlightthickness=0,
            padx=px(36),
            pady=px(32),
            width=60,
            height=30,
            cursor="arrow",
            state="disabled",
        )
        self.preview.pack()
        t = self.preview
        t.tag_configure("biz", font=(FONT, 14, "bold"))
        t.tag_configure("title", font=(FONT, 16, "bold"))
        t.tag_configure("num", font=(FONT, 10), foreground=C["muted"])
        t.tag_configure("sm", font=(FONT, 9), foreground=C["muted"])
        t.tag_configure("lab", font=(FONT, 8, "bold"), foreground=C["muted"], spacing1=px(6))
        t.tag_configure("name", font=(FONT, 11, "bold"))
        t.tag_configure("mlab", font=(FONT, 9), foreground=C["muted"])
        t.tag_configure("mval", font=(FONT, 9, "bold"))
        t.tag_configure("jt", font=(FONT, 12, "bold"), spacing1=px(10))
        t.tag_configure("scope", font=(FONT, 9), foreground=C["muted"])
        t.tag_configure(
            "th",
            font=(FONT, 8, "bold"),
            foreground=C["muted"],
            background=C["soft"],
            spacing1=px(7),
            spacing3=px(7),
            lmargin1=px(8),
        )
        t.tag_configure("row", spacing1=px(8), spacing3=px(8), lmargin1=px(8))
        t.tag_configure("amt", font=(FONT, 10, "bold"))
        t.tag_configure("tot", font=(FONT, 10), foreground=C["muted"], spacing1=px(3), spacing3=px(3))
        t.tag_configure("totS", font=(FONT, 11, "bold"), spacing1=px(6), spacing3=px(3))
        t.tag_configure(
            "hl", font=(FONT, 11, "bold"), background=C["accent"], foreground="#FFFFFF"
        )
        t.tag_configure("note", font=(FONT, 9), foreground=C["muted"], spacing3=px(2))
        t.tag_configure("pay", font=(FONT, 10))

        R_ = right.inner
        b = self.card(R_, "Document")
        self.doc_type = tk.StringVar(value="quote")
        self.doc_type.trace_add("write", lambda *_: self.on_change())
        seg = Seg(b, self.doc_type, [("quote", "Quote"), ("invoice", "Invoice")])
        seg.pack(anchor="w", pady=(0, px(12)))
        self.row_no = tk.Frame(b, bg=C["card"])
        self.row_no.pack(fill="x", pady=(0, px(12)))
        self.f_qno = self.field(self.row_no, "J", "quoteNo", "Quote number", width=12)
        self.f_ino = self.field(self.row_no, "J", "invoiceNo", "Invoice number", width=12)
        self.f_date = self.field(
            self.row_no, "J", "issueDate", "Issue date (YYYY-MM-DD)", width=12
        )
        self.f_date.pack(side="right", fill="x", expand=True, padx=(px(14), 0))
        self.f_paid = self.field(
            b, "J", "paid", "Amount already received, including tax", prefix="$", width=10
        )
        self.itemised = tk.BooleanVar()
        self.itemised.trace_add("write", lambda *_: self.on_change())
        self.chk_item = tk.Frame(b, bg=C["card"])
        self.chk_item.pack(fill="x")
        ttk.Checkbutton(
            self.chk_item,
            text="Show itemised lines",
            variable=self.itemised,
            style="Card.TCheckbutton",
        ).pack(anchor="w")
        autowrap(
            tk.Label(
                self.chk_item,
                text=(
                    "Splits the price into labour, materials and other costs. "
                    "Overhead and profit are spread across the lines, so your costs stay private."
                ),
                bg=C["card"],
                fg=C["muted"],
                font=(FONT, 9),
                justify="left",
                anchor="w",
            )
        ).pack(fill="x", padx=(px(22), 0))

        b = self.card(R_, "Customer")
        self.frow(b, [dict(store="J", key="custEmail", label="Customer email", width=24)])
        self.frow(
            b,
            [
                dict(
                    store="J",
                    key="custAddress",
                    label="Customer address",
                    text=True,
                    height=2,
                    width=24,
                )
            ],
            last=True,
        )

        b = self.card(
            R_,
            "Send to customer",
            "Save the PDF, then attach it to your email.",
            pad_bottom=0,
        )
        bb = tk.Frame(b, bg=C["card"])
        bb.pack(fill="x", pady=(0, px(12)))
        Btn(bb, "Save as PDF…", self.save_pdf, "primary").pack(side="left")
        self.frow(b, [dict(store="J", key="emailSubject", label="Email subject", width=24)])
        self.frow(
            b, [dict(store="J", key="emailBody", label="Email message", text=True, height=9, width=24)]
        )
        bb2 = tk.Frame(b, bg=C["card"])
        bb2.pack(fill="x")
        Btn(bb2, "Open in email app", self.open_email).pack(side="left")
        Btn(bb2, "Copy message", self.copy_msg).pack(side="left", padx=px(6))
        Btn(bb2, "Reset", self.reset_msg).pack(side="left")
        self.lbl_doc_status = autowrap(
            tk.Label(
                b, text="", bg=C["card"], fg=C["muted"], font=(FONT, 9), justify="left", anchor="w"
            )
        )
        self.lbl_doc_status.pack(fill="x", pady=(px(10), 0))
        return page

    def _page_library(self, parent):
        page = tk.Frame(parent, bg=C["bg"])
        self.head(
            page,
            "Job library",
            "Saved jobs",
            [
                lambda p: Btn(p, "Save current to library", self.save_to_library, "primary"),
                lambda p: Btn(p, "New blank job", self.new_blank),
            ],
        )

        # search + actions
        top = tk.Frame(page, bg=C["bg"])
        top.pack(fill="x", pady=(0, px(12)))
        self.lib_search = tk.StringVar()
        self.lib_search.trace_add("write", lambda *_: self.refresh_library())
        search_box = tk.Frame(
            top, bg=C["card"], highlightthickness=1, highlightbackground=C["field"]
        )
        search_box.pack(side="left", fill="x", expand=True)
        tk.Entry(
            search_box,
            textvariable=self.lib_search,
            relief="flat",
            bd=0,
            font=(FONT, 11),
            bg=C["card"],
            fg=C["ink"],
            insertbackground=C["ink"],
            highlightthickness=0,
        ).pack(fill="x", ipady=px(8), padx=px(12))
        tk.Label(
            top,
            text="  Search by title, customer or notes",
            bg=C["bg"],
            fg=C["muted"],
            font=(FONT, 9),
        ).pack(side="left", padx=(px(8), 0))

        body = tk.Frame(page, bg=C["bg"])
        body.pack(fill="both", expand=True)

        # tree
        cols = ("name", "client", "price", "saved")
        self.lib_tree = ttk.Treeview(
            body, columns=cols, show="headings", selectmode="browse", height=18
        )
        self.lib_tree.heading("name", text="Job / Name", anchor="w")
        self.lib_tree.heading("client", text="Customer", anchor="w")
        self.lib_tree.heading("price", text="Price (excl. tax)", anchor="e")
        self.lib_tree.heading("saved", text="Saved", anchor="w")
        self.lib_tree.column("name", width=px(320), anchor="w")
        self.lib_tree.column("client", width=px(180), anchor="w")
        self.lib_tree.column("price", width=px(130), anchor="e")
        self.lib_tree.column("saved", width=px(160), anchor="w")
        self.lib_tree.pack(side="left", fill="both", expand=True)

        sb = ttk.Scrollbar(body, orient="vertical", command=self.lib_tree.yview)
        sb.pack(side="right", fill="y")
        self.lib_tree.configure(yscrollcommand=sb.set)

        # action bar
        bar = tk.Frame(page, bg=C["bg"])
        bar.pack(fill="x", pady=(px(12), 0))
        Btn(bar, "Load into current job", self.lib_load, "primary").pack(side="left")
        Btn(bar, "Duplicate", self.lib_duplicate).pack(side="left", padx=px(8))
        Btn(bar, "Delete", self.lib_delete, "danger").pack(side="left")
        self.lbl_lib_count = tk.Label(
            bar, text="", bg=C["bg"], fg=C["muted"], font=(FONT, 9)
        )
        self.lbl_lib_count.pack(side="right")

        self.lib_tree.bind("<Double-1>", lambda e: self.lib_load())
        return page

    def _page_settings(self, parent):
        page = tk.Frame(parent, bg=C["bg"])
        self.head(
            page,
            "Business settings",
            "Your rates and business details",
            [lambda p: Btn(p, "Restore example settings", self.reset_settings)],
        )
        sf = ScrollFrame(page, C["bg"])
        sf.pack(fill="both", expand=True)
        cols = tk.Frame(sf.inner, bg=C["bg"])
        cols.pack(fill="both", expand=True)
        cols.columnconfigure(0, weight=1, uniform="c")
        cols.columnconfigure(1, weight=1, uniform="c")
        a = tk.Frame(cols, bg=C["bg"])
        a.grid(row=0, column=0, sticky="new", padx=(0, px(10)))
        b2 = tk.Frame(cols, bg=C["bg"])
        b2.grid(row=0, column=1, sticky="new", padx=(px(10), 0))

        b = self.card(a, "Your business", "Printed at the top of every quote and invoice.")
        self.frow(b, [dict(store="S", key="bizName", label="Business name", width=20)])
        self.frow(
            b,
            [
                dict(store="S", key="abn", label="ABN or tax number", width=12),
                dict(store="S", key="phone", label="Phone", width=12),
            ],
        )
        self.frow(b, [dict(store="S", key="bizEmail", label="Business email", width=20)])
        self.frow(
            b, [dict(store="S", key="address", label="Business address", text=True, height=2, width=20)]
        )
        self.frow(
            b,
            [
                dict(
                    store="S",
                    key="currency",
                    label="Currency code",
                    hint="AUD, NZD, USD, CAD, GBP, EUR, JPY, SGD, HKD, CHF, INR",
                    width=8,
                )
            ],
            last=True,
        )

        b = self.card(a, "Labour cost")
        self.frow(
            b,
            [
                dict(
                    store="S",
                    key="labourRate",
                    label="Hourly labour cost, per person",
                    prefix="$",
                    unit="per hour",
                    width=8,
                    hint=(
                        "What one person costs you per hour, including super, leave, "
                        "insurance and payroll costs. Count your own time at what you "
                        "would pay someone to do it."
                    ),
                )
            ],
            last=True,
        )

        b = self.card(a, "Overhead allowance")
        self.ov_mode = tk.StringVar(value="percent")
        self.ov_mode.trace_add("write", lambda *_: self.on_change())
        Seg(
            b,
            self.ov_mode,
            [("percent", "% of direct costs"), ("hourly", "Per labour hour")],
        ).pack(anchor="w", pady=(0, px(12)))
        self.row_ovp = self.frow(
            b,
            [
                dict(
                    store="S",
                    key="overheadPct",
                    label="Overhead as a share of direct costs",
                    unit="%",
                    width=8,
                    hint=(
                        "A year of insurance, vehicle costs, software, phone, admin and "
                        "accounting, divided by a year of direct job costs."
                    ),
                )
            ],
            last=True,
        )
        self.row_ovh = self.frow(
            b,
            [
                dict(
                    store="S",
                    key="overheadHourly",
                    label="Overhead per labour hour",
                    prefix="$",
                    unit="per hour",
                    width=8,
                    hint=(
                        "A year of overhead divided by the labour hours you work in a year. "
                        "Travel hours count."
                    ),
                )
            ],
            last=True,
        )

        b = self.card(b2, "Profit & pricing")
        self.frow(
            b,
            [
                dict(store="S", key="margin", label="Target profit margin", unit="%", width=6),
                dict(store="S", key="minPrice", label="Minimum job price", prefix="$", width=8),
            ],
        )
        self.frow(
            b,
            [
                dict(
                    store="S",
                    key="roundTo",
                    label="Round quote up to",
                    unit="$ step",
                    hint="Use 0 for no rounding, or 1, 5, 10 or 50.",
                    width=6,
                )
            ],
        )
        self.lbl_margin = autowrap(
            tk.Label(
                b,
                text="",
                bg=C["neutral_bg"],
                fg=C["ink"],
                font=(FONT, 9),
                justify="left",
                anchor="w",
                padx=px(10),
                pady=px(8),
            ),
            24,
        )
        self.lbl_margin.pack(fill="x")

        b = self.card(b2, "Travel")
        self.frow(
            b,
            [
                dict(
                    store="S",
                    key="travelRate",
                    label="Vehicle cost per kilometre",
                    prefix="$",
                    unit="per km",
                    width=8,
                    hint="Fuel, servicing, tyres and depreciation. Travel time is charged at your labour cost.",
                )
            ],
            last=True,
        )

        b = self.card(b2, "Tax")
        self.tax_on = tk.BooleanVar()
        self.tax_on.trace_add("write", lambda *_: self.on_change())
        ttk.Checkbutton(
            b,
            text="Add tax to quotes and invoices",
            variable=self.tax_on,
            style="Card.TCheckbutton",
        ).pack(anchor="w", pady=(0, px(12)))
        self.frow(
            b,
            [
                dict(store="S", key="taxName", label="Tax name", width=8),
                dict(store="S", key="taxRate", label="Tax rate", unit="%", width=6),
            ],
            last=True,
        )

        b = self.card(b2, "Terms & payment")
        self.frow(
            b,
            [
                dict(store="S", key="validDays", label="Quote valid for", unit="days", width=6),
                dict(store="S", key="depositPct", label="Deposit to book", unit="%", width=6),
                dict(store="S", key="payTerms", label="Invoice terms", unit="days", width=6),
            ],
        )
        self.frow(
            b,
            [
                dict(
                    store="S",
                    key="payDetails",
                    label="Payment details, printed on invoices",
                    text=True,
                    height=3,
                    width=20,
                )
            ],
        )
        self.frow(
            b, [dict(store="S", key="docNote", label="Closing note", width=20)], last=True
        )

        b = self.card(
            b2,
            "Your data",
            "Everything is stored on this computer. Nothing is sent anywhere.",
            pad_bottom=0,
        )
        autowrap(
            tk.Label(
                b,
                text=DATA_FILE,
                bg=C["neutral_bg"],
                fg=C["ink"],
                font=(MONO, 9),
                justify="left",
                anchor="w",
                padx=px(10),
                pady=px(8),
            ),
            24,
        ).pack(fill="x")
        bb = tk.Frame(b, bg=C["card"])
        bb.pack(fill="x", pady=(px(10), 0))
        Btn(bb, "Open data folder", self.open_data_folder).pack(side="left")
        Btn(bb, "Export backup…", self.export_backup).pack(side="left", padx=px(6))
        Btn(bb, "Import backup…", self.import_backup).pack(side="left")
        return page

    # ----- state <-> widgets -----------------------------------------------

    def fill_all(self):
        self._busy = True
        for (store, key), (w, kind) in self.vars.items():
            val = (self.S if store == "S" else self.J).get(key, "")
            if kind == "text":
                w.delete("1.0", "end")
                w.insert("1.0", str(val))
            else:
                w.set("" if val is None else self._show(val))
        self.doc_type.set(self.J.get("docType", "quote"))
        self.itemised.set(bool(self.J.get("itemised")))
        self.ov_mode.set(self.S.get("overheadMode", "percent"))
        self.tax_on.set(bool(self.S.get("taxOn")))
        self._busy = False
        self.fill_trees()

    @staticmethod
    def _show(v):
        if isinstance(v, float) and v.is_integer():
            return str(int(v))
        return str(v)

    def fill_trees(self):
        for tree, key, cols in (
            (self.tree_mat, "materials", ("d", "q", "c")),
            (self.tree_oth, "other", ("d", "a")),
        ):
            tree.delete(*tree.get_children())
            for row in self.J.get(key, []):
                vals = [row.get(c, "") for c in cols]
                vals = [self._show(v) if not isinstance(v, str) else v for v in vals]
                tree.insert("", "end", values=vals)
            tree.config(height=max(2, min(6, len(self.J.get(key, [])))))

    def collect(self):
        for (store, key), (w, kind) in self.vars.items():
            target = self.S if store == "S" else self.J
            if kind == "text":
                target[key] = w.get("1.0", "end").rstrip("\n")
            else:
                raw = w.get()
                target[key] = num(raw) if key in NUMERIC_KEYS else raw
        self.J["docType"] = self.doc_type.get()
        self.J["itemised"] = self.itemised.get()
        self.S["overheadMode"] = self.ov_mode.get()
        self.S["taxOn"] = self.tax_on.get()
        # light validation
        self.J["people"] = max(0, self.J.get("people", 0))
        self.J["hours"] = max(0.0, self.J.get("hours", 0))
        self.S["margin"] = clamp(self.S.get("margin", 0), 0, 90)

    def on_text(self, key):
        if key == "emailBody":
            self.J["emailEdited"] = True
        self.on_change()

    def on_change(self):
        if self._busy:
            return
        self.collect()
        self.refresh(user_edit=True)

    def add_row(self, key, ents):
        d = ents["d"].get().strip()
        if key == "materials":
            row = {"d": d, "q": num(ents["q"].get()) or 1, "c": num(ents["c"].get())}
            has_value = row["c"] > 0
        else:
            row = {"d": d, "a": num(ents["a"].get())}
            has_value = row["a"] > 0
        if not d and not has_value:
            return
        self.J.setdefault(key, []).append(row)
        for e in ents.values():
            e.delete(0, "end")
        ents["d"].focus_set()
        self.fill_trees()
        self.refresh()

    def remove_row(self, key, tree):
        sel = tree.selection()
        if not sel:
            return
        del self.J[key][tree.index(sel[0])]
        self.fill_trees()
        self.refresh()

    # ----- computed display ------------------------------------------------

    def refresh(self, user_edit=False):
        if not self.vars:
            return
        if not user_edit:
            self.collect()
        S, J = self.S, self.J
        r = calc(S, J)
        self.r = r
        M = lambda v: money(S, v)
        sym = SYMBOLS.get(str(S.get("currency", "AUD")).upper(), "$")
        for lbl in self._cur_labels:
            try:
                lbl.config(text=sym)
            except tk.TclError:
                pass

        tn = S.get("taxName") or "Tax"
        self.lbl_side_biz.config(text=S.get("bizName") or "Your business")
        self.lbl_side_lib.config(
            text=f"{len(self.library)} job{'s' if len(self.library) != 1 else ''} in library"
        )
        self.lbl_jobhead.config(text=J.get("title") or "New job")

        if J.get("sample"):
            try:
                self.banner.pack(fill="x", pady=(0, px(14)), before=self.banner.master.winfo_children()[-1])
            except Exception:
                self.banner.pack(fill="x", pady=(0, px(14)))
        else:
            self.banner.pack_forget()

        self.lbl_priceLab.config(
            text="RECOMMENDED QUOTE"
            + (f" (EXCL. {tn.upper()})" if S.get("taxOn") else "")
        )
        self.lbl_price.config(text=M(r["price"]))
        self.lbl_taxline.config(
            text=(f"{tn} {M(r['tax'])}   |   Total {M(r['total'])}")
            if S.get("taxOn")
            else "Total " + M(r["total"])
        )
        flag = ""
        if r["min_applied"]:
            flag = (
                f"Your minimum job price of {M(pos(S.get('minPrice')))} applies. "
                f"The costed price was {M(r['raw'])}."
            )
        elif r["rounded"]:
            flag = (
                f"Rounded up from {M(r['raw'])} to the next "
                f"{M(pos(S.get('roundTo'))).replace('.00', '')}."
            )
        self.lbl_flag.config(text=flag)

        self.stat["cost"].config(text=M(r["cost"]))
        self.stat["profit"].config(text=M(r["profit"]))
        self.stat["margin"].config(
            text=(f"{r['margin'] * 100:.1f}%") if r["price"] > 0 else "0%"
        )
        self.stat["pph"].config(text=M(r["pph"]))

        self.chip_labour.config(text=M(r["labour"]))
        self.chip_travel.config(text=M(r["travel"]))
        self.chip_mat.config(text=M(r["materials"]))
        self.chip_oth.config(text=M(r["other"]))

        self.lbl_labour.config(
            text=(
                f"{r['on_site']:.2f} hours on site at {M(pos(S.get('labourRate')))} per hour"
                if r["on_site"]
                else "Enter the people and hours on site."
            )
        )
        self.lbl_travel.config(
            text=(
                f"Vehicle {M(r['vehicle'])} plus travel time {M(r['travel_time'])}. "
                "Travel time is paid to every person."
            )
        )

        vals = {
            "labour": r["labour"],
            "travel": r["travel"],
            "materials": r["materials"],
            "other": r["other"],
            "direct": r["direct"],
            "overhead": r["overhead"],
            "cost": r["cost"],
            "profit": r["profit"],
            "price": r["price"],
        }
        for k, (a, p) in self.brk.items():
            a.config(text=M(vals[k]))
            p.config(text=(f"{vals[k] / r['price'] * 100:.1f}%") if r["price"] > 0 else "")

        self.draw_bar()
        self.verdict(r)

        mm = clamp(num(S.get("margin")), 0, 90) / 100
        self.lbl_margin.config(
            text=(
                f"At a {mm * 100:.1f}% margin, a job that costs {M(100)} is quoted at "
                f"{M(100 / (1 - mm) if mm < 1 else 0)}. "
                f"That is a {mm / (1 - mm) * 100 if mm < 1 else 0:.1f}% markup on cost."
            )
        )

        hourly = S.get("overheadMode") == "hourly"
        if hourly:
            self.row_ovp.pack_forget()
            self.row_ovh.pack(fill="x")
        else:
            self.row_ovh.pack_forget()
            self.row_ovp.pack(fill="x")

        m = build_model(S, J, r)
        self.model = m
        inv = m["inv"]
        self.lbl_dochead.config(text=f"{m['title']} {m['number']}")
        for f in (self.f_qno, self.f_ino, self.f_date):
            f.pack_forget()
        (self.f_ino if inv else self.f_qno).pack(side="left", fill="x", expand=True)
        self.f_date.pack(side="right", fill="x", expand=True, padx=(px(14), 0))
        if inv:
            self.f_paid.pack(fill="x", pady=(0, px(12)), before=self.chk_item)
        else:
            self.f_paid.pack_forget()

        self.render_preview(m)

        if not J.get("emailEdited"):
            subj, body = email_template(S, J, m)
            self._busy = True
            self.vars[("J", "emailSubject")][0].set(subj)
            tb = self.vars[("J", "emailBody")][0]
            tb.delete("1.0", "end")
            tb.insert("1.0", body)
            J["emailSubject"], J["emailBody"] = subj, body
            self._busy = False

        save_data(S, J, self.library)
        self.lbl_saved.config(
            text=f"All changes saved  {dt.datetime.now().strftime('%H:%M:%S')}"
        )

    def _doc_resized(self, e):
        if abs(e.width - self._doc_w) > 6 and self.model:
            self._doc_w = e.width
            self.after(60, lambda: self.render_preview(self.model))

    def render_preview(self, m):
        t = self.preview
        avail = self.doc_left.canvas.winfo_width()
        self.pw = px(520) if avail <= 1 else max(px(340), min(px(560), avail - px(72) - px(8)))
        R = self.pw
        t.config(width=int(R / self.meas) + 2)
        t.tag_configure("tR", tabs=(R, "right"))
        t.tag_configure("tM", tabs=(int(R * 0.5), "left", R, "right"))
        t.tag_configure("tT", tabs=(int(R * 0.42), "left", R, "right"))
        t.tag_configure(
            "tH", tabs=(int(R * 0.42), "left", R, "right"), spacing1=px(8), spacing3=px(8)
        )
        t.config(state="normal")
        for w in list(t.winfo_children()):
            w.destroy()
        t.delete("1.0", "end")

        def put(text, *tags):
            t.insert("end", text, tags)

        def rule():
            t.window_create("end", window=tk.Frame(t, bg=C["line"], width=R, height=1))
            put("\n", "sm")

        put(m["bizName"], "biz", "tR")
        put("\t" + m["title"].upper() + "\n", "title", "tR")
        for i, ln in enumerate(m["bizLines"]):
            put(ln, "sm", "tR")
            if i == 0:
                put("\t" + m["number"], "num", "tR")
            put("\n", "sm", "tR")
        if not m["bizLines"]:
            put("\t" + m["number"] + "\n", "num", "tR")
        put("\n", "sm")
        rule()

        left = [("lab", m["billLabel"].upper()), ("name", m["billName"])] + [
            ("sm", x) for x in m["billLines"]
        ]
        for i in range(max(len(left), len(m["meta"]))):
            tag, txt = left[i] if i < len(left) else ("sm", "")
            put(txt, tag, "tM")
            if i < len(m["meta"]):
                put("\t", "tM")
                put(m["meta"][i][0], "mlab", "tM")
                put("\t", "tM")
                put(m["meta"][i][1], "mval", "tM")
            put("\n", "sm", "tM")

        put(m["jobTitle"] + "\n", "jt")
        if m["scope"]:
            put(m["scope"] + "\n", "scope")
        put("\n", "sm")
        put("DESCRIPTION", "th", "tR")
        put(f"\tAMOUNT ({m['currency']})\n", "th", "tR")
        for desc, amt in m["lines"]:
            put(desc, "row", "tR")
            put("\t" + amt + "\n", "row", "amt", "tR")
            rule()
        put("\n", "sm")
        for label, val, strong in m["totals"]:
            put("\t" + label + "\t" + val + "\n", "totS" if strong else "tot", "tT")
        if m["highlight"]:
            put("\n", "sm")
            put("\t", "tH")
            put(
                " " + m["highlight"][0] + "\t" + m["highlight"][1] + "\n",
                "hl",
                "tH",
            )
        put("\n", "sm")
        if m["payment"]:
            put("PAYMENT DETAILS\n", "lab")
            put(m["payment"] + "\n", "pay")
            put("\n", "sm")
        rule()
        for n in m["notes"]:
            put(n + "\n", "note")

        t.update_idletasks()
        try:
            n = t.count("1.0", "end", "displaylines")[0]
        except Exception:
            n = 40
        t.config(height=n + 1, state="disabled")

    def draw_bar(self):
        cv = self.bar
        cv.delete("all")
        r = self.r
        if not r or r["price"] <= 0:
            return
        w = max(cv.winfo_width(), 10)
        x = 0.0
        for k, col in SEG_COLORS:
            seg = max(r[k], 0) / r["price"] * w
            if seg > 0.5:
                cv.create_rectangle(x, 0, x + seg - 2, px(14), fill=col, outline="")
            x += seg

    def verdict(self, r):
        gut = pos(self.J.get("gut"))
        M = lambda v: money(self.S, v)
        tone = "neutral"
        if r["cost"] <= 0:
            head, body = (
                "Add the job costs first",
                "Once the job has labour, travel or materials, this compares your usual price with what the job needs.",
            )
        elif gut <= 0:
            head, body = (
                "Enter your usual price",
                "Type what you would have quoted by gut feel to see what it earns you on this job.",
            )
        elif gut < r["direct"]:
            tone, head = "bad", "You would lose money on this job"
            body = (
                f"{M(gut)} does not cover the {M(r['direct'])} it costs you to do the work. "
                f"You would be {M(r['direct'] - gut)} out of pocket before any overhead."
            )
        elif gut < r["cost"]:
            tone, head = "bad", "Overhead is not covered"
            body = (
                f"{M(gut)} pays for the work but leaves {M(r['cost'] - gut)} of overhead unpaid. "
                "The job earns no profit."
            )
        elif gut < r["price"] - 0.004:
            gp = gut - r["cost"]
            tone, head = "warn", "Below your target margin"
            body = (
                f"{M(gut)} leaves {M(gp)} profit, a {gp / gut * 100:.1f}% margin against your "
                f"{r['target'] * 100:.1f}% target. It is {M(r['price'] - gut)} short of the recommended quote."
            )
        else:
            gp = gut - r["cost"]
            tone, head = "good", "At or above your target"
            body = f"{M(gut)} leaves {M(gp)} profit, a {gp / gut * 100:.1f}% margin."

        bg = {
            "neutral": C["neutral_bg"],
            "bad": C["bad_bg"],
            "warn": C["warn_bg"],
            "good": C["good_bg"],
        }[tone]
        fg = {
            "neutral": C["ink"],
            "bad": C["bad"],
            "warn": C["warn"],
            "good": C["good"],
        }[tone]
        self.verd.config(bg=bg)
        self.lbl_vhead.config(text=head, bg=bg, fg=fg)
        self.lbl_vbody.config(text=body, bg=bg)

    # ----- library actions -------------------------------------------------

    def refresh_library(self):
        self.lib_tree.delete(*self.lib_tree.get_children())
        q = (self.lib_search.get() or "").strip().lower()
        shown = 0
        # newest first
        items = sorted(
            self.library,
            key=lambda x: x.get("saved_at") or "",
            reverse=True,
        )
        for entry in items:
            job = entry.get("job") or {}
            name = entry.get("name") or job.get("title") or "Untitled"
            client = job.get("client") or ""
            # quick price estimate for display
            try:
                price = calc(self.S, job)["price"]
            except Exception:
                price = 0.0
            saved = entry.get("saved_at") or ""
            if len(saved) >= 16:
                saved = saved[:16].replace("T", " ")
            hay = f"{name} {client} {job.get('scope', '')} {job.get('title', '')}".lower()
            if q and q not in hay:
                continue
            self.lib_tree.insert(
                "",
                "end",
                iid=entry.get("id") or new_id(),
                values=(name, client, money(self.S, price), saved),
            )
            shown += 1
        self.lbl_lib_count.config(
            text=f"{shown} of {len(self.library)} job{'s' if len(self.library) != 1 else ''}"
        )

    def _selected_library_entry(self) -> Optional[Dict]:
        sel = self.lib_tree.selection()
        if not sel:
            return None
        iid = sel[0]
        for entry in self.library:
            if entry.get("id") == iid:
                return entry
        return None

    def save_to_library(self):
        self.collect()
        name = (self.J.get("title") or self.J.get("client") or "Untitled job").strip()
        # simple prompt via dialog
        dlg = tk.Toplevel(self)
        dlg.title("Save to library")
        dlg.configure(bg=C["bg"])
        dlg.transient(self)
        dlg.grab_set()
        dlg.resizable(False, False)
        tk.Label(
            dlg,
            text="Name for this saved job",
            bg=C["bg"],
            fg=C["ink"],
            font=(FONT, 11, "bold"),
        ).pack(padx=px(20), pady=(px(18), px(6)), anchor="w")
        var = tk.StringVar(value=name)
        e = tk.Entry(
            dlg,
            textvariable=var,
            font=(FONT, 12),
            width=40,
            relief="flat",
            highlightthickness=1,
            highlightbackground=C["field"],
        )
        e.pack(padx=px(20), pady=(0, px(14)), ipady=px(6))
        e.select_range(0, "end")
        e.focus_set()

        def do_save():
            n = var.get().strip() or name
            entry = {
                "id": new_id(),
                "saved_at": now_iso(),
                "name": n,
                "job": deepcopy(self.J),
            }
            entry["job"]["library_name"] = n
            entry["job"]["saved_at"] = entry["saved_at"]
            self.library.append(entry)
            save_data(self.S, self.J, self.library)
            self.lbl_side_lib.config(
                text=f"{len(self.library)} job{'s' if len(self.library) != 1 else ''} in library"
            )
            dlg.destroy()
            self.say(f"Saved “{n}” to library.")
            if self.current == "lib":
                self.refresh_library()

        bf = tk.Frame(dlg, bg=C["bg"])
        bf.pack(fill="x", padx=px(20), pady=(0, px(18)))
        Btn(bf, "Cancel", dlg.destroy).pack(side="right")
        Btn(bf, "Save", do_save, "primary").pack(side="right", padx=(0, px(8)))
        dlg.bind("<Return>", lambda e: do_save())
        dlg.bind("<Escape>", lambda e: dlg.destroy())
        # centre
        dlg.update_idletasks()
        x = self.winfo_rootx() + (self.winfo_width() - dlg.winfo_width()) // 2
        y = self.winfo_rooty() + (self.winfo_height() - dlg.winfo_height()) // 3
        dlg.geometry(f"+{x}+{y}")

    def lib_load(self):
        entry = self._selected_library_entry()
        if not entry:
            messagebox.showinfo("Job library", "Select a job first.")
            return
        if not messagebox.askyesno(
            "Load job",
            "Replace the current job with the selected library job?\n\n"
            "Unsaved changes to the current job will be lost unless you saved it to the library.",
        ):
            return
        self.J = deepcopy(entry.get("job") or blank_job())
        self.J.setdefault("materials", [])
        self.J.setdefault("other", [])
        self.J["emailEdited"] = False
        self.fill_all()
        self.refresh()
        self.show("job")
        self.say(f"Loaded “{entry.get('name') or 'job'}”.")

    def lib_duplicate(self):
        entry = self._selected_library_entry()
        if not entry:
            messagebox.showinfo("Job library", "Select a job first.")
            return
        job = deepcopy(entry.get("job") or {})
        job["id"] = new_id()
        name = (entry.get("name") or job.get("title") or "Untitled") + " (copy)"
        new_entry = {
            "id": new_id(),
            "saved_at": now_iso(),
            "name": name,
            "job": job,
        }
        self.library.append(new_entry)
        save_data(self.S, self.J, self.library)
        self.refresh_library()
        self.say(f"Duplicated as “{name}”.")

    def lib_delete(self):
        entry = self._selected_library_entry()
        if not entry:
            messagebox.showinfo("Job library", "Select a job first.")
            return
        name = entry.get("name") or "this job"
        if not messagebox.askyesno("Delete job", f"Permanently delete “{name}” from the library?"):
            return
        self.library = [e for e in self.library if e.get("id") != entry.get("id")]
        save_data(self.S, self.J, self.library)
        self.refresh_library()
        self.lbl_side_lib.config(
            text=f"{len(self.library)} job{'s' if len(self.library) != 1 else ''} in library"
        )
        self.say(f"Deleted “{name}”.")

    # ----- actions ---------------------------------------------------------

    def new_blank(self):
        if messagebox.askyesno("New blank job", "Clear the current job and start a new one?"):
            self.J = blank_job()
            self.fill_all()
            self.refresh()
            self.show("job")

    def load_sample(self):
        if messagebox.askyesno("Load sample job", "Replace the current job with the sample job?"):
            self.J = sample_job()
            self.fill_all()
            self.refresh()
            self.show("job")

    def reset_settings(self):
        if messagebox.askyesno(
            "Restore example settings", "Replace all business settings with the example values?"
        ):
            self.S = default_settings()
            self.fill_all()
            self.refresh()

    def say(self, text):
        self.lbl_doc_status.config(text=text)
        self.lbl_saved.config(text=text)

    def save_pdf(self):
        try:
            import reportlab  # noqa: F401
        except ImportError:
            messagebox.showerror(
                "PDF tool missing",
                "Install it once with:\n\n    pip install reportlab\n\nthen restart the app.",
            )
            return
        self.refresh()
        m = self.model
        if not m:
            return
        # light validation
        if not (self.J.get("title") or self.J.get("client")):
            if not messagebox.askyesno(
                "Missing details",
                "This job has no title or customer name.\n\nSave the PDF anyway?",
            ):
                return
        default = (
            f"{m['title'].replace(' ', '-')}-"
            f"{''.join(ch if ch.isalnum() or ch in '-_.' else '-' for ch in m['number'])}.pdf"
        )
        path = filedialog.asksaveasfilename(
            title="Save PDF",
            defaultextension=".pdf",
            initialfile=default,
            filetypes=[("PDF", "*.pdf")],
        )
        if not path:
            return
        try:
            make_pdf(m, path)
        except Exception as exc:
            messagebox.showerror("Could not save PDF", str(exc))
            return
        self.show("doc")
        self.say(f"Saved {path}. Attach it to your email.")
        self.open_path(os.path.dirname(path), select=path)

    def open_path(self, folder, select=None):
        try:
            if sys.platform.startswith("win"):
                if select:
                    os.system(f'explorer /select,"{os.path.normpath(select)}"')
                else:
                    os.startfile(folder)  # type: ignore
            elif sys.platform == "darwin":
                os.system(f'open -R "{select}"' if select else f'open "{folder}"')
            else:
                webbrowser.open("file://" + folder)
        except Exception:
            pass

    def open_data_folder(self):
        os.makedirs(APP_DIR, exist_ok=True)
        save_data(self.S, self.J, self.library)
        self.open_path(APP_DIR)

    def where_data(self):
        messagebox.showinfo(
            "Where is my data stored?",
            "Your settings, current job and library are saved automatically in this file "
            f"on your computer:\n\n{DATA_FILE}\n\n"
            "Nothing is sent over the internet. Use File → Export backup to keep a copy somewhere safe.",
        )

    def export_backup(self):
        self.refresh()
        path = filedialog.asksaveasfilename(
            title="Export backup",
            defaultextension=".json",
            initialfile=f"job-costing-backup-{today_stamp()}.json",
            filetypes=[("Backup file", "*.json")],
        )
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(
                    {"version": 2, "S": self.S, "current": self.J, "library": self.library},
                    f,
                    indent=2,
                )
            messagebox.showinfo("Backup saved", f"Backup saved to:\n{path}")
        except OSError as exc:
            messagebox.showerror("Could not save backup", str(exc))

    def import_backup(self):
        path = filedialog.askopenfilename(
            title="Import backup", filetypes=[("Backup file", "*.json")]
        )
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                d = json.load(f)
            if not isinstance(d, dict):
                raise ValueError("This is not a Job Costing backup file.")
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            messagebox.showerror("Could not import backup", str(exc))
            return
        if not messagebox.askyesno(
            "Import backup", "Replace your current settings, job and library with the backup?"
        ):
            return

        self.S = default_settings()
        self.J = blank_job()
        self.library = []

        if "S" in d:
            self.S.update(d["S"])
        if "version" in d and d.get("version", 1) >= 2:
            if "current" in d:
                self.J.update(d["current"])
            if "library" in d and isinstance(d["library"], list):
                self.library = d["library"]
        else:
            if "J" in d:
                self.J.update(d["J"])
            # also try to recover any library-like data
            if "library" in d and isinstance(d["library"], list):
                self.library = d["library"]

        self.J.setdefault("materials", [])
        self.J.setdefault("other", [])
        self.J.setdefault("id", new_id())
        self.fill_all()
        self.refresh()
        self.say("Backup imported.")

    def clip(self, text, ok):
        self.clipboard_clear()
        self.clipboard_append(text)
        self.say(ok)

    def copy_doc(self):
        if self.model:
            self.clip(model_text(self.model), "Document text copied.")

    def copy_msg(self):
        self.clip(
            f"Subject: {self.J.get('emailSubject', '')}\n\n{self.J.get('emailBody', '')}",
            "Message copied.",
        )

    def reset_msg(self):
        self.J["emailEdited"] = False
        self.refresh()
        self.say("Message reset.")

    def open_email(self):
        url = (
            f"mailto:{quote(self.J.get('custEmail', ''))}"
            f"?subject={quote(self.J.get('emailSubject', ''))}"
            f"&body={quote(self.J.get('emailBody', ''))}"
        )
        webbrowser.open(url)
        self.say("Opened your email app. Attach the saved PDF before sending.")


# ---------------------------------------------------------------------------
# Quick self-test (run with: python job_costing_app.py --test)
# ---------------------------------------------------------------------------

def _run_tests() -> None:
    print("Running calc tests…")
    s = default_settings()
    j = sample_job()
    r = calc(s, j)
    assert r["on_site"] == 6.0, r["on_site"]
    assert r["labour"] == 6 * 38, r["labour"]
    assert r["cost"] > 0
    assert r["price"] >= r["cost"]
    assert 0 <= r["margin"] <= 1
    assert r["total"] >= r["price"]

    # zero cost
    j2 = blank_job()
    r2 = calc(s, j2)
    assert r2["price"] == 0
    assert r2["profit"] == 0

    # min price
    s2 = default_settings()
    s2["minPrice"] = 500
    j3 = blank_job()
    j3["people"] = 1
    j3["hours"] = 1
    r3 = calc(s2, j3)
    assert r3["price"] >= 500 or r3["cost"] == 0

    # margin clamp
    s3 = default_settings()
    s3["margin"] = 95
    r4 = calc(s3, sample_job())
    assert r4["target"] <= 0.90

    print("All tests passed.")


if __name__ == "__main__":
    if "--test" in sys.argv:
        _run_tests()
    else:
        App().mainloop()
