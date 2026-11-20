"""
Automated Local Infrastructure Provisioner for Agent Network (P10.1)
Provisions:
  1. PostgreSQL 16 (portable x64)
  2. pgvector v0.8.6 extension for PG16
  3. Redis 5.0.14.1 (portable x64 with Redis Streams)
All components run strictly in user-space on localhost without requiring UAC/admin privileges.
"""
import os
import sys
import zipfile
import subprocess
import urllib.request
import shutil
import time

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
INFRA_DIR = os.path.join(REPO_ROOT, "infrastructure")
PG_DIR = os.path.join(INFRA_DIR, "pgsql")
REDIS_DIR = os.path.join(INFRA_DIR, "redis")

PG_URL = "https://get.enterprisedb.com/postgresql/postgresql-16.16-2-windows-x64-binaries.zip"
PGVECTOR_URL = "https://github.com/andreiramani/pgvector_pgsql_windows/releases/download/0.8.6_16/vector.v0.8.6-pg16.zip"
REDIS_URL = "https://github.com/tporadowski/redis/releases/download/v5.0.14.1/Redis-x64-5.0.14.1.zip"


def download_file(url: str, dest_path: str, desc: str):
    print(f"[*] Downloading {desc} from {url}...")
    headers = {"User-Agent": "Mozilla/5.0"}
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req) as resp, open(dest_path, "wb") as out_file:
        total_size = int(resp.getheader("Content-Length", 0))
        downloaded = 0
        chunk_size = 1024 * 1024  # 1 MB
        last_pct = 0
        while True:
            chunk = resp.read(chunk_size)
            if not chunk:
                break
            out_file.write(chunk)
            downloaded += len(chunk)
            if total_size > 0:
                pct = int((downloaded / total_size) * 100)
                if pct >= last_pct + 10:
                    print(f"    {desc}: {pct}% ({downloaded // (1024*1024)}MB / {total_size // (1024*1024)}MB)")
                    last_pct = pct
    print(f"[+] Download completed: {dest_path} ({os.path.getsize(dest_path)} bytes)")


def extract_zip(zip_path: str, target_dir: str, desc: str):
    print(f"[*] Extracting {desc} to {target_dir}...")
    os.makedirs(target_dir, exist_ok=True)
    with zipfile.ZipFile(zip_path, "r") as zf:
        zf.extractall(target_dir)
    print(f"[+] Extraction complete for {desc}")


def setup_redis():
    print("\n=== STEP 1: Setting up Redis 5.0.14.1 ===")
    os.makedirs(REDIS_DIR, exist_ok=True)
    redis_exe = os.path.join(REDIS_DIR, "redis-server.exe")
    if os.path.exists(redis_exe):
        print(f"[+] Redis already present at {redis_exe}")
        return redis_exe

    zip_path = os.path.join(REDIS_DIR, "redis.zip")
    download_file(REDIS_URL, zip_path, "Redis 5.0.14.1 portable")
    extract_zip(zip_path, REDIS_DIR, "Redis")
    if os.path.exists(zip_path):
        os.remove(zip_path)
    return redis_exe


def setup_postgresql_and_pgvector():
    print("\n=== STEP 2: Setting up PostgreSQL 16 + pgvector ===")
    os.makedirs(PG_DIR, exist_ok=True)
    pg_bin_dir = os.path.join(PG_DIR, "pgsql", "bin")
    initdb_exe = os.path.join(pg_bin_dir, "initdb.exe")

    if not os.path.exists(initdb_exe):
        pg_zip = os.path.join(PG_DIR, "postgresql.zip")
        download_file(PG_URL, pg_zip, "PostgreSQL 16.16-2 x64 binaries")
        extract_zip(pg_zip, PG_DIR, "PostgreSQL")
        if os.path.exists(pg_zip):
            os.remove(pg_zip)

    # Check pgvector
    lib_dir = os.path.join(PG_DIR, "pgsql", "lib")
    ext_dir = os.path.join(PG_DIR, "pgsql", "share", "extension")
    vector_dll = os.path.join(lib_dir, "vector.dll")

    if not os.path.exists(vector_dll):
        pgv_zip = os.path.join(PG_DIR, "pgvector.zip")
        download_file(PGVECTOR_URL, pgv_zip, "pgvector 0.8.6 for PG16")
        pgv_temp = os.path.join(PG_DIR, "pgv_temp")
        extract_zip(pgv_zip, pgv_temp, "pgvector temp")

        # Copy vector.dll to lib/ and control/sql to share/extension/
        for root, dirs, files in os.walk(pgv_temp):
            for f in files:
                full_path = os.path.join(root, f)
                if f == "vector.dll":
                    shutil.copy2(full_path, vector_dll)
                    print(f"[+] Installed vector.dll -> {vector_dll}")
                elif f.startswith("vector.") or f.startswith("vector--"):
                    dest = os.path.join(ext_dir, f)
                    shutil.copy2(full_path, dest)
                    print(f"[+] Installed extension file -> {dest}")

        shutil.rmtree(pgv_temp, ignore_errors=True)
        if os.path.exists(pgv_zip):
            os.remove(pgv_zip)

    print(f"[+] PostgreSQL and pgvector installed at {PG_DIR}")
    return pg_bin_dir


if __name__ == "__main__":
    setup_redis()
    setup_postgresql_and_pgvector()
    print("\n[SUCCESS] Local infrastructure binaries successfully staged.")
