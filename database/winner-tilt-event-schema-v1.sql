-- Winner Tilt AI Research Engine schema v1.0
CREATE TABLE research_event_types (
  event_type VARCHAR(40) PRIMARY KEY,
  name VARCHAR(120) NOT NULL,
  default_weight DECIMAL(8,4) NOT NULL,
  description TEXT NOT NULL,
  registry_version VARCHAR(20) NOT NULL
);

CREATE TABLE research_events (
  event_id VARCHAR(80) PRIMARY KEY,
  event_version INTEGER NOT NULL DEFAULT 1,
  supersedes_event_id VARCHAR(80) NULL REFERENCES research_events(event_id),
  event_type VARCHAR(40) NOT NULL REFERENCES research_event_types(event_type),
  title TEXT NOT NULL,
  summary TEXT NULL,
  direction VARCHAR(12) NOT NULL CHECK (direction IN ('POSITIVE','NEGATIVE','NEUTRAL','MIXED','UNKNOWN')),
  severity INTEGER NOT NULL CHECK (severity BETWEEN 1 AND 5),
  confidence DECIMAL(6,5) NOT NULL CHECK (confidence BETWEEN 0 AND 1),
  event_time TIMESTAMP WITH TIME ZONE NOT NULL,
  published_at TIMESTAMP WITH TIME ZONE NOT NULL,
  ingested_at TIMESTAMP WITH TIME ZONE NOT NULL,
  source_name VARCHAR(240) NOT NULL,
  source_tier VARCHAR(30) NOT NULL,
  source_url TEXT NULL,
  source_external_id VARCHAR(240) NULL,
  unverified BOOLEAN NOT NULL DEFAULT FALSE,
  canonical_fingerprint CHAR(64) NOT NULL UNIQUE,
  raw_payload_sha256 CHAR(64) NULL,
  created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CHECK (ingested_at >= published_at)
);

CREATE TABLE event_security_links (
  event_id VARCHAR(80) NOT NULL REFERENCES research_events(event_id),
  security_id VARCHAR(40) NOT NULL REFERENCES securities(security_id),
  relation_type VARCHAR(30) NOT NULL DEFAULT 'DIRECT',
  relevance DECIMAL(6,5) NOT NULL DEFAULT 1.0 CHECK (relevance BETWEEN 0 AND 1),
  PRIMARY KEY (event_id, security_id)
);

CREATE TABLE research_runs (
  research_run_id VARCHAR(80) PRIMARY KEY,
  engine_version VARCHAR(20) NOT NULL,
  configuration_sha256 CHAR(64) NOT NULL,
  information_cutoff TIMESTAMP WITH TIME ZONE NOT NULL,
  lookback_start TIMESTAMP WITH TIME ZONE NOT NULL,
  accepted_event_count INTEGER NOT NULL,
  rejected_event_count INTEGER NOT NULL,
  duplicate_event_count INTEGER NOT NULL,
  output_sha256 CHAR(64) NOT NULL,
  created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE research_security_summaries (
  research_run_id VARCHAR(80) NOT NULL REFERENCES research_runs(research_run_id),
  security_id VARCHAR(40) NOT NULL REFERENCES securities(security_id),
  research_signal DECIMAL(10,6) NOT NULL,
  context_label VARCHAR(30) NOT NULL,
  positive_count INTEGER NOT NULL,
  negative_count INTEGER NOT NULL,
  neutral_count INTEGER NOT NULL,
  mixed_count INTEGER NOT NULL,
  highest_severity INTEGER NULL,
  highest_severity_event_id VARCHAR(80) NULL REFERENCES research_events(event_id),
  PRIMARY KEY (research_run_id, security_id)
);

CREATE INDEX idx_research_events_published_at ON research_events(published_at);
CREATE INDEX idx_event_security_links_security ON event_security_links(security_id, event_id);
