# iTaxEasy Mobile APK Backend (Python FastAPI + Alembic + PSQL)

This repository contains the brand new Python backend specifically developed for the **iTaxEasy Mobile APK** (Phase 1). It is modeled on high-performance enterprise structures, utilizing **FastAPI**, **SQLAlchemy** (asynchronous), **Alembic** migrations, and **PostgreSQL**.

---

## 📁 Repository Directory Structure

```
itaxeasy-apk-backend/
├── app/                          # Core Python FastAPI Application
│   ├── api/                      # Routing & Business Modules
│   │   ├── deps.py               # Shared deps (get_current_user JWT guard)
│   │   └── auth/                 # Authentication Module (SRS Module 1 & 2)
│   │       ├── router.py         # Endpoints (firebase, refresh, logout, me)
│   │       ├── schemas.py        # Pydantic Request/Response Validators
│   │       └── service.py        # Firebase verify + JWT/session logic
│   ├── core/                     # Application configurations
│   │   ├── config.py             # Pydantic Settings (.env loader)
│   │   ├── database.py           # Async SQLAlchemy Engine & get_db Dependency
│   │   └── firebase.py           # Firebase Admin SDK init + token verify
│   ├── main.py                   # FastAPI app initiation and entrypoint
│   └── models.py                 # SQLAlchemy models (User, UserSession, OtpLog)
│
├── alembic/                      # Alembic Database Migration Engine
│   ├── env.py                    # Async configuration of alembic schema contexts
│   ├── script.py.mako            # Migration template file
│   └── versions/                 # Versioned migration histories
│       └── a1b2c3d4e5f6_initial_migration.py  # Baseline initial migration
│
├── dev/                          # Local automation scripts
│   ├── start.sh                  # Installs poetry, spins up DB, migrates, starts app
│   └── stop.sh                   # stops and tears down Postgres/Redis containers
│
├── alembic.ini                   # Alembic configuration
├── docker-compose.dev.yml        # Development environment services (PostgreSQL & Redis)
├── pyproject.toml                # Poetry packages configuration
└── poetry.toml                   # In-project virtual environment setting
```

---

## ⚡ Quick Start

You can spin up the local development database, run the async schema migrations, and launch the hot-reloading FastAPI application on port `3002` with a single command!

### 1. Launch Dev Environment
Run the start automation script from the project root:
```bash
./dev/start.sh
```

### 2. View Swagger API Docs
Once started, go to your browser and access:
* **Swagger UI Docs:** [http://localhost:3002/docs](http://localhost:3002/docs)
* **ReDoc Docs:** [http://localhost:3002/redoc](http://localhost:3002/redoc)

### 3. Stop Environment
To stop the database and Redis services:
```bash
./dev/stop.sh
```

> The dev Postgres (`docker-compose.dev.yml`) now uses the login `itaxeasy_apk_user` and the
> database `itaxeasy_apk`. An existing dev volume still has the old `postgres` / `itaxeasy`
> ones: recreate it with `docker compose -f docker-compose.dev.yml down -v`, which deletes the dev
> data, then run `./dev/start.sh`.

---

## 🐳 Docker Setup

The API runs in Docker with all dependencies installed inside the image. It uses Python 3.12
and the locked Poetry dependencies, and is started with `uvicorn app.main:app` on `PORT`
(default 3002) with `WORKERS` (default 2), like the PM2 deploy. It uses the Postgres on
the host machine, not a container.

- **Database:** `itaxeasy_apk`, login `itaxeasy_apk_user`. The naming follows the itaxeasy
  convention: database `itaxeasy_<name>`, login `<database>_user`.
- **Env:** everything comes from `.env` via `env_file`, never baked into the image. The Firebase
  service-account JSON files are excluded from the image, because the code doesn't use them.
- **Files:** the container filesystem is read-only (`read_only: true`); the API stores no files.
  Uploaded Form 16 PDFs go straight to the OCR service. Files larger than 1 MB are buffered in the
  container's own temp folder `/tmp`, which lives in memory (`tmpfs`) and is cleared on restart.
- **Redis:** not used by the app code.

### Ports

| Server | Service | Port | Address | Set by |
|---|---|---|---|---|
| Local (Docker Desktop) | APK API (`itaxeasy-apk-api`) | **3002** | `http://localhost:3002` (docs at `/docs`) | default (or `PORT` in `.env`) |
| server1 (`192.168.1.3`) | APK API (`itaxeasy-apk-api`) | **3002** | `http://192.168.1.3:3002` (docs at `/docs`) | `PORT=3002` in `.env` |
| Production | APK API | **54110** | nginx `apk.itaxeasy.com` → `127.0.0.1:54110` | `PORT=54110` in `.env` |

`docker ps` shows `0.0.0.0:3002->3002/tcp` for `itaxeasy-apk-api` (server1 / local); on server1 it sits next to the
itaxeasy frontend (3000) and backend (3001).

### Run locally (Docker Desktop)

`docker-compose.yml` points a `localhost` host in `DATABASE_URL` at the host machine.
```bash
docker compose up -d --build
docker compose logs -f api
docker compose down
```
Run migrations with the same host swap, because `run` bypasses the container's start command:
```bash
docker compose run --rm api sh -c 'H=$(python -c "import socket; print(socket.getaddrinfo(\"host.docker.internal\", None, socket.AF_INET)[0][4][0])"); export DATABASE_URL="$(printf %s "$DATABASE_URL" | sed "s#@localhost:#@$H:#")"; alembic upgrade head'
```

### Production (Ubuntu server)

Use `docker-compose.prod.yml`. The container joins the shared Docker network `itaxeasy`, the same
one as the itaxeasy frontend and backend, and publishes `PORT`. It reaches the server's Postgres at
`host.docker.internal`, which is the server's address on that network (`172.30.10.1`).

**One-time server setup.** The `itaxeasy` network, the Docker boot setting and the `ufw` rule for
`172.30.10.0/24` are created once by the itaxeasy backend setup. See its README, *Production →
One-time server setup*. The APK backend additionally needs:

```bash
# 1. The DB login (renamed itaxapk -> itaxeasy_apk_user) may connect from the Docker network
HBA=/etc/postgresql/18/main/pg_hba.conf
sudo cp -p $HBA $HBA.bak-apk
echo 'host    itaxeasy_apk    itaxeasy_apk_user    172.30.10.0/24    scram-sha-256' | sudo tee -a $HBA
sudo -u postgres psql -c "SELECT pg_reload_conf()"

# 2. .env in the project folder
cp -p .env .env.bak-docker
sed -i -E 's#^DATABASE_URL=postgresql://[^:]+:#DATABASE_URL=postgresql://itaxeasy_apk_user:#' .env
sed -i 's#@localhost:5432/#@host.docker.internal:5432/#' .env
sed -i '/^PORT=/d' .env; echo 'PORT=3002' >> .env   # production: PORT=54110 (nginx upstream)
```

| Variable | Value |
|---|---|
| `DATABASE_URL` | `postgresql://itaxeasy_apk_user:<password>@host.docker.internal:5432/itaxeasy_apk` |
| `PORT` | `3002` (server1) / `54110` (production) |
| `ENVIRONMENT` | `production` |
| `TEST_OTP_ENABLED` | `false` in production. When `true`, the listed test phones log in with a fixed code and no SMS. |

**Deploy / update**

```bash
git fetch origin +refs/heads/add-docker-setup:refs/remotes/origin/add-docker-setup
git checkout -B add-docker-setup origin/add-docker-setup
docker compose -f docker-compose.prod.yml build
docker compose -f docker-compose.prod.yml run --rm api alembic current         # read-only check
docker compose -f docker-compose.prod.yml run --rm api alembic upgrade head    # only if migrations are pending
docker compose -f docker-compose.prod.yml up -d --force-recreate
```

**Check**

```bash
docker ps --filter name=itaxeasy-apk --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'
curl -s http://127.0.0.1:3002/; echo                   # {"status":"healthy"} (production: :54110)
docker exec itaxeasy-apk-api sh -c 'touch /app/x 2>&1'  # "Read-only file system"
```

**Switching over from PM2** (production; a few seconds of downtime):
```bash
pm2 stop itaxeasy-apk-backend                      # frees port 54110
docker compose -f docker-compose.prod.yml up -d
curl -fsS http://127.0.0.1:54110/                 # rollback: docker compose -f docker-compose.prod.yml down && pm2 start itaxeasy-apk-backend
pm2 delete itaxeasy-apk-backend && pm2 save        # once stable, so PM2 doesn't restart it on reboot
```

**Auto-start on reboot:** `restart: always`, plus Docker enabled on boot
(`sudo systemctl enable --now docker containerd`).

---

## 🛠️ Key Technology Stack

* **FastAPI:** Modern, high-performance web framework for Python.
* **SQLAlchemy 2.0 (Async):** Fully asynchronous Object Relational Mapper.
* **Alembic:** Database migration tool for SQLAlchemy.
* **asyncpg:** Asynchronous PostgreSQL driver for asyncio.
* **Firebase Admin SDK:** Verifies the phone-OTP ID token issued on-device.
* **Poetry:** Fast and secure Python packaging and dependency manager.

---

## 🔐 Authentication (Phase 1 — Firebase Phone OTP)

Auth is **phone + Firebase OTP only** (no passwords). The OTP is sent and
verified entirely on-device by the **Firebase Phone Auth SDK** (free via Google).
The backend never sends or stores OTP codes — it only **verifies the Firebase ID
token** the app forwards, then issues its own JWT access + refresh tokens.

```
App: enter phone → Firebase sends SMS OTP → enter OTP → Firebase returns ID token
App → POST /api/auth/firebase { idToken, fullName?, email? }
Backend: verify ID token (Admin SDK) → upsert user + session → return JWT pair
App → all later calls: Authorization: Bearer <accessToken>
```

### Endpoints
| Method | Path | Purpose |
|--------|------|---------|
| POST | `/api/auth/firebase` | Register (first call, needs `fullName`) **or** login |
| POST | `/api/auth/refresh`  | Rotate refresh token → new access + refresh pair |
| POST | `/api/auth/logout`   | Revoke a refresh-token session |
| GET  | `/api/auth/me`       | Current user profile (SRS Module 2) |
| PATCH| `/api/auth/me`       | Edit profile (fullName, email, photo, timeZone, language) |

### Tables (SRS Module 1)
* `users` — phone, firebaseUid, fullName, email?, profilePhoto?, timeZone, language
* `user_sessions` — one row per refresh token (hashed), supports rotation/logout
* `otp_logs` — **audit** trail of Firebase verifications (no OTP codes stored)

---

## 🔥 Firebase Setup (one-time)

1. Create a project at <https://console.firebase.google.com>.
2. **Authentication → Sign-in method → Phone → Enable.**
3. **Project Settings → Service accounts → Generate new private key.** Save the
   downloaded JSON as `firebase-service-account.json` in this project root
   (already gitignored) and point `FIREBASE_CREDENTIALS_PATH` at it in `.env`.
4. For the mobile app (later phase): add an Android app, download
   `google-services.json`, and register your debug **and** release keystore
   **SHA-1 + SHA-256** fingerprints (required for Android phone auth).
5. For development, add **test phone numbers** under Authentication → Sign-in
   method → Phone → *Phone numbers for testing* to avoid burning SMS quota.

> Without the credentials file the server still boots (you'll see a warning), but
> `/api/auth/firebase` returns `401` until it's in place.

# itaxeasy-apk-back
