-- Winner Tilt AI Backtest Schema v2.0
CREATE TABLE IF NOT EXISTS backtest_runs (
  backtest_run_id text PRIMARY KEY,
  engine_version text NOT NULL,
  configuration_sha256 text NOT NULL,
  data_manifest_sha256 text NOT NULL,
  started_at timestamptz NOT NULL,
  completed_at timestamptz,
  validation_status text NOT NULL CHECK (validation_status IN ('VALIDATION_ONLY','PRODUCTION_VALID','FAILED')),
  start_date date NOT NULL,
  end_date date NOT NULL,
  initial_capital numeric NOT NULL CHECK (initial_capital > 0)
);
CREATE TABLE IF NOT EXISTS backtest_rebalances (
  backtest_run_id text REFERENCES backtest_runs(backtest_run_id),
  rebalance_date date NOT NULL,
  information_cutoff date NOT NULL CHECK (information_cutoff <= rebalance_date),
  one_way_turnover numeric NOT NULL,
  transaction_cost numeric NOT NULL,
  holdings jsonb NOT NULL,
  PRIMARY KEY (backtest_run_id, rebalance_date)
);
CREATE TABLE IF NOT EXISTS backtest_transactions (
  backtest_run_id text REFERENCES backtest_runs(backtest_run_id),
  transaction_seq bigint NOT NULL,
  trade_date date NOT NULL,
  security_id text NOT NULL,
  side text NOT NULL CHECK (side IN ('BUY','SELL')),
  quantity numeric NOT NULL,
  execution_price numeric NOT NULL CHECK (execution_price > 0),
  notional numeric NOT NULL,
  transaction_cost numeric NOT NULL,
  score_cutoff date NOT NULL CHECK (score_cutoff <= trade_date),
  PRIMARY KEY (backtest_run_id, transaction_seq)
);
CREATE TABLE IF NOT EXISTS backtest_equity_curve (
  backtest_run_id text REFERENCES backtest_runs(backtest_run_id),
  valuation_date date NOT NULL,
  portfolio_value numeric NOT NULL,
  benchmark_value numeric,
  cash numeric NOT NULL,
  PRIMARY KEY (backtest_run_id, valuation_date)
);
CREATE TABLE IF NOT EXISTS backtest_integrity_checks (
  backtest_run_id text REFERENCES backtest_runs(backtest_run_id),
  check_code text NOT NULL,
  passed boolean NOT NULL,
  details jsonb,
  PRIMARY KEY (backtest_run_id, check_code)
);
