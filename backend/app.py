from flask import Flask, request, jsonify
import yt_dlp
from flask_cors import CORS   # ✅ allow frontend (Netlify) to call backend (Render)

app = Flask(__name__)
CORS(app)   # ✅ enable CORS for all routes

@app.route("/")
def home():
    return "✅ Facebook Video Downloader Backend is running"

@app.route("/download", methods=["POST"])
def download_video():
    try:
        data = request.get_json()
        url = data.get("url")

        if not url:
            return jsonify({"success": False, "error": "No URL provided"}), 400

        # yt_dlp options
        ydl_opts = {
            "format": "best",
            "quiet": True,
            "noplaylist": True,
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            video_url = info.get("url", None)

        if not video_url:
            return jsonify({"success": False, "error": "Could not extract video"}), 500

        return jsonify({"success": True, "url": video_url})

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
