# LUMINA v3 — New Features & DigitalOcean Deploy Notes

This document covers the feature work added in the v3 pass and the exact steps to
ship it on a DigitalOcean droplet.

## What was added

### 1. Mobile-responsive dashboard (hamburger drawer)
- `FYP_Project/lib/ui-store.ts` — tiny zustand store for the mobile drawer state.
- `components/dashboard/app-sidebar.tsx` — refactored into a shared `SidebarBody`;
  `AppSidebar` (desktop, `hidden md:flex`) + `MobileSidebar` (a `Sheet` drawer).
- `components/dashboard/dashboard-header.tsx` — hamburger button (`md:hidden`) toggles the drawer.
- `app/dashboard/layout.tsx` — renders both; main padding is now responsive.

### 2. Persisted settings (was localStorage-only)
- Table `user_settings (user_id, settings JSONB, updated_at)`.
- `GET/PUT /api/settings` (Express) → `controllers/settingsController.js`.
- `app/dashboard/settings/page.tsx` loads from the server and writes through on Save
  (localStorage kept as an offline cache).

### 3. In-app notification system
- Table `notifications`.
- `GET /api/notifications`, `GET /api/notifications/unread-count`,
  `PATCH /api/notifications/:id/read`, `PATCH /api/notifications/read-all`.
- The header bell now reads from the DB and polls every 60s; crisis notifications are high-priority.
- Notifications are generated on each chat turn (and gated by the user's notification settings).

### 4. Activity log (log tracking)
- Table `activity_log`; `GET /api/activity`.
- `services/notificationService.js` exposes `logActivity()` + `createNotification()`,
  called fire-and-forget from `chatController.js`.

### 5. Personalized right-rail feeds (YouTube / Social / LinkedIn)
- `controllers/feedController.js` now personalizes by the student's field of study:
  - **Academic** → live YouTube courses (`YOUTUBE_API_KEY`) + education news.
  - **Social** → campus/networking news + LinkedIn profile-improvement recommendations.
  - **Wellness** → counselor/support directory.
- All providers degrade gracefully to curated/deep-linked cards when a key is missing.

### 6. Human, answer-first agent persona
- `backend/services/state_engine.py` response rules tightened: always answer with a
  concrete next step, never end on a question (except a genuine safety check), never
  identify as an AI, and build on prior context for continuity.
- The digital twin already updates on every interaction (FastAPI `_update_profile_from_chat`
  background task + Express `processNewInteractions`).

## Required DB migration

```bash
# Express side (new tables):
cd backend-express
npm run db:migrate:v3        # runs migrations/002_lumina_v3_features.sql (idempotent)
```

Under Docker, the one-shot migrate service now runs it automatically:
```bash
docker compose run --rm migrate
```

## New environment variables (all optional)

Set in `backend-express/.env` (or pass to the `express` service / droplet env):

| Var | Powers | If unset |
|-----|--------|----------|
| `YOUTUBE_API_KEY` | Academic right-rail YouTube courses | falls back to news only |
| `NEWS_API_KEY` | Academic/Social news cards | section may be empty |
| `GOOGLE_PLACES_API_KEY` | Wellness support directory | curated PK helplines |

LinkedIn has **no public recommendations API**, so those cards are generated from the
student's field and deep-link into LinkedIn's own tools — no key needed.

## DigitalOcean droplet checklist
1. Provision droplet, install Docker + Docker Compose.
2. Clone repo, copy `.env.example` → `.env` at root and per-service; fill Clerk + Gemini/Groq keys (+ optional feed keys).
3. `docker compose up --build -d`
4. `docker compose run --rm migrate` and `docker compose run --rm migrate-backend` (once).
5. Point a domain / reverse proxy (nginx/Caddy) at the frontend (3000) and Express (4000); set `FRONTEND_URL` and `NEXT_PUBLIC_EXPRESS_API_BASE` to the public URLs.
6. Verify `GET /health` on Express returns `{"status":"ok"}`.

### Port note
Code defaults `FASTAPI_BASE_URL` to `:8080`, but `docker-compose.yml` runs FastAPI on
`:8000` and sets `FASTAPI_BASE_URL=http://backend:8000` explicitly — consistent in Docker.
For non-Docker local dev, make sure `FASTAPI_BASE_URL` matches the port FastAPI actually binds.
