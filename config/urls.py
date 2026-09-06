from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    # Built-in auth only — there is deliberately no signup route. The single
    # account is created with `manage.py createsuperuser`.
    path(
        "login/",
        auth_views.LoginView.as_view(template_name="registration/login.html", redirect_authenticated_user=True),
        name="login",
    ),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("", include("expenses.urls")),
]

admin.site.site_header = "Expense Tracker admin"
admin.site.site_title = "Expense Tracker"
admin.site.index_title = "Data"
