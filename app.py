import os
from flask import Flask, request, jsonify, render_template, session, redirect, url_for, flash
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail
from dotenv import load_dotenv
import datetime
import json
from functools import wraps
import psycopg2 # For PostgreSQL connection
import psycopg2.extras # For DictCursor

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv('FLASK_SECRET_KEY', 'your_default_secret_key_here_CHANGE_ME')

# Define the key for the marketing promo category
MARKETING_PROMO_CATEGORY_KEY = 'marketing_promo' # You can change this key if needed

# Database Configuration
DATABASE_URL = os.getenv('DATABASE_URL')
if not DATABASE_URL:
    print("Error: DATABASE_URL environment variable not found.")
    # You might want to raise an exception here or handle it more gracefully

ADMIN_USERNAME = os.getenv('ADMIN_USERNAME', 'admin')
ADMIN_PASSWORD = os.getenv('ADMIN_PASSWORD', 'password')

SUPPORTED_PLATFORMS = {
    'muse': 'Muse.ai',
    'youtube': 'YouTube',
    'vimeo': 'Vimeo'
}

SENDGRID_API_KEY = os.getenv('SENDGRID_API_KEY')
RECIPIENT_EMAIL = os.getenv('RECIPIENT_EMAIL')
SENDER_EMAIL = os.getenv('SENDER_EMAIL', RECIPIENT_EMAIL)

if not SENDGRID_API_KEY: print("Error: SENDGRID_API_KEY not found")
if not RECIPIENT_EMAIL: print("Error: RECIPIENT_EMAIL not found")

def get_db_connection():
    """Establishes a connection to the PostgreSQL database."""
    try:
        conn = psycopg2.connect(DATABASE_URL)
        print("Database connection established successfully.") # Add a success print
        return conn
    except psycopg2.Error as e_db:
        print(f"psycopg2 Database Error connecting to database:")
        print(f"  Error Code: {e_db.pgcode}")
        print(f"  Error Message: {e_db.pgerror}")
        print(f"  Diagnostics: {e_db.diag}")
        print(f"  Full Exception: {e_db}")
        # For now, let's re-raise to make it obvious during development if connection fails.
        raise
    except Exception as e_generic:
        print(f"Generic Error connecting to database: {e_generic}")
        # For now, let's re-raise to make it obvious during development if connection fails.
        raise

def load_data():
    """Loads categories and videos from the Supabase PostgreSQL database."""
    conn = None
    categories_map = {}
    all_videos_list = []
    videos_by_db_id = {} # Helper to quickly find videos by their database ID

    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor) # Use DictCursor for easy column access by name

        # 1. Fetch Categories
        cur.execute("SELECT category_key, name, color, description FROM categories ORDER BY id") # Added ORDER BY for consistency
        db_categories = cur.fetchall()
        for cat_row in db_categories:
            categories_map[cat_row['category_key']] = {
                'name': cat_row['name'],
                'color': cat_row['color'],
                'description': cat_row['description'],
                'videos': [] # Initialize with an empty list for videos
            }

        # 2. Fetch All Videos (including the new 'likes' column)
        cur.execute("SELECT id, platform, video_id_on_platform, title, view_count, likes FROM videos ORDER BY id") # Added ORDER BY and likes
        db_videos = cur.fetchall()
        for vid_row in db_videos:
            video_dict = {
                'db_id': vid_row['id'], # Store the database primary key for this video
                'platform': vid_row['platform'],
                'video_id': vid_row['video_id_on_platform'], # Match key name used in templates
                'video_id_on_platform': vid_row['video_id_on_platform'], # Explicitly add for url_for debugging
                'title': vid_row['title'],
                'view_count': vid_row['view_count'],
                'likes': vid_row['likes'], # Add likes count
                'category_keys': [] # Initialize, will be populated from assignments
            }
            all_videos_list.append(video_dict)
            videos_by_db_id[vid_row['id']] = video_dict # Add to helper map

        # 3. Fetch Video-Category Assignments and Link them
        cur.execute("SELECT video_db_id, category_db_key FROM video_category_assignments")
        assignments = cur.fetchall()
        for assignment in assignments:
            video_db_id = assignment['video_db_id']
            category_key = assignment['category_db_key']

            if category_key in categories_map and video_db_id in videos_by_db_id:
                # Add the category key to the video's list of category keys
                videos_by_db_id[video_db_id]['category_keys'].append(category_key)
                # Add a reference to the video object to the category's list of videos
                # Ensure not to add duplicate video objects if a video somehow got assigned twice (though DB constraint should prevent)
                # For simplicity here, we assume data integrity from DB constraints.
                categories_map[category_key]['videos'].append(videos_by_db_id[video_db_id])
            # else:
                # print(f"Warning: Assignment found for non-existent video_db_id {video_db_id} or category_key {category_key}")

        # Sort videos within each category, e.g., by title or id, if desired. For now, they are by insertion order from assignments.
        # Example: for cat_data in categories_map.values():
        #              cat_data['videos'].sort(key=lambda v: v['title'])

    except (psycopg2.Error, Exception) as e:
        flash(f"Database error loading data: {e}", "danger")
        print(f"Database error in load_data: {e}")
        # Return empty structures on error to prevent app crash, but log/flash the error
        return {}, [] 
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()
    
    return categories_map, all_videos_list

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'logged_in' not in session:
            flash('Please log in to access this page.', 'warning')
            return redirect(url_for('admin_login', next=request.url))
        return f(*args, **kwargs)
    return decorated_function

@app.route('/')
def index():
    message = request.args.get('message')
    error = request.args.get('error')
    vespa_categories_data, all_videos_data = load_data()
    
    featured_video = None
    if all_videos_data:
        day_of_year = datetime.date.today().timetuple().tm_yday
        featured_video = all_videos_data[(day_of_year - 1) % len(all_videos_data)]

    marketing_promo_video = None
    display_categories = {}
    most_liked_videos = [] # Initialize list for most liked videos

    if vespa_categories_data:
        # Extract marketing promo video
        if MARKETING_PROMO_CATEGORY_KEY in vespa_categories_data:
            promo_category_data = vespa_categories_data[MARKETING_PROMO_CATEGORY_KEY]
            if promo_category_data.get('videos'):
                marketing_promo_video = promo_category_data['videos'][0] # Get the first video

        # Prepare categories for display, excluding the marketing promo category from the main loop
        for cat_key, cat_data in vespa_categories_data.items():
            if cat_key != MARKETING_PROMO_CATEGORY_KEY:
                display_categories[cat_key] = cat_data
            # If you wanted the marketing promo category to also appear as a regular section
            # in addition to its special spot, you would not filter it out here.
            # However, current index.html design implies it's special.
    
    # Prepare most liked videos (after all_videos_data is populated with likes)
    if all_videos_data:
        # Sort videos by likes in descending order
        sorted_videos_by_likes = sorted(all_videos_data, key=lambda v: v.get('likes', 0), reverse=True)
        most_liked_videos = sorted_videos_by_likes[:3] # Get top 3 liked videos

    return render_template(
        'index.html', 
        message=message, 
        error=error, 
        featured_video=featured_video, 
        vespa_categories=display_categories, # Use the filtered list for the main sections
        marketing_promo_video=marketing_promo_video, # Pass the special promo video
        most_liked_videos=most_liked_videos, # Pass the most liked videos
        all_videos_data=all_videos_data, # Still available if needed for other things
        current_year=datetime.date.today().year
    )

@app.route('/submit', methods=['POST'])
def submit_form():
    name = request.form.get('name')
    email = request.form.get('email')
    school = request.form.get('school', 'Not Provided')
    message_body = request.form.get('message')
    vespa_categories_data, all_videos_data = load_data()
    featured_video_for_error = featured_video_for_success = None
    if all_videos_data:
        day_of_year = datetime.date.today().timetuple().tm_yday
        featured_video_for_error = all_videos_data[0]
        featured_video_for_success = all_videos_data[(day_of_year - 1) % len(all_videos_data)]
    if not all([SENDGRID_API_KEY, RECIPIENT_EMAIL, SENDER_EMAIL]):
        return render_template('index.html', error='Sorry, server email config error.', vespa_categories=vespa_categories_data, featured_video=featured_video_for_error, current_year=datetime.date.today().year)
    if not all([name, email, message_body]):
        return render_template('index.html', error='Please fill in all required fields.', vespa_categories=vespa_categories_data, featured_video=featured_video_for_error, current_year=datetime.date.today().year)
    mail_to_send = Mail(from_email=SENDER_EMAIL, to_emails=[RECIPIENT_EMAIL], subject=f"New VESPA Academy Enquiry from {name}", html_content=f"<h3>New VESPA Enquiry</h3><p>Name: {name}</p><p>Email: {email}</p><p>School: {school}</p><hr><p>Message:</p><p>{message_body.replace('\n', '<br>')}</p>")
    try:
        SendGridAPIClient(SENDGRID_API_KEY).send(mail_to_send)
        return render_template('index.html', message='Thank you! Your message has been sent.', vespa_categories=vespa_categories_data, featured_video=featured_video_for_success, current_year=datetime.date.today().year)
    except Exception as e:
        print(f"Error sending email: {e}")
        return render_template('index.html', error='Sorry, an error occurred.', vespa_categories=vespa_categories_data, featured_video=featured_video_for_error, current_year=datetime.date.today().year)

@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        if request.form.get('username') == ADMIN_USERNAME and request.form.get('password') == ADMIN_PASSWORD:
            session['logged_in'] = True
            flash('Logged in successfully!', 'success')
            return redirect(request.args.get('next') or url_for('admin_dashboard'))
        else:
            flash('Invalid credentials.', 'danger')
    return render_template('admin_login.html')

@app.route('/admin/logout')
@login_required
def admin_logout():
    session.pop('logged_in', None)
    flash('You have been logged out.', 'info')
    return redirect(url_for('admin_login'))

@app.route('/admin')
@login_required
def admin_dashboard():
    vespa_categories_from_db, all_videos = load_data() # Use load_data for categories too
    
    return render_template(
        'admin.html', 
        videos=all_videos, 
        vespa_categories=vespa_categories_from_db, # Pass categories from database
        supported_platforms=SUPPORTED_PLATFORMS
    )

@app.route('/admin/add_video', methods=['POST'])
@login_required
def add_video():
    video_id_on_platform = request.form.get('video_id') # Renamed for clarity to match DB field
    platform = request.form.get('platform')
    title = request.form.get('title')
    category_keys_from_form = request.form.getlist('category_keys')

    if not all([video_id_on_platform, title, platform]):
        flash('Video ID, Platform, and Title are required.', 'danger')
        return redirect(url_for('admin_dashboard'))

    if platform not in SUPPORTED_PLATFORMS:
        flash('Invalid video platform selected.', 'danger')
        return redirect(url_for('admin_dashboard'))

    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()

        # Check if video already exists
        cur.execute(
            "SELECT id FROM videos WHERE platform = %s AND video_id_on_platform = %s",
            (platform, video_id_on_platform)
        )
        existing_video = cur.fetchone()
        if existing_video:
            flash(f'Video with ID \'{video_id_on_platform}\' on platform \'{SUPPORTED_PLATFORMS.get(platform, platform)}\' already exists.', 'warning')
            return redirect(url_for('admin_dashboard'))

        # Insert new video and get its database ID
        cur.execute(
            "INSERT INTO videos (platform, video_id_on_platform, title) VALUES (%s, %s, %s) RETURNING id",
            (platform, video_id_on_platform, title)
        )
        new_video_db_id = cur.fetchone()[0]

        # Assign categories
        if new_video_db_id and category_keys_from_form:
            for cat_key in category_keys_from_form:
                try:
                    cur.execute(
                        "INSERT INTO video_category_assignments (video_db_id, category_db_key) VALUES (%s, %s)",
                        (new_video_db_id, cat_key)
                    )
                except psycopg2.errors.ForeignKeyViolation:
                    # This might happen if a category key from the form is somehow invalid/not in DB
                    # Or if the category wasn't migrated properly.
                    flash(f"Warning: Could not assign category '{cat_key}' to video '{title}'. Category might not exist.", "warning")
                    print(f"ForeignKeyViolation: Could not assign category '{cat_key}' to video '{title}' (DB ID: {new_video_db_id})")
                    # Continue adding other categories
                except psycopg2.errors.UniqueViolation:
                    # Should not happen if adding a new video, but good to be aware
                    flash(f"Warning: Video '{title}' already assigned to category '{cat_key}'.", "warning")
                    print(f"UniqueViolation: Video '{title}' (DB ID: {new_video_db_id}) already assigned to category '{cat_key}'.")

        conn.commit()
        flash(f'Video \'{title}\' added successfully!', 'success')

    except (psycopg2.Error, Exception) as e:
        if conn:
            conn.rollback()
        flash(f'Database error adding video: {e}', 'danger')
        print(f"Database error in add_video: {e}")
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()
    
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/delete_video/<string:platform>/<string:video_id_on_platform_from_url>', methods=['POST'])
@login_required
def delete_video(platform, video_id_on_platform_from_url):
    conn = None
    deleted_title = None # To store the title for the flash message

    try:
        conn = get_db_connection()
        cur = conn.cursor()

        # Find the video to get its title for the flash message (optional, but nice UX)
        # And to ensure it exists before attempting delete based on DB id (though not strictly necessary if just deleting by platform/video_id_on_platform)
        cur.execute(
            "SELECT id, title FROM videos WHERE platform = %s AND video_id_on_platform = %s",
            (platform, video_id_on_platform_from_url)
        )
        video_to_delete = cur.fetchone()

        if video_to_delete:
            video_db_id = video_to_delete[0]
            deleted_title = video_to_delete[1]

            # Delete the video from the videos table.
            # Assignments in video_category_assignments should be deleted automatically due to ON DELETE CASCADE.
            cur.execute("DELETE FROM videos WHERE id = %s", (video_db_id,))
            conn.commit()
            flash(f'Video \'{deleted_title}\' ({SUPPORTED_PLATFORMS.get(platform, platform)}) deleted successfully.', 'success')
        else:
            flash(f'Video \'{video_id_on_platform_from_url}\' ({SUPPORTED_PLATFORMS.get(platform, platform)}) not found for deletion.', 'warning')

    except (psycopg2.Error, Exception) as e:
        if conn:
            conn.rollback()
        flash(f'Database error deleting video: {e}', 'danger')
        print(f"Database error in delete_video: {e}")
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()
    
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/edit_video/<string:platform>/<string:video_id_on_platform_from_url>', methods=['GET', 'POST'])
@login_required
def edit_video(platform, video_id_on_platform_from_url):
    conn = None
    video_to_edit = None
    video_db_id = None # To store the primary key of the video from the 'videos' table

    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)

        # Fetch the video by platform and video_id_on_platform to get its DB ID and details
        cur.execute(
            "SELECT id, platform, video_id_on_platform, title FROM videos WHERE platform = %s AND video_id_on_platform = %s",
            (platform, video_id_on_platform_from_url)
        )
        fetched_video = cur.fetchone()

        if not fetched_video:
            flash(f'Video \'{video_id_on_platform_from_url}\' ({SUPPORTED_PLATFORMS.get(platform, platform)}) not found.', 'warning')
            return redirect(url_for('admin_dashboard'))
        
        video_db_id = fetched_video['id']
        video_to_edit = dict(fetched_video) # Convert DictRow to a mutable dict

        # Fetch current category assignments for this video
        cur.execute(
            "SELECT category_db_key FROM video_category_assignments WHERE video_db_id = %s",
            (video_db_id,)
        )
        assigned_cat_rows = cur.fetchall()
        video_to_edit['category_keys'] = [row['category_db_key'] for row in assigned_cat_rows]

        # Fetch all available categories for the form
        cur.execute("SELECT category_key, name FROM categories ORDER BY name")
        all_categories_list = cur.fetchall()
        all_categories_for_template = {row['category_key']: {'name': row['name']} for row in all_categories_list}

        if request.method == 'POST':
            new_title = request.form.get('title')
            new_category_keys = request.form.getlist('category_keys')

            if not new_title:
                flash('Title cannot be empty.', 'danger')
                # Need to pass original video_to_edit and all_categories for template re-render
                return render_template('admin_edit_video.html', video_to_edit=video_to_edit, all_categories=all_categories_for_template, supported_platforms=SUPPORTED_PLATFORMS, platform=platform, video_id=video_id_on_platform_from_url)

            # Start transaction for update
            # Update video title
            cur.execute(
                "UPDATE videos SET title = %s WHERE id = %s",
                (new_title, video_db_id)
            )

            # Update category assignments
            # 1. Delete existing assignments for this video
            cur.execute("DELETE FROM video_category_assignments WHERE video_db_id = %s", (video_db_id,))
            
            # 2. Insert new assignments
            if new_category_keys:
                for cat_key in new_category_keys:
                    try:
                        cur.execute(
                            "INSERT INTO video_category_assignments (video_db_id, category_db_key) VALUES (%s, %s)",
                            (video_db_id, cat_key)
                        )
                    except psycopg2.errors.ForeignKeyViolation:
                        flash(f"Warning: Could not assign category '{cat_key}' to video '{new_title}'. Category may not exist.", "warning")
                        print(f"ForeignKeyViolation: edit_video - Could not assign '{cat_key}' to video DB ID {video_db_id}")
                    # Not expecting UniqueViolation here as we delete first, but good to be mindful.
            
            conn.commit()
            flash(f'Video \'{new_title}\' updated successfully.', 'success')
            return redirect(url_for('admin_dashboard'))

    except (psycopg2.Error, Exception) as e:
        if conn:
            conn.rollback()
        flash(f'Database error editing video: {e}', 'danger')
        print(f"Database error in edit_video: {e}")
        return redirect(url_for('admin_dashboard')) # Redirect on error to avoid broken state
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()

    # For GET request, render the template with the fetched video and categories
    return render_template('admin_edit_video.html', video_to_edit=video_to_edit, all_categories=all_categories_for_template, supported_platforms=SUPPORTED_PLATFORMS, platform=platform, video_id=video_id_on_platform_from_url)

# Comment out or remove the migrate_data_to_db function if you haven't already
# @app.route('/admin/migrate_to_db')
# @login_required
# def migrate_data_to_db():
#    # ... (migration code) ...
#    pass

@app.route('/like_video/<int:video_db_id>', methods=['POST'])
def like_video(video_db_id):
    if not video_db_id:
        return jsonify({'success': False, 'error': 'Video ID not provided'}), 400

    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()

        # Increment the likes count for the video
        cur.execute(
            "UPDATE videos SET likes = likes + 1 WHERE id = %s RETURNING likes",
            (video_db_id,)
        )
        updated_likes = cur.fetchone()
        
        if updated_likes:
            conn.commit()
            return jsonify({'success': True, 'new_like_count': updated_likes[0]})
        else:
            # This case means the video_db_id didn't exist
            conn.rollback() # Rollback if no update occurred
            return jsonify({'success': False, 'error': 'Video not found'}), 404

    except (psycopg2.Error, Exception) as e:
        if conn:
            conn.rollback()
        print(f"Database error in like_video: {e}")
        return jsonify({'success': False, 'error': 'Database error'}), 500
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True) 