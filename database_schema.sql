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