"""Authentication classes for the DRF API.

The Next.js frontend talks to Django through a same-origin BFF proxy using the
Django session cookie. DRF's stock ``SessionAuthentication`` enforces a CSRF
token on every unsafe method (POST/PUT/PATCH/DELETE); the SPA/BFF doesn't carry
one, so authenticated POSTs (save settings, trigger scrape/rank, logout) fail
with 403. We exempt CSRF here and rely on the session cookie's ``SameSite=Lax``
attribute to block cross-site POSTs instead.
"""
from rest_framework.authentication import SessionAuthentication


class CsrfExemptSessionAuthentication(SessionAuthentication):
    def enforce_csrf(self, request):
        # Skip DRF's CSRF check. Cross-site POST protection comes from the
        # SameSite=Lax session cookie (see SESSION_COOKIE_SAMESITE).
        return
