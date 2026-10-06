# marketplace-sentinel

[![CI](https://github.com/acar32furkan-glitch/marketplace-sentinel/actions/workflows/ci.yml/badge.svg)](https://github.com/acar32furkan-glitch/marketplace-sentinel/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/python-3.12%20%7C%203.13-blue)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![Ruff](https://img.shields.io/badge/lint-ruff-261230)](https://docs.astral.sh/ruff/)
[![Checked with mypy](https://img.shields.io/badge/mypy-strict-2f6f9f)](https://mypy-lang.org/)

**Türkçe** · [English](README.en.md)

**Aynı ürünü birden fazla pazaryerinde satan mağazalar için deterministik nöbetçi.** Aynı merchant
`sku`'sunun kanallar arasında stok/fiyat tutarsızlığını, bir kanalda hiç listelenmemiş ürünleri ve
bayatlamış verileri yakalar; **yalnızca yeni ve devam eden alarmları** bildirir, çözülenleri sessizce
kapatır.

Kimlik bilgisi yok, ağ yok, 30 saniyede görün:

```bash
git clone https://github.com/acar32furkan-glitch/marketplace-sentinel && cd marketplace-sentinel
uv sync --all-extras --dev
uv run sentinel scan --fixtures examples/data --no-state-write
```

> `--no-state-write` yalnızca demoda kullanılır: depodaki örnek durum dosyası (`examples/data/state.json`)
> bozulmaz, böylece YENİ/DEVAM EDEN/ÇÖZÜLDÜ ayrımı her koşuda aynı çıkar. Gerçek kullanımda durum
> dosyası yazılır.

![marketplace-sentinel demo çıktısı](docs/assets/demo.svg)

---

## Neden?

Aynı ürün beş pazaryerinde satılıyorsa beş ayrı gerçek vardır. Trendyol'da stok 0'a düşer ama
Hepsiburada 12 adet gösterir; bir kanalda fiyat kampanyayla %40 kırpılır, diğerleri eski fiyatta
kalır; yeni açılan bir kanalda ürün hiç listelenmemiştir ve kimse fark etmez. Bu tutarsızlıklar
sayfada "normal" görünür, ilk fark eden müşteri olur — ya da hiç olmaz, sadece satış kaybedersiniz.

marketplace-sentinel bunu **tek komutta, tekrarlanabilir biçimde** görünür kılar:

- **Ağ yok, LLM yok, saat dışarıdan.** Aynı girdi + aynı `--now` her zaman aynı alarmları üretir;
  sonuç CI'da güvenilir (bkz. [ADR-0001](docs/adr/0001-profile-driven-adapters.md)).
- **Alarm fırtınası yok.** Durum dosyası (`state.json`) tutulur; nöbetçi her koşuda aynı sorunu
  tekrar tekrar bağırmaz — yalnızca **YENİ**, **DEVAM EDEN** ve **ÇÖZÜLDÜ** ayrımını bildirir
  (bkz. [ADR-0002](docs/adr/0002-alert-state-and-dedup.md)).
- **Yeni pazaryeri = YAML.** Kanal eklemek kod değiştirmek değil, profil dosyası yazmaktır; aynı
  kural motoru her kanala uygulanır (bkz. [ADR-0001](docs/adr/0001-profile-driven-adapters.md)).

## Dört kural

| Kod | Ne yakalar | Önem | Varsayılan eşik |
|-----|-----------|------|-----------------|
| `STOK_CAKISMASI` | Aynı sku'nun kanallar arası stok farkı | UYARI · bir kanalda 0, diğerinde ≥10 ise KRİTİK | fark > 5 adet |
| `FIYAT_SAPMASI` | Aynı sku'nun kanallar arası fiyat farkı | UYARI · fiyat iki katına çıktıysa (≥%100) KRİTİK | fark > %5 |
| `LISTE_YOK` | Ürün, veri döndüren bir kanalda hiç listelenmemiş | UYARI | en az bir kanalda var, diğerinde yok |
| `VERI_BAYAT` | Kanaldan gelen veri yaşlandı | BİLGİ · ≥96 saatte UYARI | veri yaşı > 48 saat |

Kod listesi, eşikler ve gerekçeler: **[docs/rules.md](docs/rules.md)**

```bash
uv run sentinel profiles --fixtures examples/data          # aktif kanallar ve alan eşlemesi
uv run sentinel scan --fixtures examples/data --json       # ajan/CI için JSON sözleşmesi
uv run sentinel state show --state examples/data/state.json
uv run sentinel watch --fixtures examples/data --interval 900 --iterations 2
```

## Çıkış kodları

| Kod | Anlam |
|-----|-------|
| `0` | Yeni kritik alarm yok (politika karşılandı) |
| `1` | `--fail-on` politikası düştü (varsayılan `new-critical`) |
| `2` | Girdi hatası (bozuk profil, okunamayan fixture, geçersiz durum dosyası) |

`--fail-on` seçenekleri: `none` · `new-critical` (varsayılan) · `any-new`.

## CI'da kullanımı

```yaml
- name: Pazaryeri nöbeti
  run: uv run sentinel scan --fixtures content/data --fail-on new-critical --github-summary
```

`--github-summary` iş özetine (Actions sekmesi) Markdown raporu ekler; politika düşerse komut **1**
koduyla çıkar ve PR'ı kırar. Örnek iş akışı:

```yaml
name: Sentinel
on:
  schedule:
    - cron: "0 */6 * * *"   # 6 saatte bir nöbet
  workflow_dispatch:

jobs:
  nöbet:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v5
        with:
          enable-cache: true
      - run: uv sync --all-extras --dev
      - name: Nöbetçi taraması
        run: >
          uv run sentinel scan --fixtures content/data
          --fail-on new-critical --github-summary
```

## Durum ve dedupe

Nöbetçi her alarm için `kod:sku` biçiminde bir **imza** üretir (örnek: `STOK_CAKISMASI:sku-102`).
Durum dosyası önceki koşunun alarmlarını taşır, böylece:

- **YENİ** — imza ilk kez görülüyor (bildirilir).
- **DEVAM EDEN** — imza zaten açık, hâlâ geçerli (özetlenir, tekrar bağırılmaz).
- **ÇÖZÜLDÜ** — önceki koşuda açıktı, bu koşuda yok (kapanış notu).

Durum dosyası insan tarafından okunabilir JSON'dur; `--no-state-write` ile yazma kapatılır.

## Mimari

```text
examples/data/profiles/*.yaml  ─┐
examples/data/*.json (fixture) ├─→ channels/ ─→ rules.py ─→ scan.py ─→ Alarm├Durum ─→ render/cli
state.json (önceki koşu)       ─┘   (adaptör)    (saf)      (dedupe)
```

- Kural ve ölçüm katmanı **saf fonksiyondur**: IO yok, saat yok, rastgelelik yok.
- Kanal katmanı eklentidir: `profiles/*.yaml` alan eşlemesini ve auth stilini veri olarak taşır.
- `scan.py` ölçümü ağdan **bağımsız** çalıştırır; girdi fixture'dan veya gerçek istemciden gelir,
  kural motoru ikisini ayırt etmez.
- Ayrıntı: [docs/architecture.md](docs/architecture.md) · kararlar: [docs/adr/](docs/adr/)

## Kalite

```bash
uv run ruff check . && uv run ruff format --check .
uv run mypy                              # strict
uv run pytest --cov=sentinel --cov-report=term-missing --cov-fail-under=85
uv run python scripts/verify_examples.py  # örnek veri ↔ profil tutarlılığı
```

**149 test** · **%97,9 kapsam** · `ruff` + `ruff format` + `mypy --strict` temiz · CI: Python 3.12 ve
3.13 matrisi + "nöbetçi demo" işi (JSON sözleşmesi, çıkış kodu ve iş özeti doğrulanır). Kurulan
yorumlayıcı iş içinde doğrulanır; yanlış sürümle koşan matris kırmızıya döner.

## Sınırlar

- **Pazaryerine yazmaz.** Fiyat/stok güncellemez; yalnızca okur ve raporlar (kapsam dışı, bilinçli).
- **Panel kazımaz.** Veri resmî pazaryeri API'sinden ya da kullanıcının verdiği fixture'dan gelir.
- **LLM yok.** Anlam/içerik denetlemez; yalnızca sayısal ve zamansal tutarsızlıkları görür.
- **Kural motoru kanal-agnostiktir:** yeni bir pazaryeri için kod değil, `profiles/` altına bir YAML
  dosyası eklenir.

## Katkı

[CONTRIBUTING.md](CONTRIBUTING.md) · [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md) ·
[SECURITY.md](SECURITY.md) · değişiklikler: [CHANGELOG.md](CHANGELOG.md)

## Lisans

[MIT](LICENSE) © 2026 acar32furkan-glitch
