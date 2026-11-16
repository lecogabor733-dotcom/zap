import os
import socket
import shutil
import tempfile
import ipaddress
from urllib.parse import urlparse

from flask import Flask, request, jsonify, send_file, send_from_directory
import yt_dlp

app = Flask(__name__, static_folder="static")

QUALITIES = {
    "best": "best[ext=mp4]/bv*[ext=mp4]+ba[ext=m4a]/bv*+ba/best",
    "1080": "best[height<=1080][ext=mp4]/bv*[height<=1080]+ba/best[height<=1080]/best",
    "720": "best[height<=720][ext=mp4]/bv*[height<=720]+ba/best[height<=720]/best",
    "480": "best[height<=480][ext=mp4]/bv*[height<=480]+ba/best[height<=480]/best",
    "audio": "bestaudio/best",
}


def safe_url(u: str) -> bool:
    """Only http(s), and never internal/private addresses (SSRF protection)."""
    p = urlparse(u)
    if p.scheme not in ("http", "https") or not p.hostname:
        return False
    try:
        for info in socket.getaddrinfo(p.hostname, None):
            ip = ipaddress.ip_address(info[4][0])
            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
                return False
    except socket.gaierror:
        return False
    return True


@app.get("/")
def index():
    return send_from_directory("static", "index.html")


@app.get("/api/info")
def info():
    url = (request.args.get("url") or "").strip()
    if not safe_url(url):
        return jsonify(error="That doesn't look like a valid link."), 400
    opts = {"quiet": True, "noplaylist": True, "skip_download": True, "socket_timeout": 15}
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            d = ydl.extract_info(url, download=False)
    except Exception as e:
        return jsonify(error="Couldn't read that link. " + str(e).split("\n")[0][:160]), 422
    heights = sorted({f.get("height") for f in d.get("formats", []) if f.get("height")}, reverse=True)
    return jsonify(
        title=d.get("title"),
        thumbnail=d.get("thumbnail"),
        duration=d.get("duration"),
        uploader=d.get("uploader"),
        site=d.get("extractor_key"),
        heights=heights,
    )


@app.get("/api/download")
def download():
    url = (request.args.get("url") or "").strip()
    q = request.args.get("q", "best")
    if not safe_url(url) or q not in QUALITIES:
        return "Bad request", 400

    tmp = tempfile.mkdtemp(prefix="vd_")
    opts = {
        "quiet": True,
        "noplaylist": True,
        "format": QUALITIES[q],
        "outtmpl": os.path.join(tmp, "%(title).80B.%(ext)s"),
        "concurrent_fragment_downloads": 8,  # speed
        "http_chunk_size": 10 * 1024 * 1024,
        "merge_output_format": "mp4",
        "restrictfilenames": False,
    }
    if q == "audio" and shutil.which("ffmpeg"):
        opts["postprocessors"] = [{"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "192"}]

    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            ydl.extract_info(url, download=True)
        files = os.listdir(tmp)
        if not files:
            raise RuntimeError("nothing downloaded")
        path = os.path.join(tmp, files[0])
        resp = send_file(path, as_attachment=True, download_name=files[0])
        resp.call_on_close(lambda: shutil.rmtree(tmp, ignore_errors=True))
        return resp
    except Exception as e:
        shutil.rmtree(tmp, ignore_errors=True)
        return str(e).split("\n")[0][:200], 500


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print(f"\n  ⚡ Running at http://localhost:{port}\n")
    app.run(host="127.0.0.1", port=port, threaded=True)
