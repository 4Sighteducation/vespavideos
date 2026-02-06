 CREATE TABLE categories (
        id SERIAL PRIMARY KEY,
        category_key TEXT UNIQUE NOT NULL,
        name TEXT NOT NULL,
        color TEXT,
        description TEXT
    );

    CREATE TABLE videos (
        id SERIAL PRIMARY KEY,
        platform TEXT NOT NULL,
        video_id_on_platform TEXT NOT NULL,
        title TEXT NOT NULL,
        view_count INTEGER DEFAULT 0,
        CONSTRAINT unique_video_platform_id UNIQUE (platform, video_id_on_platform)
    );

    CREATE TABLE video_category_assignments (
        id SERIAL PRIMARY KEY,
        video_db_id INTEGER NOT NULL REFERENCES videos(id) ON DELETE CASCADE,
        category_db_key TEXT NOT NULL REFERENCES categories(category_key) ON DELETE CASCADE,
        UNIQUE (video_db_id, category_db_key)
    );

     INSERT INTO categories (category_key, name, color, description)
        VALUES ('marketing_promo', 'Marketing Promotion Video', '#FFD700', 'Main promotional video for the homepage.');

        ALTER TABLE videos
ADD COLUMN likes INTEGER DEFAULT 0;

CREATE TABLE series (
    id SERIAL PRIMARY KEY,
    series_key TEXT UNIQUE NOT NULL,  -- A short, unique key like 'revision_series_2024' or 'vision_foundations'
    name TEXT NOT NULL,               -- User-friendly name like "Revision Series 2024"
    description TEXT,
    is_featured BOOLEAN DEFAULT FALSE, -- Flag to mark a series as the one to feature on the homepage
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE video_series_assignments (
    id SERIAL PRIMARY KEY,
    video_db_id INTEGER NOT NULL REFERENCES videos(id) ON DELETE CASCADE,
    series_db_id INTEGER NOT NULL REFERENCES series(id) ON DELETE CASCADE,
    display_order INTEGER DEFAULT 0, -- Optional: to control video order within a series
    UNIQUE (video_db_id, series_db_id) -- Ensure a video is not assigned to the same series multiple times
);

  ALTER TABLE videos
    ADD COLUMN created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP;

    CREATE TABLE problems (
    problem_id SERIAL PRIMARY KEY,
    problem_text TEXT NOT NULL,
    theme TEXT NOT NULL
);

-- Optional: Add a description to the 'problems' table and its columns for clarity
COMMENT ON TABLE problems IS 'Stores predefined problems that videos can address, grouped by theme.';
COMMENT ON COLUMN problems.problem_id IS 'Unique identifier for each problem.';
COMMENT ON COLUMN problems.problem_text IS 'The textual description of the problem (e.g., Unclear future goals).';
COMMENT ON COLUMN problems.theme IS 'The VESPA theme this problem belongs to (e.g., VISION, EFFORT).';

CREATE TABLE video_problems (
    id SERIAL PRIMARY KEY, -- Optional, but consistent with your other join tables
    video_db_id INTEGER NOT NULL REFERENCES videos(id) ON DELETE CASCADE,
    problem_id INTEGER NOT NULL REFERENCES problems(problem_id) ON DELETE CASCADE,
    UNIQUE (video_db_id, problem_id) -- Ensures a video isn't linked to the same problem multiple times
);

ALTER TABLE video_series_assignments
DROP CONSTRAINT video_series_assignments_series_db_id_fkey; -- <<< REPLACE THIS NAME

-- Step 3: Add the foreign key constraint back WITH ON DELETE CASCADE
ALTER TABLE video_series_assignments
ADD CONSTRAINT video_series_assignments_series_db_id_fkey -- <<< Use the same or a new name
FOREIGN KEY (series_db_id)
REFERENCES series(id)
ON DELETE CASCADE;

-- ============================================================
-- Multi-site video visibility (VESPA vs CSC sister site)
-- ============================================================
-- Goal: allow one shared database to power multiple public sites (e.g. videos.vespa.academy and cscvideos.vespa.academy)
-- without duplicating videos or standing up a separate app/DB.
--
-- Migration notes:
-- 1) Run the CREATE TABLE statements below in Supabase (SQL editor).
-- 2) Insert the two default sites (vespa, csc).
-- 3) Assign EXISTING videos to 'vespa' (so current site behaviour remains unchanged).
-- 4) For CSC-only commissioned videos, assign ONLY to 'csc' (and do NOT assign to 'vespa').

CREATE TABLE IF NOT EXISTS sites (
    site_key TEXT PRIMARY KEY,  -- e.g. 'vespa', 'csc'
    name TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS video_site_assignments (
    video_db_id INTEGER NOT NULL REFERENCES videos(id) ON DELETE CASCADE,
    site_key TEXT NOT NULL REFERENCES sites(site_key) ON DELETE CASCADE,
    PRIMARY KEY (video_db_id, site_key)
);

-- Seed default sites
INSERT INTO sites (site_key, name)
VALUES ('vespa', 'VESPA Videos')
ON CONFLICT (site_key) DO NOTHING;

INSERT INTO sites (site_key, name)
VALUES ('csc', 'Central South Consortium Videos')
ON CONFLICT (site_key) DO NOTHING;

-- Assign all existing videos to VESPA site by default (keeps current behaviour)
INSERT INTO video_site_assignments (video_db_id, site_key)
SELECT v.id, 'vespa'
FROM videos v
ON CONFLICT DO NOTHING;