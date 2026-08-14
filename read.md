read.md

project: Gpron Integrated Service Platform
date: 2026-08-14
version: 2.0.0

---

current state:
✅ LIVE IN PRODUCTION (Postgres/CockroachDB migration + layered restructure + Render deploy, fully
verified end-to-end against the real deployed services, not just locally)
- Backend rewritten from MongoDB/Motor to Postgres via SQLAlchemy 2.0 (async) + asyncpg + Alembic
- `app/` restructured into a layered pattern: routes/ services/ middlewares/ utils/ validators/
  types/ exceptions/ scripts/ models/ (see architecture section below)
- Dockerized local dev: `docker-compose.yml` runs postgres + backend + frontend together
- Deployed on Render: `gpron-backend` (web service) + `gpron-frontend` (static site), both live
- Hosted database: CockroachDB Serverless (Basic plan). Originally targeted Neon, but Neon's
  domain was unreachable from the user's network across multiple connections/carriers (confirmed
  not a local issue via Neon's own status page showing all-systems-operational). CockroachDB is
  genuinely free (50M RUs + 10GiB/month, no card required), Postgres wire-compatible, and doesn't
  need manual reactivation after inactivity the way Oracle/Supabase's free tiers do.
- No existing MongoDB data was migrated. Fresh schema, dummy/test accounts only (by design,
  confirmed with user)

---

architecture:

```
app/
  main.py            FastAPI app + uvicorn entrypoint, CORS, exception handlers, router wiring
  config.py           Settings (pydantic-settings, reads .env, strips whitespace from every value)
  database.py          SQLAlchemy async engine/session, Base, get_db() dependency
  models/db.py          ORM models: User, Order, Log, Newsletter (source of truth for schema)
  types/                enums + output/response Pydantic schemas (user.py, order.py)
  validators/            input/request Pydantic schemas (user.py, order.py, newsletter.py)
  routes/                 thin controllers: parse request -> call service -> return response
  services/                 business logic + DB queries (auth, order, tracking, newsletter, google_auth)
  middlewares/auth_middleware.py   JWT auth guards: get_current_user, require_manager
  utils/security.py                 password hashing + JWT encode/decode (pure helpers)
  exceptions/                        named exceptions (errors.py) + central handler (handlers.py)
  scripts/seed_dev_data.py            recreates the two verified test accounts
migrations/            Alembic migrations (async), versions/0001_initial.py = full schema
alembic.ini
Dockerfile              backend image, --reload for hot reload
docker-compose.yml        postgres + backend + frontend, for local dev
render.yaml                Render Blueprint: gpron-backend (web) + gpron-frontend (static site)
```

database schema (Postgres): `users`, `orders` (incl. `cart`/`items` as JSONB, `base_fee`, `notes`,
`customer_name/email`), `logs`, `newsletter`. UUID primary keys. API responses still return `id`
as a string, so the public API contract is unchanged from the Mongo version.

CockroachDB specifics: needed real fixes, not just a connection-string swap. SQLAlchemy's plain
`postgresql+asyncpg` dialect fails against it on two dialect-internals mismatches -- see the
`sqlalchemy-cockroachdb` comment in requirements.txt. Fixed by adding that dialect package and
using the `cockroachdb+asyncpg://` URL scheme specifically for CockroachDB (other providers still
use plain `postgresql+asyncpg://`). `app/database.py` also patches out SQLAlchemy's automatic
"json" (non-jsonb) codec setup, which CockroachDB has no matching type for -- safe no-op since our
schema only ever uses JSONB. SSL detection stays host-based/provider-agnostic, so a future
provider switch is a URL change, not a re-migration.

---

completed tasks:
- ✅ Replaced Motor/PyMongo with SQLAlchemy async + asyncpg + Alembic
- ✅ Restructured `app/` into routes/services/middlewares/utils/validators/types/exceptions/scripts
- ✅ ORM models for users/orders/logs/newsletter with UUID PKs and JSONB cart/items
- ✅ Auth flow (register/login/Google) rewritten against Postgres, manager-code protection preserved
- ✅ Order flow (create/list/update-status) and public tracking rewritten against Postgres
- ✅ Newsletter subscribe rewritten against Postgres
- ✅ Central exception handling (NotFoundError/UnauthorizedError/ForbiddenError/ConflictError)
- ✅ Dockerfile + docker-compose.yml (postgres + backend + frontend, hot reload preserved)
- ✅ Alembic configured with async engine; initial migration hand-written (0001_initial.py)
- ✅ `render.yaml` Blueprint for backend (web service) + frontend (static site), fixed against real
  Render validation errors (preDeployCommand not on free plan, static sites reject plan/region)
- ✅ Added `sqlalchemy-cockroachdb` dialect + `cockroachdb+asyncpg://` scheme support
- ✅ Fixed two dependency gaps only caught by testing against a clean environment: `requests`
  (needed by `google.auth.transport.requests`, not declared by google-auth) and `bcrypt<4.1.0`
  (passlib 1.7.4 breaks against bcrypt>=4.1.0's removed `__about__` attribute)
- ✅ `app/config.py` strips whitespace from every setting (`str_strip_whitespace=True`) -- Render's
  env var UI turned a pasted `DATABASE_URL` into one with a trailing newline, breaking the database
  name; this fixes that class of bug permanently regardless of host platform
- ✅ **Deployed and verified live**: registered a real account, logged in, created an order,
  tracked it -- all confirmed working against the live Render backend + CockroachDB, not just
  locally
- ✅ CORS locked down: `ALLOWED_ORIGINS` set to the live frontend URL, confirmed via preflight
  request that the frontend origin is allowed and other origins are rejected

---

verified test accounts (pre-migration, MongoDB; recreate via seed script if needed on Postgres):
- Customer: customer@gpron.com / customer123
- Manager: manager@gpron.com / manager123

---

environment details:
- Backend: FastAPI + uvicorn (--reload) on port 8000 locally; live at
  https://gpron-backend.onrender.com
- Frontend: Vite on port 5174 (hot reload) locally; live at https://gpron-frontend.onrender.com
- Database: Postgres (local Docker for dev, CockroachDB Serverless for hosted/production)
- ORM/migrations: SQLAlchemy 2.0 async + asyncpg + Alembic (+ sqlalchemy-cockroachdb for the
  hosted DB specifically)
- Authentication: JWT (python-jose) + bcrypt (passlib), bcrypt pinned <4.1.0
- Linting: ruff | Formatting: black | Testing: pytest + pytest-asyncio
- Local dev: `docker compose up` (primary path) or native `uvicorn`/`npm run dev` (fallback)
- Python env: project root | Node env: frontend/

---

next steps:
1. Local dev (Docker, primary path):
   docker compose up
   (starts Postgres, runs `alembic upgrade head`, starts backend with --reload, starts frontend)

2. Seed test accounts (once containers are up):
   docker compose exec backend python -m app.scripts.seed_dev_data

3. Non-Docker fallback:
   pip install -r requirements.txt
   alembic upgrade head
   uvicorn app.main:app --reload
   cd frontend && npm install && npm run dev

4. Run tests:
   docker compose exec backend pytest
   (or `pytest` locally, against a running Postgres)

5. Housekeeping (not urgent, worth doing soon):
   - Rotate the CockroachDB SQL user password (it was shared through chat during setup) --
     regenerate in the CockroachDB console, update DATABASE_URL in Render's dashboard, redeploy
   - Consider adding EMAIL_SERVICE_KEY / OPENAI_API_KEY / Google OAuth env vars on Render if those
     features get used later -- currently unset, those code paths are gracefully unused

6. (Optional v2) Add email notifications, analytics, refined UI polish
7. (Optional v3) Delivery personnel role, mobile version

---

api endpoints (unchanged):
POST   /auth/register
POST   /auth/login
POST   /auth/google
POST   /orders              (customer, auth required)
GET    /orders/user         (customer, auth required)
GET    /orders/all          (manager only)
PATCH  /orders/status       (manager only)
GET    /track/{tracking_id} (public)
POST   /newsletter/subscribe (public)

---

pricing logic (unchanged):
Normal:  ₦500 base + ₦150 per item
Express: ₦900 base + ₦250 per item

tracking ID format: GPRON-{YEAR}-{NNNN}
