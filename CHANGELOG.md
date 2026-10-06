# Değişiklik Günlüğü

Bu dosya [Keep a Changelog](https://keepachangelog.com/tr/1.1.0/) biçimini izler ve proje
[Semantic Versioning](https://semver.org/lang/tr/) kullanır.

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
