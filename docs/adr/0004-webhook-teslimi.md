# ADR-0004 — Webhook teslimi var, ama varsayılanı kuru çalışma ve adres maskeli

- **Durum:** Kabul edildi
- **Tarih:** 2026-11-19

## Bağlam: alarm operatörün gördüğü yere ulaşmalı, ama "ağ yok" sözü bozulmamalı

v0.1.0'ın en güçlü iddiası şuydu: *"Ağ yok, LLM yok, saat dışarıdan"* — aynı girdi + aynı `--now` her
zaman aynı alarmları üretir. Bu iddia üç şeyi garanti ediyordu: tekrarlanabilir CI çıktısı, sızacak
kimlik bilgisi olmaması ve testlerin hızlı/ağsız koşması.

Ama alarm üretmek tek başına yetmiyor: kullanıcı `scan`'i 6 saatte bir zamanlıyor ve sonucu **kimse
görmüyor**. Yol haritasındaki v0.2.0 maddesi tam olarak buydu ("alarm operatörün gördüğü yere nasıl
ulaşır?"). Teslim eklenirken iki gerçek risk var:

1. **Determinizm sızıntısı.** Teslim çağrısı ölçüm yoluna karışırsa (kural üretimi sırasında) CI
   çıktısı ağa bağımlı hâle gelir; "aynı girdi aynı çıktı" sözü düşer.
2. **Belirteç sızıntısı.** Slack/Discord/Teams webhook adreslerinde **belirteç yolun içindedir**
   (`https://hooks.slack.com/services/T000/B000/XXXX`). Bu adres bir kez CI günlüğüne, `--json`
   çıktısına veya bir hata mesajına düşerse, sızıntıyı geri almanın tek yolu belirteci iptal etmektir.

## Karar

Teslim **ayrı bir modüldür** (`src/sentinel/webhook.py`), ölçüm yolunun dışındadır ve dört kurala
bağlıdır.

| Kural | Gerekçe |
|-------|---------|
| **Varsayılan kuru çalışma.** `--webhook-url` tek başına gövdeyi hazırlar, bayt sayısını ve `sha256` özetini yazar; istek atılmaz. Gerçek `POST` yalnızca açık `--webhook-send` ile. | Yanlışlıkla canlı bir kanala alarm göndermek geri alınamaz; kuru çalışma aynı gövdeyi gözden geçirmeyi mümkün kılar (`--webhook-body` ile bayt bayt). |
| **Adres her çıktıda maskeli.** `mask_url` yalnızca `şema://sunucu` bırakır; yol ve sorgu `…` olur. | Belirteç yolda durur; maskesiz tek satır günlük sızıntıdır. `--json` bloğunda da tam adres yoktur. |
| **Katı adres doğrulaması.** Yalnızca `http`/`https`; adrese gömülü kullanıcı/şifre ve `#` parçası reddedilir (çıkış `2`). | `ftp://` bir teslim değildir; gömülü kimlik bilgisi istek başlığına dönüşür ve günlüğe sızar; sunucu `#` parçasını hiç görmez, sessiz yanlış adres sanılır. |
| **Yönlendirme izlenmez.** `3xx` teslim hatasıdır. | İmzalı/bağımlı gövdeyi yönlendirme ile başka bir adrese taşımak, doğrulanmış adresi atlatmanın en kolay yoludur. |

Teslim hatası **taramanın çıkış kodunu değiştirmez**: `0/1/2` kodları tarama kararını (`--fail-on`)
ve girdi hatalarını anlatır. Bunun bedeli açıkça kabul edildi — teslim hatası görünmez kalmasın diye
stderr'e tek satır uyarı ve `--json`/`--report` çıktısına `webhook` bloğu (`ok: false`, `error`,
`attempts`, `status_code`) yazılır. CI'da teslimin gerçekten gittiğini doğrulamak isteyen iş, JSON
bloğunu okumalıdır.

## Sonuçlar

- **Determinizm korunur:** gövde yalnızca `ScanResult`'tan üretilir (`--json` ile birebir aynı
  sözleşme + `event`/`schema` zarfı), teslim sonucu gövdeye **girmez** — gövde kendi teslim
  sonucunu taşıyamaz; `webhook` bloğu yalnızca `--json`/`--report` üzerinde eklenir.
- **Kararlı özet:** `encode_body` `ensure_ascii=False` ve ayırıcısız yazar; aynı tarama aynı `sha256`
  üretir. Ölçüldü: örnek veri için gövde 6302 bayt, `sha256 cc8c1ae7…`; kuru çalışma, `--webhook-body`
  ve gerçek teslimde gönderilen baytlar birebir aynı.
- **Sır komut satırında gerekmez:** adres `SENTINEL_WEBHOOK_URL` ortam değişkeninden de okunur
  (bayrak verilirse bayrak kazanır) — kabuk geçmişi ve iş tanımı temiz kalır.
- **Yeniden deneme tek kural:** `429`/`5xx` ve ağ hatası üstel geri çekilmeyle en fazla 3 deneme;
  `401`/`403` ve diğer `4xx` anında durur (yanlış anahtarı tekrar denemek kimseyi kilitlemez).
- **Testler ağsız:** 38 test `respx` ile koşar; kuru çalışma testi ayrıca "HTTP istemcisi hiç
  kurulmadı" iddiasını taşır. Böylece "ağ yok" sözü varsayılan yolda hâlâ testle sabittir.

## Alternatifler ve neden reddedildi

- **Teslimi kanal katmanına koymak (`channels/`).** Kanal protokolü **salt okunur**: yazma üyesi
  yoktur. Bir POST'u oraya koymak, "nöbetçi satıcının hesabına yazmaz" sözünü protokol seviyesinde
  bozardı.
- **Varsayılanı gerçek gönderim yapmak.** Tek bir yanlış adres, test ortamından canlı Slack kanalına
  alarm yağdırır; kuru çalışma varsayılanı bu hatayı yapısal olarak imkânsız kılar.
- **Adresi loglayıp "dikkatli olun" demek.** Sızıntı bir politika notuyla değil, kodla engellenir.
- **Teslim hatasında çıkış kodunu `1` yapmak.** O zaman "alarm var" ile "teslim gitmedi" aynı sinyale
  düşer ve CI'daki iki farklı arıza ayırt edilemez.
