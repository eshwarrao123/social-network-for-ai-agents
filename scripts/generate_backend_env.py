"""
Generate backend/.env safely from .env.example with cryptographically secure keys.
"""
import os
import secrets
from cryptography.fernet import Fernet

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
ENV_EXAMPLE = os.path.join(REPO_ROOT, "backend", ".env.example")
ENV_TARGET = os.path.join(REPO_ROOT, "backend", ".env")

def generate_env():
    if os.path.exists(ENV_TARGET):
        print(f"[+] backend/.env already exists at {ENV_TARGET}")
        return

    with open(ENV_EXAMPLE, "r", encoding="utf-8") as f:
        content = f.read()

    jwt_secret = secrets.token_hex(32)
    fernet_key = Fernet.generate_key().decode("utf-8")

    content = content.replace("change-me-to-a-random-256-bit-hex-string", jwt_secret)
    content = content.replace("change-me-to-a-valid-fernet-key", fernet_key)
    # Set installed LLM model
    content = content.replace("LLM_MODEL=llama3.2", "LLM_MODEL=qwen2.5-coder:1.5b")
    content = content.replace("REDIS_URL=redis://localhost:6379", "REDIS_URL=redis://127.0.0.1:6379?protocol=2")
    content = content.replace("DATABASE_URL=postgresql+asyncpg://asama:asama_pass@localhost:5432/asama_db", "DATABASE_URL=postgresql+asyncpg://asama:asama_pass@127.0.0.1:5432/asama_db")
    content = content.replace("DATABASE_URL_SYNC=postgresql+psycopg2://asama:asama_pass@localhost:5432/asama_db", "DATABASE_URL_SYNC=postgresql+psycopg2://asama:asama_pass@127.0.0.1:5432/asama_db")

    with open(ENV_TARGET, "w", encoding="utf-8") as f:
        f.write(content)

    print(f"[SUCCESS] Created secure backend/.env (JWT & Fernet encryption keys generated).")

if __name__ == "__main__":
    generate_env()
