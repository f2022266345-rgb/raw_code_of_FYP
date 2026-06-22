# LUMINA — Deployment Guide

A complete, practical guide to deploying the LUMINA student-support system:
PostgreSQL + pgvector, the FastAPI AI backend, the Express API gateway, and the
Next.js frontend — locally, with Docker, on a VM, on Render, and on Vercel.

---

## 1. Architecture

```
                ┌─────────────────────────┐
  Browser ────▶ │  Next.js Frontend (3000) │   (Vercel or Docker)
                └────────────┬─────────────┘
                             │ NEXT_PUBLIC_EXPRESS_API_BASE
                             ▼
                ┌─────────────────────────┐
                │ Express Gateway  (4000)  │   auth (Clerk/JWT), routing
                └───────┬─────────┬────────┘
            FASTAPI_BASE_URL      │ DATABASE_URL
                        ▼         ▼
        ┌────────────────────┐  ┌──────────────────────────┐
        │ FastAPI AI  (8000) │  │ PostgreSQL 16 + pgvector  │
        │ agents + twin + RAG│─▶│  DB: FYP_DB_Latest        │
        └────────────────────┘  └──────────────────────────┘
```

- **One shared database** (`FYP_DB_Latest`) is used by BOTH backends.
- The **pgvector** extension is required (embeddings / RAG).
- Express is the public API the frontend talks to; it proxies AI calls to FastAPI.

| Service        | Folder            | Stack              | Default port |
|----------------|-------------------|--------------------|--------------|
| Frontend       | `FYP_Project/`    | Next.js 16, Clerk  | 3000         |
| API gateway    | `backend-express/`| Node 20 (ESM)      | 4000         |
| AI backend     | `backend/`        | FastAPI, Python    | 8000         |
| Database       | —                 | Postgres 16 + pgvector | 5432     |

---

## 2. Environment variables

Copy each `.env.example` to `.env` and fill it in.

### `backend/.env` (FastAPI)
| Var | Required | Notes |
|-----|----------|-------|
| `DATABASE_URL` | ✅ | `postgresql+psycopg://user:pass@host:5432/FYP_DB_Latest` (plain `postgresql://` is auto-upgraded) |
| `GEMINI_API_KEY` | ✅ | Google AI Studio key |
| `GEMINI_MODEL` | | default `gemini-2.5-flash` |
| `GEMINI_EMBEDDING_MODEL` | | default `gemini-embedding-001` |
| `GEMINI_HISTORY_SUMMARY` | | `0` (keep off to save quota) |
| `GEMINI_PROFILE_EXTRACTION` | | `0` (keep off to save quota) |
| `PORT` | | injected by PaaS; default 8000 |

### `backend-express/.env` (Express)
| Var | Required | Notes |
|-----|----------|-------|
| `DATABASE_URL` | ✅ | same DB as FastAPI |
| `FASTAPI_BASE_URL` | ✅ | e.g. `http://backend:8000` or the deployed FastAPI URL |
| `FRONTEND_URL` | ✅ | deployed frontend URL (CORS origin) |
| `JWT_SECRET` | ✅ | long random string |
| `CLERK_SECRET_KEY`, `CLERK_PUBLISHABLE_KEY`, `CLERK_WEBHOOK_SECRET` | ✅ | from Clerk dashboard |
| `PORT` | | default 4000 |

### `FYP_Project/.env` (Frontend — `NEXT_PUBLIC_*` are baked in at BUILD time)
| Var | Required | Notes |
|-----|----------|-------|
| `NEXT_PUBLIC_EXPRESS_API_BASE` | ✅ | deployed Express URL |
| `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY` | ✅ | Clerk publishable key |
| `CLERK_SECRET_KEY` | ✅ | Clerk secret (server) |

> ⚠️ `NEXT_PUBLIC_*` values are embedded into the browser bundle when you build.
> Changing them requires a **rebuild**, not just a restart.

---

## 3. Database: Postgres + pgvector + migrations

### 3.1 Create the database & enable pgvector
```sql
CREATE DATABASE "FYP_DB_Latest";
\c "FYP_DB_Latest"
CREATE EXTENSION IF NOT EXISTS vector;
```
The FastAPI app also runs `CREATE EXTENSION IF NOT EXISTS vector` on startup, but
enabling it explicitly first avoids permission surprises on managed Postgres.

### 3.2 Run migrations — IN THIS ORDER

Tables have cross-dependencies (`users` must exist before the digital-twin tables
that FK to it), so order matters.

**Step 1 — Express models (creates `users` + all Sequelize tables):**
```bash
cd backend-express
npm install
npm run db:sync          # scripts/run_migration_008_sync_models.js (CREATE TABLE IF NOT EXISTS)
npm run db:migrate:align # optional: aligns onboarding tables to the models
```

**Step 2 — FastAPI tables + column-default fixes (one command):**
This ensures pgvector, creates the ORM tables, and applies every
`backend/migrations/*.sql` in order (these add the DB-level defaults that fix the
`NotNullViolation` issues). Idempotent — safe to run on every deploy:
```bash
cd backend
pip install -r requirements.txt
python scripts/run_migrations.py
```

> Prefer `psql`? Run each file yourself (also idempotent):
> ```bash
> psql "$DATABASE_URL" -f migrations/004_fix_digital_twin_timestamps.sql
> psql "$DATABASE_URL" -f migrations/005_fix_skill_mastery_bkt_defaults.sql
> psql "$DATABASE_URL" -f migrations/006_digital_twin_column_defaults.sql
> ```

### 3.3 pgAdmin
1. Connect to your Postgres server, open the `FYP_DB_Latest` database.
2. Right-click the DB → **Query Tool**.
3. Run `CREATE EXTENSION IF NOT EXISTS vector;`
4. Open each `backend/migrations/00X_*.sql` file and execute it.

### 3.4 Enable pgvector on managed Postgres (Render/Supabase/RDS)
- **Render:** open the database's **PSQL** shell → `CREATE EXTENSION IF NOT EXISTS vector;`
- **Supabase:** Dashboard → Database → Extensions → enable `vector`.
- **AWS RDS:** `CREATE EXTENSION vector;` (Postgres ≥ 15 supports it).

---

## 4. Local development (no Docker)

Open three terminals:

```bash
# 1) FastAPI
cd backend
python -m venv .venv && . .venv/Scripts/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn main:app --reload --port 8000

# 2) Express
cd backend-express
npm install
npm run dev            # nodemon, port 4000

# 3) Frontend
cd FYP_Project
npm install
npm run dev            # Next.js, port 3000
```

---

## 5. Docker Compose (the easiest full stack)

Everything (DB + 3 services) with one command:

```bash
cp .env.example .env                    # fill GEMINI_API_KEY, Clerk keys, JWT_SECRET
docker compose up --build               # builds & starts db, backend, express, frontend
docker compose run --rm migrate         # Express models → creates users + tables
docker compose run --rm migrate-backend # FastAPI: pgvector + tables + SQL default fixes
```

- Frontend → http://localhost:3000
- Express → http://localhost:4000
- FastAPI docs → http://localhost:8000/docs
- Postgres → localhost:5432 (pgvector preinstalled via `pgvector/pgvector:pg16`)

Stop / reset:
```bash
docker compose down       # stop
docker compose down -v    # stop + delete the database volume
```

---

## 6. Deploy on a Virtual Machine (Ubuntu 22.04+)

### Option A — Docker on the VM (recommended)
```bash
sudo apt update && sudo apt install -y docker.io docker-compose-plugin git
git clone <your-repo-url> lumina && cd lumina
cp .env.example .env && nano .env          # fill secrets
docker compose up -d --build
docker compose run --rm migrate
```
Then put **Nginx** in front as a reverse proxy + TLS (Certbot):
```nginx
server {
  server_name your-domain.com;
  location /        { proxy_pass http://localhost:3000; }   # frontend
  location /api/    { proxy_pass http://localhost:4000; }   # express
  # (FastAPI 8000 stays internal; Express proxies to it)
}
```
```bash
sudo apt install -y nginx certbot python3-certbot-nginx
sudo certbot --nginx -d your-domain.com
```

### Option B — Bare metal (systemd)
Install Postgres+pgvector, Node 20, and Python; then create one service per app, e.g.:
```ini
# /etc/systemd/system/lumina-backend.service
[Unit]
After=network.target postgresql.service
[Service]
WorkingDirectory=/opt/lumina/backend
EnvironmentFile=/opt/lumina/backend/.env
ExecStart=/opt/lumina/backend/.venv/bin/uvicorn main:app --host 0.0.0.0 --port 8000
Restart=always
[Install]
WantedBy=multi-user.target
```
```bash
sudo systemctl enable --now lumina-backend
```
Repeat for Express (`ExecStart=/usr/bin/node server.js`) and the frontend
(`npm run build` then `node .next/standalone/server.js`).

---

## 7. Deploy on Render (Blueprint)

The repo ships a **`render.yaml`** blueprint (DB + 3 services).

1. Push the repo to GitHub.
2. Render → **New + → Blueprint** → select the repo. It reads `render.yaml`.
3. After creation, open each service → **Environment** and fill the `sync: false`
   secrets (`GEMINI_API_KEY`, Clerk keys, `FRONTEND_URL`).
4. Open the database's PSQL shell and run `CREATE EXTENSION IF NOT EXISTS vector;`
5. Run migrations once — either:
   - locally pointing `DATABASE_URL` at the Render DB external URL, **or**
   - Render → backend service → **Shell** → run the migration commands in §3.2.

> Tip: prefer deploying the **frontend on Vercel** (§8) and only the two backends
> on Render. Delete the `lumina-frontend` block from `render.yaml` if so.

---

## 8. Deploy the frontend on Vercel

1. Vercel → **Add New → Project** → import the repo.
2. **Root Directory:** `FYP_Project`. Framework auto-detects **Next.js**.
3. **Environment Variables:**
   - `NEXT_PUBLIC_EXPRESS_API_BASE` = your deployed Express URL
   - `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY` = Clerk publishable key
   - `CLERK_SECRET_KEY` = Clerk secret
4. Deploy. Vercel rebuilds on every push to the connected branch.
5. After you know the Vercel URL, set it as `FRONTEND_URL` on the Express service
   (CORS) and rebuild the frontend if you changed any `NEXT_PUBLIC_*`.

`FYP_Project/vercel.json` is included; the `output: "standalone"` setting in
`next.config.mjs` is ignored by Vercel, so it's safe for both targets.

---

## 9. Auto deploy on commit (CI/CD)

Two GitHub Actions workflows are included:

- **`.github/workflows/ci.yml`** — on every push/PR, a `changes` job detects which
  service a commit touched (via `dorny/paths-filter`) and runs **only** the
  affected build/test job (FastAPI compile + pgvector, Express `db:sync`, frontend
  `next build`).
- **`.github/workflows/deploy.yml`** — on push to `master`/`main`, it detects the
  changed service and fires that service's **deploy hook**, so unrelated commits
  don't redeploy everything.

### Wire up the deploy hooks
1. **Render** → service → Settings → **Deploy Hook** → copy the URL.
2. **Vercel** → project → Settings → Git → **Deploy Hooks** → create one, copy URL.
3. GitHub → repo → Settings → **Secrets and variables → Actions** → add:
   - `RENDER_DEPLOY_HOOK_BACKEND`
   - `RENDER_DEPLOY_HOOK_EXPRESS`
   - `VERCEL_DEPLOY_HOOK_FRONTEND`

Missing secrets are skipped gracefully (the job logs and exits 0). Render and
Vercel can ALSO auto-deploy on push by themselves — the workflow just gives you
path-scoped control.

---

## 10. Post-deploy checklist

- [ ] `GET https://<fastapi>/docs` loads (FastAPI healthy).
- [ ] `CREATE EXTENSION vector` succeeded on the production DB.
- [ ] Migrations §3.2 ran (no `relation ... does not exist` / `NotNullViolation`).
- [ ] Express `FASTAPI_BASE_URL` points at the FastAPI service.
- [ ] Express `FRONTEND_URL` = the real frontend origin (CORS).
- [ ] Frontend `NEXT_PUBLIC_EXPRESS_API_BASE` = the real Express URL (rebuilt).
- [ ] Clerk keys set on both Express and Frontend.
- [ ] `GEMINI_API_KEY` set; consider billing (free tier = 20 chat calls/day).

## 11. Troubleshooting

| Symptom | Fix |
|---------|-----|
| `relation "..." does not exist` (42P01) | Run §3.2 migrations (`npm run db:sync`). |
| `null value in column ... violates not-null` | Apply `backend/migrations/004–006`. |
| `extension "vector" is not available` | Use the `pgvector/pgvector` image or enable it on managed PG (§3.4). |
| `429 RESOURCE_EXHAUSTED` from Gemini | Free tier 20/day cap — enable billing or wait for reset. |
| CORS errors in browser | Set `FRONTEND_URL` on Express to the exact frontend origin. |
| Frontend calls `localhost` in prod | Rebuild with the correct `NEXT_PUBLIC_EXPRESS_API_BASE`. |
| Docker build fails on `cp314` wheels | Change `backend/Dockerfile` base to `python:3.12-slim`. |
| `npm ci` fails (no lockfile) | Ensure `package-lock.json` is committed (it is now un-ignored). |
