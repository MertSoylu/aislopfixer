# Saha kalibrasyonu

Bu tablo `python -m bench.field` çıktısıdır. Korpus kapalı bir devre — 17 vakayı da biz yazdık — bu yüzden yalnızca ölçümün *tutarlı* olduğunu gösterebilir. Aşağıdaki projeleri hiç kimse bu araca göre yazmadı.

Eşik: şablon skoru **50** üstü "üretilmiş", altı "tasarlanmış" sayıldı. 40 elemandan az gören bir tarama hüküm vermiyor: markup'ı bir tema paketinde ya da build çıktısında olan bir depo hakkında konuşacak verisi yok.

Üçüncü bir taraf var: **crafted** — bir tasarım evinin yaptığı, satılan landing şablonu. Bunlar üretilmiş sayfa değil; ayarlanmış bir tip rampası, elle yazılmış easing eğrileri ve kırılan bir yerleşimleri var. Şablon olmalarının sebebi kaynakta değil, kaç sitenin *onlar olacağında* — ve bu araç onu ölçemez, ölçüyormuş gibi de yapmamalı. Bu satırlar korpustaki `crafted_kit` vakasının bandına göre değerlendirilir (25–60); bant oradan okunur, burada tekrar yazılmaz.

**14/14 doğru tarafta** · 1 proje hüküm dışı.

Kapsam sütunu skoru değil, skorun ne kadarını kapsadığını söyler: *kısmi*, taramanın uçtan uca okuyabildiği bir sayfa girişi bulamadığı ve deponun sayfalarının bu aracın okumadığı bir dilde olduğu anlamına gelir. O satırlardaki sayı okunabilen parça hakkındadır.

| proje | beklenen | şablon | karar | tekrar | eleman | kapsam | süre | yığın |
|---|---|---:|---:|---:|---:|---|---:|---|
| `cruip-landing` ✓ | crafted | 45.0 | 53.1 | 53.0 | 397 | tam | 0.1s | css, glass, tailwind, tokens |
| `cruip-open-react` ✓ | crafted | 43.2 | 54.2 | 58.5 | 358 | tam | 0.1s | css, glass, tailwind, tokens |
| `landwind` ✓ | template | 63.3 | 34.4 | 65.1 | 472 | tam | 0.1s | css, tailwind, tokens |
| `tailwindtoolbox` ✓ | template | 68.0 | 30.0 | 74.7 | 294 | tam | 0.1s | inline, tailwind, tokens |
| `precedent` ✓ | template | 51.2 | 43.4 | 55.4 | 188 | tam | 0.1s | css, glass, inline, modules, tailwind, tokens |
| `next-enterprise` ✓ | template | 55.0 | 30.3 | 46.7 | 74 | tam | 0.0s | css, tailwind, tokens |
| `saas-starter` ✓ | crafted | 33.8 | 61.9 | 51.3 | 520 | tam | 0.3s | css, glass, inline, tailwind, tokens |
| `shipfast-like` ✓ | template | 51.2 | 42.8 | 68.9 | 141 | tam | 0.1s | css, tailwind, tokens |
| `bchiang-v4` ✓ | designed | 16.6 | 80.3 | 43.0 | 396 | tam | 0.1s | css-in-js, inline, tailwind |
| `leerob-site` · | designed | 41.7 | 48.1 | 47.6 | 35 | kısmi | 0.0s | css, tailwind, tokens |
| `tholman` ✓ | designed | 35.6 | 53.5 | 38.5 | 65 | tam | 0.0s | css, tailwind |
| `daisyui` ✓ | designed | 16.0 | 80.5 | 37.0 | 10324 | tam | 1.3s | css, glass, inline, tailwind, tokens |
| `hono-website` ✓ | designed | 17.7 | 73.9 | 28.8 | 57 | tam | 1.2s | css, tailwind, tokens |
| `nuxt-website` ✓ | designed | 35.0 | 59.2 | 46.8 | 2199 | tam | 2.0s | css, glass, inline, tailwind, tokens |
| `solid-site` ✓ | designed | 26.7 | 66.1 | 39.6 | 717 | tam | 0.2s | css, inline, tailwind, tokens |

## Neden bu tarafta

- **cruip-landing** — Tailwind landing template sold by a design house — tuned type ramp, authored motion, stock palette
- **cruip-open-react** — React landing template from the same house, same profile
- **landwind** — Free Tailwind landing page, the canonical shape
- **tailwindtoolbox** — Single-file Tailwind landing page
- **precedent** — Next.js starter whose home page is a generated hero
- **next-enterprise** — Enterprise Next.js boilerplate with a landing page
- **saas-starter** — SaaS starter on a shadcn token system — a marketing route inside a whole application
- **shipfast-like** — Landing-page starter template
- **bchiang-v4** — A portfolio with an authored type scale and its own palette
- **leerob-site** — A personal site: restrained, typographic, no landing kit
- **tholman** — A personal site with a point of view
- **daisyui** — A component library's own site and demos
- **hono-website** — Docs site with an authored landing page
- **nuxt-website** — Nuxt's site: designed, componentised, token-driven
- **solid-site** — A framework site with its own palette and layout language

## Hüküm verilmedi

- **leerob-site** — 35 eleman — 6/9 işaretleme dosyası okundu · 0 sayfa · 35 eleman · 37 render
