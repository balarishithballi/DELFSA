-- DELFSA initial schema: incident/asset metadata store
-- Executed automatically by the official postgres entrypoint on first boot.

CREATE TABLE IF NOT EXISTS assets (
    id SERIAL PRIMARY KEY,
    hostname VARCHAR(255) NOT NULL UNIQUE,
    ip_address INET,
    asset_type VARCHAR(64) NOT NULL,
    zone VARCHAR(64) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS incidents (
    id SERIAL PRIMARY KEY,
    incident_id VARCHAR(64) NOT NULL UNIQUE,
    correlation_key VARCHAR(255) NOT NULL,
    severity VARCHAR(16) NOT NULL,
    triggering_rule_id VARCHAR(64),
    mitre_attack_id VARCHAR(16),
    alert_count_in_window INTEGER NOT NULL DEFAULT 0,
    status VARCHAR(32) NOT NULL DEFAULT 'open',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    resolved_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_incidents_status ON incidents(status);
CREATE INDEX IF NOT EXISTS idx_incidents_created_at ON incidents(created_at);

CREATE TABLE IF NOT EXISTS scenario_runs (
    id SERIAL PRIMARY KEY,
    scenario_name VARCHAR(128) NOT NULL,
    started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at TIMESTAMPTZ,
    status VARCHAR(32) NOT NULL DEFAULT 'running'
);
