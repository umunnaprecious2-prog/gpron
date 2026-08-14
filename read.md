read.md

project: Gpron Integrated Service Platform
date: 2026-08-13
version: 2.0.0

---

current state:
🔧 ARCHITECTURE MIGRATION IN PROGRESS (Mongo → Postgres/Neon, layered restructure, Docker, Render)
- Backend rewritten from MongoDB/Motor to Postgres via SQLAlchemy 2.0 (async) + asyncpg + Alembic
- `app/` restructured into a layered pattern: routes/ services/ middlewares/ utils/ validators/
  types/ exceptions/ scripts/ models/ (see architecture section below)
- Dockerized local dev: `docker-compose.yml` runs postgres + backend + frontend together
- Render deployment blueprint added (`render.yaml`): backend web service + frontend static site
- Not yet verified end-to-end against a real Neon database (needs your real DATABASE_URL)
- No existing MongoDB data was migrated. Fresh schema, dummy/test accounts only (by design,
  confirmed with user)

---

architecture:

```
app/
  main.py            FastAPI app + uvicorn entrypoint, CORS, exception handlers, router wiring
  config.py           Settings (pydantic-settings, reads .env)
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
- ✅ `tests/conftest.py` creates tables before the test session runs
- ✅ `frontend/src/api.js` BASE reads `VITE_API_URL` for cross-origin Render deployment
- ✅ `render.yaml` Blueprint for backend (web service) + frontend (static site)
- ✅ `.env.example` and `.env` updated to Postgres/Neon connection string format

---

known pre-existing issue (not caused by this migration):
- `tests/test_orders.py`'s order-creation payload sends `items: [...]` but `OrderCreate` requires
  `cart: [...]`. Fixed as part of this migration's security/correctness pass.

---

tasks in progress:
- End-to-end verification against a real Neon database (needs user's real DATABASE_URL)
- Security review of the migrated codebase
- Initial git push to https://github.com/umunnaprecious2-prog/gpron.git (incremental commits)

---

verified test accounts (pre-migration, MongoDB; need to be recreated via seed script on Postgres):
- Customer: customer@gpron.com / customer123
- Manager: manager@gpron.com / manager123

---

environment details:
- Backend: FastAPI + uvicorn (--reload) on port 8000
- Frontend: Vite on port 5174 (hot reload)
- Database: Postgres (local Docker for dev, Neon for hosted/production)
- ORM/migrations: SQLAlchemy 2.0 async + asyncpg + Alembic
- Authentication: JWT (python-jose) + bcrypt (passlib)
- Linting: ruff | Formatting: black | Testing: pytest + pytest-asyncio
- Local dev: `docker compose up` (primary path) or native `uvicorn`/`npm run dev` (fallback)
- Hosting target: Render (backend web service + frontend static site), see render.yaml
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

5. Deploy:
   - Create a Neon project, grab the connection string, put it in Render's gpron-backend
     DATABASE_URL env var (not committed anywhere)
   - Push this repo to GitHub, connect it as a Render Blueprint (render.yaml)
   - Set ALLOWED_ORIGINS (backend) and VITE_API_URL (frontend) once both services have URLs
   - Confirm `alembic upgrade head` (preDeployCommand) applies cleanly against Neon

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
