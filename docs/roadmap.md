# Yol Haritası

Her sürüm tek bir soruya cevap verir. Deterministik çekirdek (ADR-0001) ve durum/dedupe modeli
(ADR-0002) her sürümde korunur.

## v0.1.0 — Çalışan nöbetçi (bu sürüm)

- Profil-güdümlü kanal katmanı: pazaryerleri `profiles/*.yaml` ile eklenir, kod değil.
- Dört kural: `STOK_CAKISMASI`, `FIYAT_SAPMASI`, `LISTE_YOK`, `VERI_BAYAT`.
- Alarm durumu ve dedupe: `kod:sku` imzası, YENİ/DEVAM EDEN/ÇÖZÜLDÜ ayrımı, `state.json`.
- `scan` / `watch` / `state show` / `profiles` komutları; `--json`, `--report`, `--github-summary`,
  `--fail-on`, `--now`, `--no-state-write`, `--max-alerts`.
- Fixture tabanlı çalışma (`--fixtures`): kimlik bilgisi gerektirmez, determinizm sözleşmesi testlerle
  sabitlenmiştir.

## v0.2.0 — Teslim kanalları

Sorunun cevabı: **alarm operatörün gördüğü yere nasıl ulaşır?**

- **Webhook/Slack teslimi:** yeni ve kritik alarmları bir webhook'a (Slack/Teams) gönderen `deliver`
  katmanı. Gönderim deterministiktir: aynı alarm seti aynı payload'ı üretir; ağ çağrısı yalnızca
  teslim sınırında, kuralların dışında yapılır.
- **E-posta özeti:** günlük/haftalık özet raporu (yeni, devam eden, çözülen sayıları).
- **`--dry-run` / `--print-payload`:** teslimi ağa çıkmadan doğrulama.
- **Sessiz saat (quiet hours):** KRİTİK dışındaki alarmların belirli saatlerde bekletilmesi.

## v0.3.0 — Analiz derinliği

Sorunun cevabı: **bu tutarsızlık nereden geldi ve nereye gidiyor?**

- **Fiyat geçmişi + trend:** `history.json` ile fiyat/stok zaman serisi; sapmanın "yeni mi yoksa
  kalıcı mı" olduğunu trendle ayırt etme.
- **Buybox analizi:** aynı sku'da hangi kanalın fiyatı "kazanan" (buybox) konumda; fiyat değişiminin
  buybox'ı kaybettirip kaybetmediği.
- **Kural bazlı istatistik:** hangi kanal/profil en çok alarm üretiyor (gürültülü kanal tespiti).

## v0.4.0 — İnsan tarafı rapor

Sorunun cevabı: **teknik olmayan ekibe nasıl gösterilir?**

- **HTML/panel raporu:** tek dosyalık, kanallar arası sku matrisi ve durum rozetleri taşıyan rapor
  (`--report out.html`). Bir "skor" değil, filtre/litre edilebilir bir ihlal listesi.
- **Bildirim özeti grafikleri:** zaman içinde yeni/çözülen alarm eğrisi.

## Kapsam dışı (bilinçli)

- **Pazaryerine YAZMA.** Nöbetçi fiyat/stok **güncellemez**; yalnızca okur ve raporlar. Otomatik yazma
  yanlış bir güncellemeyi tüm kanallara yayma riski taşır ve ayrı bir güvenlik tartışması gerektirir.
- **Panel kazıma.** Veri resmî pazaryeri API'sinden veya kullanıcının verdiği fixture'dan gelir; panel
  oturumu açılmaz, HTML kazınmaz.
- **LLM kararı.** Anlam/içerik denetimi yoktur; kurallar sayısal ve zamansaldır ve kararı tek başına
  LLM veremez.
- **Determinizmi bozan teslim.** v0.2'de webhook yalnızca *teslim* katmanındadır; alarm üretimi ağdan
  bağımsız ve tekrarlanabilir kalır.
