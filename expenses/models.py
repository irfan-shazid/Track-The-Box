from decimal import Decimal

from django.core.validators import MinValueValidator
from django.db import models
from django.urls import reverse


class Category(models.Model):
    name = models.CharField(max_length=50, unique=True)
    color = models.CharField(
        max_length=7,
        default="#64748b",
        help_text="Hex colour used for this category in the dashboard chart, e.g. #ef4444",
    )

    class Meta:
        ordering = ["name"]
        verbose_name_plural = "categories"

    def __str__(self):
        return self.name


class Expense(models.Model):
    # DateField, not DateTimeField: what matters is the calendar day, and a
    # plain date can never be shifted into an adjacent month by a timezone.
    date = models.DateField(db_index=True)
    name = models.CharField(max_length=200)
    # Decimal all the way down. A FloatField here would quietly corrupt totals.
    amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    category = models.ForeignKey(
        Category,
        on_delete=models.PROTECT,
        related_name="expenses",
    )
    note = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-date", "-created_at"]
        indexes = [
            models.Index(fields=["-date", "-created_at"], name="expense_date_created_idx"),
        ]

    def __str__(self):
        return f"{self.date} {self.name}"

    @property
    def month_key(self):
        """'2026-09' — the querystring value that filters the list to this expense."""
        return self.date.strftime("%Y-%m")

    def get_absolute_url(self):
        return f"{reverse('expense_list')}?month={self.month_key}"
