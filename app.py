"""
Job Costing & Quotation Calculator  (web app, Streamlit)

Cost a job, price it to your target margin, track quotes and invoices, and
download a PDF to send to the customer.

Run locally:   pip install -r requirements.txt   then   streamlit run app.py
Deploy:        push to GitHub and deploy on Streamlit Community Cloud (main file: app.py)

Streamlit Cloud does not keep files between visits, so your data lives in the
browser session. Use "Download backup" in the sidebar and "Restore backup" next time.
"""
import base64
import copy
import datetime as dt
import json
import math
import os
import tempfile
import uuid
from urllib.parse import quote

import streamlit as st

LOGO_FILE = None  # per-session logo file is set in the UI

PRICING_KEYS = ["currency", "labourRate", "overheadMode", "overheadPct", "overheadHourly", "margin", "minPrice",
                "roundTo", "travelRate", "taxOn", "taxName", "taxRate", "validDays", "depositPct", "payTerms"]
QUOTE_STATUSES = ["Draft", "Sent", "Accepted", "Declined"]
INVOICE_STATUSES = ["Draft", "Sent", "Paid"]


def today():
    return dt.date.today()


def default_settings():
    return {
        "bizName": "Example Cleaning Co.", "abn": "00 000 000 000", "phone": "0400 000 000",
        "bizEmail": "accounts@example.com.au", "address": "1 Example Street\nSydney NSW 2000",
        "currency": "AUD", "labourRate": 38, "overheadMode": "percent", "overheadPct": 15,
        "overheadHourly": 6, "margin": 25, "minPrice": 150, "roundTo": 5, "travelRate": 0.88,
        "taxOn": True, "taxName": "GST", "taxRate": 10, "validDays": 30, "depositPct": 20,
        "payTerms": 14,
        "payDetails": "Account name: Example Cleaning Co.\nBSB: 000-000\nAccount number: 0000 0000",
        "docNote": "Thank you for your business.",
        "quotePrefix": "Q-", "nextQuote": 1001, "invoicePrefix": "INV-", "nextInvoice": 1001,
    }


def job_defaults():
    now = dt.datetime.now().isoformat(timespec="seconds")
    return {
        "id": uuid.uuid4().hex[:8], "status": "Draft", "created": now, "updated": now, "paidDate": "", "snap": None,
        "docType": "quote", "quoteNo": "", "invoiceNo": "", "issueDate": today().isoformat(), "paid": 0,
        "custEmail": "", "custPhone": "", "custAddress": "", "itemised": False, "emailEdited": False,
        "emailSubject": "", "emailBody": "", "sample": False, "title": "", "client": "", "scope": "",
        "people": 1, "hours": 0, "km": 0, "travelHours": 0, "materials": [], "other": [], "gut": 0,
    }


def sample_job():
    j = job_defaults()
    j.update({
        "sample": True, "title": "End-of-lease clean, 3-bed unit", "client": "Sample Customer",
        "custEmail": "customer@example.com", "custPhone": "0411 000 000", "custAddress": "12 Sample Road\nSydney NSW 2000",
        "scope": "Full interior clean to bond-return standard: kitchen, bathrooms, floors, "
                 "windows (inside) and wardrobes.\nCarpet steam cleaning is not included.",
        "people": 2, "hours": 3, "km": 18, "travelHours": 0.5,
        "materials": [{"d": "Cleaning products", "q": 1, "c": 18},
                      {"d": "Consumables (cloths, bags, sponges)", "q": 1, "c": 12}],
        "gut": 250,
    })
    return j


def starter_templates():
    def t(name, title, scope, people, hours, km, th, mats, other=None):
        return {"id": uuid.uuid4().hex[:8], "name": name, "title": title, "scope": scope, "people": people,
                "hours": hours, "km": km, "travelHours": th,
                "materials": [{"d": d, "q": q, "c": c} for d, q, c in mats],
                "other": [{"d": d, "a": a} for d, a in (other or [])]}
    return [
        t("End-of-lease clean (3-bed)", "End-of-lease clean", "Full interior clean to bond-return standard.", 2, 3, 18, 0.5,
          [("Cleaning products", 1, 18), ("Consumables", 1, 12)]),
        t("Interior paint, one room", "Interior repaint, one room", "Prepare, patch, two coats on walls and ceiling. Furniture moved and covered.", 1, 8, 20, 0.5,
          [("Paint, 10 L", 1, 120), ("Rollers, tape, drop sheets", 1, 35)]),
        t("Lawn mow and edge", "Lawn mow and edge", "Mow, edge and blow clean. Green waste removed.", 1, 1.5, 10, 0.25,
          [("Fuel and line", 1, 8)]),
        t("Handyman half-day", "Handyman, half day", "Up to four hours of general repairs and fixing.", 1, 4, 15, 0.5,
          [("Fixings and small parts", 1, 25)]),
    ]


def assign_quote_no(S, J):
    J["quoteNo"] = "%s%d" % (S.get("quotePrefix", "Q-"), int(num(S.get("nextQuote")) or 1001))
    S["nextQuote"] = int(num(S.get("nextQuote")) or 1001) + 1


def assign_invoice_no(S, J):
    J["invoiceNo"] = "%s%d" % (S.get("invoicePrefix", "INV-"), int(num(S.get("nextInvoice")) or 1001))
    S["nextInvoice"] = int(num(S.get("nextInvoice")) or 1001) + 1


def new_job(S, base=None):
    j = job_defaults()
    if base:
        j.update(copy.deepcopy(base))
    assign_quote_no(S, j)
    return j


def eff_settings(S, J):
    e = dict(S)
    if J.get("snap"):
        e.update(J["snap"])
    return e


def take_snap(S):
    return {k: S.get(k) for k in PRICING_KEYS}


# ---------------------------------------------------------------- maths


def num(v):
    try:
        x = float(str(v).replace(",", "").replace("$", "").strip())
        return x if math.isfinite(x) else 0.0
    except (TypeError, ValueError):
        return 0.0


def is_num(v):
    s = str(v).replace(",", "").replace("$", "").strip()
    if s == "":
        return True
    try:
        return math.isfinite(float(s)) and float(s) >= 0
    except ValueError:
        return False


def pos(v):
    return max(0.0, num(v))


def r2(x):
    return math.floor(x * 100 + 0.5) / 100


def calc(s, j):
    people, hours, rate = pos(j.get("people")), pos(j.get("hours")), pos(s.get("labourRate"))
    on_site = people * hours
    travel_hours = pos(j.get("travelHours")) * people
    paid_hours = on_site + travel_hours
    labour = on_site * rate
    vehicle = pos(j.get("km")) * pos(s.get("travelRate"))
    travel_time = travel_hours * rate
    travel = vehicle + travel_time
    materials = sum(pos(r.get("q")) * pos(r.get("c")) for r in j.get("materials", []))
    other = sum(pos(r.get("a")) for r in j.get("other", []))
    direct = labour + travel + materials + other
    if s.get("overheadMode") == "hourly":
        overhead = paid_hours * pos(s.get("overheadHourly"))
    else:
        overhead = direct * pos(s.get("overheadPct")) / 100
    cost = direct + overhead
    target = min(max(num(s.get("margin")), 0), 90) / 100
    raw = cost / (1 - target) if cost > 0 else 0.0
    price, rounded, min_applied = raw, False, False
    step = pos(s.get("roundTo"))
    if step > 0 and price > 0:
        rp = math.ceil(price / step - 1e-9) * step
        rounded = rp > price + 0.004
        price = rp
    min_p = pos(s.get("minPrice"))
    if cost > 0 and min_p > price:
        price, min_applied, rounded = min_p, True, False
    price = r2(price)
    profit = price - cost
    tax_rate = pos(s.get("taxRate")) if s.get("taxOn") else 0.0
    tax = r2(price * tax_rate / 100)
    return dict(labour=labour, vehicle=vehicle, travel_time=travel_time, travel=travel,
                materials=materials, other=other, direct=direct, overhead=overhead, cost=cost,
                target=target, raw=raw, price=price, rounded=rounded, min_applied=min_applied,
                profit=profit, margin=(profit / price if price > 0 else 0.0), tax=tax,
                tax_rate=tax_rate, total=r2(price + tax), on_site=on_site, paid_hours=paid_hours,
                pph=(profit / paid_hours if paid_hours > 0 else 0.0))


def job_calc(S, J):
    eff = eff_settings(S, J)
    return calc(eff, J), eff


def doc_lines(j, r):
    title = j.get("title") or "Job"
    if not j.get("itemised") or r["direct"] <= 0:
        return [(title, r["price"])]
    parts = [("Labour and travel", r["labour"] + r["travel"]),
             ("Materials and supplies", r["materials"]), ("Other costs", r["other"])]
    parts = [p for p in parts if p[1] > 1e-5]
    out, total = [], 0.0
    for i, (name, val) in enumerate(parts):
        a = r2(r["price"] - total) if i == len(parts) - 1 else r2(r["price"] * val / r["direct"])
        total += a
        out.append((name, a))
    return out


# ---------------------------------------------------------------- documents

SYMBOLS = {"AUD": "$", "NZD": "$", "USD": "$", "CAD": "$", "GBP": "£", "EUR": "€"}


def money(s, v):
    sym = SYMBOLS.get(s.get("currency", "AUD"), "$")
    return ("-" if v < -0.004 else "") + sym + "{:,.2f}".format(abs(v))


def fmt_date(d):
    return "{} {}".format(d.day, d.strftime("%B %Y"))


def parse_date(text):
    try:
        return dt.date.fromisoformat(str(text).strip())
    except ValueError:
        return today()


def valid_date(text):
    try:
        dt.date.fromisoformat(str(text).strip())
        return True
    except ValueError:
        return False


def lines_of(text):
    return [x.strip() for x in str(text or "").splitlines() if x.strip()]


def due_date(eff, j):
    return parse_date(j.get("issueDate")) + dt.timedelta(days=int(round(pos(eff.get("payTerms")))))


def display_status(eff, j):
    st = j.get("status", "Draft")
    if j.get("docType") == "invoice" and st == "Sent" and due_date(eff, j) < today():
        return "Overdue"
    return st


def build_model(s, j, r):
    inv = j.get("docType") == "invoice"
    tn = s.get("taxName") or "Tax"
    cc = s.get("currency", "AUD")
    issue = parse_date(j.get("issueDate"))
    due = due_date(s, j)
    until = issue + dt.timedelta(days=int(round(pos(s.get("validDays")))))
    paid = pos(j.get("paid")) if inv else 0.0
    m = {"inv": inv, "currency": cc}
    m["title"] = ("Tax invoice" if s.get("taxOn") else "Invoice") if inv else "Quote"
    m["number"] = (j.get("invoiceNo") if inv else j.get("quoteNo")) or ""
    m["bizName"] = s.get("bizName") or "Your business"
    biz = []
    if s.get("abn"):
        biz.append("ABN " + s["abn"])
    biz += lines_of(s.get("address"))
    if s.get("phone"):
        biz.append(s["phone"])
    if s.get("bizEmail"):
        biz.append(s["bizEmail"])
    m["bizLines"] = biz
    m["logo"] = LOGO_FILE if LOGO_FILE and os.path.exists(LOGO_FILE) else None
    m["billLabel"] = "Bill to" if inv else "Prepared for"
    m["billName"] = j.get("client") or "Customer"
    m["billLines"] = lines_of(j.get("custAddress")) + [x for x in (j.get("custPhone"), j.get("custEmail")) if x]
    if inv:
        m["meta"] = [("Invoice date", fmt_date(issue)), ("Due date", fmt_date(due))]
    else:
        m["meta"] = [("Quote date", fmt_date(issue)),
                     ("Valid until", fmt_date(until) if pos(s.get("validDays")) > 0 else "No expiry")]
    m["jobTitle"] = j.get("title") or "Untitled job"
    m["scope"] = j.get("scope") or ""
    m["lines"] = [(d, money(s, a)) for d, a in doc_lines(j, r)]
    tot = []
    if s.get("taxOn"):
        tot.append(("Subtotal (excl. %s)" % tn, money(s, r["price"]), False))
        tot.append(("%s (%g%%)" % (tn, r["tax_rate"]), money(s, r["tax"]), False))
        tot.append(("Total (incl. %s)" % tn, money(s, r["total"]), True))
    else:
        tot.append(("Total", money(s, r["total"]), True))
    hl = None
    if inv:
        if paid > 0:
            tot.append(("Less amount received", "-" + money(s, paid), False))
        hl = ("Balance due" if paid > 0 else "Amount due", money(s, max(0.0, r["total"] - paid)))
        if j.get("status") == "Paid":
            hl = ("PAID IN FULL", money(s, r["total"]))
    elif pos(s.get("depositPct")) > 0:
        hl = ("Deposit to book (%g%%)" % pos(s.get("depositPct")),
              money(s, r["total"] * pos(s.get("depositPct")) / 100))
    m["totals"], m["highlight"] = tot, hl
    m["payment"] = s.get("payDetails") if (inv and s.get("payDetails") and j.get("status") != "Paid") else None
    notes = []
    if inv:
        if j.get("status") != "Paid":
            notes.append("Payment is due within %d days, by %s." % (round(pos(s.get("payTerms"))), fmt_date(due)))
    else:
        if pos(s.get("depositPct")) > 0:
            notes.append("A deposit is requested to book the job, with the balance due on completion.")
        if pos(s.get("validDays")) > 0:
            notes.append("This quote is valid for %d days, until %s." % (round(pos(s.get("validDays"))), fmt_date(until)))
    notes.append("All amounts are in %s." % cc)
    if s.get("docNote"):
        notes.append(s["docNote"])
    m["notes"] = notes
    return m


def model_text(m):
    L = ["%s %s" % (m["title"].upper(), m["number"]), m["bizName"]] + m["bizLines"] + [""]
    L.append("%s: %s" % (m["billLabel"], m["billName"]))
    L += [("%s: %s" % p) for p in m["meta"]]
    L += ["", m["jobTitle"]]
    if m["scope"]:
        L.append(m["scope"])
    L.append("")
    L += [("%s: %s" % p) for p in m["lines"]]
    L += [("%s: %s" % (a, b)) for a, b, _ in m["totals"]]
    if m["highlight"]:
        L.append("%s: %s" % m["highlight"])
    if m["payment"]:
        L += ["", "Payment details:", m["payment"]]
    L.append("")
    L += m["notes"]
    return "\n".join(L)


def email_template(s, j, m):
    b = [("Hi %s," % j["client"]) if j.get("client") else "Hi,", ""]
    if m["inv"]:
        b.append("Please find attached %s %s for %s." % (m["title"].lower(), m["number"], m["jobTitle"]))
        b.append("")
        b.append("%s: %s" % m["highlight"])
        b.append("Due date: %s" % m["meta"][1][1])
        if s.get("payDetails"):
            b += ["", "Payment details:", s["payDetails"]]
        b += ["", "Please let me know if you have any questions."]
    else:
        strong = [t for t in m["totals"] if t[2]][0]
        b.append("Thanks for the opportunity to quote. Please find attached quote %s for %s." % (m["number"], m["jobTitle"]))
        b.append("")
        b.append("%s: %s" % (strong[0], strong[1]))
        b.append("%s: %s" % m["meta"][1])
        b += ["", "If you are happy to go ahead, just reply to this email and we will lock in a date."]
    b += ["", "Kind regards,", m["bizName"]]
    if s.get("phone"):
        b.append(s["phone"])
    return "%s %s from %s" % (m["title"], m["number"], m["bizName"]), "\n".join(b)


def make_pdf(m, path):
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas
    draw_document(canvas.Canvas(path, pagesize=A4), m)


def draw_document(c, m):
    """Draws a quote or invoice. `c` is a reportlab canvas (for the PDF) or a TkPage (for the on-screen preview),
    so the preview and the PDF always have the same layout."""
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.lib.utils import simpleSplit

    W, H = A4
    ML, MR = 18, 192
    ACC = (36 / 255, 87 / 255, 230 / 255)
    INK, MUT, RULE, SOFT = (15 / 255, 27 / 255, 45 / 255), (95 / 255, 110 / 255, 128 / 255), \
        (221 / 255, 227 / 255, 235 / 255), (244 / 255, 246 / 255, 249 / 255)
    c.setTitle("%s %s" % (m["title"], m["number"]))
    state = {"y": 0.0, "page": 1}

    def Y(y):
        return H - y * mm

    def font(name, size, color=INK):
        c.setFont(name, size)
        c.setFillColorRGB(*color)

    def wrap(text, width_mm, name="Helvetica", size=10):
        out = []
        for para in str(text).split("\n"):
            out += simpleSplit(para, name, size, width_mm * mm) or [""]
        return out

    def hr(y):
        c.setStrokeColorRGB(*RULE)
        c.setLineWidth(0.7)
        c.line(ML * mm, Y(y), MR * mm, Y(y))

    def top_band():
        c.setFillColorRGB(*ACC)
        c.rect(0, H - 5 * mm, W, 5 * mm, stroke=0, fill=1)

    def footer():
        font("Helvetica", 8, MUT)
        c.drawString(ML * mm, Y(288), "%s  |  %s %s" % (m["bizName"], m["title"], m["number"]))
        c.drawRightString(MR * mm, Y(288), "Page %d" % state["page"])

    def need(h):
        if state["y"] + h > 272:
            footer()
            c.showPage()
            state["page"] += 1
            top_band()
            state["y"] = 20

    def text_block(lines, x, lh, name="Helvetica", size=10, color=INK):
        for ln in lines:
            need(lh)
            font(name, size, color)
            c.drawString(x * mm, Y(state["y"]), ln)
            state["y"] += lh

    top_band()
    top_y = 22.0
    state["y"] = top_y
    logo_h = 0.0
    if m.get("logo"):
        try:
            from reportlab.lib.utils import ImageReader
            img = ImageReader(m["logo"])
            iw, ih = img.getSize()
            box_w, box_h = 52.0, 17.0
            scale = min(box_w / iw, box_h / ih)
            lw, logo_h = iw * scale, ih * scale
            c.drawImage(img, ML * mm, Y(top_y - 4 + logo_h), width=lw * mm, height=logo_h * mm, mask="auto")
            state["y"] = top_y - 4 + logo_h + 8
        except Exception:  # noqa: BLE001
            logo_h = 0.0
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
    c.drawRightString((MR - 3) * mm, Y(state["y"]), "AMOUNT (%s)" % m["currency"])
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


# ---------------------------------------------------------------- storage


# ---------------------------------------------------------------- state

def blank_store():
    S = default_settings()
    j = sample_job()
    assign_quote_no(S, j)
    return {"S": S, "jobs": [j], "customers": [], "templates": starter_templates(), "current": j["id"]}


def _merge_job(j):
    base = job_defaults()
    base.update(j)
    base.setdefault("materials", [])
    base.setdefault("other", [])
    return base


def import_store(data):
    S = default_settings()
    S.update(data.get("S", {}))
    jobs = [_merge_job(j) for j in data.get("jobs", []) if isinstance(j, dict)]
    if not jobs and isinstance(data.get("J"), dict):
        jobs = [_merge_job(data["J"])]
    if not jobs:
        raise ValueError("No jobs found in that file.")
    for j in jobs:
        if not j.get("quoteNo"):
            assign_quote_no(S, j)
    cur = data.get("current")
    if cur not in [j["id"] for j in jobs]:
        cur = jobs[-1]["id"]
    return {"S": S, "jobs": jobs, "customers": [c for c in data.get("customers", []) if isinstance(c, dict)],
            "templates": data.get("templates") or starter_templates(), "current": cur}


def logo_path():
    """Writes the saved logo (stored inside the data as base64) to a temp file for the PDF."""
    b64 = st.session_state.store["S"].get("logoB64")
    if not b64:
        return None
    path = os.path.join(tempfile.gettempdir(), "jc_logo_%s.png" % st.session_state.sid)
    try:
        with open(path, "wb") as f:
            f.write(base64.b64decode(b64))
        return path
    except (OSError, ValueError):
        return None


def current_job():
    st_ = st.session_state.store
    for j in st_["jobs"]:
        if j["id"] == st_["current"]:
            return j
    st_["current"] = st_["jobs"][0]["id"]
    return st_["jobs"][0]


def touch(j):
    j["updated"] = dt.datetime.now().isoformat(timespec="seconds")


def pdf_bytes(m):
    import io
    buf = io.BytesIO()
    make_pdf(m, buf)
    return buf.getvalue()


def pdf_pages_png(data):
    import pypdfium2 as pdfium
    pdf = pdfium.PdfDocument(data)
    out = []
    for i in range(len(pdf)):
        img = pdf[i].render(scale=1.6).to_pil()
        import io
        b = io.BytesIO()
        img.save(b, format="PNG")
        out.append(b.getvalue())
    return out


def edit_rows(label, rows, cols):
    """Small table editor for materials / other costs. Returns the cleaned list."""
    import pandas as pd
    df = pd.DataFrame(rows if rows else [], columns=[c[0] for c in cols])
    out = st.data_editor(df, num_rows="dynamic", width="stretch", hide_index=True,
                         column_config={c[0]: c[1] for c in cols}, key=label)
    res = []
    for rec in out.to_dict("records"):
        d = {c[0]: rec.get(c[0]) for c in cols}
        if all((v is None or v == "" or (isinstance(v, float) and math.isnan(v))) for v in d.values()):
            continue
        for k, v in d.items():
            if isinstance(v, float) and math.isnan(v):
                d[k] = "" if k == "d" else 0
        res.append(d)
    return res


def M(S_, v):
    return money(S_, v)


# ---------------------------------------------------------------- pages

def page_jobs():
    store = st.session_state.store
    S = store["S"]
    st.title("Jobs")
    rows, tot_open, tot_paid, tot_over = [], 0.0, 0.0, 0.0
    for j in store["jobs"]:
        eff = eff_settings(S, j)
        r = calc(eff, j)
        stat = display_status(eff, j)
        inv = j.get("docType") == "invoice"
        if stat == "Paid":
            tot_paid += r["total"]
        elif stat == "Overdue":
            tot_over += r["total"] - pos(j.get("paid"))
        elif inv and stat == "Sent":
            tot_open += r["total"] - pos(j.get("paid"))
        rows.append({"Number": (j.get("invoiceNo") if inv else j.get("quoteNo")) or "", "Type": "Invoice" if inv else "Quote",
                     "Customer": j.get("client") or "", "Job": j.get("title") or "Untitled", "Status": stat,
                     "Total": round(r["total"], 2), "Date": fmt_date(parse_date(j.get("issueDate")))})
    c1, c2, c3 = st.columns(3)
    c1.metric("Invoices awaiting payment", M(S, tot_open))
    c2.metric("Overdue", M(S, tot_over))
    c3.metric("Paid", M(S, tot_paid))
    st.dataframe(rows, width="stretch", hide_index=True)

    a, b, c, d = st.columns(4)
    if a.button("New job", width="stretch"):
        j = new_job(store["S"])
        store["jobs"].append(j)
        store["current"] = j["id"]
        st.session_state.page = "Job costing"
        st.rerun()
    if b.button("Duplicate current", width="stretch"):
        base = copy.deepcopy(current_job())
        for k in ("id", "status", "snap", "invoiceNo", "paidDate", "paid", "docType", "sample"):
            base.pop(k, None)
        base["title"] = (base.get("title") or "Job") + " (copy)"
        j = new_job(store["S"], base)
        store["jobs"].append(j)
        store["current"] = j["id"]
        st.rerun()
    tnames = {t["name"]: t for t in store["templates"]}
    pick = c.selectbox("New from template", ["-"] + list(tnames), label_visibility="collapsed")
    if pick != "-" and d.button("Create from template", width="stretch"):
        t = tnames[pick]
        base = {k: copy.deepcopy(t.get(k)) for k in ("title", "scope", "people", "hours", "km", "travelHours", "materials", "other")}
        j = new_job(store["S"], base)
        store["jobs"].append(j)
        store["current"] = j["id"]
        st.session_state.page = "Job costing"
        st.rerun()
    with st.expander("Delete the current job"):
        st.write("Current: **%s**" % (current_job().get("title") or "Untitled"))
        if len(store["jobs"]) > 1 and st.button("Delete this job"):
            store["jobs"] = [j for j in store["jobs"] if j["id"] != store["current"]]
            store["current"] = store["jobs"][-1]["id"]
            st.rerun()
        elif len(store["jobs"]) <= 1:
            st.caption("You need at least one job.")


def page_costing():
    store = st.session_state.store
    S = store["S"]
    J = current_job()
    st.title("Job costing")
    if J.get("snap"):
        st.info("Pricing is locked to the settings in force when this %s was sent. Open Quote & invoice to unlock it."
                % ("invoice" if J.get("docType") == "invoice" else "quote"))
    left, right = st.columns([3, 2], gap="large")
    with left:
        J["title"] = st.text_input("Job title", J.get("title", ""), placeholder="e.g. End-of-lease clean")
        custs = {c.get("name", ""): c for c in store["customers"] if c.get("name")}
        if custs:
            p = st.selectbox("Fill from saved customer", ["-"] + sorted(custs))
            if p != "-" and st.button("Use %s" % p):
                c = custs[p]
                J.update(client=c.get("name", ""), custEmail=c.get("email", ""), custPhone=c.get("phone", ""),
                         custAddress=c.get("address", ""))
                st.rerun()
        c1, c2 = st.columns(2)
        J["client"] = c1.text_input("Customer", J.get("client", ""))
        J["custEmail"] = c2.text_input("Customer email", J.get("custEmail", ""))
        c1, c2 = st.columns(2)
        J["custPhone"] = c1.text_input("Customer phone", J.get("custPhone", ""))
        J["custAddress"] = c2.text_area("Customer address", J.get("custAddress", ""), height=68)
        J["scope"] = st.text_area("Scope of work (shown on the quote)", J.get("scope", ""), height=110)
        if J["client"] and J["client"] not in [c.get("name") for c in store["customers"]]:
            if st.button("Save customer for next time"):
                store["customers"].append({"id": uuid.uuid4().hex[:8], "name": J["client"], "email": J["custEmail"],
                                           "phone": J["custPhone"], "address": J["custAddress"]})
                st.rerun()
        st.subheader("Time and travel")
        c1, c2, c3, c4 = st.columns(4)
        J["people"] = c1.number_input("People", 0.0, 100.0, float(num(J.get("people"))), 1.0)
        J["hours"] = c2.number_input("Hours each", 0.0, 1000.0, float(num(J.get("hours"))), 0.5)
        J["km"] = c3.number_input("Distance (km)", 0.0, 10000.0, float(num(J.get("km"))), 1.0)
        J["travelHours"] = c4.number_input("Travel hrs each", 0.0, 100.0, float(num(J.get("travelHours"))), 0.25)
        st.subheader("Materials")
        from streamlit import column_config as cc
        J["materials"] = edit_rows("mat_" + J["id"], J.get("materials", []), [
            ("d", cc.TextColumn("Item")), ("q", cc.NumberColumn("Qty", min_value=0, default=1)),
            ("c", cc.NumberColumn("Unit cost", min_value=0, format="%.2f"))])
        st.subheader("Other costs")
        J["other"] = edit_rows("oth_" + J["id"], J.get("other", []), [
            ("d", cc.TextColumn("Item")), ("a", cc.NumberColumn("Amount", min_value=0, format="%.2f"))])
        J["gut"] = st.number_input("What you would have quoted by gut feel (optional)", 0.0, 1e7, float(num(J.get("gut"))), 10.0)
    touch(J)
    r, eff = job_calc(S, J)
    with right:
        st.subheader("Price")
        st.metric("Quote price (excl. tax)" if eff.get("taxOn") else "Quote price", M(eff, r["price"]))
        if eff.get("taxOn"):
            st.caption("%s %s: %s   |   Total %s" % (eff.get("taxName"), "%g%%" % r["tax_rate"], M(eff, r["tax"]), M(eff, r["total"])))
        a, b = st.columns(2)
        a.metric("Your cost", M(eff, r["cost"]))
        b.metric("Profit", M(eff, r["profit"]))
        a, b = st.columns(2)
        a.metric("Margin", "%.1f%%" % (r["margin"] * 100), "target %g%%" % (r["target"] * 100), delta_color="off")
        b.metric("Profit per paid hour", M(eff, r["pph"]))
        if r["min_applied"]:
            st.warning("Your minimum price applies, so the price is above the calculated %s." % M(eff, r["raw"]))
        elif r["rounded"]:
            st.caption("Rounded up to the next %s from %s." % (M(eff, num(eff.get("roundTo"))), M(eff, r["raw"])))
        if r["cost"] <= 0:
            st.caption("Enter hours or costs to see a price.")
        st.subheader("Where the cost goes")
        st.dataframe([{"Item": k, "Amount": round(v, 2)} for k, v in [
            ("Labour", r["labour"]), ("Travel (vehicle)", r["vehicle"]), ("Travel (time)", r["travel_time"]),
            ("Materials", r["materials"]), ("Other", r["other"]), ("Overhead", r["overhead"]), ("Total cost", r["cost"])]],
            hide_index=True, width="stretch")
        g = num(J.get("gut"))
        if g > 0:
            diff = r["price"] - g
            profit_g = g - r["cost"]
            st.subheader("Versus your gut feel")
            st.write("Gut feel %s would leave %s profit (%.1f%% margin). The calculated price is %s %s."
                     % (M(eff, g), M(eff, profit_g), (profit_g / g * 100) if g else 0, M(eff, abs(diff)),
                        "higher" if diff > 0 else "lower"))


def page_doc():
    store = st.session_state.store
    S = store["S"]
    J = current_job()
    st.title("Quote & invoice")
    r, eff = job_calc(S, J)
    left, right = st.columns([3, 2], gap="large")
    with right:
        st.subheader("Document")
        inv = J.get("docType") == "invoice"
        kind = st.radio("Type", ["Quote", "Invoice"], index=1 if inv else 0, horizontal=True)
        want_inv = kind == "Invoice"
        if want_inv != inv:
            J["docType"] = "invoice" if want_inv else "quote"
            if want_inv and not J.get("invoiceNo"):
                assign_invoice_no(S, J)
            J["status"] = "Draft"
            J["snap"] = None
            st.rerun()
        statuses = INVOICE_STATUSES if inv else QUOTE_STATUSES
        cur = J.get("status") if J.get("status") in statuses else "Draft"
        new = st.selectbox("Status", statuses, index=statuses.index(cur))
        if new != J.get("status"):
            J["status"] = new
            J["snap"] = take_snap(S) if new != "Draft" else None
            if new == "Paid":
                J["paidDate"] = today().isoformat()
            st.rerun()
        if J.get("snap"):
            st.caption("Pricing locked at the settings in force when sent.")
            if st.button("Unlock pricing (use current settings)"):
                J["snap"] = take_snap(S)
                st.rerun()
        else:
            st.caption("Not sent yet. Pricing follows your current settings.")
        if not inv and st.button("Convert to invoice", type="primary"):
            J["docType"] = "invoice"
            if not J.get("invoiceNo"):
                assign_invoice_no(S, J)
            J["status"] = "Draft"
            J["snap"] = None
            st.rerun()
        c1, c2 = st.columns(2)
        if inv:
            J["invoiceNo"] = c1.text_input("Invoice number", J.get("invoiceNo", ""))
        else:
            J["quoteNo"] = c1.text_input("Quote number", J.get("quoteNo", ""))
        d = c2.date_input("Issue date", parse_date(J.get("issueDate")))
        J["issueDate"] = d.isoformat()
        J["itemised"] = st.checkbox("Show itemised lines", bool(J.get("itemised")),
                                    help="Splits the price into labour, materials and other costs. Overhead and profit are spread across the lines, so your costs stay private.")
        if inv:
            J["paid"] = st.number_input("Amount received so far", 0.0, 1e8, float(num(J.get("paid"))), 10.0)
        touch(J)
        m = build_model(eff, J, r)
        m["logo"] = logo_path()
        data = pdf_bytes(m)
        fname = "%s-%s.pdf" % (m["title"].replace(" ", "-"), m["number"] or "draft")
        st.download_button("Download PDF", data, file_name=fname, mime="application/pdf", type="primary", width="stretch")
        st.subheader("Send to customer")
        st.caption("Download the PDF, then attach it to your email.")
        subj, body = email_template(eff, J, m)
        subj = st.text_input("Email subject", subj, key="subj_" + J["id"] + str(inv))
        body = st.text_area("Email message", body, height=260, key="body_" + J["id"] + str(inv))
        to = J.get("custEmail", "")
        st.link_button("Open in my email app", "mailto:%s?subject=%s&body=%s" % (quote(to), quote(subj), quote(body)),
                       width="stretch")
        with st.expander("Copy as text"):
            st.code(model_text(m), language=None)
    with left:
        try:
            for png in pdf_pages_png(data):
                st.image(png, width="stretch")
        except Exception:  # noqa: BLE001
            st.info("The page preview isn't available here. Use Download PDF to see the document.")


def page_customers():
    store = st.session_state.store
    st.title("Customers")
    import pandas as pd
    df = pd.DataFrame(store["customers"], columns=["id", "name", "email", "phone", "address"])
    out = st.data_editor(df, num_rows="dynamic", width="stretch", hide_index=True,
                         column_config={"id": None}, key="cust_editor")
    recs = []
    for rec in out.to_dict("records"):
        if not (rec.get("name") or "").strip():
            continue
        rec = {k: ("" if (v is None or (isinstance(v, float) and math.isnan(v))) else v) for k, v in rec.items()}
        rec["id"] = rec.get("id") or uuid.uuid4().hex[:8]
        recs.append(rec)
    store["customers"] = recs


def page_settings():
    S = st.session_state.store["S"]
    st.title("Business settings")
    st.caption("Changes apply to every job that hasn't been sent yet. Sent quotes keep the pricing they were sent with.")
    t1, t2, t3 = st.tabs(["Pricing", "Business details", "Numbering and terms"])
    with t1:
        c1, c2, c3 = st.columns(3)
        cur = ["AUD", "NZD", "USD", "CAD", "GBP", "EUR"]
        S["currency"] = c1.selectbox("Currency", cur, index=cur.index(S["currency"]) if S["currency"] in cur else 0)
        S["labourRate"] = c2.number_input("Hourly labour cost", 0.0, 10000.0, float(num(S["labourRate"])), 1.0,
                                          help="What an hour of work costs you, including wages and on-costs.")
        S["margin"] = c3.number_input("Target profit margin (%)", 0.0, 90.0, float(num(S["margin"])), 1.0,
                                      help="Profit as a share of the price. 25% means a $100 job costs you $75.")
        c1, c2, c3 = st.columns(3)
        modes = ["percent", "hourly"]
        S["overheadMode"] = c1.selectbox("Overhead method", modes, index=modes.index(S["overheadMode"]) if S["overheadMode"] in modes else 0,
                                         format_func=lambda x: "% of direct costs" if x == "percent" else "Per paid hour")
        if S["overheadMode"] == "percent":
            S["overheadPct"] = c2.number_input("Overhead (%)", 0.0, 500.0, float(num(S["overheadPct"])), 1.0)
        else:
            S["overheadHourly"] = c2.number_input("Overhead per paid hour", 0.0, 1000.0, float(num(S["overheadHourly"])), 0.5)
        S["travelRate"] = c3.number_input("Vehicle cost per km", 0.0, 100.0, float(num(S["travelRate"])), 0.01)
        c1, c2 = st.columns(2)
        S["minPrice"] = c1.number_input("Minimum job price", 0.0, 1e7, float(num(S["minPrice"])), 10.0)
        S["roundTo"] = c2.number_input("Round price up to the next", 0.0, 1000.0, float(num(S["roundTo"])), 1.0)
        c1, c2, c3 = st.columns(3)
        S["taxOn"] = c1.checkbox("Charge tax", bool(S["taxOn"]))
        S["taxName"] = c2.text_input("Tax name", S["taxName"])
        S["taxRate"] = c3.number_input("Tax rate (%)", 0.0, 100.0, float(num(S["taxRate"])), 0.5)
    with t2:
        c1, c2 = st.columns(2)
        S["bizName"] = c1.text_input("Business name", S["bizName"])
        S["abn"] = c2.text_input("ABN / tax number", S["abn"])
        c1, c2 = st.columns(2)
        S["phone"] = c1.text_input("Phone", S["phone"])
        S["bizEmail"] = c2.text_input("Email", S["bizEmail"])
        S["address"] = st.text_area("Address", S["address"], height=80)
        S["payDetails"] = st.text_area("Payment details (shown on invoices)", S["payDetails"], height=90)
        up = st.file_uploader("Logo (PNG or JPG)", type=["png", "jpg", "jpeg"])
        if up is not None:
            try:
                from PIL import Image
                import io
                im = Image.open(up).convert("RGBA")
                im.thumbnail((600, 300))
                b = io.BytesIO()
                im.save(b, format="PNG")
                S["logoB64"] = base64.b64encode(b.getvalue()).decode()
            except Exception:  # noqa: BLE001
                st.error("That image could not be read.")
        if S.get("logoB64"):
            st.image(base64.b64decode(S["logoB64"]), width=160)
            if st.button("Remove logo"):
                S.pop("logoB64", None)
                st.rerun()
    with t3:
        c1, c2, c3, c4 = st.columns(4)
        S["quotePrefix"] = c1.text_input("Quote prefix", S["quotePrefix"])
        S["nextQuote"] = c2.number_input("Next quote number", 1, 10**9, int(num(S["nextQuote"]) or 1001))
        S["invoicePrefix"] = c3.text_input("Invoice prefix", S["invoicePrefix"])
        S["nextInvoice"] = c4.number_input("Next invoice number", 1, 10**9, int(num(S["nextInvoice"]) or 1001))
        c1, c2, c3 = st.columns(3)
        S["validDays"] = c1.number_input("Quote valid for (days)", 0, 365, int(num(S["validDays"])))
        S["depositPct"] = c2.number_input("Deposit requested (%)", 0.0, 100.0, float(num(S["depositPct"])), 5.0)
        S["payTerms"] = c3.number_input("Payment terms (days)", 0, 365, int(num(S["payTerms"])))
        S["docNote"] = st.text_input("Footer note", S["docNote"])
        if st.button("Restore example settings"):
            keep = {k: S[k] for k in ("quotePrefix", "nextQuote", "invoicePrefix", "nextInvoice")}
            S.clear()
            S.update(default_settings())
            S.update(keep)
            st.rerun()


# ---------------------------------------------------------------- app

def main():
    st.set_page_config(page_title="Job Costing", page_icon=":material/calculate:", layout="wide")
    if "store" not in st.session_state:
        st.session_state.store = blank_store()
        st.session_state.sid = uuid.uuid4().hex[:8]
        st.session_state.page = "Jobs"
    store = st.session_state.store
    pages = {"Jobs": page_jobs, "Job costing": page_costing, "Quote & invoice": page_doc,
             "Customers": page_customers, "Business settings": page_settings}
    with st.sidebar:
        st.markdown("### Job Costing")
        st.caption("Quotation calculator")
        st.radio("Go to", list(pages), key="page", label_visibility="collapsed")
        st.divider()
        labels = {j["id"]: "%s  %s" % ((j.get("invoiceNo") if j.get("docType") == "invoice" else j.get("quoteNo")) or "", j.get("title") or "Untitled")
                  for j in store["jobs"]}
        cur = st.selectbox("Current job", list(labels), index=list(labels).index(store["current"]) if store["current"] in labels else 0,
                           format_func=lambda i: labels[i])
        store["current"] = cur
        st.divider()
        st.caption("Your data stays in this browser session. Download a backup to keep it.")
        st.download_button("Download backup", json.dumps(store, indent=1), file_name="job-costing-backup-%s.json" % today().strftime("%Y%m%d"),
                           mime="application/json", width="stretch")
        up = st.file_uploader("Restore backup", type=["json"], key="restore")
        if up is not None and st.session_state.get("restored") != up.file_id:
            try:
                st.session_state.store = import_store(json.load(up))
                st.session_state.restored = up.file_id
                st.rerun()
            except (ValueError, OSError) as e:
                st.error("Could not restore: %s" % e)
    pages[st.session_state.page]()


main()
