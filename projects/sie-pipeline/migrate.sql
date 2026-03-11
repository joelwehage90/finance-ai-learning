-- SIE Pipeline: Supabase database migration
-- Run this in Supabase SQL Editor to create all tables.
--
-- Design principles:
--   - NUMERIC(15,2) for all amounts (never float)
--   - Multi-tenant via tenant_id on every table
--   - Composite primary keys matching SIE data identifiers
--   - UPSERT-friendly PKs for idempotent syncing

-- Enable UUID generation
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ============================================================
-- TENANTS — company/customer master data
-- ============================================================
CREATE TABLE IF NOT EXISTS tenants (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name            TEXT NOT NULL,
    org_number      TEXT,
    fortnox_client_id     TEXT,
    fortnox_client_secret TEXT,
    fortnox_tenant_id     TEXT,
    created_at      TIMESTAMPTZ DEFAULT now()
);

-- ============================================================
-- ACCOUNTS — chart of accounts (BAS-kontoplan)
-- ============================================================
CREATE TABLE IF NOT EXISTS accounts (
    tenant_id       UUID NOT NULL REFERENCES tenants(id),
    account_number  INT NOT NULL,
    name            TEXT NOT NULL,
    account_type    CHAR(1),          -- T=Tillgang, S=Skuld, K=Kostnad, I=Intakt
    active          BOOLEAN DEFAULT true,
    sru_code        INT,
    PRIMARY KEY (tenant_id, account_number)
);

-- ============================================================
-- FINANCIAL_YEARS — fiscal year definitions
-- ============================================================
CREATE TABLE IF NOT EXISTS financial_years (
    tenant_id       UUID NOT NULL REFERENCES tenants(id),
    year_id         INT NOT NULL,      -- e.g. 2026
    start_date      DATE NOT NULL,
    end_date        DATE NOT NULL,
    PRIMARY KEY (tenant_id, year_id)
);

-- ============================================================
-- DIMENSIONS — cost centers, projects (from SIE #DIM / #OBJEKT)
-- ============================================================
CREATE TABLE IF NOT EXISTS dimensions (
    tenant_id       UUID NOT NULL REFERENCES tenants(id),
    dimension_id    INT NOT NULL,      -- 1=cost center, 6=project, etc.
    object_id       TEXT NOT NULL,     -- e.g. "SALJ", "PROD", "PROJ1"
    name            TEXT NOT NULL,
    PRIMARY KEY (tenant_id, dimension_id, object_id)
);

-- ============================================================
-- VOUCHERS — verification headers (from SIE #VER)
-- ============================================================
CREATE TABLE IF NOT EXISTS vouchers (
    tenant_id       UUID NOT NULL REFERENCES tenants(id),
    series          TEXT NOT NULL,      -- A, B, C, etc.
    number          INT NOT NULL,
    year_id         INT NOT NULL,
    date            DATE NOT NULL,
    description     TEXT,
    synced_at       TIMESTAMPTZ DEFAULT now(),
    PRIMARY KEY (tenant_id, series, number, year_id)
);

-- ============================================================
-- TRANSACTIONS — voucher rows (from SIE #TRANS)
-- ============================================================
CREATE TABLE IF NOT EXISTS transactions (
    id              BIGSERIAL PRIMARY KEY,
    tenant_id       UUID NOT NULL,
    voucher_series  TEXT NOT NULL,
    voucher_number  INT NOT NULL,
    year_id         INT NOT NULL,
    account_number  INT NOT NULL,
    amount          NUMERIC(15,2) NOT NULL,  -- positive=debit, negative=credit
    cost_center     TEXT,
    project         TEXT,
    transaction_info TEXT,
    FOREIGN KEY (tenant_id, voucher_series, voucher_number, year_id)
        REFERENCES vouchers(tenant_id, series, number, year_id),
    FOREIGN KEY (tenant_id, account_number)
        REFERENCES accounts(tenant_id, account_number)
);

-- ============================================================
-- PERIOD_BALANCES — pre-aggregated balances (from SIE #PSALDO, #IB, #UB, #RES)
-- ============================================================
CREATE TABLE IF NOT EXISTS period_balances (
    tenant_id       UUID NOT NULL REFERENCES tenants(id),
    account_number  INT NOT NULL,
    period          TEXT NOT NULL,      -- "2026-01", "2026-IB", "2026-UB", "2026-RES"
    cost_center     TEXT DEFAULT '*',
    project         TEXT DEFAULT '*',
    amount          NUMERIC(15,2) NOT NULL,
    balance_type    TEXT NOT NULL,      -- 'period', 'opening', 'closing', 'result'
    synced_at       TIMESTAMPTZ DEFAULT now(),
    PRIMARY KEY (tenant_id, account_number, period, cost_center, project)
);

-- ============================================================
-- SYNC_STATE — tracks sync status per entity
-- ============================================================
CREATE TABLE IF NOT EXISTS sync_state (
    tenant_id       UUID NOT NULL REFERENCES tenants(id),
    entity_type     TEXT NOT NULL,      -- 'sie4', 'invoices', etc.
    last_sync       TIMESTAMPTZ,
    last_full_sync  TIMESTAMPTZ,
    records_synced  INT,
    status          TEXT DEFAULT 'idle', -- 'idle', 'running', 'error'
    error_message   TEXT,
    PRIMARY KEY (tenant_id, entity_type)
);

-- ============================================================
-- BUDGET — period budgets (from SIE #PBUDGET)
-- ============================================================
CREATE TABLE IF NOT EXISTS budget (
    tenant_id       UUID NOT NULL REFERENCES tenants(id),
    account_number  INT NOT NULL,
    period          TEXT NOT NULL,      -- "2026-01"
    cost_center     TEXT DEFAULT '*',
    amount          NUMERIC(15,2) NOT NULL,
    PRIMARY KEY (tenant_id, account_number, period, cost_center)
);

-- ============================================================
-- FUNCTIONAL_PNL_MAPPING — maps accounts + cost centers to functions
-- ============================================================
CREATE TABLE IF NOT EXISTS functional_pnl_mapping (
    tenant_id           UUID NOT NULL REFERENCES tenants(id),
    account_range_from  INT NOT NULL,
    account_range_to    INT NOT NULL,
    cost_center         TEXT DEFAULT '*',
    function_id         TEXT NOT NULL,   -- 'cogs', 'selling', 'admin', etc.
    function_label      TEXT NOT NULL,
    sort_order          INT,
    PRIMARY KEY (tenant_id, account_range_from, account_range_to, cost_center)
);

-- ============================================================
-- INDEXES for performance
-- ============================================================
CREATE INDEX IF NOT EXISTS idx_transactions_account
    ON transactions(tenant_id, account_number);

CREATE INDEX IF NOT EXISTS idx_transactions_year
    ON transactions(tenant_id, year_id);

CREATE INDEX IF NOT EXISTS idx_vouchers_date
    ON vouchers(tenant_id, date);

CREATE INDEX IF NOT EXISTS idx_period_balances_period
    ON period_balances(tenant_id, period);
