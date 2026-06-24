from db.connection import get_connection

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    firebase_uid VARCHAR(128) UNIQUE,
    email VARCHAR(255) UNIQUE NOT NULL,
    username VARCHAR(100) UNIQUE NOT NULL,
    full_name VARCHAR(255),
    institution VARCHAR(255),
    research_area VARCHAR(255),
    bio TEXT,
    avatar_initials VARCHAR(4),
    is_verified BOOLEAN DEFAULT FALSE,
    is_admin BOOLEAN DEFAULT FALSE,
    institution_id INTEGER,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS institutions (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    short_name VARCHAR(100),
    cnpj VARCHAR(20) UNIQUE,
    email VARCHAR(255),
    description TEXT,
    website VARCHAR(500),
    email_domain VARCHAR(255),
    logo_initials VARCHAR(4),
    city VARCHAR(100),
    state VARCHAR(50),
    country VARCHAR(100) DEFAULT 'Brasil',
    type VARCHAR(100) DEFAULT 'Universidade',
    is_verified BOOLEAN DEFAULT FALSE,
    verified_at TIMESTAMP,
    member_count INTEGER DEFAULT 0,
    created_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS institution_members (
    id SERIAL PRIMARY KEY,
    institution_id INTEGER REFERENCES institutions(id) ON DELETE CASCADE,
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    role VARCHAR(50) DEFAULT 'member',
    joined_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(institution_id, user_id)
);

CREATE TABLE IF NOT EXISTS institution_channels (
    id SERIAL PRIMARY KEY,
    institution_id INTEGER REFERENCES institutions(id) ON DELETE CASCADE,
    name VARCHAR(100) NOT NULL,
    description TEXT,
    is_public BOOLEAN DEFAULT FALSE,
    created_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS posts (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    title VARCHAR(500) NOT NULL,
    content TEXT NOT NULL,
    category VARCHAR(100) DEFAULT 'General',
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS comments (
    id SERIAL PRIMARY KEY,
    post_id INTEGER REFERENCES posts(id) ON DELETE CASCADE,
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    content TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS gene_searches (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    query VARCHAR(500) NOT NULL,
    result_count INTEGER DEFAULT 0,
    searched_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS partnerships (
    id SERIAL PRIMARY KEY,
    institution_id INTEGER REFERENCES institutions(id) ON DELETE CASCADE,
    title VARCHAR(500) NOT NULL,
    description TEXT NOT NULL,
    type VARCHAR(100) DEFAULT 'Vaga de Pesquisa',
    requirements TEXT,
    location VARCHAR(255),
    deadline DATE,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS partnership_applications (
    id SERIAL PRIMARY KEY,
    partnership_id INTEGER REFERENCES partnerships(id) ON DELETE CASCADE,
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    message TEXT,
    status VARCHAR(50) DEFAULT 'pending',
    applied_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(partnership_id, user_id)
);

CREATE TABLE IF NOT EXISTS research_library (
    id SERIAL PRIMARY KEY,
    institution_id INTEGER REFERENCES institutions(id) ON DELETE CASCADE,
    user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    title VARCHAR(500) NOT NULL,
    content TEXT,
    category VARCHAR(100) DEFAULT 'Dados de Pesquisa',
    is_public BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS preprints (
    id SERIAL PRIMARY KEY,
    author_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    title VARCHAR(500) NOT NULL,
    abstract TEXT NOT NULL,
    content TEXT NOT NULL,
    type VARCHAR(100) NOT NULL DEFAULT 'Artigo Preliminar',
    status VARCHAR(50) NOT NULL DEFAULT 'submitted',
    keywords VARCHAR(500),
    doi VARCHAR(255),
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS preprint_reviews (
    id SERIAL PRIMARY KEY,
    preprint_id INTEGER REFERENCES preprints(id) ON DELETE CASCADE,
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    content TEXT NOT NULL,
    rating INTEGER,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS admin_flags (
    id SERIAL PRIMARY KEY,
    type VARCHAR(50) NOT NULL,
    content TEXT NOT NULL,
    sender_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    reference_id INTEGER,
    reason TEXT,
    resolved BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT NOW()
);
"""

MIGRATIONS_SQL = [
    ("users", "firebase_uid", "VARCHAR(128)"),
    ("users", "is_verified", "BOOLEAN DEFAULT FALSE"),
    ("users", "is_admin", "BOOLEAN DEFAULT FALSE"),
    ("users", "institution_id", "INTEGER"),
]


def _run_migrations(cur):
    """Add new columns to existing tables safely (idempotent)."""
    for table, col, coltype in MIGRATIONS_SQL:
        try:
            cur.execute(
                f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {col} {coltype}"
            )
        except Exception as e:
            print(f"[GeneLink] Migration warning ({table}.{col}): {e}")


def _promote_default_admins(cur):
    """Promote default admin accounts on startup."""
    admin_emails = [
        "lucaspr1305@gmail.com",
    ]
    for email in admin_emails:
        try:
            cur.execute(
                "UPDATE users SET is_admin = TRUE WHERE email = %s", (email,)
            )
        except Exception as e:
            print(f"[GeneLink] Admin promotion warning for {email}: {e}")


def init_db():
    try:
        conn = get_connection()
        cur = conn.cursor()
        for statement in SCHEMA_SQL.strip().split(";"):
            stmt = statement.strip()
            if stmt:
                try:
                    cur.execute(stmt)
                except Exception as e:
                    msg = str(e).lower()
                    if "already exists" not in msg and "duplicate" not in msg:
                        print(f"[GeneLink] Schema warning: {e}")
        _run_migrations(cur)
        _promote_default_admins(cur)
        conn.commit()
        cur.close()
        conn.close()
        print("[GeneLink] PostgreSQL database initialized.")
    except Exception as e:
        print(f"[GeneLink] Database init error: {e}")
        raise
