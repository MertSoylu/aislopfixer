# Etki kalibrasyonu

Bu tablo `python -m bench.impact` çıktısıdır. İki ayrı sayı doğrulanıyor, çünkü iki ayrı soruya cevap veriyorlar.

**1. Dönüşümün kendi tahmini** — `a`'ya basıldığında skorun ne olacağı. Bu bir model değil: plan kurulur, düzenlemeler **bellekte** uygulanır ve sonuç aynı ölçümden geçer (`transform.preview`). Gerçek çalıştırmayla birebir tutmak zorunda.

**17/17 vakada tahmin ile gerçekleşen arasındaki fark 0.1 puanın altında.**

| vaka | önce | tahmin | gerçekleşen | fark |
|---|---:|---:|---:|---:|
| `slop_saas` | 88.6 | 23.9 | 23.9 | 0.0 |
| `slop_tr` | 88.0 | 18.8 | 18.8 | 0.0 |
| `slop_react` | 87.6 | 40.0 | 40.0 | 0.0 |
| `slop_vue` | 87.6 | 40.0 | 40.0 | 0.0 |
| `slop_styled` | 87.1 | 87.1 | 87.1 | 0.0 |
| `slop_kit` | 75.9 | 36.5 | 36.5 | 0.0 |
| `clean_studio_large` | 12.4 | 11.5 | 11.5 | 0.0 |
| `crafted_kit` | 33.0 | 11.1 | 11.1 | 0.0 |
| `clean_svelte` | 6.8 | 6.4 | 6.4 | 0.0 |
| `mid_human_tailwind` | 46.9 | 18.6 | 18.6 | 0.0 |
| `clean_studio` | 8.9 | 8.5 | 8.5 | 0.0 |
| `clean_config` | 15.2 | 13.6 | 13.6 | 0.0 |
| `clean_utility` | 18.0 | 21.3 | 21.3 | 0.0 |
| `clean_css` | 20.9 | 22.1 | 22.1 | 0.0 |
| `clean_modules` | 6.0 | 6.0 | 6.0 | 0.0 |
| `half_dark_kit` | 77.2 | 15.8 | 15.8 | 0.0 |
| `clean_dark_kit` | 76.7 | 15.5 | 15.5 | 0.0 |

**2. Sıralama modeli** — “önce ne” listesindeki tek tek düşüşler (`analyze.projected_score`). Bu farklı bir soru: bir **insan** o gözlemi kapatırsa ne olur. Modelin varsayımı `DESIGNED_AT` (60), yani bir eksenin tasarlandığında ulaştığı yer. Aracın kendi dönüşümü bunun ötesine geçer — bütün ekseni proje token'larına bağlar — dolayısıyla model dönüşümü izlemez, izlememeli.

| vaka | sıralama modeli | dönüşümün gerçeği | fark |
|---|---:|---:|---:|
| `slop_saas` | −35.8 | −64.7 | 28.9 |
| `slop_tr` | −39.7 | −69.2 | 29.5 |
| `slop_react` | −34.7 | −47.6 | 12.9 |
| `slop_vue` | −34.7 | −47.6 | 12.9 |
| `slop_styled` | −0.0 | −0.0 | 0.0 |
| `slop_kit` | −24.5 | −39.4 | 14.9 |
| `clean_studio_large` | −1.3 | −0.9 | 0.4 |
| `crafted_kit` | −12.3 | −21.9 | 9.6 |
| `clean_svelte` | −0.0 | −0.4 | 0.4 |
| `mid_human_tailwind` | −17.8 | −28.3 | 10.5 |
| `clean_studio` | −0.0 | −0.4 | 0.4 |
| `clean_config` | −0.0 | −1.6 | 1.6 |
| `clean_utility` | −4.0 | −-3.3 | 7.3 |
| `clean_css` | −4.2 | −-1.2 | 5.4 |
| `clean_modules` | −0.0 | −0.0 | 0.0 |
| `half_dark_kit` | −34.7 | −61.4 | 26.7 |
| `clean_dark_kit` | −36.5 | −61.2 | 24.7 |

Sapma tek yönlü ve bilerek: listedeki düşüş bir **alt sınırdır**. Sıralama için doğru sayıdır, seviye için değil — ve seviyeyi öğrenmek isteyen zaten yukarıdaki tahmini görüyor.

## Dönüşümün yardım etmediği vakalar

Bunlar da tabloda duruyor. Zaten tasarlanmış bir projede dönüşüm skoru **yükseltebilir**: araç kendi sistemini kurar, o sistem de projenin kendi sisteminden daha dar olabilir. Tahmin ekranda göründüğü için kullanıcı bunu uygulamadan önce görür.

- **slop_styled** — 87.1 → 87.1
- **clean_utility** — 18.0 → 21.3
- **clean_css** — 20.9 → 22.1
- **clean_modules** — 6.0 → 6.0

## Kapatılan işler

- **slop_saas** — type.untuned_display, space.single_container, space.uniform_rhythm, color.default_accent, color.stock_palette, shape.no_decisions, layout.center_monoculture, layout.symmetric_grids, material.mono_shadow, material.uniform_card, layout.no_break
- **slop_tr** — space.single_container, space.uniform_rhythm, shape.mono_radius, color.default_accent, color.stock_palette, type.untuned_display, layout.center_monoculture, layout.symmetric_grids, material.mono_shadow, material.uniform_card, layout.no_break
- **slop_react** — type.untuned_display, color.default_accent, color.stock_palette, space.single_container, space.uniform_rhythm, material.no_decisions, shape.no_decisions, layout.center_monoculture, layout.symmetric_grids, layout.no_break
- **slop_vue** — type.untuned_display, color.default_accent, color.stock_palette, space.single_container, space.uniform_rhythm, material.no_decisions, shape.no_decisions, layout.center_monoculture, layout.symmetric_grids, layout.no_break
- **slop_styled** — yok
- **slop_kit** — shape.mono_radius, space.single_container, space.uniform_rhythm, material.no_decisions, layout.center_monoculture, layout.symmetric_grids, type.untuned_display, layout.no_break
- **clean_studio_large** — space.single_container
- **crafted_kit** — color.default_accent, color.stock_palette, shape.no_decisions, space.single_container
- **clean_svelte** — yok
- **mid_human_tailwind** — color.stock_palette, type.no_decisions, shape.no_decisions
- **clean_studio** — yok
- **clean_config** — yok
- **clean_utility** — shape.no_decisions, space.single_container
- **clean_css** — shape.no_decisions, space.single_container
- **clean_modules** — yok
- **half_dark_kit** — layout.no_break, space.single_container, color.default_accent, color.stock_palette, shape.no_decisions
- **clean_dark_kit** — layout.no_break, space.single_container, color.default_accent, color.stock_palette, shape.no_decisions

Aracın kendi kapattığı gözlemler (`analyze.SELF_FIXABLE`): `color.default_accent`, `color.no_decisions`, `color.stock_palette`, `layout.center_monoculture`, `layout.no_break`, `layout.no_decisions`, `layout.symmetric_grids`, `material.mono_shadow`, `material.no_decisions`, `material.uniform_card`, `shape.mono_radius`, `shape.no_decisions`, `space.no_decisions`, `space.single_container`, `space.uniform_rhythm`, `type.no_decisions`, `type.untuned_display`.

`slop_styled` listede ama kapattığı iş yok: bütün stiller CSS-in-JS'te ve ortada yeniden yazılacak bir `class` özniteliği yok. Rapor o projede ⚡ işareti koymaz, tahmin de skorun değişmeyeceğini söyler.
