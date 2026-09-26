-- Smart Click: Deals page + Categories page admin controls (Sept 2026)
-- Run ONCE against your database (local psql, or Neon's SQL Editor).
-- Safe to re-run: every statement is idempotent.

-- Hand-picked Flash Deals (Admin > Products > Edit > "Pin to Flash Deals")
ALTER TABLE products ADD COLUMN IF NOT EXISTS is_flash_deal BOOLEAN NOT NULL DEFAULT false;

-- Admin-controlled category order (Admin > Manage Categories > up/down arrows)
ALTER TABLE categories ADD COLUMN IF NOT EXISTS sort_order INTEGER NOT NULL DEFAULT 0;

-- Start the order off alphabetically (matches how categories showed before),
-- only if nobody has reordered yet.
UPDATE categories c
SET sort_order = ranked.rn
FROM (SELECT id, ROW_NUMBER() OVER (ORDER BY name) AS rn FROM categories) ranked
WHERE c.id = ranked.id
  AND NOT EXISTS (SELECT 1 FROM categories WHERE sort_order <> 0);
