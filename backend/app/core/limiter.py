"""
PURPOSE
-------
A single, shared SlowAPI Limiter instance for the whole application.

Defined in its own module (not inside main.py) specifically to avoid a
circular import: routers/auth.py needs `limiter` to decorate individual
endpoints (e.g. @limiter.limit("5/minute") on signup), and main.py needs
to import those routers to mount them — if the limiter were defined in
main.py, routers/auth.py importing FROM main.py would create a cycle.

DEPENDENCY NOTE: app.core.config.Settings does not yet define rate-limit
fields (e.g. DEFAULT_RATE_LIMIT). This file reads them via getattr(...)
with sensible defaults so it works correctly today and will automatically
pick up real config values if/when those fields are added to Settings in
a future step — see the inline comments below.
"""
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.core.config import settings

# ----------------------------------------------------------------------
# Default rate limit, applied to any endpoint decorated with
# @limiter.limit(...) that doesn't specify its own limit string, and used
# as the fallback here if Settings has no DEFAULT_RATE_LIMIT field.
#
# "100/minute" is a reasonable default for general API traffic — high
# enough not to bother a legitimate user clicking around the app, low
# enough to blunt a basic scripted-abuse attempt. Auth-specific endpoints
# (signup, login, refresh) will apply their OWN, much stricter limits
# directly via decorators in routers/auth.py (a later step) — this
# default is a floor for the rest of the API, not what auth endpoints
# will actually use.
# ----------------------------------------------------------------------
_DEFAULT_RATE_LIMIT = getattr(settings, "DEFAULT_RATE_LIMIT", "100/minute")

# ----------------------------------------------------------------------
# key_func=get_remote_address: rate limits are tracked per client IP
# address. This is the standard choice for unauthenticated endpoints
# (signup, login) where there's no user identity yet to key on — it's
# the only identifying signal available before a token exists.
#
# PRODUCTION NOTE (flagged, not implemented here): get_remote_address
# reads the client IP from the request directly. If this app is deployed
# behind a reverse proxy or load balancer (nginx, an ALB, Cloudflare),
# the "client" FastAPI/Starlette sees by default is the proxy, not the
# real visitor — every request would appear to come from the same IP,
# making the limiter useless. Fixing this requires trusting an
# X-Forwarded-For header from a KNOWN proxy, which is an infrastructure
# / deployment-topology decision (which proxy, how many hops) that
# belongs in the hardening milestone once the actual deployment target
# is known — not something to guess at here.
# ----------------------------------------------------------------------
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=[_DEFAULT_RATE_LIMIT],
)

# ----------------------------------------------------------------------
# STORAGE BACKEND NOTE (flagged, not implemented here): SlowAPI's
# Limiter defaults to in-memory storage for tracking request counts.
# That's correct and sufficient for local development and for a
# single-process deployment. It silently stops working correctly the
# moment the app runs as multiple processes/instances (e.g. behind a
# load balancer, or multiple uvicorn workers) — each process would track
# its own separate counts, so the EFFECTIVE limit becomes
# (configured_limit × number_of_processes), not the configured limit.
#
# Fixing this means pointing Limiter at a shared store (Redis is the
# standard choice: `storage_uri="redis://..."`), which requires a Redis
# instance to exist — an infrastructure dependency not yet part of
# Milestone 1's scope. Flagged for the M12 hardening milestone per the
# architecture doc, not invented as a shortcut here.
# ----------------------------------------------------------------------