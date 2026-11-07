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

def inject_styles():
    st.markdown(
        """
<style>
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600;700&family=IBM+Plex+Mono:wght@400;500&display=swap');

:root {
  --ink: #0f172a;
  --muted: #64748b;
  --line: #e2e8f0;
  --soft: #f8fafc;
  --card: #ffffff;
  --accent: #1d4ed8;
  --accent-soft: #eff6ff;
  --good: #047857;
  --good-bg: #ecfdf5;
  --warn: #b45309;
  --warn-bg: #fffbeb;
  --bad: #b91c1c;
  --bad-bg: #fef2f2;
  --side: #0b1220;
}

html, body, [class*="css"] {
  font-family: 'IBM Plex Sans', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
  color: var(--ink);
}

.block-container {
  padding-top: 1.75rem !important;
  padding-bottom: 3rem !important;
  max-width: 1180px !important;
}

/* Sidebar */
section[data-testid="stSidebar"] {
  background: var(--side) !important;
  border-right: 1px solid #1e293b;
}
section[data-testid="stSidebar"] * {
  color: #e2e8f0 !important;
}
section[data-testid="stSidebar"] .stRadio label {
  font-size: 0.92rem !important;
  font-weight: 500 !important;
  padding: 0.35rem 0 !important;
}
section[data-testid="stSidebar"] hr {
  border-color: #1e293b !important;
}

/* Typography */
h1 {
  font-size: 1.65rem !important;
  font-weight: 700 !important;
  letter-spacing: -0.03em !important;
  color: var(--ink) !important;
  margin-bottom: 0.35rem !important;
}
h2, h3 {
  font-weight: 600 !important;
  letter-spacing: -0.02em !important;
  color: var(--ink) !important;
}
.stCaption, small, .stMarkdown p {
  color: var(--muted);
}

/* Cards */
.jc-card {
  background: var(--card);
  border: 1px solid var(--line);
  border-radius: 12px;
  padding: 1.15rem 1.25rem;
  margin-bottom: 0.85rem;
}
.jc-card-title {
  font-size: 0.72rem;
  font-weight: 600;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--muted);
  margin-bottom: 0.65rem;
}
.jc-price {
  background: linear-gradient(160deg, #0b1220 0%, #1e293b 100%);
  color: #fff;
  border-radius: 14px;
  padding: 1.35rem 1.4rem 1.2rem;
  margin-bottom: 1rem;
  border: 1px solid #1e293b;
}
.jc-price-label {
  font-size: 0.7rem;
  font-weight: 600;
  letter-spacing: 0.07em;
  text-transform: uppercase;
  color: #94a3b8;
  margin-bottom: 0.25rem;
}
.jc-price-value {
  font-family: 'IBM Plex Mono', ui-monospace, monospace;
  font-size: 2.35rem;
  font-weight: 600;
  letter-spacing: -0.03em;
  line-height: 1.15;
  color: #fff;
}
.jc-price-sub {
  font-size: 0.88rem;
  color: #94a3b8;
  margin-top: 0.35rem;
}
.jc-verdict {
  border-radius: 10px;
  padding: 0.85rem 1rem;
  font-size: 0.9rem;
  line-height: 1.45;
  border: 1px solid transparent;
}
.jc-verdict strong { display: block; margin-bottom: 0.2rem; font-weight: 600; }
.jc-v-good { background: var(--good-bg); color: var(--good); border-color: #a7f3d0; }
.jc-v-warn { background: var(--warn-bg); color: var(--warn); border-color: #fde68a; }
.jc-v-bad  { background: var(--bad-bg);  color: var(--bad);  border-color: #fecaca; }
.jc-v-neutral { background: var(--soft); color: var(--ink); border-color: var(--line); }

.jc-row {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  padding: 0.4rem 0;
  border-bottom: 1px solid var(--line);
  font-size: 0.9rem;
}
.jc-row:last-child { border-bottom: none; }
.jc-row .lbl { color: var(--ink); }
.jc-row .val {
  font-family: 'IBM Plex Mono', ui-monospace, monospace;
  font-weight: 500;
  color: var(--ink);
}
.jc-row .pct { color: var(--muted); font-size: 0.8rem; margin-left: 0.5rem; min-width: 3.2rem; text-align: right; }
.jc-row.strong .lbl, .jc-row.strong .val { font-weight: 600; }

.jc-badge {
  display: inline-block;
  font-size: 0.72rem;
  font-weight: 600;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  padding: 0.2rem 0.55rem;
  border-radius: 999px;
  background: var(--accent-soft);
  color: var(--accent);
  margin-bottom: 0.75rem;
}

.jc-lib-item {
  border: 1px solid var(--line);
  border-radius: 10px;
  padding: 0.9rem 1rem;
  margin-bottom: 0.65rem;
  background: var(--card);
}
.jc-lib-name { font-weight: 600; color: var(--ink); font-size: 0.95rem; }
.jc-lib-meta { color: var(--muted); font-size: 0.82rem; margin-top: 0.15rem; }

div[data-testid="stMetricValue"] {
  font-family: 'IBM Plex Mono', ui-monospace, monospace !important;
  font-weight: 600 !important;
  font-size: 1.25rem !important;
}
div[data-testid="stMetricLabel"] {
  color: var(--muted) !important;
  font-size: 0.78rem !important;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  font-weight: 600 !important;
}

/* Inputs */
.stTextInput input, .stNumberInput input, .stTextArea textarea, .stSelectbox [data-baseweb="select"] > div {
  border-radius: 8px !important;
  border-color: var(--line) !important;
  font-family: 'IBM Plex Sans', sans-serif !important;
}
.stButton > button {
  border-radius: 8px !important;
  font-weight: 600 !important;
  font-family: 'IBM Plex Sans', sans-serif !important;
  letter-spacing: -0.01em;
}
.stButton > button[kind="primary"] {
  background: var(--accent) !important;
  border-color: var(--accent) !important;
}

/* Hide Streamlit chrome a bit */
#MainMenu { visibility: hidden; }
footer { visibility: hidden; }
header[data-testid="stHeader"] { background: transparent; }

hr { border-color: var(--line) !important; margin: 1.25rem 0 !important; }

.jc-mono {
  font-family: 'IBM Plex Mono', ui-monospace, monospace;
}
</style>
        """,
        unsafe_allow_html=True,
    )


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
        return "neutral", "Add job costs first", "Enter labour, travel or materials to compare against your usual price."
    if gut <= 0:
        return "neutral", "Enter your usual price", "Type what you would quote by gut feel to see the real margin."
    if gut < r["direct"]:
        return "bad", "You would lose money", (
            f"{M(gut)} does not cover direct costs of {M(r['direct'])}. "
            f"Shortfall {M(r['direct'] - gut)} before overhead."
        )
    if gut < r["cost"]:
        return "bad", "Overhead not covered", (
            f"{M(gut)} covers the work but leaves {M(r['cost'] - gut)} of overhead unpaid."
        )
    if gut < r["price"] - 0.004:
        gp = gut - r["cost"]
        return "warn", "Below target margin", (
            f"{M(gut)} → {M(gp)} profit ({gp / gut * 100:.1f}% vs {r['target'] * 100:.1f}% target). "
            f"{M(r['price'] - gut)} short of recommended."
        )
    gp = gut - r["cost"]
    return "good", "On target", f"{M(gut)} → {M(gp)} profit ({gp / gut * 100:.1f}% margin)."


def _breakdown_rows(r: Dict, M) -> str:
    rows = [
        ("Labour", r["labour"], False),
        ("Travel", r["travel"], False),
        ("Materials", r["materials"], False),
        ("Other", r["other"], False),
        ("Direct costs", r["direct"], True),
        ("Overhead", r["overhead"], False),
        ("Total cost", r["cost"], True),
        ("Profit", r["profit"], False),
        ("Quote price", r["price"], True),
    ]
    html = []
    for label, val, strong in rows:
        pct = f"{val / r['price'] * 100:.1f}%" if r["price"] > 0 else ""
        cls = "jc-row strong" if strong else "jc-row"
        html.append(
            f'<div class="{cls}"><span class="lbl">{label}</span>'
            f'<span><span class="val">{M(val)}</span>'
            f'<span class="pct">{pct}</span></span></div>'
        )
    return "\n".join(html)


def page_job():
    S = st.session_state.S
    J = st.session_state.J
    r = calc(S, J)
    M = lambda v: money(S, v)

    title = J.get("title") or "New job"
    st.markdown(f"<div class='jc-badge'>Job costing</div>", unsafe_allow_html=True)
    st.markdown(f"# {title}")
    if J.get("sample"):
        st.caption("Sample job loaded — adjust any figure to cost your own work.")

    left, right = st.columns([1.4, 1], gap="large")

    with left:
        with st.container(border=True):
            st.markdown("##### Job details")
            c1, c2 = st.columns(2)
            with c1:
                J["title"] = st.text_input("Job title", J.get("title") or "", placeholder="e.g. End-of-lease clean")
            with c2:
                J["client"] = st.text_input("Customer", J.get("client") or "", placeholder="Customer name")
            J["scope"] = st.text_area("Scope of work", J.get("scope") or "", height=90, placeholder="What's included and excluded")

        with st.container(border=True):
            st.markdown("##### Labour")
            c1, c2 = st.columns(2)
            with c1:
                J["people"] = st.number_input("People", min_value=0.0, value=float(J.get("people") or 1), step=1.0)
            with c2:
                J["hours"] = st.number_input("Hours on site (each)", min_value=0.0, value=float(J.get("hours") or 0), step=0.25)
            if r["on_site"]:
                st.caption(f"{r['on_site']:.2f} hrs on site × {M(pos(S.get('labourRate')))}/hr")

        with st.container(border=True):
            st.markdown("##### Travel")
            c1, c2 = st.columns(2)
            with c1:
                J["km"] = st.number_input("Return distance (km)", min_value=0.0, value=float(J.get("km") or 0), step=1.0)
            with c2:
                J["travelHours"] = st.number_input("Return travel time (hrs)", min_value=0.0, value=float(J.get("travelHours") or 0), step=0.25)
            st.caption(f"Vehicle {M(r['vehicle'])} · travel time {M(r['travel_time'])} (paid to every person)")

        with st.container(border=True):
            st.markdown("##### Materials")
            mats = J.get("materials") or []
            mat_data = [{"Item": m.get("d", ""), "Qty": float(m.get("q", 1) or 1), "Unit cost": float(m.get("c", 0) or 0)} for m in mats]
            edited = st.data_editor(
                mat_data if mat_data else [{"Item": "", "Qty": 1.0, "Unit cost": 0.0}],
                num_rows="dynamic",
                use_container_width=True,
                key="mats_ed",
                column_config={
                    "Item": st.column_config.TextColumn("Item", width="medium"),
                    "Qty": st.column_config.NumberColumn("Qty", min_value=0, step=1, format="%.2f"),
                    "Unit cost": st.column_config.NumberColumn("Unit cost", min_value=0, format="%.2f"),
                },
            )
            J["materials"] = [
                {"d": (row.get("Item") or "").strip(), "q": pos(row.get("Qty")), "c": pos(row.get("Unit cost"))}
                for row in edited
                if (row.get("Item") or "").strip() or pos(row.get("Unit cost")) > 0
            ]

        with st.container(border=True):
            st.markdown("##### Other costs")
            oths = J.get("other") or []
            oth_data = [{"Description": o.get("d", ""), "Amount": float(o.get("a", 0) or 0)} for o in oths]
            edited_o = st.data_editor(
                oth_data if oth_data else [{"Description": "", "Amount": 0.0}],
                num_rows="dynamic",
                use_container_width=True,
                key="oths_ed",
                column_config={
                    "Description": st.column_config.TextColumn("Description", width="large"),
                    "Amount": st.column_config.NumberColumn("Amount", min_value=0, format="%.2f"),
                },
            )
            J["other"] = [
                {"d": (row.get("Description") or "").strip(), "a": pos(row.get("Amount"))}
                for row in edited_o
                if (row.get("Description") or "").strip() or pos(row.get("Amount")) > 0
            ]

    with right:
        tax_note = f"excl. {(S.get('taxName') or 'tax')}" if S.get("taxOn") else "total"
        st.markdown(
            f"""
            <div class="jc-price">
              <div class="jc-price-label">Recommended quote · {tax_note}</div>
              <div class="jc-price-value">{M(r["price"])}</div>
              <div class="jc-price-sub">
                {(S.get("taxName") or "Tax") + " " + M(r["tax"]) + "  ·  Total " + M(r["total"]) if S.get("taxOn") else "Total " + M(r["total"])}
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        if r["min_applied"]:
            st.warning(f"Minimum price {M(pos(S.get('minPrice')))} applied (costed {M(r['raw'])}).")
        elif r["rounded"]:
            st.caption(f"Rounded up from {M(r['raw'])}.")

        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Cost", M(r["cost"]))
        m2.metric("Profit", M(r["profit"]))
        m3.metric("Margin", f"{r['margin'] * 100:.1f}%")
        m4.metric("Per hour", M(r["pph"]))

        with st.container(border=True):
            st.markdown("##### Gut-feel check")
            J["gut"] = st.number_input(
                "Your usual quote (before tax)",
                min_value=0.0,
                value=float(J.get("gut") or 0),
                step=10.0,
                label_visibility="collapsed",
                placeholder="0.00",
            )
            tone, head, body = verdict_text(S, J, r)
            st.markdown(
                f'<div class="jc-verdict jc-v-{tone}"><strong>{head}</strong>{body}</div>',
                unsafe_allow_html=True,
            )

        with st.container(border=True):
            st.markdown("##### Price composition")
            st.markdown(
                f'<div class="jc-card" style="padding:0.25rem 0;border:none;margin:0">{_breakdown_rows(r, M)}</div>',
                unsafe_allow_html=True,
            )

    st.divider()
    b1, b2, b3, _ = st.columns([1, 1, 1, 2])
    with b1:
        if st.button("New job", use_container_width=True):
            st.session_state.J = blank_job()
            st.rerun()
    with b2:
        if st.button("Load sample", use_container_width=True):
            st.session_state.J = sample_job()
            st.rerun()
    with b3:
        if st.button("Save to library", type="primary", use_container_width=True):
            name = (J.get("title") or J.get("client") or "Untitled").strip()
            st.session_state.library.append({
                "id": new_id(),
                "saved_at": now_iso(),
                "name": name,
                "job": deepcopy(J),
            })
            st.toast(f"Saved “{name}”")


def page_doc():
    S = st.session_state.S
    J = st.session_state.J
    r = calc(S, J)
    m = build_model(S, J, r)

    st.markdown("<div class='jc-badge'>Documents</div>", unsafe_allow_html=True)
    st.markdown(f"# {m['title']} {m['number']}")
    st.caption("Generate a quote or tax invoice and download the PDF.")

    form, preview = st.columns([1, 1.15], gap="large")

    with form:
        with st.container(border=True):
            st.markdown("##### Document")
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
                    "Amount already received (incl. tax)",
                    min_value=0.0,
                    value=float(J.get("paid") or 0),
                    step=10.0,
                )
            issue = st.date_input("Issue date", parse_date(J.get("issueDate")))
            J["issueDate"] = issue.isoformat()
            J["itemised"] = st.checkbox(
                "Itemised lines",
                value=bool(J.get("itemised")),
                help="Splits price across labour, materials and other. Overhead and profit stay private.",
            )

        with st.container(border=True):
            st.markdown("##### Customer")
            J["custEmail"] = st.text_input("Email", J.get("custEmail") or "")
            J["custAddress"] = st.text_area("Address", J.get("custAddress") or "", height=70)

        with st.container(border=True):
            st.markdown("##### Export")
            if not HAS_REPORTLAB:
                st.error("Install reportlab for PDF export.")
            else:
                try:
                    pdf = make_pdf_bytes(m)
                    fname = f"{(m['title'] or 'doc').replace(' ', '-')}-{m['number']}.pdf".replace("/", "-")
                    st.download_button(
                        "Download PDF",
                        data=pdf,
                        file_name=fname,
                        mime="application/pdf",
                        type="primary",
                        use_container_width=True,
                    )
                except Exception as exc:
                    st.error(f"PDF failed: {exc}")
            st.download_button(
                "Download text",
                data=model_text(m),
                file_name=f"{m['number']}.txt",
                mime="text/plain",
                use_container_width=True,
            )

        with st.container(border=True):
            st.markdown("##### Email draft")
            if not J.get("emailEdited"):
                subj, body = email_template(S, J, m)
                J["emailSubject"], J["emailBody"] = subj, body
            J["emailSubject"] = st.text_input("Subject", J.get("emailSubject") or "")
            J["emailBody"] = st.text_area("Body", J.get("emailBody") or "", height=200)
            J["emailEdited"] = True
            if st.button("Reset template"):
                J["emailEdited"] = False
                st.rerun()

    with preview:
        with st.container(border=True):
            st.markdown("##### Preview")
            st.code(model_text(m), language=None)


def page_library():
    st.markdown("<div class='jc-badge'>Library</div>", unsafe_allow_html=True)
    st.markdown("# Saved jobs")
    st.caption("Jobs are kept for this browser session only.")

    lib = st.session_state.library
    q = st.text_input("Search", "", placeholder="Title, customer, notes…")
    qn = q.strip().lower()

    if not lib:
        st.info("No saved jobs. Cost a job and use **Save to library**.")
        return

    items = sorted(lib, key=lambda x: x.get("saved_at") or "", reverse=True)
    shown = 0
    for entry in items:
        job = entry.get("job") or {}
        name = entry.get("name") or job.get("title") or "Untitled"
        client = job.get("client") or "—"
        hay = f"{name} {client} {job.get('scope', '')} {job.get('title', '')}".lower()
        if qn and qn not in hay:
            continue
        shown += 1
        try:
            price = calc(st.session_state.S, job)["price"]
        except Exception:
            price = 0.0
        saved = (entry.get("saved_at") or "")[:16].replace("T", " ")

        with st.container(border=True):
            c1, c2, c3 = st.columns([3.2, 1.1, 1.6])
            with c1:
                st.markdown(f"**{name}**")
                st.caption(f"{client} · {saved}")
            with c2:
                st.markdown(
                    f"<div class='jc-mono' style='font-size:1.05rem;font-weight:600;padding-top:0.35rem'>"
                    f"{money(st.session_state.S, price)}</div>",
                    unsafe_allow_html=True,
                )
            with c3:
                a, b, c = st.columns(3)
                if a.button("Load", key=f"L{entry['id']}", use_container_width=True):
                    st.session_state.J = deepcopy(job)
                    st.session_state.J["emailEdited"] = False
                    st.session_state.page = "Job costing"
                    st.rerun()
                if b.button("Copy", key=f"C{entry['id']}", use_container_width=True):
                    nj = deepcopy(job)
                    nj["id"] = new_id()
                    st.session_state.library.append({
                        "id": new_id(),
                        "saved_at": now_iso(),
                        "name": name + " (copy)",
                        "job": nj,
                    })
                    st.rerun()
                if c.button("Del", key=f"D{entry['id']}", use_container_width=True):
                    st.session_state.library = [e for e in lib if e.get("id") != entry.get("id")]
                    st.rerun()

    st.caption(f"{shown} of {len(lib)} jobs")


def page_settings():
    S = st.session_state.S
    st.markdown("<div class='jc-badge'>Settings</div>", unsafe_allow_html=True)
    st.markdown("# Business settings")
    st.caption("Rates and details used on every quote and invoice.")

    t1, t2, t3 = st.tabs(["Business", "Rates & pricing", "Terms & tax"])

    with t1:
        with st.container(border=True):
            S["bizName"] = st.text_input("Business name", S.get("bizName") or "")
            c1, c2 = st.columns(2)
            with c1:
                S["abn"] = st.text_input("ABN / tax number", S.get("abn") or "")
            with c2:
                S["phone"] = st.text_input("Phone", S.get("phone") or "")
            S["bizEmail"] = st.text_input("Email", S.get("bizEmail") or "")
            S["address"] = st.text_area("Address", S.get("address") or "", height=80)
            currencies = ["AUD", "NZD", "USD", "CAD", "GBP", "EUR", "JPY", "SGD", "HKD", "CHF", "INR"]
            cur = str(S.get("currency", "AUD")).upper()
            S["currency"] = st.selectbox("Currency", currencies, index=currencies.index(cur) if cur in currencies else 0)

    with t2:
        with st.container(border=True):
            S["labourRate"] = st.number_input(
                "Hourly labour cost (per person)",
                min_value=0.0,
                value=float(S.get("labourRate") or 38),
                step=1.0,
                help="Include on-costs. Value your own time at market rate.",
            )
            mode = st.radio(
                "Overhead",
                ["percent", "hourly"],
                horizontal=True,
                format_func=lambda x: "% of direct costs" if x == "percent" else "Per labour hour",
                index=0 if S.get("overheadMode") != "hourly" else 1,
            )
            S["overheadMode"] = mode
            if mode == "percent":
                S["overheadPct"] = st.number_input("Overhead %", min_value=0.0, value=float(S.get("overheadPct") or 15), step=1.0)
            else:
                S["overheadHourly"] = st.number_input("Overhead $/hour", min_value=0.0, value=float(S.get("overheadHourly") or 6), step=0.5)

            c1, c2, c3 = st.columns(3)
            with c1:
                S["margin"] = st.number_input("Target margin %", min_value=0.0, max_value=90.0, value=float(S.get("margin") or 25), step=1.0)
            with c2:
                S["minPrice"] = st.number_input("Minimum price", min_value=0.0, value=float(S.get("minPrice") or 150), step=10.0)
            with c3:
                S["roundTo"] = st.number_input("Round up ($)", min_value=0.0, value=float(S.get("roundTo") or 5), step=1.0)

            S["travelRate"] = st.number_input("Vehicle $/km", min_value=0.0, value=float(S.get("travelRate") or 0.88), step=0.05)

            mm = clamp(num(S.get("margin")), 0, 90) / 100
            if 0 < mm < 1:
                st.caption(
                    f"At {mm * 100:.0f}% margin, {money(S, 100)} cost → "
                    f"{money(S, 100 / (1 - mm))} quote ({mm / (1 - mm) * 100:.0f}% markup)."
                )

    with t3:
        with st.container(border=True):
            S["taxOn"] = st.checkbox("Add tax to documents", value=bool(S.get("taxOn")))
            c1, c2 = st.columns(2)
            with c1:
                S["taxName"] = st.text_input("Tax name", S.get("taxName") or "GST")
            with c2:
                S["taxRate"] = st.number_input("Tax rate %", min_value=0.0, value=float(S.get("taxRate") or 10), step=0.5)

            c1, c2, c3 = st.columns(3)
            with c1:
                S["validDays"] = st.number_input("Quote valid (days)", min_value=0, value=int(S.get("validDays") or 30), step=1)
            with c2:
                S["depositPct"] = st.number_input("Deposit %", min_value=0.0, value=float(S.get("depositPct") or 20), step=5.0)
            with c3:
                S["payTerms"] = st.number_input("Invoice terms (days)", min_value=0, value=int(S.get("payTerms") or 14), step=1)

            S["payDetails"] = st.text_area("Payment details", S.get("payDetails") or "", height=90)
            S["docNote"] = st.text_input("Closing note", S.get("docNote") or "")

    st.divider()
    if st.button("Restore example settings"):
        st.session_state.S = default_settings()
        st.rerun()


def main():
    st.set_page_config(
        page_title="Job Costing",
        page_icon="▢",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    inject_styles()
    init_state()

    with st.sidebar:
        st.markdown(
            """
            <div style="padding:0.4rem 0 1rem">
              <div style="font-weight:700;font-size:1.05rem;letter-spacing:-0.02em;color:#fff">Job Costing</div>
              <div style="font-size:0.78rem;color:#94a3b8;margin-top:0.15rem">Quotation calculator</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        pages = ["Job costing", "Quote & invoice", "Job library", "Business settings"]
        labels = {
            "Job costing": "Costing",
            "Quote & invoice": "Documents",
            "Job library": "Library",
            "Business settings": "Settings",
        }
        current = st.session_state.page if st.session_state.page in pages else pages[0]
        choice = st.radio(
            "Nav",
            pages,
            index=pages.index(current),
            format_func=lambda p: labels.get(p, p),
            label_visibility="collapsed",
        )
        st.session_state.page = choice
        st.markdown("---")
        st.caption(st.session_state.S.get("bizName") or "Your business")
        n = len(st.session_state.library)
        st.caption(f"{n} job{'s' if n != 1 else ''} in library")
        st.caption(f"v{APP_VERSION}")

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
