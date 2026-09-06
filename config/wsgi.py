"""
WSGI entry point.

Vercel's Python runtime imports this module and looks for a callable named
`app` (older runtimes look for `application`), so both names are exported.
"""

import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

application = get_wsgi_application()

# Alias for the Vercel Python runtime.
app = application
