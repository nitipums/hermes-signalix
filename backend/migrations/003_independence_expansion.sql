-- backend/migrations/003_independence_expansion.sql
ALTER TABLE company_profiles ADD COLUMN IF NOT EXISTS shares_outstanding BIGINT;
ALTER TABLE company_profiles ADD COLUMN IF NOT EXISTS market_cap BIGINT;
ALTER TABLE company_profiles ADD COLUMN IF NOT EXISTS free_float_pct NUMERIC(5,2);
ALTER TABLE company_profiles ADD COLUMN IF NOT EXISTS foreign_limit_pct NUMERIC(5,2);
CREATE INDEX IF NOT EXISTS idx_company_profiles_market_cap ON company_profiles (market_cap);
CREATE INDEX IF NOT EXISTS idx_company_profiles_free_float ON company_profiles (free_float_pct);