import os
import psycopg2
import psycopg2.extras


DATABASE_URL = os.environ.get("DATABASE_URL", "")


def get_connection():
    """Return a psycopg2 connection using DATABASE_URL (PostgreSQL only)."""
    if not DATABASE_URL:
        raise RuntimeError(
            "DATABASE_URL environment variable is not set. "
            "Set it to your PostgreSQL connection string."
        )
    conn = psycopg2.connect(DATABASE_URL, cursor_factory=psycopg2.extras.RealDictCursor)
    return conn
