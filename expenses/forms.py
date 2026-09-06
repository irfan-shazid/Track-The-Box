from django import forms
from django.utils import timezone

from .models import Budget, Category, Expense


class ExpenseForm(forms.ModelForm):
    class Meta:
        model = Expense
        fields = ["date", "name", "amount", "category", "note"]
        widgets = {
            "date": forms.DateInput(
                # type="date" gives the native picker; the value must be ISO
                # for the browser to populate it when editing.
                attrs={"type": "date", "class": "input"},
                format="%Y-%m-%d",
            ),
            "name": forms.TextInput(
                attrs={"class": "input", "placeholder": "e.g. Lunch at Star Kabab", "autofocus": True}
            ),
            "amount": forms.NumberInput(
                attrs={"class": "input", "step": "0.01", "min": "0.01", "inputmode": "decimal", "placeholder": "0.00"}
            ),
            "category": forms.Select(attrs={"class": "input"}),
            "note": forms.Textarea(attrs={"class": "input", "rows": 3, "placeholder": "Optional"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["date"].input_formats = ["%Y-%m-%d"]
        self.fields["category"].queryset = Category.objects.all()
        self.fields["category"].empty_label = None
        # QuickExpenseForm drops `note`, so this subclass-safe guard matters.
        if "note" in self.fields:
            self.fields["note"].required = False
        if not self.instance.pk and not self.initial.get("date"):
            # "Today" in Asia/Dhaka, not UTC.
            self.initial["date"] = timezone.localdate()


class QuickExpenseForm(ExpenseForm):
    """The one-line form at the top of the list page. Same model, no note field."""

    class Meta(ExpenseForm.Meta):
        fields = ["date", "name", "amount", "category"]


class BudgetForm(forms.ModelForm):
    """Just the amount. The month comes from the URL, not the user."""

    class Meta:
        model = Budget
        fields = ["amount"]
        widgets = {
            "amount": forms.NumberInput(
                attrs={
                    "class": "input",
                    "step": "0.01",
                    "min": "0.01",
                    "inputmode": "decimal",
                    "placeholder": "0.00",
                    "autofocus": True,
                }
            ),
        }
        labels = {"amount": "Monthly target"}
