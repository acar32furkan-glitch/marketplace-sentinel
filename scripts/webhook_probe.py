"""Yerel sahte webhook sunucusuna karşı teslimi gerçekten çalıştırır.

Belgelerdeki (`docs/webhook.md`) çıktılar bu betikle üretildi: sunucu 127.0.0.1 üzerinde dinler,
CLI ayrı bir süreç olarak çağrılır ve sunucunun gördüğü istek sayısı yazdırılır. İnternete çıkılmaz.

Kullanım:

    uv run python scripts/webhook_probe.py examples/data ok
    uv run python scripts/webhook_probe.py examples/data flaky
    uv run python scripts/webhook_probe.py examples/data redirect
    uv run python scripts/webhook_probe.py examples/data fail
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

MODES = ("ok", "flaky", "redirect", "fail")
SEEN: list[dict[str, object]] = []
MODE = "ok"


class Handler(BaseHTTPRequestHandler):
    """Moda göre 200/302/500 döndüren ve her isteği kaydeden sahte alıcı."""

    def do_POST(self) -> None:
        """Gövdeyi oku, kaydet ve moda göre yanıtla."""
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length)
        SEEN.append(
            {
                "path": self.path,
                "content_type": self.headers.get("Content-Type"),
                "user_agent": self.headers.get("User-Agent"),
                "bytes": len(raw),
                "event": json.loads(raw.decode("utf-8")).get("event"),
            }
        )
        if MODE == "redirect":
            status = 302
        elif MODE == "fail" or (MODE == "flaky" and len(SEEN) == 1):
            status = 500
        else:
            status = 200
        self.send_response(status)
        self.send_header("Location", "https://baska.example/hook")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def log_message(self, *_args: object) -> None:
        """Erişim günlüğünü sustur; çıktıyı betik yazıyor."""


def main() -> int:
    """Sahte sunucuyu başlat, CLI'yı koştur, iki tarafın gördüğünü yazdır."""
    global MODE  # noqa: PLW0603 - mod tek süreçlik betikte global
    parser = argparse.ArgumentParser(description="Webhook teslimini yerel sahte sunucuya karşı ölç.")
    parser.add_argument("fixtures", type=Path, help="Örnek veri klasörü (ör. examples/data).")
    parser.add_argument("mode", choices=MODES, nargs="?", default="ok", help="Sunucu davranışı.")
    args = parser.parse_args()
    MODE = args.mode

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    port = server.server_address[1]
    threading.Thread(target=server.serve_forever, daemon=True).start()
    command = [
        sys.executable,
        "-m",
        "sentinel",
        "scan",
        "--fixtures",
        str(args.fixtures),
        "--no-state-write",
        "--webhook-url",
        f"http://127.0.0.1:{port}/hook/gizli-belirtec",
        "--webhook-send",
        "--json",
    ]
    try:
        completed = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", check=False)
    finally:
        server.shutdown()

    print(f"mod: {MODE}")
    print(f"çıkış kodu: {completed.returncode}")
    print(f"stderr: {completed.stderr.strip()}")
    payload = json.loads(completed.stdout)
    print("json webhook bloğu: " + json.dumps(payload["webhook"], ensure_ascii=False))
    print(f"sunucunun gördüğü istek: {len(SEEN)}")
    for index, entry in enumerate(SEEN, start=1):
        print(f"  {index}. " + json.dumps(entry, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
