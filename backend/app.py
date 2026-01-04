from flask import Flask, request, jsonify
from flask_cors import CORS
import yt_dlp
import time

app = Flask(__name__)
CORS(app)

# ====== STATS STORAGE ======
stats = {
    "requests": 0,
    "downloads": 0,
    "cache_hits": 0,
    "videos_served": 0,
    "unique_ips": set(),
    "download_logs": []
}

cache = {}  # url -> video_url

# ====== Helper function to fetch video ======
def fetch_facebook_video(url):
    if url in cache:
        stats["cache_hits"] += 1
        return cache[url]

    ydl_opts = {
        "format": "best",
        "quiet": True,
        "noplaylist": True,
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)
        video_url = info.get("url")
        if video_url:
            cache[url] = video_url
        return video_url

# ====== Download route ======
@app.route("/download", methods=["POST"])
def download_video():
    stats["requests"] += 1
    ip = request.remote_addr

    data = request.get_json()
    url = data.get("url")
    if not url:
        return jsonify({"success": False, "error": "No URL provided"}), 400

    stats["unique_ips"].add(ip)

    try:
        video_url = fetch_facebook_video(url)
        if not video_url:
            return jsonify({"success": False, "error": "Could not extract video"}), 500

        stats["downloads"] += 1
        stats["videos_served"] += 1

        stats["download_logs"].append({
            "ip": ip,
            "url": url,
            "timestamp": int(time.time())
        })

        return jsonify({"success": True, "url": video_url})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

# ====== Stats route for admin ======
@app.route("/stats", methods=["GET"])
def get_stats():
    return jsonify({
        "requests": stats["requests"],
        "downloads": stats["downloads"],
        "cache_hits": stats["cache_hits"],
        "videos_served": stats["videos_served"],
        "unique_ips": len(stats["unique_ips"]),
        "download_logs": stats["download_logs"]
    })

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000, threaded=True)