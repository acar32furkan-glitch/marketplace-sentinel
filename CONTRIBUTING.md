# Katkı Rehberi

Teşekkürler! Bu proje **deterministik ve yan etkisiz kalmayı** bir tasarım ilkesi olarak benimser;
katkıların tamamı bu çizgide olmalıdır.

## Hızlı kurulum

```bash
git clone https://github.com/acar32furkan-glitch/marketplace-sentinel
cd marketplace-sentinel
uv sync --all-extras --dev
uv run sentinel scan --fixtures examples/data   # kimlik bilgisi gerekmez
uv run pytest
```

## Determinizm kuralları (pazarlık dışı)

1. **Ağ çağrısı yok.** Kural ve ölçüm katmanı saf fonksiyondur; veri dışarıdan (fixture veya çağıran
   tarafından) verilir. Ölçüm içinde `requests`/`httpx` çağrısı tasarım tartışması gerektirir
   (bkz. `docs/adr/0001-profile-driven-adapters.md`).
2. **Saat dışarıdan verilir.** `--now` ile enjekte edilir; kural içinde `datetime.now()` çağrılmaz.
   `VERI_BAYAT` gibi zamana bağlı kurallar bu yüzden `now` parametresini alır.
3. **Rastgelelik yok.** `random`, UUID, dict sırasına bağlı çıktı yok. Alarmlar `(önem, kod, sku)` ile
   deterministik sıralanır; aynı girdi her zaman aynı çıktıyı üretir.
4. **Durum dışsaldır.** Nöbetçi durumu kendi belleğinde tutmaz; `state.json` dosyası girdi ve çıktıdır.
   Aynı girdi + aynı durum → aynı YENİ/DEVAM EDEN/ÇÖZÜLDÜ ayrımı (`tests` bunu sabitler).
5. **Yanlış alarm, kaçırmaktan pahalıdır.** Bir kural emin olmadığında susar; eksik veri "0 stok"
   değildir, "bilinmiyor"dur ve alarm üretmez.

## Yeni kural ekleme adımları

1. `src/sentinel/rules.py` içine saf bir fonksiyon yaz: girdi bağlamı (`RuleContext`: listeler +
   eşikler + `now` + sağlıklı kanallar), çıktı `RuleOutcome` (kapsam `checked` + uyarılar). Fonksiyonu
   `RULES` sözlüğüne ve `RULE_LABELS` etiketlerine ekle.
2. Kural kodunu sabit olarak tanımla (`STOK_CAKISMASI` biçiminde büyük harf, alt çizgi) ve önem
   seviyesini (`KRİTİK`/`UYARI`/`BİLGİ`) belirle.
3. **Kapsamını (`checked`) açıkça bildir.** Kural yalnızca gerçekten baktığı sku/kanal çiftlerini
   saymalı; hiç bakmadığı veri için "temiz" sayılmamalı.
4. Varsayılan eşiği `Thresholds` modeline ekle; eşikler tek yerden yönetilir ve `scan` çağrısına
   parametre olarak geçirilir.
5. Test yaz: sınır durumları (eşikte/−1/+1), eksik veri (alarm üretmemeli), determinizm
   (aynı girdi iki kez → aynı çıktı) ve durum makinesi geçişleri.
6. Dokümantasyonu güncelle: `docs/rules.md` kod tablosu ve örnek mesaj, gerekirse
   `docs/architecture.md` ve `docs/roadmap.md`.
7. Yeni kural `--json` çıktısına `code` alanıyla düşer; JSON şemasını bozmayın.

## Yanlış alarm bildirimi ve kapsam bildirimi zorunluluğu

- Bir **yanlış alarm** veya kaçırılan tutarsızlık bildirirken lütfen **fixture'ı** paylaşın (mümkünse
  küçülterek): kural, veriye bakan bir fonksiyondur ve örnek olmadan düzeltilemez.
- Her yeni kural veya davranış değişikliği, o kuralın **neyi kapsamadığını** da yazmalıdır
  (`docs/rules.md` içindeki "kapsam dışı" notu). "Şunu da yakalar" cümlesi kadar "şunu yakalamaz"
  cümlesi de zorunludur — sessiz sınır, en tehlikeli sınırdır.

## Kalite kapıları

```bash
uv run ruff check . && uv run ruff format --check .
uv run mypy                              # strict
uv run pytest --cov=sentinel --cov-report=term-missing --cov-fail-under=85
uv run sentinel scan --fixtures examples/data --json   # demo hâlâ geçerli JSON üretiyor mu?
```

## Commit ve PR

- Conventional Commits: `feat(rules): ...`, `fix(state): ...`, `docs: ...`, `test: ...`.
- PR açıklamasında: ne değişti, neden, hangi kural/senaryo etkilendi, determinizm korundu mu.
- Yeni bir pazaryeri profili eklediyseniz `examples/data/profiles/` altına örnek dosya koyun.
