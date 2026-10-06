# Kural Sözlüğü

Nöbetçi dört kuralı çalıştırır. Her kural **kendi kapsamını** (`checked`) bildirir: yalnızca
gerçekten baktığı sku/kanal çiftleri sayılır; eksik veri "temiz" sayılmaz, "bilinmiyor"dur ve alarm
üretmez.

Önem seviyesi üçtür: **KRİTİK**, **UYARI**, **BİLGİ**. Durum seviyesi de üçtür: **YENİ**,
**DEVAM EDEN**, **ÇÖZÜLDÜ** (bkz. [ADR-0002](adr/0002-alert-state-and-dedup.md)).

## 1. Stok çakışması (`STOK_CAKISMASI`)

| Alan | Değer |
|------|-------|
| Koşul | Aynı `sku` için kanallar arasındaki maksimum ve minimum stok farkı eşiği aşıyor |
| Önem | UYARI (varsayılan); bir kanalda stok 0, diğerinde ≥10 ise **KRİTİK** |
| Varsayılan eşik | fark > **5 adet** |
| Örnek mesaj | `sku-102 · STOK_CAKISMASI [KRİTİK]: sku-102 bir kanalda tükendi, diğerinde satışta (stok farkı 24)` |

- Kapsam: en az **iki kanalda** gözlemi olan sku'lar. Tek kanalda listelenen sku bu kurala girmez
  (o durum `LISTE_YOK` sorusudur).
- Stok "bilinmiyor" (`null`) bir gözlem fark hesabına katılmaz; bilinmeyen veri yanlış alarm üretmez.
- **Neden KRİTİK eşiği 0/≥10?** Çakışma "küçük senkron gecikmesi" olabilir; ama bir kanal satışı
  kapatmışken diğeri satmaya devam ediyorsa sipariş iptali ve ceza riski vardır — bu artık gecikme
  değil, müşteriye yanlış bilgidir.

## 2. Fiyat sapması (`FIYAT_SAPMASI`)

| Alan | Değer |
|------|-------|
| Koşul | Aynı `sku` için kanallar arasındaki maksimum ve minimum fiyat farkı eşiği aşıyor |
| Önem | UYARI (varsayılan); fiyat **iki katına** çıktıysa (fark ≥ **%100**) KRİTİK |
| Varsayılan eşik | fark > **%5** (referans: kanallardaki en düşük fiyat) |
| Örnek mesaj | `sku-103 · FIYAT_SAPMASI [UYARI]: sku-103 fiyatı kanal_a 100.00 ile kanal_b 118.00 arasında %18.0 farklı` |

- Fark, en düşük gözlenen fiyata göre oransal hesaplanır: `(max − min) / min`; yani "ucuz kanala
  göre pahalı kanal ne kadar yukarıda" sorusunun cevabıdır.
- **Para birimi ayrımı yoktur:** karşılaştırma tüm kanalların aynı para biriminde listelendiğini
  varsayar (çoklu para birimi normalizasyonu yol haritasında kapsam dışıdır).
- **Neden %5?** Kanal komisyonu ve kupon kaynaklı küçük farklar normaldir; %5'in üzeri genelde bir
  kanalda güncellemenin kaçtığını gösterir. Fiyatın iki katına çıktığı (≥%100) durum ise kampanya
  ya da fiyat girişi hatasıdır ve doğrudan kârı etkiler.

## 3. Listeleme yok (`LISTE_YOK`)

| Alan | Değer |
|------|-------|
| Koşul | Bir `sku` en az bir kanalda listeliyken, veri döndüren başka bir kanalda hiç yok |
| Önem | **UYARI** |
| Varsayılan eşik | En az bir kanalda var, diğerinde yok (ek eşik yoktur) |
| Örnek mesaj | `sku-108 · LISTE_YOK [UYARI]: sku-108 kanal_a kanalında hiç listelenmiyor` |

- Kapsam: en az bir kanalda listelenen sku'lar; yalnızca o turda **veri döndüren** kanallara karşı
  denetlenir.
- Bir kanal o koşuda **hiç veri döndürmediyse** bu "listeleme yok" değildir; "kanal verisi yok"
  durumudur ve alarm üretmez — eksik veri yanlış "liste yok" alarmına dönüşmez.
- **Neden UYARI?** Eksik liste doğrudan ciro kaybıdır; ne var ki ürün bir kanalda bilinçli olarak
  kapatılmış da olabilir. Bu yüzden nöbetçi bildirir ve kararı operatöre bırakır.

## 4. Veri bayat (`VERI_BAYAT`)

| Alan | Değer |
|------|-------|
| Koşul | Kanal gözleminin yaşı (`now − observed_at`) eşiği aşıyor |
| Önem | BİLGİ (varsayılan); yaş eşiğin **iki katına** (varsayılan 96 saat) ulaşırsa UYARI |
| Varsayılan eşik | yaş > **48 saat** |
| Örnek mesaj | `sku-105 · VERI_BAYAT [UYARI]: sku-105 verisi 5.0 gün önce güncellenmiş` |

- Kapsam: veri getiren her kanal. Yaş, `now` ile `observed_at` arasındaki farktır; `now` dışarıdan
  verilir, bu yüzden kural deterministiktir.
- **Neden 48 saat?** Sağlıklı bir kanal akışı tipik olarak günlük senkronize olur; 48 saat iki
  senkron turunun kaçması demektir. Bayat veri üzerinde alınan stok/fiyat kararları yanıltıcıdır,
  bu yüzden bayatlama diğer alarmların **güvenilirliğini** de etkiler.

## Durum makinesi

Her alarm `kod:sku` imzasıyla kimliklenir ve önceki durumla karşılaştırılır:

```text
önceki durumda yok  + şimdi var      → YENİ        (bildirilir)
önceki durumda var  + şimdi var      → DEVAM EDEN  (özetlenir, tekrar bağırılmaz)
önceki durumda var  + şimdi yok      → ÇÖZÜLDÜ     (kapanış notu)
önceki durumda yok  + şimdi yok      → (alarm yok)
```

- **YENİ alarm** `--fail-on` politikasını tetikler (varsayılan: yeni bir KRİTİK alarm çıkış kodunu
  `1` yapar).
- **DEVAM EDEN** alarm her koşuda yeniden bildirilmez; sayaç ve ilk görülme zamanı güncellenir.
- **ÇÖZÜLDÜ** alarm bilgisayar tarafında kapanır; istenirse özet sonunda "çözüldü" satırı olarak
  görünür. Aynı sorun sonra tekrar çıkarsa yeniden **YENİ** sayılır.

## Skor ve karar

Bu proje tek bir "kalite skoru" üretmez; kararı **politika** verir:

| Kavram | Kural |
|--------|-------|
| Çıkış kodu 0 | `--fail-on` politikası karşılandı (varsayılan: yeni kritik alarm yok) |
| Çıkış kodu 1 | Politika düştü (`new-critical` / `any-new`) |
| Çıkış kodu 2 | Girdi hatası (bozuk profil, okunamayan fixture, geçersiz durum dosyası) |

Bu bilinçli bir seçimdir: nöbetçi "genel sağlık puanı" değil **ihlal dedektörü**dür. Operatörün
sorusu "durumum 87/100 mü?" değil, "şu an yeni ve kritik bir sorun var mı?" sorusudur.
