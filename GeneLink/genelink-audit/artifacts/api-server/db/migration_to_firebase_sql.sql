-- =============================================================================
-- GeneLink — Migration Script: Add Firebase UID support to existing DB
-- Run this against your existing PostgreSQL database.
-- Safe to run multiple times (IF NOT EXISTS / ON CONFLICT).
-- =============================================================================

-- 1. Add firebase_uid column to users
ALTER TABLE users
  ADD COLUMN IF NOT EXISTS firebase_uid VARCHAR(128);

-- Make it unique once it's populated (run after populating UIDs)
-- ALTER TABLE users ADD CONSTRAINT users_firebase_uid_key UNIQUE (firebase_uid);

-- 2. Add firebase_uid column to institutions
ALTER TABLE institutions
  ADD COLUMN IF NOT EXISTS firebase_uid VARCHAR(128);

-- 3. Remove password_hash from users (Firebase handles passwords now)
--    WARNING: Only run this AFTER migrating all users to Firebase Auth.
--    Keep the column for now and remove it later:
-- ALTER TABLE users DROP COLUMN IF EXISTS password_hash;

-- 4. Remove password_hash from institutions
--    WARNING: Only run this AFTER migrating all institutions to Firebase Auth.
-- ALTER TABLE institutions DROP COLUMN IF EXISTS password_hash;

-- 5. Remove chat_messages table (data migrated to Firestore)
--    WARNING: Export data to Firestore before dropping.
-- DROP TABLE IF EXISTS chat_messages;

-- 6. Remove private_messages and private_conversations (migrated to Firestore)
--    WARNING: Export data to Firestore before dropping.
-- DROP TABLE IF EXISTS private_messages;
-- DROP TABLE IF EXISTS private_conversations;

-- 7. Remove channel_messages (migrated to Firestore)
--    WARNING: Export data to Firestore before dropping.
-- DROP TABLE IF EXISTS channel_messages;

-- =============================================================================
-- Verify migration
-- =============================================================================

SELECT column_name, data_type
FROM information_schema.columns
WHERE table_name = 'users'
ORDER BY ordinal_position;

SELECT column_name, data_type
FROM information_schema.columns
WHERE table_name = 'institutions'
ORDER BY ordinal_position;
