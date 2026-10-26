# Koşu Senaryoları

Nöbetçinin **gerçek koşularda** nasıl davrandığı: ilk koşu, sonraki koşu, kısmi kanal hatası ve bozuk
durum dosyası. Her senaryoda komut ve o komutun **gerçekten ürettiği çıktı** vardır; çıktılar
uydurulmamıştır. Kuralların kendisi [rules.md](rules.md), durum makinesi
[ADR-0002](adr/0002-alert-state-and-dedup.md) içinde.

## Çalışma düzeni

Senaryolar depodaki örnek verinin **tek kullanımlık kopyası** üzerinde koşulur; `examples/data/state.json`
böylece bozulmaz ve bu dokümandaki çıktılar tekrar üretilebilir kalır (`--no-state-write` bu yüzden
demoda kullanılır).

```bash
uv sync --all-extras --dev           # bir kez

# Linux/macOS ve MSYS dışı kabuklar:
export KOSU="$(mktemp -d)/kosu"
# Windows (git-bash): native Python MSYS `/tmp/...` yolunu çözemez — Windows yolu kullanın:
# export KOSU="$LOCALAPPDATA/Temp/kosu"
mkdir -p "$KOSU"
```

> **Tuzak:** git-bash'te `mktemp -d` `/tmp/tmp.XXXX` (MSYS) yolu verir; o yol `uv run` ile çalışan
> Windows Python'una geçtiğinde `girdi hatası: profil klasörü bulunamadı: \tmp\...` çıkar. Windows'ta
> çalışma klasörünü Windows biçiminde (`$LOCALAPPDATA/Temp/kosu`) verin.

Aşağıdaki çıktılarda yalnızca bu klasörün yolu `$KOSU` ile kısaltılmıştır; satırlar komut çıktısından
birebir alınmıştır. Tüm koşular sabit referans anıyla (`06.10.2026 09:00`, `DEMO_NOW`) çalışır, yani
aynı kopya + aynı komut her zaman aynı çıktıyı verir.

| # | Senaryo | Ne kanıtlanır |
|---|---------|----------------|
| 1 | İlk koşu (durum dosyası yok) | Tüm alarmlar **YENİ**; kritik varsa çıkış kodu `1` |
| 2 | Sonraki koşu | **DEVAM EDEN** alarm tekrar bağırılmaz; düzeltilen alarm **ÇÖZÜLDÜ** olur |
| 3 | Kısmi kanal hatası | Hatalı kanal taramayı düşürmez; alarmlar kapanır — bunu `errors` alanından ayırt edersiniz |
| 4 | Bozuk durum dosyası | Çıkış kodu `2`; nöbetçi dosyayı tahminle onarmaz |

---

## 1. İlk koşu — durum dosyası yok (soğuk başlangıç)

```bash
cp -r examples/data "$KOSU/s1" && rm "$KOSU/s1/state.json"
uv run sentinel scan --fixtures "$KOSU/s1"
```

```text
KANAL ÇAKIŞMASI NÖBETÇİSİ — 06.10.2026 09:00
  kanal: kanal_a, kanal_b  ·  listelenen ürün: 14
  YENİ 6  ·  DEVAM EDEN 0  ·  ÇÖZÜLDÜ 0  ·  KRİTİK 1  ·  UYARI 4
------------------------------------------------------------------------

YENİ (6)
  1. [KRİTİK] [STOK_CAKISMASI] sku-102 bir kanalda tükendi, diğerinde satışta (stok farkı 24)
     kanal  : kanal_a, kanal_b
     durum  : kanal_a 0, kanal_b 24
     aksiyon: Stok senkronizasyonunu hemen düzeltin: tükenmiş kanaldan sipariş gelirse iptal ve ceza riski doğar.
  … (uyarı 2–6, kısaltıldı: FIYAT_SAPMASI:sku-103 · LISTE_YOK:sku-104 · LISTE_YOK:sku-108 ·
     VERI_BAYAT:sku-105 · VERI_BAYAT:sku-106)
KARAR: KALDI ✘ — 1 yeni kritik uyarı var (kod: STOK_CAKISMASI)
```

Çıkış kodu **1**: `--fail-on` varsayılanı `new-critical` ve ilk koşuda kritik alarm "yeni"dir. Durum
dosyası yazıldığı için (komut `--state` almıyor, `<fixtures>/state.json` varsayılanı kullanılıyor):

```bash
uv run sentinel state show --state "$KOSU/s1/state.json"
```

```text
DURUM DOSYASI — $KOSU/s1/state.json
  kayıtlı imza: 6
  FIYAT_SAPMASI:sku-103           ilk görülme: 2026-10-06T09:00:00+03:00
  LISTE_YOK:sku-104               ilk görülme: 2026-10-06T09:00:00+03:00
  LISTE_YOK:sku-108               ilk görülme: 2026-10-06T09:00:00+03:00
  STOK_CAKISMASI:sku-102          ilk görülme: 2026-10-06T09:00:00+03:00
  VERI_BAYAT:sku-105              ilk görülme: 2026-10-06T09:00:00+03:00
  VERI_BAYAT:sku-106              ilk görülme: 2026-10-06T09:00:00+03:00
```

**Dikkat:** durum dosyası yoksa bu bir hata değildir — dosya yokluğu "ilk koşu" sayılır ve tüm alarmlar
YENİ olur. Bu yüzden durum dosyasını **kaybetmek** her alarmı yeniden "yeni" yapar; CI'da
`new-critical` politikası kırmızıya döner (alarm değişmediği hâlde). Durum dosyasını yedekleyin.

## 2. Sonraki koşu — dedupe ve çözülme

Aynı kopya üzerinde ikinci kez koşulduğunda:

```bash
uv run sentinel scan --fixtures "$KOSU/s1"
```

```text
KANAL ÇAKIŞMASI NÖBETÇİSİ — 06.10.2026 09:00
  kanal: kanal_a, kanal_b  ·  listelenen ürün: 14
  YENİ 0  ·  DEVAM EDEN 6  ·  ÇÖZÜLDÜ 0  ·  KRİTİK 1  ·  UYARI 4
…
DEVAM EDEN (6)
  1. [KRİTİK] [STOK_CAKISMASI] sku-102 bir kanalda tükendi, diğerinde satışta (stok farkı 24)
…
```

Çıkış kodu **0**: kritik alarm hâlâ açık ama **yeni değil**, dolayısıyla `new-critical` politikası
karşılanır. Bu bilinçli bir karardır — bilinen borç CI'ı kırmaz, yeni kritik alarm kırar.

Şimdi operatörün fiyatı düzelttiği durumu simüle edelim: `kanal_a`'da `sku-103` 100.00 → 118.00
(`kanal_b` ile eşitlenir).

```bash
cp -r examples/data "$KOSU/s2" && rm "$KOSU/s2/state.json"
uv run sentinel scan --fixtures "$KOSU/s2"          # 1. tur: FIYAT_SAPMASI:sku-103 YENİ
uv run python - "$KOSU/s2/kanal_a.json" <<'PY'
import json, pathlib, sys
path = pathlib.Path(sys.argv[1])
data = json.loads(path.read_text(encoding="utf-8"))
for row in data["listings"]:
    if row["urun_kodu"] == "sku-103":
        row["satis_fiyati"] = "118.00"                       # kanal_b ile eşitlendi
        row["guncelleme_zamani"] = "2026-10-06T08:50:00+03:00"
path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
PY
uv run sentinel scan --fixtures "$KOSU/s2"          # 2. tur: aynı alarm artık yok
```

```text
KANAL ÇAKIŞMASI NÖBETÇİSİ — 06.10.2026 09:00
  kanal: kanal_a, kanal_b  ·  listelenen ürün: 14
  YENİ 0  ·  DEVAM EDEN 5  ·  ÇÖZÜLDÜ 1  ·  KRİTİK 1  ·  UYARI 3
------------------------------------------------------------------------

DEVAM EDEN (5)
  1. [KRİTİK] [STOK_CAKISMASI] sku-102 bir kanalda tükendi, diğerinde satışta (stok farkı 24)
  … (uyarı 2–5: LISTE_YOK:sku-104 · LISTE_YOK:sku-108 · VERI_BAYAT:sku-105 · VERI_BAYAT:sku-106)

ÇÖZÜLDÜ (1)
  1. [BİLGİ] [FIYAT_SAPMASI] sku-103 uyarısı bu turda kayboldu (çözüldü)
     kanal  : —
     durum  : önceki turda bildirilen durum artık geçerli değil
     aksiyon: Ek aksiyon gerekmez; kaydı arşivleyebilirsiniz.
```

Özet satırındaki `ÇÖZÜLDÜ 1` ile `ÇÖZÜLDÜ (1)` bloğu tek bir olayı anlatır: alarm bir önceki turda
açıktı, bu turda yok. Aynı sorun sonra tekrar çıkarsa yeniden **YENİ** sayılır.

## 3. Kısmi kanal hatası — tarama düşmez

`kanal_b.json` bozulur (örnekte süslü parantez kapanmadan bırakılmıştır):

```bash
cp -r examples/data "$KOSU/s3" && rm "$KOSU/s3/state.json"
uv run sentinel scan --fixtures "$KOSU/s3"                                   # temiz tur
echo '{"marketplace": "kanal_b", "listings": [}' > "$KOSU/s3/kanal_b.json"
uv run sentinel scan --fixtures "$KOSU/s3" --json
```

```json
{
  "listings": 7,
  "passed": true,
  "counts": { "new": 0, "ongoing": 2, "resolved": 4 },
  "codes": { "VERI_BAYAT": 2 },
  "errors": [
    "kanal_b: kanal_b.json JSON olarak çözülemedi: Expecting value"
  ],
  "new": []
}
```

Bu blok kısaltılmıştır (boşluk için `ongoing`/`resolved`/`alerts` dizilerinin gövdeleri çıkarıldı);
sayılar, `errors` alanı ve `new` alanı komut çıktısından birebir alınmıştır.

Ne oldu:

- **Tarama düşmedi.** `kanal_a` okundu (7 ürün), hatalı kanal kural motorundan çıkarıldı. Hata
  `errors` alanında ve konsolda `not: kanal_b: …` satırında görünür.
- **Eksik veri "liste yok"a dönüşmedi.** `kanal_b` için yanlış bir `LISTE_YOK` alarmı üretilmedi;
  bu davranış [rules.md](rules.md) içinde "bilinmiyor ≠ temiz" olarak tanımlıdır.
- **Ama dört alarm ÇÖZÜLDÜ olarak kapandı** (`STOK_CAKISMASI:sku-102`, `FIYAT_SAPMASI:sku-103`,
  `LISTE_YOK:sku-104`, `LISTE_YOK:sku-108`). Bunların hepsi karşılaştırmalı kurallardır ve girdisi
  `kanal_b`'dir; kanal verisi gelmeyince koşul oluşmaz ve imza bir sonraki durum dosyasına yazılmaz.

> **Kritik uyarı:** kanal erişimi geçici olarak kaybolduğunda nöbetçi bunu "sorun çözüldü" gibi
> gösterebilir ve **çıkış kodu `0`** olur (`passed: true`). "Çözüldü" satırını görünce nedenini
> `errors`/`not:` satırından doğrulayın: kanal hatası varsa o alarmlar operatör tarafından
> **kapanmamıştır**, sadece görünmez olmuştur. Kanal geri geldiğinde aynı alarmlar bir kez daha
> **YENİ** olarak bildirilir (yeni kritikse politika yine kırmızıya döner).

Kanal dosyası tamamen yokken de aynı yol izlenir; fark, hata mesajıdır:

```text
  kanal: kanal_a, kanal_b  ·  listelenen ürün: 7
  YENİ 0  ·  DEVAM EDEN 2  ·  ÇÖZÜLDÜ 0  ·  KRİTİK 0  ·  UYARI 1
------------------------------------------------------------------------
not: kanal_b: örnek dosya bulunamadı: $KOSU/s3/kanal_b.json
```

## 4. Bozuk durum dosyası — girdi hatası, tahmin yok

Nöbetçi durum dosyasını **onarmaya çalışmaz**. Şekli bozuksa anlaşılır bir girdi hatası verir ve
hiçbir alarm üretmez (aksi hâlde tüm alarmlar sahte biçimde "yeni" ya da sahte biçimde "sessiz"
olurdu). Beş bozukluk örneği:

| Durum dosyası içeriği | Çıktı (stderr) | Çıkış |
|---|---|---|
| `{"alerts": {"LISTE_YOK:sku-104"` (yarım JSON) | `girdi hatası: durum dosyası geçerli JSON değil: $KOSU/s4/state.json (satır 1, sütun 32: Expecting ':' delimiter)` | `2` |
| `{"alerts": []}` (`alerts` nesne değil) | `girdi hatası: durum dosyasında 'alerts' nesnesi yok: $KOSU/s4/state.json` | `2` |
| `["LISTE_YOK:sku-104"]` (kök dizi) | `girdi hatası: durum dosyası bir nesne olmalı: $KOSU/s4/state.json` | `2` |
| `{"version": 1, "generated_at": "…"}` (`alerts` alanı yok) | `girdi hatası: durum dosyasında 'alerts' alanı yok: $KOSU/s4/state.json` | `2` |
| `{"alerts": {"FIYAT_SAPMASI:sku-103": {"first_seen": "bozuk-tarih"}}}` | `uyarı: durum dosyasında 'FIYAT_SAPMASI:sku-103' kaydının 'first_seen' değeri ISO zaman damgası değil ('bozuk-tarih'); ilk görülme bu turun anı sayılacak: $KOSU/s4/state.json` — alarm **DEVAM EDEN** sayılır | `1` |

İlk dört satırda koşu **hiç başlamaz**: hata cümlesi Türkçedir ve dosya yolunu taşır; JSON çözücünün
İngilizce ayrıntısı yalnızca parantez içinde ek bilgi olarak kalır. Son satır bilinçli bir ayrımdır:
bozuk bir `first_seen` kaydın varlığını ortadan kaldırmaz, bu yüzden alarm "YENİ" diye yeniden
bağırılmaz — kayıt korunur ve kullanıcı stderr'de tek satır uyarı görür (ayrıntılı tablo:
[rules.md § Durum dosyası doğrulaması](rules.md#durum-dosyası-doğrulaması)).

`state show` alt komutu dosya yoksa da girdi hatası verir (çıktı: `girdi hatası: durum dosyası
bulunamadı: $KOSU/s4/yok.json`, kod `2`) — yani "kayıt yok" ile "dosya yok" karıştırılmaz.

### Elle onarım

Durum dosyası insan tarafından okunabilir JSON'dur; bozuksa en güvenli onarım **boş bir durum
dosyasıyla başlamaktır** (eski alarmlar kaybolur, hepsi bir kez daha YENİ bildirilir):

```bash
echo '{"alerts": {}}' > "$KOSU/s4/state.json"
uv run sentinel scan --fixtures "$KOSU/s4"
```

```text
  YENİ 6  ·  DEVAM EDEN 0  ·  ÇÖZÜLDÜ 0  ·  KRİTİK 1  ·  UYARI 4
KARAR: KALDI ✘ — 1 yeni kritik uyarı var (kod: STOK_CAKISMASI)
```

Bozuk dosyayı elle tamir etmeye çalışmak yerine arşivleyip sıfırdan başlamak daha az sürprizlidir:
onarılmış bir dosyada yanlış `first_seen` değerleri kalırsa "ne zamandır açık?" sorusu yanlış cevap verir.

---

## `--no-state-write` ne zaman kullanılır

`sentinel scan --no-state-write` durum dosyasını **okur ama yazmaz**. Örnek kopyada dosya koşudan sonra
bit bit aynı kalır (`sha256` öncesi ve sonrası `3dd70032…7a637f`):

```bash
cp -r examples/data "$KOSU/s5"          # durum dosyası da kopyalanır, silinmez
sha256sum "$KOSU/s5/state.json"
uv run sentinel scan --fixtures "$KOSU/s5" --no-state-write
sha256sum "$KOSU/s5/state.json"        # aynı karma
```

```text
  kanal: kanal_a, kanal_b  ·  listelenen ürün: 14
  YENİ 5  ·  DEVAM EDEN 1  ·  ÇÖZÜLDÜ 1  ·  KRİTİK 1  ·  UYARI 4
…
DEVAM EDEN (1)
  1. [UYARI] [LISTE_YOK] sku-104 kanal_b kanalında hiç listelenmiyor
…
ÇÖZÜLDÜ (1)
  1. [BİLGİ] [FIYAT_SAPMASI] sku-999 uyarısı bu turda kayboldu (çözüldü)
KARAR: KALDI ✘ — 1 yeni kritik uyarı var (kod: STOK_CAKISMASI)
```

Görüldüğü gibi **her alarm YENİ sayılmaz**: durum dosyası hâlâ okunduğu için içindeki imzalar bu koşuya
da uygulanır. `LISTE_YOK:sku-104` (dosyada var, şimdi de var) **DEVAM EDEN**, dosyada olup bu turda
görülmeyen `FIYAT_SAPMASI:sku-999` ise **ÇÖZÜLDÜ** olur. Yani demoda durum dosyası iki turlu bir
senaryoyu "donmuş" hâlde gösterir; `--no-state-write` tekrar üretilebilirlik sağlar, ama durum dosyası
gerçeklikten kopar:

- **Dosya yok/boşsa** tüm alarmlar YENİ'dir (soğuk başlangıç, Senaryo 1).
- **Dosya varsa** aynı bölünme (YENİ/DEVAM EDEN/ÇÖZÜLDÜ) her koşuda tekrar eder; "çözüldü" satırı
  sonsuza kadar çözülmüş kalır, dosya asla güncellenmez.

Bu yüzden `--no-state-write` üretimde/CI'da kullanılmaz (bilinen bir alarmın "çözüldü" görünmesi ya da
tersi yanıltıcıdır). Doğru kullanım: demo, doküman çıktısı ve depodaki örnek durum dosyasını
korumak. Üretimde durum dosyasını yazın, kalıcı bir yeri (`--state`) olsun ve yedekleyin.

> [ADR-0002](adr/0002-alert-state-and-dedup.md) içindeki "bu durumda tüm alarmlar YENİ sayılır" ifadesi
> yalnızca durum dosyası **okunamadığında** doğrudur; okunabilir bir dosya varken yukarıdaki bölünme
> uygulanır. Aynı ADR'de "bozuk/**eksik** dosya çıkış kodu 2 verir" ifadesi de eksik dosya için
> geçerli değildir: eksik dosya soğuk başlangıçtır (Senaryo 1), hata veren şey **bozuk** dosyadır
> (Senaryo 4). Her iki ifade bu dokümana göre düzeltilmiştir.
