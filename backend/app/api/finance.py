"""Admin: expenses, profit & loss report, Excel and PDF export."""
import io
from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import CurrentStaff, require
from app.db import get_db
from app.models import Expense, User
from app.models.enums import Currency, ExpenseCategory
from app.services import app_settings
from app.services.audit import audit
from app.services.finance import GROUPS, report
from app.services.reports import PRESETS, resolve_period

router = APIRouter(prefix="/api/admin/finance", tags=["finance"])


class ExpenseIn(BaseModel):
    category: ExpenseCategory
    spent_on: date
    description: str = Field(min_length=1, max_length=255)
    currency: Currency = Currency.USD
    amount_minor: int = Field(gt=0, le=1_000_000_000)  # cents for USD, riel for KHR
    notes: str = Field("", max_length=1000)


def _usd(db: Session, currency: Currency, amount_minor: int) -> tuple[Decimal, int]:
    """Convert at today's rate and remember that rate (old expenses never change)."""
    rate = app_settings.khr_per_usd(db)
    usd = amount_minor if currency == Currency.USD else int((Decimal(amount_minor) / rate * 100).to_integral_value())
    return rate, usd


def expense_out(e: Expense, names: dict[int, str]) -> dict:
    return {"id": e.id, "category": e.category, "spent_on": e.spent_on, "description": e.description,
            "currency": e.currency, "amount_minor": e.amount_minor, "amount_usd_cents": e.amount_usd_cents,
            "khr_per_usd": str(e.khr_per_usd), "notes": e.notes, "created_by": names.get(e.created_by_user_id)}


def _period(db: Session, period: str, start: date | None, end: date | None) -> tuple[date, date]:
    try:
        return resolve_period(db, period, start, end)
    except ValueError as err:
        raise HTTPException(422, str(err))


PERIOD = Query("month", pattern="^(" + "|".join(PRESETS) + ")$")
GROUP = Query(None, pattern="^(" + "|".join(GROUPS) + ")$")


@router.get("/expenses")
def list_expenses(period: str = PERIOD, start: date | None = None, end: date | None = None,
                  db: Session = Depends(get_db), _: CurrentStaff = Depends(require("finance.view"))):
    s, e = _period(db, period, start, end)
    names = {u.id: u.full_name for u in db.scalars(select(User))}
    rows = db.scalars(select(Expense).where(Expense.spent_on >= s, Expense.spent_on <= e)
                      .order_by(Expense.spent_on.desc(), Expense.id.desc())).all()
    return [expense_out(x, names) for x in rows]


@router.post("/expenses", status_code=201)
def add_expense(body: ExpenseIn, request: Request, db: Session = Depends(get_db),
                staff: CurrentStaff = Depends(require("finance.edit"))):
    rate, usd = _usd(db, body.currency, body.amount_minor)
    e = Expense(**body.model_dump(), khr_per_usd=rate, amount_usd_cents=usd, created_by_user_id=staff.id)
    db.add(e)
    db.flush()
    audit(db, "finance.expense_added", "expense", e.id, staff.id,
          {"category": body.category, "amount_minor": body.amount_minor, "currency": body.currency}, request)
    db.commit()
    return expense_out(e, {staff.id: staff.user.full_name})


@router.put("/expenses/{expense_id}")
def edit_expense(expense_id: int, body: ExpenseIn, request: Request, db: Session = Depends(get_db),
                 staff: CurrentStaff = Depends(require("finance.edit"))):
    e = db.get(Expense, expense_id)
    if not e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Expense not found.")
    before = expense_out(e, {})
    for k, v in body.model_dump().items():
        setattr(e, k, v)
    if body.currency == Currency.USD:
        e.amount_usd_cents = body.amount_minor
    else:  # keep the rate saved with this expense
        e.amount_usd_cents = int((Decimal(body.amount_minor) / e.khr_per_usd * 100).to_integral_value())
    audit(db, "finance.expense_edited", "expense", e.id, staff.id,
          {"before": {k: str(v) for k, v in before.items()}}, request)
    db.commit()
    return expense_out(e, {})


@router.delete("/expenses/{expense_id}", status_code=204)
def delete_expense(expense_id: int, request: Request, db: Session = Depends(get_db),
                   staff: CurrentStaff = Depends(require("finance.edit"))):
    e = db.get(Expense, expense_id)
    if not e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Expense not found.")
    audit(db, "finance.expense_deleted", "expense", e.id, staff.id, {k: str(v) for k, v in expense_out(e, {}).items()}, request)
    db.delete(e)
    db.commit()


@router.get("/report")
def get_report(period: str = PERIOD, start: date | None = None, end: date | None = None, group: str | None = GROUP,
               db: Session = Depends(get_db), _: CurrentStaff = Depends(require("finance.view"))):
    s, e = _period(db, period, start, end)
    return report(db, s, e, group)


# ---------------------------------------------------------------- exports
def _money(cents: int) -> float:
    return round(cents / 100, 2)


LINES = [
    ("Gross sales", "gross_sales_usd_cents", 1), ("Discounts", "discounts_usd_cents", -1),
    ("Net sales", "net_sales_usd_cents", 1), ("Refunds", "refunds_usd_cents", -1),
    ("Cost of ingredients used (COGS)", "cogs_usd_cents", -1), ("Waste", "waste_usd_cents", -1),
    ("Gross profit", "gross_profit_usd_cents", 1), ("Expenses", "expenses_usd_cents", -1),
    ("Net profit (estimate)", "net_profit_usd_cents", 1),
]


@router.get("/report.xlsx")
def export_excel(period: str = PERIOD, start: date | None = None, end: date | None = None, group: str | None = GROUP,
                 db: Session = Depends(get_db), _: CurrentStaff = Depends(require("finance.view"))):
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill

    s, e = _period(db, period, start, end)
    r = report(db, s, e, group)
    wb = Workbook()
    ws = wb.active
    ws.title = "Profit and loss"
    bold = Font(bold=True)
    head = PatternFill("solid", fgColor="263D31")
    ws.append(["LAGOM — Profit and loss (USD)"])
    ws["A1"].font = Font(bold=True, size=14)
    ws.append([f"{s.isoformat()} to {e.isoformat()}", f"{r['orders']} paid orders"])
    ws.append([])
    for label, key, sign in LINES:
        ws.append([label, _money(r[key]) * (1 if sign > 0 or not r[key] else -1)])
        if label in ("Net sales", "Gross profit", "Net profit (estimate)"):
            ws.cell(ws.max_row, 1).font = bold
            ws.cell(ws.max_row, 2).font = bold
    ws.append([])
    ws.append(["Expenses by category"])
    ws.cell(ws.max_row, 1).font = bold
    for cat, cents in r["expenses_by_category"].items():
        ws.append([cat.title(), _money(cents)])
    ws.append([])
    ws.append(["Sales by payment method"])
    ws.cell(ws.max_row, 1).font = bold
    for k, v in r["sales_by_method"].items():
        ws.append(["ABA KHQR" if k == "khqr" else "Cash" if k == "cash" else k, _money(v)])
    ws.append(["Ingredient purchases (stock bought, for information)", _money(r["purchases_usd_cents"])])
    ws.column_dimensions["A"].width = 52
    ws.column_dimensions["B"].width = 16
    for row in ws.iter_rows(min_row=4, min_col=2, max_col=2):
        for c in row:
            c.number_format = '"$"#,##0.00'

    ws2 = wb.create_sheet(f"By {r['period']['group']}")
    cols = ["Period", "Orders", "Net sales", "Refunds", "COGS", "Waste", "Gross profit", "Expenses", "Net profit"]
    ws2.append(cols)
    for i, _c in enumerate(cols, start=1):
        ws2.cell(1, i).font = Font(bold=True, color="F3EBDD")
        ws2.cell(1, i).fill = head
    for p in r["periods"]:
        ws2.append([p["label"], p["orders"], *[_money(p[k]) for k in ("net_sales", "refunds", "cogs", "waste",
                                                                       "gross_profit", "expenses", "net_profit")]])
    for row in ws2.iter_rows(min_row=2, min_col=3, max_col=9):
        for c in row:
            c.number_format = '"$"#,##0.00'
    ws2.column_dimensions["A"].width = 22

    ws3 = wb.create_sheet("Expenses")
    # Text typed by staff must never run as an Excel formula (e.g. "=HYPERLINK(...)")
    ws3.append(["Date", "Category", "Description", "Currency", "Amount", "USD", "Rate"])
    for x in db.scalars(select(Expense).where(Expense.spent_on >= s, Expense.spent_on <= e).order_by(Expense.spent_on)):
        amount = x.amount_minor / 100 if x.currency == Currency.USD else x.amount_minor
        ws3.append([x.spent_on, x.category.value.title(), x.description, x.currency.value, amount,
                    _money(x.amount_usd_cents), float(x.khr_per_usd)])
        ws3.cell(ws3.max_row, 3).data_type = "s"  # always plain text, never a formula
    ws3.column_dimensions["C"].width = 40

    buf = io.BytesIO()
    wb.save(buf)
    return Response(buf.getvalue(), media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": f'attachment; filename="lagom-finance-{s}-{e}.xlsx"'})


@router.get("/report.pdf")
def export_pdf(period: str = PERIOD, start: date | None = None, end: date | None = None, group: str | None = GROUP,
               db: Session = Depends(get_db), _: CurrentStaff = Depends(require("finance.view"))):
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    s, e = _period(db, period, start, end)
    r = report(db, s, e, group)
    forest, cream = colors.HexColor("#263D31"), colors.HexColor("#F3EBDD")
    styles = getSampleStyleSheet()
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm, topMargin=18 * mm,
                            bottomMargin=18 * mm, title="LAGOM profit and loss")
    fmt = lambda c: f"${c / 100:,.2f}" if c >= 0 else f"-${-c / 100:,.2f}"  # noqa: E731
    story = [Paragraph("<font color='#263D31' size='20'><b>L A G O M</b></font>", styles["Title"]),
             Paragraph(f"Profit and loss · {s.isoformat()} to {e.isoformat()} · {r['orders']} paid orders", styles["Normal"]),
             Spacer(1, 8 * mm)]
    data = [[label, fmt(-r[key] if sign < 0 and r[key] else r[key])] for label, key, sign in LINES]
    t = Table(data, colWidths=[110 * mm, 50 * mm])
    t.setStyle(TableStyle([("ALIGN", (1, 0), (1, -1), "RIGHT"), ("LINEBELOW", (0, 0), (-1, -1), 0.25, colors.lightgrey),
                           *[("FONTNAME", (0, i), (-1, i), "Helvetica-Bold") for i in (2, 6, 8)],
                           ("BACKGROUND", (0, 8), (-1, 8), cream)]))
    story += [t, Spacer(1, 8 * mm), Paragraph("<b>By period</b>", styles["Heading3"])]
    rows = [["Period", "Orders", "Net sales", "COGS", "Expenses", "Net profit"]]
    rows += [[p["label"], str(p["orders"]), fmt(p["net_sales"]), fmt(p["cogs"]), fmt(p["expenses"]), fmt(p["net_profit"])]
             for p in r["periods"]]
    t2 = Table(rows, repeatRows=1, colWidths=[44 * mm, 18 * mm, 26 * mm, 24 * mm, 26 * mm, 26 * mm])
    t2.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), forest), ("TEXTCOLOR", (0, 0), (-1, 0), cream),
                            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"), ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
                            ("FONTSIZE", (0, 0), (-1, -1), 9), ("LINEBELOW", (0, 1), (-1, -1), 0.25, colors.lightgrey)]))
    story += [t2, Spacer(1, 6 * mm),
              Paragraph("Net profit is an estimate: sales minus refunds, ingredients used, waste and recorded expenses.",
                        styles["Italic"])]
    doc.build(story)
    return Response(buf.getvalue(), media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="lagom-finance-{s}-{e}.pdf"'})
