# R5 Local Database Setup

This setup is for a trusted development machine with PostgreSQL and MongoDB already installed or otherwise available locally. It does not require paid services. Docker Compose may be used on a conventional development computer if the operator prefers it, but it is optional and is not a requirement of the application. Do not assume Docker, systemd, or a MongoDB server can run inside Android Debian PRoot.

## 1. Prepare isolated development databases

Create a dedicated development PostgreSQL database and a dedicated MongoDB database. Give the development user only the privileges needed to use the ChainScope schema and test its own data. Do not reuse production data, production credentials, or another project's database. The application does not create PostgreSQL tables automatically.

Set credentials in a local secret manager or the current shell (the examples below are intentionally empty placeholders):

```sh
export APP_ENV=development
export HOST=127.0.0.1
export CHAIN_SCOPE_POSTGRES_DSN=''
export CHAIN_SCOPE_MONGODB_URI=''
export CHAIN_SCOPE_MONGODB_DATABASE='chainscope_dev'
```

The PostgreSQL DSN must select the asyncpg driver. Accepted forms include `postgresql+asyncpg://...` and `postgresql://...` (the application normalizes the latter). MongoDB uses a standard Mongo URI. Never put actual values in Git, issue text, logs, this document, or `.env.example`.

## 2. Apply the schema migration

From the project root with its virtual environment active:

```sh
python -m pip install -r requirements-dev.txt
alembic upgrade head
```

The migration creates the R5 tables described in `DATABASE_SCHEMA.md`. Startup will not call `create_all()` or run Alembic automatically.

## 3. Run the local API

```sh
APP_ENV=development HOST=127.0.0.1 uvicorn app.main:app --host 127.0.0.1 --port 8000
```

`GET /health` is liveness only. `GET /api/v1/health/dependencies` checks the configured PostgreSQL and MongoDB adapters. The API group refuses to operate outside development/test or when the configured bind host is not loopback. No authentication exists, so do not bind the API to `0.0.0.0`, a LAN interface, or a public host.

## 4. Optional live database integration test

Use dedicated databases named for testing, not development or production. First apply the migration to the dedicated PostgreSQL test database; configure a separate MongoDB test database whose name contains `test`:

```sh
export CHAIN_SCOPE_TEST_POSTGRES_DSN='postgresql+asyncpg://.../chainscope_test'
export CHAIN_SCOPE_TEST_MONGODB_URI='mongodb://...'
export CHAIN_SCOPE_TEST_MONGODB_DATABASE='chainscope_test'
export CHAIN_SCOPE_POSTGRES_DSN="$CHAIN_SCOPE_TEST_POSTGRES_DSN"
alembic upgrade head
HF_HUB_OFFLINE=1 python -m pytest -q tests/test_r5_live_databases.py
```

The integration test requires all three `CHAIN_SCOPE_TEST_*` values and rejects database names that are not explicitly test-named. It inserts unique synthetic rows and removes only the rows it created. Without these variables, the test is skipped; local SQLite/fake-Mongo tests are not described as live PostgreSQL/Mongo validation.

## Android / Debian PRoot note

The target tablet has not been used for this phase. R5's Python drivers were resolved for ARM64 in the remote build environment, but a compatible PostgreSQL/MongoDB server deployment inside PRoot is not established. No Docker, systemd, `mongod`, or database service is assumed to exist there. Keep the API on loopback and do not place database credentials in the app bundle. Any future remote database connection needs a separately approved threat model, transport encryption, access controls and tablet test phase.
