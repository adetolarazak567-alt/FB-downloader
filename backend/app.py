from flask import Flask, request, jsonify, redirect
from flask_cors import CORS
import yt_dlp
import time
import threading
import sqlite3
import os
import re
import requests
import io
from flask import send_file

app = Flask(__name__)
CORS(app)

# ====== SQLITE SETUP ======
DB_FILE = "toolifyx_stats.db"

def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()

    c.execute("""
        CREATE TABLE IF NOT EXISTS stats (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            requests INTEGER DEFAULT 0,
            downloads INTEGER DEFAULT 0,
            cache_hits INTEGER DEFAULT 0,
            videos_served INTEGER DEFAULT 0
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS unique_ips (
            ip TEXT PRIMARY KEY
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS download_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ip TEXT,
            url TEXT,
            timestamp INTEGER
        )
    """)

    c.execute("INSERT OR IGNORE INTO stats (id) VALUES (1)")

    conn.commit()
    conn.close()

init_db()

# ====== STATS STORAGE (RAM CACHE + SQLITE SYNC) ======
stats = {
    "requests": 0,
    "downloads": 0,
    "cache_hits": 0,
    "videos_served": 0,
    "unique_ips": set(),
    "download_logs": []
}

cache = {}

# ===== SQLITE HELPERS =====

def increment_stat(field):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute(f"UPDATE stats SET {field} = {field} + 1 WHERE id = 1")
    conn.commit()
    conn.close()

def add_unique_ip(ip):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO unique_ips (ip) VALUES (?)", (ip,))
    conn.commit()
    conn.close()

def add_download_log(ip, url):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute(
        "INSERT INTO download_logs (ip, url, timestamp) VALUES (?, ?, ?)",
        (ip, url, int(time.time()))
    )
    conn.commit()
    conn.close()

def get_db_stats():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()

    c.execute("SELECT requests, downloads, cache_hits, videos_served FROM stats WHERE id=1")
    stats_row = c.fetchone()

    c.execute("SELECT COUNT(*) FROM unique_ips")
    unique_ips = c.fetchone()[0]

    c.execute("SELECT ip, url, timestamp FROM download_logs ORDER BY id DESC LIMIT 100")
    logs = c.fetchall()

    conn.close()

    return {
        "requests": stats_row[0],
        "downloads": stats_row[1],
        "cache_hits": stats_row[2],
        "videos_served": stats_row[3],
        "unique_ips": unique_ips,
        "download_logs": [
            {"ip": log[0], "url": log[1], "timestamp": log[2]}
            for log in logs
        ]
    }

# ====== CLEAN + SHORT RENAME FUNCTION ======

def clean_filename(name):

    name = re.sub(r'[^a-zA-Z0-9 ]', '', name)
    name = re.sub(r'\s+', ' ', name).strip()

    if len(name) > 40:
        name = name[:40]

    return f"{name} ToolifyX Downloader.mp4"


# ====== Helper function with timeout ======

def extract_video(url, result_holder):

    try:

        ydl_opts = {
            "format": "best",
            "quiet": True,
            "noplaylist": True,
            "socket_timeout": 15,
            "retries": 2,
            "nocheckcertificate": True,
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:

            info = ydl.extract_info(url, download=False)

            result_holder["url"] = info.get("url")

            title = info.get("title", "Video")

            result_holder["title"] = title

    except Exception as e:

        result_holder["error"] = str(e)


def fetch_facebook_video(url):

    if url in cache:

        increment_stat("cache_hits")

        return cache[url]

    result = {}

    t = threading.Thread(
        target=extract_video,
        args=(url, result)
    )

    t.start()

    t.join(timeout=20)

    if t.is_alive():

        return None

    video_url = result.get("url")

    title = result.get("title", "Video")

    if video_url:

        cache[url] = (video_url, title)

        return cache[url]

    return None

# ====== Fetch route (FAST preview) ======

@app.route("/fetch", methods=["POST"])
def fetch_video():

    increment_stat("requests")

    ip = request.remote_addr
    add_unique_ip(ip)

    data = request.get_json()
    url = data.get("url")

    if not url:
        return jsonify({
            "success": False,
            "error": "No URL provided"
        }), 400

    try:

        result = fetch_facebook_video(url)

        if not result:
            return jsonify({
                "success": False,
                "error": "Video not found or timeout"
            }), 408

        video_url, title = result

        filename = clean_filename(title)

        increment_stat("videos_served")

        return jsonify({
            "success": True,
            "url": video_url,
            "filename": filename
        })

    except Exception as e:

        return jsonify({
            "success": False,
            "error": str(e)
        }), 500
# ====== Download route ======

@app.route("/download", methods=["POST"])
def download_video():

    increment_stat("requests")

    ip = request.remote_addr
    add_unique_ip(ip)

    data = request.get_json()
    url = data.get("url")

    if not url:
        return jsonify({"success": False, "error": "No URL provided"}), 400

    try:

        result = fetch_facebook_video(url)

        if not result:
            return jsonify({
                "success": False,
                "error": "Facebook blocked this video or timeout"
            }), 408

        video_url, title = result

        # ✅ use your clean rename function
        filename = clean_filename(title)

        # stream video
        response = requests.get(video_url, stream=True)

        video_stream = io.BytesIO(response.content)

        increment_stat("downloads")
        increment_stat("videos_served")

        add_download_log(ip, url)

        return send_file(
            video_stream,
            as_attachment=True,
            download_name=filename,
            mimetype="video/mp4"
        )

    except Exception as e:

        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


# ====== Stats route ======

@app.route("/stats", methods=["GET"])

def get_stats():

    return jsonify(get_db_stats())


# ====== Start server ======

if __name__ == "__main__":

    app.run(host="0.0.0.0", port=10000, threaded=True)