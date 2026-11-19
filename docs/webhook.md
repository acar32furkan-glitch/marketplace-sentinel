# Webhook teslimi — alarmı operatörün gördüğü yere gönder

Nöbetçi alarmı üretir; **teslim** ayrı bir adımdır. `--webhook-url` verildiğinde `scan` gövdeyi
hazırlar ve **varsayılan olarak göndermez** (kuru çalışma). Gerçek `POST` yalnızca `--webhook-send`
ile yapılır. Karar ve gerekçeler: [ADR-0004](adr/0004-webhook-teslimi.md).

## Üç komut

```bash
# 1) Kuru çalışma (varsayılan): gövde hazırlanır, özet + sha256 yazılır, ağa çıkılmaz.
uv run sentinel scan --fixtures examples/data --no-state-write \
  --webhook-url "https://hooks.example.com/services/T000/B000/gizli-belirtec"

# 2) Gövdeyi bayt bayt gözden geçir (gönderilen dosya ile aynı baytlar).
uv run sentinel scan --fixtures examples/data --no-state-write \
  --webhook-url "https://hooks.example.com/services/T000/B000/gizli-belirtec" \
  --webhook-body /tmp/webhook-govde.json

# 3) Gerçekten gönder (adresi ortam değişkeninde tutmak yeğlenir).
export SENTINEL_WEBHOOK_URL="https://hooks.example.com/services/T000/B000/gizli-belirtec"
uv run sentinel scan --fixtures examples/data --webhook-send
```

Kuru çalışmanın gerçek çıktısı (stderr):

```text
webhook: kuru çalışma — POST https://hooks.example.com/… · gövde 6302 bayt · sha256 cc8c1ae79535… · istek atılmadı
webhook: göndermek için --webhook-send ekleyin.
```

Üç ayrıntı bilinçli:

- **`/…`**: yol ve sorgu gizlenir. Sağlayıcılar belirteci yolun içine koyar; tam adres hiçbir çıktıya
  (konsol, `--json`, hata mesajı) yazılmaz.
- **`6302 bayt` + `sha256`**: gövdenin ne olduğunu ve değişip değişmediğini tek satırda görmenin yolu.
  `--webhook-body` dosyasının `sha256`'sı bu değerle aynıdır.
- **`istek atılmadı`**: kuru çalışmada HTTP istemcisi hiç kurulmaz; bir test bunu `httpx.Client`
  kurulursa patlayacak biçimde sabitler.

## Gövde

Gövde ayrı bir şema **uydurmaz**: `--json` ile aynı sözleşmeyi taşır, üstüne `event` ve `schema`
eklenir. Örnek veride gövdenin başı (tek satır, 6302 bayt):

```json
{"event":"scan","schema":1,"version":"0.1.0","generated_at":"2026-10-06T09:00:00+03:00","channels":["kanal_a","kanal_b"],"listings":14,"policy":"new-critical","passed":false,"reasons":["1 yeni kritik uyarı var (kod: STOK_CAKISMASI)"],"counts":{"new":5,"ongoing":1,"resolved":1},"codes":{"STOK_CAKISMASI":…
```

Alıcı tarafta işe yarayan alanlar:

| Alan | Ne için |
|------|---------|
| `event` · `schema` | Aynı adrese başka şeyler de POST ediliyorsa ayırt etmek (`event: "scan"`, `schema: 1`) |
| `counts` · `codes` | "Bu turda ne oldu" özeti; gövdeyi baştan sona okumadan karar |
| `new` / `ongoing` / `resolved` | Durum kırılımı (dedupe sayesinde tekrar bağırmaz) |
| `alerts` | Tüm alarmlar (`signature`, `severity`, `message_tr`, `detail_tr`, `hint_tr`) |
| `passed` · `reasons` | Kapı kararı; webhook alıcısı da aynı kararı görür |

`webhook` bloğu **gövdeye girmez** — gövde kendi teslim sonucunu taşıyamaz. Blok yalnızca `--json` ve
`--report` çıktısında vardır:

```json
"webhook": {"url": "https://hooks.example.com/…", "dry_run": true, "sent": false, "ok": true,
            "attempts": 0, "status_code": null, "bytes": 6302, "sha256": "cc8c1ae7…", "error": null}
```

## Teslim politikası

| Yanıt | Davranış |
|-------|----------|
| `2xx` | Teslim edildi; `attempts` kaçıncı denemede başarıldığını yazar |
| `429`, `500`, `502`, `503`, `504` | Üstel geri çekilmeyle yeniden dene (en fazla 3 deneme) |
| `401`, `403` | Anında dur: `kimlik reddedildi` (yanlış anahtarı tekrar denemek kimseyi kilitlemez) |
| Diğer `4xx` | Anında dur: `istek reddedildi` |
| `3xx` | Anında dur: `yönlendirme izlenmedi` — doğrulanmış adresi atlatmanın en kolay yolu |
| Ağ hatası (`ConnectError`, `ReadTimeout` …) | Yeniden dene, sonra `ağ hatası: <sınıf adı>` |

**Teslim hatası taramanın çıkış kodunu değiştirmez.** `0/1/2` kodları tarama kararını ve girdi
hatalarını anlatır; teslim hatası stderr'e ve `webhook.ok: false` alanına yazılır. CI'da teslimin
gerçekten gittiğini doğrulamak istiyorsanız JSON bloğunu okuyun:

```bash
uv run sentinel scan --fixtures content/data --webhook-send --json > rapor.json || true
uv run python -c "import json,sys; d=json.load(open('rapor.json')); assert d['webhook']['ok'], d['webhook']"
```

## Yerel sahte sunucuya karşı dört senaryo (gerçek çıktı)

Depodaki `scripts/webhook_probe.py` 127.0.0.1 üzerinde sahte bir alıcı açar, CLI'yı ayrı süreç
olarak çağırır ve **sunucunun gördüğü isteği** yazar. İnternete çıkılmaz.

| Senaryo | Komut | Sonuç (ölçüldü) |
|---------|-------|-----------------|
| Normal | `uv run python scripts/webhook_probe.py examples/data ok` | `webhook: teslim edildi — HTTP 200 · gövde 6302 bayt · 1 deneme` · sunucu 1 istek · `ok: true` |
| Geçici hata | `… flaky` | `HTTP 200 · 2 deneme` · sunucu 2 istek (birincisi 500) |
| Yönlendirme | `… redirect` | `uyarı: webhook teslim edilemedi — yönlendirme izlenmedi: HTTP 302 (1 deneme)` · sunucu 1 istek, takip yok |
| Kalıcı hata | `… fail` | `uyarı: … geçici hata: HTTP 500 (3 deneme); taramanın çıkış kodu değişmedi.` · sunucu 3 istek |

`ok` senaryosunda sunucunun kaydettiği istek:

```json
{"path": "/hook/gizli-belirtec", "content_type": "application/json",
 "user_agent": "marketplace-sentinel/0.1.0 (+https://github.com/acar32furkan-glitch/marketplace-sentinel)",
 "bytes": 6302, "event": "scan"}
```

Sunucu yolun tamamını görür (belirteç ona gider), ama **çıktıda** yalnızca `http://127.0.0.1:6506/…`
yazılır. `fail` senaryosunda çıkış kodu `1` kaldı: kod tarama kararından geliyor, teslimden değil.

## Adres doğrulama (çıkış kodu `2`)

Geçersiz adres taramayı hiç başlatmaz. Ölçülen mesajlar:

```text
girdi hatası: --webhook-url: webhook adresi http:// veya https:// ile başlamalı (görülen: ftp): ftp://hooks.example.test/…
girdi hatası: --webhook-url: webhook adresine kullanıcı/şifre gömülmemeli: adres günlüğe sızar, kimlik bilgisi başlıkla verilir
girdi hatası: --webhook-url: webhook adresinde '#' parçası olmamalı: sunucuya hiç gitmez, yanlış adrese POST sanılır
girdi hatası: --webhook-url: webhook adresinde sunucu adı yok: (adres çözülemedi)
```

`SENTINEL_WEBHOOK_URL` de aynı doğrulamadan geçer; hata mesajı kaynağı adlandırır
(`girdi hatası: SENTINEL_WEBHOOK_URL: …`), böylece "hangi adres bozuk?" sorusu tahmine kalmaz.

## Neyi yapmaz

- **Pazaryerine yazmaz.** Tek yönlü `POST`, kullanıcının verdiği adrese; pazaryeri hesabına istek yok.
- **Yeniden göndermez.** Kuyruk/outbox yok: teslim edilemeyen tur kaybolur, bir sonraki tur yalnızca
  yeni durumları taşır. Kalıcı teslim garantisi isteniyorsa alıcı tarafında kuyruk kurulmalı.
- **İmzalamaz.** `HMAC` başlığı yok; alıcıyı korumak için belirteçli adres (Slack/Discord deseni)
  veya ağ seviyesinde kısıt kullanılmalı. Bu, v0.2.0'ın açık maddesidir.
- **`watch` ile birlikte çalışmaz.** Teslim yalnızca `scan` komutundadır; uzun koşan `watch` her turda
  ayrı süreç çağırmak yerine tek `scan` çağrısıyla zamanlanmalıdır.
