import json
import re
import urllib.request
import urllib.error
from http.server import BaseHTTPRequestHandler
import yt_dlp

COBALT_INSTANCES = [
    "https://cobalt.api.timelessnesses.me",
    "https://cobalt.synzr.space",
    "https://cob.frytki.pl",
    "https://cobalt.ggtyler.dev",
]

QUALITY_FORMATS = {
    "max":   "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
    "1080":  "bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/best[height<=1080][ext=mp4]/best",
    "720":   "bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/best[height<=720][ext=mp4]/best",
    "480":   "bestvideo[height<=480][ext=mp4]+bestaudio[ext=m4a]/best[height<=480][ext=mp4]/best",
    "360":   "bestvideo[height<=360][ext=mp4]+bestaudio[ext=m4a]/best[height<=360][ext=mp4]/best",
    "audio": "bestaudio[ext=m4a]/bestaudio",
}

def is_youtube(url):
    return bool(re.search(r"youtube\.com|youtu\.be", url))

def get_yt_dlp_result(url, quality="max"):
    fmt = QUALITY_FORMATS.get(quality, QUALITY_FORMATS["max"])
    ydl_opts = {
        "format": fmt,
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "skip_download": True,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)

    # Get the direct URL from the best format
    download_url = None
    if "url" in info:
        download_url = info["url"]
    elif "formats" in info:
        for f in reversed(info["formats"]):
            if f.get("url"):
                download_url = f["url"]
                break

    return {
        "downloadUrl": download_url,
        "title": info.get("title", "video"),
        "thumbnail": info.get("thumbnail"),
        "duration": info.get("duration"),
        "uploader": info.get("uploader") or info.get("channel"),
        "source": "yt-dlp",
    }

def get_cobalt_url(url):
    for instance in COBALT_INSTANCES:
        try:
            payload = json.dumps({
                "url": url,
                "vQuality": "max",
                "filenamePattern": "basic",
            }).encode("utf-8")
            req = urllib.request.Request(
                f"{instance}/api/json",
                data=payload,
                headers={
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                },
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=6) as resp:
                data = json.loads(resp.read())

            status = data.get("status")
            if status in ("stream", "redirect") and data.get("url"):
                return {"downloadUrl": data["url"], "instance": instance}
            if status == "picker" and data.get("picker"):
                items = data["picker"]
                video = next((i for i in items if i.get("type") == "video"), None)
                picked_url = (video or items[0]).get("url")
                if picked_url:
                    return {"downloadUrl": picked_url, "instance": instance}
        except Exception:
            continue

    raise Exception("All Cobalt instances failed or platform is unsupported.")

def cors_headers():
    return {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "POST, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type",
        "Content-Type": "application/json",
    }

class handler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        self.send_response(200)
        for k, v in cors_headers().items():
            self.send_header(k, v)
        self.end_headers()

    def do_POST(self):
        try:
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length) or b"{}")
            url = body.get("url", "").strip()
            quality = body.get("quality", "max")

            if not url:
                self._respond(400, {"success": False, "error": "No URL provided"})
                return

            if is_youtube(url):
                result = get_yt_dlp_result(url, quality)
                if not result.get("downloadUrl"):
                    raise Exception("yt-dlp returned no download URL")
                self._respond(200, {"success": True, **result})
            else:
                result = get_cobalt_url(url)
                self._respond(200, {
                    "success": True,
                    "downloadUrl": result["downloadUrl"],
                    "info": {
                        "title": "video",
                        "source": f"cobalt ({result['instance']})",
                    },
                })

        except Exception as e:
            self._respond(500, {"success": False, "error": str(e)})

    def _respond(self, status, data):
        body = json.dumps(data).encode("utf-8")
        self.send_response(status)
        for k, v in cors_headers().items():
            self.send_header(k, v)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass  # Suppress default access logs
