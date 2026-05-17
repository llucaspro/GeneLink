from db.connection import get_connection, DB_TYPE

SCHEMA_POSTGRES = """
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    email VARCHAR(255) UNIQUE NOT NULL,
    username VARCHAR(100) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
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
    password_hash VARCHAR(255),
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
    created_by INTEGER,
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
    created_by INTEGER REFERENCES users(id),
    created_at TIMESTAMP DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS channel_messages (
    id SERIAL PRIMARY KEY,
    channel_id INTEGER REFERENCES institution_channels(id) ON DELETE CASCADE,
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    username VARCHAR(100) NOT NULL,
    content TEXT NOT NULL,
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
CREATE TABLE IF NOT EXISTS chat_messages (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    username VARCHAR(100) NOT NULL,
    message TEXT NOT NULL,
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
"""

SCHEMA_SQLITE = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT UNIQUE NOT NULL,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    full_name TEXT,
    institution TEXT,
    research_area TEXT,
    bio TEXT,
    avatar_initials TEXT,
    is_verified INTEGER DEFAULT 0,
    is_admin INTEGER DEFAULT 0,
    institution_id INTEGER,
    created_at TEXT DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS institutions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    short_name TEXT,
    cnpj TEXT UNIQUE,
    email TEXT,
    password_hash TEXT,
    description TEXT,
    website TEXT,
    email_domain TEXT,
    logo_initials TEXT,
    city TEXT,
    state TEXT,
    country TEXT DEFAULT 'Brasil',
    type TEXT DEFAULT 'Universidade',
    is_verified INTEGER DEFAULT 0,
    verified_at TEXT,
    member_count INTEGER DEFAULT 0,
    created_by INTEGER,
    created_at TEXT DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS institution_members (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    institution_id INTEGER REFERENCES institutions(id) ON DELETE CASCADE,
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    role TEXT DEFAULT 'member',
    joined_at TEXT DEFAULT (datetime('now')),
    UNIQUE(institution_id, user_id)
);
CREATE TABLE IF NOT EXISTS institution_channels (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    institution_id INTEGER REFERENCES institutions(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    description TEXT,
    is_public INTEGER DEFAULT 0,
    created_by INTEGER REFERENCES users(id),
    created_at TEXT DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS channel_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    channel_id INTEGER REFERENCES institution_channels(id) ON DELETE CASCADE,
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    username TEXT NOT NULL,
    content TEXT NOT NULL,
    created_at TEXT DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS posts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    content TEXT NOT NULL,
    category TEXT DEFAULT 'General',
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS comments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    post_id INTEGER REFERENCES posts(id) ON DELETE CASCADE,
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    content TEXT NOT NULL,
    created_at TEXT DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS chat_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    username TEXT NOT NULL,
    message TEXT NOT NULL,
    created_at TEXT DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS gene_searches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    query TEXT NOT NULL,
    result_count INTEGER DEFAULT 0,
    searched_at TEXT DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS partnerships (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    institution_id INTEGER REFERENCES institutions(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    description TEXT NOT NULL,
    type TEXT DEFAULT 'Vaga de Pesquisa',
    requirements TEXT,
    location TEXT,
    deadline TEXT,
    is_active INTEGER DEFAULT 1,
    created_at TEXT DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS partnership_applications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    partnership_id INTEGER REFERENCES partnerships(id) ON DELETE CASCADE,
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    message TEXT,
    status TEXT DEFAULT 'pending',
    applied_at TEXT DEFAULT (datetime('now')),
    UNIQUE(partnership_id, user_id)
);
CREATE TABLE IF NOT EXISTS research_library (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    institution_id INTEGER REFERENCES institutions(id) ON DELETE CASCADE,
    user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    title TEXT NOT NULL,
    content TEXT,
    category TEXT DEFAULT 'Dados de Pesquisa',
    is_public INTEGER DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS preprints (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    author_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    abstract TEXT NOT NULL,
    content TEXT NOT NULL,
    type TEXT NOT NULL DEFAULT 'Artigo Preliminar',
    status TEXT NOT NULL DEFAULT 'submitted',
    keywords TEXT,
    doi TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS preprint_reviews (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    preprint_id INTEGER REFERENCES preprints(id) ON DELETE CASCADE,
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    content TEXT NOT NULL,
    rating INTEGER,
    created_at TEXT DEFAULT (datetime('now'))
);
"""


def _run_migrations(cur):
    """Add new columns to existing tables safely."""
    new_cols_postgres = [
        ("users",        "is_verified",   "BOOLEAN DEFAULT FALSE"),
        ("users",        "is_admin",      "BOOLEAN DEFAULT FALSE"),
        ("users",        "institution_id","INTEGER"),
        ("institutions", "email",         "VARCHAR(255)"),
        ("institutions", "password_hash", "VARCHAR(255)"),
    ]
    new_cols_sqlite = [
        ("users",        "is_verified",   "INTEGER DEFAULT 0"),
        ("users",        "is_admin",      "INTEGER DEFAULT 0"),
        ("users",        "institution_id","INTEGER"),
        ("institutions", "email",         "TEXT"),
        ("institutions", "password_hash", "TEXT"),
    ]
    cols = new_cols_sqlite if DB_TYPE == "sqlite" else new_cols_postgres
    for table, col, coltype in cols:
        try:
            if DB_TYPE == "postgres":
                cur.execute(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {col} {coltype}")
            else:
                cur.execute(f"SELECT {col} FROM {table} LIMIT 1")
        except Exception:
            try:
                cur.execute(f"ALTER TABLE {table} ADD COLUMN {col} {coltype}")
            except Exception:
                pass


def init_db():
    try:
        conn = get_connection()
        cur = conn.cursor()
        schema = SCHEMA_SQLITE if DB_TYPE == "sqlite" else SCHEMA_POSTGRES
        for statement in schema.strip().split(";"):
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
        print(f"[GeneLink] Database initialized ({DB_TYPE}).")
    except Exception as e:
        print(f"[GeneLink] Database init error: {e}")
        raise


def _promote_default_admins(cur):
    """Promote default admin accounts on startup."""
    admin_emails = [
        "lucaspr1305@gmail.com",
    ]
    for email in admin_emails:
        try:
            if DB_TYPE == "postgres":
                cur.execute(
                    "UPDATE users SET is_admin = TRUE WHERE email = %s",
                    (email,)
                )
            else:
                cur.execute(
                    "UPDATE users SET is_admin = 1 WHERE email = ?",
                    (email,)
                )
        except Exception as e:
            print(f"[GeneLink] Admin promotion warning for {email}: {e}")
