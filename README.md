# Expense Tracker

A single-user personal expense tracker. Log what you spend, review it by month.

Django 5.2 · PostgreSQL on [Neon](https://neon.tech) · deployed on Vercel · server-rendered templates, plain CSS, one Chart.js bar chart.

---

## What it does

| Page | Path | |
|---|---|---|
| Dashboard | `/` | Month total, month-over-month delta, spend per day, projected month end, largest expense, per-category breakdown, 6-month bar chart with an average line, month picker |
| Expense list | `/expenses/` | Filtered by month (`?month=2026-09`), grouped by day with per-day subtotals, sortable, searchable, running total, quick-add form at the top |
| Add / edit | `/expenses/new/`, `/expenses/<id>/edit/` | `ModelForm`, native date picker, redirects back to that expense's month |
| Delete | `/expenses/<id>/delete/` | Confirmation page; only `POST` actually deletes |
| CSV export | `/expenses/export/?month=2026-09` | Exports the current month, honouring active filters |
| Admin | `/admin/` | Both models, with `date_hierarchy` and category/date filters |

Everything sits behind `@login_required`. There is no signup page by design — you create the one account with `createsuperuser`.

### Interface

Plain CSS in a single stylesheet, no framework. Every colour is a custom property defined once at the top of `static/css/style.css`, with a dark palette swapped in under `prefers-color-scheme: dark` — the app gets opened on a phone at night. The Chart.js bar chart reads the same custom properties at draw time, so it follows the theme too.

Phone layout is a first-class case, not an afterthought: the top nav collapses to a bottom tab bar with a floating add button, list rows reflow from a grid into stacked cards, and inputs are 16px so iOS doesn't zoom the page on focus. Amounts are always monospace with tabular figures so digits line up down a column. Icons are one inline SVG sprite referenced with `<use>` — no icon font, no extra request.

---

## Local setup

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # macOS / Linux

pip install -r requirements.txt

cp .env.example .env            # then fill it in — see below
```

Generate a secret key for `.env`:

```bash
python -c "from django.core.management.utils import get_random_secret_key as k; print(k())"
```

Run the migrations, create your account, start the server:

```bash
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

Open http://127.0.0.1:8000/ and sign in.

---

## Environment variables

Both `.env` (local) and Vercel's **Project Settings → Environment Variables** need these five keys:

| Key | What goes in it |
|---|---|
| `SECRET_KEY` | 50-char random string. Never commit it. Use a **different** value on Vercel than locally. |
| `DEBUG` | `True` locally, `False` on Vercel. Defaults to `False` if unset. |
| `ALLOWED_HOSTS` | Comma-separated. `127.0.0.1,localhost` locally. On Vercel you can leave it empty — the deployment hostname is added automatically from `VERCEL_URL` / `VERCEL_PROJECT_PRODUCTION_URL`. Add your custom domain here if you attach one. |
| `DATABASE_URL` | Neon **pooled** string — the host contains `-pooler`. This is what the running app uses. |
| `DATABASE_URL_DIRECT` | Neon **direct** string — no `-pooler` in the host. Used only by `migrate` / `makemigrations`. |

`.env` is gitignored. `.env.example` is committed with dummy values.

---

## The Neon pooled/direct split

Neon hands out two connection strings and mixing them up causes confusing failures.

**Pooled** (`ep-xxx-pooler.region.aws.neon.tech`) goes through PgBouncer in *transaction* mode. That is the right endpoint for the app, especially on Vercel, where every serverless invocation would otherwise open its own Postgres connection and exhaust the limit.

**Direct** (`ep-xxx.region.aws.neon.tech`) is a real Postgres session. Schema changes need one: `migrate` takes advisory locks and runs DDL that does not survive being chopped into per-statement transactions by PgBouncer.

`config/settings.py` picks the right one automatically by looking at `sys.argv` — run `manage.py migrate` and it uses `DATABASE_URL_DIRECT`; serve a request and it uses `DATABASE_URL`. You don't have to swap anything by hand.

Three settings follow from using PgBouncer, all in `settings.py`:

- **`DISABLE_SERVER_SIDE_CURSORS = True`** — server-side cursors (what `.iterator()` opens) reference a session that transaction pooling has already handed to someone else. Without this you get errors that look nothing like their cause.
- **`CONN_MAX_AGE = 0`** — PgBouncer is doing the pooling. Holding connections open on Django's side just burns Neon compute and starves the pool.
- **`sslmode=require`** — forced onto whichever URL is used; Neon refuses plaintext connections.

**Cold starts are expected.** Neon suspends compute after inactivity on the free tier, so the first request after an idle period takes a few seconds while the database wakes. That is the platform, not a bug. `connect_timeout` is set to 10s to give it room.

---

## Deploying to Vercel

**1. Run migrations from your machine first.** Vercel's build container should not be doing schema changes, and it uses the pooled endpoint anyway:

```bash
python manage.py migrate      # uses DATABASE_URL_DIRECT automatically
python manage.py createsuperuser
```

**2. Push the repo to GitHub and import it in Vercel.** No framework preset needed — `vercel.json` describes the build.

**3. Set the five environment variables** listed above in Project Settings, for Production (and Preview if you use it). Set `DEBUG=False`.

**4. Deploy.**

### How the deployment is wired

`vercel.json` defines two builds:

- `config/wsgi.py` via `@vercel/python` — the Django app itself, as a serverless function. It exports both `application` and `app`, since different runtime versions look for different names.
- `build_files.sh` via `@vercel/static-build` — runs `collectstatic` into `staticfiles_build/`, which Vercel publishes to its CDN.

The routes send `/static/*` to the CDN output and everything else to the function, so static files never cost you a function invocation. `STATIC_ROOT` is `staticfiles_build/static/` so the collected paths line up with the `/static/` route.

WhiteNoise stays in the middleware stack for local `DEBUG=False` runs. Note the static storage backend is `CompressedStaticFilesStorage`, **not** the `Manifest` variant — the manifest would live in the CDN output that the serverless function never sees, so hashed lookups would fail at runtime.

Python version is pinned to 3.12 in `.python-version` and in `vercel.json`.

### After deploying

Vercel's filesystem is read-only, so you cannot run `manage.py` there. Any future migration runs from your machine against `DATABASE_URL_DIRECT`, then you redeploy.

---

## Notes on the data model

- **`amount` is a `DecimalField(10, 2)`.** Never a float — floats accumulate rounding error across a month of totals. Decimal is preserved end to end: model, aggregation, template filter, CSV.
- **`date` is a `DateField`, not `DateTimeField`.** What matters is which day you spent it. It also means no timezone can shift a late-night expense into the next month.
- `TIME_ZONE = "Asia/Dhaka"`, so "today" in the date field default is your local day.
- `MinValueValidator(Decimal("0.01"))` on amount — no zero or negative expenses.
- `Meta.ordering = ["-date", "-created_at"]`, with an index on `date` and a composite index matching that ordering. Every query filters by date.
- `Category` is `on_delete=PROTECT`, so you can't delete a category out from under existing expenses.
- Seven categories (Food, Transport, Bills, Rent, Health, Shopping, Other) are seeded by a data migration, each with a hex colour used in the dashboard.

Day subtotals on the list page call `.order_by()` with no arguments before `.values("date").annotate(...)`. An explicit ordering gets folded into the `GROUP BY`, and `-created_at` is unique per row, so without clearing it every expense comes back as its own one-row "day".

Every aggregation is a database `GROUP BY` — `TruncMonth` + `Sum`, wrapped in `Coalesce(..., Decimal("0"))` so an empty month returns zero instead of `None`. Nothing is summed by looping a queryset in Python.

## Changing the currency

The taka sign lives in exactly two coupled places: `CURRENCY_SYMBOL` in `settings.py`, read by the `money` template filter in `expenses/templatetags/money.py`. Change the setting and every amount on every page follows.

---

## Project layout

```
.
├── config/                  project settings, root urls, wsgi/asgi
├── expenses/                the single app
│   ├── migrations/          0001_initial, 0002_seed_categories
│   ├── templatetags/money.py  |money filter, {% currency_symbol %}, {% query_replace %}
│   ├── models.py forms.py views.py admin.py urls.py
├── templates/
│   ├── base.html
│   ├── registration/login.html
│   └── expenses/            dashboard, list, form, delete confirmation
├── static/css/style.css     the entire stylesheet
├── build_files.sh           Vercel static build step
├── vercel.json              build + routing config
├── .python-version          3.12
├── .env.example             committed; .env is not
└── requirements.txt         pinned
```
