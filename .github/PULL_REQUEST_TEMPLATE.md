## Ne değişti?

<!-- Kısa özet. Örnek: "STOK_CAKISMASI artık bir kanalda 0 diğerinde ≥10 olan durumu kritik sayıyor" -->

## Neden?

<!-- Hangi tutarsızlık sınıfı yakalanıyor: Closes #12 -->

## Etkilenen kural / profil

- [ ] Yeni veya değişen kural kodunu yazdım (`docs/rules.md` tablosunu güncelledim)
- [ ] Yeni bir pazaryeri profili eklendiyse `examples/data/profiles/` altına örnek koydum
- [ ] `uv run sentinel scan --fixtures examples/data --json` yerelde çalışıyor

## Determinizm kontrol listesi

- [ ] Kural saf fonksiyon (ağ çağrısı yok, rastgelelik yok)
- [ ] Zaman `now` ile enjekte ediliyor (`datetime.now()` çağrılmıyor)
- [ ] Alarm sırası deterministik (`önem, kod, sku`) ve kapsam (`checked`) doğru bildiriliyor
- [ ] Durum makinesi geçişleri (YENİ/DEVAM EDEN/ÇÖZÜLDÜ) testle sabitlendi
- [ ] Yanlış alarm riski test edildi (emin olunmayan veride kural susuyor)

## Kontrol listesi

- [ ] `uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run pytest` geçiyor
- [ ] Dokümantasyon güncellendi (`docs/rules.md`, gerekirse `docs/architecture.md` ve `docs/roadmap.md`)
