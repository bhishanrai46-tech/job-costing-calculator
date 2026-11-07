#!/usr/bin/env python3
"""
Job Costing & Quotation Calculator  (desktop app)

Cost a job, price it to your target margin, track quotes and invoices, and
produce a PDF to send to the customer.  Runs on Windows, macOS and Linux.

Needs:  Python 3.9+   and   pip install reportlab
Run:    python job_costing_app.py
Data is saved to  ~/.job_costing/data.json  (daily backups in ~/.job_costing/backups)
"""
import base64
import copy
import datetime as dt
import json
import math
import os
import shutil
import sys
import uuid
import webbrowser
from urllib.parse import quote

import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk
from tkinter import font as tkfont

APP_DIR = os.path.join(os.path.expanduser("~"), ".job_costing")
DATA_FILE = os.path.join(APP_DIR, "data.json")
BACKUP_DIR = os.path.join(APP_DIR, "backups")
LOGO_FILE = os.path.join(APP_DIR, "logo.png")
LOGO_PREVIEW = os.path.join(APP_DIR, "logo_preview.png")

ICON_PNG = "iVBORw0KGgoAAAANSUhEUgAAAEAAAABACAYAAACqaXHeAAAGB0lEQVR4nO2bX2gc1xWHv3PuzGq1u5KJMXJs0rpK7UKbxi0JCWlo+sdQaClxIGSjPhbyEGhe+hLISxF6aF/ah76kUEofkodiWSbUDoUmFBdSkz60MdShfyA2qpvGTVQXy5ZWWs3OvacPsysnlVWvdlajjTYfzLIwM7v3nHvPPed3Z65wS0yYRpiRAHBkauERnH7TfPIlQ+4RkXHMG4jc+v6iMUOcmNkNwf4srvQaPvzqrdmJ3wEwbcoMBmL/e+dGA6ZNO4Z/cmphyrn4mRDWvqhRVSy0sJCAhULM2jKiiJYQjQlpw1RHznnfev7S7MQsfNC29Vs+8AN1c8yJ/9jxvx4sV/f9XFz562CE1hKAxxBEtFCjtopZQDDAaTwGCOabv242rj719plPX+nY2Ln8pgPaJyaf/McDkaueFjdyILSuty8UtyPG5MY8gMZ7nPm1f6W+8dj8yY//4f1OyHpz2pQ58ZP1Sw9GUeUVET3gk8U0M/zDajx02u+TxVRED0RR5ZXJ+qUHmRPPtCmZA7Ivh+rzd0Zu7GXB3RF8w4totNPN7xciGgXf8IK7I3JjLx+qz9+ZnTFV6nPCjIRI4hc0rkz4tJGCfoh7fTPU+bSRalyZiCR+gRkJ1OeyNHb4W+89oVF1LrRupMCu6flNSDUej0LaqF88sf+UgolZ+iwEAxuQvL6dmECwzGYTmZx65xEnpbNYy92yLtidGBJ7b8kxdaLHNSpHg1vdbAcWNCpHTvS4EsLDFlpgQ9P7YIiFFoTwcGTCUULCwFd4/URELSSYcFRFXG2oRn8HC4i4WpRX1QmgBY8dA0I/+sy8RXmMVwEfYLlhbNCZ24gqVMtZsy3XH4v0XPSoQDMxKmXlq/eVCh0Fjabxx78lxE5wLp8TenKACqwmxt0HIn723F6O3FV88Xj2jSZP/+gaIWTt6dUHPfWbCCQJfHdqjCN3RbTSrI4MoZgj9XDs/jJPfLnC0orlUi49d50o7NvjsgnJQApMJN5D5GDfHiUEQ3KUML07QOAnLy3x0D17GYmLraEiB1euen7xmxVqFcXncL4cnrrSU/iIQHPN+OzdMV97oIxTAdleMWHtj6XVwC9fW+Xfi55SLLkmwZ4dQHsyXFkzmon1Pgv1gAhUR5U4ypsGc2r/YFAZEWqjxYZApxDKazz9WPwIBsF3ceGAMjwCaBOG3gG5Q6CfYsgsC6kiyeWAfouh2MFoWfqj9LpkIMSQtQX5wrXAm5da1Cr5cvtWGCgx1EqNn55u8IMXbzBWLWYkDIYYsiyU4kh45vEaRw/HrDQNLaC8GAwx1B7urRTiCPbUBB/aSzXbHAoDJ4bOvrHG799MqI1KLpHTLQMhhkJ7Enz7vZTT51bxntwrPd0yUGJIHYyNKqrFGM+giSGz/omcbvlIDO10A3aaoXdA7hBQ6U4Mrcd33j/sM7nFULdZYCdm+G7IVQitrhn33qYO2Mkc3w09OcAp3FgxvvL5EV783l4i110a/MZDo3z7+//BdXl9EfQ8CZrBdx4fwzlhrZU9rfl/RyuFY/eP8IV7SyyvGm5Apt+eQ8ACXL3usxWhzkR4q2EtmbOi9rC/vpwZPygh0FM/mEGpBD+eXeKtf6bE0U0nbDgkC5lWajz/0jIXLraolKXwpa/N6FkLvH9F6L5PxZumwp1c7emGnkMgGJRLQis1fnt+7bb5PXYUtsqzFaKbfbR1gmUjYbx6+9s7hdBgYRYhTvK8JGVQyMLFtiBO1MwvM0RvyK0jiplfVjEuiJaynRbDglkQLSHGBUX1ddGY9jaT4UAw0RhUX1dv4UxImylDFQeiIW2m3sIZnZ89eM4sOa9xbX2Pze7GvMY1zJLz87MHzymIiUQ/zBLaxn11uw8xUMlsFlPqJ93FE/tP+WTxVVcaj8xCutNN3C7MQupK45FPFl+9eGL/KeonnYAp03DoL3+fKLnqn0TjieAbfvftGwpeXdVZaC0kvvG5y5/5xAIzoJ2HWpfnJt9N/dKjhr+mrup200gwC6m6qjP8tdQvPXp5bvLd7IyEod84+dHW2Q0/MNSbp9cZnu3z/wVa741OvVOwZwAAAABJRU5ErkJggg=="

PRICING_KEYS = ["currency", "labourRate", "overheadMode", "overheadPct", "overheadHourly", "margin", "minPrice",
                "roundTo", "travelRate", "taxOn", "taxName", "taxRate", "validDays", "depositPct", "payTerms"]
QUOTE_STATUSES = ["Draft", "Sent", "Accepted", "Declined"]
INVOICE_STATUSES = ["Draft", "Sent", "Paid"]

# ---------------------------------------------------------------- defaults


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
    m["logo"] = LOGO_FILE if os.path.exists(LOGO_FILE) else None
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


def _merge_job(j):
    base = job_defaults()
    base.update(j)
    base.setdefault("materials", [])
    base.setdefault("other", [])
    return base


def load_store():
    data = None
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        data = None
    S = default_settings()
    jobs, customers, templates, current = [], [], None, None
    if isinstance(data, dict):
        S.update(data.get("S", {}))
        if isinstance(data.get("jobs"), list):
            jobs = [_merge_job(j) for j in data["jobs"] if isinstance(j, dict)]
        elif isinstance(data.get("J"), dict):  # file from the first version of the app
            jobs = [_merge_job(data["J"])]
        customers = [c for c in data.get("customers", []) if isinstance(c, dict)]
        templates = data.get("templates")
        current = data.get("current")
    if templates is None:
        templates = starter_templates()
    if not jobs:
        j = sample_job()
        assign_quote_no(S, j)
        jobs = [j]
    for j in jobs:
        if not j.get("quoteNo"):
            assign_quote_no(S, j)
    ids = [j["id"] for j in jobs]
    if current not in ids:
        current = sorted(jobs, key=lambda x: x.get("updated", ""))[-1]["id"]
    store = {"S": S, "jobs": jobs, "customers": customers, "templates": templates, "current": current}
    if data:
        daily_backup()
    return store


def daily_backup():
    try:
        os.makedirs(BACKUP_DIR, exist_ok=True)
        target = os.path.join(BACKUP_DIR, "data-%s.json" % today().strftime("%Y%m%d"))
        if not os.path.exists(target) and os.path.exists(DATA_FILE):
            shutil.copy2(DATA_FILE, target)
        files = sorted(f for f in os.listdir(BACKUP_DIR) if f.startswith("data-") and f.endswith(".json"))
        for old in files[:-14]:
            os.remove(os.path.join(BACKUP_DIR, old))
    except OSError:
        pass


def save_store(store):
    try:
        os.makedirs(APP_DIR, exist_ok=True)
        tmp = DATA_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(store, f, indent=1)
        os.replace(tmp, DATA_FILE)
        return True
    except OSError:
        return False


# ---------------------------------------------------------------- interface

C = dict(side="#0F1B2D", side_hover="#18283F", side_active="#1F3453", side_fg="#C5D0E0", side_muted="#7D8EA6",
         bg="#F3F5F9", card="#FFFFFF", line="#DDE3EC", field="#C3CDDA", ink="#111C2E", muted="#66758A",
         accent="#2457E6", accent_dark="#1B47C4", soft="#F6F8FB", good="#0F7A4B", warn="#8F5200", bad="#B3261E",
         good_bg="#DCF3E7", warn_bg="#FBEBCF", bad_bg="#FBE0DD", neutral_bg="#EEF2F8", sel="#E3EBFC")
if sys.platform.startswith("win"):
    FONT, MONO = "Segoe UI", "Consolas"
elif sys.platform == "darwin":
    FONT, MONO = "Helvetica Neue", "Menlo"
else:
    FONT, MONO = "DejaVu Sans", "DejaVu Sans Mono"
SC = 1.0  # screen scale, set once the window exists


def px(n):
    return int(round(n * SC))


NUMERIC_KEYS = {"labourRate", "overheadPct", "overheadHourly", "margin", "minPrice", "roundTo", "travelRate", "taxRate",
                "validDays", "depositPct", "payTerms", "people", "hours", "km", "travelHours", "gut", "paid",
                "nextQuote", "nextInvoice"}
GREY = "#E3E6EB"
SEG_COLORS = [("labour", "#2457E6"), ("travel", "#0E8A8A"), ("materials", "#C27A0E"),
              ("other", "#7A4FBF"), ("overhead", "#8393A3"), ("profit", "#12A266")]
STATUS_FILTERS = ["All", "Draft", "Sent", "Accepted", "Declined", "Overdue", "Paid"]


def short_date(d):
    return "{} {}".format(d.day, d.strftime("%b %Y"))


def autowrap(label, pad=4):
    label.bind("<Configure>", lambda e: label.config(wraplength=max(80, e.width - pad)))
    return label


class Btn(tk.Label):
    """Flat button that looks the same on Windows, macOS and Linux."""

    def __init__(self, parent, text, command, kind="secondary"):
        look = {"primary": (C["accent"], "#FFFFFF", C["accent_dark"], C["accent"]),
                "secondary": (C["card"], C["ink"], C["soft"], C["field"]),
                "danger": (C["card"], C["bad"], C["bad_bg"], C["field"])}[kind]
        self.look, self.command = look, command
        super().__init__(parent, text=text, bg=look[0], fg=look[1], font=(FONT, 10, "bold"), padx=px(16), pady=px(7),
                         cursor="hand2", highlightthickness=1, highlightbackground=look[3], bd=0)
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
            b = tk.Label(self, text=text, font=(FONT, 10, "bold"), padx=px(16), pady=px(6), cursor="hand2", bd=0)
            b.pack(side="left", padx=(0, 3))
            b.bind("<Button-1>", lambda e, v=value: var.set(v))
            self.items[value] = b
        var.trace_add("write", lambda *_: self.paint())
        self.paint()

    def paint(self):
        for value, b in self.items.items():
            on = self.var.get() == value
            b.config(bg=C["card"] if on else C["neutral_bg"], fg=C["ink"] if on else C["muted"])


class ScrollFrame(tk.Frame):
    def __init__(self, parent, bg):
        super().__init__(parent, bg=bg)
        self.canvas = tk.Canvas(self, bg=bg, highlightthickness=0, bd=0)
        self.sb = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.inner = tk.Frame(self.canvas, bg=bg)
        self.win = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.inner.bind("<Configure>", lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>", lambda e: self.canvas.itemconfigure(self.win, width=e.width))
        self.canvas.configure(yscrollcommand=self.sb.set)
        self.sb.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)


class TkPage:
    """Draws reportlab-style page commands onto a Tk canvas, one white A4 page after another."""

    def __init__(self, cv, W, H, scale, ox, top, gap):
        self.cv, self.W, self.H, self.s, self.ox, self.gap = cv, W, H, scale, ox, gap
        self.oy, self.pages = top, 1
        self.fill, self.stroke, self.lw = "#000000", "#000000", 1.0
        self.fname, self.fsize = "Helvetica", 10.0
        self._fonts, self._imgs = {}, []
        self.family = "Arial" if sys.platform.startswith("win") else "Helvetica"
        self._bg()

    def _bg(self):
        x0, y0, x1, y1 = self.ox, self.oy, self.ox + self.W * self.s, self.oy + self.H * self.s
        self.cv.create_rectangle(x0 + 3, y0 + 4, x1 + 3, y1 + 4, fill="#C5CAD3", outline="")
        self.cv.create_rectangle(x0, y0, x1, y1, fill="#FFFFFF", outline="#D3D8E0")

    @property
    def bottom(self):
        return self.oy + self.H * self.s + self.gap

    @staticmethod
    def _hex(r, g, b):
        return "#%02x%02x%02x" % (int(round(r * 255)), int(round(g * 255)), int(round(b * 255)))

    def X(self, x):
        return self.ox + x * self.s

    def Yc(self, y):
        return self.oy + (self.H - y) * self.s

    def _font(self):
        key = (self.fname, self.fsize)
        if key not in self._fonts:
            self._fonts[key] = tkfont.Font(family=self.family, size=-max(5, int(round(self.fsize * self.s))),
                                           weight="bold" if "Bold" in self.fname else "normal")
        return self._fonts[key]

    def setTitle(self, t):
        pass

    def setFillColorRGB(self, r, g, b):
        self.fill = self._hex(r, g, b)

    def setStrokeColorRGB(self, r, g, b):
        self.stroke = self._hex(r, g, b)

    def setLineWidth(self, w):
        self.lw = w

    def setFont(self, name, size):
        self.fname, self.fsize = name, size

    def _text(self, x, y, text, anchor):
        if text == "":
            return
        f = self._font()
        self.cv.create_text(self.X(x), self.Yc(y) + f.metrics("descent"), text=text, anchor=anchor, font=f, fill=self.fill)

    def drawString(self, x, y, text):
        self._text(x, y, text, "sw")

    def drawRightString(self, x, y, text):
        self._text(x, y, text, "se")

    def rect(self, x, y, w, h, stroke=1, fill=0):
        self.cv.create_rectangle(self.X(x), self.Yc(y + h), self.X(x + w), self.Yc(y),
                                 fill=self.fill if fill else "", outline=self.stroke if stroke else "")

    def roundRect(self, x, y, w, h, r, stroke=1, fill=0):
        x0, y0, x1, y1, rr = self.X(x), self.Yc(y + h), self.X(x + w), self.Yc(y), r * self.s
        pts = [x0 + rr, y0, x1 - rr, y0, x1, y0, x1, y0 + rr, x1, y1 - rr, x1, y1, x1 - rr, y1, x0 + rr, y1,
               x0, y1, x0, y1 - rr, x0, y0 + rr, x0, y0]
        self.cv.create_polygon(pts, smooth=True, fill=self.fill if fill else "", outline=self.stroke if stroke else "")

    def line(self, x1, y1, x2, y2):
        self.cv.create_line(self.X(x1), self.Yc(y1), self.X(x2), self.Yc(y2), fill=self.stroke, width=max(1, int(round(self.lw * self.s))))

    def drawImage(self, img, x, y, width=None, height=None, mask=None):
        path = getattr(img, "fileName", None)
        if not path or not os.path.exists(path):
            return
        try:
            from PIL import Image
            wpx, hpx = max(1, int(width * self.s)), max(1, int(height * self.s))
            im = Image.open(path).convert("RGBA").resize((wpx, hpx), Image.LANCZOS)
            tmp = os.path.join(APP_DIR, "logo_page.png")
            im.save(tmp)
            ph = tk.PhotoImage(file=tmp)
            self._imgs.append(ph)
            self.cv.create_image(self.X(x), self.Yc(y + height), image=ph, anchor="nw")
        except Exception:  # noqa: BLE001
            pass

    def showPage(self):
        self.oy += self.H * self.s + self.gap
        self.pages += 1
        self._bg()

    def save(self):
        pass


class App(tk.Tk):
    def __init__(self):
        if sys.platform.startswith("win"):
            try:
                import ctypes
                ctypes.windll.shcore.SetProcessDpiAwareness(1)
            except Exception:  # noqa: BLE001
                pass
        super().__init__()
        global SC
        SC = max(1.0, self.winfo_fpixels("1i") / 96.0)
        self.title("Job Costing & Quotation Calculator")
        self.configure(bg=C["bg"])
        try:
            self._icon = tk.PhotoImage(data=ICON_PNG)
            self.iconphoto(True, self._icon)
        except tk.TclError:
            pass
        w, h = px(1280), px(840)
        self.geometry("%dx%d+%d+%d" % (w, h, max(0, (self.winfo_screenwidth() - w) // 2), max(0, (self.winfo_screenheight() - h) // 3)))
        self.minsize(px(1080), px(700))
        self.store = load_store()
        self.S = self.store["S"]
        self.J = self.job_by_id(self.store["current"])
        self.vars, self.cvars, self.boxes, self.pages, self.navs = {}, {}, {}, {}, {}
        self.invalid = set()
        self._cur_labels = []
        self._busy = False
        self.r = self.model = self.eff = None
        self.current = "job"
        self.sort = ("updated", True)
        self.cust_sel = None
        self._logo_img = None
        self._ttk_style()
        self._menu()
        self._shell()
        self.load_logo_preview()
        self.fill_all()
        self.refresh()
        self.show("jobs" if len(self.store["jobs"]) > 1 else "job")
        self.bind_all("<MouseWheel>", self._wheel)
        self.bind_all("<Button-4>", self._wheel)
        self.bind_all("<Button-5>", self._wheel)
        for key, fn in (("n", self.new_job_ui), ("e", self.save_pdf), ("d", self.duplicate_job),
                        ("f", self.focus_search)):
            self.bind_all("<Control-%s>" % key, lambda e, f=fn: f())
        for i, page in enumerate(("jobs", "job", "doc", "cust", "set"), 1):
            self.bind_all("<Control-Key-%d>" % i, lambda e, p=page: self.show(p))

    # ---------- base styling
    def _ttk_style(self):
        st = ttk.Style(self)
        try:
            st.theme_use("clam")
        except tk.TclError:
            pass
        st.configure("Treeview", rowheight=px(30), font=(FONT, 10), background=C["card"], fieldbackground=C["card"],
                     foreground=C["ink"], borderwidth=0, relief="flat")
        st.configure("Treeview.Heading", font=(FONT, 9, "bold"), background=C["soft"], foreground=C["muted"],
                     relief="flat", borderwidth=0, padding=(8, 7))
        st.map("Treeview", background=[("selected", C["sel"])], foreground=[("selected", C["ink"])])
        st.map("Treeview.Heading", background=[("active", C["neutral_bg"])])
        st.layout("Treeview", [("Treeview.treearea", {"sticky": "nswe"})])
        st.configure("Vertical.TScrollbar", background="#C9D2DE", troughcolor=C["bg"], bordercolor=C["bg"],
                     arrowcolor=C["bg"], lightcolor="#C9D2DE", darkcolor="#C9D2DE", gripcount=0, relief="flat", arrowsize=px(12))
        st.map("Vertical.TScrollbar", background=[("active", "#AEB9C8")])
        st.configure("Card.TCheckbutton", background=C["card"], foreground=C["ink"], font=(FONT, 10))
        st.map("Card.TCheckbutton", background=[("active", C["card"])])
        st.configure("TCombobox", fieldbackground=C["card"], background=C["soft"], bordercolor=C["field"], lightcolor=C["card"],
                     darkcolor=C["card"], arrowcolor=C["muted"], padding=px(6))
        st.map("TCombobox", fieldbackground=[("readonly", C["card"])], bordercolor=[("focus", C["accent"])])
        self.option_add("*TCombobox*Listbox.font", (FONT, 10))

    def _menu(self):
        mb = tk.Menu(self)
        f = tk.Menu(mb, tearoff=0)
        f.add_command(label="New job\tCtrl+N", command=self.new_job_ui)
        f.add_command(label="New job from template…", command=self.pick_template)
        f.add_command(label="Duplicate job\tCtrl+D", command=self.duplicate_job)
        f.add_command(label="Add the sample job", command=self.add_sample)
        f.add_separator()
        f.add_command(label="Save quote or invoice as PDF…\tCtrl+E", command=self.save_pdf)
        f.add_separator()
        f.add_command(label="Export backup…", command=self.export_backup)
        f.add_command(label="Import backup…", command=self.import_backup)
        f.add_command(label="Open data folder", command=self.open_data_folder)
        f.add_separator()
        f.add_command(label="Exit", command=self.destroy)
        mb.add_cascade(label="File", menu=f)
        h = tk.Menu(mb, tearoff=0)
        h.add_command(label="Where is my data stored?", command=self.where_data)
        h.add_command(label="Keyboard shortcuts", command=lambda: messagebox.showinfo(
            "Keyboard shortcuts", "Ctrl+N    New job\nCtrl+D    Duplicate job\nCtrl+E    Save as PDF\nCtrl+F    Search jobs\n"
            "Ctrl+1 to 5    Jobs, Job costing, Quote & invoice, Customers, Settings"))
        h.add_command(label="About", command=lambda: messagebox.showinfo(
            "About", "Job Costing & Quotation Calculator\n\nCost a job, price it to your target margin, track quotes and invoices, and send a PDF."))
        mb.add_cascade(label="Help", menu=h)
        self.config(menu=mb)

    # ---------- shell: sidebar, pages, status bar
    def _shell(self):
        status = tk.Frame(self, bg=C["card"], highlightthickness=1, highlightbackground=C["line"])
        status.pack(side="bottom", fill="x")
        self.lbl_saved = tk.Label(status, text="", bg=C["card"], fg=C["muted"], font=(FONT, 9), padx=px(14), pady=px(5))
        self.lbl_saved.pack(side="left")
        tk.Label(status, text="Data file:  " + DATA_FILE, bg=C["card"], fg=C["muted"], font=(FONT, 9), padx=px(14)).pack(side="right")

        side = tk.Frame(self, bg=C["side"], width=px(232))
        side.pack(side="left", fill="y")
        side.pack_propagate(False)
        brand = tk.Frame(side, bg=C["side"])
        brand.pack(fill="x", padx=px(18), pady=(px(24), px(22)))
        mark = tk.Canvas(brand, width=px(34), height=px(34), bg=C["side"], highlightthickness=0)
        mark.pack(side="left")
        mark.create_rectangle(0, 0, px(34), px(34), fill=C["accent"], outline="")
        for i, wd in enumerate((18, 12, 7)):
            y = px(10 + i * 7)
            mark.create_line(px(9), y, px(9 + wd), y, fill="white", width=px(2.4))
        tx = tk.Frame(brand, bg=C["side"])
        tx.pack(side="left", padx=(px(10), 0))
        tk.Label(tx, text="Job Costing", bg=C["side"], fg="white", font=(FONT, 12, "bold")).pack(anchor="w")
        tk.Label(tx, text="Quotation Calculator", bg=C["side"], fg=C["side_muted"], font=(FONT, 9)).pack(anchor="w")

        for key, label in (("jobs", "Jobs"), ("job", "Job costing"), ("doc", "Quote & invoice"),
                           ("cust", "Customers"), ("set", "Business settings")):
            item = tk.Frame(side, bg=C["side"], cursor="hand2")
            item.pack(fill="x")
            bar = tk.Frame(item, bg=C["side"], width=px(4))
            bar.pack(side="left", fill="y")
            lab = tk.Label(item, text=label, bg=C["side"], fg=C["side_fg"], font=(FONT, 11, "bold"), anchor="w", padx=px(18), pady=px(11), cursor="hand2")
            lab.pack(side="left", fill="x", expand=True)
            for wdg in (item, lab, bar):
                wdg.bind("<Button-1>", lambda e, k=key: self.show(k))
                wdg.bind("<Enter>", lambda e, k=key: self._nav_hover(k, True))
                wdg.bind("<Leave>", lambda e, k=key: self._nav_hover(k, False))
            self.navs[key] = (item, lab, bar)

        foot = tk.Frame(side, bg=C["side"])
        foot.pack(side="bottom", fill="x", padx=px(18), pady=px(18))
        tk.Frame(foot, bg="#1E3049", height=1).pack(fill="x", pady=(0, px(12)))
        self.lbl_side_biz = tk.Label(foot, text="", bg=C["side"], fg="white", font=(FONT, 10, "bold"), anchor="w", justify="left")
        autowrap(self.lbl_side_biz)
        self.lbl_side_biz.pack(fill="x")
        tk.Label(foot, text="Saved on this computer", bg=C["side"], fg=C["side_muted"], font=(FONT, 9)).pack(anchor="w")

        self.content = tk.Frame(self, bg=C["bg"])
        self.content.pack(side="left", fill="both", expand=True)
        self.pages["jobs"] = self._page_jobs(self.content)
        self.pages["job"] = self._page_job(self.content)
        self.pages["doc"] = self._page_doc(self.content)
        self.pages["cust"] = self._page_customers(self.content)
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
        if key == "jobs":
            self.refresh_jobs()
        elif key == "cust":
            self.refresh_customers()

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

    # ---------- building blocks
    def head(self, parent, crumb, title, buttons=()):
        h = tk.Frame(parent, bg=C["bg"])
        h.pack(fill="x", pady=(0, px(16)))
        left = tk.Frame(h, bg=C["bg"])
        left.pack(side="left")
        crumb_lbl = tk.Label(left, text=crumb.upper(), bg=C["bg"], fg=C["accent"], font=(FONT, 9, "bold"))
        crumb_lbl.pack(anchor="w")
        lbl = tk.Label(left, text=title, bg=C["bg"], fg=C["ink"], font=(FONT, 20, "bold"))
        lbl.pack(anchor="w")
        right = tk.Frame(h, bg=C["bg"])
        right.pack(side="right", anchor="s")
        for b in buttons:
            b(right).pack(side="left", padx=(px(8), 0))
        return crumb_lbl, lbl

    def card(self, parent, title, sub=None, chip=False, pad_bottom=14):
        outer = tk.Frame(parent, bg=C["card"], highlightthickness=1, highlightbackground=C["line"])
        outer.pack(fill="x", pady=(0, px(pad_bottom)))
        top = tk.Frame(outer, bg=C["card"])
        top.pack(fill="x", padx=px(20), pady=(px(16), 0))
        tk.Label(top, text=title, bg=C["card"], fg=C["ink"], font=(FONT, 12, "bold")).pack(side="left")
        chip_lbl = None
        if chip:
            chip_lbl = tk.Label(top, text="", bg=C["neutral_bg"], fg=C["ink"], font=(FONT, 10, "bold"), padx=px(10), pady=px(2))
            chip_lbl.pack(side="right")
        if sub:
            autowrap(tk.Label(outer, text=sub, bg=C["card"], fg=C["muted"], font=(FONT, 9), anchor="w", justify="left")).pack(fill="x", padx=px(20), pady=(px(2), 0))
        body = tk.Frame(outer, bg=C["card"])
        body.pack(fill="x", padx=px(20), pady=(px(12), px(18)))
        body.chip = chip_lbl
        return body

    def bind_var(self, store, key):
        v = tk.StringVar()
        if store == "C":
            self.cvars[key] = v
            return v
        self.vars[(store, key)] = (v, "str")
        if key == "emailSubject":
            v.trace_add("write", lambda *_: None if self._busy else (self.J.__setitem__("emailEdited", True), self.on_change()))
        else:
            v.trace_add("write", lambda *_: self.on_change())
        return v

    def field(self, parent, store, key, label, unit="", prefix="", hint="", width=10, text=False, height=3):
        f = tk.Frame(parent, bg=C["card"])
        tk.Label(f, text=label, bg=C["card"], fg=C["ink"], font=(FONT, 9, "bold"), anchor="w").pack(anchor="w", pady=(0, px(4)))
        box = tk.Frame(f, bg=C["card"], highlightthickness=1, highlightbackground=C["field"])
        box.pack(fill="x")
        if store != "C":
            self.boxes[(store, key)] = box
        if text:
            t = tk.Text(box, height=height, width=width, wrap="word", font=(FONT, 10), relief="flat", bd=0, bg=C["card"], fg=C["ink"],
                        insertbackground=C["ink"], highlightthickness=0, padx=px(8), pady=px(6), undo=True)
            t.pack(fill="x")
            if store != "C":
                t.bind("<KeyRelease>", lambda e: self.on_text(key))
                self.vars[(store, key)] = (t, "text")
            else:
                self.cvars[key] = t
            t.bind("<FocusIn>", lambda e: box.config(highlightbackground=C["accent"]))
            t.bind("<FocusOut>", lambda e: self.paint_boxes())
        else:
            if prefix:
                pl = tk.Label(box, text=prefix, bg=C["soft"], fg=C["muted"], font=(FONT, 10), padx=px(10))
                pl.pack(side="left", fill="y")
                self._cur_labels.append(pl)
            v = self.bind_var(store, key)
            e = tk.Entry(box, textvariable=v, relief="flat", bd=0, font=(FONT, 11), bg=C["card"], fg=C["ink"],
                         insertbackground=C["ink"], highlightthickness=0, width=width)
            e.pack(side="left", fill="x", expand=True, ipady=px(6), padx=px(8))
            if unit:
                tk.Label(box, text=unit, bg=C["soft"], fg=C["muted"], font=(FONT, 9, "bold"), padx=px(10)).pack(side="right", fill="y")
            e.bind("<FocusIn>", lambda ev, b=box, en=e: (b.config(highlightbackground=C["accent"]), en.after_idle(lambda: en.select_range(0, "end"))))
            e.bind("<FocusOut>", lambda ev: self.paint_boxes())
        if hint:
            autowrap(tk.Label(f, text=hint, bg=C["card"], fg=C["muted"], font=(FONT, 9), justify="left", anchor="w")).pack(fill="x", pady=(px(4), 0))
        return f

    def frow(self, body, specs, last=False):
        row = tk.Frame(body, bg=C["card"])
        row.pack(fill="x", pady=(0, 0 if last else px(12)))
        for i, sp in enumerate(specs):
            self.field(row, **sp).pack(side="left", fill="x", expand=True, padx=(0 if i == 0 else px(14), 0), anchor="n")
        return row

    def paint_boxes(self):
        focus = str(self.focus_get() or "")
        for key, box in self.boxes.items():
            inside = focus.startswith(str(box) + ".") or focus == str(box)
            if key in self.invalid:
                box.config(highlightbackground=C["bad"])
            else:
                box.config(highlightbackground=C["accent"] if inside else C["field"])

    def plain_entry(self, parent, var, width=24):
        box = tk.Frame(parent, bg=C["card"], highlightthickness=1, highlightbackground=C["field"])
        e = tk.Entry(box, textvariable=var, relief="flat", bd=0, font=(FONT, 10), bg=C["card"], fg=C["ink"], highlightthickness=0, width=width)
        e.pack(fill="x", ipady=px(6), padx=px(8))
        e.bind("<FocusIn>", lambda ev: box.config(highlightbackground=C["accent"]))
        e.bind("<FocusOut>", lambda ev: box.config(highlightbackground=C["field"]))
        return box, e

    def make_list(self, parent, title, sub, key, cols):
        body = self.card(parent, title, sub, chip=True)
        tree = ttk.Treeview(body, columns=[c[0] for c in cols], show="headings", height=3, selectmode="browse")
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
            tk.Label(fr, text=head, bg=C["card"], fg=C["muted"], font=(FONT, 9, "bold")).pack(anchor="w")
            box, e = self.plain_entry(fr, tk.StringVar(), 20 if cid == "d" else 9)
            box.pack(fill="x")
            e.bind("<Return>", lambda ev, k=key, es=ents: self.add_row(k, es))
            ents[cid] = e
        btns = tk.Frame(form, bg=C["card"])
        btns.pack(side="left", anchor="s")
        Btn(btns, "Add", lambda k=key, es=ents: self.add_row(k, es), "primary").pack(side="left", padx=(0, px(6)))
        Btn(btns, "Remove", lambda k=key, t=tree: self.remove_row(k, t)).pack(side="left")
        return tree, body.chip

    # ================================================================ JOBS LIST
    def _page_jobs(self, parent):
        page = tk.Frame(parent, bg=C["bg"])
        self.head(page, "Jobs", "All quotes and invoices", [
            lambda p: Btn(p, "New from template", self.pick_template), lambda p: Btn(p, "New job", self.new_job_ui, "primary")])
        kp = tk.Frame(page, bg=C["bg"])
        kp.pack(fill="x", pady=(0, px(16)))
        self.kpi = {}
        for i, (k, lab) in enumerate((("wait", "AWAITING REPLY"), ("acc", "ACCEPTED, TO INVOICE"), ("out", "OUTSTANDING"),
                                      ("over", "OVERDUE"), ("paid", "PAID THIS MONTH"))):
            kp.columnconfigure(i, weight=1, uniform="k")
            tile = tk.Frame(kp, bg=C["card"], highlightthickness=1, highlightbackground=C["line"])
            tile.grid(row=0, column=i, sticky="nsew", padx=(0 if i == 0 else px(10), 0))
            tk.Label(tile, text=lab, bg=C["card"], fg=C["muted"], font=(FONT, 8, "bold"), anchor="w").pack(fill="x", padx=px(14), pady=(px(12), 0))
            val = tk.Label(tile, text="", bg=C["card"], fg=C["ink"], font=(FONT, 17, "bold"), anchor="w")
            val.pack(fill="x", padx=px(14))
            sub = tk.Label(tile, text="", bg=C["card"], fg=C["muted"], font=(FONT, 9), anchor="w")
            sub.pack(fill="x", padx=px(14), pady=(0, px(12)))
            self.kpi[k] = (val, sub)

        box = tk.Frame(page, bg=C["card"], highlightthickness=1, highlightbackground=C["line"])
        box.pack(fill="both", expand=True)
        tb = tk.Frame(box, bg=C["card"])
        tb.pack(fill="x", padx=px(16), pady=px(14))
        for text, fn, kind in (("Open", self.open_selected, "primary"), ("Duplicate", self.duplicate_selected, "secondary"),
                               ("Save as template", self.save_template, "secondary"), ("Delete", self.delete_job, "danger")):
            Btn(tb, text, fn, kind).pack(side="right", padx=(px(6), 0))
        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", lambda *_: self.refresh_jobs())
        tk.Label(tb, text="Search", bg=C["card"], fg=C["muted"], font=(FONT, 9, "bold")).pack(side="left", padx=(0, px(8)))
        sbox, self.search_entry = self.plain_entry(tb, self.search_var, 22)
        sbox.pack(side="left")
        tk.Label(tb, text="Show", bg=C["card"], fg=C["muted"], font=(FONT, 9, "bold")).pack(side="left", padx=(px(16), px(8)))
        self.filter_var = tk.StringVar(value="All")
        cb = ttk.Combobox(tb, textvariable=self.filter_var, values=STATUS_FILTERS, state="readonly", width=10, font=(FONT, 10))
        cb.pack(side="left")
        cb.bind("<<ComboboxSelected>>", lambda e: self.refresh_jobs())
        cols = [("no", "Number", 110, "w"), ("job", "Job", 260, "w"), ("client", "Customer", 170, "w"), ("type", "Type", 80, "w"),
                ("status", "Status", 90, "w"), ("date", "Date", 100, "w"), ("total", "Total", 100, "e")]
        wrap = tk.Frame(box, bg=C["card"])
        wrap.pack(fill="both", expand=True)
        self.jobs_tree = ttk.Treeview(wrap, columns=[c[0] for c in cols], show="headings", selectmode="browse")
        for cid, head, w, anc in cols:
            self.jobs_tree.heading(cid, text=head, anchor=anc, command=lambda c=cid: self.sort_jobs(c))
            self.jobs_tree.column(cid, width=px(w), anchor=anc, stretch=(cid in ("job", "client")))
        sb = ttk.Scrollbar(wrap, orient="vertical", command=self.jobs_tree.yview)
        self.jobs_tree.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self.jobs_tree.pack(side="left", fill="both", expand=True)
        self.jobs_tree.tag_configure("Overdue", foreground=C["bad"])
        self.jobs_tree.tag_configure("Paid", foreground=C["good"])
        self.jobs_tree.tag_configure("Declined", foreground=C["muted"])
        self.jobs_tree.tag_configure("current", font=(FONT, 10, "bold"))
        self.jobs_tree.bind("<Double-1>", lambda e: self.open_selected())
        self.jobs_tree.bind("<Return>", lambda e: self.open_selected())
        self.lbl_empty = tk.Label(box, text="No jobs match. Click New job to start one.", bg=C["card"], fg=C["muted"], font=(FONT, 10))
        return page

    def job_by_id(self, jid):
        for j in self.store["jobs"]:
            if j["id"] == jid:
                return j
        return self.store["jobs"][0]

    def job_row(self, j):
        r, eff = job_calc(self.S, j)
        inv = j.get("docType") == "invoice"
        return {"no": (j.get("invoiceNo") if inv else j.get("quoteNo")) or "", "job": j.get("title") or "Untitled job",
                "client": j.get("client") or "", "type": "Invoice" if inv else "Quote", "status": display_status(eff, j),
                "date": j.get("issueDate", ""), "total": r["total"], "r": r, "eff": eff, "job_obj": j}

    def refresh_jobs(self):
        if not hasattr(self, "jobs_tree"):
            return
        rows = [self.job_row(j) for j in self.store["jobs"]]
        self.update_kpis(rows)
        q = self.search_var.get().strip().lower()
        flt = self.filter_var.get()
        shown = []
        for r in rows:
            if flt != "All" and r["status"] != flt:
                continue
            if q and q not in (r["no"] + " " + r["job"] + " " + r["client"]).lower():
                continue
            shown.append(r)
        col, rev = self.sort
        key = {"no": lambda r: r["no"].lower(), "job": lambda r: r["job"].lower(), "client": lambda r: r["client"].lower(),
               "type": lambda r: r["type"], "status": lambda r: r["status"], "date": lambda r: r["date"],
               "total": lambda r: r["total"], "updated": lambda r: r["job_obj"].get("updated", "")}[col]
        shown.sort(key=key, reverse=rev)
        tree = self.jobs_tree
        tree.delete(*tree.get_children())
        for r in shown:
            j = r["job_obj"]
            tags = [r["status"]]
            if j["id"] == self.J["id"]:
                tags.append("current")
            tree.insert("", "end", iid=j["id"], values=(r["no"], r["job"], r["client"], r["type"], r["status"],
                                                          short_date(parse_date(r["date"])), money(r["eff"], r["total"])), tags=tags)
        if shown:
            self.lbl_empty.place_forget()
        else:
            self.lbl_empty.place(relx=0.5, rely=0.6, anchor="center")

    def sort_jobs(self, col):
        self.sort = (col, not self.sort[1]) if self.sort[0] == col else (col, col in ("date", "total"))
        self.refresh_jobs()

    def update_kpis(self, rows):
        M = lambda v: money(self.S, v)  # noqa: E731
        wait = [r for r in rows if r["type"] == "Quote" and r["status"] == "Sent"]
        acc = [r for r in rows if r["type"] == "Quote" and r["status"] == "Accepted"]
        out = [r for r in rows if r["type"] == "Invoice" and r["status"] in ("Sent", "Overdue")]
        over = [r for r in rows if r["type"] == "Invoice" and r["status"] == "Overdue"]
        month = today().strftime("%Y-%m")
        paid = [r for r in rows if r["type"] == "Invoice" and r["status"] == "Paid" and str(r["job_obj"].get("paidDate", "")).startswith(month)]
        bal = lambda r: max(0.0, r["total"] - pos(r["job_obj"].get("paid")))  # noqa: E731
        data = {"wait": (sum(r["total"] for r in wait), len(wait), "quote"), "acc": (sum(r["total"] for r in acc), len(acc), "quote"),
                "out": (sum(bal(r) for r in out), len(out), "invoice"), "over": (sum(bal(r) for r in over), len(over), "invoice"),
                "paid": (sum(r["total"] for r in paid), len(paid), "invoice")}
        for k, (amount, n, noun) in data.items():
            val, sub = self.kpi[k]
            val.config(text=M(amount), fg=(C["bad"] if (k == "over" and n) else C["ink"]))
            sub.config(text="%d %s%s" % (n, noun, "" if n == 1 else "s"))

    def selected_job(self):
        sel = self.jobs_tree.selection()
        return self.job_by_id(sel[0]) if sel else None

    def open_selected(self):
        j = self.selected_job()
        if j:
            self.set_current(j)
            self.show("job")

    def duplicate_selected(self):
        j = self.selected_job()
        if j:
            self.duplicate_job(j)

    def set_current(self, job):
        self.J = job
        self.store["current"] = job["id"]
        self.fill_all()
        self.refresh()

    def new_job_ui(self):
        j = new_job(self.S)
        self.store["jobs"].append(j)
        self.set_current(j)
        self.show("job")
        self.after(50, lambda: self.focus_var("J", "title"))

    def focus_var(self, store, key):
        box = self.boxes.get((store, key))
        if box:
            for w in box.winfo_children():
                if isinstance(w, (tk.Entry, tk.Text)):
                    w.focus_set()
                    break

    def focus_search(self):
        self.show("jobs")
        self.search_entry.focus_set()

    def add_sample(self):
        j = sample_job()
        assign_quote_no(self.S, j)
        self.store["jobs"].append(j)
        self.set_current(j)
        self.show("job")

    def duplicate_job(self, src=None):
        src = src if isinstance(src, dict) else self.J
        j = copy.deepcopy(src)
        now = dt.datetime.now().isoformat(timespec="seconds")
        j.update({"id": uuid.uuid4().hex[:8], "status": "Draft", "snap": None, "paidDate": "", "invoiceNo": "", "docType": "quote",
                  "issueDate": today().isoformat(), "paid": 0, "emailEdited": False, "sample": False, "created": now, "updated": now})
        assign_quote_no(self.S, j)
        self.store["jobs"].append(j)
        self.set_current(j)
        self.show("job")
        self.say("Duplicated. This copy is a new draft quote.")

    def delete_job(self):
        j = self.selected_job()
        if not j:
            return
        if not messagebox.askyesno("Delete job", "Delete \"%s\" (%s)?\n\nThis cannot be undone." % (j.get("title") or "Untitled job", j.get("quoteNo"))):
            return
        self.store["jobs"] = [x for x in self.store["jobs"] if x["id"] != j["id"]]
        if not self.store["jobs"]:
            self.store["jobs"].append(new_job(self.S))
        if self.J["id"] == j["id"]:
            self.set_current(sorted(self.store["jobs"], key=lambda x: x.get("updated", ""))[-1])
        save_store(self.store)
        self.refresh_jobs()

    # ---------- templates
    def save_template(self):
        j = self.selected_job() or self.J
        name = simpledialog.askstring("Save as template", "Template name:", initialvalue=j.get("title") or "", parent=self)
        if not name or not name.strip():
            return
        t = {"id": uuid.uuid4().hex[:8], "name": name.strip()}
        for k in ("title", "scope", "people", "hours", "km", "travelHours"):
            t[k] = j.get(k)
        t["materials"] = copy.deepcopy(j.get("materials", []))
        t["other"] = copy.deepcopy(j.get("other", []))
        self.store["templates"].append(t)
        save_store(self.store)
        self.say("Template saved: %s" % t["name"])
        messagebox.showinfo("Template saved", "\"%s\" is now in New from template." % t["name"])

    def pick_template(self):
        dlg = tk.Toplevel(self)
        dlg.title("New job from template")
        dlg.configure(bg=C["bg"])
        dlg.transient(self)
        w, h = px(560), px(420)
        dlg.geometry("%dx%d+%d+%d" % (w, h, self.winfo_rootx() + px(260), self.winfo_rooty() + px(120)))
        tk.Label(dlg, text="Start from a template", bg=C["bg"], fg=C["ink"], font=(FONT, 14, "bold")).pack(anchor="w", padx=px(20), pady=(px(18), px(2)))
        tk.Label(dlg, text="Labour, travel and materials are filled in. Rates come from your Business settings.", bg=C["bg"], fg=C["muted"], font=(FONT, 9)).pack(anchor="w", padx=px(20), pady=(0, px(10)))
        tree = ttk.Treeview(dlg, columns=("name", "what"), show="headings", selectmode="browse", height=9)
        tree.heading("name", text="Template", anchor="w")
        tree.heading("what", text="Crew and hours", anchor="w")
        tree.column("name", width=px(300), anchor="w")
        tree.column("what", width=px(180), anchor="w")
        tree.pack(fill="both", expand=True, padx=px(20))

        def fill():
            tree.delete(*tree.get_children())
            for t in self.store["templates"]:
                tree.insert("", "end", iid=t["id"], values=(t["name"], "%s people x %s hrs" % (self._show(t.get("people")), self._show(t.get("hours")))))
        fill()

        def use():
            sel = tree.selection()
            if not sel:
                return
            t = [x for x in self.store["templates"] if x["id"] == sel[0]][0]
            base = {k: copy.deepcopy(t.get(k)) for k in ("title", "scope", "people", "hours", "km", "travelHours", "materials", "other")}
            j = new_job(self.S, base)
            self.store["jobs"].append(j)
            dlg.destroy()
            self.set_current(j)
            self.show("job")

        def remove():
            sel = tree.selection()
            if sel and messagebox.askyesno("Delete template", "Delete this template?", parent=dlg):
                self.store["templates"] = [x for x in self.store["templates"] if x["id"] != sel[0]]
                save_store(self.store)
                fill()
        bar = tk.Frame(dlg, bg=C["bg"])
        bar.pack(fill="x", padx=px(20), pady=px(14))
        Btn(bar, "Use template", use, "primary").pack(side="right")
        Btn(bar, "Close", dlg.destroy).pack(side="right", padx=px(8))
        Btn(bar, "Delete", remove, "danger").pack(side="left")
        tree.bind("<Double-1>", lambda e: use())
        dlg.grab_set()

    # ================================================================ JOB COSTING
    def _page_job(self, parent):
        page = tk.Frame(parent, bg=C["bg"])
        self.crumb_job, self.lbl_jobhead = self.head(page, "Job costing", "New job", [
            lambda p: Btn(p, "All jobs", lambda: self.show("jobs")), lambda p: Btn(p, "Duplicate", self.duplicate_job),
            lambda p: Btn(p, "Save as template", self.save_template)])
        self.banner = tk.Label(page, text="Sample job. A two-person end-of-lease clean that a gut-feel quote would underprice. Change any figure to cost your own job.",
                               bg="#E8EEFD", fg=C["ink"], font=(FONT, 10), anchor="w", padx=px(14), pady=px(8), justify="left")
        autowrap(self.banner, 28)
        self.lockbar = tk.Frame(page, bg=C["warn_bg"])
        self.lock_lbl = tk.Label(self.lockbar, text="Pricing is locked at the rates in force when this job was sent, so later changes to your settings do not alter it.",
                                 bg=C["warn_bg"], fg=C["warn"], font=(FONT, 10), anchor="w", justify="left")
        autowrap(self.lock_lbl, 12)
        self.lock_lbl.pack(side="left", fill="x", expand=True, padx=px(14), pady=px(8))
        Btn(self.lockbar, "Use current rates", self.relock).pack(side="right", padx=px(10), pady=px(6))
        body = tk.Frame(page, bg=C["bg"])
        body.pack(fill="both", expand=True)
        self.job_body = body
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
        self.frow(b, [dict(store="J", key="title", label="Job title", width=22), dict(store="J", key="client", label="Customer", width=16)])
        self.frow(b, [dict(store="J", key="custEmail", label="Customer email", width=22), dict(store="J", key="custPhone", label="Customer phone", width=16)])
        self.frow(b, [dict(store="J", key="custAddress", label="Customer address", text=True, height=2, width=30)])
        self.frow(b, [dict(store="J", key="scope", label="Scope of work", text=True, height=3, width=30)])
        cb = tk.Frame(b, bg=C["card"])
        cb.pack(fill="x")
        self.btn_pick_cust = Btn(cb, "Choose saved customer", self.pick_customer_menu)
        self.btn_pick_cust.pack(side="left")
        Btn(cb, "Save to customer list", self.save_customer_from_job).pack(side="left", padx=px(8))

        b = self.card(L, "Labour", None, chip=True)
        self.chip_labour = b.chip
        self.frow(b, [dict(store="J", key="people", label="People on the job", unit="people", width=6),
                      dict(store="J", key="hours", label="Hours on site, each", unit="hrs", width=6)])
        self.lbl_labour = tk.Label(b, text="", bg=C["card"], fg=C["muted"], font=(FONT, 9), anchor="w")
        self.lbl_labour.pack(anchor="w")

        b = self.card(L, "Travel", None, chip=True)
        self.chip_travel = b.chip
        self.frow(b, [dict(store="J", key="km", label="Distance, return trip", unit="km", width=6),
                      dict(store="J", key="travelHours", label="Travel time, return trip", unit="hrs", width=6)])
        self.lbl_travel = autowrap(tk.Label(b, text="", bg=C["card"], fg=C["muted"], font=(FONT, 9), anchor="w", justify="left"))
        self.lbl_travel.pack(fill="x")

        self.tree_mat, self.chip_mat = self.make_list(L, "Materials & supplies", "Everything you buy for this job.", "materials",
                                                      [("d", "Item", 260, "w"), ("q", "Qty", 70, "e"), ("c", "Unit cost", 100, "e")])
        self.tree_oth, self.chip_oth = self.make_list(L, "Other costs", "Equipment hire, subcontractors, tip fees and permits.", "other",
                                                      [("d", "Description", 330, "w"), ("a", "Amount", 110, "e")])

        hero = tk.Frame(right, bg=C["side"])
        hero.pack(fill="x", pady=(0, px(14)))
        hi = tk.Frame(hero, bg=C["side"])
        hi.pack(fill="x", padx=px(22), pady=px(18))
        self.lbl_priceLab = tk.Label(hi, text="", bg=C["side"], fg="#93A4BB", font=(FONT, 9, "bold"))
        self.lbl_priceLab.pack(anchor="w")
        self.lbl_price = tk.Label(hi, text="", bg=C["side"], fg="white", font=(FONT, 34, "bold"))
        self.lbl_price.pack(anchor="w")
        self.lbl_taxline = tk.Label(hi, text="", bg=C["side"], fg="#93A4BB", font=(FONT, 10))
        self.lbl_taxline.pack(anchor="w")
        self.lbl_flag = autowrap(tk.Label(hi, text="", bg=C["side"], fg="#F0B25C", font=(FONT, 9), justify="left", anchor="w"))
        self.lbl_flag.pack(fill="x")
        tk.Frame(hi, bg="#263A52", height=1).pack(fill="x", pady=(px(12), px(10)))
        grid = tk.Frame(hi, bg=C["side"])
        grid.pack(fill="x")
        grid.columnconfigure(0, weight=1)
        grid.columnconfigure(1, weight=1)
        self.stat = {}
        for i, (k, lab) in enumerate((("cost", "TOTAL COST"), ("profit", "PROFIT"), ("margin", "MARGIN"), ("pph", "PROFIT PER HOUR"))):
            cell = tk.Frame(grid, bg=C["side"])
            cell.grid(row=i // 2, column=i % 2, sticky="w", pady=px(4))
            tk.Label(cell, text=lab, bg=C["side"], fg="#93A4BB", font=(FONT, 8, "bold")).pack(anchor="w")
            self.stat[k] = tk.Label(cell, text="", bg=C["side"], fg="white", font=(FONT, 14, "bold"))
            self.stat[k].pack(anchor="w")

        b = self.card(right, "Compare with your usual quote")
        self.frow(b, [dict(store="J", key="gut", label="Your usual quote, before tax", prefix="$", width=10)])
        self.verd = tk.Frame(b, bg=C["neutral_bg"])
        self.verd.pack(fill="x")
        self.lbl_vhead = tk.Label(self.verd, text="", bg=C["neutral_bg"], fg=C["ink"], font=(FONT, 10, "bold"), anchor="w", justify="left")
        autowrap(self.lbl_vhead)
        self.lbl_vhead.pack(fill="x", padx=px(12), pady=(px(10), 0))
        self.lbl_vbody = tk.Label(self.verd, text="", bg=C["neutral_bg"], fg=C["ink"], font=(FONT, 10), anchor="w", justify="left")
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
        rows = [("labour", "Labour", "#2457E6"), ("travel", "Travel", "#0E8A8A"), ("materials", "Materials & supplies", "#C27A0E"),
                ("other", "Other costs", "#7A4FBF"), ("direct", "Direct costs", None), ("overhead", "Overhead", "#8393A3"),
                ("cost", "Total cost", None), ("profit", "Profit", "#12A266"), ("price", "Quote price", None)]
        for i, (k, lab, col) in enumerate(rows):
            strong = col is None
            if strong:
                tk.Frame(tbl, bg=C["line"], height=1).grid(row=i * 2, column=0, columnspan=4, sticky="ew")
            else:
                tk.Frame(tbl, bg=col, width=px(10), height=px(10)).grid(row=i * 2 + 1, column=0, sticky="w", padx=(0, px(8)))
            f = (FONT, 10, "bold") if strong else (FONT, 10)
            tk.Label(tbl, text=lab, bg=C["card"], fg=C["ink"], font=f, anchor="w").grid(row=i * 2 + 1, column=1, sticky="w", pady=px(3))
            a = tk.Label(tbl, text="", bg=C["card"], fg=C["ink"], font=f, anchor="e")
            a.grid(row=i * 2 + 1, column=2, sticky="e", padx=(px(10), 0))
            p = tk.Label(tbl, text="", bg=C["card"], fg=C["muted"], font=(FONT, 9), width=6, anchor="e")
            p.grid(row=i * 2 + 1, column=3, sticky="e")
            self.brk[k] = (a, p)
        return page

    def relock(self):
        self.J["snap"] = take_snap(self.S)
        self.refresh()

    # ================================================================ QUOTE & INVOICE
    def _page_doc(self, parent):
        page = tk.Frame(parent, bg=C["bg"])
        self.crumb_doc, self.lbl_dochead = self.head(page, "Quote & invoice", "Quote", [
            lambda p: Btn(p, "Copy as text", self.copy_doc), lambda p: Btn(p, "Save as PDF…", self.save_pdf, "primary")])
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

        left.canvas.config(bg=GREY)
        left.inner.config(bg=GREY)
        self.preview = tk.Canvas(left.inner, bg=GREY, highlightthickness=0, bd=0, height=px(800))
        self.preview.pack(fill="x")

        R_ = right.inner
        b = self.card(R_, "Document")
        self.doc_type = tk.StringVar(value="quote")
        self.doc_type.trace_add("write", lambda *_: self.on_change())
        Seg(b, self.doc_type, [("quote", "Quote"), ("invoice", "Invoice")]).pack(anchor="w", pady=(0, px(12)))
        sf = tk.Frame(b, bg=C["card"])
        sf.pack(fill="x", pady=(0, px(12)))
        tk.Label(sf, text="Status", bg=C["card"], fg=C["ink"], font=(FONT, 9, "bold")).pack(anchor="w", pady=(0, px(4)))
        self.status_var = self.bind_var("J", "status")
        self.cmb_status = ttk.Combobox(sf, textvariable=self.status_var, values=QUOTE_STATUSES, state="readonly", font=(FONT, 10))
        self.cmb_status.pack(fill="x")
        self.lbl_status_hint = autowrap(tk.Label(sf, text="", bg=C["card"], fg=C["muted"], font=(FONT, 9), justify="left", anchor="w"))
        self.lbl_status_hint.pack(fill="x", pady=(px(4), 0))
        self.row_actions = tk.Frame(b, bg=C["card"])
        self.row_actions.pack(fill="x", pady=(0, px(12)))
        self.btn_convert = Btn(self.row_actions, "Convert to invoice", self.convert_to_invoice, "primary")
        self.btn_paid = Btn(self.row_actions, "Mark as paid", lambda: self.status_var.set("Paid"), "primary")
        self.row_no = tk.Frame(b, bg=C["card"])
        self.row_no.pack(fill="x", pady=(0, px(12)))
        self.f_qno = self.field(self.row_no, "J", "quoteNo", "Quote number", width=12)
        self.f_ino = self.field(self.row_no, "J", "invoiceNo", "Invoice number", width=12)
        self.f_date = self.field(self.row_no, "J", "issueDate", "Issue date (YYYY-MM-DD)", width=12)
        self.f_date.pack(side="right", fill="x", expand=True, padx=(px(14), 0))
        self.f_paid = self.field(b, "J", "paid", "Amount already received, including tax", prefix="$", width=10)
        self.chk_item = tk.Frame(b, bg=C["card"])
        self.chk_item.pack(fill="x")
        self.itemised = tk.BooleanVar()
        self.itemised.trace_add("write", lambda *_: self.on_change())
        ttk.Checkbutton(self.chk_item, text="Show itemised lines", variable=self.itemised, style="Card.TCheckbutton").pack(anchor="w")
        autowrap(tk.Label(self.chk_item, text="Splits the price into labour, materials and other costs. Overhead and profit are spread across the lines, so your costs stay private.",
                          bg=C["card"], fg=C["muted"], font=(FONT, 9), justify="left", anchor="w")).pack(fill="x", padx=(px(22), 0))

        b = self.card(R_, "Send to customer", "Save the PDF, then attach it to your email.", pad_bottom=0)
        bb = tk.Frame(b, bg=C["card"])
        bb.pack(fill="x", pady=(0, px(12)))
        Btn(bb, "Save as PDF…", self.save_pdf, "primary").pack(side="left")
        self.frow(b, [dict(store="J", key="emailSubject", label="Email subject", width=24)])
        self.frow(b, [dict(store="J", key="emailBody", label="Email message", text=True, height=9, width=24)])
        bb2 = tk.Frame(b, bg=C["card"])
        bb2.pack(fill="x")
        Btn(bb2, "Open in email app", self.open_email).pack(side="left")
        Btn(bb2, "Copy message", self.copy_msg).pack(side="left", padx=px(6))
        Btn(bb2, "Reset", self.reset_msg).pack(side="left")
        self.lbl_doc_status = autowrap(tk.Label(b, text="", bg=C["card"], fg=C["muted"], font=(FONT, 9), justify="left", anchor="w"))
        self.lbl_doc_status.pack(fill="x", pady=(px(10), 0))
        return page

    def convert_to_invoice(self):
        self._busy = True
        self.doc_type.set("invoice")
        self.vars[("J", "issueDate")][0].set(today().isoformat())
        self.status_var.set("Draft")
        self.J["emailEdited"] = False
        self._busy = False
        self.on_change()
        self.say("Converted to an invoice. Set the status to Sent once you have sent it.")

    # ================================================================ CUSTOMERS
    def _page_customers(self, parent):
        page = tk.Frame(parent, bg=C["bg"])
        self.head(page, "Customers", "Customer list", [lambda p: Btn(p, "New customer", self.cust_new, "primary")])
        body = tk.Frame(page, bg=C["bg"])
        body.pack(fill="both", expand=True)
        body.columnconfigure(0, weight=1)
        body.columnconfigure(1, minsize=px(400))
        body.rowconfigure(0, weight=1)
        lbox = tk.Frame(body, bg=C["card"], highlightthickness=1, highlightbackground=C["line"])
        lbox.grid(row=0, column=0, sticky="nsew")
        tb = tk.Frame(lbox, bg=C["card"])
        tb.pack(fill="x", padx=px(16), pady=px(14))
        self.cust_search = tk.StringVar()
        self.cust_search.trace_add("write", lambda *_: self.refresh_customers())
        sbox, _ = self.plain_entry(tb, self.cust_search, 28)
        sbox.pack(side="left")
        tk.Label(tb, text="Search customers", bg=C["card"], fg=C["muted"], font=(FONT, 9)).pack(side="left", padx=px(10))
        cols = [("name", "Name", 160, "w"), ("email", "Email", 190, "w"), ("phone", "Phone", 105, "w"), ("jobs", "Jobs", 44, "e")]
        wrap = tk.Frame(lbox, bg=C["card"])
        wrap.pack(fill="both", expand=True)
        self.cust_tree = ttk.Treeview(wrap, columns=[c[0] for c in cols], show="headings", selectmode="browse")
        for cid, head, w, anc in cols:
            self.cust_tree.heading(cid, text=head, anchor=anc)
            self.cust_tree.column(cid, width=px(w), minwidth=px(w), anchor=anc, stretch=(cid == "name"))
        self.cust_tree.pack(side="left", fill="both", expand=True)
        self.cust_tree.bind("<<TreeviewSelect>>", lambda e: self.cust_select())
        self.cust_empty = tk.Label(lbox, text="No customers yet. Add one on the right, or save one from a job.", bg=C["card"], fg=C["muted"], font=(FONT, 10))

        right = ScrollFrame(body, C["bg"])
        right.grid(row=0, column=1, sticky="nsew", padx=(px(20), 0))
        b = self.card(right.inner, "Customer details", pad_bottom=0)
        self.frow(b, [dict(store="C", key="name", label="Name", width=22)])
        self.frow(b, [dict(store="C", key="email", label="Email", width=14), dict(store="C", key="phone", label="Phone", width=12)])
        self.frow(b, [dict(store="C", key="address", label="Address", text=True, height=3, width=22)])
        bb = tk.Frame(b, bg=C["card"])
        bb.pack(fill="x")
        Btn(bb, "Save", self.cust_save, "primary").pack(side="left")
        Btn(bb, "Use for current job", self.cust_use).pack(side="left", padx=px(6))
        Btn(bb, "Delete", self.cust_delete, "danger").pack(side="right")
        self.lbl_cust_status = autowrap(tk.Label(b, text="", bg=C["card"], fg=C["muted"], font=(FONT, 9), justify="left", anchor="w"))
        self.lbl_cust_status.pack(fill="x", pady=(px(10), 0))
        return page

    def cust_fields(self):
        return {"name": self.cvars["name"].get().strip(), "email": self.cvars["email"].get().strip(),
                "phone": self.cvars["phone"].get().strip(), "address": self.cvars["address"].get("1.0", "end").strip()}

    def cust_load(self, c):
        self.cvars["name"].set(c.get("name", ""))
        self.cvars["email"].set(c.get("email", ""))
        self.cvars["phone"].set(c.get("phone", ""))
        self.cvars["address"].delete("1.0", "end")
        self.cvars["address"].insert("1.0", c.get("address", ""))

    def refresh_customers(self):
        if not hasattr(self, "cust_tree"):
            return
        q = self.cust_search.get().strip().lower()
        counts = {}
        for j in self.store["jobs"]:
            k = (j.get("client") or "").strip().lower()
            counts[k] = counts.get(k, 0) + 1
        self.cust_tree.delete(*self.cust_tree.get_children())
        n = 0
        for c in sorted(self.store["customers"], key=lambda x: x.get("name", "").lower()):
            if q and q not in (c.get("name", "") + " " + c.get("email", "") + " " + c.get("phone", "")).lower():
                continue
            self.cust_tree.insert("", "end", iid=c["id"], values=(c.get("name", ""), c.get("email", ""), c.get("phone", ""), counts.get(c.get("name", "").strip().lower(), 0)))
            n += 1
        if n:
            self.cust_empty.place_forget()
        else:
            self.cust_empty.place(relx=0.5, rely=0.5, anchor="center")
        if self.cust_sel and self.cust_tree.exists(self.cust_sel):
            self.cust_tree.selection_set(self.cust_sel)

    def cust_select(self):
        sel = self.cust_tree.selection()
        if not sel:
            return
        self.cust_sel = sel[0]
        c = [x for x in self.store["customers"] if x["id"] == sel[0]]
        if c:
            self.cust_load(c[0])
            self.lbl_cust_status.config(text="")

    def cust_new(self):
        self.cust_sel = None
        self.cust_tree.selection_remove(self.cust_tree.selection())
        self.cust_load({})

    def cust_save(self):
        f = self.cust_fields()
        if not f["name"]:
            self.lbl_cust_status.config(text="Enter a name first.", fg=C["bad"])
            return
        if self.cust_sel:
            c = [x for x in self.store["customers"] if x["id"] == self.cust_sel][0]
            c.update(f)
        else:
            c = dict(f, id=uuid.uuid4().hex[:8])
            self.store["customers"].append(c)
            self.cust_sel = c["id"]
        save_store(self.store)
        self.refresh_customers()
        self.lbl_cust_status.config(text="Saved %s." % f["name"], fg=C["muted"])

    def cust_delete(self):
        if not self.cust_sel:
            return
        c = [x for x in self.store["customers"] if x["id"] == self.cust_sel]
        if c and messagebox.askyesno("Delete customer", "Delete %s from the customer list?\n\nTheir jobs are not deleted." % c[0].get("name", "")):
            self.store["customers"] = [x for x in self.store["customers"] if x["id"] != self.cust_sel]
            save_store(self.store)
            self.cust_new()
            self.refresh_customers()

    def cust_use(self):
        f = self.cust_fields()
        if not f["name"]:
            self.lbl_cust_status.config(text="Select or enter a customer first.", fg=C["bad"])
            return
        self.apply_customer(f)
        self.show("job")

    def apply_customer(self, c):
        self._busy = True
        self.vars[("J", "client")][0].set(c.get("name", ""))
        self.vars[("J", "custEmail")][0].set(c.get("email", ""))
        self.vars[("J", "custPhone")][0].set(c.get("phone", ""))
        t = self.vars[("J", "custAddress")][0]
        t.delete("1.0", "end")
        t.insert("1.0", c.get("address", ""))
        self._busy = False
        self.J["emailEdited"] = False
        self.on_change()

    def pick_customer_menu(self):
        menu = tk.Menu(self, tearoff=0)
        custs = sorted(self.store["customers"], key=lambda x: x.get("name", "").lower())
        if not custs:
            menu.add_command(label="No saved customers yet", state="disabled")
        for c in custs[:25]:
            menu.add_command(label=c.get("name", ""), command=lambda c=c: self.apply_customer(c))
        if len(custs) > 25:
            menu.add_separator()
            menu.add_command(label="More in Customers…", command=lambda: self.show("cust"))
        b = self.btn_pick_cust
        menu.tk_popup(b.winfo_rootx(), b.winfo_rooty() + b.winfo_height())

    def save_customer_from_job(self):
        J = self.J
        name = (J.get("client") or "").strip()
        if not name:
            self.say("Enter the customer name first.")
            messagebox.showinfo("Customer name needed", "Enter the customer name on this job first.")
            return
        data = {"name": name, "email": J.get("custEmail", ""), "phone": J.get("custPhone", ""), "address": J.get("custAddress", "")}
        for c in self.store["customers"]:
            if c.get("name", "").strip().lower() == name.lower():
                c.update(data)
                break
        else:
            self.store["customers"].append(dict(data, id=uuid.uuid4().hex[:8]))
        save_store(self.store)
        messagebox.showinfo("Customer saved", "%s is in your customer list." % name)

    # ================================================================ SETTINGS
    def _page_settings(self, parent):
        page = tk.Frame(parent, bg=C["bg"])
        self.head(page, "Business settings", "Your rates and business details", [lambda p: Btn(p, "Restore example settings", self.reset_settings)])
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
        self.frow(b, [dict(store="S", key="abn", label="ABN or tax number", width=12), dict(store="S", key="phone", label="Phone", width=12)])
        self.frow(b, [dict(store="S", key="bizEmail", label="Business email", width=20)])
        self.frow(b, [dict(store="S", key="address", label="Business address", text=True, height=2, width=20)])
        self.frow(b, [dict(store="S", key="currency", label="Currency code", hint="AUD, NZD, USD, CAD, GBP or EUR", width=8)], last=True)

        b = self.card(a, "Logo", "Shown at the top of quotes and invoices. PNG or JPG works best.")
        row = tk.Frame(b, bg=C["card"])
        row.pack(fill="x")
        self.logo_lbl = tk.Label(row, text="No logo yet", bg=C["neutral_bg"], fg=C["muted"], font=(FONT, 9), width=22, height=3)
        self.logo_lbl.pack(side="left")
        bb = tk.Frame(row, bg=C["card"])
        bb.pack(side="left", padx=px(14))
        Btn(bb, "Choose logo…", self.choose_logo).pack(anchor="w")
        Btn(bb, "Remove", self.remove_logo).pack(anchor="w", pady=(px(6), 0))

        b = self.card(a, "Labour cost")
        self.frow(b, [dict(store="S", key="labourRate", label="Hourly labour cost, per person", prefix="$", unit="per hour", width=8,
                           hint="What one person costs you per hour, including super, leave, insurance and payroll costs. Count your own time at what you would pay someone to do it.")], last=True)

        b = self.card(a, "Overhead allowance")
        self.ov_mode = tk.StringVar(value="percent")
        self.ov_mode.trace_add("write", lambda *_: self.on_change())
        Seg(b, self.ov_mode, [("percent", "% of direct costs"), ("hourly", "Per labour hour")]).pack(anchor="w", pady=(0, px(12)))
        self.row_ovp = self.frow(b, [dict(store="S", key="overheadPct", label="Overhead as a share of direct costs", unit="%", width=8,
                                          hint="A year of insurance, vehicle costs, software, phone, admin and accounting, divided by a year of direct job costs.")], last=True)
        self.row_ovh = self.frow(b, [dict(store="S", key="overheadHourly", label="Overhead per labour hour", prefix="$", unit="per hour", width=8,
                                          hint="A year of overhead divided by the labour hours you work in a year. Travel hours count.")], last=True)

        b = self.card(b2, "Profit & pricing")
        self.frow(b, [dict(store="S", key="margin", label="Target profit margin", unit="%", width=6),
                      dict(store="S", key="minPrice", label="Minimum job price", prefix="$", width=8)])
        self.frow(b, [dict(store="S", key="roundTo", label="Round quote up to", unit="$ step", hint="Use 0 for no rounding, or 1, 5, 10 or 50.", width=6)])
        self.lbl_margin = autowrap(tk.Label(b, text="", bg=C["neutral_bg"], fg=C["ink"], font=(FONT, 9), justify="left", anchor="w", padx=px(10), pady=px(8)), 24)
        self.lbl_margin.pack(fill="x")

        b = self.card(b2, "Travel")
        self.frow(b, [dict(store="S", key="travelRate", label="Vehicle cost per kilometre", prefix="$", unit="per km", width=8,
                           hint="Fuel, servicing, tyres and depreciation. Travel time is charged at your labour cost.")], last=True)

        b = self.card(b2, "Tax")
        self.tax_on = tk.BooleanVar()
        self.tax_on.trace_add("write", lambda *_: self.on_change())
        ttk.Checkbutton(b, text="Add tax to quotes and invoices", variable=self.tax_on, style="Card.TCheckbutton").pack(anchor="w", pady=(0, px(12)))
        self.frow(b, [dict(store="S", key="taxName", label="Tax name", width=8), dict(store="S", key="taxRate", label="Tax rate", unit="%", width=6)], last=True)

        b = self.card(b2, "Terms & numbering")
        self.frow(b, [dict(store="S", key="validDays", label="Quote valid for", unit="days", width=6),
                      dict(store="S", key="depositPct", label="Deposit to book", unit="%", width=6),
                      dict(store="S", key="payTerms", label="Invoice terms", unit="days", width=6)])
        self.frow(b, [dict(store="S", key="quotePrefix", label="Quote prefix", width=6), dict(store="S", key="nextQuote", label="Next quote number", width=7),
                      dict(store="S", key="invoicePrefix", label="Invoice prefix", width=6), dict(store="S", key="nextInvoice", label="Next invoice number", width=7)])
        self.frow(b, [dict(store="S", key="payDetails", label="Payment details, printed on invoices", text=True, height=3, width=20)])
        self.frow(b, [dict(store="S", key="docNote", label="Closing note", width=20)], last=True)

        b = self.card(b2, "Your data", "Everything is stored on this computer. Nothing is sent anywhere. A backup is kept for each day you use the app.", pad_bottom=0)
        autowrap(tk.Label(b, text=DATA_FILE, bg=C["neutral_bg"], fg=C["ink"], font=(MONO, 9), justify="left", anchor="w", padx=px(10), pady=px(8)), 24).pack(fill="x")
        bb = tk.Frame(b, bg=C["card"])
        bb.pack(fill="x", pady=(px(10), 0))
        Btn(bb, "Open data folder", self.open_data_folder).pack(side="left")
        Btn(bb, "Export backup…", self.export_backup).pack(side="left", padx=px(6))
        Btn(bb, "Import backup…", self.import_backup).pack(side="left")
        return page

    # ---------- logo
    def load_logo_preview(self):
        self._logo_img = None
        if os.path.exists(LOGO_PREVIEW):
            try:
                self._logo_img = tk.PhotoImage(file=LOGO_PREVIEW)
            except tk.TclError:
                self._logo_img = None
        if hasattr(self, "logo_lbl"):
            if self._logo_img:
                self.logo_lbl.config(image=self._logo_img, text="", width=self._logo_img.width() + 16, height=self._logo_img.height() + 12)
            else:
                self.logo_lbl.config(image="", text="No logo yet", width=22, height=3)

    def choose_logo(self):
        path = filedialog.askopenfilename(title="Choose your logo", filetypes=[("Images", "*.png *.jpg *.jpeg *.gif *.bmp"), ("All files", "*.*")])
        if not path:
            return
        try:
            from PIL import Image
        except ImportError:
            messagebox.showerror("Logo tool missing", "Install it once with:\n\n    pip install pillow\n\nthen restart the app.")
            return
        try:
            im = Image.open(path).convert("RGBA")
            os.makedirs(APP_DIR, exist_ok=True)
            big = im.copy()
            big.thumbnail((900, 360))
            big.save(LOGO_FILE)
            small = im.copy()
            small.thumbnail((px(190), px(48)))
            small.save(LOGO_PREVIEW)
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Could not use that image", str(exc))
            return
        self.load_logo_preview()
        self.refresh()

    def remove_logo(self):
        for p in (LOGO_FILE, LOGO_PREVIEW):
            try:
                os.remove(p)
            except OSError:
                pass
        self.load_logo_preview()
        self.refresh()

    # ---------- state <-> widgets
    def _set_var(self, store, key, value):
        was = self._busy
        self._busy = True
        w = self.vars[(store, key)][0]
        w.set(self._show(value))
        self._busy = was

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
        return "" if v is None else str(v)

    def fill_trees(self):
        for tree, key, cols in ((self.tree_mat, "materials", ("d", "q", "c")), (self.tree_oth, "other", ("d", "a"))):
            tree.delete(*tree.get_children())
            for row in self.J.get(key, []):
                tree.insert("", "end", values=[self._show(row.get(c, "")) for c in cols])
            tree.config(height=max(2, min(6, len(self.J.get(key, [])))))

    def collect(self):
        inv = set()
        for (store, key), (w, kind) in self.vars.items():
            target = self.S if store == "S" else self.J
            if kind == "text":
                target[key] = w.get("1.0", "end").rstrip("\n")
            else:
                raw = w.get()
                if key in NUMERIC_KEYS:
                    if not is_num(raw):
                        inv.add((store, key))
                    target[key] = num(raw)
                else:
                    target[key] = raw
                    if key == "issueDate" and not valid_date(raw):
                        inv.add((store, key))
                    if key in ("custEmail", "bizEmail") and raw.strip() and ("@" not in raw or " " in raw.strip()):
                        inv.add((store, key))
        self.invalid = inv
        self.J["docType"] = self.doc_type.get()
        self.J["itemised"] = self.itemised.get()
        self.S["overheadMode"] = self.ov_mode.get()
        self.S["taxOn"] = self.tax_on.get()

    def sync_job_state(self):
        J, S = self.J, self.S
        allowed = INVOICE_STATUSES if J["docType"] == "invoice" else QUOTE_STATUSES
        if J.get("status") not in allowed:
            J["status"] = "Draft"
            self._set_var("J", "status", "Draft")
        if J["docType"] == "invoice" and not str(J.get("invoiceNo", "")).strip():
            assign_invoice_no(S, J)
            self._set_var("J", "invoiceNo", J["invoiceNo"])
        if J["status"] == "Draft":
            J["snap"] = None
        elif not J.get("snap"):
            J["snap"] = take_snap(S)
        J["paidDate"] = (J.get("paidDate") or today().isoformat()) if J["status"] == "Paid" else ""

    def on_text(self, key):
        if key == "emailBody":
            self.J["emailEdited"] = True
        self.on_change()

    def on_change(self):
        if self._busy:
            return
        self.collect()
        self.J["updated"] = dt.datetime.now().isoformat(timespec="seconds")
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
        self.J[key].append(row)
        for e in ents.values():
            e.delete(0, "end")
        ents["d"].focus_set()
        self.fill_trees()
        self.J["updated"] = dt.datetime.now().isoformat(timespec="seconds")
        self.refresh()

    def remove_row(self, key, tree):
        sel = tree.selection()
        if not sel:
            return
        del self.J[key][tree.index(sel[0])]
        self.fill_trees()
        self.J["updated"] = dt.datetime.now().isoformat(timespec="seconds")
        self.refresh()

    # ---------- computed display
    def refresh(self, user_edit=False):
        if not self.vars:
            return
        if not user_edit:
            self.collect()
        self.sync_job_state()
        S, J = self.S, self.J
        r, eff = job_calc(S, J)
        self.r, self.eff = r, eff
        M = lambda v: money(eff, v)  # noqa: E731
        sym = SYMBOLS.get(eff.get("currency", "AUD"), "$")
        for lbl in self._cur_labels:
            try:
                lbl.config(text=sym)
            except tk.TclError:
                pass
        tn = eff.get("taxName") or "Tax"
        status = display_status(eff, J)
        self.lbl_side_biz.config(text=S.get("bizName") or "Your business")
        self.lbl_jobhead.config(text=J.get("title") or "New job")
        self.crumb_job.config(text="JOB COSTING   |   %s" % status.upper())
        self.crumb_doc.config(text="QUOTE & INVOICE   |   %s" % status.upper())
        self.banner.pack_forget()
        self.lockbar.pack_forget()
        if J.get("sample"):
            self.banner.pack(fill="x", pady=(0, px(14)), before=self.job_body)
        if J.get("snap") and any(J["snap"].get(k) != S.get(k) for k in PRICING_KEYS):
            self.lockbar.pack(fill="x", pady=(0, px(14)), before=self.job_body)
        self.lbl_priceLab.config(text="RECOMMENDED QUOTE" + (" (EXCL. %s)" % tn.upper() if eff.get("taxOn") else ""))
        self.lbl_price.config(text=M(r["price"]))
        self.lbl_taxline.config(text=("%s %s   |   Total %s" % (tn, M(r["tax"]), M(r["total"]))) if eff.get("taxOn") else "Total " + M(r["total"]))
        flag = ""
        if r["min_applied"]:
            flag = "Your minimum job price of %s applies. The costed price was %s." % (M(pos(eff.get("minPrice"))), M(r["raw"]))
        elif r["rounded"]:
            flag = "Rounded up from %s to the next %s." % (M(r["raw"]), M(pos(eff.get("roundTo"))).replace(".00", ""))
        self.lbl_flag.config(text=flag)
        self.stat["cost"].config(text=M(r["cost"]))
        self.stat["profit"].config(text=M(r["profit"]))
        self.stat["margin"].config(text=("%.1f%%" % (r["margin"] * 100)) if r["price"] > 0 else "0%")
        self.stat["pph"].config(text=M(r["pph"]))
        self.chip_labour.config(text=M(r["labour"]))
        self.chip_travel.config(text=M(r["travel"]))
        self.chip_mat.config(text=M(r["materials"]))
        self.chip_oth.config(text=M(r["other"]))
        self.lbl_labour.config(text=("%.2f hours on site at %s per hour" % (r["on_site"], M(pos(eff.get("labourRate"))))) if r["on_site"] else "Enter the people and hours on site.")
        self.lbl_travel.config(text="Vehicle %s plus travel time %s. Travel time is paid to every person." % (M(r["vehicle"]), M(r["travel_time"])))
        vals = {"labour": r["labour"], "travel": r["travel"], "materials": r["materials"], "other": r["other"], "direct": r["direct"],
                "overhead": r["overhead"], "cost": r["cost"], "profit": r["profit"], "price": r["price"]}
        for k, (a, p) in self.brk.items():
            a.config(text=M(vals[k]))
            p.config(text=("%.1f%%" % (vals[k] / r["price"] * 100)) if r["price"] > 0 else "")
        self.draw_bar()
        self.verdict(r)
        mm = min(max(num(S.get("margin")), 0), 90) / 100
        self.lbl_margin.config(text="At a %.1f%% margin, a job that costs %s is quoted at %s. That is a %.1f%% markup on cost." %
                               (mm * 100, money(S, 100), money(S, 100 / (1 - mm)), mm / (1 - mm) * 100))
        hourly = S.get("overheadMode") == "hourly"
        (self.row_ovp.pack_forget() if hourly else self.row_ovp.pack(fill="x"))
        (self.row_ovh.pack(fill="x") if hourly else self.row_ovh.pack_forget())

        m = build_model(eff, J, r)
        self.model = m
        inv = m["inv"]
        self.lbl_dochead.config(text="%s %s" % (m["title"], m["number"]))
        self.cmb_status.config(values=INVOICE_STATUSES if inv else QUOTE_STATUSES)
        hint = {"Draft": "Not sent yet. Pricing follows your current settings.", "Sent": "Pricing is locked at today's rates.",
                "Accepted": "Ready to convert to an invoice.", "Declined": "The customer declined this quote.",
                "Paid": "Paid in full."}.get(J.get("status"), "")
        if status == "Overdue":
            hint = "Overdue. Payment was due on %s." % fmt_date(due_date(eff, J))
        self.lbl_status_hint.config(text=hint, fg=C["bad"] if status == "Overdue" else C["muted"])
        for b in (self.btn_convert, self.btn_paid):
            b.pack_forget()
        self.row_actions.pack_forget()
        if not inv:
            self.btn_convert.pack(side="left")
        elif J.get("status") != "Paid":
            self.btn_paid.pack(side="left")
        if not inv or J.get("status") != "Paid":
            self.row_actions.pack(fill="x", pady=(0, px(12)), before=self.row_no)
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
            subj, body = email_template(eff, J, m)
            self._busy = True
            self.vars[("J", "emailSubject")][0].set(subj)
            tb = self.vars[("J", "emailBody")][0]
            tb.delete("1.0", "end")
            tb.insert("1.0", body)
            J["emailSubject"], J["emailBody"] = subj, body
            self._busy = False
        self.paint_boxes()
        self.store["current"] = J["id"]
        ok = save_store(self.store)
        msg = ("All changes saved  %s" % dt.datetime.now().strftime("%H:%M:%S")) if ok else "Could not save to the data file"
        if self.invalid:
            msg += "   |   Check the red fields"
        self.lbl_saved.config(text=msg, fg=C["bad"] if (self.invalid or not ok) else C["muted"])
        if self.current == "jobs":
            self.refresh_jobs()

    def _doc_resized(self, e):
        if abs(e.width - self._doc_w) > 6 and self.model:
            self._doc_w = e.width
            self.after(60, lambda: self.render_preview(self.model))

    def render_preview(self, m):
        cv = self.preview
        cv.delete("all")
        cw = max(self.doc_left.canvas.winfo_width(), px(420))
        try:
            from reportlab.lib.pagesizes import A4
        except ImportError:
            cv.config(height=px(300))
            cv.create_text(cw / 2, px(120), text="Install the PDF tool to see the page preview:\npip install reportlab",
                           font=(FONT, 11), fill=C["muted"], justify="center")
            return
        W, H = A4
        margin, gap = px(20), px(20)
        page_w = max(px(360), min(cw - 2 * margin, px(820)))
        scale = page_w / W
        page = TkPage(cv, W, H, scale, (cw - page_w) / 2, margin, gap)
        draw_document(page, m)
        cv.config(width=cw, height=int(page.bottom + margin - gap))

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
        M = lambda v: money(self.eff, v)  # noqa: E731
        tone = "neutral"
        if r["cost"] <= 0:
            head, body = "Add the job costs first", "Once the job has labour, travel or materials, this compares your usual price with what the job needs."
        elif gut <= 0:
            head, body = "Enter your usual price", "Type what you would have quoted by gut feel to see what it earns you on this job."
        elif gut < r["direct"]:
            tone, head = "bad", "You would lose money on this job"
            body = "%s does not cover the %s it costs you to do the work. You would be %s out of pocket before any overhead." % (M(gut), M(r["direct"]), M(r["direct"] - gut))
        elif gut < r["cost"]:
            tone, head = "bad", "Overhead is not covered"
            body = "%s pays for the work but leaves %s of overhead unpaid. The job earns no profit." % (M(gut), M(r["cost"] - gut))
        elif gut < r["price"] - 0.004:
            gp = gut - r["cost"]
            tone, head = "warn", "Below your target margin"
            body = "%s leaves %s profit, a %.1f%% margin against your %.1f%% target. It is %s short of the recommended quote." % (M(gut), M(gp), gp / gut * 100, r["target"] * 100, M(r["price"] - gut))
        else:
            gp = gut - r["cost"]
            tone, head = "good", "At or above your target"
            body = "%s leaves %s profit, a %.1f%% margin." % (M(gut), M(gp), gp / gut * 100)
        bg = {"neutral": C["neutral_bg"], "bad": C["bad_bg"], "warn": C["warn_bg"], "good": C["good_bg"]}[tone]
        fg = {"neutral": C["ink"], "bad": C["bad"], "warn": C["warn"], "good": C["good"]}[tone]
        self.verd.config(bg=bg)
        self.lbl_vhead.config(text=head, bg=bg, fg=fg)
        self.lbl_vbody.config(text=body, bg=bg)

    # ---------- actions
    def reset_settings(self):
        if messagebox.askyesno("Restore example settings", "Replace all business settings with the example values?\n\nYour jobs and customers are not affected."):
            keep = {k: self.S[k] for k in ("nextQuote", "nextInvoice")}
            self.S.clear()
            self.S.update(default_settings())
            self.S.update(keep)
            self.fill_all()
            self.refresh()

    def say(self, text):
        self.lbl_doc_status.config(text=text)

    def save_pdf(self):
        try:
            import reportlab  # noqa: F401
        except ImportError:
            messagebox.showerror("PDF tool missing", "Install it once with:\n\n    pip install reportlab\n\nthen restart the app.")
            return
        self.refresh()
        m = self.model
        default = "%s-%s.pdf" % (m["title"].replace(" ", "-"), "".join(ch if ch.isalnum() or ch in "-_." else "-" for ch in m["number"]))
        path = filedialog.asksaveasfilename(title="Save PDF", defaultextension=".pdf", initialfile=default, filetypes=[("PDF", "*.pdf")])
        if not path:
            return
        try:
            make_pdf(m, path)
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Could not save PDF", str(exc))
            return
        self.show("doc")
        self.say("Saved %s. Attach it to your email, then set the status to Sent." % path)
        self.open_path(os.path.dirname(path), select=path)

    def open_path(self, folder, select=None):
        try:
            if sys.platform.startswith("win"):
                if select:
                    os.system('explorer /select,"%s"' % os.path.normpath(select))
                else:
                    os.startfile(folder)  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                os.system('open -R "%s"' % select if select else 'open "%s"' % folder)
            else:
                webbrowser.open("file://" + folder)
        except Exception:  # noqa: BLE001
            pass

    def open_data_folder(self):
        os.makedirs(APP_DIR, exist_ok=True)
        save_store(self.store)
        self.open_path(APP_DIR)

    def where_data(self):
        messagebox.showinfo("Where is my data stored?", "Your jobs, customers, templates and settings are saved automatically in this file on your computer:\n\n%s\n\nA backup copy is kept for each day you use the app in the backups folder next to it.\n\nNothing is sent over the internet. Use File > Export backup to keep a copy somewhere safe." % DATA_FILE)

    def export_backup(self):
        self.refresh()
        path = filedialog.asksaveasfilename(title="Export backup", defaultextension=".json", initialfile="job-costing-backup-%s.json" % today().strftime("%Y%m%d"), filetypes=[("Backup file", "*.json")])
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(self.store, f, indent=1)
            messagebox.showinfo("Backup saved", "Backup saved to:\n%s" % path)
        except OSError as exc:
            messagebox.showerror("Could not save backup", str(exc))

    def import_backup(self):
        path = filedialog.askopenfilename(title="Import backup", filetypes=[("Backup file", "*.json")])
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                d = json.load(f)
            if not isinstance(d, dict) or "S" not in d or ("jobs" not in d and "J" not in d):
                raise ValueError("This is not a Job Costing backup file.")
        except (OSError, ValueError) as exc:
            messagebox.showerror("Could not import backup", str(exc))
            return
        if not messagebox.askyesno("Import backup", "Replace all your current jobs, customers and settings with this backup?"):
            return
        daily_backup()
        try:
            shutil.copy2(path, DATA_FILE)
        except OSError as exc:
            messagebox.showerror("Could not import backup", str(exc))
            return
        self.store = load_store()
        self.S = self.store["S"]
        self.J = self.job_by_id(self.store["current"])
        self.fill_all()
        self.refresh()
        self.show("jobs")

    def clip(self, text, ok):
        self.clipboard_clear()
        self.clipboard_append(text)
        self.say(ok)

    def copy_doc(self):
        self.clip(model_text(self.model), "Document text copied.")

    def copy_msg(self):
        self.clip("Subject: %s\n\n%s" % (self.J.get("emailSubject", ""), self.J.get("emailBody", "")), "Message copied.")

    def reset_msg(self):
        self.J["emailEdited"] = False
        self.refresh()
        self.say("Message reset.")

    def open_email(self):
        url = "mailto:%s?subject=%s&body=%s" % (quote(self.J.get("custEmail", "")), quote(self.J.get("emailSubject", "")), quote(self.J.get("emailBody", "")))
        webbrowser.open(url)
        self.say("Opened your email app. Attach the saved PDF before sending.")


if __name__ == "__main__":
    App().mainloop()
