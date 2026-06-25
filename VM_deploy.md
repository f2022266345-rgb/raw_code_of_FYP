# VM_deploy.md — Deploy LUMINA backends to a DigitalOcean CPU Droplet (1 → 100%)

A complete, copy-paste guide to run **both backends** on a single DigitalOcean
Ubuntu droplet with Docker, a shared Postgres, an nginx reverse proxy, free SSL
(Let's Encrypt), a custom domain, and **commit-to-deploy** via GitHub Actions.

Each backend is its own Git repo and deploys **independently** when you push to it.

---

## 0. Architecture

```
                       Internet
                          │  (DNS: api.example.com → DROPLET_PUBLIC_IP)
                          ▼
            ┌─────────────────────────────┐   Droplet (Ubuntu, Docker)
            │  nginx  :80/:443  (infra)    │   external network: lumina-net
            │   TLS termination + proxy    │
            └──────────────┬──────────────┘
                           │ http://lumina-express:4000
                           ▼
   ┌──────────────────────────────┐        ┌──────────────────────────────┐
   │ lumina-express (Express)     │ ─────▶ │ lumina-backend (FastAPI)     │
   │ repo: backend-express        │  8000  │ repo: backend  (internal only)│
   └───────────────┬──────────────┘        └───────────────┬──────────────┘
                   │  postgresql://lumina-db:5432           │
                   └────────────────┬──────────────────────┘
                                    ▼
                       ┌──────────────────────────┐
                       │ lumina-db (Postgres+pgvec)│  volume: pgdata
                       └──────────────────────────┘

Frontend (FYP_Project / Next.js) → deploy on Vercel, pointed at https://api.example.com
```

**Why this shape:** the three containers share one Docker network (`lumina-net`)
and find each other by container name (`lumina-db`, `lumina-backend`,
`lumina-express`). Only nginx is public. FastAPI is never exposed to the internet.

---

## 1. What you need first
- A DigitalOcean account.
- A domain name (e.g. `example.com`) with access to its DNS.
- Two GitHub repos:
  - **FastAPI** → already exists: `FYP_fastapi_backend`.
  - **Express** → create a new empty repo, e.g. `FYP_express_backend` (see §12).
- Your API keys ready: `GEMINI_API_KEY`, `GROQ_API_KEY`, Clerk keys, and optional
  feed keys (`YOUTUBE_API_KEY`, `NEWS_API_KEY`, `GOOGLE_PLACES_API_KEY`).

Pick one API subdomain for this guide: **`api.example.com`** (replace everywhere).

---

## 2. Create the droplet
1. DigitalOcean → **Create → Droplets**.
2. Region: closest to your users (e.g. Bangalore/Singapore for Pakistan).
3. Image: **Ubuntu 24.04 LTS**.
4. Size: **Basic → Regular**, minimum **2 GB RAM / 1 vCPU** (building images needs
   RAM; 2 GB is the practical floor, 4 GB is comfortable).
5. Authentication: **SSH key** (recommended) — upload your laptop's public key.
6. Hostname: `lumina-prod`. Create.

You now have a **public IP** (e.g. `203.0.113.10`). This is your **external IP** —
used for SSH, DNS, and all inbound traffic.

> **External vs internal IP**
> - **External (public) IP** — `203.0.113.10`: reachable from the internet; what
>   your domain points to.
> - **Internal (private/VPC) IP** — e.g. `10.114.0.2` (Networking tab): only
>   reachable by other droplets in the same VPC; use it if you later add a second
>   droplet or a DO Managed Database, so DB traffic never leaves the private network.
> - **Container-internal DNS** — `lumina-db`, `lumina-backend`: only inside the
>   Docker `lumina-net` network. This is how the apps talk to each other here.

---

## 3. First login + basic hardening
```bash
ssh root@203.0.113.10

# Create a non-root deploy user
adduser deploy
usermod -aG sudo deploy
rsync --archive --chown=deploy:deploy ~/.ssh /home/deploy   # copy your SSH key
# (now you can: ssh deploy@203.0.113.10)

# Firewall: allow SSH + web only
ufw allow OpenSSH
ufw allow 80
ufw allow 443
ufw --force enable
ufw status
```

---

## 4. Install Docker + Compose plugin
```bash
# As deploy (or root)
sudo apt-get update
sudo apt-get install -y ca-certificates curl git
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc
echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] \
  https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo $VERSION_CODENAME) stable" | \
  sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

# Run docker without sudo
sudo usermod -aG docker $USER
newgrp docker
docker --version && docker compose version
```

---

## 5. DNS — point your domain at the droplet
In your DNS provider, add an **A record**:

| Type | Name | Value           | TTL  |
|------|------|-----------------|------|
| A    | api  | 203.0.113.10    | 3600 |

(Optionally `app` → your Vercel frontend, per Vercel's instructions.)

Verify (may take a few minutes): `dig +short api.example.com` → your droplet IP.

---

## 6. Lay out the folders on the droplet
```bash
sudo mkdir -p /opt/lumina
sudo chown -R $USER:$USER /opt/lumina
cd /opt/lumina
```

You will end up with:
```
/opt/lumina/
  infra/             # shared Postgres + nginx + certbot (this guide provides files)
  backend/           # FastAPI repo clone
  backend-express/   # Express repo clone
```

---

## 7. Give the droplet read access to your private repos (deploy key)
```bash
# Generate a key the droplet uses to pull from GitHub
ssh-keygen -t ed25519 -C "lumina-droplet" -f ~/.ssh/github_deploy -N ""
cat ~/.ssh/github_deploy.pub
```
Add that public key as a **Deploy key** (read-only) on **each** GitHub repo:
GitHub repo → Settings → Deploy keys → Add deploy key → paste → Save.

Tell SSH to use it for GitHub:
```bash
cat >> ~/.ssh/config <<'EOF'
Host github.com
  IdentityFile ~/.ssh/github_deploy
  IdentitiesOnly yes
EOF
chmod 600 ~/.ssh/config
ssh -T git@github.com   # should greet you (accept the host key)
```

---

## 8. Clone the repos
```bash
cd /opt/lumina
git clone git@github.com:AbdRicher/FYP_fastapi_backend.git backend
git clone git@github.com:<your-user>/FYP_express_backend.git backend-express
```

> The `infra/` folder is not in either app repo. Create it on the droplet and copy
> in the three files from this project's `Backend/infra/` (compose, `.env.example`,
> `nginx/conf.d/lumina.conf`). Easiest: `scp -r Backend/infra deploy@203.0.113.10:/opt/lumina/`.

---

## 9. Configure environment files
```bash
# Infra
cd /opt/lumina/infra
cp .env.example .env
nano .env            # set a strong POSTGRES_PASSWORD

# FastAPI
cd /opt/lumina/backend
cp .env.example .env
nano .env
#   DATABASE_URL=postgresql+psycopg://postgres:<PASSWORD>@lumina-db:5432/FYP_DB_Latest
#   GEMINI_API_KEY=... GROQ_API_KEY=...   (PORT stays 8000)

# Express
cd /opt/lumina/backend-express
cp .env.example .env
nano .env
#   DATABASE_URL=postgresql://postgres:<PASSWORD>@lumina-db:5432/FYP_DB_Latest
#   FASTAPI_BASE_URL=http://lumina-backend:8000
#   FRONTEND_URL=https://app.example.com   (your Vercel URL)
#   CLERK_SECRET_KEY=... CLERK_PUBLISHABLE_KEY=... CLERK_WEBHOOK_SECRET=...
#   JWT_SECRET=...   (optional feed keys: YOUTUBE_API_KEY / NEWS_API_KEY / GOOGLE_PLACES_API_KEY)
```
Use the **same** `<PASSWORD>` in all three. The host is the container name
`lumina-db` — that is the "internal" address on the Docker network.

---

## 10. Create the shared network + start infra
```bash
docker network create lumina-net          # one time
cd /opt/lumina/infra
# Edit nginx/conf.d/lumina.conf: replace api.example.com with your real subdomain.
docker compose up -d
docker compose ps                         # lumina-db, lumina-nginx, lumina-certbot up
```

---

## 11. Start the backends + run first-time migrations
```bash
# FastAPI
cd /opt/lumina/backend
docker compose up -d --build

# Express
cd /opt/lumina/backend-express
docker compose up -d --build

# ── First-run DB migrations (order matters) ──
# 1) Express creates the core/Sequelize tables (users, profiles, etc.)
cd /opt/lumina/backend-express
docker compose exec -T express node scripts/run_migration_008_sync_models.js
docker compose exec -T express node scripts/run_migration_007_align_onboarding_schema.js
docker compose exec -T express npm run db:migrate:v3     # settings/notifications/activity

# 2) FastAPI creates pgvector + ORM tables + SQL defaults
cd /opt/lumina/backend
docker compose exec -T backend python scripts/run_migrations.py
```
Health check:
```bash
cd /opt/lumina/backend-express
docker compose exec -T express curl -fsS http://localhost:4000/health
# → {"status":"ok","database":"connected",...}
```

---

## 12. SSL with Let's Encrypt (certbot)
With nginx already serving HTTP for `api.example.com` (step 10), issue the cert:
```bash
cd /opt/lumina/infra
docker compose run --rm --entrypoint "\
  certbot certonly --webroot -w /var/www/certbot \
  -d api.example.com --email you@example.com --agree-tos --no-eff-email" certbot
```
Then enable HTTPS:
1. Edit `infra/nginx/conf.d/lumina.conf`:
   - **Uncomment** the `server { listen 443 ssl; ... }` block.
   - In the `:80` server, replace the `location / { proxy_pass ... }` body with
     `return 301 https://$host$request_uri;` (keep the ACME `location` block).
2. Reload:
```bash
docker compose exec nginx nginx -s reload
```
Test: `curl -I https://api.example.com/health` → `200`. Certbot auto-renews
(the `certbot` service loops `renew` every 12h); reload nginx weekly via cron:
```bash
(crontab -l 2>/dev/null; echo "0 3 * * 1 docker compose -f /opt/lumina/infra/docker-compose.yml exec nginx nginx -s reload") | crontab -
```

---

## 13. Commit-to-deploy (GitHub Actions → droplet)
Each repo already contains `.github/workflows/deploy.yml`. It SSHes into the
droplet on every push and runs `git pull && docker compose up -d --build`.

**a) Make a key for GitHub Actions → droplet (separate from the deploy key):**
```bash
# On the droplet
ssh-keygen -t ed25519 -C "gha-deploy" -f ~/.ssh/gha -N ""
cat ~/.ssh/gha.pub >> ~/.ssh/authorized_keys
cat ~/.ssh/gha            # copy this PRIVATE key
```
**b) In EACH GitHub repo → Settings → Secrets and variables → Actions, add:**

| Secret | Value |
|--------|-------|
| `DROPLET_HOST` | `203.0.113.10` |
| `DROPLET_USER` | `deploy` |
| `DROPLET_SSH_KEY` | the **private** `~/.ssh/gha` contents |
| `DROPLET_PORT` | `22` (optional) |

**c) Done.** Now `git push` to `backend` rebuilds only FastAPI; `git push` to
`backend-express` rebuilds only Express. Watch progress in the repo's **Actions** tab.

> Small droplet tip: building on the VM uses RAM. If a build OOMs, add a swapfile:
> `sudo fallocate -l 2G /swapfile && sudo chmod 600 /swapfile && sudo mkswap /swapfile && sudo swapon /swapfile && echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab`

---

## 14. Frontend (Vercel)
The Next.js app stays on Vercel. Set its env:
- `NEXT_PUBLIC_EXPRESS_API_BASE = https://api.example.com`
- `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY = ...`, `CLERK_SECRET_KEY = ...`

And in the droplet's Express `.env`, set `FRONTEND_URL` to the Vercel URL so CORS allows it.

---

## 15. Everyday operations
```bash
# Logs (run from each service's directory)
( cd /opt/lumina/backend-express && docker compose logs -f )
( cd /opt/lumina/backend         && docker compose logs -f )
( cd /opt/lumina/infra           && docker compose logs -f nginx )

# Restart a service
cd /opt/lumina/backend-express && docker compose restart

# Manual update (same as CI does)
cd /opt/lumina/backend-express && git pull && docker compose up -d --build

# Backup the database
docker exec lumina-db pg_dump -U postgres FYP_DB_Latest | gzip > ~/lumina_$(date +%F).sql.gz
```

---

## 16. Git restructuring (run on your LOCAL machine)
You asked to drop the outer monorepo and run the two backends as independent
repos. The FastAPI backend is already its own repo (`FYP_fastapi_backend`). For
Express, create a new GitHub repo first, then:

```bash
cd "Project Code"

# (Optional but recommended) keep a zip backup of the old monorepo first:
#   git bundle create ../raw_code_backup.bundle --all

# 1) Remove the outer monorepo repo (IRREVERSIBLE — destroys monorepo history)
rm -rf .git

# 2) Initialise the Express repo
cd Backend/backend-express
git init -b main
git add .
git commit -m "Initial commit: LUMINA Express gateway"
git remote add origin git@github.com:<your-user>/FYP_express_backend.git
git push -u origin main

# 3) Push the v3 changes already made to the FastAPI repo
cd ../backend
git add .
git commit -m "v3: answer-first persona, twin updates"
git push        # pushes to its existing remote (branch dev)
```

> `node_modules/` and `.env` are already in each repo's `.gitignore`, so they are
> not pushed. The droplet rebuilds dependencies during `docker compose build`.

---

## 17. Troubleshooting
| Symptom | Fix |
|--------|-----|
| `502 Bad Gateway` from nginx | Express container down or wrong name. `docker ps`, check `lumina-express` is on `lumina-net`. |
| Express can't reach FastAPI | `FASTAPI_BASE_URL` must be `http://lumina-backend:8000` (container name, not localhost). |
| DB connection refused | Wrong host — must be `lumina-db`, and all three must share `lumina-net`. |
| certbot fails | DNS A record must resolve to the droplet and port 80 must be open before issuing. |
| Action can't SSH | `DROPLET_SSH_KEY` must be the **private** key; its public half must be in `~/.ssh/authorized_keys` on the droplet. |
| Build killed (OOM) | Add swap (see §13) or use a 4 GB droplet. |

---

You're done — push to either backend repo and it redeploys itself. 🎉
