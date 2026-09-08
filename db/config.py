"""Connection config for the Postgres migration. Override via env vars if needed."""
import os

PG_DSN = dict(
    host=os.environ.get("PGHOST", "localhost"),
    port=int(os.environ.get("PGPORT", "5432")),
    user=os.environ.get("PGUSER", "postgres"),
    password=os.environ.get("PGPASSWORD", "xauusd_dev_pw"),
    dbname=os.environ.get("PGDATABASE", "xauusd"),
)
