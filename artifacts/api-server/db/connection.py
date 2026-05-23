import os
import re
import sqlite3
from urllib.parse import urlparse, urlunparse

DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///database.db")
DB_TYPE = "sqlite" if DATABASE_URL.startswith("sqlite") else "postgres"

_RETURNING_RE = re.compile(r'\s+RETURNING\s+.+$', re.IGNORECASE | re.DOTALL)
_TABLE_RE = re.compile(r'INSERT\s+INTO\s+(\w+)', re.IGNORECASE)


class _Cursor:
    """Unified cursor: handles %s→? and INSERT...RETURNING for SQLite."""

    def __init__(self, raw_cur, raw_conn):
        self._c = raw_cur
        self._raw_conn = raw_conn

    def execute(self, sql, params=()):
        if DB_TYPE == "postgres":
            self._c.execute(sql, params)
            return self

        m = _RETURNING_RE.search(sql)
        if m:
            sql_clean = _RETURNING_RE.sub('', sql).replace('%s', '?')
            self._c.execute(sql_clean, params)
            last_id = self._c.lastrowid
            tm = _TABLE_RE.search(sql_clean)
            if tm and last_id:
                self._c.execute(
                    f'SELECT * FROM {tm.group(1)} WHERE rowid=?', (last_id,)
                )
        else:
            self._c.execute(sql.replace('%s', '?'), params)
        return self

    def fetchone(self):
        row = self._c.fetchone()
        if row is None:
            return None
        return dict(row) if DB_TYPE == "sqlite" else row

    def fetchall(self):
        rows = self._c.fetchall()
        if DB_TYPE == "sqlite":
            return [dict(r) for r in rows]
        return rows

    def close(self):
        self._c.close()


class _Connection:
    def __init__(self, raw_conn):
        self._conn = raw_conn

    def cursor(self):
        return _Cursor(self._conn.cursor(), self._conn)

    def commit(self):
        self._conn.commit()

    def close(self):
        self._conn.close()


def get_connection():
    db_env_url = os.environ.get("DATABASE_URL", "sqlite:///database.db")

    if db_env_url.startswith("sqlite"):
        path = (
            db_env_url
            .replace("sqlite:///", "")
            .replace("sqlite://", "")
            .strip() or "database.db"
        )
        raw = sqlite3.connect(path, check_same_thread=False)
        raw.row_factory = sqlite3.Row
        raw.execute("PRAGMA journal_mode=WAL")
        raw.execute("PRAGMA foreign_keys=ON")
        return _Connection(raw)
    else:
        import psycopg2
        import psycopg2.extras
        if "pooler.supabase.com" in db_env_url:
            parsed = urlparse(db_env_url)
            if parsed.username and "postgres.cbbldgiifqsrgzpfrqxq" not in parsed.username:
                new_netloc = f"postgres.cbbldgiifqsrgzpfrqxq:{parsed.password}@{parsed.hostname}:{parsed.port}"
                parsed = parsed._replace(netloc=new_netloc)
                db_env_url = urlunparse(parsed)
        raw = psycopg2.connect(db_env_url, cursor_factory=psycopg2.extras.RealDictCursor)
        return _Connection(raw)
