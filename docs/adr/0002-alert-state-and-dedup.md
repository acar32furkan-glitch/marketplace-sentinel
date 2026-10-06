# ADR-0002 — Alarm durumu saklanır, dedupe `kod:sku` imzasıyla yapılır

- **Durum:** Kabul edildi
- **Tarih:** 2026-10-06

## Bağlam: "alarm fırtınası" problemi

Bir nöbetçi, izlediği gerçekliği her koşuda baştan ölçer. Eğer koşu **durumsuz** olsaydı, 6 saatte
bir çalışan bir zamanlanmış görev aynı bozuk fiyatı günde dört kez "yeni" diye bağırırdı. Bir hafta
sonra operatör:

- bildirimleri görmezden gelmeye başlar (alarm yorgunluğu) ve gerçekten **yeni** bir kritik alarmı
  kaçırır;
- "bu sorun ne zaman başladı, ne zamandır açık?" sorusunu cevaplayamaz;
- "düzelttim" ile "hâlâ bozuk" arasındaki farkı göremez.

Klasik çözümler (önem eşiğini yükseltmek, bildirim sayısını kırpmak) sorunu görmezden gelir; asıl
eksik olan **hafızadır**.

## Karar

Her alarm deterministik bir **imza** ile kimliklenir:

```text
signature = "<kural_kodu>:<sku>"        örnek: "STOK_CAKISMASI:TRN-1001"
```

Önceki koşunun alarmları `state.json` içinde tutulur ve `state.classify()` her alarmı üç durumdan
birine yerleştirir:

| Önceki | Şimdi | Durum |
|--------|-------|-------|
| yok | var | **YENİ** — bildirilir, politikayı tetikler |
| var | var | **DEVAM EDEN** — özetlenir, tekrar bağırılmaz |
| var | yok | **ÇÖZÜLDÜ** — kapanış notu |
| yok | yok | (alarm yok) |

Durum dosyası insan tarafından okunabilir JSON'dur ve girdi/çıktı olarak açıkça yönetilir:

```json
{
  "version": 1,
  "generated_at": "2026-10-06T09:00:00+03:00",
  "alerts": {
    "STOK_CAKISMASI:sku-102": {
      "first_seen": "2026-10-05T09:00:00+03:00",
      "last_seen": "2026-10-06T09:00:00+03:00"
    }
  }
}
```

Dosya, her imzayı ilk görülme anına eşler; kaydın önem/kod/sku bilgisi imzanın kendisinden çözülür,
böylece durum dosyası küçük ve okunur kalır.

- **İmza neden `kod:sku`?** Ölçülen şey ürünün kendisidir. Fiyat 749.90'dan 760.00'a çıksa da sorun
  "aynı sku'nun fiyat tutarsızlığı"dır; imza metne değil kimliğe bakar, bu yüzden küçük sayı
  oynamaları alarmı "yeni" yapmaz.
- **Determinizm:** sınıflama yalnızca girdi ve önceki duruma bağlıdır; saat dışarıdan verilir
  (`--now`), rastgelelik ve ağ yoktur. Aynı `(alarm seti, durum)` her zaman aynı YENİ/DEVAM
  EDEN/ÇÖZÜLDÜ ayrımını üretir; bu `tests/` içinde sabitlenmiştir.
- **`--no-state-write`:** durum yazmadan çalıştırma (CI'da bir seferlik doğrulama için). Bu durumda
  tüm alarmlar YENİ sayılır; bu bilinçli bir uyarıdır, sessiz bir sürpriz değil.

## Sonuçlar

- **Kazanç:** bildirim **yeni** ve **kritik** olana odaklanır; aynı sorun bir kez bağırılır, çözülünce
  kapanır. Operatör alarmı ciddiye alır. `--fail-on new-critical` politikası da bu sayede anlamlıdır:
  bilinen borç CI'yı kırmaz, yeni kritik alarm kırar.
- **Bedel:** durum dosyası yönetilmesi gereken bir yan varlıktır. Bozuk/eksik dosya girdi hatası
  (çıkış kodu `2`) verir — nöbetçi dosyayı tahminle onarmaz ve sessizce sıfırlamaz, çünkü bu tüm
  alarmları sahte biçimde "yeni" ya da sahte biçimde "sessiz" yapardı.
- **Kural:** imza biçimi genişletilebilir (`kod:sku` + isteğe bağlı kanal ayrımı) ama değiştirilmesi
  durum dosyası sürümünü (`version`) yükseltmeyi gerektirir; eski sürüm durum dosyası reddedilir ya da
  açık bir geçişle okunur.
- **Kapsam dışı:** durum saklama bir **dedupe** çözümüdür, uzun dönemli bir tarihçe değildir. Fiyat
  geçmişi ve trend analizi ayrı bir özelliktir (bkz. [yol haritası](../roadmap.md), v0.3).
