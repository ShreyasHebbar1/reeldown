import os
import threading
import urllib.request
import json
import hashlib
from datetime import datetime
from flask import Flask, request, jsonify, render_template, Response, stream_with_context, send_from_directory, session, redirect, url_for
import yt_dlp

app = Flask(__name__, static_folder="static", template_folder="static")

# Configure Data Directory (important for persistent volumes on deployment platforms like Render)
DATA_DIR = os.environ.get("DATA_DIR", os.getcwd())
if DATA_DIR != os.getcwd():
    os.makedirs(DATA_DIR, exist_ok=True)

COOKIES_FILE = os.path.join(DATA_DIR, "cookies.txt")
STATS_FILE = os.path.join(DATA_DIR, "stats.json")
COOKIE_STATUS_FILE = os.path.join(DATA_DIR, "cookie_status.json")
SECRETS_FILE = os.path.join(DATA_DIR, "secrets.json")

# Admin Credentials and Secret Key Settings
ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "terimaaki123")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "raju123*")
app.secret_key = os.environ.get("SECRET_KEY", "reelflow_secure_admin_session_key_2026")

try:
    if os.path.exists(SECRETS_FILE):
        with open(SECRETS_FILE, "r", encoding="utf-8") as f:
            secrets_data = json.load(f)
            ADMIN_USERNAME = secrets_data.get("admin_username", ADMIN_USERNAME)
            ADMIN_PASSWORD = secrets_data.get("admin_password", ADMIN_PASSWORD)
            if "secret_key" in secrets_data:
                app.secret_key = secrets_data["secret_key"]
except Exception as e:
    print(f"Error loading admin credentials or secret key: {e}")

# Stats telemetry lock and file
stats_lock = threading.Lock()


def parse_user_agent(ua_string):
    if not ua_string:
        return "Other", "Other"
        
    ua_lower = ua_string.lower()
    
    # Platform / OS
    if "windows" in ua_lower:
        platform = "Windows"
    elif "macintosh" in ua_lower or "mac os" in ua_lower:
        if "iphone" in ua_lower or "ipad" in ua_lower or "ipod" in ua_lower:
            platform = "iOS"
        else:
            platform = "macOS"
    elif "android" in ua_lower:
        platform = "Android"
    elif "iphone" in ua_lower or "ipad" in ua_lower or "ipod" in ua_lower:
        platform = "iOS"
    elif "linux" in ua_lower:
        platform = "Linux"
    else:
        platform = "Other"
        
    # Browser
    if "edg" in ua_lower:
        browser = "Edge"
    elif "chrome" in ua_lower and "safari" in ua_lower and "opr" not in ua_lower and "opt" not in ua_lower:
        browser = "Chrome"
    elif "firefox" in ua_lower:
        browser = "Firefox"
    elif "safari" in ua_lower and "chrome" not in ua_lower:
        browser = "Safari"
    elif "opr" in ua_lower or "opera" in ua_lower:
        browser = "Opera"
    else:
        browser = "Other"
        
    return browser, platform

def track_visit(action_type):
    try:
        # Try to get visitor's IP and User-Agent
        ip_addr = request.headers.get('X-Forwarded-For', request.remote_addr or '127.0.0.1')
        if ',' in ip_addr:
            ip_addr = ip_addr.split(',')[0].strip()
            
        ua_str = request.headers.get('User-Agent', '')
        
        # Hash IP for privacy
        ip_hash = hashlib.sha256(ip_addr.encode('utf-8')).hexdigest()[:16]
        
        # Get current date
        date_str = datetime.now().strftime("%Y-%m-%d")
        
        # Parse User-Agent
        browser, platform = parse_user_agent(ua_str)
        
        with stats_lock:
            stats = {
                "total_page_views": 0,
                "total_api_info": 0,
                "total_api_download": 0,
                "daily": {},
                "browsers": {},
                "platforms": {}
            }
            
            if os.path.exists(STATS_FILE):
                try:
                    with open(STATS_FILE, 'r', encoding='utf-8') as f:
                        loaded = json.load(f)
                        for k in stats.keys():
                            if k in loaded:
                                stats[k] = loaded[k]
                except Exception:
                    pass
                    
            # Update metrics
            if action_type == 'page_view':
                stats["total_page_views"] += 1
            elif action_type == 'api_info':
                stats["total_api_info"] += 1
            elif action_type == 'api_download':
                stats["total_api_download"] += 1
                
            # Ensure daily structure
            if date_str not in stats["daily"]:
                stats["daily"][date_str] = {
                    "page_views": 0,
                    "api_info": 0,
                    "api_download": 0,
                    "unique_visitors": []
                }
                
            day_stats = stats["daily"][date_str]
            
            if action_type == 'page_view':
                day_stats["page_views"] = day_stats.get("page_views", 0) + 1
            elif action_type == 'api_info':
                day_stats["api_info"] = day_stats.get("api_info", 0) + 1
            elif action_type == 'api_download':
                day_stats["api_download"] = day_stats.get("api_download", 0) + 1
                
            # Add to unique visitors if not already there
            if "unique_visitors" not in day_stats:
                day_stats["unique_visitors"] = []
            if ip_hash not in day_stats["unique_visitors"]:
                day_stats["unique_visitors"].append(ip_hash)
                
            # Update browser & platform charts (only on page views to avoid skewing)
            if action_type == 'page_view':
                stats["browsers"][browser] = stats["browsers"].get(browser, 0) + 1
                stats["platforms"][platform] = stats["platforms"].get(platform, 0) + 1
            
            # Save stats
            with open(STATS_FILE, 'w', encoding='utf-8') as f:
                json.dump(stats, f)
    except Exception as e:
        print(f"Tracking error: {e}")

def format_duration(seconds):
    if not seconds:
        return "Unknown"
    mins = int(seconds) // 60
    secs = int(seconds) % 60
    return f"{mins}:{secs:02d}"

def get_cookies_expiry_date():
    if not os.path.exists(COOKIES_FILE):
        return None
        
    try:
        sessionid_expiry = None
        other_expiry = []
        
        with open(COOKIES_FILE, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                parts = line.split('\t')
                if len(parts) >= 7:
                    name = parts[5]
                    try:
                        exp = int(parts[4])
                    except ValueError:
                        continue
                        
                    if exp > 0:
                        if name == 'sessionid':
                            sessionid_expiry = exp
                        else:
                            other_expiry.append(exp)
                            
        # Use sessionid expiry if found, else fallback to max of other expiry dates
        expiry_epoch = sessionid_expiry or (max(other_expiry) if other_expiry else None)
        if expiry_epoch:
            dt = datetime.fromtimestamp(expiry_epoch)
            return dt.strftime("%Y-%m-%d %H:%M:%S")
    except Exception as e:
        print(f"Error parsing cookies expiry: {e}")
        
    return None

def apply_cookies_to_ytdl(ydl_opts, browser_cookies=None):
    if os.path.exists(COOKIES_FILE) and os.path.getsize(COOKIES_FILE) > 0:
        ydl_opts['cookiefile'] = COOKIES_FILE
        print("Using server-side cookies.txt configuration")
    elif browser_cookies and browser_cookies != 'none':
        ydl_opts['cookiesfrombrowser'] = (browser_cookies,)
        print(f"Using cookies from browser: {browser_cookies}")

@app.route('/')
def index():
    track_visit('page_view')
    return render_template("index.html")

@app.route('/instagram-reels-downloader')
def instagram_reels_downloader():
    return redirect('/', code=301)

@app.route('/reels-downloader')
def reels_downloader():
    return redirect('/', code=301)

@app.route('/instagram-video-downloader')
def instagram_video_downloader():
    return redirect('/', code=301)

@app.route('/download-instagram-reels')
def download_instagram_reels():
    track_visit('page_view')
    return render_template("download-instagram-reels.html")

@app.route('/instagram-reels-downloader-iphone')
def instagram_reels_downloader_iphone():
    track_visit('page_view')
    return render_template("instagram-reels-downloader-iphone.html")

@app.route('/instagram-reels-downloader-android')
def instagram_reels_downloader_android():
    track_visit('page_view')
    return render_template("instagram-reels-downloader-android.html")

@app.route('/privacy')
def privacy():
    track_visit('page_view')
    return render_template("privacy.html")

@app.route('/terms')
def terms():
    track_visit('page_view')
    return render_template("terms.html")

@app.route('/contact')
def contact():
    track_visit('page_view')
    return render_template("contact.html")

@app.route('/api/info', methods=['POST'])
def get_info():
    track_visit('api_info')
    data = request.json or {}
    url = data.get('url')
    browser_cookies = data.get('cookies')
    
    if not url:
        return jsonify({"error": "No URL provided"}), 400
        
    ydl_opts = {
        'skip_download': True,
        'nocheckcertificate': True,
        'quiet': True,
        'no_warnings': True,
    }
    
    apply_cookies_to_ytdl(ydl_opts, browser_cookies)
        
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            
            # Handle playlist/carousel entries if returned
            if 'entries' in info:
                valid_entries = [e for e in info['entries'] if e]
                if valid_entries:
                    # Find the first entry that contains video format URLs
                    video_entry = None
                    for entry in valid_entries:
                        if entry.get('url') or entry.get('formats'):
                            video_entry = entry
                            break
                    info = video_entry or valid_entries[0]
            
            # Extract video URL with progressive formats fallbacks
            video_url = info.get('url')
            if not video_url and info.get('formats'):
                valid_formats = [f for f in info['formats'] if f.get('url')]
                if valid_formats:
                    progressive_formats = [f for f in valid_formats if f.get('vcodec') != 'none' and f.get('acodec') != 'none']
                    if progressive_formats:
                        video_url = progressive_formats[-1]['url']
                    else:
                        video_url = valid_formats[-1]['url']
            
            if not video_url:
                return jsonify({"error": "No downloadable video found in this post. Make sure it contains a video, not just photos."}), 400

            return jsonify({
                "title": info.get('title', 'Instagram Video'),
                "thumbnail": info.get('thumbnail', ''),
                "duration": format_duration(info.get('duration', 0)),
                "uploader": info.get('uploader', 'Unknown Creator'),
                "url": url,
                "video_url": video_url  # Direct video stream URL on CDN
            })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/download-stream')
def download_stream():
    track_visit('api_download')
    video_url = request.args.get('url')
    filename = request.args.get('filename', 'video.mp4')
    if not video_url:
        return "Missing url parameter", 400
        
    try:
        req = urllib.request.Request(
            video_url, 
            headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
        )
        response = urllib.request.urlopen(req, timeout=20)
        
        def generate():
            while True:
                chunk = response.read(16384)  # Stream in 16KB chunks
                if not chunk:
                    break
                yield chunk
                
        # Format a safe filename
        safe_filename = "".join([c for c in filename if c.isalpha() or c.isdigit() or c in ' .-_']).strip()
        if not safe_filename.endswith('.mp4'):
            safe_filename += '.mp4'
            
        headers = {
            'Content-Disposition': f'attachment; filename="{safe_filename}"',
            'Content-Type': 'video/mp4'
        }
        return Response(stream_with_context(generate()), headers=headers)
    except Exception as e:
        return f"Error streaming video: {e}", 500



@app.route('/api/proxy-image')
def proxy_image():
    img_url = request.args.get('url')
    if not img_url:
        return "Missing url parameter", 400
    try:
        req = urllib.request.Request(
            img_url, 
            headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        )
        with urllib.request.urlopen(req, timeout=10) as response:
            img_data = response.read()
            content_type = response.headers.get('Content-Type', 'image/jpeg')
            return img_data, 200, {'Content-Type': content_type}
    except Exception as e:
        return f"Error proxying image: {e}", 500

@app.route('/robots.txt')
def robots():
    return send_from_directory(app.static_folder, 'robots.txt')

@app.route('/sitemap.xml')
def sitemap():
    return send_from_directory(app.static_folder, 'sitemap.xml')

# --- Admin Panel & Telemetry APIs ---
@app.route('/admin')
def admin_panel():
    logged_in = session.get('admin_logged_in', False)
    return render_template("admin.html", logged_in=logged_in)

@app.route('/admin/login', methods=['POST'])
def admin_login():
    data = request.json or {}
    username = data.get('username')
    password = data.get('password')
    
    if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
        session['admin_logged_in'] = True
        return jsonify({"success": True})
    else:
        return jsonify({"success": False, "error": "Invalid credentials"}), 401

@app.route('/admin/logout')
def admin_logout():
    session.pop('admin_logged_in', None)
    return redirect(url_for('admin_panel'))

def verify_instagram_cookies():
    cookies_path = COOKIES_FILE
    if not os.path.exists(cookies_path) or os.path.getsize(cookies_path) == 0:
        return False, "No cookies file found or file is empty."
        
    try:
        cookie_items = []
        with open(cookies_path, 'r', encoding='utf-8') as f:
            for line in f:
                if line.startswith('#') or not line.strip():
                    continue
                parts = line.strip().split('\t')
                if len(parts) >= 7:
                    cookie_items.append(f"{parts[5]}={parts[6]}")
                    
        if not cookie_items:
            return False, "No valid Netscape format cookies parsed."
            
        cookie_header = "; ".join(cookie_items)
        
        req = urllib.request.Request(
            "https://www.instagram.com/accounts/edit/",
            headers={
                "Cookie": cookie_header,
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            }
        )
        
        with urllib.request.urlopen(req, timeout=10) as resp:
            final_url = resp.geturl()
            if "accounts/login" in final_url:
                return False, "Expired or invalid (Instagram redirected to login)."
            else:
                return True, "Active and valid."
    except Exception as e:
        return False, f"Verification failed: {str(e)}"

@app.route('/admin/api/stats')
def admin_get_stats():
    if not session.get('admin_logged_in'):
        return jsonify({"error": "Unauthorized"}), 401
        
    stats_data = {
        "total_page_views": 0,
        "total_api_info": 0,
        "total_api_download": 0,
        "daily": {},
        "browsers": {},
        "platforms": {}
    }
    
    if os.path.exists(STATS_FILE):
        try:
            with open(STATS_FILE, 'r', encoding='utf-8') as f:
                stats_data = json.load(f)
        except Exception:
            pass
            
    # Include history for the admin panel log table
    history_data = []
    
    # Check if we need to perform the daily auto validity check (if last check was > 24 hours ago)
    cookie_status = None
    status_path = COOKIE_STATUS_FILE
    need_validation = True
    
    if os.path.exists(status_path):
        try:
            with open(status_path, 'r', encoding='utf-8') as f:
                cookie_status = json.load(f)
                last_updated_str = cookie_status.get("last_updated") or cookie_status.get("last_attempt_time")
                if last_updated_str:
                    last_updated = datetime.strptime(last_updated_str, "%Y-%m-%d %H:%M:%S")
                    if (datetime.now() - last_updated).total_seconds() < 86400:
                        need_validation = False
        except Exception:
            pass
            
    if need_validation:
        def bg_check():
            valid, message = verify_instagram_cookies()
            status_data = {
                "status": "success" if valid else "error",
                "last_updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "last_success_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S") if valid else None,
                "error_message": None if valid else message
            }
            if not valid and os.path.exists(status_path):
                try:
                    with open(status_path, 'r', encoding='utf-8') as f:
                        old = json.load(f)
                        status_data["last_success_time"] = old.get("last_success_time")
                except:
                    pass
            try:
                with open(status_path, 'w', encoding='utf-8') as f:
                    json.dump(status_data, f, indent=4, ensure_ascii=False)
            except:
                pass
        threading.Thread(target=bg_check).start()
        
        if not cookie_status:
            cookie_status = {"status": "checking"}
            
    expiry_date = get_cookies_expiry_date()
    if not cookie_status:
        cookie_status = {
            "status": "success" if os.path.exists(COOKIES_FILE) and os.path.getsize(COOKIES_FILE) > 0 else "unknown"
        }
    cookie_status["expires_at"] = expiry_date
            
    return jsonify({
        "stats": stats_data,
        "history": history_data,
        "cookie_status": cookie_status
    })

@app.route('/admin/api/reset-stats', methods=['POST'])
def admin_reset_stats():
    if not session.get('admin_logged_in'):
        return jsonify({"error": "Unauthorized"}), 401
        
    empty_stats = {
        "total_page_views": 0,
        "total_api_info": 0,
        "total_api_download": 0,
        "daily": {},
        "browsers": {},
        "platforms": {}
    }
    
    with stats_lock:
        try:
            with open(STATS_FILE, 'w', encoding='utf-8') as f:
                json.dump(empty_stats, f, indent=4, ensure_ascii=False)
        except Exception as e:
            return jsonify({"error": f"Failed to reset stats: {e}"}), 500
            
    return jsonify({"success": True})

@app.route('/admin/api/check-cookies', methods=['POST'])
def admin_check_cookies():
    if not session.get('admin_logged_in'):
        return jsonify({"error": "Unauthorized"}), 401
        
    valid, message = verify_instagram_cookies()
    
    status_path = COOKIE_STATUS_FILE
    status_data = {
        "status": "success" if valid else "error",
        "last_updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "last_success_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S") if valid else None,
        "error_message": None if valid else message
    }
    
    if not valid and os.path.exists(status_path):
        try:
            with open(status_path, 'r', encoding='utf-8') as f:
                old = json.load(f)
                status_data["last_success_time"] = old.get("last_success_time")
        except:
            pass
            
    try:
        with open(status_path, 'w', encoding='utf-8') as f:
            json.dump(status_data, f, indent=4, ensure_ascii=False)
    except:
        pass
        
    if valid:
        return jsonify({"success": True, "message": message})
    else:
        return jsonify({"success": False, "error": message})

@app.route('/admin/api/change-password', methods=['POST'])
def admin_change_password():
    if not session.get('admin_logged_in'):
        return jsonify({"error": "Unauthorized"}), 401
        
    data = request.json or {}
    new_password = data.get('new_password')
    new_username = data.get('new_username')
    
    if not new_password:
        return jsonify({"error": "Missing new password"}), 400
        
    global ADMIN_PASSWORD, ADMIN_USERNAME
    
    # Load existing secrets.json if it exists
    secrets_data = {}
    if os.path.exists(SECRETS_FILE):
        try:
            with open(SECRETS_FILE, "r", encoding="utf-8") as f:
                secrets_data = json.load(f)
        except:
            pass
            
    # Update values
    secrets_data["admin_password"] = new_password
    ADMIN_PASSWORD = new_password
    
    if new_username:
        secrets_data["admin_username"] = new_username
        ADMIN_USERNAME = new_username
        
    try:
        with open(SECRETS_FILE, "w", encoding="utf-8") as f:
            json.dump(secrets_data, f, indent=4, ensure_ascii=False)
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": f"Failed to save secrets: {e}"}), 500

@app.route('/admin/api/upload-cookies', methods=['POST'])
def admin_upload_cookies():
    if not session.get('admin_logged_in'):
        return jsonify({"error": "Unauthorized"}), 401
        
    data = request.json or {}
    cookies_text = data.get('cookies_text')
    
    if not cookies_text:
        return jsonify({"error": "No cookie content provided"}), 400
        
    try:
        # Save to cookies.txt in workspace root
        cookies_path = COOKIES_FILE
        with open(cookies_path, 'w', encoding='utf-8') as f:
            f.write(cookies_text)
            
        # Update cookie_status.json
        status_path = COOKIE_STATUS_FILE
        status_data = {
            "status": "success",
            "last_updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "last_success_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "error_message": None
        }
        with open(status_path, 'w', encoding='utf-8') as f:
            json.dump(status_data, f, indent=4, ensure_ascii=False)
            
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": f"Failed to save cookies: {e}"}), 500

if __name__ == '__main__':
    app.run(host='127.0.0.1', port=8080, debug=True)
