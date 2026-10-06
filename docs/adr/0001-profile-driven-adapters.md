# ADR-0001 — Pazaryeri adaptörleri profil-güdümlüdür, kod değil

- **Durum:** Kabul edildi
- **Tarih:** 2026-10-06

## Bağlam

Nöbetçinin değeri, kaç kanalı izlediğiyle doğru orantılıdır. İlk akla gelen tasarım her pazaryeri
için bir sınıf yazmaktır: `TrendyolChannel`, `HepsiburadaChannel`, `AmazonChannel`. Bu yaklaşımın
üç sorunu var:

1. **Kanal eklemek sürüm gerektirir.** Yeni bir pazaryeri için kod, test, PR ve yeni sürüm gerekir;
   operatör kendi kanalını ekleyemez.
2. **Farklar çoğunlukla veri, mantık değil.** Pazaryerleri arasındaki gerçek fark `sku`,
   `sellingPrice`/`price`, `quantity`/`stock` gibi **alan adları**, kimlik doğrulama biçimi ve yanıt
   yapısıdır. Bunlar için farklı kod yolları yazmak kopyala-yapıştır sınıflar üretir.
3. **Kural motoru kanaldan sızar.** Kanal sınıfına gömülen mantık, kural motorunu kanala bağımlı
   hâle getirir ve determinizmi test etmeyi zorlaştırır.

## Karar

Pazaryerleri `examples/data/profiles/*.yaml` (üretimde `profiles/`) altındaki **profil dosyalarıyla**
tanımlanır. Bir profil şunları taşır:

- **`field_map`** — kanalın alan adlarının kanonik listeye eşlenmesi (`sku`, `title`, `price`,
  `stock`, `updated_at`, ...). Veri; kod değil.
- **`auth`** — kimlik doğrulama stili (`none`/`basic`/`bearer`/`header`) ve gereken gizli değerin
  ortam değişkeni adı. `--fixtures` modunda hiç kullanılmaz; gerçek istemcide değerler ortam
  değişkenlerinden okunur.
- **sayfalama ve yol** — `products_path`, `items_path`, `page_param`, `size_param`, `page_size`
  kanalın yanıt biçimini (hangi nokta yolunda liste var, nasıl sayfalanır) tarif eder.

Kod tarafında iki somut adaptör vardır:

- `FixtureChannel(profile, path)` — kaydı bir JSON dosyasından okur (demo, test, çevrimdışı koşu).
- `HttpChannel(profile, env, client)` — aynı profille gerçek bir HTTP API'sinden sayfalayarak okur;
  yalnızca `GET` yapar ve kimlik bilgisi değerini asla loglamaz.

Her ikisi de **aynı profili** tüketir ve aynı kanonik `Listing`'i üretir; kural motoru hangi
adaptörün kullanıldığını **bilmez**. Yeni bir pazaryeri eklemek = yeni bir YAML dosyası.

## Sonuçlar

- **Kazanç:** yeni kanal kod gerektirmez; kural motoru kanal-agnostik ve test edilebilir kalır
  (`tests/` içinde fixture kanalları ile determinizm doğrulanır). Bir kanalın alanları değişirse
  profil düzenlenir, sürüm çıkmaz. Demo, gerçek veriye bağımlı olmadan çalışır.
- **Bedel:** bazı kanalların gerçekte özel mantığı vardır (sayfalama, imzalama, dönüşüm, birleşik
  varyant modelleri); bunlar saf veri eşlemesiyle ifade edilemez. Bu durumda profil bir "kaçış
  kapısı" yerine profilden beslenen küçük bir adaptör genişletmesi gerektirir.
- **Sınır:** auth stilleri veri olarak seçilir ama gizli **değerler** asla profilde tutulmaz; yalnızca
  ortam değişkeninden okunur (bkz. [SECURITY.md](../SECURITY.md)).
- **Kural:** bir kanal için kod yazma dürtüsü doğduğunda önce "bu bir `mapping` satırı mı?" sorusu
  sorulur; veriyle ifade edilebilen hiçbir fark için sınıf yazılmaz.
