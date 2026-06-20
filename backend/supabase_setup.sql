-- Supabase SQL Schema Setup for Warehouse gateway
-- Copy and paste this directly into the Supabase SQL Editor (https://supabase.com/dashboard/project/_/sql)

-- 1. Create the events table
CREATE TABLE IF NOT EXISTS events (
    id bigint PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
    created_at timestamp with time zone DEFAULT timezone('utc'::text, now()) NOT NULL,
    object_type text NOT NULL,
    track_id bigint NOT NULL,
    direction text NOT NULL,
    video_path text
);

-- 2. Configure Row Level Security (RLS)
-- This allows your API anon key to insert and select events
ALTER TABLE events ENABLE ROW LEVEL SECURITY;

-- Policy to allow inserting events
CREATE POLICY "Allow anon insert" 
ON events 
FOR INSERT 
TO anon 
WITH CHECK (true);

-- Policy to allow reading events (for stats/bot queries)
CREATE POLICY "Allow anon select" 
ON events 
FOR SELECT 
TO anon 
USING (true);

-- 3. Create indices for performance
CREATE INDEX IF NOT EXISTS idx_events_created_at ON events(created_at);
CREATE INDEX IF NOT EXISTS idx_events_object_type ON events(object_type);
