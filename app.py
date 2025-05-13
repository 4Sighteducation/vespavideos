import os
from flask import Flask, request, jsonify, render_template, session, redirect, url_for, flash
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail
from dotenv import load_dotenv
import datetime
import json
from functools import wraps

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv('FLASK_SECRET_KEY', 'your_default_secret_key_here_CHANGE_ME')

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

def load_data():
    try:
        with open('VideoPage/data.json', 'r') as f:
            data = json.load(f)
    except FileNotFoundError:
        flash("data.json not found. Please create it.", "danger")
        return {}, [] 
    except json.JSONDecodeError:
        flash("Error: data.json is not valid JSON.", "danger")
        return {}, []

    categories_from_file = data.get('categories', {})
    all_videos_from_file = data.get('videos', [])
    vespa_categories_with_videos = { k: {**v, 'videos': []} for k, v in categories_from_file.items() }

    for video_data in all_videos_from_file:
        if 'video_id' not in video_data or 'title' not in video_data or 'platform' not in video_data:
            print(f"Skipping video due to missing \'video_id\', \'title\', or \'platform\': {video_data}")
            continue
        if video_data['platform'] not in SUPPORTED_PLATFORMS:
            print(f"Skipping video due to unsupported platform: {video_data}")
            continue
        for category_key in video_data.get("category_keys", []):
            if category_key in vespa_categories_with_videos:
                vespa_categories_with_videos[category_key]['videos'].append(video_data)
            # else: print(f"Warning: Video {video_data.get('video_id')} refers to non-existent category {category_key}")
    return vespa_categories_with_videos, all_videos_from_file

def save_data(data_to_save):
    try:
        with open('VideoPage/data.json', 'w') as f:
            json.dump(data_to_save, f, indent=2)
        return True
    except Exception as e:
        flash(f"Error saving data: {e}", "danger")
        return False

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
    return render_template('index.html', message=message, error=error, featured_video=featured_video, vespa_categories=vespa_categories_data, all_videos_data=all_videos_data, current_year=datetime.date.today().year)

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
    _, all_videos = load_data()
    try:
        with open('VideoPage/data.json', 'r') as f: data = json.load(f)
        categories_from_file = data.get('categories', {})
    except (FileNotFoundError, json.JSONDecodeError) as e:
        flash(f"Error loading categories for admin: {e}", "danger")
        categories_from_file = {}
    return render_template('admin.html', videos=all_videos, vespa_categories=categories_from_file, supported_platforms=SUPPORTED_PLATFORMS)

@app.route('/admin/add_video', methods=['POST'])
@login_required
def add_video():
    video_id = request.form.get('video_id')
    platform = request.form.get('platform')
    title = request.form.get('title')
    category_keys = request.form.getlist('category_keys')
    if not all([video_id, title, platform]):
        flash('Video ID, Platform, and Title are required.', 'danger')
        return redirect(url_for('admin_dashboard'))
    if platform not in SUPPORTED_PLATFORMS:
        flash('Invalid video platform selected.', 'danger')
        return redirect(url_for('admin_dashboard'))
    try:
        with open('VideoPage/data.json', 'r') as f: data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        flash(f'Error loading data.json: {e}', 'danger')
        return redirect(url_for('admin_dashboard'))
    if any(v['video_id'] == video_id and v['platform'] == platform for v in data.get('videos', [])):
        flash(f'Video with ID \'{video_id}\' on platform \'{SUPPORTED_PLATFORMS.get(platform, platform)}\' already exists.', 'warning')
        return redirect(url_for('admin_dashboard'))
    new_video = {'video_id': video_id, 'platform': platform, 'title': title, 'category_keys': category_keys}
    data.setdefault('videos', []).append(new_video)
    if save_data(data):
        flash(f'Video \'{title}\' added successfully!', 'success')
    else:
        flash('Failed to save video.', 'danger')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/delete_video/<string:platform>/<string:video_id>', methods=['POST'])
@login_required
def delete_video(platform, video_id):
    try:
        with open('VideoPage/data.json', 'r') as f: data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        flash(f'Error loading data.json: {e}', 'danger')
        return redirect(url_for('admin_dashboard'))
    videos = data.get('videos', [])
    original_length = len(videos)
    videos = [v for v in videos if not (v['video_id'] == video_id and v['platform'] == platform)]
    if len(videos) < original_length:
        data['videos'] = videos
        if save_data(data):
            flash(f'Video \'{video_id}\' ({SUPPORTED_PLATFORMS.get(platform, platform)}) deleted.', 'success')
        else:
            flash('Failed to delete video.', 'danger')
    else:
        flash(f'Video \'{video_id}\' ({SUPPORTED_PLATFORMS.get(platform, platform)}) not found.', 'warning')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/edit_video/<string:platform>/<string:video_id>', methods=['GET', 'POST'])
@login_required
def edit_video(platform, video_id):
    try:
        with open('VideoPage/data.json', 'r') as f: data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        flash(f'Error loading data.json: {e}', 'danger')
        return redirect(url_for('admin_dashboard'))
    videos = data.get('videos', [])
    all_categories = data.get('categories', {})
    video_to_edit = None
    video_index = -1
    for i, v in enumerate(videos):
        if v['video_id'] == video_id and v['platform'] == platform:
            video_to_edit = v
            video_index = i
            break
    if not video_to_edit:
        flash(f'Video \'{video_id}\' ({SUPPORTED_PLATFORMS.get(platform, platform)}) not found.', 'warning')
        return redirect(url_for('admin_dashboard'))
    if request.method == 'POST':
        new_title = request.form.get('title')
        new_category_keys = request.form.getlist('category_keys')
        if not new_title:
            flash('Title cannot be empty.', 'danger')
            return render_template('admin_edit_video.html', video_to_edit=video_to_edit, all_categories=all_categories, supported_platforms=SUPPORTED_PLATFORMS)
        videos[video_index]['title'] = new_title
        videos[video_index]['category_keys'] = new_category_keys
        data['videos'] = videos
        if save_data(data):
            flash(f'Video \'{new_title}\' updated.', 'success')
        else:
            flash('Failed to save updated video.', 'danger')
        return redirect(url_for('admin_dashboard'))
    return render_template('admin_edit_video.html', video_to_edit=video_to_edit, all_categories=all_categories, supported_platforms=SUPPORTED_PLATFORMS)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True) 