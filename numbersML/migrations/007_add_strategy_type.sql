-- Migration: Add strategy_type and class_path to strategies table
-- Strategy type is an innate property (class-based vs config-based), not version-specific

-- Add strategy_type column with check constraint
ALTER TABLE strategies 
ADD COLUMN IF NOT EXISTS strategy_type TEXT DEFAULT 'config' NOT NULL;

-- Add check constraint for valid strategy types
ALTER TABLE strategies 
ADD CONSTRAINT strategies_strategy_type_check 
CHECK (strategy_type = ANY (ARRAY['config'::text, 'class'::text]));

-- Add class_path column for class-based strategies (NULL for config-based)
ALTER TABLE strategies 
ADD COLUMN IF NOT EXISTS class_path TEXT;

-- Add index for efficient queries by strategy type
CREATE INDEX IF NOT EXISTS idx_strategies_type ON strategies(strategy_type);

-- Add index for class_path lookups
CREATE INDEX IF NOT EXISTS idx_strategies_class_path ON strategies(class_path) 
WHERE class_path IS NOT NULL;

-- Update existing strategies: infer type from config if present
-- First, set all to 'config' as default
UPDATE strategies SET strategy_type = 'config' WHERE strategy_type IS NULL;

-- Update class_path for strategies that have it in their latest version config
-- This is a one-time migration to populate class_path from existing data
UPDATE strategies s
SET 
    strategy_type = 'class',
    class_path = v.config->>'class_path'
FROM strategy_versions v
WHERE s.id = v.strategy_id 
  AND v.is_active = true
  AND v.config->>'strategy_type' = 'class';

COMMENT ON COLUMN strategies.strategy_type IS 'Innate strategy type: config (JSON-based) or class (Python class-based)';
COMMENT ON COLUMN strategies.class_path IS 'Fully qualified class path for class-based strategies (e.g., src.strategies.user.grid1.Grid1Strategy)';
