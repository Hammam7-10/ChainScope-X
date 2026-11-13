# R5 Local Database Setup

This setup is for a trusted development host. It uses only local, self-hosted PostgreSQL and MongoDB and no paid service. The repository includes an optional `compose.yaml` for a conventional Linux/macOS/Windows development computer with Docker Compose installed. Docker is not required by the application and is not assumed to exist or work inside Android Debian PRoot.

## 1. Start local development databases

On a conventional development computer that already has Docker Compose, copy the placeholder configuration to the ignored `.env` file, set strong local-only passwords, and start the two services:

```sh
cp .env.example .env
# Edit .env locally: set POSTGRES_PASSWORD and MONGO_INITDB_ROOT_PASSWORD.
# Keep the actual values only in this ignored file or a local secret manager.
docker compose up -d
```

Both container ports are bound to `127.0.0.1`; named volumes preserve database state across restarts. `docker compose down` stops the containers but preserves data. `docker compose down -v` deletes the local database volumes and is destructive. The Compose file contains no password defaults; it refuses to start until the required variables are set.

For a native PostgreSQL/Mongo installation, start the services using that host's existing service manager and create isolated development databases/users. The app does not install servers or provision users. Do not use production databases or another project's data.

## 2. Configure the application

Set these environment variables in the local shell/secret manager or the ignored `.env` file:

```sh
export APP_ENV=development
export HOST=127.0.0.1
export CHAIN_SCOPE_POSTGRES_DSN='postgresql+asyncpg://<user>:<password>@127.0.0.1:5432/chainscope_dev'
export CHAIN_SCOPE_MONGODB_URI='mongodb://<user>:<password>@127.0.0.1:27017/?authSource=admin'
export CHAIN_SCOPE_MONGODB_DATABASE='chainscope_dev'
```

Replace placeholders locally; never put real values in Git, tickets, logs, this document, or `.env.example`. Percent-encode reserved characters in URI credentials. The Mongo root user created by Compose authenticates against `admin`; the ChainScope database name remains `chainscope_dev`. PostgreSQL accepts `postgresql+asyncpg://...`; `postgresql://...` is normalized by the config adapter.

## 3. Apply the schema migration and run the API

From the project root with its virtual environment active:

```sh
python -m pip install -r requirements-dev.txt
alembic upgrade head
APP_ENV=development HOST=127.0.0.1 uvicorn app.main:app --host 127.0.0.1 --port 8000
```

`alembic upgrade head` creates the R5 tables in PostgreSQL. Startup does not run Alembic or call `create_all()`. `GET /health` is liveness only; `GET /api/v1/health/dependencies` checks configured PostgreSQL and MongoDB adapters. API business routes require development/test mode, a loopback `HOST`, and a direct loopback client peer. No authentication exists; do not bind to a LAN/public interface and do not put the app behind a reverse proxy.

## 4. Optional live database integration test

Use dedicated test databases, never the development or production databases. Configure the test variables, point Alembic explicitly at the test PostgreSQL DSN, apply the migration, then run the opt-in integration test:

```sh
export CHAIN_SCOPE_TEST_POSTGRES_DSN='postgresql+asyncpg://<user>:<password>@127.0.0.1:5432/chainscope_test'
export CHAIN_SCOPE_TEST_MONGODB_URI='mongodb://<user>:<password>@127.0.0.1:27017/?authSource=admin'
export CHAIN_SCOPE_TEST_MONGODB_DATABASE='chainscope_test'
export CHAIN_SCOPE_POSTGRES_DSN="$CHAIN_SCOPE_TEST_POSTGRES_DSN"
alembic upgrade head
HF_HUB_OFFLINE=1 python -m pytest -q tests/test_r5_live_databases.py
```

The test requires all three `CHAIN_SCOPE_TEST_*` values and rejects database names not explicitly test-named. It inserts uniquely identified synthetic records and removes only its own rows. Without those variables it is skipped; SQLite/fake-Mongo tests are not live-service verification.

## Android / Debian PRoot note

The Samsung target was not used for R5. Python drivers were resolved for ARM64 in the remote build environment, but a database-server deployment inside PRoot is not established. Do not assume Docker, systemd, `mongod`, or PostgreSQL is available there. The Compose file is for a conventional host only. Keep the API on loopback and do not bundle database credentials with the app. Any future remote database connection requires separately approved threat modeling, transport encryption, access controls, and tablet testing.
