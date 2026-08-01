# aislopfixer

> Ölçer: bir web projesinin tasarımı **ne kadar şablon**? Düzeltir: projeye özgü bir tasarım sistemi türetip kodu ona taşır. Terminal arayüzü, tamamen çevrimdışı, API anahtarı yok.

[![npm](https://img.shields.io/npm/v/@mertsoylu/aislopfixer.svg)](https://www.npmjs.com/package/@mertsoylu/aislopfixer)
[![Python](https://img.shields.io/badge/python-%E2%89%A53.11-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

**Güncel sürüm: 0.7.0** — [npm](https://www.npmjs.com/package/@mertsoylu/aislopfixer)

---

## Sorun

AI slop artık yazım hatası değil. Bugünün modelleri temiz, erişilebilir, semantik kod yazıyor. Yine de çıktının hepsi birbirine benziyor. Şuna bakın:

```html
<section class="py-20 bg-white">
  <div class="max-w-7xl mx-auto px-4 text-center">
    <h2 class="text-4xl font-bold text-gray-900 mb-4">Features</h2>
    <p class="text-lg text-gray-600 mb-12">Everything you need</p>
    <div class="grid md:grid-cols-3 gap-8">
      <div class="rounded-2xl border p-6 shadow-sm">…</div>
```

Bu blokta yasak bir kelime yok. Tek bir hata yok. Ve tamamen slop — çünkü:

- `py-20` sayfadaki dokuz bölümün dokuzunda da var: **ritim yok, tek değer var**
- `max-w-7xl mx-auto px-4` her yerde: **tek container kararı**
- `text-center` her bölüm başlığında: **hizalama monokültürü**
- `grid-cols-3` üç ayrı yerde: **simetri monokültürü**
- Dört yazı boyutu, hepsi Tailwind varsayılan rampasından: **tipografi kararı sıfır**
- `rounded-2xl border shadow-sm` her kartta: **tek malzeme dili**

Yani slop **tekil token'da değil, token dağılımında**. Regex tabanlı bir linter bunu göremez, çünkü tek tek her sınıf meşru.

## Ölçü

**Bu projede kaç tane bağımsız tasarım kararı var?**

İnsan tasarımı bir landing page'de 30–50 karar bulunur. Üretilmiş çıktıda 4–8. Bu ölçülebilir, deterministik ve çevrimdışı.

Araç iki eksen ölçer:

| Eksen | Ne | Üretilmiş sayfa | Tasarlanmış sayfa |
|---|---|---:|---:|
| **Karar yoğunluğu** | Kaç bağımsız, varsayılan-dışı karar var | 10–30 | 60–100 |
| **Tekrar** | Sayfanın ne kadarı kendisinin kopyası | 80–95 | 20–55 |

**Şablon skoru** bu ikisinden çıkar. Kritik ayrım: *tutarlılık slop değildir*. Yüksek tekrar + yüksek karar = iyi bir tasarım sistemi, araç susar. Yüksek tekrar + düşük karar = şablon.

Değerin nereden geldiği kararı belirler:

| Kaynak | Örnek | Ağırlık |
|---|---|---:|
| Framework varsayılanı | `py-20`, `text-xl`, `bg-gray-100` | 0.25 |
| Yazılmış değer | `text-[2.75rem]`, `py-[68px]` | 1.0 |
| Proje tokenı | `bg-surface`, `rounded-panel` | 1.5 |

Ayrıca *yapısal* kararlar da sayılır — değeri varsayılan olsa bile: role göre değişen bant ritmi, asimetrik ızgara, container'dan taşan bir bant, hizalama çeşitliliği.

Sayı değil **oran** ölçülür: bir eksende kaç farklı değer varsa, hedef odur. Daha çok varsayılan kullanmak skoru yükseltmez, ve on kademeli bir renk rampası on karar değil **bir** karardır. Bu yüzden 40 elemanlık bir sayfa ile 10 000 elemanlık bir depo aynı ölçekte okunur.

Ölçüm sekiz eksende yapılır: **Tipografi · Renk · Boşluk/Ritim · Biçim · Yerleşim · Malzeme · Hareket · Kopya**. Projenin hiç kullanmadığı bir eksen sıfır sayılmaz, hesaba katılmaz — gölgesi ve animasyonu olmayan bir sayfa o eksenlerde başarısız olmamıştır, o eksenleri kullanmamayı seçmiştir.

### Kalibrasyon

`bench/cases/` içindeki etiketli korpus, her vakanın düşmesi gereken bandı taşır. `python -m bench.run`:

```
case                şablon  karar  tekrar  band          durum
----------------------------------------------------------------
slop_saas             88.6   18.9    87.8   70–100      ok
slop_tr               88.0   21.6    93.2   70–100      ok
slop_kit              75.9   28.5    76.3   70–100      ok
mid_human_tailwind    46.9   36.8    35.6   18–50       ok
crafted_kit           33.0   63.7    55.4   25–60       ok
clean_studio_large    12.4   85.8    39.9    0–20       ok

ayrım payı: 29.0 puan
```

`mid_human_tailwind` korpusun en zor vakası: elle yazılmış, sadece Tailwind varsayılanlarını kullanan dürüst bir sayfa. Onu şablondan ayıramayan bir ölçüm, tasarımı değil Tailwind'i ölçüyor demektir.

`crafted_kit` başka bir ayrımı sabitler: bir tasarım evinin yaptığı, satılan landing şablonu. Ayarlanmış tip rampası ve elle yazılmış easing eğrileri var, ama paleti kutudan çıkma. “Herkesin sayfası olacak” ile “kimse karar vermemiş” aynı iddia değil ve araç yalnızca ikincisini ölçer — o yüzden bu vaka ortada durur.

İkiz kuralı korpusun omurgası: `slop_saas` / `slop_react` / `slop_vue` / `slop_styled` aynı tasarımın dört yığındaki hâli, `clean_utility` / `clean_css` ise aynı temiz sayfanın utility ve ham CSS hâli. Aralarındaki fark 5 puanı geçerse araç tasarımı değil lehçeyi ölçüyordur.

Korpus kapalı bir devre — vakaları biz yazdık. Açık devre `bench/field.md`: on beş gerçek depo klonlanır, taranır, ve **hangi satırın yanlış tarafa düştüğü tabloda kalır**. `--transform` ile aynı tablo dönüşümün çıktısını da ölçer: önce/sonra skor, ve “yalnızca sınıf listeleri değişti” invaryantının bayt düzeyinde doğrulanması. `bench/impact.md` ise aracın `a`'ya basılmadan önce gösterdiği tahmini gerçekleşenle karşılaştırır — o tahmin bir model değil, dönüşümün bellekte çalıştırılmış hâlidir, ve on yedi vakada da fark sıfırdır. Hiçbiri bir kapı değil.

---

## Kurulum

```bash
npm install -g @mertsoylu/aislopfixer
aislopfixer ./projem
```

Makinede **Python ≥ 3.11** olmalı. İlk çalıştırmada npm başlatıcısı `~/.aislopfixer/` altında yalıtılmış bir Python ortamı kurar (bir kez internet gerekir), sonrasında anında açılır.

## Kullanım

```bash
aislopfixer ./my-site
aislopfixer ./monorepo --pages "app/(marketing)"
```

`--pages`, bir depo içindeki **tek bir siteyi** ölçmek içindir. Ağacın tamamı yine okunur — bileşenler nerede dururlarsa dursunlar çözülür — süzülen şey ölçümün neyi anlattığıdır: verilen yolun altındaki sayfalar ve onların kullandığı bileşenler. `.aislopfixer.toml` içindeki `pages = ["app/(marketing)"]` ile aynı iş.

### 1 · Rapor ekranı

Manşette şablon skoru ve iki eksen. Solda sekiz eksenin karar/tekrar ölçerleri, altında ölçülen gözlemler; sağda seçili gözlemin ayrıntısı — ne ölçüldü, kaynakta nerede (`dosya:satır` ve kod satırı), ve yerine ne yapılmalı.

| Tuş | |
|---|---|
| `↑` `↓` | gözlemler arasında gez |
| `a` | gözlemi kabul et (raporda kalır, reçeteye girmez) |
| `x` | agent reçetesi yaz (`.aislopfixer/brief.md` ve pano) |
| `s` | sistem ekranı |
| `r` / `n` / `q` | yeniden tara / başka klasör / özet |

### 2 · Sistem ekranı

Araç projeye özgü bir tasarım sistemi türetir ve kodun ona göre nasıl değişeceğini **uygulamadan önce** diff olarak gösterir.

| Tuş | |
|---|---|
| `s` | arketipi değiştir (sistem ve diff anında yeniden hesaplanır) |
| `d` | diff ile değişiklik listesi arasında geçiş |
| `a` | uygula |
| `u` | geri al |
| `1`–`5` / `0` | dönüşümü eksene göre süz (renk · tip · ritim · yerleşim · malzeme) |

`a`'nın üstünde duran sayı bir tahmin değil: dönüşüm bellekte çalıştırılıp aynı boru hattıyla yeniden ölçülür. Zaten bir sistemi olan bir projede araçınki daha dardır ve skor **yükselir** — o durumda `a` kapalı sunulur, yazmak için iki kez basmak gerekir.

---

## Türetilen sistem

Bir varsayılanı başka bir varsayılanla değiştirmek işe yaramaz. Bu yüzden altı elle yazılmış **arketip** var; her biri tip, ritim, kenar, derinlik ve hizalama konusunda diğerlerinden farklı bir pozisyon alıyor:

**Editorial** · **Swiss** · **Terminal** · **Warm Craft** · **High Contrast** · **Archive**

Proje kimliğinden (klasör ve paket adı, CRC32) türetilen tohum arketipi ve hue'yu seçer — yani **aynı proje her zaman aynı sistemi alır**, farklı projeler farklı sistem alır. Projenin kendi markalı rengi varsa (yazılmış bir hex, hazır paletten bir shade değil) o hue korunur; yalnızca etrafındaki sistem yeniden kurulur.

Sistem `.aislopfixer/system.css` olarak yazılır — hem `@theme` (Tailwind v4) hem `:root` (düz CSS veya v3) bloğuyla, ikisi de aynı değerlerle:

```css
@theme {
  --color-paper: #fdf7ef;      --color-ink: #21180d;
  --color-ink-muted: #5e554b;  --color-rule: #e0d7cd;
  --color-accent: #b74124;     --color-on-accent: #fdf7ef;
  --font-display: "Signifier", Georgia, serif;
  --text-display: 3.227rem;    --leading-display: 0.98;
  --tracking-display: -0.032em;
  --spacing-band-open: 7.5rem; --spacing-band-dense: 3.5rem;
  --container-read: 46ch;      --container-content: 74rem;
  --radius-panel: 2px;         --radius-control: 6px;
}
```

Paletler HSL doygunluğu yerine **sabit kroma** ile üretilir: doygunluk, açıklık uçlara yaklaştıkça anlamını yitirir, bu yüzden kroma belirtip doygunluğu çözmek tonun sayfa zemininden mürekkebe kadar görünür kalmasını sağlar. Her arketipin `ink/paper`, `ink-muted/paper` ve `on-accent/accent` çiftlerinin WCAG eşiklerini geçtiği test edilir.

## Dönüşüm

**Sert kural: yalnızca sınıf listeleri değişir, DOM ağacına asla dokunulmaz.** Bu yüzden çıktı her zaman derlenir; en kötü ihtimalle sayfa yanlış görünür, build kırılmaz.

```diff
- <section class="py-20 bg-white">
-   <div class="max-w-7xl mx-auto px-4 text-center">
-     <h2 class="text-4xl font-bold text-gray-900 mb-4">Features</h2>
-     <p class="text-lg text-gray-600 mb-12">Powerful tools that scale.</p>
-     <div class="grid md:grid-cols-3 gap-8">
-       <div class="rounded-2xl border border-gray-200 p-6 shadow-sm">
+ <section class="py-band-narrative bg-paper">
+   <div class="max-w-content mx-auto px-4">
+     <h2 class="text-section font-display leading-display tracking-display font-bold text-ink mb-4">Features</h2>
+     <p class="text-lead text-ink-muted mb-12">Powerful tools that scale.</p>
+     <div class="grid gap-x-[1.75rem] gap-y-[2.5rem] grid-cols-1 md:grid-cols-12">
+       <div class="border border-rule p-6 md:col-span-5">
```

Yapılanlar:

- **Token remap** — stok palet değerleri sistem rollerine (`bg-blue-600` → `bg-accent`, `text-gray-600` → `text-ink-muted`)
- **Tip rolleri** — framework rampası display/section/title/lead/body/meta'ya; display boyutlar rampada hiç olmayan leading ve tracking'i kazanır
- **Ritim** — tek bant değeri, bölümün *ne olduğuna* göre dört banda ayrılır (hero → `open`, özellikler → `narrative`, fiyat ve SSS → `dense`, alt bilgi → `close`)
- **Simetri kırma** — simetrik ızgaralar 12 sütunlu asimetrik bölünmeye; her ızgara farklı bir desen alır, yoksa asimetri de tekdüzeleşir
- **Hizalama** — ortalanmış başlık monokültürü arketipin doktrinine göre çözülür
- **Tam genişlik kırılması** — sayfada bir medya elemanı, yalnızca sınıflarla container'ın dışına taşınır
- **Bağlama** — `.aislopfixer/system.css` HTML `<head>` ya da CSS girişine bağlanır

Güvenlik: her dosyaya bir kez `.aislopfixer.bak`, uygulamadan önce tam diff, `u` ile geri alma, ve **idempotent** çalışma (ikinci geçiş sıfır düzenleme üretir). Dosyalar LF olarak okunup **kendi satır sonu ve BOM'uyla** geri yazılır.

Ölçülen etki: `slop_saas` 88.6 → 23.9, `slop_react` 87.6 → 40.0. Saha tarafında on iki deponun on ikisinde patch `git apply` temiz, ikinci geçiş sıfır düzenleme, ve **hepsinde skor düşüyor**.

`className={cn(...)}` gibi ifade sınıfları **atlanır ve sayılır** — orası kod, sessizce düzenlenmez.

## Agent reçetesi

Sınıf yazımıyla çözülemeyen şeyler kalır: kanonik bölüm sırası, üç işi birden yapan tek blok şekli, slot doldurmak için yazılmış metin. `x` bunları bir coding agent'ın uygulayabileceği markdown brief'e çevirir — türetilen sistemin token isimleriyle ve ölçüme dayalı kabul kriteriyle birlikte.

---

## Mimari

```
src/aislopfixer/
├── cli.py / app.py        # TUI giriş noktası ve ekran akışı
├── scanner.py             # dosya yürüyüşü (uzantı, boyut, minified filtresi)
├── store.py               # .aislopfixer/{state.json, report.md}
├── screens/               # splash → path → scan → report → system → summary
└── design/
    ├── models.py          # Axis, Origin, Decl, Element, Observation, DesignReport
    ├── parse/             # markup (toleranslı HTML/JSX/MDX tarayıcı), css,
    │                      #   classes, components, styles, expr, theme, lexer
    ├── metrics/           # vocabulary · rhythm · layout · repetition · palette ·
    │                      #   content · tells · sections · states · contrast
    ├── analyze.py         # metrikleri birleştirir → DesignReport
    ├── scope.py           # kök + kapsam: hangi siteyi ölçtüğümüz (--pages)
    ├── render.py          # yazılmış ağaç → tarayıcının aldığı ağaç
    ├── system/            # archetypes · derive · color · emit · preview
    ├── transform/         # classmap · plan · apply · wire · verify
    └── brief.py           # rapor → agent reçetesi
```

Boru hattı: **ayrıştır → ölç → sistem türet → planla → önizle → uygula → yeniden ölç.**

## Geliştirme

```bash
pip install -e ".[dev]"
aislopfixer ./bench/cases/slop_saas   # arayüzü aç
python -m bench.run                    # kalibrasyon tablosu
pytest                                 # 185 test
python -m bench.field --no-fetch       # saha tablosu (önbellekteki klonlar)
python -m bench.impact                 # tahmin edilen vs gerçekleşen düşüş
```

## Lisans

MIT
