"""
PURPOSE
-------
Application entry point ONLY. This file wires together everything built in
the previous steps of Milestone 1 — it contains no business logic, no
request handling logic, and no data access of its own. Its entire job is
assembly: create the FastAPI app, manage the database connection lifecycle,
register middleware/handlers, and mount routers at their final paths.
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.core.config import settings
from app.core.database import close_database_connection, connect_to_database
from app.core.exceptions import register_exception_handlers
from app.core.limiter import limiter
from app.routers import auth, users


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Manages the database connection's lifetime across the whole
    application process — NOT per-request. connect_to_database() runs
    once, before the app starts accepting requests; everything after
    `yield` runs once, as the app shuts down. This is FastAPI's
    recommended replacement for the older @app.on_event("startup") /
    @app.on_event("shutdown") pattern.
    """
    await connect_to_database()
    yield
    await close_database_connection()


app = FastAPI(
    title=settings.APP_NAME,
    lifespan=lifespan,
    # Interactive API docs are genuinely useful in development but expose
    # the full API surface/schema to anyone who finds the URL — disabled
    # entirely outside development, per settings.is_production.
    docs_url=None if settings.is_production else "/docs",
    redoc_url=None if settings.is_production else "/redoc",
)

# ----------------------------------------------------------------------
# CORS
#
# allow_origins reads settings.cors_origin_list — the parsed list derived
# from the raw CORS_ORIGINS env var (app.core.config) — never a wildcard
# "*". An explicit allow-list is what makes allow_credentials=True (below)
# safe: browsers reject the combination of a wildcard origin with
# credentialed requests anyway, and even where they didn't, "any origin
# may send credentialed requests" is not a posture this app wants.
#
# allow_methods / allow_headers are scoped to what this API actually
# uses (standard REST verbs, Authorization + Content-Type headers) rather
# than left wildcarded.
# ----------------------------------------------------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)

# ----------------------------------------------------------------------
# Exception handlers
#
# register_exception_handlers (built in app.core.exceptions) wires up
# ALL THREE handlers in one call: AppError -> {error_code, message},
# RequestValidationError -> the same shape with field-level detail, and
# a catch-all for genuinely unhandled exceptions. main.py does not define
# any handler logic itself — it only triggers registration.
# ----------------------------------------------------------------------
register_exception_handlers(app)

# ----------------------------------------------------------------------
# Rate limiting (SlowAPI)
#
# app.state.limiter = limiter: SlowAPI's @limiter.limit(...) decorators
# (already applied inside routers/auth.py) look up the limiter instance
# via app.state at request time — this line is what connects those
# decorators to the shared Limiter instance built in app.core.limiter.
#
# add_exception_handler(RateLimitExceeded, ...): when a client exceeds a
# configured limit, SlowAPI raises RateLimitExceeded internally. Without
# this handler registered, that exception would fall through to FastAPI's
# default handling (or the catch-all above) rather than SlowAPI's own
# well-formed 429 response. _rate_limit_exceeded_handler is SlowAPI's
# own, purpose-built handler for this — not something to reimplement.
# ----------------------------------------------------------------------
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# ----------------------------------------------------------------------
# Routers
#
# Both routers already declare their OWN prefix internally
# (routers/auth.py -> "/auth", routers/users.py -> "/users"). Mounting
# them here with prefix=settings.API_V1_PREFIX ("/api/v1") combines with
# each router's own prefix to produce the final paths:
#   /api/v1/auth/signup, /api/v1/auth/login, /api/v1/auth/refresh
#   /api/v1/users/me
# This is exactly the resolution flagged as an open question when
# routers/auth.py was built — settings.API_V1_PREFIX is now the single
# place that controls the API's version segment for every router mounted
# this way.
# ----------------------------------------------------------------------
app.include_router(auth.router, prefix=settings.API_V1_PREFIX)
app.include_router(users.router, prefix=settings.API_V1_PREFIX)


@app.get("/")
async def root() -> dict[str, str]:
    """
    Simple unauthenticated root endpoint — useful as a quick manual
    smoke check that the process is up and serving requests, distinct
    from a real health-check endpoint (not part of Milestone 1's
    required scope; not invented here).
    """
    return {"message": "CareerPulse API is running"}