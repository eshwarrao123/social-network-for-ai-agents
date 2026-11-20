"""
Initialize, start, and verify PostgreSQL 16 + pgvector for Agent Network.
Runs strictly on 127.0.0.1:5432 without administrative privileges.
"""
import os
import sys
import subprocess
import time

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
INFRA_DIR = os.path.join(REPO_ROOT, "infrastructure")
PG_DIR = os.path.join(INFRA_DIR, "pgsql")
PG_BIN = os.path.join(PG_DIR, "pgsql", "bin")
PG_DATA = os.path.join(PG_DIR, "data")
PG_LOG = os.path.join(PG_DIR, "pg_server.log")


def run_cmd(cmd, desc, env=None, check=True):
    print(f"[*] Running: {desc}...")
    res = subprocess.run(cmd, capture_output=True, text=True, env=env)
    if res.returncode != 0 and check:
        print(f"[FAIL] {desc} returned code {res.returncode}")
        print("STDOUT:", res.stdout)
        print("STDERR:", res.stderr)
        raise RuntimeError(f"{desc} failed")
    return res.stdout, res.stderr


def init_and_start_postgres():
    initdb_exe = os.path.join(PG_BIN, "initdb.exe")
    pg_ctl_exe = os.path.join(PG_BIN, "pg_ctl.exe")
    psql_exe = os.path.join(PG_BIN, "psql.exe")

    # 1. Initialize cluster if data dir doesn't exist
    if not os.path.exists(os.path.join(PG_DATA, "PG_VERSION")):
        print(f"[*] Initializing PostgreSQL cluster at {PG_DATA}...")
        run_cmd(
            [initdb_exe, "-D", PG_DATA, "-U", "postgres", "-A", "trust", "-E", "UTF8", "--no-locale"],
            "initdb"
        )
    else:
        print(f"[+] Cluster already initialized at {PG_DATA}")

    # 2. Check if postgres is already running
    status_out, _ = run_cmd([pg_ctl_exe, "-D", PG_DATA, "status"], "check status", check=False)
    if "server is running" not in status_out:
        print("[*] Starting PostgreSQL server on 127.0.0.1:5432...")
        run_cmd(
            [pg_ctl_exe, "-D", PG_DATA, "-l", PG_LOG, "-o", "-p 5432 -h 127.0.0.1", "start"],
            "pg_ctl start"
        )
        time.sleep(2)
    else:
        print("[+] PostgreSQL server is already running")

    # 3. Create user and database
    # Check if user asama exists
    out, _ = run_cmd(
        [psql_exe, "-U", "postgres", "-h", "127.0.0.1", "-p", "5432", "-t", "-c", "SELECT 1 FROM pg_roles WHERE rolname='asama';"],
        "check user asama"
    )
    if "1" not in out:
        print("[*] Creating user asama...")
        run_cmd(
            [psql_exe, "-U", "postgres", "-h", "127.0.0.1", "-p", "5432", "-c", "CREATE USER asama WITH PASSWORD 'asama_pass'; ALTER USER asama WITH SUPERUSER;"],
            "create user asama"
        )
    else:
        print("[+] User asama exists. Ensuring password and superuser privilege...")
        run_cmd(
            [psql_exe, "-U", "postgres", "-h", "127.0.0.1", "-p", "5432", "-c", "ALTER USER asama WITH PASSWORD 'asama_pass'; ALTER USER asama WITH SUPERUSER;"],
            "update user asama"
        )

    # Check if database asama_db exists
    out, _ = run_cmd(
        [psql_exe, "-U", "postgres", "-h", "127.0.0.1", "-p", "5432", "-t", "-c", "SELECT 1 FROM pg_database WHERE datname='asama_db';"],
        "check db asama_db"
    )
    if "1" not in out:
        print("[*] Creating database asama_db...")
        run_cmd(
            [psql_exe, "-U", "postgres", "-h", "127.0.0.1", "-p", "5432", "-c", "CREATE DATABASE asama_db OWNER asama;"],
            "create db asama_db"
        )
    else:
        print("[+] Database asama_db exists")

    # 4. Enable vector extension in asama_db
    print("[*] Enabling pgvector extension in asama_db...")
    run_cmd(
        [psql_exe, "-U", "asama", "-h", "127.0.0.1", "-p", "5432", "-d", "asama_db", "-c", "CREATE EXTENSION IF NOT EXISTS vector;"],
        "create extension vector"
    )

    # 5. Verify pgvector extension
    out, _ = run_cmd(
        [psql_exe, "-U", "asama", "-h", "127.0.0.1", "-p", "5432", "-d", "asama_db", "-t", "-c", "SELECT extname, extversion FROM pg_extension WHERE extname = 'vector';"],
        "verify extension"
    )
    print(f"[+] Installed pgvector version: {out.strip()}")

    # 6. Verify 768-d vector and HNSW cosine index
    print("[*] Verifying 768-dimension vector and HNSW cosine index...")
    test_sql = """
    DROP TABLE IF EXISTS test_hnsw_probe;
    CREATE TABLE test_hnsw_probe (id serial primary key, embedding vector(768));
    CREATE INDEX test_hnsw_idx ON test_hnsw_probe USING hnsw (embedding vector_cosine_ops) WITH (m = 16, ef_construction = 64);
    INSERT INTO test_hnsw_probe (embedding) VALUES ('[0.1, 0.2, 0.3, ...]'::vector(768)) -- test parsing failsafe or dummy
    """
    # Create valid 768-d dummy array
    dummy_vec = "[" + ", ".join(["0.01"] * 768) + "]"
    verify_script = f"""
    DROP TABLE IF EXISTS test_hnsw_probe;
    CREATE TABLE test_hnsw_probe (id serial primary key, embedding vector(768));
    CREATE INDEX test_hnsw_idx ON test_hnsw_probe USING hnsw (embedding vector_cosine_ops) WITH (m = 16, ef_construction = 64);
    INSERT INTO test_hnsw_probe (embedding) VALUES ('{dummy_vec}');
    SELECT id, embedding <-> '{dummy_vec}' as distance FROM test_hnsw_probe;
    DROP TABLE test_hnsw_probe;
    """
    out, _ = run_cmd(
        [psql_exe, "-U", "asama", "-h", "127.0.0.1", "-p", "5432", "-d", "asama_db", "-c", verify_script],
        "test HNSW vector cosine index"
    )
    print("[+] Vector and HNSW test output:")
    print(out.strip())
    print("\n[SUCCESS] PostgreSQL 16 and pgvector verified and fully operational!")


if __name__ == "__main__":
    init_and_start_postgres()
