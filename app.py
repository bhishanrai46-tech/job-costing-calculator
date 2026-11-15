#!/usr/bin/env python3
"""Job Costing & Quotation Calculator (single-file Streamlit app).

Cost a job, price it to your target margin, issue locked quotes and invoices as PDF,
track payments, and keep a job library with JSON backup.

Install:  pip install streamlit reportlab pillow pandas tzdata
Run:      streamlit run app.py
Optional: set JOBCOST_DATA_FILE=~/jobcost-data.json to autosave to a file on your own computer.
"""
from __future__ import annotations

import base64
import datetime as dt
import hashlib
import html
import io
import json
import math
import os
import re
import tempfile
import uuid
from copy import deepcopy
from decimal import ROUND_CEILING, ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import quote

import pandas as pd
import streamlit as st
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader, simpleSplit
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas


# ======================================================================
# COSTING ENGINE
# ======================================================================

try:  # zoneinfo needs the tzdata package on Windows
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover
    ZoneInfo = None  # type: ignore

APP_VERSION = "3.0"
DATA_VERSION = 3

ZERO = Decimal("0")
CENT = Decimal("0.01")
HUNDRED = Decimal("100")

SYMBOLS = {
    "AUD": "$", "NZD": "$", "USD": "$", "CAD": "$",
    "GBP": "£", "EUR": "€", "JPY": "¥", "SGD": "$",
    "HKD": "$", "CHF": "CHF ", "INR": "₹",
}
CURRENCIES = list(SYMBOLS)

STATUSES = ["Draft", "Quote sent", "Accepted", "Invoiced", "Paid", "Declined"]

# Job fields frozen into a document when it is issued.
SNAPSHOT_JOB_KEYS = [
    "title", "client", "scope", "people", "hours", "km", "travelHours",
    "materials", "other", "itemised", "custAddress", "custAbn",
]


# ---------------------------------------------------------------------------
# Number, text and date helpers
# ---------------------------------------------------------------------------

_STRIP = re.compile(r"[,\s$£€¥₹]|CHF", re.IGNORECASE)


def dec(v: Any) -> Decimal:
    """Parse almost anything into a finite Decimal. Bad input becomes 0."""
    if v is None or isinstance(v, bool):
        return ZERO
    if isinstance(v, Decimal):
        x = v
    elif isinstance(v, float):
        if not math.isfinite(v):
            return ZERO
        x = Decimal(repr(v))
    elif isinstance(v, int):
        x = Decimal(v)
    else:
        s = _STRIP.sub("", str(v))
        if not s:
            return ZERO
        try:
            x = Decimal(s)
        except InvalidOperation:
            return ZERO
    return x if x.is_finite() else ZERO


def pos(v: Any) -> Decimal:
    return max(ZERO, dec(v))


def to_cents(x: Decimal) -> Decimal:
    """Round to cents, half up."""
    return x.quantize(CENT, rounding=ROUND_HALF_UP)


def clamp(v: Decimal, lo: Decimal, hi: Decimal) -> Decimal:
    return max(lo, min(hi, v))


def txt(v: Any) -> str:
    """Safe string from a value that may be None or NaN (as data editors return)."""
    if v is None:
        return ""
    if isinstance(v, float) and not math.isfinite(v):
        return ""
    return str(v)


def lines_of(text: Any) -> List[str]:
    return [x.strip() for x in txt(text).splitlines() if x.strip()]


def new_id() -> str:
    return str(uuid.uuid4())


def get_tz(name: str):
    if ZoneInfo is not None:
        try:
            return ZoneInfo(name or "UTC")
        except Exception:
            pass
    return dt.timezone.utc


def today(tzname: str = "UTC") -> dt.date:
    return dt.datetime.now(get_tz(tzname)).date()


def now_iso(tzname: str = "UTC") -> str:
    return dt.datetime.now(get_tz(tzname)).replace(microsecond=0, tzinfo=None).isoformat()


def parse_date(text: Any, fallback: Optional[dt.date] = None) -> dt.date:
    if isinstance(text, dt.datetime):
        return text.date()
    if isinstance(text, dt.date):
        return text
    s = txt(text).strip()
    fb = fallback or dt.date.today()
    if not s:
        return fb
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y", "%Y/%m/%d"):
        try:
            return dt.datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return fb


def fmt_date(d: dt.date) -> str:
    return f"{d.day} {d.strftime('%B %Y')}"


def money(s: Dict, v: Any) -> str:
    sym = SYMBOLS.get(str(s.get("currency", "AUD")).upper(), "$")
    x = to_cents(dec(v))
    return ("-" if x < 0 else "") + sym + f"{abs(x):,.2f}"


def pct(v: Any) -> str:
    """Compact percentage text: 20.0 -> '20', 7.50 -> '7.5'."""
    x = dec(v)
    return format(x.normalize(), "f") if x != 0 else "0"


def safe_filename(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "-", name).strip("-") or "document"


# ---------------------------------------------------------------------------
# Defaults and normalisation
# ---------------------------------------------------------------------------

def default_settings() -> Dict:
    return {
        "bizName": "Example Cleaning Co.",
        "abn": "00 000 000 000",
        "phone": "0400 000 000",
        "bizEmail": "accounts@example.com.au",
        "address": "1 Example Street\nSydney NSW 2000",
        "currency": "AUD",
        "timezone": "Australia/Sydney",
        "labourRate": 38.0,
        "overheadMode": "percent",
        "overheadPct": 15.0,
        "overheadHourly": 6.0,
        "materialsAllowancePct": 0.0,
        "otherAllowancePct": 0.0,
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
        "terms": "",
        "showAcceptance": True,
        "quotePrefix": "Q-",
        "invoicePrefix": "INV-",
        "nextQuote": 1,
        "nextInvoice": 1,
        "logo": "",
    }


def normalise_settings(raw: Any) -> Dict:
    """Merge untrusted settings onto the defaults, coercing every type."""
    out = default_settings()
    if not isinstance(raw, dict):
        return out
    for k, d in out.items():
        if k not in raw:
            continue
        v = raw[k]
        if isinstance(d, bool):
            out[k] = bool(v)
        elif isinstance(d, int):
            out[k] = max(0, int(dec(v)))
        elif isinstance(d, float):
            out[k] = float(pos(v))
        else:
            out[k] = txt(v)
    out["margin"] = float(clamp(dec(out["margin"]), ZERO, Decimal(90)))
    if out["currency"].upper() not in SYMBOLS:
        out["currency"] = "AUD"
    out["currency"] = out["currency"].upper()
    if out["overheadMode"] not in ("percent", "hourly"):
        out["overheadMode"] = "percent"
    out["nextQuote"] = max(1, out["nextQuote"])
    out["nextInvoice"] = max(1, out["nextInvoice"])
    return out


def doc_defaults(tz: str = "UTC") -> Dict:
    return {
        "docType": "quote",
        "quoteNo": "",
        "invoiceNo": "",
        "issueDate": today(tz).isoformat(),
        "payments": [],
        "custEmail": "",
        "custAddress": "",
        "custAbn": "",
        "itemised": False,
        "emailEdited": False,
        "emailSubject": "",
        "emailBody": "",
        "status": "Draft",
        "issued": {},
    }


def blank_job(tz: str = "UTC") -> Dict:
    j = doc_defaults(tz)
    j.update({
        "id": new_id(),
        "sample": False,
        "title": "",
        "client": "",
        "scope": "",
        "people": 1.0,
        "hours": 0.0,
        "km": 0.0,
        "travelHours": 0.0,
        "materials": [],
        "other": [],
        "gut": 0.0,
        "saved_at": now_iso(tz),
    })
    return j


def sample_job(tz: str = "UTC") -> Dict:
    j = blank_job(tz)
    j.update({
        "sample": True,
        "title": "End-of-lease clean, 3-bed unit",
        "client": "Sample Customer",
        "custEmail": "customer@example.com",
        "custAddress": "12 Sample Road\nSydney NSW 2000",
        "scope": (
            "Full interior clean to bond-return standard: kitchen, bathrooms, floors, "
            "windows (inside) and wardrobes.\nCarpet steam cleaning is not included."
        ),
        "people": 2.0,
        "hours": 3.0,
        "km": 18.0,
        "travelHours": 0.5,
        "materials": [
            {"d": "Cleaning products", "q": 1.0, "c": 18.0},
            {"d": "Consumables (cloths, bags, sponges)", "q": 1.0, "c": 12.0},
        ],
        "gut": 250.0,
    })
    return j


def normalise_job(raw: Any, tz: str = "UTC") -> Dict:
    """Coerce an untrusted job dict into a well-formed one."""
    j = blank_job(tz)
    if not isinstance(raw, dict):
        return j
    for k in ("title", "client", "scope", "custEmail", "custAddress", "custAbn",
              "quoteNo", "invoiceNo", "emailSubject", "emailBody", "saved_at"):
        if k in raw:
            j[k] = txt(raw[k])
    for k in ("people", "hours", "km", "travelHours", "gut"):
        if k in raw:
            j[k] = float(pos(raw[k]))
    for k in ("itemised", "emailEdited", "sample"):
        if k in raw:
            j[k] = bool(raw[k])
    if raw.get("id"):
        j["id"] = txt(raw["id"])
    if raw.get("docType") in ("quote", "invoice"):
        j["docType"] = raw["docType"]
    if raw.get("status") in STATUSES:
        j["status"] = raw["status"]
    if raw.get("issueDate"):
        j["issueDate"] = parse_date(raw["issueDate"], today(tz)).isoformat()

    mats = []
    for m in raw.get("materials") or []:
        if isinstance(m, dict):
            mats.append({"d": txt(m.get("d")), "q": float(pos(m.get("q"))), "c": float(pos(m.get("c")))})
    j["materials"] = mats
    oth = []
    for o in raw.get("other") or []:
        if isinstance(o, dict):
            oth.append({"d": txt(o.get("d")), "a": float(pos(o.get("a")))})
    j["other"] = oth

    pays = []
    for p in raw.get("payments") or []:
        if isinstance(p, dict) and pos(p.get("amount")) > 0:
            pays.append({
                "date": parse_date(p.get("date"), today(tz)).isoformat(),
                "amount": float(pos(p.get("amount"))),
                "note": txt(p.get("note")),
            })
    j["payments"] = pays

    issued: Dict[str, Dict] = {}
    src = raw.get("issued")
    if isinstance(src, dict):
        for kind in ("quote", "invoice"):
            snap = src.get(kind)
            if isinstance(snap, dict) and isinstance(snap.get("S"), dict) and isinstance(snap.get("job"), dict):
                sj = snap["job"]
                job_part = normalise_job({**sj}, tz)
                issued[kind] = {
                    "kind": kind,
                    "number": txt(snap.get("number")),
                    "issueDate": parse_date(snap.get("issueDate"), today(tz)).isoformat(),
                    "issuedAt": txt(snap.get("issuedAt")),
                    "S": normalise_settings(snap["S"]),
                    "job": {k: job_part[k] for k in SNAPSHOT_JOB_KEYS},
                }
    j["issued"] = issued
    return j


# ---------------------------------------------------------------------------
# Costing
# ---------------------------------------------------------------------------

def calc(s: Dict, j: Dict) -> Dict:
    people = pos(j.get("people"))
    hours = pos(j.get("hours"))
    rate = pos(s.get("labourRate"))

    on_site = people * hours
    travel_hours = pos(j.get("travelHours")) * people
    paid_hours = on_site + travel_hours

    labour = to_cents(on_site * rate)
    vehicle = to_cents(pos(j.get("km")) * pos(s.get("travelRate")))
    travel_time = to_cents(travel_hours * rate)
    travel = vehicle + travel_time

    mat_base = sum((to_cents(pos(r.get("q")) * pos(r.get("c"))) for r in j.get("materials") or []), ZERO)
    mat_allow = to_cents(mat_base * pos(s.get("materialsAllowancePct")) / HUNDRED)
    materials = mat_base + mat_allow

    oth_base = sum((to_cents(pos(r.get("a"))) for r in j.get("other") or []), ZERO)
    oth_allow = to_cents(oth_base * pos(s.get("otherAllowancePct")) / HUNDRED)
    other = oth_base + oth_allow

    direct = labour + travel + materials + other

    if s.get("overheadMode") == "hourly":
        overhead = to_cents(paid_hours * pos(s.get("overheadHourly")))
    else:
        overhead = to_cents(direct * pos(s.get("overheadPct")) / HUNDRED)

    cost = direct + overhead
    target = clamp(dec(s.get("margin")), ZERO, Decimal(90)) / HUNDRED
    raw = to_cents(cost / (1 - target)) if cost > 0 else ZERO

    price = raw
    rounded = False
    min_applied = False

    step = pos(s.get("roundTo"))
    if step > 0 and price > 0:
        rp = to_cents((price / step).to_integral_value(rounding=ROUND_CEILING) * step)
        rounded = rp > price
        price = rp

    min_p = pos(s.get("minPrice"))
    if cost > 0 and min_p > price:
        price = to_cents(min_p)
        min_applied = True
        rounded = False

    price = to_cents(price)
    profit = price - cost
    tax_rate = pos(s.get("taxRate")) if s.get("taxOn") else ZERO
    tax = to_cents(price * tax_rate / HUNDRED)
    total = price + tax

    return {
        "labour": labour, "vehicle": vehicle, "travel_time": travel_time, "travel": travel,
        "materials": materials, "materials_base": mat_base, "materials_allowance": mat_allow,
        "other": other, "other_base": oth_base, "other_allowance": oth_allow,
        "direct": direct, "overhead": overhead, "cost": cost,
        "target": target, "raw": raw, "price": price,
        "rounded": rounded, "min_applied": min_applied,
        "profit": profit, "margin": (profit / price if price > 0 else ZERO),
        "tax": tax, "tax_rate": tax_rate, "total": total,
        "on_site": on_site, "paid_hours": paid_hours,
        "pph": (to_cents(profit / paid_hours) if paid_hours > 0 else ZERO),
    }


def doc_lines(j: Dict, r: Dict) -> List[Tuple[str, Decimal]]:
    """Lines printed on the document. Itemised lines always add up to the price."""
    title = j.get("title") or "Job"
    if not j.get("itemised") or r["direct"] <= 0:
        return [(title, r["price"])]
    parts = [
        ("Labour and travel", r["labour"] + r["travel"]),
        ("Materials and supplies", r["materials"]),
        ("Other costs", r["other"]),
    ]
    parts = [p for p in parts if p[1] > 0]
    out: List[Tuple[str, Decimal]] = []
    running = ZERO
    for i, (name, val) in enumerate(parts):
        a = to_cents(r["price"] - running) if i == len(parts) - 1 else to_cents(r["price"] * val / r["direct"])
        running += a
        out.append((name, a))
    return out


def verdict(s: Dict, j: Dict, r: Dict) -> Tuple[str, str, str]:
    """Compare the user's gut-feel quote with the costed price."""
    gut = pos(j.get("gut"))

    def M(v):
        return money(s, v)

    if r["cost"] <= 0:
        return ("neutral", "Add the job costs first",
                "Once the job has labour, travel or materials, this compares your usual price with what the job needs.")
    if gut <= 0:
        return ("neutral", "Enter your usual price",
                "Type what you would have quoted by gut feel to see what it earns you on this job.")
    if gut < r["direct"]:
        return ("bad", "You would lose money on this job",
                f"{M(gut)} does not cover the {M(r['direct'])} it costs you to do the work. "
                f"You would be {M(r['direct'] - gut)} out of pocket before any overhead.")
    if gut < r["cost"]:
        return ("bad", "Overhead is not covered",
                f"{M(gut)} pays for the work but leaves {M(r['cost'] - gut)} of overhead unpaid. "
                "The job earns no profit.")
    gp = gut - r["cost"]
    gm = gp / gut
    target = r["target"]
    if gut < r["price"] and gm < target:
        return ("warn", "Below your target margin",
                f"{M(gut)} leaves {M(gp)} profit, a {gm * 100:.1f}% margin against your "
                f"{target * 100:.1f}% target. It is {M(r['price'] - gut)} short of the recommended quote.")
    if gut < r["price"]:
        return ("good", "On target",
                f"{M(gut)} leaves {M(gp)} profit, a {gm * 100:.1f}% margin. The recommended quote "
                f"is {M(r['price'])} only because of your rounding or minimum price settings.")
    return ("good", "At or above your target", f"{M(gut)} leaves {M(gp)} profit, a {gm * 100:.1f}% margin.")


# ---------------------------------------------------------------------------
# Document numbering, payments and frozen (issued) documents
# ---------------------------------------------------------------------------

def _counter_key(kind: str) -> str:
    return "nextQuote" if kind == "quote" else "nextInvoice"


def _prefix(s: Dict, kind: str) -> str:
    return txt(s.get("quotePrefix" if kind == "quote" else "invoicePrefix"))


def peek_number(s: Dict, kind: str) -> str:
    n = max(1, int(dec(s.get(_counter_key(kind))) or 1))
    return f"{_prefix(s, kind)}{n:04d}"


def allocate_number(s: Dict, kind: str) -> str:
    """Return the next number and advance the counter."""
    num = peek_number(s, kind)
    s[_counter_key(kind)] = max(1, int(dec(s.get(_counter_key(kind))) or 1)) + 1
    return num


def number_in_use(library: List[Dict], job: Dict, kind: str, number: str) -> bool:
    """True if a different saved job already issued this document number."""
    number = number.strip().lower()
    if not number:
        return False
    for entry in library:
        other = entry.get("job") or {}
        if other.get("id") == job.get("id"):
            continue
        snap = (other.get("issued") or {}).get(kind)
        if snap and txt(snap.get("number")).strip().lower() == number:
            return True
    return False


def payments_total(j: Dict) -> Decimal:
    return sum((to_cents(pos(p.get("amount"))) for p in j.get("payments") or []), ZERO)


def make_snapshot(s: Dict, j: Dict, kind: str, number: str, issue_date: dt.date, tz: str) -> Dict:
    s_copy = deepcopy(s)
    s_copy["logo"] = ""  # the logo is always taken live; keeps snapshots small
    return {
        "kind": kind,
        "number": number,
        "issueDate": issue_date.isoformat(),
        "issuedAt": now_iso(tz),
        "S": s_copy,
        "job": {k: deepcopy(j.get(k)) for k in SNAPSHOT_JOB_KEYS},
    }


def doc_context(s: Dict, j: Dict, kind: Optional[str] = None) -> Tuple[Dict, Dict, Optional[Dict]]:
    """Settings and job as they should appear on the document.

    If the document has been issued, returns the frozen copies so later changes
    to rates or the job never alter it. Payments and customer email stay live.
    """
    kind = kind or j.get("docType") or "quote"
    snap = (j.get("issued") or {}).get(kind)
    if not snap:
        j2 = deepcopy(j)
        j2["docType"] = kind
        return s, j2, None
    s2 = deepcopy(snap["S"])
    s2["logo"] = s.get("logo", "")
    j2 = deepcopy(j)
    j2.update(deepcopy(snap["job"]))
    j2["docType"] = kind
    j2["issueDate"] = snap["issueDate"]
    j2["quoteNo" if kind == "quote" else "invoiceNo"] = snap["number"]
    return s2, j2, snap


def invoice_figures(s: Dict, j: Dict) -> Tuple[Dict, Decimal, Decimal]:
    s2, j2, _ = doc_context(s, j, "invoice")
    r = calc(s2, j2)
    paid = payments_total(j)
    return r, paid, max(ZERO, r["total"] - paid)


def sync_status(s: Dict, j: Dict) -> None:
    """Keep the job status in step with payments on an issued invoice."""
    if not (j.get("issued") or {}).get("invoice"):
        return
    r, paid, _ = invoice_figures(s, j)
    if r["total"] > 0 and paid >= r["total"]:
        j["status"] = "Paid"
    elif j.get("status") == "Paid":
        j["status"] = "Invoiced"


def entry_figures(s: Dict, j: Dict) -> Dict:
    """Headline figures for a saved job (locked quote figures if it has been issued)."""
    snap = (j.get("issued") or {}).get("quote") or (j.get("issued") or {}).get("invoice")
    kind = "quote" if (j.get("issued") or {}).get("quote") else ("invoice" if snap else None)
    if snap:
        s2, j2, _ = doc_context(s, j, kind)
        r = calc(s2, j2)
    else:
        r = calc(s, j)
    inv = (j.get("issued") or {}).get("invoice")
    paid = payments_total(j)
    outstanding = ZERO
    if inv:
        ri, _, bal = invoice_figures(s, j)
        outstanding = bal
    return {"price": r["price"], "total": r["total"], "locked": bool(snap),
            "paid": paid, "outstanding": outstanding, "invoiced": bool(inv)}

# ======================================================================
# DOCUMENTS
# ======================================================================

def esc(text: Any) -> str:
    return html.escape(txt(text), quote=True)


def build_model(s: Dict, j: Dict, r: Dict) -> Dict:
    """Everything a document shows, as plain strings, shared by PDF and preview."""
    inv = j.get("docType") == "invoice"
    tn = s.get("taxName") or "Tax"
    cc = str(s.get("currency", "AUD")).upper()
    issue = parse_date(j.get("issueDate"))
    due = issue + dt.timedelta(days=int(pos(s.get("payTerms"))))
    valid_days = int(pos(s.get("validDays")))
    until = issue + dt.timedelta(days=valid_days)
    paid = payments_total(j) if inv else ZERO
    balance = max(ZERO, r["total"] - paid)

    m: Dict[str, Any] = {"inv": inv, "currency": cc}
    m["title"] = ("Tax invoice" if s.get("taxOn") else "Invoice") if inv else "Quote"
    m["number"] = txt(j.get("invoiceNo") if inv else j.get("quoteNo"))
    m["bizName"] = s.get("bizName") or "Your business"
    m["logo"] = txt(s.get("logo"))

    biz = []
    if s.get("abn"):
        biz.append("ABN " + txt(s["abn"]))
    biz += lines_of(s.get("address"))
    if s.get("phone"):
        biz.append(txt(s["phone"]))
    if s.get("bizEmail"):
        biz.append(txt(s["bizEmail"]))
    m["bizLines"] = biz

    m["billLabel"] = "Bill to" if inv else "Prepared for"
    m["billName"] = j.get("client") or "Customer"
    bill = lines_of(j.get("custAddress"))
    if j.get("custAbn"):
        bill.append("ABN " + txt(j["custAbn"]))
    if j.get("custEmail"):
        bill.append(txt(j["custEmail"]))
    m["billLines"] = bill

    if inv:
        m["meta"] = [("Invoice date", fmt_date(issue)), ("Due date", fmt_date(due))]
    else:
        m["meta"] = [
            ("Quote date", fmt_date(issue)),
            ("Valid until", fmt_date(until) if valid_days > 0 else "No expiry"),
        ]

    m["jobTitle"] = j.get("title") or "Untitled job"
    m["scope"] = txt(j.get("scope"))
    m["lines"] = [(d, money(s, a)) for d, a in doc_lines(j, r)]

    tot = []
    if s.get("taxOn"):
        tot.append((f"Subtotal (excl. {tn})", money(s, r["price"]), False))
        tot.append((f"{tn} ({pct(r['tax_rate'])}%)", money(s, r["tax"]), False))
        tot.append((f"Total (incl. {tn})", money(s, r["total"]), True))
    else:
        tot.append(("Total", money(s, r["total"]), True))

    hl = None
    if inv:
        if paid > 0:
            tot.append(("Less payments received", "-" + money(s, paid), False))
        hl = ("Balance due" if paid > 0 else "Amount due", money(s, balance))
    elif pos(s.get("depositPct")) > 0:
        hl = (
            f"Deposit to book ({pct(s.get('depositPct'))}%)",
            money(s, to_cents(r["total"] * pos(s.get("depositPct")) / 100)),
        )
    m["totals"], m["highlight"] = tot, hl
    m["balance"] = balance
    m["payment"] = txt(s.get("payDetails")) if (inv and s.get("payDetails")) else None

    notes = []
    if inv:
        if paid > 0 and balance <= 0:
            notes.append("Paid in full. Thank you.")
        else:
            notes.append(f"Payment is due within {int(pos(s.get('payTerms')))} days, by {fmt_date(due)}.")
    else:
        if pos(s.get("depositPct")) > 0:
            notes.append("A deposit is requested to book the job, with the balance due on completion.")
        if valid_days > 0:
            notes.append(f"This quote is valid for {valid_days} days, until {fmt_date(until)}.")
    notes.append(f"All amounts are in {cc}.")
    if s.get("docNote"):
        notes.append(txt(s["docNote"]))
    m["notes"] = notes
    m["terms"] = lines_of(s.get("terms"))
    m["acceptance"] = (not inv) and bool(s.get("showAcceptance"))
    return m


def model_text(m: Dict) -> str:
    L = [f"{m['title'].upper()} {m['number']}", m["bizName"]] + m["bizLines"] + [""]
    L.append(f"{m['billLabel']}: {m['billName']}")
    L += m["billLines"]
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
    if m["terms"]:
        L += ["", "Terms:"] + m["terms"]
    return "\n".join(L)


def email_template(s: Dict, j: Dict, m: Dict) -> Tuple[str, str]:
    b = [f"Hi {j['client']}," if j.get("client") else "Hi,", ""]
    if m["inv"]:
        b.append(f"Please find attached {m['title'].lower()} {m['number']} for {m['jobTitle']}.")
        b.append("")
        if m["balance"] <= 0:
            b.append("This invoice has been paid in full. Thank you.")
        else:
            b.append(f"{m['highlight'][0]}: {m['highlight'][1]}")
            b.append(f"{m['meta'][1][0]}: {m['meta'][1][1]}")
            if s.get("payDetails"):
                b += ["", "Payment details:", txt(s["payDetails"])]
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
        b += ["", "If you are happy to go ahead, just reply to this email and we will lock in a date."]
    b += ["", "Kind regards,", m["bizName"]]
    if s.get("phone"):
        b.append(txt(s["phone"]))
    return f"{m['title']} {m['number']} from {m['bizName']}", "\n".join(b)


_PREVIEW_CSS = """
html, body { margin: 0; padding: 0; background: transparent; }
.pv-wrap { background: linear-gradient(180deg,#e8edf4 0%,#dce3ec 100%); padding: 16px 12px 24px;
  border-radius: 8px; border: 1px solid #c5ced9; }
.pv-sheet { background:#fff; max-width:480px; margin:0 auto; font-family: Inter,"Segoe UI",system-ui,-apple-system,sans-serif;
  color:#0B1220; font-size:13px; line-height:1.5; border-radius:4px; overflow:hidden;
  box-shadow:0 0 0 1px rgba(11,18,32,.06),0 8px 24px rgba(11,18,32,.08); }
.pv-band { height:5px; background: linear-gradient(90deg,#1e40af,#1d4ed8 40%,#3b82f6); }
.pv-body { padding:22px 20px 18px; }
.pv-header { display:flex; justify-content:space-between; align-items:flex-start; gap:16px; }
.pv-logo { max-height:44px; max-width:150px; display:block; margin-bottom:8px; }
.pv-biz-name { font-size:15px; font-weight:700; letter-spacing:-.025em; margin:0 0 6px; }
.pv-line { color:#475569; font-size:12px; line-height:1.45; }
.pv-doc-title { font-size:18px; font-weight:700; letter-spacing:.04em; text-align:right; margin:0; line-height:1.15; }
.pv-doc-num { color:#64748B; font-size:12px; text-align:right; margin-top:4px; }
.pv-divider { height:1px; background:#D0D7E2; margin:14px 0; border:none; }
.pv-two-col { display:flex; justify-content:space-between; gap:20px; margin-bottom:16px; flex-wrap:wrap; }
.pv-label { font-size:10px; font-weight:700; letter-spacing:.08em; text-transform:uppercase; color:#64748B; margin:0 0 5px; }
.pv-bill-name { font-size:13.5px; font-weight:700; margin:0 0 3px; }
.pv-meta { min-width:150px; }
.pv-meta-row { display:flex; justify-content:space-between; gap:12px; font-size:12px; margin-bottom:5px; color:#475569; }
.pv-meta-row strong { color:#0B1220; font-weight:600; text-align:right; }
.pv-job { font-size:14px; font-weight:700; letter-spacing:-.02em; margin:0 0 4px; }
.pv-scope { color:#475569; font-size:12px; margin:0 0 14px; line-height:1.5; }
.pv-table { width:100%; border-collapse:collapse; margin-bottom:8px; }
.pv-table thead th { background:#F1F5F9; color:#475569; font-size:10px; font-weight:700; letter-spacing:.07em;
  text-transform:uppercase; text-align:left; padding:9px 10px; border-bottom:1px solid #D0D7E2; }
.pv-table thead th:last-child { text-align:right; }
.pv-table tbody td { padding:10px; border-bottom:1px solid #E2E8F0; vertical-align:top; }
.pv-amt { text-align:right; font-weight:600; white-space:nowrap; }
.pv-totals { margin-top:6px; padding-right:2px; }
.pv-tot { display:flex; justify-content:flex-end; align-items:baseline; gap:24px; font-size:12.5px; padding:5px 6px; color:#475569; }
.pv-tot span:last-child { min-width:80px; text-align:right; color:#0B1220; font-weight:500; }
.pv-tot-strong { color:#0B1220; font-weight:700; font-size:13.5px; margin-top:2px; padding-top:10px; border-top:1.5px solid #0B1220; }
.pv-tot-strong span:last-child { font-weight:700; font-size:14px; }
.pv-hl { margin:14px 0 4px auto; max-width:240px; background:linear-gradient(135deg,#1e40af 0%,#1d4ed8 100%); color:#fff;
  border-radius:6px; padding:11px 14px; display:flex; justify-content:space-between; align-items:center; gap:12px;
  font-size:12px; font-weight:500; box-shadow:0 2px 8px rgba(29,78,216,.28); }
.pv-hl strong { font-size:15px; font-weight:700; color:#fff; }
.pv-section-label { font-size:10px; font-weight:700; letter-spacing:.08em; text-transform:uppercase; color:#64748B; margin:16px 0 6px; }
.pv-pay { font-size:12px; line-height:1.55; margin-bottom:4px; }
.pv-notes { margin-top:4px; }
.pv-note { color:#475569; font-size:12px; margin:0 0 5px; line-height:1.45; }
.pv-terms { color:#475569; font-size:11px; margin:0 0 4px; line-height:1.4; }
.pv-sign { margin-top:14px; display:flex; gap:14px; font-size:11px; color:#475569; }
.pv-sign div { flex:1; border-top:1px solid #94A3B8; padding-top:4px; }
@media (max-width:380px) {
  .pv-wrap { padding:10px 6px 16px; } .pv-body { padding:16px 14px 14px; }
  .pv-header { flex-direction:column; gap:10px; } .pv-doc-title,.pv-doc-num { text-align:left; }
  .pv-two-col { flex-direction:column; gap:12px; } .pv-hl { max-width:100%; margin-left:0; }
}
"""


def render_preview(m: Dict) -> str:
    """Self-contained HTML page (for an iframe). Every dynamic value is escaped."""

    def div_lines(items, cls="pv-line"):
        return "".join(f'<div class="{cls}">{esc(x)}</div>' for x in items if txt(x).strip())

    logo = ""
    if m.get("logo", "").startswith("data:image/"):
        logo = f'<img class="pv-logo" alt="" src="{esc(m["logo"])}"/>'

    meta = "".join(
        f'<div class="pv-meta-row"><span>{esc(k)}</span><strong>{esc(v)}</strong></div>'
        for k, v in m.get("meta") or [] if txt(v).strip()
    )
    rows = "".join(
        f'<tr><td>{esc(d)}</td><td class="pv-amt">{esc(a)}</td></tr>' for d, a in m.get("lines") or []
    )
    totals = "".join(
        f'<div class="pv-tot{" pv-tot-strong" if strong else ""}"><span>{esc(a)}</span><span>{esc(b)}</span></div>'
        for a, b, strong in m.get("totals") or []
    )
    hl = ""
    if m.get("highlight"):
        hl = f'<div class="pv-hl"><span>{esc(m["highlight"][0])}</span><strong>{esc(m["highlight"][1])}</strong></div>'
    pay = ""
    if txt(m.get("payment")).strip():
        pay = ('<div class="pv-section-label">Payment details</div><div class="pv-pay">'
               + esc(m["payment"]).replace("\n", "<br>") + "</div>")
    notes = "".join(f'<p class="pv-note">{esc(n)}</p>' for n in m.get("notes") or [] if txt(n).strip())
    terms = ""
    if m.get("terms"):
        terms = '<div class="pv-section-label">Terms</div>' + div_lines(m["terms"], "pv-terms")
    sign = ""
    if m.get("acceptance"):
        sign = ('<div class="pv-section-label">Acceptance</div>'
                '<div class="pv-sign"><div>Name</div><div>Signature</div><div>Date</div></div>')
    scope = ""
    if txt(m.get("scope")).strip():
        scope = f'<p class="pv-scope">{esc(m["scope"]).replace(chr(10), "<br>")}</p>'
    bill = (
        f'<div><p class="pv-label">{esc(m.get("billLabel"))}</p>'
        f'<p class="pv-bill-name">{esc(m.get("billName"))}</p>{div_lines(m.get("billLines") or [])}</div>'
    )
    table = (
        f'<table class="pv-table"><thead><tr><th>Description</th><th>Amount ({esc(m.get("currency"))})</th></tr></thead>'
        f"<tbody>{rows}</tbody></table>"
    ) if rows else ""

    body = (
        f'<div class="pv-wrap"><div class="pv-sheet"><div class="pv-band"></div><div class="pv-body">'
        f'<div class="pv-header"><div>{logo}<p class="pv-biz-name">{esc(m.get("bizName"))}</p>'
        f'{div_lines(m.get("bizLines") or [])}</div>'
        f'<div><p class="pv-doc-title">{esc(txt(m.get("title")).upper())}</p>'
        f'<div class="pv-doc-num">{esc(m.get("number"))}</div></div></div>'
        f'<hr class="pv-divider"/><div class="pv-two-col">{bill}<div class="pv-meta">{meta}</div></div>'
        f'<p class="pv-job">{esc(m.get("jobTitle"))}</p>{scope}{table}'
        f'<div class="pv-totals">{totals}</div>{hl}{pay}'
        f'<hr class="pv-divider"/><div class="pv-notes">{notes}</div>{terms}{sign}'
        f"</div></div></div>"
    )
    return f'<!DOCTYPE html><html><head><meta charset="utf-8"/><style>{_PREVIEW_CSS}</style></head><body>{body}</body></html>'

# ======================================================================
# PDF
# ======================================================================

_HERE = os.path.dirname(os.path.abspath(__file__))

_FONT_PAIRS = [
    (os.path.join(_HERE, "fonts", "DejaVuSans.ttf"), os.path.join(_HERE, "fonts", "DejaVuSans-Bold.ttf")),
    ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
    ("/usr/share/fonts/dejavu/DejaVuSans.ttf", "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf"),
    ("/usr/share/fonts/TTF/DejaVuSans.ttf", "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf"),
    ("/System/Library/Fonts/Supplemental/Arial.ttf", "/System/Library/Fonts/Supplemental/Arial Bold.ttf"),
    ("C:\\Windows\\Fonts\\arial.ttf", "C:\\Windows\\Fonts\\arialbd.ttf"),
]

_fonts: Optional[Tuple[str, str, bool]] = None


def _get_fonts() -> Tuple[str, str, bool]:
    """(regular, bold, is_unicode). Falls back to built-in Helvetica."""
    global _fonts
    if _fonts:
        return _fonts
    for reg, bold in _FONT_PAIRS:
        if os.path.exists(reg) and os.path.exists(bold):
            try:
                pdfmetrics.registerFont(TTFont("JC-Regular", reg))
                pdfmetrics.registerFont(TTFont("JC-Bold", bold))
                _fonts = ("JC-Regular", "JC-Bold", True)
                return _fonts
            except Exception:
                continue
    _fonts = ("Helvetica", "Helvetica-Bold", False)
    return _fonts


def _make_safe(regular: str, unicode_ok: bool):
    """Replace characters the font cannot draw with '?', so no empty boxes appear."""
    if unicode_ok:
        have = pdfmetrics.getFont(regular).face.charToGlyph

        def safe(text: str) -> str:
            return "".join(ch if (ord(ch) in have or ch == "\n") else "?" for ch in str(text) if ch.isprintable() or ch == "\n")
    else:
        def safe(text: str) -> str:
            return str(text).encode("cp1252", "replace").decode("cp1252")
    return safe


class _NumberedCanvas(canvas.Canvas):
    """Canvas that prints 'Page x of y' in the footer once the page count is known."""

    def __init__(self, *args, footer_left: str = "", font: str = "Helvetica", **kwargs):
        super().__init__(*args, **kwargs)
        self._pages: List[dict] = []
        self._footer_left = footer_left
        self._footer_font = font

    def showPage(self):
        self._pages.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        pages = self._pages
        total = len(pages)
        for n, state in enumerate(pages, start=1):
            self.__dict__.update(state)
            self.setFont(self._footer_font, 8)
            self.setFillColorRGB(95 / 255, 110 / 255, 128 / 255)
            self.drawString(18 * mm, A4[1] - 288 * mm, self._footer_left)
            self.drawRightString(192 * mm, A4[1] - 288 * mm, f"Page {n} of {total}")
            super().showPage()
        super().save()


def make_pdf_bytes(m: Dict, logo_bytes: Optional[bytes] = None) -> bytes:
    regular, bold, unicode_ok = _get_fonts()
    safe = _make_safe(regular, unicode_ok)

    buf = io.BytesIO()
    W, H = A4
    ML, MR = 18, 192
    ACC = (36 / 255, 87 / 255, 230 / 255)
    INK = (15 / 255, 27 / 255, 45 / 255)
    MUT = (95 / 255, 110 / 255, 128 / 255)
    RULE = (221 / 255, 227 / 255, 235 / 255)
    SOFT = (244 / 255, 246 / 255, 249 / 255)

    title = f"{m['title']} {m['number']}".strip()
    c = _NumberedCanvas(buf, pagesize=A4, footer_left=safe(f"{m['bizName']}  |  {title}"), font=regular)
    c.setTitle(safe(title))
    c.setAuthor(safe(m["bizName"]))
    y = [0.0]

    def Y(v: float) -> float:
        return H - v * mm

    def font(name: str, size: float, color=INK) -> None:
        c.setFont(name, size)
        c.setFillColorRGB(*color)

    def wrap(text: str, width_mm: float, name: str = regular, size: float = 10) -> List[str]:
        out: List[str] = []
        for para in safe(text).split("\n"):
            out += simpleSplit(para, name, size, width_mm * mm) or [""]
        return out

    def hr(at: float) -> None:
        c.setStrokeColorRGB(*RULE)
        c.setLineWidth(0.7)
        c.line(ML * mm, Y(at), MR * mm, Y(at))

    def top_band() -> None:
        c.setFillColorRGB(*ACC)
        c.rect(0, H - 5 * mm, W, 5 * mm, stroke=0, fill=1)

    def need(h: float, redraw=None) -> None:
        if y[0] + h > 278:
            c.showPage()
            top_band()
            y[0] = 20
            if redraw:
                redraw()

    def block(lines: List[str], x: float, lh: float, name: str = regular, size: float = 10, color=INK) -> None:
        for ln in lines:
            need(lh)
            font(name, size, color)
            c.drawString(x * mm, Y(y[0]), ln)
            y[0] += lh

    top_band()
    y[0] = 20
    top_y = y[0]

    if logo_bytes:
        try:
            img = ImageReader(io.BytesIO(logo_bytes))
            iw, ih = img.getSize()
            scale = min(50 * mm / iw, 15 * mm / ih)
            dw, dh = iw * scale, ih * scale
            c.drawImage(img, ML * mm, Y(y[0]) - dh, width=dw, height=dh, mask="auto")
            y[0] += dh / mm + 3
        except Exception:
            pass

    name_y = y[0] + 3
    y[0] = name_y
    block(wrap(m["bizName"], 100, bold, 17), ML, 7, bold, 17)
    for ln in m["bizLines"]:
        block(wrap(ln, 95, regular, 9.5), ML, 4.6, regular, 9.5, MUT)
    left_end = y[0]

    font(bold, 22)
    c.drawRightString(MR * mm, Y(top_y + 4), safe(m["title"].upper()))
    font(regular, 10.5, MUT)
    c.drawRightString(MR * mm, Y(top_y + 11), safe(m["number"]))
    y[0] = max(left_end, top_y + 16) + 6
    hr(y[0])
    y[0] += 9

    col_top = y[0]
    font(bold, 8, MUT)
    c.drawString(ML * mm, Y(y[0]), safe(m["billLabel"].upper()))
    y[0] += 5.5
    block(wrap(m["billName"], 85, bold, 11.5), ML, 5.5, bold, 11.5)
    for ln in m["billLines"]:
        block(wrap(ln, 85, regular, 9.5), ML, 4.7, regular, 9.5, MUT)
    left_y = y[0]
    ry = col_top
    for k, v in m["meta"]:
        font(regular, 9.5, MUT)
        c.drawString(128 * mm, Y(ry), safe(k))
        font(bold, 9.5)
        c.drawRightString(MR * mm, Y(ry), safe(v))
        ry += 6
    y[0] = max(left_y, ry) + 8

    need(20)
    block(wrap(m["jobTitle"], 174, bold, 12.5), ML, 6, bold, 12.5)
    if m["scope"]:
        y[0] += 1
        block(wrap(m["scope"], 174, regular, 9.5), ML, 4.7, regular, 9.5, MUT)
    y[0] += 6

    def table_header() -> None:
        c.setFillColorRGB(*SOFT)
        c.rect(ML * mm, Y(y[0] + 3), (MR - ML) * mm, 8.5 * mm, stroke=0, fill=1)
        font(bold, 8, MUT)
        c.drawString((ML + 3) * mm, Y(y[0]), "DESCRIPTION")
        c.drawRightString((MR - 3) * mm, Y(y[0]), safe(f"AMOUNT ({m['currency']})"))
        y[0] += 7

    need(24)
    table_header()
    for desc, amt in m["lines"]:
        dl = wrap(desc, 140)
        need(len(dl) * 5 + 6, table_header)
        font(regular, 10)
        for i, ln in enumerate(dl):
            c.drawString((ML + 3) * mm, Y(y[0] + i * 5), ln)
        font(bold, 10)
        c.drawRightString((MR - 3) * mm, Y(y[0]), safe(amt))
        y[0] += len(dl) * 5 - 1
        hr(y[0])
        y[0] += 6.5
    y[0] += 2

    need(len(m["totals"]) * 7.5 + 30)
    for label, val, strong in m["totals"]:
        if strong:
            c.setStrokeColorRGB(*RULE)
            c.line(118 * mm, Y(y[0] - 4.5), MR * mm, Y(y[0] - 4.5))
            font(bold, 11.5)
        else:
            font(regular, 10, MUT)
        c.drawString(118 * mm, Y(y[0]), safe(label))
        font(bold if strong else regular, 11.5 if strong else 10)
        c.drawRightString(MR * mm, Y(y[0]), safe(val))
        y[0] += 7.5

    if m["highlight"]:
        y[0] += 1
        need(16)
        c.setFillColorRGB(*ACC)
        c.roundRect(110 * mm, Y(y[0] + 6), (MR - 110) * mm, 12 * mm, 1.5 * mm, stroke=0, fill=1)
        c.setFillColorRGB(1, 1, 1)
        c.setFont(regular, 10)
        c.drawString(114 * mm, Y(y[0] + 1.3), safe(m["highlight"][0]))
        c.setFont(bold, 13)
        c.drawRightString((MR - 4) * mm, Y(y[0] + 1.8), safe(m["highlight"][1]))
        y[0] += 14
    y[0] += 4

    if m["payment"]:
        need(22)
        font(bold, 8, MUT)
        c.drawString(ML * mm, Y(y[0]), "PAYMENT DETAILS")
        y[0] += 5.5
        block(wrap(m["payment"], 120), ML, 5)
        y[0] += 3

    if m["notes"]:
        need(12)
        hr(y[0])
        y[0] += 6
        for n in m["notes"]:
            block(wrap(n, 174, regular, 9), ML, 4.6, regular, 9, MUT)
            y[0] += 1

    if m.get("terms"):
        need(14)
        y[0] += 3
        font(bold, 8, MUT)
        c.drawString(ML * mm, Y(y[0]), "TERMS")
        y[0] += 5
        for t in m["terms"]:
            block(wrap(t, 174, regular, 8.5), ML, 4.1, regular, 8.5, MUT)

    if m.get("acceptance"):
        need(28)
        y[0] += 5
        font(bold, 8, MUT)
        c.drawString(ML * mm, Y(y[0]), "ACCEPTANCE")
        y[0] += 11
        c.setStrokeColorRGB(0.58, 0.64, 0.72)
        c.setLineWidth(0.6)
        for x0, x1, lab in ((ML, 80, "Name"), (86, 140, "Signature"), (146, MR, "Date")):
            c.line(x0 * mm, Y(y[0]), x1 * mm, Y(y[0]))
            font(regular, 8, MUT)
            c.drawString(x0 * mm, Y(y[0] + 4), lab)

    c.showPage()
    c.save()
    return buf.getvalue()

# ======================================================================
# STORAGE
# ======================================================================

MAX_IMPORT_BYTES = 10 * 1024 * 1024
MAX_LOGO_BYTES = 2 * 1024 * 1024
MAX_JOBS = 5000


# ---------------------------------------------------------------------------
# Logo
# ---------------------------------------------------------------------------

def process_logo(data: bytes) -> str:
    """Validate and shrink an uploaded image, returning a PNG data URI."""
    from PIL import Image  # local import: Pillow is only needed for logos

    if len(data) > MAX_LOGO_BYTES:
        raise ValueError("Logo file is too large (limit 2 MB).")
    img = Image.open(io.BytesIO(data))
    img.load()
    if img.mode not in ("RGB", "RGBA"):
        img = img.convert("RGBA")
    img.thumbnail((600, 240))
    out = io.BytesIO()
    img.save(out, format="PNG", optimize=True)
    return "data:image/png;base64," + base64.b64encode(out.getvalue()).decode("ascii")


def logo_bytes(uri: str) -> Optional[bytes]:
    prefix = "data:image/png;base64,"
    if not uri or not uri.startswith(prefix):
        return None
    try:
        return base64.b64decode(uri[len(prefix):], validate=True)
    except Exception:
        return None


def valid_logo(uri: str) -> str:
    """Return the URI only if it decodes to a real PNG, else an empty string."""
    raw = logo_bytes(uri)
    if not raw or len(raw) > MAX_LOGO_BYTES:
        return ""
    try:
        from PIL import Image

        Image.open(io.BytesIO(raw)).verify()
        return uri
    except Exception:
        return ""


# ---------------------------------------------------------------------------
# Payload (backup file) format
# ---------------------------------------------------------------------------

def make_payload(settings: Dict, library: List[Dict], job: Optional[Dict]) -> Dict:
    return {
        "app": "jobcost",
        "dataVersion": DATA_VERSION,
        "settings": settings,
        "library": library,
        "job": job,
    }


def dumps(payload: Dict) -> str:
    return json.dumps(payload, indent=2, ensure_ascii=False, default=str, sort_keys=True)


def parse_payload(text: str) -> Tuple[Dict, List[Dict], Optional[Dict]]:
    """Validate and normalise a backup. Raises ValueError with a friendly message."""
    if len(text) > MAX_IMPORT_BYTES:
        raise ValueError("That file is too large to be a backup.")
    try:
        raw = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"That is not a valid JSON file ({exc.msg}).") from exc
    if not isinstance(raw, dict) or raw.get("app") != "jobcost":
        raise ValueError("That file is not a Job Costing backup.")

    settings = normalise_settings(raw.get("settings"))
    settings["logo"] = valid_logo(settings.get("logo", ""))
    tz = settings["timezone"]

    library: List[Dict] = []
    seen = set()
    entries = raw.get("library")
    if isinstance(entries, list):
        for entry in entries[:MAX_JOBS]:
            if not isinstance(entry, dict) or not isinstance(entry.get("job"), dict):
                continue
            job = normalise_job(entry["job"], tz)
            if job["id"] in seen:
                continue
            seen.add(job["id"])
            library.append({
                "id": txt(entry.get("id")) or new_id(),
                "saved_at": txt(entry.get("saved_at")) or now_iso(tz),
                "name": txt(entry.get("name")) or job["title"] or job["client"] or "Untitled job",
                "job": job,
            })

    job = normalise_job(raw["job"], tz) if isinstance(raw.get("job"), dict) else None
    return settings, library, job


# ---------------------------------------------------------------------------
# Optional local autosave
# ---------------------------------------------------------------------------

def data_path() -> Optional[str]:
    p = os.environ.get("JOBCOST_DATA_FILE", "").strip()
    return os.path.expanduser(p) if p else None


def load_file() -> Optional[Tuple[Dict, List[Dict], Optional[Dict]]]:
    path = data_path()
    if not path or not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return parse_payload(fh.read())
    except (OSError, ValueError):
        return None


def save_file(payload: Dict) -> bool:
    """Atomic write so a crash never leaves a half-written file."""
    path = data_path()
    if not path:
        return False
    try:
        folder = os.path.dirname(os.path.abspath(path))
        os.makedirs(folder, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=folder, prefix=".jobcost-", suffix=".tmp")
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(dumps(payload))
        os.replace(tmp, path)
        return True
    except OSError:
        return False

# ======================================================================
# USER INTERFACE
# ======================================================================

#!/usr/bin/env python3
"""Job Costing & Quotation Calculator (Streamlit).

Cost a job, price it to your target margin, issue locked quotes and invoices as PDF,
track payments, and keep a job library with JSON backup.

Run:  streamlit run app.py
"""




ss = st.session_state

PAGES = ["Job costing", "Quote & invoice", "Job library", "Business settings"]

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@500;600&display=swap');
:root { --ink:#0B1220; --muted:#475569; --line:#D0D7E2; --soft:#F1F5F9; --accent:#1D4ED8; --side:#0B1526;
  --good:#047857; --warn:#B45309; --bad:#B91C1C; --good-bg:#D1FAE5; --warn-bg:#FEF3C7; --bad-bg:#FEE2E2; --neutral-bg:#E2E8F0; }
html, body, [class*="css"] { font-family: Inter, "Segoe UI", system-ui, sans-serif; }
.block-container { padding-top: 1.2rem; max-width: 1280px; }
h1.pg { font-size: 1.45rem; font-weight: 700; letter-spacing: -0.03em; margin: 0 0 .5rem; line-height: 1.25; color: var(--ink); }
.crumb { font-size:.72rem; font-weight:700; letter-spacing:.07em; text-transform:uppercase; color: var(--accent); margin-bottom:.2rem; }
.hero { background: var(--side); color:#F8FAFC; border-radius:8px; padding:1.1rem 1.15rem 1rem; margin-bottom:.85rem; }
.hero-label { font-size:.7rem; font-weight:700; letter-spacing:.06em; text-transform:uppercase; color:#94A3B8; margin-bottom:.25rem; }
.hero-price { font-family:"JetBrains Mono",Consolas,monospace; font-size:2rem; font-weight:600; letter-spacing:-.03em; line-height:1.15; color:#fff; }
.hero-sub { font-size:.88rem; color:#CBD5E1; margin-top:.35rem; }
.hero-flag { font-size:.8rem; color:#FCD34D; margin-top:.5rem; line-height:1.4; }
.hero-stats { display:grid; grid-template-columns:repeat(4,1fr); gap:.7rem 1rem; margin-top:.9rem; padding-top:.85rem; border-top:1px solid #1E334D; }
.hero-stat-label { font-size:.65rem; font-weight:700; letter-spacing:.05em; text-transform:uppercase; color:#94A3B8; }
.hero-stat-value { font-family:"JetBrains Mono",monospace; font-size:1.05rem; font-weight:600; color:#fff; margin-top:.12rem; }
.verdict { border-radius:6px; padding:.75rem .9rem; font-size:.9rem; line-height:1.5; margin-top:.55rem; }
.verdict strong { display:block; font-weight:700; margin-bottom:.2rem; }
.v-good{background:var(--good-bg);color:var(--good)} .v-warn{background:var(--warn-bg);color:var(--warn)}
.v-bad{background:var(--bad-bg);color:var(--bad)} .v-neutral{background:var(--neutral-bg);color:var(--ink)}
.brk { display:flex; justify-content:space-between; align-items:baseline; padding:.42rem 0; border-bottom:1px solid var(--line); font-size:.9rem; gap:.5rem; }
.brk:last-child { border-bottom:none; }
.brk .nm { flex:1; min-width:0; } .brk .am { font-family:"JetBrains Mono",monospace; font-weight:500; white-space:nowrap; }
.brk .pc { color:var(--muted); font-size:.78rem; min-width:3rem; text-align:right; margin-left:.35rem; display:inline-block; }
.brk.str .nm, .brk.str .am { font-weight:700; }
.dot { display:inline-block; width:8px; height:8px; border-radius:2px; margin-right:.45rem; }
.segbar { display:flex; height:12px; border-radius:3px; overflow:hidden; margin:.45rem 0 .8rem; background:var(--soft); }
.segbar > div { height:100%; }
.banner { background:#DBEAFE; color:#1E3A5F; font-size:.9rem; padding:.7rem .95rem; border-radius:6px; margin-bottom:.9rem; border:1px solid #BFDBFE; line-height:1.45; }
.lockbar { background:#ECFDF5; color:#065F46; font-size:.88rem; padding:.6rem .85rem; border-radius:6px; border:1px solid #A7F3D0; margin-bottom:.6rem; }
.head { display:flex; justify-content:space-between; align-items:center; font-weight:600; }
.chip { background:var(--neutral-bg); color:var(--ink); font-size:.8rem; font-weight:700; font-family:"JetBrains Mono",monospace; padding:.2rem .55rem; border-radius:4px; }
.tiles { display:grid; grid-template-columns:repeat(4,1fr); gap:.6rem; margin-bottom:.8rem; }
.tile { background:#fff; border:1px solid var(--line); border-radius:8px; padding:.7rem .85rem; }
.tile .l { font-size:.68rem; font-weight:700; letter-spacing:.05em; text-transform:uppercase; color:var(--muted); }
.tile .v { font-family:"JetBrains Mono",monospace; font-weight:600; font-size:1.15rem; margin-top:.15rem; }
.price { font-family:"JetBrains Mono",monospace; font-weight:600; font-size:1.05rem; padding-top:.3rem; }
.pill { display:inline-block; font-size:.72rem; font-weight:700; padding:.1rem .5rem; border-radius:99px; background:var(--neutral-bg); }
@media (max-width: 768px) {
  .block-container { padding-left:.65rem; padding-right:.65rem; }
  .hero-price { font-size:1.55rem; } .hero-stats { grid-template-columns:1fr 1fr; } .tiles { grid-template-columns:1fr 1fr; }
  .stButton > button, .stDownloadButton > button { min-height:2.85rem; width:100%; }
  input, textarea { font-size:16px !important; }
}
</style>
"""


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------

def md(s) -> str:
    """Escape '$' so Streamlit markdown never treats money as LaTeX."""
    return str(s).replace("$", "\\$")


def tz() -> str:
    return ss.S.get("timezone") or "UTC"


def jk(name: str) -> str:
    """Widget key, scoped to the current job so loading another job resets the widgets."""
    return f"j{ss.jkey}_{name}"


def set_job(job: dict) -> None:
    old = f"j{ss.get('jkey', 0)}_"
    for k in [k for k in ss.keys() if isinstance(k, str) and k.startswith(old)]:
        del ss[k]
    ss.J = job
    ss.jkey = ss.get("jkey", 0) + 1


def clear_prefix(prefix: str) -> None:
    for k in [k for k in ss.keys() if isinstance(k, str) and k.startswith(prefix)]:
        del ss[k]


def goto(page: str) -> None:
    ss._goto = page


def text_field(label, data, name, key, *, area=False, **kw):
    """Text widget initialised from `data` only when it has no state yet (zero/empty safe)."""
    if key not in ss:
        ss[key] = txt(data.get(name, ""))
    data[name] = (st.text_area if area else st.text_input)(label, key=key, **kw)
    return data[name]


def num_field(label, data, name, key, default, *, as_int=False, **kw):
    """Number widget. `default` applies only when the field is missing, never when it is 0."""
    if key not in ss:
        v = data.get(name, default)
        ss[key] = int(dec(v)) if as_int else float(dec(v))
    data[name] = st.number_input(label, key=key, **kw)
    return data[name]


def jtext(label, name, **kw):
    return text_field(label, ss.J, name, jk(name), **kw)


def jnum(label, name, default, **kw):
    return num_field(label, ss.J, name, jk(name), default, **kw)


def stext(label, name, **kw):
    return text_field(label, ss.S, name, f"s_{name}", **kw)


def snum(label, name, default, **kw):
    return num_field(label, ss.S, name, f"s_{name}", default, **kw)


# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------

def init_state() -> None:
    """Create session state once. A version marker (not just 'S') guards it, so state
    left by an older version of the app is migrated instead of crashing the new code."""
    if ss.get("_ready") == DATA_VERSION:
        return
    # Drop widget keys from older versions; they may hold values of the wrong type.
    for k in [k for k in ss.keys() if isinstance(k, str) and (k.startswith("j") and "_" in k[:6] or k.startswith("s_"))]:
        del ss[k]
    try:
        old_s, old_j, old_lib = ss.get("S"), ss.get("J"), ss.get("library")
    except Exception:
        old_s = old_j = old_lib = None
    loaded = load_file()
    if loaded:
        ss.S, ss.library, job = loaded
        ss.J = job or blank_job(ss.S["timezone"])
    elif isinstance(old_s, dict):
        ss.S = normalise_settings(old_s)
        ss.J = normalise_job(old_j, ss.S["timezone"]) if isinstance(old_j, dict) else blank_job(ss.S["timezone"])
        lib = []
        for e in old_lib if isinstance(old_lib, list) else []:
            if isinstance(e, dict) and isinstance(e.get("job"), dict):
                nj = normalise_job(e["job"], ss.S["timezone"])
                lib.append({"id": txt(e.get("id")) or new_id(), "saved_at": txt(e.get("saved_at")) or now_iso(ss.S["timezone"]),
                            "name": txt(e.get("name")) or nj["title"] or "Untitled job", "job": nj})
        ss.library = lib
    else:
        ss.S = default_settings()
        ss.library = []
        ss.J = sample_job(ss.S["timezone"])
    ss.jkey = 0
    ss.nav = "Job costing"
    ss._sig = None
    ss._confirm_del = None
    ss._ready = DATA_VERSION


def upsert_library(job: dict) -> str:
    name = (job.get("title") or job.get("client") or "Untitled job").strip()
    for e in ss.library:
        if e["job"].get("id") == job["id"]:
            e.update(saved_at=now_iso(tz()), name=name, job=deepcopy(job))
            return "Updated"
    ss.library.append({"id": new_id(), "saved_at": now_iso(tz()), "name": name, "job": deepcopy(job)})
    return "Saved"


def autosave() -> None:
    if not data_path():
        return
    payload = make_payload(ss.S, ss.library, ss.J)
    sig = hashlib.sha1(dumps(payload).encode("utf-8")).hexdigest()
    if sig != ss.get("_sig"):
        if save_file(payload):
            ss._sig = sig


# ---------------------------------------------------------------------------
# HTML fragments (rendered with st.html: no markdown, so '$' is never mangled)
# ---------------------------------------------------------------------------

def hero_html(S, r) -> str:
    M = lambda v: money(S, v)
    tn = S.get("taxName") or "Tax"
    flag = ""
    if r["min_applied"]:
        flag = f'<div class="hero-flag">Your minimum job price of {esc(M(S.get("minPrice")))} applies. The costed price was {esc(M(r["raw"]))}.</div>'
    elif r["rounded"]:
        flag = f'<div class="hero-flag">Rounded up from {esc(M(r["raw"]))}.</div>'
    sub = f'{esc(tn)} {esc(M(r["tax"]))} &nbsp;|&nbsp; Total {esc(M(r["total"]))}' if S.get("taxOn") else f'Total {esc(M(r["total"]))}'
    lab = "RECOMMENDED QUOTE" + (f" (EXCL. {esc(tn.upper())})" if S.get("taxOn") else "")
    stat = lambda l, v: f'<div><div class="hero-stat-label">{l}</div><div class="hero-stat-value">{esc(v)}</div></div>'
    return (
        f'<div class="hero"><div class="hero-label">{lab}</div><div class="hero-price">{esc(M(r["price"]))}</div>'
        f'<div class="hero-sub">{sub}</div>{flag}<div class="hero-stats">'
        + stat("Total cost", M(r["cost"])) + stat("Profit", M(r["profit"]))
        + stat("Margin", f'{float(r["margin"]) * 100:.1f}%') + stat("Profit per hour", M(r["pph"]))
        + "</div></div>"
    )


SEGS = [("labour", "#2457E6"), ("travel", "#0E8A8A"), ("materials", "#C27A0E"),
        ("other", "#7A4FBF"), ("overhead", "#8393A3"), ("profit", "#12A266")]


def seg_bar(r) -> str:
    if r["price"] <= 0:
        return ""
    parts = []
    for k, col in SEGS:
        p = float(max(r[k], 0) / r["price"] * 100)
        if p > 0.3:
            parts.append(f'<div style="width:{p:.2f}%;background:{col}"></div>')
    return f'<div class="segbar">{"".join(parts)}</div>'


def breakdown_html(S, r) -> str:
    rows = [
        ("labour", "Labour", "#2457E6", False), ("travel", "Travel", "#0E8A8A", False),
        ("materials", "Materials & supplies", "#C27A0E", False), ("other", "Other costs", "#7A4FBF", False),
        ("direct", "Direct costs", None, True), ("overhead", "Overhead", "#8393A3", False),
        ("cost", "Total cost", None, True), ("profit", "Profit", "#12A266", False), ("price", "Quote price", None, True),
    ]
    out = []
    for key, label, col, strong in rows:
        pc = f'{float(r[key] / r["price"] * 100):.1f}%' if r["price"] > 0 else ""
        dot = f'<span class="dot" style="background:{col}"></span>' if col else ""
        out.append(
            f'<div class="brk{" str" if strong else ""}"><span class="nm">{dot}{label}</span>'
            f'<span><span class="am">{esc(money(S, r[key]))}</span><span class="pc">{pc}</span></span></div>'
        )
    return "".join(out)


# ---------------------------------------------------------------------------
# Page: Job costing
# ---------------------------------------------------------------------------

def _materials_editor(J) -> None:
    ed_key, init_key = jk("mat_ed"), jk("mat_init")
    if ed_key not in ss or init_key not in ss:
        rows = J.get("materials") or []
        ss[init_key] = pd.DataFrame({
            "Item": pd.Series([txt(m.get("d")) for m in rows], dtype="object"),
            "Qty": pd.Series([float(dec(m.get("q"))) for m in rows], dtype="float64"),
            "Unit cost": pd.Series([float(dec(m.get("c"))) for m in rows], dtype="float64"),
        })
    edited = st.data_editor(
        ss[init_key], num_rows="dynamic", key=ed_key, hide_index=True, width="stretch",
        column_config={
            "Item": st.column_config.TextColumn("Item"),
            "Qty": st.column_config.NumberColumn("Qty", min_value=0, default=1.0, format="%.2f"),
            "Unit cost": st.column_config.NumberColumn("Unit cost", min_value=0, default=0.0, format="%.2f"),
        },
    )
    out = []
    for rec in edited.to_dict("records"):
        item, q, c = txt(rec.get("Item")).strip(), pos(rec.get("Qty")), pos(rec.get("Unit cost"))
        if item or c > 0:
            out.append({"d": item, "q": float(q), "c": float(c)})
    J["materials"] = out


def _other_editor(J) -> None:
    ed_key, init_key = jk("oth_ed"), jk("oth_init")
    if ed_key not in ss or init_key not in ss:
        rows = J.get("other") or []
        ss[init_key] = pd.DataFrame({
            "Description": pd.Series([txt(o.get("d")) for o in rows], dtype="object"),
            "Amount": pd.Series([float(dec(o.get("a"))) for o in rows], dtype="float64"),
        })
    edited = st.data_editor(
        ss[init_key], num_rows="dynamic", key=ed_key, hide_index=True, width="stretch",
        column_config={
            "Description": st.column_config.TextColumn("Description"),
            "Amount": st.column_config.NumberColumn("Amount", min_value=0, default=0.0, format="%.2f"),
        },
    )
    out = []
    for rec in edited.to_dict("records"):
        d, a = txt(rec.get("Description")).strip(), pos(rec.get("Amount"))
        if d or a > 0:
            out.append({"d": d, "a": float(a)})
    J["other"] = out


def _cb_status() -> None:
    ss.J["status"] = ss[jk("status")]


def page_job() -> None:
    S, J = ss.S, ss.J
    st.html('<div class="crumb">Job costing</div>')
    title_box = st.container()
    hero_box = st.container()

    if J.get("sample"):
        st.html('<div class="banner">Sample job loaded: a two-person end-of-lease clean that a gut-feel quote '
                "would underprice. Change any figure to cost your own job.</div>")
    if J.get("issued"):
        kinds = " and ".join(sorted(J["issued"]))
        st.html(f'<div class="lockbar">This job has an issued {kinds}. Changes here do not alter it; '
                "unlock it on the Quote &amp; invoice page to revise.</div>")

    left, right = st.columns([1.4, 1], gap="large")

    with left:
        with st.container(border=True):
            st.markdown("**Job details**")
            st.caption("Shown on the quote and invoice.")
            c1, c2 = st.columns(2)
            with c1:
                jtext("Job title", "title")
            with c2:
                jtext("Customer", "client")
            jtext("Scope of work", "scope", area=True, height=88)

        with st.container(border=True):
            lab_head = st.empty()
            c1, c2 = st.columns(2)
            with c1:
                jnum("People on the job", "people", 1.0, min_value=0.0, step=1.0)
            with c2:
                jnum("Hours on site, each", "hours", 0.0, min_value=0.0, step=0.25)
            lab_cap = st.empty()

        with st.container(border=True):
            trv_head = st.empty()
            c1, c2 = st.columns(2)
            with c1:
                jnum("Distance, return trip (km)", "km", 0.0, min_value=0.0, step=1.0)
            with c2:
                jnum("Travel time, return trip (hrs)", "travelHours", 0.0, min_value=0.0, step=0.25)
            trv_cap = st.empty()

        with st.container(border=True):
            mat_head = st.empty()
            st.caption("Everything you buy for this job. If you are registered for GST, enter costs excluding GST.")
            _materials_editor(J)
            mat_cap = st.empty()

        with st.container(border=True):
            oth_head = st.empty()
            st.caption("Equipment hire, subcontractors, tip fees and permits.")
            _other_editor(J)

    # Every input above has now updated J, so the figures below are never one edit behind.
    r = calc(S, J)
    M = lambda v: money(S, v)
    chip = lambda name, v: f'<div class="head"><span>{name}</span><span class="chip">{esc(M(v))}</span></div>'
    lab_head.html(chip("Labour", r["labour"]))
    trv_head.html(chip("Travel", r["travel"]))
    mat_head.html(chip("Materials &amp; supplies", r["materials"]))
    oth_head.html(chip("Other costs", r["other"]))
    lab_cap.caption(
        md(f"{r['on_site']:.2f} hours on site at {M(pos(S.get('labourRate')))} per hour")
        if r["on_site"] else "Enter the people and hours on site."
    )
    trv_cap.caption(md(f"Vehicle {M(r['vehicle'])} plus travel time {M(r['travel_time'])}. Travel time is paid to every person."))
    if r["materials_allowance"] > 0:
        mat_cap.caption(md(f"Includes a {M(r['materials_allowance'])} wastage and handling allowance."))

    title_box.html(f'<h1 class="pg">{esc(J.get("title") or "New job")}</h1>')
    hero_box.html(hero_html(S, r))

    with right:
        with st.container(border=True):
            st.markdown("**Compare with your usual quote**")
            jnum("Your usual quote, before tax", "gut", 0.0, min_value=0.0, step=10.0)
            tone, head, body = verdict(S, J, r)
            st.html(f'<div class="verdict v-{tone}"><strong>{esc(head)}</strong>{esc(body)}</div>')

        with st.container(border=True):
            st.markdown("**Where the price goes**")
            st.html(seg_bar(r) + breakdown_html(S, r))

        with st.container(border=True):
            st.markdown("**Job status**")
            ss[jk("status")] = J.get("status", "Draft")
            st.selectbox("Status", STATUSES, key=jk("status"), on_change=_cb_status, label_visibility="collapsed")

    st.divider()
    a, b, c = st.columns(3)
    if a.button("New blank job", width="stretch"):
        set_job(blank_job(tz()))
        st.rerun()
    if b.button("Load sample job", width="stretch"):
        set_job(sample_job(tz()))
        st.rerun()
    if c.button("Save to library", type="primary", width="stretch"):
        J["saved_at"] = now_iso(tz())
        verb = upsert_library(J)
        st.toast(md(f"{verb} “{J.get('title') or J.get('client') or 'Untitled job'}”"))


# ---------------------------------------------------------------------------
# Page: Quote & invoice
# ---------------------------------------------------------------------------

def sync_doc_fields() -> None:
    """Pull the freshest widget values into J (callbacks run before the script body)."""
    J = ss.J
    for name in ("custEmail", "custAddress", "custAbn"):
        if jk(name) in ss:
            J[name] = txt(ss[jk(name)])
    if jk("itemised") in ss:
        J["itemised"] = bool(ss[jk("itemised")])


def _num_name(kind: str) -> str:
    return "quoteNo" if kind == "quote" else "invoiceNo"


def _issue_number(kind: str, typed: str) -> str:
    """Final document number: keeps a unique typed number, otherwise allocates the next one."""
    number = typed.strip()
    if not number or number_in_use(ss.library, ss.J, kind, number):
        return allocate_number(ss.S, kind)
    if number == peek_number(ss.S, kind):
        allocate_number(ss.S, kind)
    return number


def cb_doc_type() -> None:
    ss.J["docType"] = ss[jk("docType")]
    ss.J["emailEdited"] = False


def cb_number() -> None:
    kind = ss.J["docType"]
    ss.J[_num_name(kind)] = txt(ss[jk(_num_name(kind))])
    ss.J["emailEdited"] = False


def cb_date() -> None:
    d = ss.get(jk("issueDate"))
    if isinstance(d, dt.date):
        ss.J["issueDate"] = d.isoformat()


def cb_email_edited() -> None:
    ss.J["emailEdited"] = True


def cb_email_reset() -> None:
    ss.J["emailEdited"] = False


def cb_issue() -> None:
    S, J = ss.S, ss.J
    sync_doc_fields()
    kind = J["docType"]
    name = _num_name(kind)
    number = _issue_number(kind, txt(ss.get(jk(name), J.get(name))))
    d = ss.get(jk("issueDate"))
    issue = d if isinstance(d, dt.date) else parse_date(J.get("issueDate"), today(tz()))
    J[name], J["issueDate"] = number, issue.isoformat()
    J["issued"][kind] = make_snapshot(S, J, kind, number, issue, tz())
    if kind == "quote" and J.get("status") == "Draft":
        J["status"] = "Quote sent"
    if kind == "invoice" and J.get("status") != "Paid":
        J["status"] = "Invoiced"
    sync_status(S, J)
    J["emailEdited"] = False
    upsert_library(J)
    st.toast(md(f"{'Quote' if kind == 'quote' else 'Invoice'} {number} issued. Figures are now locked."))


def cb_unlock() -> None:
    kind = ss.J["docType"]
    ss.J["issued"].pop(kind, None)
    ss.J["emailEdited"] = False
    st.toast("Unlocked. The document now follows the live figures again.")


def cb_convert() -> None:
    S, J = ss.S, ss.J
    sync_doc_fields()
    quote_snap = (J.get("issued") or {}).get("quote")
    J["docType"] = "invoice"
    J["emailEdited"] = False
    if not quote_snap:
        return
    number = _issue_number("invoice", "")
    issue = today(tz())
    snap = deepcopy(quote_snap)
    snap.update(kind="invoice", number=number, issueDate=issue.isoformat(), issuedAt=now_iso(tz()))
    snap["S"]["payDetails"], snap["S"]["payTerms"] = S["payDetails"], S["payTerms"]
    J["issued"]["invoice"] = snap
    J["invoiceNo"], J["issueDate"] = number, issue.isoformat()
    if J.get("status") != "Paid":
        J["status"] = "Invoiced"
    upsert_library(J)
    st.toast(md(f"Invoice {number} created from the accepted quote."))


def page_doc() -> None:
    S, J = ss.S, ss.J
    st.html('<div class="crumb">Quote &amp; invoice</div>')
    title_box = st.container()
    form, preview = st.columns([1, 1.2], gap="medium")

    with form:
        with st.container(border=True):
            st.markdown("**Document**")
            ss[jk("docType")] = J.get("docType", "quote")
            st.radio("Type", ["quote", "invoice"], key=jk("docType"), horizontal=True, on_change=cb_doc_type,
                     format_func=lambda x: "Quote" if x == "quote" else "Invoice", label_visibility="collapsed")
            kind = J["docType"]
            locked = bool((J.get("issued") or {}).get(kind))

            name = _num_name(kind)
            if not txt(J.get(name)).strip() and not locked:
                J[name] = peek_number(S, kind)
            ss[jk(name)] = J[name]
            st.text_input(f"{'Quote' if kind == 'quote' else 'Invoice'} number", key=jk(name), on_change=cb_number, disabled=locked)
            if not locked and number_in_use(ss.library, J, kind, txt(J.get(name))):
                st.warning("Another saved job already uses this number. A new one is assigned when you issue it.")

            try:
                ss[jk("issueDate")] = parse_date(J.get("issueDate"), today(tz()))
                st.date_input("Issue date", key=jk("issueDate"), format="DD/MM/YYYY", on_change=cb_date, disabled=locked)
            except Exception:
                pass
            cb_date()
            st.checkbox("Show itemised lines", key=jk("itemised"), disabled=locked,
                        value=bool(J.get("itemised")) if jk("itemised") not in ss else None,
                        help="Splits the price into labour, materials and other costs. Overhead and profit stay private.")

        with st.container(border=True):
            st.markdown("**Customer**")
            text_field("Customer email", J, "custEmail", jk("custEmail"), placeholder="customer@email.com")
            text_field("Customer address", J, "custAddress", jk("custAddress"), area=True, height=72, disabled=locked)
            text_field("Customer ABN (optional)", J, "custAbn", jk("custAbn"), disabled=locked)

        if kind == "invoice":
            _payments_card(J)

    # Everything below uses the document exactly as it will be issued (frozen if locked).
    S2, J2, snap = doc_context(S, J, kind)
    r = calc(S2, J2)
    m = build_model(S2, J2, r)
    title_box.html(f'<h1 class="pg">{esc(m["title"])} {esc(m["number"])}</h1>')

    with form:
        with st.container(border=True):
            st.markdown("**Issue**")
            if snap:
                st.html(f'<div class="lockbar">Issued {esc(fmt_date(parse_date(snap["issueDate"])))}. '
                        "Prices, rates and wording are locked, so changing your rates later will not alter this document.</div>")
                c1, c2 = st.columns(2)
                c1.button("Unlock to revise", on_click=cb_unlock, width="stretch")
                c2.button("Re-issue with current figures", on_click=_reissue, width="stretch")
            else:
                st.caption("Issuing locks the figures and wording, saves the job to your library and uses up the document number.")
                st.button(f"Issue this {kind}", type="primary", on_click=cb_issue, width="stretch")
            if kind == "quote":
                st.button("Convert to invoice", on_click=cb_convert, width="stretch",
                          help="Creates an invoice from the issued quote's locked figures." if snap else
                          "Switches to an invoice using the current figures.")
            if (kind == "invoice" and S2.get("taxOn") and S2.get("currency") == "AUD" and r["total"] >= 1000
                    and not (J.get("client") and (J.get("custAbn") or J.get("custAddress")))):
                st.warning("Tax invoices of $1,000 or more should identify the buyer (name and address or ABN). "
                           "Check the requirements with your accountant.")

        with st.container(border=True):
            st.markdown("**1. Download the PDF**")
            st.caption("Save the file, then attach it when you send the email.")
            fname = safe_filename(f"{m['title']}-{m['number']}") + ".pdf"
            try:
                pdf = make_pdf_bytes(m, logo_bytes(S.get("logo", "")))
                st.download_button("Save as PDF", data=pdf, file_name=fname, mime="application/pdf",
                                   type="primary", width="stretch", on_click="ignore", key="dl_pdf")
            except Exception as exc:  # pragma: no cover - surfaced to the user
                st.error(f"Could not create the PDF: {exc}")
            st.download_button("Download as text", data=model_text(m), file_name=safe_filename(m["number"] or "document") + ".txt",
                               mime="text/plain", width="stretch", on_click="ignore", key="dl_txt")

        _email_card(S2, J, J2, m)

    with preview:
        st.markdown("**Preview**")
        st.caption("Live layout, matching the downloaded PDF.")
        st.iframe(render_preview(m), height=700)


def _reissue() -> None:
    cb_unlock()
    cb_issue()


def _payments_card(J) -> None:
    S = ss.S
    with st.container(border=True):
        st.markdown("**Payments received**")
        pays = J.setdefault("payments", [])
        if not pays:
            st.caption("No payments recorded yet.")
        for i, p in enumerate(list(pays)):
            c1, c2, c3 = st.columns([2, 2, 1])
            c1.write(fmt_date(parse_date(p.get("date"))))
            c2.write(money(S, p.get("amount")).replace("$", "\\$"))
            if c3.button("Remove", key=jk(f"rmpay{i}")):
                pays.pop(i)
                sync_status(S, J)
                st.rerun()
        with st.form(jk("payform"), clear_on_submit=True, border=False):
            c1, c2 = st.columns(2)
            when = c1.date_input("Date received", value=today(tz()), format="DD/MM/YYYY")
            amt = c2.number_input("Amount (incl. tax)", min_value=0.0, value=0.0, step=10.0)
            note = st.text_input("Note (optional)", placeholder="Deposit, bank transfer ...")
            if st.form_submit_button("Add payment", width="stretch") and amt > 0:
                pays.append({"date": when.isoformat(), "amount": float(amt), "note": note})
                sync_status(S, J)
                st.rerun()


def _email_card(S2, J, J2, m) -> None:
    with st.container(border=True):
        st.markdown("**2. Send by email**")
        st.caption("Opens your email app with the message filled in. Attach the PDF you just downloaded before sending.")
        ks, kb = jk("emailSubject"), jk("emailBody")
        subj_t, body_t = email_template(S2, J2, m)
        if not J.get("emailEdited"):
            ss[ks], ss[kb] = subj_t, body_t
        else:
            ss.setdefault(ks, J.get("emailSubject", subj_t))
            ss.setdefault(kb, J.get("emailBody", body_t))
        to = txt(J.get("custEmail")).strip()
        st.caption(f"To: {to}" if to else "Add the customer email above to fill in the To field.")
        st.text_input("Subject", key=ks, on_change=cb_email_edited)
        st.text_area("Message", key=kb, height=220, on_change=cb_email_edited)
        J["emailSubject"], J["emailBody"] = ss[ks], ss[kb]

        body_crlf = ss[kb].replace("\r\n", "\n").replace("\n", "\r\n")
        mailto = f"mailto:{quote(to, safe='@,;')}?subject={quote(ss[ks], safe='')}&body={quote(body_crlf, safe='')}"
        c1, c2 = st.columns(2)
        c1.link_button("Open email app", mailto, type="primary", width="stretch")
        c2.button("Reset to template", on_click=cb_email_reset, width="stretch")
        if len(mailto) > 1900:
            st.caption("This message is long; some email apps cut it off. Use the copy icon below instead.")
        with st.expander("Copy message text"):
            st.code(f"To: {to}\nSubject: {ss[ks]}\n\n{ss[kb]}", language=None)


# ---------------------------------------------------------------------------
# Page: Library
# ---------------------------------------------------------------------------

def _tile(label: str, value: str) -> str:
    return f'<div class="tile"><div class="l">{esc(label)}</div><div class="v">{esc(value)}</div></div>'


def page_library() -> None:
    S = ss.S
    st.html('<div class="crumb">Job library</div><h1 class="pg">Saved jobs</h1>')
    lib = ss.library
    if not lib:
        st.info("No saved jobs yet. Cost a job and click **Save to library**.")
        return

    figs = {e["id"]: entry_figures(S, e["job"]) for e in lib}
    open_quotes = sum((figs[e["id"]]["total"] for e in lib if e["job"].get("status") in ("Quote sent", "Accepted")), ZERO)
    outstanding = sum((f["outstanding"] for f in figs.values()), ZERO)
    received = sum((f["paid"] for f in figs.values()), ZERO)
    st.html('<div class="tiles">' + _tile("Jobs saved", str(len(lib))) + _tile("Open quotes", money(S, open_quotes))
            + _tile("Outstanding", money(S, outstanding)) + _tile("Received", money(S, received)) + "</div>")

    c1, c2 = st.columns([3, 1.4])
    q = c1.text_input("Search", "", placeholder="Search by title, customer or notes").strip().lower()
    status_filter = c2.selectbox("Status", ["All"] + STATUSES)

    shown = 0
    for entry in sorted(lib, key=lambda x: x.get("saved_at") or "", reverse=True):
        job = entry["job"]
        name = entry.get("name") or job.get("title") or "Untitled"
        hay = f"{name} {job.get('client', '')} {job.get('scope', '')}".lower()
        if q and q not in hay:
            continue
        if status_filter != "All" and job.get("status") != status_filter:
            continue
        shown += 1
        f = figs[entry["id"]]
        saved = (entry.get("saved_at") or "")[:16].replace("T", " ")
        with st.container(border=True):
            a, b, c = st.columns([3, 1.4, 1.8])
            with a:
                st.markdown(md(f"**{name}**"))
                st.caption(md(f"{job.get('client') or '-'} · {saved}"))
                st.html(f'<span class="pill">{esc(job.get("status", "Draft"))}</span>')
            with b:
                st.html(f'<div class="price">{esc(money(S, f["total"]))}</div>'
                        f'<div style="font-size:.72rem;color:#475569">{"locked, incl. tax" if f["locked"] else "at current rates"}</div>')
            with c:
                if ss._confirm_del == entry["id"]:
                    st.caption("Delete this job?")
                    y, n = st.columns(2)
                    if y.button("Yes", key=f"y{entry['id']}", type="primary", width="stretch"):
                        ss.library = [e for e in lib if e["id"] != entry["id"]]
                        ss._confirm_del = None
                        st.rerun()
                    if n.button("No", key=f"n{entry['id']}", width="stretch"):
                        ss._confirm_del = None
                        st.rerun()
                else:
                    x, y, z = st.columns(3)
                    if x.button("Load", key=f"ld{entry['id']}", width="stretch"):
                        set_job(normalise_job(deepcopy(job), tz()))
                        goto("Job costing")
                        st.rerun()
                    if y.button("Copy", key=f"cp{entry['id']}", width="stretch"):
                        nj = normalise_job(deepcopy(job), tz())
                        nj.update(id=new_id(), issued={}, payments=[], quoteNo="", invoiceNo="", status="Draft",
                                  docType="quote", emailEdited=False, sample=False)
                        ss.library.append({"id": new_id(), "saved_at": now_iso(tz()), "name": name + " (copy)", "job": nj})
                        st.rerun()
                    if z.button("Delete", key=f"dl{entry['id']}", width="stretch"):
                        ss._confirm_del = entry["id"]
                        st.rerun()
    st.caption(f"{shown} of {len(lib)} jobs")


# ---------------------------------------------------------------------------
# Page: Settings
# ---------------------------------------------------------------------------

def _timezones() -> list:
    try:
        from zoneinfo import available_timezones
        zones = sorted(available_timezones())
    except Exception:
        zones = []
    return zones or ["UTC", "Australia/Sydney"]


def _logo_card() -> None:
    S = ss.S
    with st.container(border=True):
        st.markdown("**Logo**")
        st.caption("Optional. Printed at the top of quotes and invoices. PNG or JPG.")
        if S.get("logo"):
            raw = logo_bytes(S["logo"])
            if raw:
                st.image(raw, width=160)
            if st.button("Remove logo"):
                S["logo"] = ""
                st.rerun()
        up = st.file_uploader("Upload logo", type=["png", "jpg", "jpeg"], key="logo_up", label_visibility="collapsed")
        if up is not None and ss.get("_logo_id") != up.file_id:
            try:
                S["logo"] = process_logo(up.getvalue())
                ss._logo_id = up.file_id
                st.rerun()
            except Exception as exc:
                st.error(f"Could not use that image: {exc}")


def _data_tab() -> None:
    S = ss.S
    with st.container(border=True):
        st.markdown("**Backup**")
        path = data_path()
        if path:
            st.success(f"Autosave is on. Your data is saved to {path}.")
        else:
            st.warning("This session is not saved automatically. Download a backup regularly and restore it here later.")
        payload = dumps(make_payload(S, ss.library, ss.J))
        st.download_button("Download backup (JSON)", data=payload, file_name=f"jobcost-backup-{today(tz()).isoformat()}.json",
                           mime="application/json", type="primary", on_click="ignore", key="dl_backup")

    with st.container(border=True):
        st.markdown("**Restore from a backup**")
        st.caption("Replaces your settings, library and current job with the contents of the file.")
        up = st.file_uploader("Backup file", type=["json"], key="restore_up", label_visibility="collapsed")
        if up is not None:
            ok = st.checkbox("I understand this replaces my current data", key="restore_ok")
            if st.button("Restore backup", disabled=not ok):
                try:
                    s2, lib2, job2 = parse_payload(up.getvalue().decode("utf-8", "replace"))
                except ValueError as exc:
                    st.error(str(exc))
                else:
                    ss.S, ss.library = s2, lib2
                    clear_prefix("s_")
                    set_job(job2 or blank_job(s2["timezone"]))
                    st.toast(f"Restored {len(lib2)} saved jobs.")
                    st.rerun()

    with st.container(border=True):
        st.markdown("**Reset**")
        if st.checkbox("Show reset options", key="reset_show"):
            if st.button("Restore example settings"):
                logo = S.get("logo", "")
                ss.S = default_settings()
                ss.S["logo"] = logo
                clear_prefix("s_")
                st.rerun()
            if st.button("Delete ALL saved jobs"):
                ss.library = []
                st.rerun()


def page_settings() -> None:
    S = ss.S
    st.html('<div class="crumb">Business settings</div><h1 class="pg">Your rates and business details</h1>')
    t1, t2, t3, t4 = st.tabs(["Your business", "Rates & pricing", "Terms & documents", "Data & backup"])

    with t1:
        with st.container(border=True):
            st.markdown("**Your business**")
            st.caption("Printed at the top of every quote and invoice.")
            stext("Business name", "bizName")
            c1, c2 = st.columns(2)
            with c1:
                stext("ABN or tax number", "abn")
            with c2:
                stext("Phone", "phone")
            stext("Business email", "bizEmail")
            stext("Business address", "address", area=True, height=72)
            c1, c2 = st.columns(2)
            cur = S.get("currency", "AUD")
            S["currency"] = c1.selectbox("Currency", CURRENCIES, index=CURRENCIES.index(cur) if cur in CURRENCIES else 0, key="s_currency")
            zones = _timezones()
            z = S.get("timezone", "UTC")
            if z not in zones:
                zones = [z] + zones
            S["timezone"] = c2.selectbox("Time zone (for document dates)", zones, index=zones.index(z), key="s_timezone")
        _logo_card()

    with t2:
        with st.container(border=True):
            st.markdown("**Labour cost**")
            snum("Hourly labour cost, per person", "labourRate", 38.0, min_value=0.0, step=1.0,
                 help="What one person costs you per hour, including super, leave, insurance and payroll. "
                      "If you work on the job yourself, include your own time at a market wage.")
        with st.container(border=True):
            st.markdown("**Overhead allowance**")
            if "s_overheadMode" not in ss:
                ss["s_overheadMode"] = S.get("overheadMode", "percent")
            S["overheadMode"] = st.radio("Mode", ["percent", "hourly"], horizontal=True, key="s_overheadMode",
                                         format_func=lambda x: "% of direct costs" if x == "percent" else "Per labour hour")
            if S["overheadMode"] == "percent":
                snum("Overhead as a share of direct costs (%)", "overheadPct", 15.0, min_value=0.0, step=1.0)
            else:
                snum("Overhead per labour hour", "overheadHourly", 6.0, min_value=0.0, step=0.5)
        with st.container(border=True):
            st.markdown("**Materials and subcontractors**")
            st.caption("An allowance for wastage, delivery and handling, added to what you pay. Leave at 0 for none.")
            c1, c2 = st.columns(2)
            with c1:
                snum("Materials allowance (%)", "materialsAllowancePct", 0.0, min_value=0.0, step=1.0)
            with c2:
                snum("Other costs allowance (%)", "otherAllowancePct", 0.0, min_value=0.0, step=1.0)
        with st.container(border=True):
            st.markdown("**Profit & pricing**")
            c1, c2, c3 = st.columns(3)
            with c1:
                snum("Target profit margin (%)", "margin", 25.0, min_value=0.0, max_value=90.0, step=1.0)
            with c2:
                snum("Minimum job price", "minPrice", 150.0, min_value=0.0, step=10.0)
            with c3:
                snum("Round quote up to", "roundTo", 5.0, min_value=0.0, step=1.0, help="0 turns rounding off.")
            mm = clamp(dec(S.get("margin")), ZERO, dec(90)) / 100
            if 0 < mm < 1:
                st.info(md(f"At a {float(mm) * 100:.1f}% margin, a job that costs {money(S, 100)} is quoted at "
                           f"{money(S, to_cents(100 / (1 - mm)))}. That is a {float(mm / (1 - mm)) * 100:.1f}% markup on cost."))
        with st.container(border=True):
            st.markdown("**Travel**")
            snum("Vehicle cost per kilometre", "travelRate", 0.88, min_value=0.0, step=0.05,
                 help="Fuel, servicing, tyres and depreciation. Travel time is charged at your labour cost.")

    with t3:
        with st.container(border=True):
            st.markdown("**Tax**")
            if "s_taxOn" not in ss:
                ss["s_taxOn"] = bool(S.get("taxOn"))
            S["taxOn"] = st.checkbox("Add tax to quotes and invoices", key="s_taxOn")
            c1, c2 = st.columns(2)
            with c1:
                stext("Tax name", "taxName")
            with c2:
                snum("Tax rate (%)", "taxRate", 10.0, min_value=0.0, step=0.5)
        with st.container(border=True):
            st.markdown("**Terms & payment**")
            c1, c2, c3 = st.columns(3)
            with c1:
                snum("Quote valid for (days, 0 = no expiry)", "validDays", 30, as_int=True, min_value=0, step=1)
            with c2:
                snum("Deposit to book (%)", "depositPct", 20.0, min_value=0.0, max_value=100.0, step=5.0)
            with c3:
                snum("Invoice terms (days)", "payTerms", 14, as_int=True, min_value=0, step=1)
            stext("Payment details, printed on invoices", "payDetails", area=True, height=90)
            stext("Closing note", "docNote")
            stext("Terms and conditions (optional, printed on documents)", "terms", area=True, height=110)
            if "s_showAcceptance" not in ss:
                ss["s_showAcceptance"] = bool(S.get("showAcceptance"))
            S["showAcceptance"] = st.checkbox("Add a signature block to quotes", key="s_showAcceptance")
        with st.container(border=True):
            st.markdown("**Document numbers**")
            st.caption("Numbers are assigned when you issue a document. The next number is suggested automatically.")
            c1, c2 = st.columns(2)
            with c1:
                stext("Quote prefix", "quotePrefix")
                snum("Next quote number", "nextQuote", 1, as_int=True, min_value=1, step=1)
            with c2:
                stext("Invoice prefix", "invoicePrefix")
                snum("Next invoice number", "nextInvoice", 1, as_int=True, min_value=1, step=1)

    with t4:
        _data_tab()


# ---------------------------------------------------------------------------
# App shell
# ---------------------------------------------------------------------------

def main() -> None:
    st.set_page_config(page_title="Job Costing & Quotes", page_icon=":material/request_quote:",
                       layout="wide", initial_sidebar_state="expanded")
    st.markdown(CSS, unsafe_allow_html=True)
    init_state()

    target = ss.pop("_goto", None)
    if target:
        ss.nav = target

    with st.sidebar:
        st.html('<div style="font-weight:700;font-size:1.05rem;padding:.2rem 0 .6rem">Job Costing<br>'
                '<span style="font-weight:400;font-size:.75rem;opacity:.7">Quotation Calculator</span></div>')
        st.radio("Navigate", PAGES, key="nav", label_visibility="collapsed")
        st.divider()
        st.html(f'<div style="font-weight:700;font-size:.88rem">{esc(ss.S.get("bizName") or "Your business")}</div>')
        n = len(ss.library)
        st.caption(f"{n} job{'s' if n != 1 else ''} in library")
        if data_path():
            st.caption("Autosave on")
        else:
            st.caption("Session only. Download a backup in Business settings.")

    page = ss.nav
    if page == "Job costing":
        page_job()
    elif page == "Quote & invoice":
        page_doc()
    elif page == "Job library":
        page_library()
    else:
        page_settings()
    autosave()


main()
