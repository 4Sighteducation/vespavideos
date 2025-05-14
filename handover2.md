Project Update & Handover: VESPA Video Marketing Page & Admin Panel
Date: October 26, 2023 (Please adjust to the current date)
Reference: This document supplements the original handoverdoc -vespavideos.txt.
I. Overview of Recent Enhancements:
This development session focused on significantly enhancing the user-facing video page, adding "like" and "series" functionalities, and improving the admin panel to manage these new features.
II. New Features & Significant Changes:
Homepage UI & Video Display (templates/index.html):
Restructured Marketing Section:
The main marketing video (from marketing_promo_video category) is now integrated directly into the top promotional banner ("Transform Student Success...").
The banner content has been updated with new text, icons ("How it Works," "Proven Impact"), and layout.
Marketing video display is smaller and more responsive.
"Community Favourites" Section:
Displays the top 3 most liked videos across all categories.
VESPA Category Display:
Each main VESPA category (Vision, Effort, etc.) now displays its first 5 videos directly.
A "View all videos in \[Category Name]" button is present for each category if it contains videos.
These buttons are color-coordinated with their respective category color.
Clicking the button opens a modal showing all videos in that category.
"Featured Series" Section:
Displays a single series designated as "featured" in the admin panel.
Shows the featured series' name and description.
Displays the top 3 most liked videos from that series.
Includes a "View all videos in \[Series Name]" button (solid blue style).
This button opens a modal showing all videos belonging to the featured series.
Removed Sections: The old "About the VESPA Academy Portal" video, "About the Revision Series" text, and "Today's Featured Revision Video" (daily rotating) sections have been removed from the homepage layout.
Video "Like" Functionality:
Users can click a "Like" button (heart icon) on any video card.
Like counts are stored in the videos table (new likes column).
Like buttons and dynamically updated like counts are displayed on all video cards (homepage direct display, modals, Community Favourites, Featured Series).
Implemented via a backend route /like_video/<int:video_db_id> in app.py.
Series Management (Database & Admin Panel):
Database Changes:
New table series created: (id SERIAL PK, series_key TEXT UNIQUE NOT NULL, name TEXT NOT NULL, description TEXT, is_featured BOOLEAN DEFAULT FALSE, created_at TIMESTAMP WITH TIME ZONE).
New table video_series_assignments created: (id SERIAL PK, video_db_id INTEGER FK to videos.id, series_db_id INTEGER FK to series.id, display_order INTEGER DEFAULT 0, UNIQUE (video_db_id, series_db_id)).
Admin - Manage Series (/admin/series & templates/admin_series.html):
A new admin page allows creation and listing of series.
When creating a series, it can be marked as "featured." The system ensures only one series can be featured at a time.
Admin - Video Assignments (/admin, templates/admin.html, templates/admin_edit_video.html):
The "Add New Video" and "Edit Existing Video" forms now include a checkbox section to assign/unassign videos to/from available series.
Enhanced "Add Video" Logic (app.py):
If adding a video using an ID and platform that already exists in the videos table, the system no longer errors.
Instead, it updates the existing video's assignments.
Crucially, if category checkboxes are left unselected when updating an existing video this way, its original categories are preserved. The same applies to series. This allows adding an existing video to a new series without losing its original category tags.
Backend Logic (app.py):
load_data(): Updated to fetch the likes count for each video.
New load_featured_series_data(): Fetches the designated featured series, its top 3 liked videos, and all videos belonging to it (for the modal).
index() route: Updated to use new data functions and pass all necessary data (most liked videos, featured series info, featured series top videos, all featured series videos) to index.html.
admin_dashboard(): Now loads category definitions from the database (via load_data()) rather than data.json for consistency in the "Add Video" form.
add_video(): Significantly refactored to handle new/existing videos and their category/series assignments as described above.
edit_video(): Updated to fetch and pass series data to its template, and to process series assignment updates.
III. Key Files Modified/Created:
Modified:
app.py
templates/index.html
templates/admin.html
templates/admin_edit_video.html
Created:
templates/admin_series.html
IV. Database Schema Changes Summary:
videos table: Added column likes INTEGER DEFAULT 0.
New table series: (id, series_key, name, description, is_featured, created_at).
New table video_series_assignments: (id, video_db_id, series_db_id, display_order).
V. Important Considerations for Future Development:
Old Daily Featured Video Logic: The featured_video variable (daily rotating based on all_videos_data) is still calculated in app.py's index route and passed to index.html, but its display components were removed. This logic can be fully removed from app.py unless a new purpose for it is envisioned.
Series Admin Enhancements: The /admin/series page currently supports adding and listing series. "Edit" and "Delete" functionality for series are potential future additions.
Video Order in Series: The display_order column in video_series_assignments is used by load_featured_series_data() to sort videos within a series (when fetching all videos for the modal). An admin interface to manually manage this display_order for videos within each series could be a useful enhancement.
Linter Warnings: The linter consistently flags Jinja templating within <style> tags in HTML files as errors. These are benign and related to the linter's parsing, not actual CSS/HTML issues.
VI. Deployment:
Ensure all environment variables (DATABASE_URL, FLASK_SECRET_KEY, ADMIN_USERNAME, ADMIN_PASSWORD, SENDGRID_API_KEY, etc.) are correctly set in Heroku Config Vars.
Deployment to Heroku is via git push heroku main.