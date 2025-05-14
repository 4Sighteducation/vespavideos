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
    """Loads categories, videos (including keywords and problems) from the Supabase PostgreSQL database."""
    conn = None
    categories_map = {}
    all_videos_list = []
    videos_by_db_id = {} # Helper to quickly find videos by their database ID

    # Define icons for categories
    category_icons = {
        'vision': 'bi-lightbulb',
        'effort': 'bi-graph-up',
        'systems': 'bi-gear-wide-connected',
        'practice': 'bi-pencil-square',
        'attitude': 'bi-emoji-smile',
        # Add more icons here as new categories are created or discovered
    }

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
                'videos': [], # Initialize with an empty list for videos
                'icon': category_icons.get(cat_row['category_key'].lower(), 'bi-collection-play') # Use .lower() for lookup & Default icon
            }

        # 2. Fetch All Videos (including keywords, likes, created_at)
        cur.execute("SELECT id, platform, video_id_on_platform, title, view_count, likes, created_at, keywords FROM videos ORDER BY id")
        db_videos = cur.fetchall()
        for vid_row in db_videos:
            video_dict = {
                'db_id': vid_row['id'], 
                'platform': vid_row['platform'],
                'video_id': vid_row['video_id_on_platform'], 
                'video_id_on_platform': vid_row['video_id_on_platform'], 
                'title': vid_row['title'],
                'view_count': vid_row['view_count'],
                'likes': vid_row['likes'],
                'created_at': vid_row['created_at'],
                'keywords': vid_row['keywords'] if vid_row['keywords'] is not None else '', # Ensure keywords is a string
                'category_keys': [], 
                'problems': [] 
            }
            all_videos_list.append(video_dict)
            videos_by_db_id[vid_row['id']] = video_dict

        # 3. Fetch Video-Category Assignments and Link them
        cur.execute("SELECT video_db_id, category_db_key FROM video_category_assignments")
        assignments = cur.fetchall()
        for assignment in assignments:
            video_db_id = assignment['video_db_id']
            category_key = assignment['category_db_key']

            if category_key in categories_map and video_db_id in videos_by_db_id:
                videos_by_db_id[video_db_id]['category_keys'].append(category_key)
                categories_map[category_key]['videos'].append(videos_by_db_id[video_db_id])

        # 4. Fetch Video-Problem Assignments and Link them
        cur.execute("""
            SELECT vp.video_db_id, p.problem_text, p.theme
            FROM video_problems vp
            JOIN problems p ON vp.problem_id = p.problem_id
        """)
        problem_assignments = cur.fetchall()
        for prob_assign in problem_assignments:
            video_db_id = prob_assign['video_db_id']
            if video_db_id in videos_by_db_id:
                videos_by_db_id[video_db_id]['problems'].append({
                    'text': prob_assign['problem_text'],
                    'theme': prob_assign['theme']
                })

        # Sort videos within each category by likes (descending) and then title (ascending)
        for cat_data in categories_map.values():
            # Ensure 'likes' exists and default to 0 if not; ensure 'title' exists and default to empty string
            cat_data['videos'].sort(key=lambda v: (v.get('likes', 0), v.get('title', '')), reverse=False) # Initial sort for title ascending
            cat_data['videos'].sort(key=lambda v: v.get('likes', 0), reverse=True) # Stable sort for likes descending

        # Dynamically create and populate "Fresh New Vids" category
        fresh_vids_category_key = 'fresh_new_vids'
        fresh_vids_list = []
        
        # Calculate the cutoff date for "fresh" videos (last 14 days)
        # Ensure datetime and timedelta are available (datetime is imported, timedelta needs to be)
        # datetime.timedelta is part of the datetime module.
        fourteen_days_ago = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=14)

        temp_fresh_vids = []
        for video in all_videos_list: # all_videos_list now contains video dicts with 'created_at'
            if video.get('created_at'): # Check if created_at is not None
                video_created_at = video['created_at']
                # Ensure video_created_at is offset-aware if it's not already
                # (psycopg2 usually makes TIMESTAMPTZ aware, but good to be safe)
                if not video_created_at.tzinfo:
                    video_created_at = video_created_at.replace(tzinfo=datetime.timezone.utc)
                
                if video_created_at >= fourteen_days_ago:
                    temp_fresh_vids.append(video)
        
        # Sort these fresh videos by created_at descending (most recent first)
        temp_fresh_vids.sort(key=lambda v: v.get('created_at'), reverse=True)
        fresh_vids_list = temp_fresh_vids

        print(f"DEBUG: Found {len(fresh_vids_list)} fresh videos.") # Temporary debug line

        # Only add the "Fresh New Vids" category if there are any fresh videos
        if fresh_vids_list:
            categories_map[fresh_vids_category_key] = {
                'name': 'Fresh New Vids',
                'color': '#00e5db',  # Theme color as requested
                'description': 'Videos added in the last 14 days!',
                'videos': fresh_vids_list,
                'icon': 'bi-stars' # Icon for Fresh New Vids
            }

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

def get_all_problems():
    """Fetches all unique problems from the database for search filters."""
    conn = None
    problems_list = []
    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        cur.execute("SELECT problem_id, problem_text, theme FROM problems ORDER BY theme, problem_text")
        problems_list = cur.fetchall()
    except (psycopg2.Error, Exception) as e:
        flash(f"Database error loading problems: {e}", "danger")
        print(f"Database error in get_all_problems: {e}")
    finally:
        if conn:
            if cur:
                cur.close()
            conn.close()
    return problems_list

def load_featured_series_data():
    """Loads the featured series and its top 3 liked videos."""
    conn = None
    featured_series_info = None
    featured_series_top_videos = []
    featured_series_all_videos = [] # Add list for all videos in the series

    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)

        # 1. Find the featured series
        cur.execute("SELECT id, series_key, name, description FROM series WHERE is_featured = TRUE LIMIT 1")
        series_row = cur.fetchone()

        if series_row:
            featured_series_info = dict(series_row)
            
            # 2. Fetch videos assigned to this series, including their like counts, ordered by likes
            # We need a JOIN to get video details and likes from the 'videos' table
            # and order by likes to easily pick the top 3.
            cur.execute("""
                SELECT v.id, v.platform, v.video_id_on_platform, v.title, v.view_count, v.likes, v.id as db_id
                FROM videos v
                JOIN video_series_assignments vsa ON v.id = vsa.video_db_id
                WHERE vsa.series_db_id = %s
                ORDER BY v.likes DESC, vsa.display_order ASC, v.id ASC
                LIMIT 3
            """, (featured_series_info['id'],))
            
            video_rows_top = cur.fetchall()
            for vid_row in video_rows_top:
                video_data = {
                    'db_id': vid_row['id'],
                    'platform': vid_row['platform'],
                    'video_id': vid_row['video_id_on_platform'],
                    'title': vid_row['title'],
                    'view_count': vid_row['view_count'],
                    'likes': vid_row['likes']
                }
                featured_series_top_videos.append(video_data)

            # 3. Fetch ALL videos assigned to this series for the modal, ordered by display_order then title
            cur.execute("""
                SELECT v.id, v.platform, v.video_id_on_platform, v.title, v.view_count, v.likes, v.id as db_id
                FROM videos v
                JOIN video_series_assignments vsa ON v.id = vsa.video_db_id
                WHERE vsa.series_db_id = %s
                ORDER BY vsa.display_order ASC, v.title ASC, v.id ASC
            """, (featured_series_info['id'],))

            video_rows_all = cur.fetchall()
            for vid_row in video_rows_all:
                video_data_all = {
                    'db_id': vid_row['id'],
                    'platform': vid_row['platform'],
                    'video_id': vid_row['video_id_on_platform'],
                    'title': vid_row['title'],
                    'view_count': vid_row['view_count'],
                    'likes': vid_row['likes']
                }
                featured_series_all_videos.append(video_data_all)

        # else: No featured series found, variables will remain None/empty list

    except (psycopg2.Error, Exception) as e:
        print(f"Database error in load_featured_series_data: {e}")
        return None, [], [] # Return three values now
    finally:
        if conn:
            if cur: 
                cur.close()
            conn.close()
    
    return featured_series_info, featured_series_top_videos, featured_series_all_videos # Return all three

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
    all_problems_for_filter = get_all_problems() # Fetch all problems
    
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

        # Prepare categories for display, ensuring "Fresh New Vids" is first if it exists.
        ordered_display_categories = []
        fresh_vids_category_key = 'fresh_new_vids' # Key used in load_data

        if fresh_vids_category_key in vespa_categories_data:
            # Add Fresh New Vids first, and include its key for the template if needed
            fresh_vids_data = vespa_categories_data[fresh_vids_category_key]
            ordered_display_categories.append( (fresh_vids_category_key, fresh_vids_data) )

        for cat_key, cat_data in vespa_categories_data.items():
            if cat_key != MARKETING_PROMO_CATEGORY_KEY and cat_key != fresh_vids_category_key:
                ordered_display_categories.append( (cat_key, cat_data) )
        
        # display_categories = {} # Original approach, replaced by ordered_display_categories
        # for cat_key, cat_data in vespa_categories_data.items():
        #     if cat_key != MARKETING_PROMO_CATEGORY_KEY:
        #         display_categories[cat_key] = cat_data
    else:
        ordered_display_categories = [] # Ensure it's an empty list if vespa_categories_data is empty
    
    # Prepare most liked videos (after all_videos_data is populated with likes)
    if all_videos_data:
        # Sort videos by likes in descending order
        sorted_videos_by_likes = sorted(all_videos_data, key=lambda v: v.get('likes', 0), reverse=True)
        most_liked_videos = sorted_videos_by_likes[:3] # Get top 3 liked videos

    # Load featured series data
    featured_series_info, featured_series_top_videos, featured_series_all_videos = load_featured_series_data()

    return render_template(
        'index.html', 
        message=message, 
        error=error, 
        featured_video=featured_video, # This is the old daily featured video, consider removing or repurposing
        vespa_categories=ordered_display_categories, # Use the new ordered list
        marketing_promo_video=marketing_promo_video, 
        most_liked_videos=most_liked_videos, 
        all_videos_data=all_videos_data, 
        featured_series_info=featured_series_info, 
        featured_series_top_videos=featured_series_top_videos,
        featured_series_all_videos=featured_series_all_videos, # Pass all series videos
        all_problems=all_problems_for_filter, # Pass problems to template
        current_year=datetime.date.today().year
    )

@app.route('/search')
def search():
    query = request.args.get('query', '').strip()
    problem_query_val = request.args.get('problem_query', '').strip()

    if not query and problem_query_val:
        query = problem_query_val
        
    categories_data, all_videos_data = load_data()
    all_problems_for_filter = get_all_problems() # Fetch problems for the modal
    
    search_results = []
    
    if query:
        query_lower = query.lower()
        for video in all_videos_data:
            # Check title
            if query_lower in video.get('title', '').lower():
                search_results.append(video)
                continue
            
            # Check keywords
            if query_lower in video.get('keywords', '').lower():
                search_results.append(video)
                continue
            
            # Check problems
            for problem in video.get('problems', []):
                if query_lower in problem.get('text', '').lower() or \
                   query_lower in problem.get('theme', '').lower():
                    search_results.append(video)
                    break # Found a match in problems, move to next video
            if video in search_results: # If added from problem search, continue
                continue

            # Check categories the video is assigned to
            for cat_key in video.get('category_keys', []):
                if cat_key in categories_data: # Ensure category exists in loaded data
                    category_name = categories_data[cat_key].get('name', '').lower()
                    if query_lower in category_name:
                        search_results.append(video)
                        break # Found a match in category names, move to next video
            # No need to continue here, it's the last check for this video

    return render_template('search_results.html',
                           query=query,
                           results=search_results,
                           all_problems=all_problems_for_filter, # Pass problems to template
                           current_year=datetime.date.today().year)

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
    all_problems_for_filter = get_all_problems() # Fetch all problems
    if request.method == 'POST':
        if request.form.get('username') == ADMIN_USERNAME and request.form.get('password') == ADMIN_PASSWORD:
            session['logged_in'] = True
            flash('Logged in successfully!', 'success')
            return redirect(request.args.get('next') or url_for('admin_dashboard'))
        else:
            flash('Invalid credentials.', 'danger')
    return render_template('admin_login.html', all_problems=all_problems_for_filter)

@app.route('/admin/logout')
@login_required
def admin_logout():
    session.pop('logged_in', None)
    flash('You have been logged out.', 'info')
    return redirect(url_for('admin_login'))

@app.route('/admin')
@login_required
def admin_dashboard():
    vespa_categories_from_db, all_videos = load_data()
    all_problems_for_filter = get_all_problems() # Fetch all problems
    
    conn = None
    all_series_for_dashboard = []
    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        cur.execute("SELECT id, series_key, name FROM series ORDER BY name")
        all_series_for_dashboard = cur.fetchall()
    except (psycopg2.Error, Exception) as e_series_fetch:
        print(f"Error fetching series for admin dashboard navbar: {e_series_fetch}")
        # flash('Could not load series list for navbar.', 'warning') # Optional: flash message
    finally:
        if conn:
            if cur: # cur might not be defined if get_db_connection failed
                cur.close()
            conn.close()

    return render_template(
        'admin.html', 
        videos=all_videos, 
        vespa_categories=vespa_categories_from_db,
        supported_platforms=SUPPORTED_PLATFORMS,
        all_series=all_series_for_dashboard,
        all_problems=all_problems_for_filter # Pass problems
    )

@app.route('/admin/add_video', methods=['POST'])
@login_required
def add_video():
    video_id_on_platform = request.form.get('video_id')
    platform = request.form.get('platform')
    title = request.form.get('title')
    category_keys_from_form = request.form.getlist('category_keys')
    series_ids_from_form = request.form.getlist('series_ids')

    if not all([video_id_on_platform, title, platform]):
        flash('Video ID, Platform, and Title are required.', 'danger')
        return redirect(url_for('admin_dashboard'))

    if platform not in SUPPORTED_PLATFORMS:
        flash('Invalid video platform selected.', 'danger')
        return redirect(url_for('admin_dashboard'))

    conn = None
    video_db_id_to_use = None
    was_existing_video = False

    try:
        conn = get_db_connection()
        cur = conn.cursor()

        # Check if video already exists
        cur.execute(
            "SELECT id FROM videos WHERE platform = %s AND video_id_on_platform = %s",
            (platform, video_id_on_platform)
        )
        existing_video_row = cur.fetchone()

        if existing_video_row:
            video_db_id_to_use = existing_video_row[0]
            was_existing_video = True
            # If it's an existing video, its title is NOT updated here. Users should use Edit for that.
            # We only update assignments if new ones are provided in the form.

            # Handle Category Assignments for Existing Video
            if category_keys_from_form: # Only update categories if new ones are actually submitted
                cur.execute("DELETE FROM video_category_assignments WHERE video_db_id = %s", (video_db_id_to_use,))
                for cat_key in category_keys_from_form:
                    try:
                        cur.execute(
                            "INSERT INTO video_category_assignments (video_db_id, category_db_key) VALUES (%s, %s)",
                            (video_db_id_to_use, cat_key)
                        )
                    except psycopg2.errors.ForeignKeyViolation:
                        flash(f"Warning: Could not assign category '{cat_key}' to video '{title}'. Category might not exist.", "warning")
                    except psycopg2.errors.UniqueViolation:
                        pass # Should be fine since we deleted first
            # If category_keys_from_form is empty, existing categories are preserved.

            # Handle Series Assignments for Existing Video
            if series_ids_from_form: # Only update series if new ones are actually submitted
                cur.execute("DELETE FROM video_series_assignments WHERE video_db_id = %s", (video_db_id_to_use,))
                for series_id_str in series_ids_from_form:
                    try:
                        series_id = int(series_id_str)
                        cur.execute(
                            "INSERT INTO video_series_assignments (video_db_id, series_db_id) VALUES (%s, %s)",
                            (video_db_id_to_use, series_id)
                        )
                    except psycopg2.errors.ForeignKeyViolation:
                        flash(f"Warning: Could not assign series ID '{series_id}' to video '{title}'. Series might not exist.", "warning")
                    except psycopg2.errors.UniqueViolation:
                        pass # Should be fine
                    except ValueError:
                        flash(f"Warning: Invalid series ID '{series_id_str}' provided for existing video.", "warning")
            # If series_ids_from_form is empty, existing series are preserved.

        else: # Video does not exist, create it new
            cur.execute(
                "INSERT INTO videos (platform, video_id_on_platform, title) VALUES (%s, %s, %s) RETURNING id",
                (platform, video_id_on_platform, title)
            )
            new_video_db_id_row = cur.fetchone()
            if new_video_db_id_row:
                video_db_id_to_use = new_video_db_id_row[0]
            else:
                # Should not happen if INSERT was successful and RETURNING id was used, but as a safeguard:
                conn.rollback()
                flash('Error creating new video record.', 'danger')
                return redirect(url_for('admin_dashboard'))
            
            # For new videos, assign categories and series as submitted
            if video_db_id_to_use and category_keys_from_form:
                for cat_key in category_keys_from_form:
                    try:
                        cur.execute(
                            "INSERT INTO video_category_assignments (video_db_id, category_db_key) VALUES (%s, %s)",
                            (video_db_id_to_use, cat_key)
                        )
                    except psycopg2.errors.ForeignKeyViolation:
                        flash(f"Warning: Could not assign category '{cat_key}' to new video '{title}'. Category might not exist.", "warning")
                    except psycopg2.errors.UniqueViolation:
                        flash(f"Warning: New video '{title}' already assigned to category '{cat_key}'. (Should be rare)", "warning")
            
            if video_db_id_to_use and series_ids_from_form:
                for series_id_str in series_ids_from_form:
                    try:
                        series_id = int(series_id_str)
                        cur.execute(
                            "INSERT INTO video_series_assignments (video_db_id, series_db_id) VALUES (%s, %s)",
                            (video_db_id_to_use, series_id)
                        )
                    except psycopg2.errors.ForeignKeyViolation:
                        flash(f"Warning: Could not assign series ID '{series_id}' to new video '{title}'. Series might not exist.", "warning")
                    except psycopg2.errors.UniqueViolation:
                        flash(f"Warning: New video '{title}' already assigned to series ID '{series_id}'. (Should be rare)", "warning")
                    except ValueError:
                        flash(f"Warning: Invalid series ID '{series_id_str}' provided for new video.", "warning")

        # Commit happens outside the if/else for existing/new video logic
        conn.commit()
        if was_existing_video:
            flash(f'Assignments for existing video \'{title}\' updated successfully!', 'success')
        else:
            flash(f'Video \'{title}\' added and assigned successfully!', 'success')

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
    video_db_id = None 
    all_series_for_form = [] 
    assigned_series_ids = [] 
    all_problems_for_filter = get_all_problems() # Fetch problems

    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)

        # Fetch all available series for the form selector
        cur.execute("SELECT id, name, series_key FROM series ORDER BY name")
        all_series_for_form = cur.fetchall()

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

        # Fetch current series assignments for this video
        cur.execute(
            "SELECT series_db_id FROM video_series_assignments WHERE video_db_id = %s",
            (video_db_id,)
        )
        assigned_series_rows = cur.fetchall()
        assigned_series_ids = [row['series_db_id'] for row in assigned_series_rows]

        # Fetch all available categories for the form
        cur.execute("SELECT category_key, name FROM categories ORDER BY name")
        all_categories_list = cur.fetchall()
        all_categories_for_template = {row['category_key']: {'name': row['name']} for row in all_categories_list}

        if request.method == 'POST':
            new_title = request.form.get('title')
            new_category_keys = request.form.getlist('category_keys')
            new_series_ids = request.form.getlist('series_ids') # Get selected series IDs

            if not new_title:
                flash('Title cannot be empty.', 'danger')
                return render_template(
                    'admin_edit_video.html', 
                    video_to_edit=video_to_edit, 
                    all_categories=all_categories_for_template, 
                    supported_platforms=SUPPORTED_PLATFORMS, 
                    platform=platform, 
                    video_id=video_id_on_platform_from_url,
                    all_series=all_series_for_form, 
                    assigned_series_ids=assigned_series_ids,
                    all_problems=all_problems_for_filter # Pass problems
                )

            # Start transaction for update
            # Update video title
            cur.execute(
                "UPDATE videos SET title = %s WHERE id = %s",
                (new_title, video_db_id)
            )

            # Update category assignments
            # 1. Delete existing assignments for this video
            cur.execute("DELETE FROM video_category_assignments WHERE video_db_id = %s", (video_db_id,))
            
            # 2. Insert new category assignments
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
            
            # Update series assignments
            # 1. Delete existing series assignments for this video
            cur.execute("DELETE FROM video_series_assignments WHERE video_db_id = %s", (video_db_id,))
            # 2. Insert new series assignments
            if new_series_ids:
                for series_id_str in new_series_ids:
                    try:
                        series_id = int(series_id_str)
                        cur.execute(
                            "INSERT INTO video_series_assignments (video_db_id, series_db_id) VALUES (%s, %s)",
                            (video_db_id, series_id)
                        )
                    except psycopg2.errors.ForeignKeyViolation:
                        flash(f"Warning: Could not assign series ID '{series_id}' to video '{new_title}'. Series may not exist.", "warning")
                        print(f"ForeignKeyViolation: edit_video - Could not assign series ID '{series_id}' to video DB ID {video_db_id}")
                    except ValueError:
                        flash(f"Warning: Invalid series ID '{series_id_str}' submitted.", "warning")
                        print(f"ValueError: edit_video - Invalid series ID '{series_id_str}' for video DB ID {video_db_id}")

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
    return render_template(
        'admin_edit_video.html', 
        video_to_edit=video_to_edit, 
        all_categories=all_categories_for_template, 
        supported_platforms=SUPPORTED_PLATFORMS, 
        platform=platform, 
        video_id=video_id_on_platform_from_url,
        all_series=all_series_for_form, 
        assigned_series_ids=assigned_series_ids,
        all_problems=all_problems_for_filter # Pass problems
    )

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

@app.route('/admin/series', methods=['GET', 'POST'])
@login_required
def admin_manage_series():
    conn = None
    all_problems_for_filter = get_all_problems() # Fetch problems
    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)

        if request.method == 'POST':
            series_key = request.form.get('series_key')
            name = request.form.get('name')
            description = request.form.get('description', '')
            is_featured = 'is_featured' in request.form # Checkbox value

            if not series_key or not name:
                flash('Series Key and Name are required.', 'danger')
            else:
                try:
                    # If is_featured is true, first set all other series to not featured
                    if is_featured:
                        cur.execute("UPDATE series SET is_featured = FALSE WHERE is_featured = TRUE")
                    
                    cur.execute(
                        "INSERT INTO series (series_key, name, description, is_featured) VALUES (%s, %s, %s, %s)",
                        (series_key, name, description, is_featured)
                    )
                    conn.commit()
                    flash(f'Series \'{name}\' added successfully!', 'success')
                except psycopg2.errors.UniqueViolation:
                    conn.rollback()
                    flash(f'Error: Series Key \'{series_key}\' already exists.', 'danger')
                except (psycopg2.Error, Exception) as e_insert:
                    conn.rollback()
                    flash(f'Database error adding series: {e_insert}', 'danger')
                    print(f"Database error in admin_manage_series (POST): {e_insert}")
            return redirect(url_for('admin_manage_series')) # Redirect to refresh and show list

        # For GET request, fetch all series to display
        cur.execute("SELECT id, series_key, name, description, is_featured, created_at FROM series ORDER BY name")
        all_series = cur.fetchall()

    except (psycopg2.Error, Exception) as e_fetch:
        flash(f'Database error fetching series: {e_fetch}', 'danger')
        print(f"Database error in admin_manage_series (GET): {e_fetch}")
        all_series = [] # Ensure it's an empty list on error
    finally:
        if conn:
            if cur:
                cur.close()
            conn.close()
    
    return render_template('admin_series.html', all_series=all_series, all_problems=all_problems_for_filter)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True) 