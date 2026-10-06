"""`sentinel scan` çıktısını SVG "terminal kaydı" olarak üretir.

README'de ekran görüntüsü yerine gerçek çıktının görseli durur: betik `examples/data`
fixture'ları üzerinde nöbetçiyi çalıştırır ve metni renkli bir SVG'ye çevirir. Çıktı değiştiğinde
görsel de kendiliğinden güncellenir (`make demo-svg`).

Determinizm: zaman `sentinel.parsing.DEMO_NOW` çapasından gelir (CLI'nin `--fixtures` demosuyla aynı
an), böylece betik her koşuda aynı SVG'yi üretir; ağ çağrısı ve rastgelelik yoktur.
"""

from __future__ import annotations

import html
from pathlib import Path

from sentinel.channels.fixture import FixtureChannel
from sentinel.parsing import DEMO_NOW
from sentinel.profiles import load_profiles
from sentinel.render import render_scan_text
from sentinel.rules import Thresholds
from sentinel.scan import FailPolicy, decide, run_scan
from sentinel.state import load_state

PROJECT = Path(__file__).resolve().parent.parent
DATA = PROJECT / "examples" / "data"
PROFILES = DATA / "profiles"
STATE = DATA / "state.json"
OUTPUT = PROJECT / "docs" / "assets" / "demo.svg"

CHAR_WIDTH = 7.62
LINE_HEIGHT = 19
PADDING_X = 22
PADDING_TOP = 62
MAX_CHARS = 112

BACKGROUND = "#0b1120"
CHROME = "#1e293b"
TEXT = "#e2e8f0"
DIM = "#94a3b8"
COLORS = {
    "[KRİTİK]": "#f87171",
    "[UYARI]": "#fbbf24",
    "[BİLGİ]": "#38bdf8",
    "KARAR: KALDI": "#f87171",
    "KARAR: GEÇTİ": "#4ade80",
}


def wrap(lines: list[str], *, width: int = MAX_CHARS) -> list[str]:
    """Uzun satırları görselde taşmayacak biçimde böl."""
    wrapped: list[str] = []
    for line in lines:
        if len(line) <= width:
            wrapped.append(line)
            continue
        indent = " " * (line.index(":") + 2 if ":" in line[:16] else 7)
        current = line
        while len(current) > width:
            cut = current.rfind(" ", 0, width)
            cut = cut if cut > 20 else width
            wrapped.append(current[:cut])
            current = indent + current[cut:].lstrip()
        wrapped.append(current)
    return wrapped


def color_for(line: str) -> str:
    """Satırın rengini içeriğe göre seç (önem/durum etiketleri, karar satırı)."""
    for marker, color in COLORS.items():
        if marker in line:
            return color
    if line.startswith(("  ", "     ")) or not line.strip():
        return DIM
    return TEXT


def build_svg(lines: list[str], *, title: str) -> str:
    """Render the lines as a dark terminal-style SVG."""
    lines = [line[:MAX_CHARS] for line in lines]
    width = int(max(len(line) for line in lines) * CHAR_WIDTH) + PADDING_X * 2
    height = PADDING_TOP + len(lines) * LINE_HEIGHT + 26
    rows: list[str] = []
    for index, line in enumerate(lines):
        y = PADDING_TOP + index * LINE_HEIGHT
        color = color_for(line)
        content = html.escape(line, quote=False)
        rows.append(
            f'<text x="{PADDING_X}" y="{y}" fill="{color}" font-family="ui-monospace, SFMono-Regular, '
            f'Menlo, Consolas, monospace" font-size="13.5" xml:space="preserve">{content}</text>'
        )
    return "\n".join(
        [
            (
                f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
                f'viewBox="0 0 {width} {height}" role="img" aria-label="{html.escape(title)}">'
            ),
            f'  <rect width="{width}" height="{height}" rx="10" fill="{BACKGROUND}"/>',
            f'  <rect width="{width}" height="38" rx="10" fill="{CHROME}"/>',
            f'  <rect y="28" width="{width}" height="10" fill="{CHROME}"/>',
            '  <circle cx="20" cy="19" r="6" fill="#f87171"/>',
            '  <circle cx="40" cy="19" r="6" fill="#fbbf24"/>',
            '  <circle cx="60" cy="19" r="6" fill="#4ade80"/>',
            (
                f'  <text x="{PADDING_X + 60}" y="24" fill="{DIM}" font-family="ui-sans-serif, system-ui, '
                f'sans-serif" font-size="12.5">{html.escape(title)}</text>'
            ),
            *("  " + row for row in rows),
            "</svg>",
        ]
    )


def build_channels() -> dict[str, FixtureChannel]:
    """Her profil için, aynı adlı fixture dosyasından beslenen bir örnek kanal kur."""
    return {name: FixtureChannel(profile, DATA / f"{name}.json") for name, profile in load_profiles(PROFILES).items()}


def main() -> int:
    """Run the sentinel on the bundled fixtures and write the SVG."""
    channels = build_channels()
    result = run_scan(
        channels,
        thresholds=Thresholds(),
        now=DEMO_NOW,
        previous_state=load_state(STATE),
    )
    text = render_scan_text(result, max_alerts=8)
    passed, reasons = decide(result, FailPolicy.NEW_CRITICAL)
    if not passed:
        text = "\n".join([text, "KARAR: KALDI ✘ — " + "; ".join(reasons)])
    lines = wrap(text.splitlines())
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(build_svg(lines, title="sentinel scan — örnek fixture'lar"), encoding="utf-8")
    print(f"yazıldı: {OUTPUT} ({len(lines)} satır, {len(result.new)} yeni uyarı)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
