"""Komut satırı arayüzü.

sentinel scan --fixtures examples/data [--state examples/data/state.json] [--json] [--fail-on POLICY]
sentinel state show --state examples/data/state.json [--json]
sentinel watch --fixtures examples/data --interval 900 --iterations 2 [--state ...]
sentinel profiles --fixtures examples/data [--json]
sentinel --version

Çıkış kodları: 0 alarm yok/çözüldü · 1 --fail-on politikası düştü · 2 girdi hatası.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from collections.abc import Callable, Mapping, Sequence
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from sentinel import __version__
from sentinel.channels import Channel
from sentinel.channels.fixture import FixtureChannel
from sentinel.models import Alert, ScanResult
from sentinel.parsing import DEMO_NOW
from sentinel.profiles import MarketplaceProfile, load_profiles
from sentinel.render import render_github_summary, render_scan_text
from sentinel.scan import FailPolicy, decide, run_scan
from sentinel.state import load_state, save_state

EXIT_OK = 0
EXIT_FAILED = 1
EXIT_INPUT_ERROR = 2
DEFAULT_FIXTURES = Path("examples/data")
PROFILES_SUBDIR = "profiles"
STATE_FILENAME = "state.json"


class InputError(ValueError):
    """Kullanıcı girdisi geçersiz (dosya yolu, ISO zaman damgası, bayrak değeri)."""


def build_parser() -> argparse.ArgumentParser:
    """Argparse ağacını kur (tek kök, görev başına alt komut)."""
    parser = argparse.ArgumentParser(
        prog="sentinel",
        description="Çok pazaryerli kanal çakışması nöbetçisi: yalnızca yeni durumları bildirir.",
    )
    parser.add_argument("--version", action="version", version=f"sentinel {__version__}")
    sub = parser.add_subparsers(dest="command")

    scan = sub.add_parser("scan", help="Kanalları tara ve yalnızca yeni/çözülen durumları bildir.")
    scan.add_argument("--fixtures", type=Path, default=DEFAULT_FIXTURES, help="Örnek veri klasörü.")
    scan.add_argument("--state", type=Path, default=None, help="Durum dosyası (varsayılan: <fixtures>/state.json).")
    scan.add_argument("--json", action="store_true", dest="as_json", help="Sonucu JSON olarak ver.")
    scan.add_argument("--report", type=Path, default=None, help="Sonucu bu dosyaya da yaz (JSON).")
    scan.add_argument(
        "--fail-on",
        choices=[policy.value for policy in FailPolicy],
        default=FailPolicy.NEW_CRITICAL.value,
        help="Kapı politikası (varsayılan: new-critical).",
    )
    scan.add_argument("--no-state-write", action="store_true", help="Durum dosyasını güncelleme.")
    scan.add_argument("--max-alerts", type=int, default=20, help="Konsolda gösterilecek en fazla uyarı.")
    scan.add_argument("--now", default=None, help="Referans an (ISO); verilmezse örnek veri çapası.")
    scan.add_argument(
        "--github-summary",
        action="store_true",
        help="Markdown özetini $GITHUB_STEP_SUMMARY dosyasına ekle (Actions iş özeti).",
    )

    state = sub.add_parser("state", help="Durum dosyası işlemleri.")
    state_sub = state.add_subparsers(dest="state_command")
    show = state_sub.add_parser("show", help="Kayıtlı imzaları göster.")
    show.add_argument("--state", type=Path, required=True, help="Durum dosyası.")
    show.add_argument("--json", action="store_true", dest="as_json", help="Sonucu JSON olarak ver.")

    watch = sub.add_parser("watch", help="Belirli aralıkla tekrar tara ve her turda özet yaz.")
    watch.add_argument("--fixtures", type=Path, default=DEFAULT_FIXTURES, help="Örnek veri klasörü.")
    watch.add_argument("--interval", type=float, default=900.0, help="Turlar arası saniye.")
    watch.add_argument("--iterations", type=int, default=1, help="Kaç tur çalıştırılacak.")
    watch.add_argument("--state", type=Path, default=None, help="Durum dosyası.")
    watch.add_argument("--max-alerts", type=int, default=20, help="Konsolda gösterilecek en fazla uyarı.")

    profiles = sub.add_parser("profiles", help="Yüklü pazaryeri profillerini özetle.")
    profiles.add_argument("--fixtures", type=Path, default=DEFAULT_FIXTURES, help="Örnek veri klasörü.")
    profiles.add_argument("--json", action="store_true", dest="as_json", help="Sonucu JSON olarak ver.")
    return parser


def _resolve_now(text: str | None) -> datetime:
    if text is None:
        return DEMO_NOW
    try:
        return datetime.fromisoformat(text)
    except ValueError as exc:
        msg = f"--now geçersiz ISO zaman damgası: {text}"
        raise InputError(msg) from exc


def _build_channels(fixtures: Path, profiles: Mapping[str, MarketplaceProfile]) -> dict[str, Channel]:
    return {name: FixtureChannel(profile, fixtures / f"{name}.json") for name, profile in profiles.items()}


def _load_channels(fixtures: Path) -> dict[str, Channel]:
    return _build_channels(fixtures, load_profiles(fixtures / PROFILES_SUBDIR))


def _alert_json(alert: Alert) -> dict[str, Any]:
    return alert.model_dump(mode="json")


def _payload(result: ScanResult, *, passed: bool, reasons: list[str], policy: FailPolicy) -> dict[str, Any]:
    return {
        "version": __version__,
        "generated_at": result.generated_at.isoformat(),
        "channels": list(result.channels),
        "listings": result.listings,
        "policy": policy.value,
        "passed": passed,
        "reasons": reasons,
        "counts": {"new": len(result.new), "ongoing": len(result.ongoing), "resolved": len(result.resolved)},
        "codes": result.by_code(),
        "errors": list(result.errors),
        "new": [_alert_json(alert) for alert in result.new],
        "ongoing": [_alert_json(alert) for alert in result.ongoing],
        "resolved": [_alert_json(alert) for alert in result.resolved],
        "alerts": [_alert_json(alert) for alert in result.alerts],
    }


def _write_github_summary(markdown: str) -> None:
    target = os.environ.get("GITHUB_STEP_SUMMARY", "").strip()
    if not target:
        print("uyarı: GITHUB_STEP_SUMMARY tanımlı değil, iş özeti yazılmadı.", file=sys.stderr)
        return
    with Path(target).open("a", encoding="utf-8") as handle:
        handle.write(markdown + "\n")


def cmd_scan(args: argparse.Namespace) -> int:
    """Kanalları tara, raporla ve (istenirse) durum dosyasını güncelle."""
    fixtures: Path = args.fixtures
    state_path: Path = args.state or (fixtures / STATE_FILENAME)
    now = _resolve_now(args.now)
    policy = FailPolicy(args.fail_on)
    channels = _load_channels(fixtures)
    result = run_scan(channels, now=now, previous_state=load_state(state_path))
    passed, reasons = decide(result, policy)

    if args.as_json or args.report:
        payload = _payload(result, passed=passed, reasons=reasons, policy=policy)
        if args.report:
            args.report.parent.mkdir(parents=True, exist_ok=True)
            args.report.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        if args.as_json:
            print(json.dumps(payload, ensure_ascii=False, indent=2))

    if not args.as_json:
        print(render_scan_text(result, max_alerts=args.max_alerts))
        if not passed:
            for reason in reasons:
                print(f"KARAR: KALDI ✘ — {reason}")

    if args.github_summary:
        _write_github_summary(render_github_summary(result, max_alerts=args.max_alerts))

    if not args.no_state_write:
        save_state(state_path, (*result.new, *result.ongoing), now=now)
    return EXIT_OK if passed else EXIT_FAILED


def cmd_state_show(args: argparse.Namespace) -> int:
    """Durum dosyasındaki imzaları göster."""
    path: Path = args.state
    if not path.is_file():
        msg = f"durum dosyası bulunamadı: {path}"
        raise FileNotFoundError(msg)
    state = load_state(path)
    if args.as_json:
        payload = {"state": str(path), "count": len(state), "signatures": state}
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return EXIT_OK
    print(f"DURUM DOSYASI — {path}")
    print(f"  kayıtlı imza: {len(state)}")
    if not state:
        print("  (kayıt yok)")
    for signature, first_seen in sorted(state.items()):
        print(f"  {signature:<30}  ilk görülme: {first_seen}")
    return EXIT_OK


def cmd_watch(args: argparse.Namespace) -> int:
    """Örnek kanalları belirli aralıkla tekrar tara; her turda özet yaz.

    ``now`` her turda ``interval`` kadar ilerletilir — saat okunmaz, bu yüzden demo deterministiktir.
    """
    fixtures: Path = args.fixtures
    state_path: Path = args.state or (fixtures / STATE_FILENAME)
    channels = _load_channels(fixtures)
    iterations = max(1, args.iterations)
    for turn in range(1, iterations + 1):
        now = DEMO_NOW + timedelta(seconds=args.interval * (turn - 1))
        result = run_scan(channels, now=now, previous_state=load_state(state_path))
        print(f"--- tur {turn}/{iterations} — {now:%d.%m.%Y %H:%M} ---")
        print(render_scan_text(result, max_alerts=args.max_alerts))
        save_state(state_path, (*result.new, *result.ongoing), now=now)
        if turn < iterations and args.interval > 0:
            time.sleep(args.interval)
    return EXIT_OK


def _profile_json(profile: MarketplaceProfile) -> dict[str, Any]:
    return {
        "name": profile.name,
        "base_url": profile.base_url,
        "products_path": profile.products_path,
        "auth": profile.auth.value,
        "items_path": profile.items_path,
        "field_map": profile.field_map.model_dump(),
    }


def cmd_profiles(args: argparse.Namespace) -> int:
    """Yüklü profillerin özetini yaz (ad, base_url, auth stili, alan eşlemesi)."""
    profiles = load_profiles(args.fixtures / PROFILES_SUBDIR)
    if args.as_json:
        payload = {"profiles": [_profile_json(profile) for profile in profiles.values()]}
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return EXIT_OK
    width = max(len(name) for name in profiles)
    print(f"marketplace-sentinel {__version__} · yüklü profil: {len(profiles)}")
    for profile in profiles.values():
        mapping = profile.field_map
        print(f"  {profile.name:<{width}}  {profile.auth.value:<6}  {profile.base_url}{profile.products_path}")
        print(
            f"  {'':<{width}}  alan eşlemesi: sku={mapping.sku}, title={mapping.title}, "
            f"price={mapping.price}, stock={mapping.stock}"
        )
        print(
            f"  {'':<{width}}  items_path={profile.items_path or '—'} · "
            f"sayfa={profile.page_param or '—'}/{profile.size_param or '—'} ({profile.page_size})"
        )
    return EXIT_OK


def main(argv: Sequence[str] | None = None) -> int:
    """Giriş noktası; hataları belgelenen çıkış kodlarına eşler."""
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command is None:
        parser.print_help()
        return EXIT_INPUT_ERROR
    handlers: dict[str, Callable[[argparse.Namespace], int]] = {
        "scan": cmd_scan,
        "watch": cmd_watch,
        "profiles": cmd_profiles,
    }
    try:
        if args.command == "state":
            if args.state_command != "show":
                print("girdi hatası: 'state' için 'show' alt komutu gerekir.", file=sys.stderr)
                return EXIT_INPUT_ERROR
            return cmd_state_show(args)
        return handlers[args.command](args)
    except (ValueError, FileNotFoundError) as exc:
        print(f"girdi hatası: {exc}", file=sys.stderr)
        return EXIT_INPUT_ERROR


if __name__ == "__main__":
    sys.exit(main())
