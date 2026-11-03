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
    """Returns (tone, head, body) where tone is good|warn|bad|neutral."""
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
            f"{M(gut)} pays for the work but leaves {M(r['cost'] - gut)} of overhead unpaid. "
            "The job earns no profit."
        )
    if gut < r["price"] - 0.004:
        gp = gut - r["cost"]
        return "warn", "Below your target margin", (
            f"{M(gut)} leaves {M(gp)} profit, a {gp / gut * 100:.1f}% margin against your "
            f"{r['target'] * 100:.1f}% target. It is {M(r['price'] - gut)} short of the recommended quote."
        )
    gp = gut - r["cost"]
    return "good", "At or above your target", f"{M(gut)} leaves {M(gp)} profit, a {gp / gut * 100:.1f}% margin."


# ---------------------------------------------------------------------------
# Pages
# ---------------------------------------------------------------------------

def page_job():
    S = st.session_state.S
    J = st.session_state.J
    r = calc(S, J)
    M = lambda v: money(S, v)

    st.title(J.get("title") or "New job")
    if J.get("sample"):
        st.info(
            "Sample job loaded. A two-person end-of-lease clean that a gut-feel quote would underprice. "
            "Change any figure to cost your own job."
        )

    col_left, col_right = st.columns([1.35, 1], gap="large")

    with col_left:
        st.subheader("Job details")
        J["title"] = st.text_input("Job title", J.get("title") or "")
        J["client"] = st.text_input("Customer", J.get("client") or "")
        J["scope"] = st.text_area("Scope of work", J.get("scope") or "", height=100)

        st.subheader("Labour")
        c1, c2 = st.columns(2)
        with c1:
            J["people"] = st.number_input("People on the job", min_value=0.0, value=float(J.get("people") or 1), step=1.0)
        with c2:
            J["hours"] = st.number_input("Hours on site, each", min_value=0.0, value=float(J.get("hours") or 0), step=0.25)
        st.caption(f"{r['on_site']:.2f} hours on site at {M(pos(S.get('labourRate')))} per hour" if r["on_site"] else "Enter the people and hours on site.")

        st.subheader("Travel")
        c1, c2 = st.columns(2)
        with c1:
            J["km"] = st.number_input("Distance, return trip (km)", min_value=0.0, value=float(J.get("km") or 0), step=1.0)
        with c2:
            J["travelHours"] = st.number_input("Travel time, return trip (hrs)", min_value=0.0, value=float(J.get("travelHours") or 0), step=0.25)
        st.caption(
            f"Vehicle {M(r['vehicle'])} plus travel time {M(r['travel_time'])}. "
            "Travel time is paid to every person."
        )

        st.subheader("Materials & supplies")
        mats = J.get("materials") or []
        mat_df_data = [{"Item": m.get("d", ""), "Qty": m.get("q", 1), "Unit cost": m.get("c", 0)} for m in mats]
        edited_mats = st.data_editor(
            mat_df_data if mat_df_data else [{"Item": "", "Qty": 1.0, "Unit cost": 0.0}],
            num_rows="dynamic",
            use_container_width=True,
            key="mats_editor",
        )
        J["materials"] = [
            {"d": row.get("Item") or "", "q": pos(row.get("Qty")), "c": pos(row.get("Unit cost"))}
            for row in edited_mats
            if (row.get("Item") or "").strip() or pos(row.get("Unit cost")) > 0
        ]

        st.subheader("Other costs")
        oths = J.get("other") or []
        oth_df_data = [{"Description": o.get("d", ""), "Amount": o.get("a", 0)} for o in oths]
        edited_oths = st.data_editor(
            oth_df_data if oth_df_data else [{"Description": "", "Amount": 0.0}],
            num_rows="dynamic",
            use_container_width=True,
            key="oths_editor",
        )
        J["other"] = [
            {"d": row.get("Description") or "", "a": pos(row.get("Amount"))}
            for row in edited_oths
            if (row.get("Description") or "").strip() or pos(row.get("Amount")) > 0
        ]

    with col_right:
        # Hero price card
        st.markdown(
            f"""
            <div style="background:#0F1B2D;color:white;padding:1.4rem 1.5rem;border-radius:12px;margin-bottom:1rem">
              <div style="font-size:0.75rem;color:#93A4BB;font-weight:600;letter-spacing:0.04em">
                RECOMMENDED QUOTE{" (EXCL. " + (S.get("taxName") or "TAX").upper() + ")" if S.get("taxOn") else ""}
              </div>
              <div style="font-size:2.4rem;font-weight:700;line-height:1.2;margin:0.2rem 0">{M(r["price"])}</div>
              <div style="font-size:0.9rem;color:#93A4BB">
                {(S.get("taxName") or "Tax") + " " + M(r["tax"]) + "  ·  Total " + M(r["total"]) if S.get("taxOn") else "Total " + M(r["total"])}
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        if r["min_applied"]:
            st.warning(f"Minimum job price of {M(pos(S.get('minPrice')))} applies. Costed price was {M(r['raw'])}.")
        elif r["rounded"]:
            st.caption(f"Rounded up from {M(r['raw'])}.")

        m1, m2 = st.columns(2)
        m1.metric("Total cost", M(r["cost"]))
        m2.metric("Profit", M(r["profit"]))
        m3, m4 = st.columns(2)
        m3.metric("Margin", f"{r['margin'] * 100:.1f}%")
        m4.metric("Profit / hour", M(r["pph"]))

        st.subheader("Compare with your usual quote")
        J["gut"] = st.number_input(
            "Your usual quote, before tax",
            min_value=0.0,
            value=float(J.get("gut") or 0),
            step=10.0,
        )
        tone, head, body = verdict_text(S, J, r)
        colors = {"good": "#DCF3E7", "warn": "#FBEBCF", "bad": "#FBE0DD", "neutral": "#EEF2F8"}
        fgs = {"good": "#0F7A4B", "warn": "#8F5200", "bad": "#B3261E", "neutral": "#111C2E"}
        st.markdown(
            f"""
            <div style="background:{colors[tone]};color:{fgs[tone]};padding:0.9rem 1rem;border-radius:8px;margin-top:0.5rem">
              <strong>{head}</strong><br/><span style="font-size:0.92rem">{body}</span>
            </div>
            """,
            unsafe_allow_html=True,
        )

        st.subheader("Where the price goes")
        breakdown = {
            "Labour": r["labour"],
            "Travel": r["travel"],
            "Materials": r["materials"],
            "Other": r["other"],
            "Overhead": r["overhead"],
            "Profit": r["profit"],
        }
        # filter zeros for cleaner chart
        chart_data = {k: v for k, v in breakdown.items() if v > 0.004}
        if chart_data and r["price"] > 0:
            st.bar_chart(chart_data, horizontal=True)
        for label, val in [
            ("Labour", r["labour"]),
            ("Travel", r["travel"]),
            ("Materials", r["materials"]),
            ("Other costs", r["other"]),
            ("Direct costs", r["direct"]),
            ("Overhead", r["overhead"]),
            ("Total cost", r["cost"]),
            ("Profit", r["profit"]),
            ("Quote price", r["price"]),
        ]:
            pct = f"{val / r['price'] * 100:.1f}%" if r["price"] > 0 else ""
            st.write(f"**{label}** — {M(val)}  {pct}")

    # action row
    st.divider()
    b1, b2, b3 = st.columns(3)
    with b1:
        if st.button("New blank job", use_container_width=True):
            st.session_state.J = blank_job()
            st.rerun()
    with b2:
        if st.button("Load sample job", use_container_width=True):
            st.session_state.J = sample_job()
            st.rerun()
    with b3:
        if st.button("Save to library", type="primary", use_container_width=True):
            name = (J.get("title") or J.get("client") or "Untitled job").strip()
            entry = {
                "id": new_id(),
                "saved_at": now_iso(),
                "name": name,
                "job": deepcopy(J),
            }
            st.session_state.library.append(entry)
            st.success(f'Saved “{name}” to library.')


def page_doc():
    S = st.session_state.S
    J = st.session_state.J
    r = calc(S, J)
    m = build_model(S, J, r)

    st.title(f"{m['title']} {m['number']}")

    col_form, col_preview = st.columns([1, 1.2], gap="large")

    with col_form:
        st.subheader("Document")
        doc_type = st.radio("Type", ["quote", "invoice"], horizontal=True, format_func=lambda x: x.title(),
                            index=0 if J.get("docType") != "invoice" else 1)
        J["docType"] = doc_type

        if doc_type == "quote":
            J["quoteNo"] = st.text_input("Quote number", J.get("quoteNo") or "")
        else:
            J["invoiceNo"] = st.text_input("Invoice number", J.get("invoiceNo") or "")
            J["paid"] = st.number_input("Amount already received (incl. tax)", min_value=0.0, value=float(J.get("paid") or 0), step=10.0)

        issue = st.date_input("Issue date", parse_date(J.get("issueDate")))
        J["issueDate"] = issue.isoformat()
        J["itemised"] = st.checkbox(
            "Show itemised lines",
            value=bool(J.get("itemised")),
            help="Splits the price into labour, materials and other. Overhead and profit stay private.",
        )

        st.subheader("Customer")
        J["custEmail"] = st.text_input("Customer email", J.get("custEmail") or "")
        J["custAddress"] = st.text_area("Customer address", J.get("custAddress") or "", height=80)

        st.subheader("Download")
        if not HAS_REPORTLAB:
            st.error("Install reportlab to enable PDF: `pip install reportlab`")
        else:
            try:
                pdf_bytes = make_pdf_bytes(m)
                fname = f"{m['title'].replace(' ', '-')}-{m['number']}.pdf".replace("/", "-")
                st.download_button(
                    "Download PDF",
                    data=pdf_bytes,
                    file_name=fname,
                    mime="application/pdf",
                    type="primary",
                    use_container_width=True,
                )
            except Exception as exc:
                st.error(f"Could not generate PDF: {exc}")

        st.download_button(
            "Download as text",
            data=model_text(m),
            file_name=f"{m['number']}.txt",
            mime="text/plain",
            use_container_width=True,
        )

        st.subheader("Email draft")
        if not J.get("emailEdited"):
            subj, body = email_template(S, J, m)
            J["emailSubject"], J["emailBody"] = subj, body
        J["emailSubject"] = st.text_input("Subject", J.get("emailSubject") or "")
        J["emailBody"] = st.text_area("Message", J.get("emailBody") or "", height=220)
        J["emailEdited"] = True
        if st.button("Reset email template"):
            J["emailEdited"] = False
            st.rerun()

    with col_preview:
        st.subheader("Preview")
        st.code(model_text(m), language=None)


def page_library():
    st.title("Job library")
    lib = st.session_state.library

    q = st.text_input("Search by title, customer or notes", "")
    qn = q.strip().lower()

    if not lib:
        st.info("No saved jobs yet. Cost a job and click **Save to library**.")
        return

    # newest first
    items = sorted(lib, key=lambda x: x.get("saved_at") or "", reverse=True)
    shown = 0
    for entry in items:
        job = entry.get("job") or {}
        name = entry.get("name") or job.get("title") or "Untitled"
        client = job.get("client") or ""
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
            c1, c2, c3 = st.columns([3, 1.2, 1.5])
            with c1:
                st.markdown(f"**{name}**")
                st.caption(f"{client} · Saved {saved}")
            with c2:
                st.metric("Price", money(st.session_state.S, price), label_visibility="collapsed")
            with c3:
                b1, b2, b3 = st.columns(3)
                if b1.button("Load", key=f"load_{entry['id']}", use_container_width=True):
                    st.session_state.J = deepcopy(job)
                    st.session_state.J["emailEdited"] = False
                    st.session_state.page = "Job costing"
                    st.rerun()
                if b2.button("Copy", key=f"dup_{entry['id']}", use_container_width=True):
                    new_job = deepcopy(job)
                    new_job["id"] = new_id()
                    new_entry = {
                        "id": new_id(),
                        "saved_at": now_iso(),
                        "name": name + " (copy)",
                        "job": new_job,
                    }
                    st.session_state.library.append(new_entry)
                    st.rerun()
                if b3.button("Del", key=f"del_{entry['id']}", use_container_width=True):
                    st.session_state.library = [e for e in lib if e.get("id") != entry.get("id")]
                    st.rerun()

    st.caption(f"Showing {shown} of {len(lib)} saved jobs")


def page_settings():
    S = st.session_state.S
    st.title("Business settings")

    tab1, tab2, tab3 = st.tabs(["Business", "Rates & pricing", "Terms & tax"])

    with tab1:
        S["bizName"] = st.text_input("Business name", S.get("bizName") or "")
        c1, c2 = st.columns(2)
        with c1:
            S["abn"] = st.text_input("ABN or tax number", S.get("abn") or "")
        with c2:
            S["phone"] = st.text_input("Phone", S.get("phone") or "")
        S["bizEmail"] = st.text_input("Business email", S.get("bizEmail") or "")
        S["address"] = st.text_area("Business address", S.get("address") or "", height=80)
        S["currency"] = st.selectbox(
            "Currency",
            ["AUD", "NZD", "USD", "CAD", "GBP", "EUR", "JPY", "SGD", "HKD", "CHF", "INR"],
            index=["AUD", "NZD", "USD", "CAD", "GBP", "EUR", "JPY", "SGD", "HKD", "CHF", "INR"].index(
                str(S.get("currency", "AUD")).upper()
            ) if str(S.get("currency", "AUD")).upper() in ["AUD", "NZD", "USD", "CAD", "GBP", "EUR", "JPY", "SGD", "HKD", "CHF", "INR"] else 0,
        )

    with tab2:
        S["labourRate"] = st.number_input(
            "Hourly labour cost, per person",
            min_value=0.0,
            value=float(S.get("labourRate") or 38),
            step=1.0,
            help="Include super, leave, insurance and payroll. Count your own time at market rate.",
        )
        mode = st.radio(
            "Overhead mode",
            ["percent", "hourly"],
            horizontal=True,
            format_func=lambda x: "% of direct costs" if x == "percent" else "Per labour hour",
            index=0 if S.get("overheadMode") != "hourly" else 1,
        )
        S["overheadMode"] = mode
        if mode == "percent":
            S["overheadPct"] = st.number_input("Overhead % of direct costs", min_value=0.0, value=float(S.get("overheadPct") or 15), step=1.0)
        else:
            S["overheadHourly"] = st.number_input("Overhead per labour hour", min_value=0.0, value=float(S.get("overheadHourly") or 6), step=0.5)

        c1, c2, c3 = st.columns(3)
        with c1:
            S["margin"] = st.number_input("Target margin %", min_value=0.0, max_value=90.0, value=float(S.get("margin") or 25), step=1.0)
        with c2:
            S["minPrice"] = st.number_input("Minimum job price", min_value=0.0, value=float(S.get("minPrice") or 150), step=10.0)
        with c3:
            S["roundTo"] = st.number_input("Round up to ($ step)", min_value=0.0, value=float(S.get("roundTo") or 5), step=1.0)

        S["travelRate"] = st.number_input("Vehicle cost per km", min_value=0.0, value=float(S.get("travelRate") or 0.88), step=0.05)

        mm = clamp(num(S.get("margin")), 0, 90) / 100
        if mm < 1:
            st.caption(
                f"At a {mm * 100:.1f}% margin, a job that costs {money(S, 100)} is quoted at "
                f"{money(S, 100 / (1 - mm))}. That is a {mm / (1 - mm) * 100:.1f}% markup on cost."
            )

    with tab3:
        S["taxOn"] = st.checkbox("Add tax to quotes and invoices", value=bool(S.get("taxOn")))
        c1, c2 = st.columns(2)
        with c1:
            S["taxName"] = st.text_input("Tax name", S.get("taxName") or "GST")
        with c2:
            S["taxRate"] = st.number_input("Tax rate %", min_value=0.0, value=float(S.get("taxRate") or 10), step=0.5)

        c1, c2, c3 = st.columns(3)
        with c1:
            S["validDays"] = st.number_input("Quote valid (days)", min_value=0, value=int(S.get("validDays") or 30), step=1)
        with c2:
            S["depositPct"] = st.number_input("Deposit to book %", min_value=0.0, value=float(S.get("depositPct") or 20), step=5.0)
        with c3:
            S["payTerms"] = st.number_input("Invoice terms (days)", min_value=0, value=int(S.get("payTerms") or 14), step=1)

        S["payDetails"] = st.text_area("Payment details (on invoices)", S.get("payDetails") or "", height=100)
        S["docNote"] = st.text_input("Closing note", S.get("docNote") or "")

    st.divider()
    if st.button("Restore example settings"):
        st.session_state.S = default_settings()
        st.rerun()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    st.set_page_config(
        page_title="Job Costing & Quotation Calculator",
        page_icon="💼",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    # Light custom CSS
    st.markdown(
        """
        <style>
          .block-container { padding-top: 1.5rem; }
          div[data-testid="stMetricValue"] { font-size: 1.35rem; }
        </style>
        """,
        unsafe_allow_html=True,
    )

    init_state()

    with st.sidebar:
        st.markdown("### Job Costing")
        st.caption("Quotation Calculator")
        st.divider()
        pages = ["Job costing", "Quote & invoice", "Job library", "Business settings"]
        choice = st.radio("Navigate", pages, index=pages.index(st.session_state.page) if st.session_state.page in pages else 0, label_visibility="collapsed")
        st.session_state.page = choice
        st.divider()
        st.caption(st.session_state.S.get("bizName") or "Your business")
        st.caption(f"{len(st.session_state.library)} job(s) in library")
        st.caption(f"v{APP_VERSION} · data stays in this browser session")

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
