"""Tarama: kanalları çeker, kuralları çalıştırır ve durum takibini uygular.

Kimlik bilgisi eksikliği dahil kanal hataları **taramayı düşürmez**: diğer kanallarla devam edilir.
Hatalı kanal kural motorundan çıkarılır, böylece eksik veri yüzünden yanlış "liste yok" veya
"stok çakışması" uyarısı üretilmez.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from enum import StrEnum

from sentinel.channels import Channel, ChannelError
from sentinel.models import Alert, Listing, ScanResult, Severity
from sentinel.rules import RULES, RuleContext, Thresholds, alert_sort_key
from sentinel.state import classify


class FailPolicy(StrEnum):
    """``--fail-on`` politikası: taramanın çıkış kodunu belirler."""

    NONE = "none"
    NEW_CRITICAL = "new-critical"
    ANY_NEW = "any-new"


def run_scan(
    channels: Mapping[str, Channel],
    *,
    thresholds: Thresholds | None = None,
    now: datetime,
    previous_state: dict[str, str] | None = None,
) -> ScanResult:
    """Her kanaldan listeleri çek, kuralları çalıştır ve durum takibini uygula.

    Args:
        channels: Kanal adı → kanal eşlemesi (sıralama ad üzerinden yapılır, deterministik).
        thresholds: Politika eşikleri; verilmezse varsayılanlar kullanılır.
        now: Referans an — çağıran verir, nöbetçi saati kendisi okumaz.
        previous_state: Önceki turun imza → ilk görülme eşlemesi.

    Returns:
        Durum kırılımı ve kanal hatalarını taşıyan :class:`ScanResult`.
    """
    limits = thresholds or Thresholds()
    listings: list[Listing] = []
    errors: list[str] = []
    healthy: list[str] = []
    for name in sorted(channels):
        channel = channels[name]
        try:
            fetched = channel.fetch_listings()
        except ChannelError as exc:
            errors.append(f"{name}: {exc}")
            continue
        healthy.append(name)
        listings.extend(fetched)

    context = RuleContext(
        listings=tuple(listings),
        thresholds=limits,
        now=now,
        channels=tuple(healthy),
    )
    alerts: list[Alert] = []
    for check in RULES.values():
        alerts.extend(check(context).alerts)
    ordered = tuple(sorted(alerts, key=alert_sort_key))
    new, ongoing, resolved = classify(list(ordered), dict(previous_state or {}), now=now)
    return ScanResult(
        generated_at=now,
        channels=tuple(sorted(channels)),
        listings=len(listings),
        alerts=ordered,
        new=tuple(new),
        ongoing=tuple(ongoing),
        resolved=tuple(resolved),
        errors=tuple(errors),
    )


def decide(result: ScanResult, policy: FailPolicy) -> tuple[bool, list[str]]:
    """``(geçti_mi, nedenler)`` döndür — politika koda gömülü değil, dışarıdan gelir."""
    if policy is FailPolicy.NONE:
        return (True, [])
    if policy is FailPolicy.ANY_NEW:
        if not result.new:
            return (True, [])
        return (False, [f"{len(result.new)} yeni uyarı var (fail-on=any-new)"])
    criticals = [alert for alert in result.new if alert.severity is Severity.CRITICAL]
    if not criticals:
        return (True, [])
    codes = ", ".join(sorted({alert.code for alert in criticals}))
    return (False, [f"{len(criticals)} yeni kritik uyarı var (kod: {codes})"])


__all__ = ["FailPolicy", "decide", "run_scan"]
