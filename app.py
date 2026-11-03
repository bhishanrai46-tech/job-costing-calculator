#!/usr/bin/env python3
"""
Job Costing & Quotation Calculator — Streamlit edition

Cost a job, price it to your target margin, manage a simple job library,
and download a professional quote or tax invoice as PDF.

Run locally:  streamlit run app.py
Deploy:       push to GitHub and connect at share.streamlit.io
"""

from __future__ import annotations

import datetime as dt
import io
import json
import math
import uuid
from copy import deepcopy
from typing import Any, Dict, List, Optional, Tuple

import streamlit as st

# Optional PDF (graceful if missing)
try:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.lib.utils import simpleSplit
    from reportlab.pdfgen import canvas
    HAS_REPORTLAB = True
except ImportError:
    HAS_REPORTLAB = False

# ---------------------------------------------------------------------------
# Constants & pure helpers (shared with desktop version)
# ---------------------------------------------------------------------------

APP_VERSION = "2.0-streamlit"

SYMBOLS = {
    "AUD": "$", "NZD": "$", "USD": "$", "CAD": "$",
    "GBP": "£", "EUR": "€", "JPY": "¥", "SGD": "$",
    "HKD": "$", "CHF": "CHF ", "INR": "₹",
}

SEG_COLORS = {
    "labour": "#2457E6",
    "travel": "#0E8A8A",
    "materials": "#C27A0E",
    "other": "#7A4FBF",
    "overhead": "#8393A3",
    "profit": "#12A266",
}


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
# Costing engine
# ---------------------------------------------------------------------------

def calc(s: Dict, j: Dict) -> Dict:
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


def make_pdf_bytes(m: Dict) -> bytes:
    if not HAS_REPORTLAB:
        raise RuntimeError("reportlab is not installed")

    buf = io.BytesIO()
    W, H = A4
    ML, MR = 18, 192
    ACC = (36 / 255, 87 / 255, 230 / 255)
    INK = (15 / 255, 27 / 255, 45 / 255)
    MUT = (95 / 255, 110 / 255, 128 / 255)
    RULE = (221 / 255, 227 / 255, 235 / 255)
    SOFT = (244 / 255, 246 / 255, 249 / 255)

    c = canvas.Canvas(buf, pagesize=A4)
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
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Streamlit session helpers
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Streamlit UI — matched to desktop Tkinter app
# ---------------------------------------------------------------------------

DESKTOP_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@500;600&display=swap');

:root {
  --side: #0F1B2D;
  --side-hover: #18283F;
  --side-active: #1F3453;
  --side-fg: #C5D0E0;
  --side-muted: #7D8EA6;
  --bg: #F3F5F9;
  --card: #FFFFFF;
  --line: #DDE3EC;
  --field: #C3CDDA;
  --ink: #111C2E;
  --muted: #66758A;
  --accent: #2457E6;
  --accent-dark: #1B47C4;
  --soft: #F6F8FB;
  --good: #0F7A4B;
  --warn: #8F5200;
  --bad: #B3261E;
  --good-bg: #DCF3E7;
  --warn-bg: #FBEBCF;
  --bad-bg: #FBE0DD;
  --neutral-bg: #EEF2F8;
}

html, body, [class*="css"] {
  font-family: Inter, "Segoe UI", system-ui, sans-serif !important;
  color: var(--ink);
}

.stApp {
  background: var(--bg) !important;
}

.block-container {
  padding-top: 1.25rem !important;
  padding-bottom: 2.5rem !important;
  padding-left: 1.75rem !important;
  padding-right: 1.75rem !important;
  max-width: 1280px !important;
}

/* —— Sidebar (match desktop) —— */
section[data-testid="stSidebar"] {
  background: var(--side) !important;
  border-right: none !important;
  min-width: 232px !important;
}
section[data-testid="stSidebar"] > div {
  background: var(--side) !important;
  padding-top: 1.25rem !important;
}
section[data-testid="stSidebar"] * {
  color: var(--side-fg) !important;
}
section[data-testid="stSidebar"] .stRadio label {
  font-size: 0.95rem !important;
  font-weight: 600 !important;
  padding: 0.55rem 0.4rem !important;
  border-radius: 0 !important;
}
section[data-testid="stSidebar"] .stRadio label:hover {
  background: var(--side-hover) !important;
}
section[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p {
  color: var(--side-muted) !important;
}
section[data-testid="stSidebar"] hr {
  border-color: #1E3049 !important;
  margin: 0.75rem 0 !important;
}

/* —— Typography —— */
h1 {
  font-size: 1.55rem !important;
  font-weight: 700 !important;
  letter-spacing: -0.03em !important;
  color: var(--ink) !important;
  margin: 0 0 0.25rem 0 !important;
}
h2, h3, h4, h5 {
  font-weight: 600 !important;
  color: var(--ink) !important;
  letter-spacing: -0.02em !important;
}
.stCaption, [data-testid="stCaptionContainer"] {
  color: var(--muted) !important;
  font-size: 0.85rem !important;
}

/* —— Cards —— */
div[data-testid="stVerticalBlockBorderWrapper"] {
  background: var(--card) !important;
  border: 1px solid var(--line) !important;
  border-radius: 4px !important;
  box-shadow: none !important;
}

/* —— Price hero (desktop dark panel) —— */
.hero {
  background: var(--side);
  color: #fff;
  border-radius: 4px;
  padding: 1.15rem 1.25rem 1rem;
  margin-bottom: 0.85rem;
}
.hero-label {
  font-size: 0.7rem;
  font-weight: 700;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: #93A4BB;
  margin-bottom: 0.2rem;
}
.hero-price {
  font-family: "JetBrains Mono", "Consolas", monospace;
  font-size: 2.15rem;
  font-weight: 600;
  letter-spacing: -0.03em;
  line-height: 1.15;
  color: #fff;
}
.hero-sub {
  font-size: 0.88rem;
  color: #93A4BB;
  margin-top: 0.3rem;
}
.hero-flag {
  font-size: 0.8rem;
  color: #F0B25C;
  margin-top: 0.45rem;
}
.hero-stats {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 0.65rem 1rem;
  margin-top: 0.9rem;
  padding-top: 0.85rem;
  border-top: 1px solid #263A52;
}
.hero-stat-label {
  font-size: 0.65rem;
  font-weight: 700;
  letter-spacing: 0.05em;
  text-transform: uppercase;
  color: #93A4BB;
}
.hero-stat-value {
  font-family: "JetBrains Mono", monospace;
  font-size: 1.05rem;
  font-weight: 600;
  color: #fff;
  margin-top: 0.1rem;
}

/* —— Crumb —— */
.crumb {
  font-size: 0.72rem;
  font-weight: 700;
  letter-spacing: 0.07em;
  text-transform: uppercase;
  color: var(--accent);
  margin-bottom: 0.15rem;
}

/* —— Verdict —— */
.verdict {
  border-radius: 4px;
  padding: 0.75rem 0.9rem;
  font-size: 0.88rem;
  line-height: 1.45;
  margin-top: 0.5rem;
}
.verdict strong {
  display: block;
  font-weight: 700;
  margin-bottom: 0.15rem;
}
.v-good { background: var(--good-bg); color: var(--good); }
.v-warn { background: var(--warn-bg); color: var(--warn); }
.v-bad  { background: var(--bad-bg);  color: var(--bad); }
.v-neutral { background: var(--neutral-bg); color: var(--ink); }

/* —— Breakdown rows —— */
.brk {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  padding: 0.38rem 0;
  border-bottom: 1px solid var(--line);
  font-size: 0.88rem;
}
.brk:last-child { border-bottom: none; }
.brk .nm { color: var(--ink); }
.brk .am {
  font-family: "JetBrains Mono", monospace;
  font-weight: 500;
  color: var(--ink);
}
.brk .pc {
  color: var(--muted);
  font-size: 0.78rem;
  min-width: 3.1rem;
  text-align: right;
  margin-left: 0.45rem;
}
.brk.str .nm, .brk.str .am { font-weight: 700; }
.brk-dot {
  display: inline-block;
  width: 8px;
  height: 8px;
  border-radius: 2px;
  margin-right: 0.45rem;
  vertical-align: middle;
}

/* —— Segment bar —— */
.segbar {
  display: flex;
  height: 12px;
  border-radius: 2px;
  overflow: hidden;
  margin: 0.4rem 0 0.75rem;
  background: var(--soft);
}
.segbar > div { height: 100%; }

/* —— Sample banner —— */
.banner {
  background: #E8EEFD;
  color: var(--ink);
  font-size: 0.88rem;
  padding: 0.6rem 0.9rem;
  border-radius: 4px;
  margin-bottom: 0.85rem;
  border: 1px solid #D0DBF7;
}

/* —— Metrics —— */
div[data-testid="stMetricValue"] {
  font-family: "JetBrains Mono", monospace !important;
  font-weight: 600 !important;
  font-size: 1.15rem !important;
  color: var(--ink) !important;
}
div[data-testid="stMetricLabel"] {
  color: var(--muted) !important;
  font-size: 0.72rem !important;
  font-weight: 700 !important;
  letter-spacing: 0.04em !important;
  text-transform: uppercase !important;
}

/* —— Inputs —— */
.stTextInput input, .stNumberInput input, .stTextArea textarea {
  border-radius: 4px !important;
  border: 1px solid var(--field) !important;
  font-size: 0.95rem !important;
}
.stButton > button {
  border-radius: 4px !important;
  font-weight: 600 !important;
  font-size: 0.88rem !important;
  border: 1px solid var(--field) !important;
  background: var(--card) !important;
  color: var(--ink) !important;
  padding: 0.4rem 1rem !important;
}
.stButton > button[kind="primary"] {
  background: var(--accent) !important;
  border-color: var(--accent) !important;
  color: #fff !important;
}
.stButton > button[kind="primary"]:hover {
  background: var(--accent-dark) !important;
  border-color: var(--accent-dark) !important;
}

/* Hide Streamlit chrome */
#MainMenu, footer, header[data-testid="stHeader"] { visibility: hidden; height: 0; }
header[data-testid="stHeader"] { background: transparent !important; }

hr {
  border: none !important;
  border-top: 1px solid var(--line) !important;
  margin: 1rem 0 !important;
}

.chip {
  display: inline-block;
  background: var(--neutral-bg);
  color: var(--ink);
  font-size: 0.8rem;
  font-weight: 700;
  font-family: "JetBrains Mono", monospace;
  padding: 0.15rem 0.55rem;
  border-radius: 3px;
  float: right;
}
</style>
"""


def inject_styles():
    st.markdown(DESKTOP_CSS, unsafe_allow_html=True)


def init_state():
    if "S" not in st.session_state:
        st.session_state.S = default_settings()
    if "J" not in st.session_state:
        st.session_state.J = sample_job()
    if "library" not in st.session_state:
        st.session_state.library = []
    if "page" not in st.session_state:
        st.session_state.page = "Job costing"


def verdict_text(s: Dict, j: Dict, r: Dict) -> Tuple[str, str, str]:
    gut = pos(j.get("gut"))
    M = lambda v: money(s, v)
    if r["cost"] <= 0:
        return "neutral", "Add the job costs first", "Once the job has labour, travel or materials, this compares your usual price with what the job needs."
    if gut <= 0:
        return "neutral", "Enter your usual price", "Type what you would have quoted by gut feel to see what it earns you on this job."
    if gut < r["direct"]:
        return "bad", "You would lose money on this job", (
            f"{M(gut)} does not cover the {M(r['direct'])} it costs you to do the work. "
            f"You would be {M(r['direct'] - gut)} out of pocket before any overhead."
        )
    if gut < r["cost"]:
        return "bad", "Overhead is not covered", (
            f"{M(gut)} pays for the work but leaves {M(r['cost'] - gut)} of overhead unpaid. The job earns no profit."
        )
    if gut < r["price"] - 0.004:
        gp = gut - r["cost"]
        return "warn", "Below your target margin", (
            f"{M(gut)} leaves {M(gp)} profit, a {gp / gut * 100:.1f}% margin against your "
            f"{r['target'] * 100:.1f}% target. It is {M(r['price'] - gut)} short of the recommended quote."
        )
    gp = gut - r["cost"]
    return "good", "At or above your target", f"{M(gut)} leaves {M(gp)} profit, a {gp / gut * 100:.1f}% margin."


def _seg_bar(r: Dict) -> str:
    if r["price"] <= 0:
        return ""
    segs = [
        ("labour", "#2457E6"),
        ("travel", "#0E8A8A"),
        ("materials", "#C27A0E"),
        ("other", "#7A4FBF"),
        ("overhead", "#8393A3"),
        ("profit", "#12A266"),
    ]
    parts = []
    for k, col in segs:
        pct = max(r[k], 0) / r["price"] * 100
        if pct > 0.3:
            parts.append(f'<div style="width:{pct:.2f}%;background:{col}"></div>')
    return f'<div class="segbar">{"".join(parts)}</div>'


def _breakdown(r: Dict, M) -> str:
    rows = [
        ("labour", "Labour", "#2457E6", False),
        ("travel", "Travel", "#0E8A8A", False),
        ("materials", "Materials & supplies", "#C27A0E", False),
        ("other", "Other costs", "#7A4FBF", False),
        ("direct", "Direct costs", None, True),
        ("overhead", "Overhead", "#8393A3", False),
        ("cost", "Total cost", None, True),
        ("profit", "Profit", "#12A266", False),
        ("price", "Quote price", None, True),
    ]
    html = []
    for key, label, col, strong in rows:
        val = r[key]
        pct = f"{val / r['price'] * 100:.1f}%" if r["price"] > 0 else ""
        cls = "brk str" if strong else "brk"
        dot = f'<span class="brk-dot" style="background:{col}"></span>' if col else ""
        html.append(
            f'<div class="{cls}"><span class="nm">{dot}{label}</span>'
            f'<span><span class="am">{M(val)}</span><span class="pc">{pct}</span></span></div>'
        )
    return "\n".join(html)


def page_job():
    S, J = st.session_state.S, st.session_state.J
    r = calc(S, J)
    M = lambda v: money(S, v)
    tn = S.get("taxName") or "Tax"

    st.markdown('<div class="crumb">Job costing</div>', unsafe_allow_html=True)
    st.markdown(f"# {J.get('title') or 'New job'}")

    if J.get("sample"):
        st.markdown(
            '<div class="banner">Sample job loaded. A two-person end-of-lease clean that a gut-feel quote '
            "would underprice. Change any figure to cost your own job.</div>",
            unsafe_allow_html=True,
        )

    left, right = st.columns([1.35, 1], gap="medium")

    with left:
        with st.container(border=True):
            st.markdown("**Job details**")
            st.caption("Shown on the quote and invoice.")
            c1, c2 = st.columns(2)
            with c1:
                J["title"] = st.text_input("Job title", J.get("title") or "")
            with c2:
                J["client"] = st.text_input("Customer", J.get("client") or "")
            J["scope"] = st.text_area("Scope of work", J.get("scope") or "", height=88)

        with st.container(border=True):
            st.markdown(
                f'**Labour** <span class="chip">{M(r["labour"])}</span>',
                unsafe_allow_html=True,
            )
            c1, c2 = st.columns(2)
            with c1:
                J["people"] = st.number_input("People on the job", min_value=0.0, value=float(J.get("people") or 1), step=1.0)
            with c2:
                J["hours"] = st.number_input("Hours on site, each", min_value=0.0, value=float(J.get("hours") or 0), step=0.25)
            if r["on_site"]:
                st.caption(f"{r['on_site']:.2f} hours on site at {M(pos(S.get('labourRate')))} per hour")
            else:
                st.caption("Enter the people and hours on site.")

        with st.container(border=True):
            st.markdown(
                f'**Travel** <span class="chip">{M(r["travel"])}</span>',
                unsafe_allow_html=True,
            )
            c1, c2 = st.columns(2)
            with c1:
                J["km"] = st.number_input("Distance, return trip", min_value=0.0, value=float(J.get("km") or 0), step=1.0, help="km")
            with c2:
                J["travelHours"] = st.number_input("Travel time, return trip", min_value=0.0, value=float(J.get("travelHours") or 0), step=0.25, help="hrs")
            st.caption(
                f"Vehicle {M(r['vehicle'])} plus travel time {M(r['travel_time'])}. Travel time is paid to every person."
            )

        with st.container(border=True):
            st.markdown(
                f'**Materials & supplies** <span class="chip">{M(r["materials"])}</span>',
                unsafe_allow_html=True,
            )
            st.caption("Everything you buy for this job.")
            mats = J.get("materials") or []
            data = [{"Item": m.get("d", ""), "Qty": float(m.get("q") or 1), "Unit cost": float(m.get("c") or 0)} for m in mats]
            edited = st.data_editor(
                data if data else [{"Item": "", "Qty": 1.0, "Unit cost": 0.0}],
                num_rows="dynamic",
                use_container_width=True,
                key="mat_ed",
                column_config={
                    "Item": st.column_config.TextColumn("Item"),
                    "Qty": st.column_config.NumberColumn("Qty", min_value=0, format="%.2f"),
                    "Unit cost": st.column_config.NumberColumn("Unit cost", min_value=0, format="%.2f"),
                },
            )
            J["materials"] = [
                {"d": (row.get("Item") or "").strip(), "q": pos(row.get("Qty")), "c": pos(row.get("Unit cost"))}
                for row in edited
                if (row.get("Item") or "").strip() or pos(row.get("Unit cost")) > 0
            ]

        with st.container(border=True):
            st.markdown(
                f'**Other costs** <span class="chip">{M(r["other"])}</span>',
                unsafe_allow_html=True,
            )
            st.caption("Equipment hire, subcontractors, tip fees and permits.")
            oths = J.get("other") or []
            odata = [{"Description": o.get("d", ""), "Amount": float(o.get("a") or 0)} for o in oths]
            oed = st.data_editor(
                odata if odata else [{"Description": "", "Amount": 0.0}],
                num_rows="dynamic",
                use_container_width=True,
                key="oth_ed",
                column_config={
                    "Description": st.column_config.TextColumn("Description"),
                    "Amount": st.column_config.NumberColumn("Amount", min_value=0, format="%.2f"),
                },
            )
            J["other"] = [
                {"d": (row.get("Description") or "").strip(), "a": pos(row.get("Amount"))}
                for row in oed
                if (row.get("Description") or "").strip() or pos(row.get("Amount")) > 0
            ]

    with right:
        # Hero — same as desktop dark panel
        flag = ""
        if r["min_applied"]:
            flag = f'<div class="hero-flag">Your minimum job price of {M(pos(S.get("minPrice")))} applies. The costed price was {M(r["raw"])}.</div>'
        elif r["rounded"]:
            flag = f'<div class="hero-flag">Rounded up from {M(r["raw"])}.</div>'

        tax_line = (
            f'{tn} {M(r["tax"])} &nbsp;|&nbsp; Total {M(r["total"])}'
            if S.get("taxOn")
            else f'Total {M(r["total"])}'
        )
        lab = "RECOMMENDED QUOTE" + (f" (EXCL. {tn.upper()})" if S.get("taxOn") else "")

        st.markdown(
            f"""
            <div class="hero">
              <div class="hero-label">{lab}</div>
              <div class="hero-price">{M(r["price"])}</div>
              <div class="hero-sub">{tax_line}</div>
              {flag}
              <div class="hero-stats">
                <div><div class="hero-stat-label">Total cost</div><div class="hero-stat-value">{M(r["cost"])}</div></div>
                <div><div class="hero-stat-label">Profit</div><div class="hero-stat-value">{M(r["profit"])}</div></div>
                <div><div class="hero-stat-label">Margin</div><div class="hero-stat-value">{r["margin"]*100:.1f}%</div></div>
                <div><div class="hero-stat-label">Profit per hour</div><div class="hero-stat-value">{M(r["pph"])}</div></div>
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        with st.container(border=True):
            st.markdown("**Compare with your usual quote**")
            J["gut"] = st.number_input(
                "Your usual quote, before tax",
                min_value=0.0,
                value=float(J.get("gut") or 0),
                step=10.0,
            )
            tone, head, body = verdict_text(S, J, r)
            st.markdown(
                f'<div class="verdict v-{tone}"><strong>{head}</strong>{body}</div>',
                unsafe_allow_html=True,
            )

        with st.container(border=True):
            st.markdown("**Where the price goes**")
            st.markdown(_seg_bar(r), unsafe_allow_html=True)
            st.markdown(_breakdown(r, M), unsafe_allow_html=True)

    st.divider()
    a, b, c, _ = st.columns([1, 1, 1.2, 2])
    with a:
        if st.button("New blank job", use_container_width=True):
            st.session_state.J = blank_job()
            st.rerun()
    with b:
        if st.button("Load sample job", use_container_width=True):
            st.session_state.J = sample_job()
            st.rerun()
    with c:
        if st.button("Save to library", type="primary", use_container_width=True):
            name = (J.get("title") or J.get("client") or "Untitled job").strip()
            st.session_state.library.append({
                "id": new_id(),
                "saved_at": now_iso(),
                "name": name,
                "job": deepcopy(J),
            })
            st.toast(f"Saved “{name}”")


def page_doc():
    S, J = st.session_state.S, st.session_state.J
    r = calc(S, J)
    m = build_model(S, J, r)

    st.markdown('<div class="crumb">Quote & invoice</div>', unsafe_allow_html=True)
    st.markdown(f"# {m['title']} {m['number']}")

    form, preview = st.columns([1, 1.2], gap="medium")

    with form:
        with st.container(border=True):
            st.markdown("**Document**")
            doc_type = st.radio(
                "Type",
                ["quote", "invoice"],
                horizontal=True,
                format_func=lambda x: "Quote" if x == "quote" else "Invoice",
                index=0 if J.get("docType") != "invoice" else 1,
                label_visibility="collapsed",
            )
            J["docType"] = doc_type
            if doc_type == "quote":
                J["quoteNo"] = st.text_input("Quote number", J.get("quoteNo") or "")
            else:
                J["invoiceNo"] = st.text_input("Invoice number", J.get("invoiceNo") or "")
                J["paid"] = st.number_input(
                    "Amount already received, including tax",
                    min_value=0.0,
                    value=float(J.get("paid") or 0),
                    step=10.0,
                )
            issue = st.date_input("Issue date", parse_date(J.get("issueDate")))
            J["issueDate"] = issue.isoformat()
            J["itemised"] = st.checkbox(
                "Show itemised lines",
                value=bool(J.get("itemised")),
                help="Splits the price into labour, materials and other costs. Overhead and profit stay private.",
            )

        with st.container(border=True):
            st.markdown("**Customer**")
            J["custEmail"] = st.text_input("Customer email", J.get("custEmail") or "")
            J["custAddress"] = st.text_area("Customer address", J.get("custAddress") or "", height=72)

        with st.container(border=True):
            st.markdown("**Send to customer**")
            st.caption("Save the PDF, then attach it to your email.")
            if not HAS_REPORTLAB:
                st.error("Install reportlab: pip install reportlab")
            else:
                try:
                    pdf = make_pdf_bytes(m)
                    fname = f"{(m['title'] or 'doc').replace(' ', '-')}-{m['number']}.pdf".replace("/", "-")
                    st.download_button(
                        "Save as PDF…",
                        data=pdf,
                        file_name=fname,
                        mime="application/pdf",
                        type="primary",
                        use_container_width=True,
                    )
                except Exception as exc:
                    st.error(str(exc))
            st.download_button(
                "Copy as text",
                data=model_text(m),
                file_name=f"{m['number']}.txt",
                mime="text/plain",
                use_container_width=True,
            )

        with st.container(border=True):
            st.markdown("**Email**")
            if not J.get("emailEdited"):
                subj, body = email_template(S, J, m)
                J["emailSubject"], J["emailBody"] = subj, body
            J["emailSubject"] = st.text_input("Email subject", J.get("emailSubject") or "")
            J["emailBody"] = st.text_area("Email message", J.get("emailBody") or "", height=200)
            J["emailEdited"] = True
            if st.button("Reset message"):
                J["emailEdited"] = False
                st.rerun()

    with preview:
        with st.container(border=True):
            st.markdown("**Preview**")
            st.code(model_text(m), language=None)


def page_library():
    st.markdown('<div class="crumb">Job library</div>', unsafe_allow_html=True)
    st.markdown("# Saved jobs")

    lib = st.session_state.library
    q = st.text_input("Search", "", placeholder="Search by title, customer or notes")
    qn = q.strip().lower()

    if not lib:
        st.info("No saved jobs yet. Cost a job and click **Save to library**.")
        return

    items = sorted(lib, key=lambda x: x.get("saved_at") or "", reverse=True)
    shown = 0
    for entry in items:
        job = entry.get("job") or {}
        name = entry.get("name") or job.get("title") or "Untitled"
        client = job.get("client") or ""
        hay = f"{name} {client} {job.get('scope', '')}".lower()
        if qn and qn not in hay:
            continue
        shown += 1
        try:
            price = calc(st.session_state.S, job)["price"]
        except Exception:
            price = 0.0
        saved = (entry.get("saved_at") or "")[:16].replace("T", " ")

        with st.container(border=True):
            c1, c2, c3 = st.columns([3, 1.2, 1.6])
            with c1:
                st.markdown(f"**{name}**")
                st.caption(f"{client or '—'} · {saved}")
            with c2:
                st.markdown(
                    f'<div style="font-family:JetBrains Mono,monospace;font-weight:600;font-size:1.05rem;padding-top:0.3rem">'
                    f'{money(st.session_state.S, price)}</div>',
                    unsafe_allow_html=True,
                )
            with c3:
                x, y, z = st.columns(3)
                if x.button("Load", key=f"ld{entry['id']}", use_container_width=True):
                    st.session_state.J = deepcopy(job)
                    st.session_state.J["emailEdited"] = False
                    st.session_state.page = "Job costing"
                    st.rerun()
                if y.button("Copy", key=f"cp{entry['id']}", use_container_width=True):
                    nj = deepcopy(job)
                    nj["id"] = new_id()
                    st.session_state.library.append({
                        "id": new_id(),
                        "saved_at": now_iso(),
                        "name": name + " (copy)",
                        "job": nj,
                    })
                    st.rerun()
                if z.button("Del", key=f"dl{entry['id']}", use_container_width=True):
                    st.session_state.library = [e for e in lib if e.get("id") != entry.get("id")]
                    st.rerun()

    st.caption(f"{shown} of {len(lib)} jobs")


def page_settings():
    S = st.session_state.S
    st.markdown('<div class="crumb">Business settings</div>', unsafe_allow_html=True)
    st.markdown("# Your rates and business details")

    t1, t2, t3 = st.tabs(["Your business", "Rates & pricing", "Terms & tax"])

    with t1:
        with st.container(border=True):
            st.markdown("**Your business**")
            st.caption("Printed at the top of every quote and invoice.")
            S["bizName"] = st.text_input("Business name", S.get("bizName") or "")
            c1, c2 = st.columns(2)
            with c1:
                S["abn"] = st.text_input("ABN or tax number", S.get("abn") or "")
            with c2:
                S["phone"] = st.text_input("Phone", S.get("phone") or "")
            S["bizEmail"] = st.text_input("Business email", S.get("bizEmail") or "")
            S["address"] = st.text_area("Business address", S.get("address") or "", height=72)
            curs = ["AUD", "NZD", "USD", "CAD", "GBP", "EUR", "JPY", "SGD", "HKD", "CHF", "INR"]
            cur = str(S.get("currency", "AUD")).upper()
            S["currency"] = st.selectbox("Currency code", curs, index=curs.index(cur) if cur in curs else 0)

    with t2:
        with st.container(border=True):
            st.markdown("**Labour cost**")
            S["labourRate"] = st.number_input(
                "Hourly labour cost, per person",
                min_value=0.0,
                value=float(S.get("labourRate") or 38),
                step=1.0,
                help="What one person costs you per hour, including super, leave, insurance and payroll.",
            )

        with st.container(border=True):
            st.markdown("**Overhead allowance**")
            mode = st.radio(
                "Mode",
                ["percent", "hourly"],
                horizontal=True,
                format_func=lambda x: "% of direct costs" if x == "percent" else "Per labour hour",
                index=0 if S.get("overheadMode") != "hourly" else 1,
            )
            S["overheadMode"] = mode
            if mode == "percent":
                S["overheadPct"] = st.number_input(
                    "Overhead as a share of direct costs",
                    min_value=0.0,
                    value=float(S.get("overheadPct") or 15),
                    step=1.0,
                )
            else:
                S["overheadHourly"] = st.number_input(
                    "Overhead per labour hour",
                    min_value=0.0,
                    value=float(S.get("overheadHourly") or 6),
                    step=0.5,
                )

        with st.container(border=True):
            st.markdown("**Profit & pricing**")
            c1, c2, c3 = st.columns(3)
            with c1:
                S["margin"] = st.number_input("Target profit margin %", min_value=0.0, max_value=90.0, value=float(S.get("margin") or 25), step=1.0)
            with c2:
                S["minPrice"] = st.number_input("Minimum job price", min_value=0.0, value=float(S.get("minPrice") or 150), step=10.0)
            with c3:
                S["roundTo"] = st.number_input("Round quote up to", min_value=0.0, value=float(S.get("roundTo") or 5), step=1.0, help="$ step")

            mm = clamp(num(S.get("margin")), 0, 90) / 100
            if 0 < mm < 1:
                st.info(
                    f"At a {mm*100:.1f}% margin, a job that costs {money(S, 100)} is quoted at "
                    f"{money(S, 100/(1-mm))}. That is a {mm/(1-mm)*100:.1f}% markup on cost."
                )

        with st.container(border=True):
            st.markdown("**Travel**")
            S["travelRate"] = st.number_input(
                "Vehicle cost per kilometre",
                min_value=0.0,
                value=float(S.get("travelRate") or 0.88),
                step=0.05,
                help="Fuel, servicing, tyres and depreciation. Travel time is charged at your labour cost.",
            )

    with t3:
        with st.container(border=True):
            st.markdown("**Tax**")
            S["taxOn"] = st.checkbox("Add tax to quotes and invoices", value=bool(S.get("taxOn")))
            c1, c2 = st.columns(2)
            with c1:
                S["taxName"] = st.text_input("Tax name", S.get("taxName") or "GST")
            with c2:
                S["taxRate"] = st.number_input("Tax rate %", min_value=0.0, value=float(S.get("taxRate") or 10), step=0.5)

        with st.container(border=True):
            st.markdown("**Terms & payment**")
            c1, c2, c3 = st.columns(3)
            with c1:
                S["validDays"] = st.number_input("Quote valid for (days)", min_value=0, value=int(S.get("validDays") or 30), step=1)
            with c2:
                S["depositPct"] = st.number_input("Deposit to book %", min_value=0.0, value=float(S.get("depositPct") or 20), step=5.0)
            with c3:
                S["payTerms"] = st.number_input("Invoice terms (days)", min_value=0, value=int(S.get("payTerms") or 14), step=1)
            S["payDetails"] = st.text_area("Payment details, printed on invoices", S.get("payDetails") or "", height=90)
            S["docNote"] = st.text_input("Closing note", S.get("docNote") or "")

    st.divider()
    if st.button("Restore example settings"):
        st.session_state.S = default_settings()
        st.rerun()


def main():
    st.set_page_config(
        page_title="Job Costing & Quotation Calculator",
        page_icon="▢",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    inject_styles()
    init_state()

    with st.sidebar:
        st.markdown(
            """
            <div style="display:flex;align-items:center;gap:10px;padding:0.35rem 0 1.1rem">
              <div style="width:34px;height:34px;background:#2457E6;border-radius:4px;display:flex;flex-direction:column;justify-content:center;padding-left:8px;gap:4px">
                <div style="height:2.5px;width:18px;background:#fff;border-radius:1px"></div>
                <div style="height:2.5px;width:12px;background:#fff;border-radius:1px"></div>
                <div style="height:2.5px;width:7px;background:#fff;border-radius:1px"></div>
              </div>
              <div>
                <div style="font-weight:700;font-size:0.95rem;color:#fff;line-height:1.2">Job Costing</div>
                <div style="font-size:0.72rem;color:#7D8EA6">Quotation Calculator</div>
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        pages = [
            ("Job costing", "Job costing"),
            ("Quote & invoice", "Quote & invoice"),
            ("Job library", "Job library"),
            ("Business settings", "Business settings"),
        ]
        labels = [p[0] for p in pages]
        current = st.session_state.page if st.session_state.page in labels else labels[0]
        choice = st.radio(
            "nav",
            labels,
            index=labels.index(current),
            label_visibility="collapsed",
        )
        st.session_state.page = choice

        st.markdown("---")
        st.markdown(
            f'<div style="font-weight:700;color:#fff;font-size:0.88rem">{st.session_state.S.get("bizName") or "Your business"}</div>',
            unsafe_allow_html=True,
        )
        n = len(st.session_state.library)
        st.caption(f"{n} job{'s' if n != 1 else ''} in library · session only")

    page = st.session_state.page
    if page == "Job costing":
        page_job()
    elif page == "Quote & invoice":
        page_doc()
    elif page == "Job library":
        page_library()
    else:
        page_settings()


if __name__ == "__main__":
    main()
