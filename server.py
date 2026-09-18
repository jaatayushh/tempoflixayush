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
import urllib.request
import urllib.parse
from http.server import SimpleHTTPRequestHandler, HTTPServer
from socketserver import ThreadingMixIn
from concurrent.futures import ThreadPoolExecutor

PORT = int(os.environ.get("PORT", 3000))
SECRET_KEY = base64.b64decode("NzZpUmwwN3MweFNOOWpxbUVXQXQ3OUVCSlp1bElRSXNWNjRGWnIyTw==").decode("utf-8")
BASE_URL = "https://api3.aoneroom.com"

ADULT_REGEX = r"(?i)\b(porn|porno|xxx|erotic|erotica|hentai|nsfw|nudity|onlyfans|softcore|hardcore|fetish|ullu|kooku|primeplay|hotshots|besharams|voovi|moodx|jav|playboy|lust\s*stories|rabbit\s*movies|hunters\s*app|chikooflix|redprime|sexy\s*scenes)\b"

def is_adult(title, genre=None, desc=None):
    import re
    if title and re.search(ADULT_REGEX, title):
        return True
    if genre and re.search(ADULT_REGEX, genre):
        return True
    if desc and re.search(ADULT_REGEX, desc):
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

dash_sessions = {}
streams_cache = {}

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
    def fix_rep(match):
        tag = match.group(0)
        codec_m = re.search(r'codecs="([^"]+)"', tag)
        if codec_m:
            c = codec_m.group(1)
            if c.startswith('hev1.') and len(c.split('.')) < 4:
                tag = tag.replace(f'codecs="{c}"', 'codecs="hev1.1.6.L93.B0"')
            elif c.startswith('hvc1.') and len(c.split('.')) < 4:
                tag = tag.replace(f'codecs="{c}"', 'codecs="hvc1.1.6.L93.B0"')
            elif c.startswith('avc1.') and len(c.split('.')) < 3:
                tag = tag.replace(f'codecs="{c}"', 'codecs="avc1.4d401f"')
        return tag
    return re.sub(r'<Representation[^>]+>', fix_rep, manifest_text)

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
    if token:
        h["Authorization"] = f"Bearer {token}"
    return h

token_cache = {"token": None, "ts": 0}
def get_token(force=False):
    now = time.time()
    if not force and token_cache["token"] and (now - token_cache["ts"]) < 3600:
        return token_cache["token"]
    u = f"{BASE_URL}/wefeed-mobile-bff/tab/ranking-list?tabId=0&categoryType=4516404531735022304&page=1&perPage=1"
    req = urllib.request.Request(u, headers=get_api_headers(u))
    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            t = json.loads(resp.headers.get("x-user", "{}")).get("token")
            if t:
                token_cache["token"] = t
                token_cache["ts"] = now
                return t
    except Exception as e:
        print(f"[ERROR] Failed to get token: {e}", flush=True)
    return token_cache.get("token")

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

class MultiCyberServer(SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "*")
        super().end_headers()

    def do_OPTIONS(self):
        self.send_response(200)
        self.end_headers()

    def send_json(self, data, status=200):
        body = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def serve_static_file(self, filepath, content_type="text/html; charset=utf-8"):
        if not os.path.isfile(filepath):
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b"404 Not Found")
            return
        with open(filepath, "rb") as f:
            data = f.read()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        host = self.headers.get("Host", "").lower().split(":")[0]
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        qs = urllib.parse.parse_qs(parsed.query)

        # ----------------------------------------------------------------------
        # 1. Host-Based Routing (Subdomains)
        # ----------------------------------------------------------------------
        # If user visits music.ayush.ai.studio -> serve music.html on root
        if host.startswith("music.") and path in ["", "/"]:
            return self.serve_static_file("static/music.html")

        # If user visits flix.ayush.ai.studio -> serve flix.html on root
        if host.startswith("flix.") and path in ["", "/"]:
            return self.serve_static_file("static/flix.html")

        # If user visits api.ayush.ai.studio -> serve api.html on root
        if host.startswith("api.") and path in ["", "/"]:
            return self.serve_static_file("static/api.html")

        # ----------------------------------------------------------------------
        # 2. Path-Based Navigation (Works everywhere)
        # ----------------------------------------------------------------------
        if path in ["", "/"]:
            return self.serve_static_file("static/portfolio.html")

        if path in ["/music", "/music/"]:
            return self.serve_static_file("static/music.html")

        if path in ["/flix", "/flix/"]:
            return self.serve_static_file("static/flix.html")

        if path in ["/watch", "/watch/"]:
            return self.serve_static_file("static/watch.html")

        if path in ["/api", "/api/"]:
            return self.serve_static_file("static/api.html")

        # Static assets
        if path.startswith("/static/"):
            rel = path.lstrip("/")
            ct = "text/plain"
            if rel.endswith(".css"): ct = "text/css"
            elif rel.endswith(".js"): ct = "application/javascript"
            elif rel.endswith(".html"): ct = "text/html; charset=utf-8"
            elif rel.endswith(".wgt") or rel.endswith(".apk") or rel.endswith(".zip"): ct = "application/octet-stream"
            elif rel.endswith(".svg"): ct = "image/svg+xml"
            elif rel.endswith(".png"): ct = "image/png"
            return self.serve_static_file(rel, ct)

        if path.startswith("/lib/"):
            rel = path.lstrip("/")
            ct = "application/javascript"
            return self.serve_static_file(rel, ct)

        # ----------------------------------------------------------------------
        # 3. Streaming & DASH Media Proxy Engine
        # ----------------------------------------------------------------------
        if path.startswith("/stream/dash/"):
            return self.handle_dash_proxy(path)

        if path.startswith("/stream/proxy/"):
            video_url = qs.get("url", [""])[0]
            cookie = qs.get("cookie", [""])[0]
            return self.handle_stream_proxy(video_url, cookie)

        # ----------------------------------------------------------------------
        # 4. JSON REST API Endpoints
        # ----------------------------------------------------------------------
        if path == "/api/search":
            q = qs.get("q", [""])[0]
            return self.handle_api_search(q)

        if path == "/api/streams":
            sid = qs.get("id", [""])[0]
            se = int(qs.get("se", [0])[0])
            ep = int(qs.get("ep", [0])[0])
            return self.handle_api_streams(sid, se, ep)

        if path == "/api/home":
            return self.handle_api_home()

        # Fallback to standard handler
        return super().do_GET()

    # --- API HANDLERS ---
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
                        "rating": sub.get("imdbRatingValue") or "7.5",
                        "type": "series" if stype in (2, 7) else "movie",
                        "genre": genre,
                        "desc": desc,
                        "year": (sub.get("releaseDate") or "2026")[:4]
                    })
            self.send_json({"status": "success", "results": clean_results})
        except Exception as e:
            print(f"[ERROR] Search failed for '{query}': {e}", flush=True)
            self.send_json({"status": "error", "message": str(e)}, status=500)

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
            subject_candidates = [(sid, "Original Audio")]
            seen_cand_ids = {str(sid)}
            try:
                det_url = f"{BASE_URL}/wefeed-mobile-bff/subject-api/get?subjectId={sid}"
                det_res = api_request(det_url)
                for d in det_res.get("data", {}).get("dubs", []):
                    did = d.get("subjectId")
                    dname = (d.get("name") or d.get("lanName") or "Dub").strip()
                    if did and str(did) not in seen_cand_ids:
                        seen_cand_ids.add(str(did))
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
                        if ".mpd" in resolved_url.lower():
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

    def handle_api_home(self):
        try:
            url = f"{BASE_URL}/wefeed-mobile-bff/subject-api/search/v2"
            body = json.dumps({"page": 1, "perPage": 20, "keyword": "avengers"})
            resp = api_request(url, method="POST", body=body)
            self.send_json({"status": "success", "data": resp.get("data", {})})
        except Exception as e:
            self.send_json({"status": "error", "message": str(e)}, 500)

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

        target_url = sess["manifest_url"] if (filename == "manifest.mpd" or filename.endswith(".mpd")) else f"{sess['base_url']}/{filename}"
        range_hdr = self.headers.get("Range")
        if range_hdr: upstream_headers["Range"] = range_hdr

        try:
            if filename.endswith(".mpd") or filename == "manifest.mpd":
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
        except Exception as e:
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
    print(f"  Local Port: {PORT}", flush=True)
    print(f"  - Portfolio:  http://localhost:{PORT}/  (ayush.ai.studio)", flush=True)
    print(f"  - AyushMuzic: http://localhost:{PORT}/music (music.ayush.ai.studio)", flush=True)
    print(f"  - Ayushflix:  http://localhost:{PORT}/flix  (flix.ayush.ai.studio)", flush=True)
    print(f"  - Stream API: http://localhost:{PORT}/api   (api.ayush.ai.studio)", flush=True)
    print(f"===========================================================", flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nServer shutting down.", flush=True)
        httpd.server_close()

if __name__ == "__main__":
    run()
