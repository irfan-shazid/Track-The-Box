import calendar
import csv
from datetime import date
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import DecimalField, Q, Sum, Value
from django.db.models.functions import Coalesce, TruncMonth
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from .forms import BudgetForm, ExpenseForm, QuickExpenseForm
from .models import Budget, Category, Expense

ZERO = Decimal("0.00")
MONEY = DecimalField(max_digits=12, decimal_places=2)


# ---------------------------------------------------------------------------
# Month helpers
# ---------------------------------------------------------------------------


def month_start(d):
    return d.replace(day=1)


def add_months(d, n):
    """Shift a first-of-month date by n months. Always lands on day 1."""
    total = (d.year * 12 + d.month - 1) + n
    return date(total // 12, total % 12 + 1, 1)


def parse_month(value):
    """'2026-09' -> date(2026, 9, 1). Anything unparseable falls back to this month."""
    today = timezone.localdate()
    if value:
        try:
            year, month = value.split("-")
            return date(int(year), int(month), 1)
        except (ValueError, TypeError):
            pass
    return month_start(today)


def month_range(start):
    """Half-open [start, next_month) -- the right way to filter a month on a DateField."""
    return start, add_months(start, 1)


def q2(value):
    """Pin a Decimal to 2dp. SUM() widens the scale, and 2085.74000000000 in a
    chart tooltip or a CSV cell is just noise."""
    return (value or ZERO).quantize(Decimal("0.01"))


def sum_amount(queryset):
    """One SUM in the database, never None."""
    return q2(
        queryset.aggregate(
            total=Coalesce(Sum("amount", output_field=MONEY), Value(ZERO), output_field=MONEY)
        )["total"]
    )


def months_with_data():
    """Distinct months that actually have expenses, newest first -- powers the month picker."""
    rows = (
        Expense.objects.annotate(month=TruncMonth("date"))
        .values("month")
        .annotate(total=Coalesce(Sum("amount", output_field=MONEY), Value(ZERO), output_field=MONEY))
        .order_by("-month")
    )
    return [{"date": r["month"], "key": r["month"].strftime("%Y-%m"), "total": q2(r["total"])} for r in rows]



def budget_status(month, spent):
    """Everything the UI needs about a month's spending target.

    Returns None when no target is set for that month — the templates treat
    that as "offer to set one" rather than as a zero target.
    """
    budget = Budget.objects.filter(month=month).first()
    if budget is None:
        return None

    target = budget.amount
    remaining = q2(target - spent)
    over = remaining < ZERO

    used_pct = (spent / target * Decimal("100")).quantize(Decimal("0.1")) if target else Decimal("0.0")

    today = timezone.localdate()
    days_in_month = calendar.monthrange(month.year, month.month)[1]
    is_current = month_start(today) == month
    # Days you can still spend on, today included — on the 30th of a 31-day
    # month there are two days left to budget for, not one.
    days_left = days_in_month - today.day + 1 if is_current else 0

    # What's left, spread over the days that remain.
    allowance = q2(remaining / days_left) if not over and days_left > 0 else None

    if over:
        state = "over"
    elif used_pct >= Decimal("85"):
        state = "warn"
    else:
        state = "ok"

    return {
        "target": target,
        "spent": spent,
        # Always positive; `over` says which label to use.
        "remaining": abs(remaining),
        "over": over,
        "used_pct": used_pct,
        # The meter bar is capped so a 300% overspend doesn't overflow its track.
        "meter_pct": min(used_pct, Decimal("100")),
        "state": state,
        "allowance": allowance,
        "days_left": days_left,
        "is_current": is_current,
    }


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------


@login_required
def dashboard(request):
    current = parse_month(request.GET.get("month"))
    previous = add_months(current, -1)

    cur_start, cur_end = month_range(current)
    prev_start, prev_end = month_range(previous)

    current_total = sum_amount(Expense.objects.filter(date__gte=cur_start, date__lt=cur_end))
    previous_total = sum_amount(Expense.objects.filter(date__gte=prev_start, date__lt=prev_end))

    delta = current_total - previous_total
    if previous_total:
        delta_pct = (delta / previous_total * Decimal("100")).quantize(Decimal("0.1"))
    else:
        delta_pct = None  # no baseline -- "no data last month", not "+100%"

    # Per-category breakdown, grouped and summed by Postgres.
    breakdown_rows = (
        Expense.objects.filter(date__gte=cur_start, date__lt=cur_end)
        .values("category__name", "category__color")
        .annotate(total=Coalesce(Sum("amount", output_field=MONEY), Value(ZERO), output_field=MONEY))
        .order_by("-total")
    )
    breakdown = [
        {
            "name": row["category__name"],
            "color": row["category__color"],
            "total": q2(row["total"]),
            "pct": (row["total"] / current_total * Decimal("100")).quantize(Decimal("0.1"))
            if current_total
            else Decimal("0.0"),
        }
        for row in breakdown_rows
    ]

    # Last 6 months including the selected one. One grouped query, then filled
    # out in order so a month with zero spend still shows as an empty bar.
    window_start = add_months(current, -5)
    totals_by_month = {
        row["month"]: q2(row["total"])
        for row in Expense.objects.filter(date__gte=window_start, date__lt=cur_end)
        .annotate(month=TruncMonth("date"))
        .values("month")
        .annotate(total=Coalesce(Sum("amount", output_field=MONEY), Value(ZERO), output_field=MONEY))
    }
    chart_labels, chart_values = [], []
    for i in range(6):
        m = add_months(window_start, i)
        chart_labels.append(m.strftime("%b %Y"))
        # Decimal -> str keeps full precision through JSON; Chart.js parses it.
        chart_values.append(str(totals_by_month.get(m, ZERO)))

    top = breakdown[0] if breakdown else None
    month_expenses = Expense.objects.filter(date__gte=cur_start, date__lt=cur_end)
    expense_count = month_expenses.count()

    today = timezone.localdate()
    days_in_month = calendar.monthrange(current.year, current.month)[1]
    is_current_month = month_start(today) == current
    days_elapsed = today.day if is_current_month else days_in_month
    days_left = days_in_month - days_elapsed if is_current_month else 0

    largest = month_expenses.select_related("category").order_by("-amount").first()
    recent = month_expenses.select_related("category")[:5]

    budget = budget_status(current, current_total)

    # All-time records, not scoped to the month being viewed -- "highest" and
    # "lowest" only mean something across the whole history. Reused for the
    # month picker below, so this is one query, not two.
    all_months = months_with_data()
    highest_month = lowest_month = None
    if len(all_months) >= 2:
        highest_month = max(all_months, key=lambda m: m["total"])
        lowest_month = min(all_months, key=lambda m: m["total"])
        # Every month tied at the same total (e.g. exactly two months, equal
        # spend) would make "highest" and "lowest" the same month, which reads
        # as a bug rather than a coincidence -- so just don't claim a record.
        if highest_month["key"] == lowest_month["key"]:
            highest_month = lowest_month = None

    return render(
        request,
        "expenses/dashboard.html",
        {
            "month": current,
            "month_key": current.strftime("%Y-%m"),
            "prev_month": previous,
            "prev_month_key": previous.strftime("%Y-%m"),
            "next_month_key": add_months(current, 1).strftime("%Y-%m"),
            "is_current_month": is_current_month,
            "current_total": current_total,
            "previous_total": previous_total,
            "delta": delta,
            "delta_abs": abs(delta),
            "delta_pct": delta_pct,
            "delta_pct_abs": abs(delta_pct) if delta_pct is not None else None,
            "breakdown": breakdown,
            "top_category": top,
            "expense_count": expense_count,
            "days_left": days_left,
            "largest": largest,
            "recent": recent,
            "budget": budget,
            "highest_month": highest_month,
            "lowest_month": lowest_month,
            "chart_labels": chart_labels,
            "chart_values": chart_values,
            "available_months": all_months,
        },
    )


# ---------------------------------------------------------------------------
# Expense list
# ---------------------------------------------------------------------------

SORT_FIELDS = {
    "date": ["date", "created_at"],
    "amount": ["amount"],
    "name": ["name"],
    "category": ["category__name"],
}

SORT_LABELS = [("date", "Date"), ("amount", "Amount"), ("name", "Name"), ("category", "Category")]


@login_required
def expense_list(request):
    current = parse_month(request.GET.get("month"))
    start, end = month_range(current)

    queryset = Expense.objects.select_related("category").filter(date__gte=start, date__lt=end)

    search = request.GET.get("q", "").strip()
    if search:
        queryset = queryset.filter(Q(name__icontains=search) | Q(note__icontains=search))

    category_id = request.GET.get("category", "").strip()
    if category_id.isdigit():
        queryset = queryset.filter(category_id=int(category_id))
    else:
        category_id = ""

    sort = request.GET.get("sort", "date")
    if sort not in SORT_FIELDS:
        sort = "date"
    direction = "asc" if request.GET.get("dir") == "asc" else "desc"
    prefix = "" if direction == "asc" else "-"
    queryset = queryset.order_by(*[prefix + field for field in SORT_FIELDS[sort]])

    opposite = "asc" if direction == "desc" else "desc"
    # Clicking the active sort flips it; clicking a different one starts at
    # descending, which is what you want for both dates and amounts.
    sort_options = [
        {"key": key, "label": label, "dir": opposite if key == sort else "desc"}
        for key, label in SORT_LABELS
    ]

    total = sum_amount(queryset)

    # Day subtotals, grouped by Postgres. Only used when the list is in date
    # order — grouping an amount-sorted list by day would produce nonsense.
    group_by_day = sort == "date"
    day_groups = []
    if group_by_day:
        subtotals = {
            row["date"]: q2(row["total"])
            # .order_by() must be cleared first: an explicit ordering is folded
            # into the GROUP BY, and "-created_at" is unique per row, so every
            # expense would come back as its own one-row "day".
            for row in queryset.order_by()
            .values("date")
            .annotate(total=Coalesce(Sum("amount", output_field=MONEY), Value(ZERO), output_field=MONEY))
        }
        # One pass over rows we are rendering anyway, stitching each day's
        # already-computed subtotal onto its group header.
        for expense in queryset:
            if not day_groups or day_groups[-1]["date"] != expense.date:
                day_groups.append(
                    {"date": expense.date, "total": subtotals.get(expense.date, ZERO), "items": []}
                )
            day_groups[-1]["items"].append(expense)

    return render(
        request,
        "expenses/expense_list.html",
        {
            "expenses": queryset,
            "day_groups": day_groups,
            "group_by_day": group_by_day,
            "total": total,
            "count": queryset.count(),
            "month": current,
            "month_key": current.strftime("%Y-%m"),
            "prev_month_key": add_months(current, -1).strftime("%Y-%m"),
            "next_month_key": add_months(current, 1).strftime("%Y-%m"),
            "categories": Category.objects.all(),
            "search": search,
            "selected_category": category_id,
            "sort": sort,
            "direction": direction,
            "opposite_dir": opposite,
            "sort_options": sort_options,
            "quick_form": QuickExpenseForm(initial={"date": timezone.localdate()}),
            # Unfiltered month total, so the target line means the same thing
            # here as on the dashboard even while a filter is applied.
            "budget": budget_status(current, sum_amount(Expense.objects.filter(date__gte=start, date__lt=end))),
            "available_months": months_with_data(),
            "is_filtered": bool(search or category_id),
        },
    )


# ---------------------------------------------------------------------------
# Create / edit / delete
# ---------------------------------------------------------------------------


@login_required
def expense_create(request):
    if request.method == "POST":
        # The quick-add form on the list page posts here too, minus the note field.
        quick = request.POST.get("quick") == "1"
        form_class = QuickExpenseForm if quick else ExpenseForm
        form = form_class(request.POST)
        if form.is_valid():
            expense = form.save()
            messages.success(request, 'Added "%s".' % expense.name)
            return redirect(expense.get_absolute_url())
        if quick:
            # A failed quick-add shouldn't strand the user on a bare form page.
            messages.error(request, "Could not save that expense -- check the highlighted fields.")
    else:
        initial = {}
        month = request.GET.get("month")
        if month:
            # Adding while viewing a past month? Default the date into that month.
            selected = parse_month(month)
            today = timezone.localdate()
            initial["date"] = today if month_start(today) == selected else selected
        form = ExpenseForm(initial=initial)

    return render(
        request,
        "expenses/expense_form.html",
        {"form": form, "title": "Add expense", "submit_label": "Save expense"},
    )


@login_required
def expense_edit(request, pk):
    expense = get_object_or_404(Expense.objects.select_related("category"), pk=pk)

    if request.method == "POST":
        form = ExpenseForm(request.POST, instance=expense)
        if form.is_valid():
            expense = form.save()
            messages.success(request, 'Updated "%s".' % expense.name)
            return redirect(expense.get_absolute_url())
    else:
        form = ExpenseForm(instance=expense)

    return render(
        request,
        "expenses/expense_form.html",
        {
            "form": form,
            "expense": expense,
            "title": "Edit expense",
            "submit_label": "Save changes",
        },
    )


@login_required
def expense_delete(request, pk):
    expense = get_object_or_404(Expense.objects.select_related("category"), pk=pk)

    if request.method == "POST":
        target = expense.get_absolute_url()
        name = expense.name
        expense.delete()
        messages.success(request, 'Deleted "%s".' % name)
        return redirect(target)

    return render(request, "expenses/expense_confirm_delete.html", {"expense": expense})


# ---------------------------------------------------------------------------
# CSV export
# ---------------------------------------------------------------------------


@login_required
def expense_export_csv(request):
    """Export the current month, honouring whatever filters the list page has on."""
    current = parse_month(request.GET.get("month"))
    start, end = month_range(current)

    queryset = Expense.objects.select_related("category").filter(date__gte=start, date__lt=end)

    search = request.GET.get("q", "").strip()
    if search:
        queryset = queryset.filter(Q(name__icontains=search) | Q(note__icontains=search))
    category_id = request.GET.get("category", "").strip()
    if category_id.isdigit():
        queryset = queryset.filter(category_id=int(category_id))

    queryset = queryset.order_by("date", "created_at")

    response = HttpResponse(content_type="text/csv; charset=utf-8")
    filename = "expenses-%s.csv" % current.strftime("%Y-%m")
    response["Content-Disposition"] = 'attachment; filename="%s"' % filename
    # BOM so Excel reads the UTF-8 correctly.
    response.write("﻿")

    writer = csv.writer(response)
    writer.writerow(["Date", "Name", "Category", "Amount", "Note"])
    for expense in queryset:
        writer.writerow(
            [
                expense.date.isoformat(),
                expense.name,
                expense.category.name,
                "%.2f" % expense.amount,
                expense.note.replace("\r\n", " ").replace("\n", " "),
            ]
        )
    writer.writerow([])
    writer.writerow(["Total", "", "", "%.2f" % sum_amount(queryset), ""])

    return response


# ---------------------------------------------------------------------------
# Monthly spending target
# ---------------------------------------------------------------------------


@login_required
def budget_edit(request):
    """Set, change, or remove the spending target for one month."""
    month = parse_month(request.GET.get("month") or request.POST.get("month"))
    budget = Budget.objects.filter(month=month).first()
    back = f"{reverse('dashboard')}?month={month:%Y-%m}"

    if request.method == "POST":
        if "remove" in request.POST:
            if budget:
                budget.delete()
                messages.success(request, f"Removed the target for {month:%B %Y}.")
            return redirect(back)

        form = BudgetForm(request.POST, instance=budget)
        if form.is_valid():
            target = form.save(commit=False)
            # The month comes from the URL, never from the submitted form.
            target.month = month
            target.save()
            messages.success(request, f"Target for {month:%B %Y} saved.")
            return redirect(back)
    else:
        initial = {}
        if budget is None:
            # Carry the most recent earlier target forward as a starting point;
            # month-to-month targets rarely change much.
            previous = Budget.objects.filter(month__lt=month).order_by("-month").first()
            if previous:
                initial["amount"] = previous.amount
        form = BudgetForm(instance=budget, initial=initial)

    start, end = month_range(month)
    spent = sum_amount(Expense.objects.filter(date__gte=start, date__lt=end))

    return render(
        request,
        "expenses/budget_form.html",
        {
            "form": form,
            "month": month,
            "month_key": month.strftime("%Y-%m"),
            "budget": budget,
            "spent": spent,
            "back_url": back,
        },
    )
