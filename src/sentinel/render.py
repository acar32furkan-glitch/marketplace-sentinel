"""Konsol, Markdown ve GitHub Actions iş özeti biçiminde çıktı.

Metinler Türkçedir: nöbetçiyi okuyan kişi satıcıdır. Kod, SKU ve kanal adları olduğu gibi kalır ki
CI kaydı ve kural sözlüğü birebir eşleşsin.
"""

from __future__ import annotations

from sentinel import __version__
from sentinel.models import Alert, AlertStatus, ScanResult, Severity

_BULLET = {Severity.CRITICAL: "[KRİTİK]", Severity.WARNING: "[UYARI]", Severity.INFO: "[BİLGİ]"}
_RULE_WIDTH = 72
_STATUS_LABEL = {AlertStatus.NEW: "yeni", AlertStatus.ONGOING: "devam", AlertStatus.RESOLVED: "çözüldü"}


def render_scan_text(result: ScanResult, *, max_alerts: int = 20) -> str:
    """Türkçe konsol raporunu üret."""
    lines: list[str] = []
    lines.append(f"KANAL ÇAKIŞMASI NÖBETÇİSİ — {result.generated_at:%d.%m.%Y %H:%M}")
    lines.append(f"  kanal: {', '.join(result.channels) or '—'}  ·  listelenen ürün: {result.listings}")
    lines.append(
        f"  YENİ {len(result.new)}  ·  DEVAM EDEN {len(result.ongoing)}  ·  ÇÖZÜLDÜ {len(result.resolved)}"
        f"  ·  KRİTİK {result.count(Severity.CRITICAL)}  ·  UYARI {result.count(Severity.WARNING)}"
    )
    lines.append("-" * _RULE_WIDTH)
    _append_group(lines, "YENİ", result.new, max_alerts)
    _append_group(lines, "DEVAM EDEN", result.ongoing, max_alerts)
    _append_group(lines, "ÇÖZÜLDÜ", result.resolved, max_alerts)
    if result.errors:
        lines.append("-" * _RULE_WIDTH)
        lines.extend(f"not: {error}" for error in result.errors)
    if not (result.new or result.ongoing or result.resolved):
        lines.append("")
        lines.append("Bildirilecek bir şey yok. 🎉")
    return "\n".join(lines)


def _append_group(lines: list[str], title: str, alerts: tuple[Alert, ...], max_alerts: int) -> None:
    if not alerts:
        return
    limit = len(alerts) if max_alerts < 0 else max_alerts
    shown = alerts[:limit]
    lines.append("")
    lines.append(f"{title} ({len(alerts)})")
    for index, alert in enumerate(shown, start=1):
        lines.append(f"{index:>3}. {_BULLET[alert.severity]} [{alert.code}] {alert.message_tr}")
        lines.append(f"     kanal  : {', '.join(alert.marketplaces) or '—'}")
        lines.append(f"     durum  : {alert.detail_tr}")
        lines.append(f"     aksiyon: {alert.hint_tr}")
    hidden = len(alerts) - len(shown)
    if hidden > 0:
        lines.append(f"  … {hidden} uyarı daha var (--max-alerts ile artırın).")


def render_markdown(result: ScanResult, *, max_alerts: int = 20) -> str:
    """PR yorumu veya iş özeti için kompakt Markdown üret."""
    lines = [
        f"### Kanal çakışması nöbetçisi — {result.generated_at:%d.%m.%Y %H:%M}",
        "",
        (f"**Yeni:** {len(result.new)} · **Devam eden:** {len(result.ongoing)} · **Çözüldü:** {len(result.resolved)}"),
        "",
        f"- kanal: {', '.join(result.channels) or '—'}",
        f"- listelenen ürün: {result.listings}",
        f"- kritik: {result.count(Severity.CRITICAL)} · uyarı: {result.count(Severity.WARNING)}",
    ]
    codes = result.by_code()
    if codes:
        lines.append("- kod dağılımı: " + ", ".join(f"`{code}` ×{count}" for code, count in sorted(codes.items())))
    active = (*result.new, *result.ongoing)
    if active:
        lines.extend(["", "| Durum | Önem | Kod | SKU | Kanallar |", "|-------|------|-----|-----|----------|"])
        limit = len(active) if max_alerts < 0 else max_alerts
        lines.extend(
            f"| {_STATUS_LABEL[alert.status]} | {alert.severity.severity_tr} | `{alert.code}` | {alert.sku} |"
            f" {', '.join(alert.marketplaces) or '—'} |"
            for alert in active[:limit]
        )
    if result.resolved:
        lines.extend(["", "**Çözülen:** " + ", ".join(f"`{alert.signature}`" for alert in result.resolved)])
    if result.errors:
        lines.extend(["", "**Kanal hataları:**"])
        lines.extend(f"- {error}" for error in result.errors)
    lines.extend(["", f"<sub>marketplace-sentinel {__version__} · deterministik kural motoru</sub>"])
    return "\n".join(lines)


def render_github_summary(result: ScanResult, *, max_alerts: int = 20) -> str:
    """GitHub Actions iş özeti için Markdown (``$GITHUB_STEP_SUMMARY`` dosyasına eklenir)."""
    return render_markdown(result, max_alerts=max_alerts)


__all__ = ["render_github_summary", "render_markdown", "render_scan_text"]
