#!/usr/bin/env python3
"""
手机拍照直传网页服务端（不存手机相册 -> 内存流直传飞书多维表格 + Webhook 群提醒）
"""

import argparse
import base64
import json
import socket
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from feishu_wrongbook_cli import WrongbookCLI  # noqa: E402

HTML_FILE = SCRIPT_DIR.parent / "resources" / "capture.html"


def get_lan_ip() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


class CaptureHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt: str, *args) -> None:
        print(f"[WebCapture] {self.address_string()} - {fmt % args}")

    def do_GET(self) -> None:
        if self.path == "/" or self.path.startswith("/index") or self.path.startswith("/capture"):
            content = HTML_FILE.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(content)
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self) -> None:
        if self.path == "/api/upload":
            try:
                length = int(self.headers.get("Content-Length", "0"))
                raw_body = self.rfile.read(length).decode("utf-8")
                payload = json.loads(raw_body)
                b64_str: str = payload.get("image_base64", "")
                note: str = payload.get("note", "")

                if "," in b64_str:
                    b64_str = b64_str.split(",", 1)[1]
                image_bytes = base64.b64decode(b64_str)

                cli = WrongbookCLI()
                res = cli.upload_wrong_question(image_bytes=image_bytes, note=note)

                resp_bytes = json.dumps(res, ensure_ascii=False).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.end_headers()
                self.wfile.write(resp_bytes)
            except Exception as e:
                err_bytes = json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False).encode("utf-8")
                self.send_response(500)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.end_headers()
                self.wfile.write(err_bytes)
        else:
            self.send_response(404)
            self.end_headers()


def main() -> None:
    parser = argparse.ArgumentParser(description="启动手机错题直传网页服务")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()

    lan_ip = get_lan_ip()
    server = HTTPServer(("0.0.0.0", args.port), CaptureHandler)
    print("=" * 60)
    print("📸 手机数学错题直传网页服务已启动！（拍照不占手机相册）")
    print(f"👉 电脑本机访问: http://127.0.0.1:{args.port}")
    print(f"📱 手机局域网访问 (同Wi-Fi下发给老婆收藏): http://{lan_ip}:{args.port}")
    print("=" * 60)
    server.serve_forever()


if __name__ == "__main__":
    main()
