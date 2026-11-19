# Değişiklik Günlüğü

Bu dosya [Keep a Changelog](https://keepachangelog.com/tr/1.1.0/) biçimini izler ve proje
[Semantic Versioning](https://semver.org/lang/tr/) kullanır.

## [Yayınlanmadı]

### Eklendi
- **Webhook teslimi (`--webhook-url`, `--webhook-send`, `--webhook-body`):** `scan` sonucunu JSON
  olarak dışarı POST eder. Varsayılan **kuru çalışmadır** — gövde, bayt sayısı ve `sha256` yazılır,
  ağa çıkılmaz; gerçek teslim açık `--webhook-send` ister. Adres `SENTINEL_WEBHOOK_URL` ortam
  değişkeninden de okunur (bayrak kazanır).
- **Maskeleme:** webhook adresi hiçbir çıktıda tam görünmez (`https://host/…`); Slack/Discord
  belirteçleri yolda durduğu için konsol, `--json` ve hata mesajları yalnızca maskeli adresi taşır.
- **Teslim politikası:** `429`/`5xx` ve ağ hatasında üstel geri çekilmeyle en fazla 3 deneme;
  `401`/`403` ve diğer `4xx` anında durur; `3xx` **izlenmez** (teslim hatası). Teslim hatası
  taramanın çıkış kodunu değiştirmez; `--json`/`--report` çıktısındaki `webhook` bloğu `ok: false`,
  `error`, `attempts`, `status_code` taşır.
- **Katı adres doğrulaması:** yalnızca `http`/`https`; adrese gömülü kullanıcı/şifre ve `#` parçası
  girdi hatası (çıkış `2`).
- **Doğrulama betiği:** `scripts/webhook_probe.py` yerel sahte sunucuya karşı dört senaryoyu
  (normal, geçici hata, yönlendirme, kalıcı hata) gerçekten koşturur; çıktılar `docs/webhook.md`'de.
- **Belgeler:** `docs/webhook.md`, [ADR-0004](docs/adr/0004-webhook-teslimi.md), README/README.en.md
  bölümü, mimari tablosu satırı, SECURITY.md tehdit modeli güncellemesi.

### Değişti
- `--json` / `--report` sözleşmesine, yalnızca webhook yapılandırıldığında `webhook` bloğu eklenir;
  webhook yoksa çıktı birebir eskisi gibidir (testle sabit).
- Test sayısı 157 → 195; kapsam %98.

## [0.1.0] - 2026-10-06

### Eklendi
- **Profil-güdümlü kanal katmanı:** pazaryerleri kodla değil `profiles/*.yaml` dosyalarıyla eklenir;
  alan eşlemesi (`field_map`), kimlik doğrulama stili ve sayfalama/yol bilgisi veri olarak taşınır.
  Aynı kural motoru her kanala uygulanır.
- **Dört kural:** `STOK_CAKISMASI` (kanallar arası stok farkı), `FIYAT_SAPMASI` (kanallar arası fiyat
  farkı), `LISTE_YOK` (ürün tanımlı kanallardan birinde yok), `VERI_BAYAT` (kanal verisi bayatladı).
  Her kural saf fonksiyondur: IO yok, saat yok, rastgelelik yok.
- **Önem ve eşik modeli:** `KRİTİK` / `UYARI` / `BİLGİ` (`Thresholds` ile tek yerden yönetilir).
  Varsayılanlar: fiyat farkı %5 (fiyat iki katına çıkarsa kritik), stok farkı 5 adet (bir kanalda 0,
  diğerinde ≥10 ise kritik), bayatlama 48 saat (48–96 saat bilgi, ≥96 saat uyarı).
- **Alarm durumu ve dedupe:** her alarm `kod:sku` imzasıyla tanımlanır; `state.json` önceki koşuyu
  taşır ve nöbetçi yalnızca **YENİ** / **DEVAM EDEN** / **ÇÖZÜLDÜ** ayrımını bildirir — aynı sorun
  her koşuda tekrar bağırılmaz (alarm fırtınası yok).
- **Determinizm:** zaman dışarıdan verilir (`--now`), ağ çağrısı yoktur, LLM yoktur; alarmlar
  `(önem, kod, sku)` ile deterministik sıralanır ve aynı girdi her zaman aynı çıktıyı üretir.
- **Fixture tabanlı çalışma:** `scan --fixtures <dizin>` kimlik bilgisi gerektirmeden çalışır;
  girdi fixture'dan mı gerçek istemciden mi geldiğini kural motoru ayırt etmez.
- **Komutlar:** `scan`, `watch` (`--interval`, `--iterations`), `state show`, `profiles`, `--version`.
- **`scan` bayrakları:** `--fixtures`, `--state`, `--json`, `--report <dosya>`,
  `--fail-on {none,new-critical,any-new}` (varsayılan `new-critical`), `--no-state-write`,
  `--max-alerts`, `--now <ISO>`, `--github-summary`.
- **Çıkış kodları:** `0` yeni kritik alarm yok, `1` `--fail-on` politikası düştü, `2` girdi hatası
  (bozuk profil, okunamayan fixture, geçersiz durum dosyası).
- **Çıktılar:** Türkçe konsol raporu (önem renkleriyle), `--json` sözleşmesi, `--report` dosyası ve
  `--github-summary` (Actions iş özeti için Markdown).
- **Kalite:** determinizm sözleşmesi, durum makinesi ve CLI sözleşmesi testlerle sabitlendi;
  tüm testler geçiyor, `ruff` + `mypy --strict` temiz, kapsam `--cov-fail-under=85` ile korunuyor,
  GitHub Actions CI (Python 3.12 ve 3.13 matrisi) ve Dependabot yapılandırıldı.
- **Dokümantasyon:** mimari, kural sözlüğü, iki ADR, yol haritası ve gerçek çıktıdan üretilen SVG demo
  (`scripts/make_demo_svg.py` → `docs/assets/demo.svg`).
