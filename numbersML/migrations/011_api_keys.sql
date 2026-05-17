-- Migration: 011_api_keys.sql
-- Database schema for API key management

CREATE TABLE api_keys (
    id UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
    name TEXT NOT NULL,
    environment TEXT NOT NULL CHECK (environment IN ('mainnet', 'testnet')),
    api_key_encrypted BYTEA NOT NULL,
    api_secret_encrypted BYTEA NOT NULL,
    is_active BOOLEAN DEFAULT true,
    permissions JSONB DEFAULT '{}',
    ip_whitelist TEXT[],
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    last_used_at TIMESTAMPTZ,
    created_by TEXT DEFAULT 'system'
);

-- Never expose encrypted values in queries
CREATE OR REPLACE VIEW api_keys_public AS
SELECT id, name, environment, is_active, permissions, ip_whitelist,
       created_at, updated_at, last_used_at, created_by
FROM api_keys;

-- Index for environment filtering
CREATE INDEX idx_api_keys_environment ON api_keys(environment);

-- Index for active keys
CREATE INDEX idx_api_keys_is_active ON api_keys(is_active);
