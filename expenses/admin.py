from django.contrib import admin

from .models import Budget, Category, Expense


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ["name", "color", "expense_count"]
    search_fields = ["name"]

    def get_queryset(self, request):
        from django.db.models import Count

        return super().get_queryset(request).annotate(_expense_count=Count("expenses"))

    @admin.display(ordering="_expense_count", description="expenses")
    def expense_count(self, obj):
        return obj._expense_count


@admin.register(Expense)
class ExpenseAdmin(admin.ModelAdmin):
    list_display = ["date", "name", "category", "amount"]
    list_filter = ["category", "date"]
    search_fields = ["name", "note"]
    date_hierarchy = "date"
    list_select_related = ["category"]
    autocomplete_fields = ["category"]
    ordering = ["-date", "-created_at"]


@admin.register(Budget)
class BudgetAdmin(admin.ModelAdmin):
    list_display = ["month", "amount", "updated_at"]
    ordering = ["-month"]
    date_hierarchy = "month"
