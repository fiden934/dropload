import json
import re
import urllib.request
from http.server import BaseHTTPRequestHandler

# Invidious public instances for YouTube
INVIDIOUS_INSTANCES = [
    "https://inv.nadeko.net",
    "https://invidious.fdn.fr",
    "https://yt.artemislena.eu",
    "https://invidious.privacyredirect.com",
    "https://invidious.nerdvpn.de",
]

# Cobalt instances for non-YouTube platforms
COBALT_INSTANCES = [
    "https://cobalt.api.timelessnesses.me",
    "https://cobalt.synzr.space",
    "https://cob.frytki.pl",
    "https://cobalt.ggtyler.dev",
]

QUALITY_MAP = {
    "max":   9999,
    "1080":  1080,
    "720":   720,
    "480":   480,
    "360":   360,
    "audio": 0,
}

def is_youtube(url):
    return bool(re.search(r"youtube\.com|youtu\.be", url))

def extract_video_id(url):
    patterns = [
        r"youtube\.com/watch\?v=([a-zA-Z0-9_-]{11})",
        r"youtu\.be/([a-zA-Z0-9_-]{11})",
        r"youtube\.com/shorts/([a-zA-Z0-9_-]{11})",
        r"youtube\.com/embed/([a-zA-Z0-9_-]{11})",
    ]
    for p in patterns:
        m = re.search(p, url)
        if m:
            return m.group(1)
    return None

def get_invidious_result(video_id, quality="max"):
    max_height = QUALITY_MAP.get(quality, 9999)
    audio_only = (quality == "audio")

    for instance in INVIDIOUS_INSTANCES:
        try:
            api_url = f"{instance}/api/v1/videos/{video_id}?fields=title,author,lengthSeconds,videoThumbnails,adaptiveFormats,formatStreams"
            req = urllib.request.Request(
                api_url,
                headers={"User-Agent": "Mozilla/5.0"},
            )
            with urllib.request.urlopen(req, timeout=7) as resp:
                data = json.loads(resp.read())

            title = data.get("title", "video")
            author = data.get("author", "")
            duration = data.get("lengthSeconds")
            thumbnails = data.get("videoThumbnails", [])
            thumbnail = next((t["url"] for t in thumbnails if t.get("quality") == "high"), None)
            if thumbnail and thumbnail.startswith("/"):
                thumbnail = instance + thumbnail

            if audio_only:
                # Pick best audio format
                audio_formats = [
                    f for f in data.get("adaptiveFormats", [])
                    if f.get("type", "").startswith("audio")
                ]
                if audio_formats:
                    best = max(audio_formats, key=lambda f: f.get("bitrate", 0))
                    dl_url = best.get("url")
                    if dl_url:
                        return {
                            "downloadUrl": dl_url,
                            "title": title,
                            "thumbnail": thumbnail,
                            "duration": duration,
                            "uploader": author,
                            "source": f"invidious ({instance})",
                        }
            else:
                # Try combined formatStreams first (video+audio in one)
                combined = [
                    f for f in data.get("formatStreams", [])
                    if f.get("url") and int(f.get("resolution", "0p").replace("p","") or 0) <= max_height
                ]
                if combined:
                    best = max(combined, key=lambda f: int(f.get("resolution", "0p").replace("p","") or 0))
                    return {
                        "downloadUrl": best["url"],
                        "title": title,
                        "thumbnail": thumbnail,
                        "duration": duration,
                        "uploader": author,
                        "source": f"invidious ({instance})",
                    }

                # Fall back to adaptive video formats
                video_formats = [
                    f for f in data.get("adaptiveFormats", [])
                    if f.get("type", "").startswith("video/mp4")
                    and f.get("url")
                    and int(f.get("resolution", "0p").replace("p","") or 0) <= max_height
                ]
                if video_formats:
                    best = max(video_formats, key=lambda f: int(f.get("resolution", "0p").replace("p","") or 0))
                    return {
                        "downloadUrl": best["url"],
                        "title": title,
                        "thumbnail": thumbnail,
                        "duration": duration,
                        "uploader": author,
                        "source": f"invidious ({instance})",
                    }

        except Exception:
            continue

    raise Exception("All Invidious instances failed. Try again in a moment.")

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
                video_id = extract_video_id(url)
                if not video_id:
                    raise Exception("Could not extract YouTube video ID from URL")
                result = get_invidious_result(video_id, quality)
                self._respond(200, {"success": True, **result})
            else:
                result = get_cobalt_url(url)
                self._respond(200, {
                    "success": True,
                    "downloadUrl": result["downloadUrl"],
                    "title": "video",
                    "source": f"cobalt ({result['instance']})",
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
        pass
