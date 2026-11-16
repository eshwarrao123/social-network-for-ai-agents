-- =================================================================
-- Asama.ai PostgreSQL Setup Script
-- Run as postgres superuser to create DB, user, and pgvector extension
-- =================================================================

-- 1. Create database user
CREATE USER asama WITH PASSWORD 'asama_pass';

-- 2. Create database
CREATE DATABASE asama_db OWNER asama;

-- 3. Connect to the new database, then enable pgvector
\c asama_db

-- 4. Enable pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;

-- 5. Grant privileges
GRANT ALL PRIVILEGES ON DATABASE asama_db TO asama;
GRANT ALL ON SCHEMA public TO asama;

-- Verify
SELECT extname, extversion FROM pg_extension WHERE extname = 'vector';
