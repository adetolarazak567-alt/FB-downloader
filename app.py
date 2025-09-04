import io
import os
import requests
from flask import Flask, request, jsonify, Response
from flask_cors import CORS
from yt_dlp import YoutubeDL

app = Flask(__name__)
CORS(app)  # allow cross-origin from your frontend

YDL_OPTS_INFO = {
    "quiet": True,
    "nocheckcertificate": True,
    "skip_download": True,
    "restrictfilenames": True,
    "geo_bypass": True,
}

def pick_best_mp4(formats):
    """
    Choose a progressive MP4 with both audio+video when possible, otherwise best MP4.
    """
    best = None
    for f in formats or []:
        # Prefer avc/mp4 with both audio+video
        if f.get("ext") == "mp4" and f.get("acodec") != "none" and f.get("vcodec") != "none":
            if not best or (f.get("height", 0) > best.get("height", 0)):
                best = f
    if best:
        return best
    # fallback to any mp4
    for f in formats or []:
        if f.get("ext") == "mp4":
            if not best or (f.get("height", 0) > best.get("height", 0)):
                best = f
    return best

@app.get("/api/info")
def info():
    url = request.args.get("url", "").strip()
    if not url:
        return jsonify({"error": "missing url"}), 400
    try:
        with YoutubeDL(YDL_OPTS_INFO) as ydl:
            info = ydl.extract_info(url, download=False)
        # If it's a playlist-like object, try the first entry
        if "entries" in info and info["entries"]:
            info = info["entries"][0]

        fmt = pick_best_mp4(info.get("formats"))
        if not fmt or not fmt.get("url"):
            return jsonify({"error": "no downloadable mp4 found"}), 404

        title = info.get("title") or "Facebook Video"
        thumb = info.get("thumbnail")
        quality = f"{fmt.get('height','?')}p • MP4" if fmt.get("height") else "MP4"

        return jsonify({
            "title": title,
            "thumbnail": thumb,
            "download_url": fmt["url"],
            "quality": quality
        })
    except Exception as e:
        return jsonify({"error": "extract failed", "detail": str(e)}), 500

@app.get("/api/download")
def download():
    """
    Streams the file to the client so the browser treats it as a download.
    Accepts ?url=<direct_mp4_url> (from /api/info).
    """
    direct = request.args.get("url", "").strip()
    if not direct:
        return jsonify({"error": "missing url"}), 400

    try:
        # Stream from source and pipe to client
        src = requests.get(direct, stream=True, timeout=30)
        src.raise_for_status()
        headers = {
            "Content-Type": src.headers.get("Content-Type", "video/mp4"),
            "Content-Disposition": 'attachment; filename="facebook-video.mp4"',
        }
        return Response(src.iter_content(chunk_size=1024*256), headers=headers)
    except Exception as e:
        return jsonify({"error": "download failed", "detail": str(e)}), 502

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8000"))
    app.run(host="0.0.0.0", port=port)
