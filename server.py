import os
import sys

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

import json
import time
import base64
import hmac
import hashlib
import threading
import secrets
import datetime
import urllib.request
import urllib.parse
from http.server import SimpleHTTPRequestHandler, HTTPServer
from socketserver import ThreadingMixIn
from concurrent.futures import ThreadPoolExecutor

PORT = int(os.environ.get("PORT", 3000))
SECRET_KEY = base64.b64decode("NzZpUmwwN3MweFNOOWpxbUVXQXQ3OUVCSlp1bElRSXNWNjRGWnIyTw==").decode("utf-8")
BASE_URL = "https://api3.aoneroom.com"
ADMIN_EMAIL = "canwingamers@gmail.com"
API_KEYS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "api_keys.json")

ADULT_REGEX = r"(?i)\b(porn|porno|xxx|erotic|erotica|hentai|nsfw|nudity|onlyfans|softcore|hardcore|fetish|ullu|kooku|primeplay|hotshots|besharams|voovi|moodx|jav|playboy|lust\s*stories|rabbit\s*movies|hunters\s*app|chikooflix|redprime|sexy\s*scenes)\b"

# Rate limiting
rate_limit_store = {}  # {ip: {"count": N, "window_start": timestamp}}
rate_limit_lock = threading.Lock()

def check_rate_limit(ip, max_requests=120, window_seconds=60):
    """Returns True if request is allowed, False if rate-limited."""
    now = time.time()
    with rate_limit_lock:
        if ip not in rate_limit_store:
            rate_limit_store[ip] = {"count": 1, "window_start": now}
            return True
        entry = rate_limit_store[ip]
        if now - entry["window_start"] > window_seconds:
            entry["count"] = 1
            entry["window_start"] = now
            return True
        entry["count"] += 1
        if entry["count"] > max_requests:
            return False
        return True

def is_adult(title, genre=None, desc=None):
    import re
    if title and re.search(ADULT_REGEX, str(title)):
        return True
    if genre and re.search(ADULT_REGEX, str(genre)):
        return True
    if desc and re.search(ADULT_REGEX, str(desc)):
        return True
    return False

def md5(data):
    return hashlib.md5(data).hexdigest()

def get_x_client_token(ts):
    return f"{ts},{md5(str(ts)[::-1].encode())}"

def generate_signature(method, accept, content_type, url, body="", timestamp=None):
    if timestamp is None:
        timestamp = int(time.time() * 1000)
    parts = url.split("://", 1)[1].split("/", 1)
    full_path = "/" + parts[1] if len(parts) > 1 else "/"
    path = full_path.split("?")[0]
    query = ""
    if "?" in full_path:
        params = [p.split("=", 1) for p in full_path.split("?")[1].split("&") if p]
        params.sort(key=lambda x: x[0])
        query = "&".join(f"{p[0]}={p[1]}" for p in params)
    canonical_url = f"{path}?{query}" if query else path
    body_bytes = body.encode("utf-8") if body else b""
    body_hash = md5(body_bytes[:102400]) if body_bytes else ""
    canonical = f"{method.upper()}\n{accept or ''}\n{content_type or ''}\n{len(body_bytes) if body_bytes else ''}\n{timestamp}\n{body_hash}\n{canonical_url}"
    mac = hmac.new(base64.b64decode(SECRET_KEY), canonical.encode("utf-8"), hashlib.md5)
    return f"{timestamp}|2|{base64.b64encode(mac.digest()).decode()}"

def extract_policy_resource(cookie):
    import re
    if not cookie:
        return None
    m = re.search(r"CloudFront-Policy=([^;]+)", cookie)
    if not m:
        return None
    try:
        raw = m.group(1).translate(str.maketrans("-_~", "+=/"))
        raw += "=" * ((4 - len(raw) % 4) % 4)
        data = json.loads(base64.b64decode(raw).decode('utf-8', errors='ignore'))
        return data.get("Statement", [{}])[0].get("Resource")
    except Exception:
        return None

def is_update_stream(url):
    u = (url or "").lower()
    return "b164fbfb4347792950bdfbfb563d39d9" in u or "/other/2026/09/04/" in u or "app_update" in u

# Token management
token_cache = {"token": None, "ts": 0}
token_lock = threading.Lock()

def get_token(force=False):
    with token_lock:
        now = time.time()
        if not force and token_cache["token"] and (now - token_cache["ts"]) < 3600:
            return token_cache["token"]
        u = f"{BASE_URL}/wefeed-mobile-bff/tab/ranking-list?tabId=0&categoryType=4516404531735022304&page=1&perPage=1"
        req = urllib.request.Request(u, headers=get_api_headers(u))
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                t = json.loads(resp.headers.get("x-user", "{}")).get("token")
                if t:
                    token_cache["token"] = t
                    token_cache["ts"] = now
                    return t
        except Exception as e:
            print(f"[WARN] Token refresh failed: {e}", flush=True)
        return token_cache.get("token") or ""

def get_api_headers(url, method="GET", body="", token=None):
    now = int(time.time() * 1000)
    ct = "application/json"
    h = {
        "user-agent": "com.community.mbox.in/50020126 (Linux; U; Android 14; en_US; Pixel 8; Build/UD1A.230803.041; Cronet/145.0.7582.0)",
        "accept": "application/json",
        "content-type": ct,
        "x-client-token": get_x_client_token(now),
        "x-tr-signature": generate_signature(method, "application/json", ct, url, body, now),
        "x-client-info": '{"package_name":"com.community.mbox.in","version_name":"4.0.02.0831.03","version_code":50020126,"os":"android","os_version":"14","install_ch":"official","device_id":"1234567890abcdef1234567890abcdef","install_store":"official","gaid":"1b2212c1-dadf-43c3-a0c8-bd6ce48ae22d","brand":"Google","model":"Pixel 8","system_language":"en","net":"NETWORK_WIFI","region":"US","timezone":"America/New_York","sp_code":"","X-Play-Mode":"1","X-Idle-Data":"1","X-Family-Mode":"0","X-Content-Mode":"0"}',
        "x-client-status": "0"
    }
    t = token if token is not None else token_cache.get("token")
    if t:
        h["Authorization"] = f"Bearer {t}"
    return h

def api_request(url, method="GET", body="", timeout=15):
    token = get_token()
    headers = get_api_headers(url, method=method, body=body, token=token)
    data = body.encode("utf-8") if body else None
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        if e.code in (401, 441):
            token = get_token(force=True)
            headers = get_api_headers(url, method=method, body=body, token=token)
            req = urllib.request.Request(url, data=data, headers=headers, method=method)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        raise

# API Key Management
api_keys_lock = threading.Lock()

def load_api_keys():
    with api_keys_lock:
        if not os.path.exists(API_KEYS_FILE):
            default_data = {
                "keys": [{
                    "id": "key_dev_master_01",
                    "key": "ayush_live_dev_7f8a9b1c2d3e4f506172",
                    "name": "Master Developer Key",
                    "created_at": datetime.datetime.utcnow().isoformat() + "Z",
                    "status": "active",
                    "requests_count": 0,
                    "last_used_at": None
                }]
            }
            with open(API_KEYS_FILE, "w", encoding="utf-8") as f:
                json.dump(default_data, f, indent=2)
            return default_data
        try:
            with open(API_KEYS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {"keys": []}

def save_api_keys(data):
    with api_keys_lock:
        with open(API_KEYS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

def track_api_key_usage(key_str):
    data = load_api_keys()
    for k in data.get("keys", []):
        if k.get("key") == key_str:
            if k.get("status") != "active":
                return False, "revoked"
            k["requests_count"] = k.get("requests_count", 0) + 1
            k["last_used_at"] = datetime.datetime.utcnow().isoformat() + "Z"
            save_api_keys(data)
            return True, k
    return False, "not_found"

# Media & DASH Proxies
dash_sessions = {}
streams_cache = {}
home_cache = {}

def register_dash_session(resolved_url, cookie):
    base_dash_url = resolved_url.rsplit('/', 1)[0]
    sess_id = hashlib.md5(f"{resolved_url}:{cookie[:20]}".encode()).hexdigest()[:16]
    dash_sessions[sess_id] = {
        "base_url": base_dash_url,
        "manifest_url": resolved_url,
        "cookie": cookie,
        "ts": time.time()
    }
    return sess_id

def rewrite_manifest_codecs(manifest_text):
    import re

    def fix_tag(match):
        tag = match.group(0)
        codec_m = re.search(r'codecs="([^"]+)"', tag)
        if codec_m:
            c = codec_m.group(1)
            # HEVC codecs: hev1 or hvc1
            if c == "hev1" or c == "hvc1" or (c.startswith("hev1") and len(c.split('.')) < 4) or (c.startswith("hvc1") and len(c.split('.')) < 4):
                h_m = re.search(r'height="(\d+)"', tag) or re.search(r'maxHeight="(\d+)"', manifest_text)
                h = int(h_m.group(1)) if h_m else 480
                lvl = "L120" if h >= 1080 else ("L93" if h >= 720 else "L90")
                tag = tag.replace(f'codecs="{c}"', f'codecs="hev1.1.6.{lvl}.B0"')
            elif c == "avc1" or (c.startswith("avc1") and len(c.split('.')) < 3):
                tag = tag.replace(f'codecs="{c}"', 'codecs="avc1.4d401f"')
        return tag

    manifest_text = re.sub(r'<Representation\b[^>]+>', fix_tag, manifest_text)
    manifest_text = re.sub(r'<AdaptationSet\b[^>]+>', fix_tag, manifest_text)

    # Provide dual representation: both hev1 (Chromium/Android) and hvc1 (Apple Safari/Edge)
    def duplicate_for_hvc1(match):
        rep_block = match.group(0)
        if 'codecs="hev1.' in rep_block and 'hvc1.' not in rep_block:
            hvc_rep = rep_block
            orig_id_m = re.search(r'id="([^"]+)"', rep_block)
            orig_id = orig_id_m.group(1) if orig_id_m else "0"
            hvc_rep = re.sub(r'id="([^"]+)"', r'id="\1_hvc"', hvc_rep, count=1)
            hvc_rep = hvc_rep.replace('codecs="hev1.', 'codecs="hvc1.')
            hvc_rep = hvc_rep.replace('$RepresentationID$', orig_id)
            return rep_block + "\n\t\t" + hvc_rep
        return rep_block

    manifest_text = re.sub(r'<Representation\b[^>]*>.*?</Representation>', duplicate_for_hvc1, manifest_text, flags=re.DOTALL)
    return manifest_text

def fetch_category_items(cat_spec, cat_title):
    try:
        if isinstance(cat_spec, dict):
            u = f"{BASE_URL}/wefeed-mobile-bff/subject-api/list"
            body_dict = {"page": 1, "perPage": 16, "sort": "ForYou"}
            body_dict.update(cat_spec)
            resp = api_request(u, method="POST", body=json.dumps(body_dict), timeout=10)
        else:
            u = f"{BASE_URL}/wefeed-mobile-bff/tab/ranking-list?tabId=0&categoryType={cat_spec}&page=1&perPage=16"
            resp = api_request(u, timeout=10)

        raw_items = resp.get("data", {}).get("items", []) or resp.get("data", {}).get("subjects", [])
        clean_items = []
        for it in raw_items:
            title = it.get("title", "")
            genre = str(it.get("genre", ""))
            desc = str(it.get("description", ""))
            stype = it.get("subjectType", 1)
            display_title = title.split("[")[0].strip()
            if not display_title or stype not in (1, 2, 7) or is_adult(title, genre, desc):
                continue
            cover_obj = it.get("cover") or {}
            poster = cover_obj.get("url")
            if not poster:
                continue
            clean_items.append({
                "id": str(it.get("subjectId")),
                "title": display_title,
                "rawTitle": title,
                "poster": poster,
                "rating": str(it.get("imdbRatingValue") or "7.5"),
                "type": "series" if stype in (2, 7) else "movie",
                "genre": genre,
                "desc": desc,
                "year": (str(it.get("releaseDate") or "2026"))[:4]
            })
        if clean_items:
            return (cat_title, clean_items)
    except Exception as e:
        print(f"[WARN] Category {cat_title} error: {e}", flush=True)
    return (cat_title, [])

def build_home_feed(tab="all"):
    get_token()
    if tab == "movies":
        CATEGORIES = [
            ("4516404531735022304", "🔥 Trending Movies"),
            ("414907768299210008", "🌟 Bollywood Blockbusters"),
            ("3859721901924910512", "💥 South Indian (Hindi Dub)"),
            ({"channelId": "1", "classify": "Hindi dub", "country": "United States"}, "🎬 Hollywood in Hindi"),
            ("8019599703232971616", "🌍 Hollywood Hits"),
            ({"channelId": "1", "genre": "Action"}, "⚡ Action Hits"),
            ({"channelId": "1", "genre": "Comedy"}, "😂 Comedy Hits"),
        ]
    elif tab == "series":
        CATEGORIES = [
            ({"channelId": "2", "country": "India"}, "📺 Top Indian Web Series"),
            ("4741626294545400336", "🔥 Global Trending Series"),
            ({"channelId": "2", "classify": "Hindi dub", "country": "United States"}, "🎬 Hollywood Series in Hindi"),
            ("7878715743607948784", "🇰🇷 Korean Drama"),
            ("8788126208987989488", "🇨🇳 Chinese Drama"),
        ]
    elif tab == "anime":
        CATEGORIES = [
            ("8434602210994128512", "🎌 Anime Universe"),
        ]
    else:
        CATEGORIES = [
            ("4516404531735022304", "🔥 Trending in India"),
            ("414907768299210008", "🌟 Bollywood Blockbusters"),
            ("3859721901924910512", "💥 South Indian (Hindi Dub)"),
            ({"channelId": "2", "country": "India"}, "📺 Top Indian Web Series"),
            ({"channelId": "1", "classify": "Hindi dub", "country": "United States"}, "🎬 Hollywood in Hindi"),
            ("8019599703232971616", "🌍 Hollywood Blockbusters"),
            ("4741626294545400336", "📺 Top Series This Week"),
            ({"channelId": "1", "genre": "Action"}, "⚡ Action Movies"),
            ("8434602210994128512", "🎌 Anime Universe"),
            ("7878715743607948784", "🇰🇷 Korean Drama"),
        ]

    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = [executor.submit(fetch_category_items, cid, ctitle) for cid, ctitle in CATEGORIES]
        results = [f.result() for f in futures]

    result_rows = []
    hero_item = None
    results_dict = dict(results)
    for cid, ctitle in CATEGORIES:
        items = results_dict.get(ctitle, [])
        if items:
            result_rows.append({"title": ctitle, "items": items})
            if not hero_item:
                for it in items:
                    if len(it.get("desc", "")) > 25:
                        hero_item = it
                        break

    if not hero_item and result_rows and result_rows[0]["items"]:
        hero_item = result_rows[0]["items"][0]

    feed_data = {
        "status": "success",
        "tab": tab,
        "hero": hero_item,
        "rows": result_rows
    }
    home_cache[tab] = {"data": feed_data, "ts": time.time()}
    return feed_data


class MultiCyberServer(SimpleHTTPRequestHandler):

    def end_headers(self):
        # CORS: Only allow specific origins instead of wildcard
        origin = self.headers.get("Origin", "")
        allowed_origins = [
            "https://ayush.ai.studio", "https://flix.ayush.ai.studio",
            "https://music.ayush.ai.studio", "https://api.ayush.ai.studio",
            "http://localhost:3000", "http://127.0.0.1:3000"
        ]
        if origin in allowed_origins:
            self.send_header("Access-Control-Allow-Origin", origin)
        elif not origin or "localhost" in origin or "127.0.0.1" in origin:
            self.send_header("Access-Control-Allow-Origin", origin or "*")
        else:
            self.send_header("Access-Control-Allow-Origin", "https://ayush.ai.studio")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization, X-API-Key, X-Admin-Email, Range, X-Ayush-Internal")
        self.send_header("Access-Control-Max-Age", "86400")
        # Security headers
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "SAMEORIGIN")
        self.send_header("X-XSS-Protection", "1; mode=block")
        self.send_header("Referrer-Policy", "strict-origin-when-cross-origin")
        self.send_header("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        self.send_header("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
        super().end_headers()

    def do_OPTIONS(self):
        self.send_response(204)
        self.end_headers()

    def send_json(self, data, status=200):
        body = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def serve_static_file(self, filepath, content_type="text/html; charset=utf-8"):
        # Path traversal protection
        base_dir = os.path.dirname(os.path.abspath(__file__))
        abs_path = os.path.normpath(os.path.join(base_dir, filepath))
        if not abs_path.startswith(base_dir):
            self.send_response(403)
            self.end_headers()
            self.wfile.write(b"403 Forbidden")
            return
        if not os.path.isfile(abs_path):
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b"404 Not Found")
            return
        with open(abs_path, "rb") as f:
            data = f.read()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def check_api_key_auth(self, qs):
        host = self.headers.get("Host", "").lower().split(":")[0]

        # 1. If accessing via the public API domain (api.ayush.ai.studio), an API key is STRICTLY required!
        if host.startswith("api."):
            api_key = self.headers.get("X-API-Key") or qs.get("api_key", [""])[0] or qs.get("key", [""])[0]
            if not api_key:
                return False, "missing"
            ok, result = track_api_key_usage(api_key.strip())
            if ok:
                return True, result
            return False, result

        # 2. For the website frontends (flix.ayush.ai.studio, music.ayush.ai.studio, localhost):
        ref = self.headers.get("Referer", "").lower()
        origin = self.headers.get("Origin", "").lower()
        sec_fetch = self.headers.get("Sec-Fetch-Site", "").lower()
        internal_hdr = self.headers.get("X-Ayush-Internal", "")

        if internal_hdr == "1" or sec_fetch in ("same-origin", "same-site"):
            return True, {"name": "Internal Client", "status": "active"}

        if any(d in host for d in ["localhost", "127.0.0.1", "flix.", "music."]) or (host.endswith("ayush.ai.studio") and not host.startswith("api.")):
            return True, {"name": "Web UI Client", "status": "active"}

        if any(d in ref for d in ["localhost", "127.0.0.1", "ayush.ai.studio"]) or any(d in origin for d in ["localhost", "127.0.0.1", "ayush.ai.studio"]):
            return True, {"name": "Internal Client", "status": "active"}

        # 3. Any other direct external caller requires a valid API key
        api_key = self.headers.get("X-API-Key") or qs.get("api_key", [""])[0] or qs.get("key", [""])[0]
        if not api_key:
            return False, "missing"

        ok, result = track_api_key_usage(api_key.strip())
        if ok:
            return True, result
        return False, result

    def check_admin_auth(self, body_json=None):
        auth_hdr = self.headers.get("Authorization", "")

        # Only accept Firebase JWT Bearer token with verified admin email
        if auth_hdr.startswith("Bearer "):
            token = auth_hdr.split(" ", 1)[1]
            try:
                parts = token.split(".")
                if len(parts) >= 2:
                    pad = len(parts[1]) % 4
                    p_b64 = parts[1] + ("=" * (4 - pad) if pad else "")
                    payload = json.loads(base64.urlsafe_b64decode(p_b64).decode("utf-8", errors="replace"))
                    email = (payload.get("email") or "").lower()
                    # Verify token is not expired
                    exp = payload.get("exp", 0)
                    if exp and exp < time.time():
                        return False
                    if email == ADMIN_EMAIL.lower():
                        return True
            except Exception:
                pass

        return False

    def do_GET(self):
        host = self.headers.get("Host", "").lower().split(":")[0]
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        qs = urllib.parse.parse_qs(parsed.query)
        client_ip = self.client_address[0] if self.client_address else "unknown"

        # Rate limiting for API endpoints
        if path.startswith("/api/"):
            limit = 15 if path.startswith("/api/admin/") else 120
            if not check_rate_limit(client_ip, max_requests=limit, window_seconds=60):
                self.send_json({"status": "error", "code": 429, "message": "Too many requests. Please slow down."}, status=429)
                return

        # ----------------------------------------------------------------------
        # 1. Host-Based Subdomain Routing
        # ----------------------------------------------------------------------
        if host.startswith("flix."):
            if path in ["", "/", "/watch", "/play"] or path.startswith("/watch/"):
                return self.serve_static_file("static/watch.html")
            if path in ["/info", "/info/"]:
                return self.serve_static_file("static/flix.html")

        if host.startswith("music.") and path in ["", "/"]:
            return self.serve_static_file("static/music.html")

        if host.startswith("api.") and path in ["", "/"]:
            return self.serve_static_file("static/api.html")

        # ----------------------------------------------------------------------
        # 2. Path-Based Navigation
        # ----------------------------------------------------------------------
        if path in ["", "/"]:
            return self.serve_static_file("static/portfolio.html")

        if path in ["/admin", "/admin/"]:
            return self.serve_static_file("static/admin.html")

        if path in ["/flix", "/flix/", "/watch", "/watch/"]:
            return self.serve_static_file("static/watch.html")

        if path in ["/info", "/info/"]:
            return self.serve_static_file("static/flix.html")

        if path in ["/music", "/music/"]:
            return self.serve_static_file("static/music.html")

        if path in ["/api", "/api/"]:
            return self.serve_static_file("static/api.html")

        # ----------------------------------------------------------------------
        # 3. Static Files
        # ----------------------------------------------------------------------
        if path.startswith("/static/"):
            rel = path.lstrip("/")
            ct = "text/plain"
            if rel.endswith(".css"): ct = "text/css"
            elif rel.endswith(".js"): ct = "application/javascript"
            elif rel.endswith(".html"): ct = "text/html; charset=utf-8"
            elif rel.endswith(".wgt") or rel.endswith(".apk") or rel.endswith(".zip"): ct = "application/octet-stream"
            elif rel.endswith(".svg"): ct = "image/svg+xml"
            elif rel.endswith(".png"): ct = "image/png"
            elif rel.endswith(".jpg") or rel.endswith(".jpeg"): ct = "image/jpeg"
            return self.serve_static_file(rel, ct)

        if path.startswith("/lib/"):
            rel = path.lstrip("/")
            ct = "application/javascript"
            return self.serve_static_file(rel, ct)

        # ----------------------------------------------------------------------
        # 4. Admin API Endpoints
        # ----------------------------------------------------------------------
        if path == "/api/admin/keys":
            if not self.check_admin_auth():
                self.send_json({"status": "error", "message": "Admin authorization required (canwingamers@gmail.com)"}, status=403)
                return
            keys_data = load_api_keys()
            total_reqs = sum(k.get("requests_count", 0) for k in keys_data.get("keys", []))
            active_cnt = sum(1 for k in keys_data.get("keys", []) if k.get("status") == "active")
            return self.send_json({
                "status": "success",
                "keys": keys_data.get("keys", []),
                "stats": {
                    "total_keys": len(keys_data.get("keys", [])),
                    "active_keys": active_cnt,
                    "total_requests": total_reqs
                }
            })

        # ----------------------------------------------------------------------
        # 5. Media Proxies (DASH & Chunks)
        # ----------------------------------------------------------------------
        if path.startswith("/stream/dash/"):
            return self.handle_dash_proxy(path)

        if path.startswith("/stream/proxy/") or path == "/stream":
            video_url = qs.get("url", [""])[0]
            cookie = qs.get("cookie", [""])[0]
            return self.handle_stream_proxy(video_url, cookie)

        # ----------------------------------------------------------------------
        # 6. JSON REST API Endpoints (Protected by API Key for external calls)
        # ----------------------------------------------------------------------
        if path.startswith("/api/"):
            if not path.startswith("/api/admin/") and path != "/api/tmdb/image":
                is_auth, key_info = self.check_api_key_auth(qs)
                if not is_auth:
                    self.send_json({
                        "status": "error",
                        "code": 401,
                        "error": "Unauthorized",
                        "message": "Unauthorized: A valid API key is required. Contact the admin on Reddit for a free API key: https://www.reddit.com/user/Used-Show-2246/"
                    }, status=401)
                    return

            if path == "/api/tmdb/image":
                t_path = qs.get("path", [""])[0]
                t_size = qs.get("size", ["w500"])[0]
                return self.handle_api_tmdb_image(t_path, t_size)

            if path == "/api/home":
                tab = qs.get("tab", ["all"])[0]
                return self.handle_api_home(tab)

            if path == "/api/search":
                q = qs.get("q", [""])[0]
                return self.handle_api_search(q)

            if path == "/api/resolve":
                slug = qs.get("slug", [""])[0] or qs.get("q", [""])[0]
                return self.handle_api_resolve(slug)

            if path == "/api/details":
                sid = qs.get("id", [""])[0]
                return self.handle_api_details(sid)

            if path == "/api/tmdb":
                t_path = qs.get("path", [""])[0]
                return self.handle_api_tmdb(t_path)

            if path == "/api/streams":
                sid = qs.get("id", [""])[0]
                se = int(qs.get("se", [0])[0])
                ep = int(qs.get("ep", [0])[0])
                return self.handle_api_streams(sid, se, ep)

        # SPA Fallback for /watch/* deep links
        if path.startswith("/watch/"):
            return self.serve_static_file("static/watch.html")

        return super().do_GET()

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        client_ip = self.client_address[0] if self.client_address else "unknown"
        # Rate limit admin POST endpoints (15 req/min)
        if path.startswith("/api/admin/"):
            if not check_rate_limit(client_ip, max_requests=15, window_seconds=60):
                self.send_json({"status": "error", "code": 429, "message": "Too many requests."}, status=429)
                return
        length = int(self.headers.get("Content-Length", 0))
        body_bytes = self.rfile.read(length) if length > 0 else b""
        body_json = {}
        try:
            if body_bytes:
                body_json = json.loads(body_bytes.decode("utf-8"))
        except Exception:
            pass

        # Admin Actions
        if path.startswith("/api/admin/"):
            if not self.check_admin_auth(body_json):
                self.send_json({"status": "error", "message": "Admin authorization required (canwingamers@gmail.com)"}, status=403)
                return

            if path == "/api/admin/keys/create":
                name = body_json.get("name", "New API Key").strip() or "Unnamed Key"
                data = load_api_keys()
                new_key = {
                    "id": f"key_{secrets.token_hex(6)}",
                    "key": f"ayush_live_{secrets.token_hex(16)}",
                    "name": name,
                    "created_at": datetime.datetime.utcnow().isoformat() + "Z",
                    "status": "active",
                    "requests_count": 0,
                    "last_used_at": None
                }
                data.setdefault("keys", []).append(new_key)
                save_api_keys(data)
                self.send_json({"status": "success", "key": new_key})
                return

            if path == "/api/admin/keys/toggle":
                key_id = body_json.get("id")
                new_status = body_json.get("status", "revoked")
                data = load_api_keys()
                updated = False
                for k in data.get("keys", []):
                    if k.get("id") == key_id:
                        k["status"] = new_status
                        updated = True
                        break
                if updated:
                    save_api_keys(data)
                    self.send_json({"status": "success", "message": f"Key status changed to {new_status}"})
                else:
                    self.send_json({"status": "error", "message": "Key not found"}, status=404)
                return

            if path == "/api/admin/keys/delete":
                key_id = body_json.get("id")
                data = load_api_keys()
                before_len = len(data.get("keys", []))
                data["keys"] = [k for k in data.get("keys", []) if k.get("id") != key_id]
                if len(data["keys"]) < before_len:
                    save_api_keys(data)
                    self.send_json({"status": "success", "message": "Key deleted successfully"})
                else:
                    self.send_json({"status": "error", "message": "Key not found"}, status=404)
                return

        self.send_json({"status": "error", "message": "Endpoint not found"}, status=404)

    # --- API HANDLERS ---
    def handle_api_home(self, tab="all"):
        now = time.time()
        cached = home_cache.get(tab)
        if cached and (now - cached["ts"]) < 1800:
            self.send_json(cached["data"])
            return
        feed = build_home_feed(tab)
        self.send_json(feed)

    def handle_api_search(self, query):
        if not query:
            self.send_json({"status": "success", "results": []})
            return
        try:
            u = f"{BASE_URL}/wefeed-mobile-bff/subject-api/search/v2"
            body = json.dumps({"page": 1, "perPage": 20, "keyword": query})
            resp = api_request(u, method="POST", body=body)
            clean_results = []
            results_groups = resp.get("data", {}).get("results", [])
            for grp in results_groups:
                for sub in grp.get("subjects", []):
                    title = sub.get("title", "")
                    genre = str(sub.get("genre", ""))
                    desc = str(sub.get("description", ""))
                    stype = sub.get("subjectType", 1)
                    display_title = title.split("[")[0].strip()
                    if not display_title or stype not in (1, 2, 7) or is_adult(title, genre, desc):
                        continue
                    cover_obj = sub.get("cover") or {}
                    poster = cover_obj.get("url")
                    if not poster:
                        continue
                    clean_results.append({
                        "id": str(sub.get("subjectId")),
                        "title": display_title,
                        "rawTitle": title,
                        "poster": poster,
                        "rating": str(sub.get("imdbRatingValue") or "7.5"),
                        "type": "series" if stype in (2, 7) else "movie",
                        "genre": genre,
                        "desc": desc,
                        "year": (str(sub.get("releaseDate") or "2026"))[:4]
                    })
            self.send_json({"status": "success", "results": clean_results})
        except Exception as e:
            print(f"[ERROR] Search failed for '{query}': {e}", flush=True)
            self.send_json({"status": "error", "message": str(e)}, status=500)

    def handle_api_resolve(self, slug):
        if not slug:
            self.send_json({"status": "error", "message": "Missing slug"}, status=400)
            return
        keyword = slug.replace("-", " ").replace("_", " ").strip()
        try:
            u = f"{BASE_URL}/wefeed-mobile-bff/subject-api/search/v2"
            body = json.dumps({"page": 1, "perPage": 5, "keyword": keyword})
            resp = api_request(u, method="POST", body=body)
            results = resp.get("data", {}).get("results", [])
            match_sub = None
            for grp in results:
                for sub in grp.get("subjects", []):
                    title = sub.get("title", "")
                    genre = str(sub.get("genre", ""))
                    desc = str(sub.get("description", ""))
                    stype = sub.get("subjectType", 1)
                    display_title = title.split("[")[0].strip()
                    if not display_title or stype not in (1, 2, 7) or is_adult(title, genre, desc):
                        continue
                    match_sub = sub
                    break
                if match_sub:
                    break

            if not match_sub:
                self.send_json({"status": "error", "message": "Content not found"}, status=404)
                return

            sid = str(match_sub.get("subjectId"))
            self.handle_api_details(sid)
        except Exception as e:
            self.send_json({"status": "error", "message": str(e)}, status=500)

    def handle_api_details(self, sid):
        if not sid:
            self.send_json({"status": "error", "message": "Missing ID"}, status=400)
            return
        try:
            u = f"{BASE_URL}/wefeed-mobile-bff/subject-api/get?subjectId={sid}"
            resp = api_request(u)
            data = resp.get("data", {})
            title = data.get("title", "")
            display_title = title.split("[")[0].strip()
            genre = str(data.get("genre", ""))
            desc = str(data.get("description", ""))
            stype = data.get("subjectType", 1)
            is_series = stype in (2, 7)
            cover_obj = data.get("cover") or {}
            poster = cover_obj.get("url")

            actors = []
            for staff in data.get("staffList", []):
                if staff.get("staffType") == 1:
                    actors.append({
                        "name": staff.get("name"),
                        "character": staff.get("character")
                    })

            dubs = []
            for d in data.get("dubs", []):
                dubs.append({
                    "id": str(d.get("subjectId")),
                    "name": d.get("lanName") or "Alternative"
                })

            seasons_info = []
            if is_series:
                try:
                    se_url = f"{BASE_URL}/wefeed-mobile-bff/subject-api/season-info?subjectId={sid}"
                    se_resp = api_request(se_url)
                    raw_seasons = se_resp.get("data", {}).get("seasons", [])
                    for sn in raw_seasons:
                        s_num = sn.get("se", 1)
                        max_ep = sn.get("maxEp", 1)
                        seasons_info.append({
                            "season": s_num,
                            "maxEp": max_ep,
                            "episodes": list(range(1, max_ep + 1))
                        })
                except Exception as ex:
                    print(f"[WARN] Season-info failed for {sid}: {ex}", flush=True)

            details = {
                "id": str(sid),
                "title": display_title,
                "rawTitle": title,
                "poster": poster,
                "backdrop": poster,
                "rating": str(data.get("imdbRatingValue") or "7.8"),
                "year": (str(data.get("releaseDate") or "2026"))[:4],
                "duration": data.get("duration") or ("Series" if is_series else "2h"),
                "genre": genre,
                "desc": desc,
                "actors": actors[:6],
                "dubs": dubs,
                "isSeries": is_series,
                "seasons": seasons_info
            }
            self.send_json({"status": "success", "details": details})
        except Exception as e:
            print(f"[ERROR] Details failed for {sid}: {e}", flush=True)
            self.send_json({"status": "error", "message": str(e)}, status=500)

    def handle_api_tmdb(self, tmdb_path):
        if not tmdb_path:
            self.send_json({"error": "Missing path parameter"}, status=400)
            return
        api_keys = [
            "6cffbd2afef40abe5ce96016e1c81548",
            "c23e85e267104b90be8bf97775586616",
            "3da1f6e39ec2f73d6103a8312d37d145",
            "b3bc22ae6b28399e5df80f33b1e3557e"
        ]
        for key in api_keys:
            sep = "&" if "?" in tmdb_path else "?"
            url = f"https://api.themoviedb.org/3/{tmdb_path}{sep}api_key={key}"
            try:
                req = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": "Ayushflix/1.0"})
                with urllib.request.urlopen(req, timeout=10) as resp:
                    if resp.status == 200:
                        data = json.loads(resp.read().decode("utf-8"))
                        self.send_json(data)
                        return
            except Exception:
                continue
        self.send_json({"error": "TMDB proxy request failed"}, status=502)

    def handle_api_tmdb_image(self, img_path, size="w500"):
        if not img_path or img_path.strip() in ("", "/", "null", "undefined", "None"):
            self.send_response(400); self.end_headers(); return
        clean_path = img_path.strip()
        if not clean_path.startswith("/"):
            clean_path = f"/{clean_path}"
        # Validate path looks like a TMDB image path
        if not clean_path.endswith((".jpg", ".png", ".svg", ".webp")):
            clean_path += ".jpg"  # TMDB paths always end with extension
        allowed_sizes = {"w45","w92","w154","w185","w300","w342","w500","w780","w1280","h632","original"}
        if size not in allowed_sizes:
            size = "w500"

        target_url = f"https://image.tmdb.org/t/p/{size}{clean_path}"
        fallback_url = f"https://wsrv.nl/?url=https://image.tmdb.org/t/p/{size}{clean_path}"
        fallback_url2 = f"https://wsrv.nl/?url=https://image.tmdb.org/t/p/{size}{clean_path}&output=jpg&q=85"

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8"
        }

        for u in [target_url, fallback_url, fallback_url2]:
            try:
                req = urllib.request.Request(u, headers=headers)
                with urllib.request.urlopen(req, timeout=12) as resp:
                    if resp.status == 200:
                        content_type = resp.headers.get("Content-Type", "image/jpeg")
                        data = resp.read()
                        if len(data) < 100:  # Too small, likely an error page
                            continue
                        self.send_response(200)
                        self.send_header("Content-Type", content_type)
                        self.send_header("Content-Length", str(len(data)))
                        self.send_header("Cache-Control", "public, max-age=604800, immutable")
                        self.end_headers()
                        self.wfile.write(data)
                        return
            except Exception:
                continue

        self.send_response(404)
        self.end_headers()

    def handle_api_streams(self, sid, se=0, ep=0):
        if not sid:
            self.send_json({"status": "error", "message": "Missing ID"}, status=400)
            return

        cache_key = f"{sid}_{se}_{ep}"
        now = time.time()
        if cache_key in streams_cache and (now - streams_cache[cache_key]["ts"]) < 300:
            self.send_json({"status": "success", "streams": streams_cache[cache_key]["streams"]})
            return

        try:
            subject_candidates = [(str(sid), "Original Audio")]
            seen_cand_ids = {str(sid)}
            try:
                det_url = f"{BASE_URL}/wefeed-mobile-bff/subject-api/get?subjectId={sid}"
                det_res = api_request(det_url)
                for d in det_res.get("data", {}).get("dubs", []):
                    did = str(d.get("subjectId"))
                    dname = (d.get("name") or d.get("lanName") or "Dub").strip()
                    if did and did not in seen_cand_ids:
                        seen_cand_ids.add(did)
                        subject_candidates.append((did, dname))
            except Exception as e:
                print(f"[WARN] Dubs fetch failed for {sid}: {e}", flush=True)

            subject_candidates.sort(key=lambda x: (
                0 if ("hindi" in x[1].lower() or "hin" in x[1].lower()) else
                1 if ("original" in x[1].lower() or "english" in x[1].lower()) else
                2
            ))

            def fetch_cand_streams(cand):
                c_id, lan_name = cand
                valid = []
                try:
                    p_url = f"{BASE_URL}/wefeed-mobile-bff/subject-api/play-info?subjectId={c_id}&se={se}&ep={ep}"
                    resp = api_request(p_url)
                    raw_streams = resp.get("data", {}).get("streams", [])
                    for st in raw_streams:
                        cookie = st.get("signCookie", "")
                        raw_url = st.get("url", "")
                        fmt = (st.get("format") or "MP4").upper()
                        res = st.get("resolutions") or "HD"
                        resolved_url = raw_url
                        is_dash = ".mpd" in resolved_url.lower()

                        # Universal fix: If upstream enforces app update by returning a dummy update video,
                        # resolve the real DASH stream URL from the signed CloudFront-Policy
                        if is_update_stream(raw_url) or "/dash/" in cookie:
                            policy_res = extract_policy_resource(cookie)
                            if policy_res:
                                base_res = policy_res.rstrip('*').rstrip('/')
                                if "/dash/" in base_res or "/hls/" in base_res or "sacdn." in base_res:
                                    resolved_url = f"{base_res}/index.mpd"
                                    is_dash = True

                        # If still an update video with no real stream, discard it
                        if is_update_stream(resolved_url):
                            continue

                        if is_dash:
                            sess_id = register_dash_session(resolved_url, cookie)
                            proxy_url = f"/stream/dash/{sess_id}/manifest.mpd"
                            stream_fmt = "DASH"
                        else:
                            proxy_url = f"/stream/proxy/?url={urllib.parse.quote_plus(resolved_url)}&cookie={urllib.parse.quote_plus(cookie)}"
                            stream_fmt = fmt

                        valid.append({
                            "language": lan_name,
                            "format": stream_fmt,
                            "resolution": str(res),
                            "originalUrl": resolved_url,
                            "streamUrl": proxy_url,
                            "cookie": cookie
                        })
                except Exception as ex:
                    print(f"[WARN] Play-info failed for {c_id}: {ex}", flush=True)
                return valid

            with ThreadPoolExecutor(max_workers=8) as executor:
                stream_groups = list(executor.map(fetch_cand_streams, subject_candidates))

            all_streams = [s for grp in stream_groups for s in grp]
            streams_cache[cache_key] = {"ts": now, "streams": all_streams}
            self.send_json({"status": "success", "streams": all_streams})
        except Exception as e:
            print(f"[ERROR] Streams failed for {sid}: {e}", flush=True)
            self.send_json({"status": "error", "message": str(e)}, status=500)

    def handle_dash_proxy(self, path):
        parts = path.strip("/").split("/")
        if len(parts) < 4:
            self.send_response(400); self.end_headers(); return
        sess_id = parts[2]
        filename = "/".join(parts[3:])
        sess = dash_sessions.get(sess_id)
        if not sess:
            self.send_response(404); self.end_headers(); return

        upstream_headers = {
            "User-Agent": "com.community.mbox.in/50020126 (Linux; U; Android 14; en_US; Pixel 8; Build/UD1A.230803.041; Cronet/145.0.7582.0)",
            "Referer": "https://api3.aoneroom.com",
            "Connection": "keep-alive"
        }
        if sess.get("cookie"):
            upstream_headers["Cookie"] = sess["cookie"]

        clean_fn = filename.replace("_hvc", "")
        target_url = sess["manifest_url"] if (filename == "manifest.mpd" or filename.endswith(".mpd")) else f"{sess['base_url']}/{clean_fn}"
        range_hdr = self.headers.get("Range")
        if range_hdr: upstream_headers["Range"] = range_hdr

        try:
            if filename.endswith(".mpd") or filename == "manifest.mpd":
                try:
                    req = urllib.request.Request(target_url, headers=upstream_headers)
                    with urllib.request.urlopen(req, timeout=15) as v_resp:
                        data = rewrite_manifest_codecs(v_resp.read().decode('utf-8', errors='replace')).encode('utf-8')
                        self.send_response(200)
                        self.send_header("Content-Type", "application/dash+xml; charset=utf-8")
                        self.send_header("Content-Length", str(len(data)))
                        self.send_header("Cache-Control", "no-cache")
                        self.end_headers()
                        self.wfile.write(data)
                        return
                except urllib.error.HTTPError as he:
                    alt_url = None
                    if target_url.endswith("/manifest.mpd"):
                        alt_url = target_url[:-13] + "/index.mpd"
                    elif target_url.endswith("/index.mpd"):
                        alt_url = target_url[:-10] + "/manifest.mpd"
                    if alt_url:
                        try:
                            req2 = urllib.request.Request(alt_url, headers=upstream_headers)
                            with urllib.request.urlopen(req2, timeout=15) as v_resp2:
                                data = rewrite_manifest_codecs(v_resp2.read().decode('utf-8', errors='replace')).encode('utf-8')
                                self.send_response(200)
                                self.send_header("Content-Type", "application/dash+xml; charset=utf-8")
                                self.send_header("Content-Length", str(len(data)))
                                self.send_header("Cache-Control", "no-cache")
                                self.end_headers()
                                self.wfile.write(data)
                                return
                        except Exception:
                            pass
                    raise

            req = urllib.request.Request(target_url, headers=upstream_headers)
            with urllib.request.urlopen(req, timeout=20) as v_resp:
                self.send_response(v_resp.status)
                ct = "video/iso.segment" if filename.endswith(".m4s") else v_resp.headers.get("Content-Type", "application/octet-stream")
                self.send_header("Content-Type", ct)
                if filename.endswith(".m4s"):
                    self.send_header("Cache-Control", "public, max-age=86400, immutable")
                else:
                    self.send_header("Cache-Control", "public, max-age=3600")
                if v_resp.headers.get("Content-Length"): self.send_header("Content-Length", v_resp.headers.get("Content-Length"))
                if v_resp.headers.get("Content-Range"): self.send_header("Content-Range", v_resp.headers.get("Content-Range"))
                self.send_header("Accept-Ranges", "bytes")
                self.end_headers()

                while True:
                    chunk = v_resp.read(256 * 1024)
                    if not chunk: break
                    try: self.wfile.write(chunk)
                    except (ConnectionResetError, ConnectionAbortedError, BrokenPipeError): break
        except Exception:
            try: self.send_response(502); self.end_headers()
            except Exception: pass

    def handle_stream_proxy(self, video_url, cookie):
        if not video_url:
            self.send_response(400); self.end_headers(); return
        headers = {
            "User-Agent": "com.community.mbox.in/50020126 (Linux; U; Android 14; en_US; Pixel 8; Build/UD1A.230803.041; Cronet/145.0.7582.0)",
            "Referer": "https://api3.aoneroom.com",
            "Connection": "keep-alive"
        }
        if cookie: headers["Cookie"] = cookie
        range_hdr = self.headers.get("Range")
        if range_hdr: headers["Range"] = range_hdr

        try:
            req = urllib.request.Request(video_url, headers=headers)
            with urllib.request.urlopen(req, timeout=15) as v_resp:
                self.send_response(v_resp.status)
                self.send_header("Content-Type", v_resp.headers.get("Content-Type", "video/mp4"))
                self.send_header("Cache-Control", "public, max-age=3600")
                if v_resp.headers.get("Content-Length"): self.send_header("Content-Length", v_resp.headers.get("Content-Length"))
                if v_resp.headers.get("Content-Range"): self.send_header("Content-Range", v_resp.headers.get("Content-Range"))
                self.send_header("Accept-Ranges", "bytes")
                self.end_headers()
                while True:
                    chunk = v_resp.read(256 * 1024)
                    if not chunk: break
                    try: self.wfile.write(chunk)
                    except (ConnectionResetError, ConnectionAbortedError, BrokenPipeError): break
        except Exception:
            try: self.send_response(502); self.end_headers()
            except Exception: pass

class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True

def run():
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    server_address = ("0.0.0.0", PORT)
    httpd = ThreadedHTTPServer(server_address, MultiCyberServer)
    print(f"===========================================================", flush=True)
    print(f"  AYUSH CYBERNETIC MULTI-SERVICE PLATFORM ONLINE", flush=True)
    print(f"  Port: {PORT}", flush=True)
    print(f"  - Portfolio:  http://localhost:{PORT}/      (ayush.ai.studio)", flush=True)
    print(f"  - Ayushflix:  http://localhost:{PORT}/watch  (flix.ayush.ai.studio)", flush=True)
    print(f"  - AyushMuzic: http://localhost:{PORT}/music  (music.ayush.ai.studio)", flush=True)
    print(f"  - Stream API: http://localhost:{PORT}/api    (api.ayush.ai.studio)", flush=True)
    print(f"===========================================================", flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nServer shutting down.", flush=True)
        httpd.server_close()

if __name__ == "__main__":
    run()
