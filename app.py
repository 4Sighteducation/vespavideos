import os
from flask import Flask, request, jsonify, render_template
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail
from dotenv import load_dotenv
import datetime

load_dotenv()

app = Flask(__name__)

# VESPA Pillar Categories Data
VESPA_CATEGORIES = {
    "VISION": {
        "name": "VISION",
        "color": "#ff8f00",
        "description": "Connecting present work to future goals. Developing clear aspirations and purpose, building future-mindedness, and empowering students to take control.",
        "videos": [] # Videos will be populated below
    },
    "EFFORT": {
        "name": "EFFORT",
        "color": "#86b4f0",
        "description": "Challenging the myth of effortless success. Focusing on efficient effort, quality and quantity of sustained hard work, and building productive study tools.",
        "videos": []
    },
    "SYSTEMS": {
        "name": "SYSTEMS",
        "color": "#72cb44",
        "description": "Organization as the foundation of success. Structuring information, time management, addressing underperformance through project management, and developing effective habits.",
        "videos": []
    },
    "PRACTICE": {
        "name": "PRACTICE",
        "color": "#7f31a4",
        "description": "Making deliberate practice the cornerstone of improvement. Focusing on *how* to study effectively, implementing research-backed methods, and transforming effort into progress.",
        "videos": [] # Current revision series will go here
    },
    "ATTITUDE": {
        "name": "ATTITUDE",
        "color": "#f032e6",
        "description": "Building psychological resources for academic resilience. Developing confidence, emotional control, academic buoyancy, and cultivating a growth mindset.",
        "videos": []
    },
    "REVISION_SERIES": {
        "name": "Revision Series - Effective Study Strategies",
        "color": "#6c757d", # A neutral color for this general series
        "description": "Ten short videos guiding students through effective study and revision practices, from environment to strategies.",
        "videos": []
    }
}

# Video data: Each video can belong to multiple categories
ALL_VIDEOS_DATA = [
    {"id": "zGDx41A", "title": "1. Managing your Physical Environment", "categories": ["REVISION_SERIES", "SYSTEMS"]}, # Example: Could also fit Systems
    {"id": "avfERD2", "title": "2. Managing your Digital Environment", "categories": ["REVISION_SERIES", "SYSTEMS"]},
    {"id": "gf4fhoE", "title": "3. Will vs Skill - Strategic Study", "categories": ["REVISION_SERIES", "EFFORT", "ATTITUDE"]},
    {"id": "oG2PRXN", "title": "4. Sticky Timetables", "categories": ["REVISION_SERIES", "PRACTICE", "SYSTEMS"]},
    {"id": "QFntkp8", "title": "5. 25min Sprints", "categories": ["REVISION_SERIES", "PRACTICE", "EFFORT"]},
    {"id": "qjmbeU8", "title": "6. Cog P vs Cog A", "categories": ["REVISION_SERIES", "PRACTICE"]},
    {"id": "7WDUM16", "title": "7. High vs Low Utility", "categories": ["REVISION_SERIES", "PRACTICE"]},
    {"id": "4vxb4Z2", "title": "8. Test your Future Self", "categories": ["REVISION_SERIES", "PRACTICE", "VISION"]},
    {"id": "p4ZN47c", "title": "9. Closed Book Notetaking", "categories": ["REVISION_SERIES", "PRACTICE"]},
    {"id": "5AA3b27", "title": "10. Teach your imaginary Class", "categories": ["REVISION_SERIES", "PRACTICE"]}
    # Add more videos here, assigning them to appropriate categories
]

# Populate categories with their videos
for video_data in ALL_VIDEOS_DATA:
    for category_key in video_data["categories"]:
        if category_key in VESPA_CATEGORIES:
            VESPA_CATEGORIES[category_key]["videos"].append(video_data)

# Environment Variables (keep as is)
SENDGRID_API_KEY = os.getenv('SENDGRID_API_KEY')
RECIPIENT_EMAIL = os.getenv('RECIPIENT_EMAIL')
SENDER_EMAIL = os.getenv('SENDER_EMAIL', RECIPIENT_EMAIL)
SENDGRID_TEMPLATE_ID = os.getenv('SENDGRID_TEMPLATE_ID')

# Basic checks (keep as is)
if not SENDGRID_API_KEY: print("Error: SENDGRID_API_KEY not found")
if not RECIPIENT_EMAIL: print("Error: RECIPIENT_EMAIL not found")
# if not SENDGRID_TEMPLATE_ID: print("Error: SENDGRID_TEMPLATE_ID not found for main app") # Might use different template or no template

@app.route('/')
def index():
    message = request.args.get('message')
    error = request.args.get('error')

    day_of_year = datetime.date.today().timetuple().tm_yday
    featured_video = ALL_VIDEOS_DATA[(day_of_year - 1) % len(ALL_VIDEOS_DATA)] if ALL_VIDEOS_DATA else None
    
    # For simplicity, the main marketing page might not use a SendGrid template for form submission by default,
    # or it might use a different one. We'll keep the direct email for now for the form.
    return render_template('index.html', 
                           message=message, 
                           error=error, 
                           featured_video=featured_video, 
                           vespa_categories=VESPA_CATEGORIES,
                           all_videos_data=ALL_VIDEOS_DATA # Pass all video data for potential other uses
                           )

@app.route('/submit', methods=['POST'])
def submit_form():
    name = request.form.get('name')
    email = request.form.get('email')
    school = request.form.get('school', 'Not Provided')
    message_body = request.form.get('message')

    if not SENDGRID_API_KEY or not RECIPIENT_EMAIL or not SENDER_EMAIL:
        print("Server configuration error: Email sending details missing.")
        return render_template('index.html', error='Sorry, server email config error.', vespa_categories=VESPA_CATEGORIES, featured_video=ALL_VIDEOS_DATA[0] if ALL_VIDEOS_DATA else None) # Basic featured video

    if not name or not email or not message_body:
        return render_template('index.html', error='Please fill in all required fields.', vespa_categories=VESPA_CATEGORIES, featured_video=ALL_VIDEOS_DATA[0] if ALL_VIDEOS_DATA else None)

    # Using direct email for this marketing page form, not necessarily a template
    subject = f"New VESPA Academy Enquiry from {name}"
    html_content = f"""
        <h3>New VESPA Academy Website Enquiry</h3>
        <p><strong>Name:</strong> {name}</p>
        <p><strong>Email:</strong> {email}</p>
        <p><strong>School/Organization:</strong> {school}</p>
        <hr>
        <p><strong>Message:</strong></p>
        <p>{message_body.replace('\n', '<br>')}</p>
    """
    mail_to_send = Mail(
        from_email=SENDER_EMAIL,
        to_emails=[RECIPIENT_EMAIL],
        subject=subject,
        html_content=html_content
    )

    try:
        sg = SendGridAPIClient(SENDGRID_API_KEY)
        sg.send(mail_to_send)
        print(f"Enquiry email sent! To: {RECIPIENT_EMAIL}")
        day_of_year = datetime.date.today().timetuple().tm_yday
        featured_video = ALL_VIDEOS_DATA[(day_of_year - 1) % len(ALL_VIDEOS_DATA)] if ALL_VIDEOS_DATA else None
        return render_template('index.html', message='Thank you! Your message has been sent.', vespa_categories=VESPA_CATEGORIES, featured_video=featured_video)
    except Exception as e:
        print(f"Error sending enquiry email: {e}")
        day_of_year = datetime.date.today().timetuple().tm_yday
        featured_video = ALL_VIDEOS_DATA[(day_of_year - 1) % len(ALL_VIDEOS_DATA)] if ALL_VIDEOS_DATA else None
        return render_template('index.html', error='Sorry, an error occurred sending your message.', vespa_categories=VESPA_CATEGORIES, featured_video=featured_video)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True) 