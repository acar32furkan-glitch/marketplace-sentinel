# Güvenlik Politikası

## Desteklenen sürümler

| Sürüm | Destek |
|-------|--------|
| 0.1.x | ✅ |
| < 0.1 | ❌ (geliştirme sürümleri) |

## Bir açığı nasıl bildirirsiniz?

Güvenlikle ilgili konuları herkese açık issue olarak **açmayın**. GitHub üzerinden özel güvenlik
bildirimi gönderin: depoda **Security → Report a vulnerability**. Bildirimde şunları paylaşın:

- etkilenen sürüm ve işletim sistemi,
- en küçük yeniden üretim adımları (girdi dosyaları: profil, fixture, durum dosyası),
- beklenen ve gözlenen davranış,
- varsa istismar senaryosu.

İlk yanıt hedefi: 7 iş günü. Düzeltme yayınlandığında bildirimi yapan kişi (isterseniz) sürüm
notlarında anılır.

## Tehdit modeli

`marketplace-sentinel` **çevrimdışı bir CLI/kütüphanedir**: ölçüm katmanı ağa çıkmaz, hesap açmaz,
kimlik bilgisi istemez ve pazaryerine **yazmaz**. Yalnızca okur ve raporlar.

Bu proje açısından anlamlı riskler:

| Risk | Değerlendirme |
|------|---------------|
| Doğruluk riski | Kurallar alarm üretir; hatalı bir kural **yanlış alarm** ya da **kaçırmadır**. Kaçırılan tutarsızlık ticari kayıptır; yanlış alarm ise operatörü alarma alıştırır. Her ikisi de issue olarak bildirilmeye değer. |
| Gizli bilgiler | Kimlik bilgileri **yalnızca ortam değişkenlerinden** okunur; hangi değişken olduğu profilde (`username_env`, `password_env`, `token_env`) tanımlanır, değerin kendisi kodda/profilde/durum dosyasında tutulmaz. `.env*` dosyaları `.gitignore` ile dışlanır; `--fixtures` modunda kimlik bilgisi hiç okunmaz, HTTP kanalı değeri hata mesajına ve loga yazmaz. |
| Girdi dosyaları | Profil (YAML), fixture (JSON) ve durum dosyası kullanıcı girdisidir. YAML `yaml.safe_load` ile yüklenir; `eval`/`exec` yolu ve şablon yürütme yoktur. |
| Yazma yok | Nöbetçi hiçbir koşuda pazaryerine geri yazmaz ve panel oturumu açmaz; uzaktan gelen bir yanıt kod yürütme yoluna girmez. |
| Kaynak tüketimi | Büyük fixture'lar için işlem doğrusaldır (sku × kanal); bilinen üstel desen yoktur. `--max-alerts` çıktı hacmini sınırlar. |
| Durum dosyası bütünlüğü | Bozuk durum dosyası girdi hatası (çıkış kodu `2`) verir; nöbetçi dosyayı tahminle onarmaya çalışmaz ve sessizce sıfırlamaz. |

## Kapsam dışı

- Kullanıcının verdiği fixture verisinin içeriğinin doğruluğu (bu bir veri sorunudur, güvenlik değil).
- Pazaryeri API'lerinin kendi güvenliği ve kimlik doğrulaması.
- Ağ üzerinden veri toplayan harici istemciler (bu depo değil, onları çağıran kurulum).
