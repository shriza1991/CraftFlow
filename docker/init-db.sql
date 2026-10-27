-- Initialize vector extension on default development database
CREATE EXTENSION IF NOT EXISTS vector;

-- Create isolated test database for running pytest test suites without affecting development data
SELECT 'CREATE DATABASE ages_art_db_test'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'ages_art_db_test')\gexec

-- Enable vector extension on the test database
\c ages_art_db_test
CREATE EXTENSION IF NOT EXISTS vector;
