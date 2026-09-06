from django.db import migrations

# name -> chart colour
DEFAULT_CATEGORIES = [
    ("Food", "#ef4444"),
    ("Transport", "#f59e0b"),
    ("Bills", "#3b82f6"),
    ("Rent", "#8b5cf6"),
    ("Health", "#10b981"),
    ("Shopping", "#ec4899"),
    ("Other", "#64748b"),
]


def seed(apps, schema_editor):
    Category = apps.get_model("expenses", "Category")
    for name, color in DEFAULT_CATEGORIES:
        Category.objects.get_or_create(name=name, defaults={"color": color})


def unseed(apps, schema_editor):
    # Only remove seeded categories that never got used — PROTECT would raise
    # otherwise, and losing a category you actually spent money under is worse
    # than leaving a stale row behind.
    Category = apps.get_model("expenses", "Category")
    Category.objects.filter(
        name__in=[name for name, _ in DEFAULT_CATEGORIES],
        expenses__isnull=True,
    ).delete()


class Migration(migrations.Migration):
    dependencies = [("expenses", "0001_initial")]
    operations = [migrations.RunPython(seed, unseed)]
