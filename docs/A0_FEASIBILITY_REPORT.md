# SONAR — A0 Supplier Integration Feasibility Report

İnceleme: 8 Ekim 2026. Tarihler Türkiye saatiyle (UTC+3) verilmiştir; JSON kayıtları UTC kullanır. Kapsam yalnızca A0'dır.

## Karar

**CONDITIONAL GO. A0 araştırması tamamlandı; iki tedarikçi için de sınıflandırma PARTIAL.** Gerçek ürün bilgileri yerel Python uygulamasıyla okunabiliyor. Ancak iki tedarikçide güvenilir, uçtan uca otomatik tam MPN arama ve karşılaştırma hedefi henüz sağlanmış değil.

| Tedarikçi | Sınıf | Çalışan işlev | Önemli engel |
|---|---|---|---|
| Özdisan | **PARTIAL** | İzin verilen, bilinen ürün URL'sinden açık MPN/üretici, stok adedi, MOQ/kat, ambalaj ve fiyat kademeleri okunuyor | Mevcut robot kuralları normal `search=` aramasını ve API yollarını engelliyor. Otomatik keşif **BLOCKED**; birim fiyatın KDV anlamı doğrulanmadı |
| Direnc.net | **PARTIAL** | Normal arama → gerçek ürün URL'si → stok durumu, temel fiyat/vergi etiketi ve miktar tablosu okunuyor | Denenen ürünlerde açık üretici MPN'si ve stok adedi eksik. Ambalaj eksik; bazı üretici adları belirsiz. Miktar tablosunun KDV işareti güvenilir değil |

PASS, temel arama ve satın alma verisinin güvenilir biçimde çalışmasıdır. PARTIAL, kullanılabilir işlevler yanında önemli boşluklar bulunmasıdır. BLOCKED, güvenilir erişimin mevcut koşullarda gösterilememesidir. Özdisan'ın arama işlevi BLOCKED olsa da ürün okuma çalıştığından tedarikçinin toplam sınıfı PARTIAL tutuldu.

**A1'e koşulsuz hazır değil.** Bir sonraki aşamadan önce izinli Özdisan keşif kaynağı/tedarikçi anlaşması bulunmalı veya bilinen URL ile çalışma sınırı ürün kapsamına açıkça alınmalı. Direnc.net sonuçlarının kullanıcı incelemesi gerektiren adaylar olarak sunulması ve eksik MPN/ambalaj/stok/KDV bilgilerinin korunması da kabul edilen kapsam olmalı. İki otomatik tedarikçiyi kesin eşleştirip en ucuz teklifi garantileme varsayımıyla tam uygulama yatırımına geçmek için **NO-GO**. A1 veya sonraki fazların kodu bu çalışmada yazılmadı.

## 1. Başlangıç ve uygulanan A0

[GitHub deposu](https://github.com/Batuhxn/SONAR) değişiklik öncesinde yeniden incelendi: public, boyut 0; içerik API'si boş depo yanıtı verdi. İlk commit veya korunması gereken uygulama yoktu. Depo yerel çalışma alanına klonlandı; çalışma GitHub'da değiştirilmedi.

Uygulananlar:

- Python paket yapısı ve kilitlenmiş üç runtime bağımlılığı; doğrudan bağımlılık yalnızca BeautifulSoup.
- Ortak `SupplierAdapter`: `search`, `product`, `parse_product`, `health`.
- Ayrı Özdisan ve Direnc.net adaptörleri; site URL/DOM/veri davranışı ortak iş mantığına yerleştirilmedi.
- Standart kütüphane HTTP istemcisi: robot kuralları, minimum istek aralığı, yönlendirme kontrolü, erişim/hata durumları, SHA-256 ve zaman kaydı.
- `search`, `product`, `health`, `verify` komutları; aktif/pasif/parametrik/negatif test manifesti.
- Açıklanabilir veri modeli: `Offer`, `PriceBreak`, `Result`; Decimal fiyatlar, bilinmeyen sayılar için `null`, alan kaynağı ve uyarılar.
- 41 otomatik test, ayrı gerçek HTTP kanıtları, kurulum kılavuzu ve mimari belgesi.

Windows 11 Pro 64-bit, sürüm 10.0.26200; Python 3.12.10 üzerinde çalıştırıldı. Ücretli API/servis, bulut veritabanı, hosting, kullanıcı hesabı, CAPTCHA çözümü veya tarayıcı otomasyonu kullanılmadı. Hiçbir satın alma veya otomatik muadil değiştirme yapılmadı.

## 2. Erişim ve kullanım koşulları

[Özdisan robots.txt](https://www.ozdisan.com/robots.txt), gerçek HTTP 200 ile alındı. Ana sayfanın public SearchAction tanımı `/c?search=...` adresini gösteriyor. Robot dosyasının ilgili kuralları:

```text
Disallow: /*search=
Disallow: /api/
Disallow: /_next/
```

Bu nedenle Özdisan arama URL'lerine **istek gönderilmedi**. Kanıtta `attempted:false`, `robots_disallowed` ve kontrol zamanı vardır. Ürün sayfasında zaten bulunan JSON-LD ve anonim sayfa verisi okunur; ayrı API veya Next.js yolları çağrılmaz. Politika değişirse bile mevcut A0 adaptörü otomatik arama başarısı iddia etmez; keşif ayrıştırıcısı ayrıca doğrulanmalıdır.

[Direnc.net robots.txt](https://www.direnc.net/robots.txt) normal `/arama?q=...` formunu engellemiyor; `/srv/` ve `/ajax.php` yollarını engelliyor. Doğrudan normal arama HTML'si ve orada gözlenen ürün linkleri kullanıldı. Autocomplete/private servis yolları araştırılarak kısıtlar aşılmadı.

Her istemci alan adı başına istek başlangıçları arasında en az iki saniye bırakır; daha uzun robot crawl-delay varsa uygular. Kimlik `SONAR-A0` olarak açıkça belirtilir. Kimlik değiştirme, cookie/login veya proxy yoktur. 403/429/robot kontrol hatası karşısında doğrulama turu o tedarikçi için devam etmez. Aynı tedarikçiye eşzamanlı ayrı süreçler çalıştırılmamalıdır.

[Özdisan üyelik koşulları](https://www.ozdisan.com/sozlesmeler/uyelik-sozlesmesi) ve [Direnc.net kullanım koşulları](https://www.direnc.net/kullanim-sozlesmesi) gerçek isteklerle okundu. İçerik/yazılım ve yeniden kullanım sınırlamaları mevcut; robot dosyasındaki erişim izni bütün içeriği ticari olarak yeniden yayımlama izni sayılmadı. Public/çok kullanıcılı ürün için veri kullanım koşulları ayrıca netleştirilmelidir. Bu A0, tedarikçi izni veya resmi API anlaşması bulunduğunu iddia etmez. Tam HTML, yorumlar, müşteri bilgileri veya site script'leri repoya alınmadı.

Politika/koşul URL'leri, alınma zamanları, ilgili kısa kurallar ve response hash'leri: [access-policy.json](evidence/access-policy.json).

## 3. Gerçek doğrulama kayıtları

| Tur | Türkiye saati | Vaka sayısı | Sonuçlar | Ürün kayıtları |
|---|---|---:|---|---:|
| İlk tur | 19:39:42–19:40:31 | 24 | 10 robots_disallowed, 7 partial, 7 not_found | 9 |
| İkinci tur | 19:44:18–19:45:27 | 27 | 10 robots_disallowed, 10 partial, 7 not_found | 14 |
| Son doğrulanmış tur | 19:51:09–19:52:09 | 27 | 10 robots_disallowed, 10 partial, 7 not_found | 14 |

Son turda 30 gerçek HTTP isteği var: Özdisan 8, Direnc.net 22. Buna robot dosyaları, ürün sayfaları ve gereken izinli yönlendirmeler dahildir. Özdisan'ın 10 arama vakası yalnızca robot ön kontrolünde durdu; bu 30 isteğe dahil değildir. Tablodaki ürün kaydı sayısı **uygun parça/eşleşme sayısı değildir**; alakasız adaylar da sonuçların yanlış olduğunu göstermek üzere korunur.

Turlar birbirinden bağımsız istemcilerle yeni HTTP istekleri yaptı. Aynı gün kısa aralıklı tekrarlar kararlılığa sınırlı kanıt sağlar; haftalar boyunca veya bütün katalogda güvenilirlik garantisi değildir. İlk turların undocumented KDV flag yorumları son turda düzeltilmiştir. Nihai veri yorumu [validated-run.json](evidence/validated-run.json) dosyasıdır; [run-1.json](evidence/run-1.json) ve [run-2.json](evidence/run-2.json) araştırma geçmişidir.

Her kayıt gerçek URL, alınma zamanı, HTTP durum kodu, response boyutu/hash'i ve normalize alanlar içerir. Test fixture'ları bu canlı sonuçların yerine kullanılmadı. Normalizasyon saf fonksiyon testlerinden ayrıdır.

### Özdisan sonuçları

Arama için LM358P, NE555P, LM324N, 1N4148, RC0603FR-0710KL, CC0603KRX7R9BB104, iki parametrik sorgu ve iki uydurma negatif test kimliği kullanıldı. Hepsi mevcut robot politikasında engellendi. Bu durum “parça yok” anlamına gelmez.

Bilinen public URL'lerle ürün okuma aşağıdaki sonuçları verdi; URL'ler tedarikçi ana sayfasındaki gerçek linklerden veya ayrı public araştırmadan alınmıştır, adaptör aramasıyla bulunmuş gibi sunulmaz:

| Ürün | Açık MPN eşleşmesi | Son turdaki stok adedi | MOQ / kat | Fiyat/ambalaj |
|---|---|---:|---|---|
| [LM358P](https://www.ozdisan.com/p/amplifikatorler-242/texas-lm358p-13549) | Tam MPN | 18.063 | 1 / 1 | TRY/USD, 4 kademe, TUBE |
| [NE555P](https://www.ozdisan.com/p/programlanabilir-zamanlayici-ve-osilator-entegreleri-211/texas-ne555p-14278) | Tam MPN | 2.779 | 1 / 1 | TRY/USD, 4 kademe, BOX |
| [RC0603FR-0710KL](https://www.ozdisan.com/p/SMT---SMD-and-Chip-Resistors-194/yageo-rc0603fr-0710kl-379294) | Tam MPN | 11.150 | 50 / 1 | TRY/USD, 7 kademe, ayrı ambalaj kayıtları |
| [CC0603KRX7R9BB104](https://www.ozdisan.com/p/SMT---SMD-and-MLCC-Capacitors-184/yageo-cc0603krx7r9bb104-476015) | Tam MPN | **0, stok dışı** | 10 / 1 | TRY/USD, 7 kademe, ayrı ambalaj kayıtları |
| [LM324N-TI](https://www.ozdisan.com/p/amplifikatorler-242/texas-lm324n-ti-27237), sorgu LM324N | **Partial; son ek korunur** | 1.375 | 1 / 1 | TRY/USD, 4 kademe, TUBE |

Bu stok rakamları yalnızca belirtilen turdaki tarihsel kanıttır. MPN, üretici, stok ve fiyat kademeleri anonim public sayfa verisinden gelir. MPQ ayrı saklanır; MOQ veya kat olduğu varsayılmaz. Fiyatlar ambalaj ve para birimiyle birlikte tutulur.

**KDV sınırı:** Görünür tabloda toplam fiyat KDV dahil olarak etiketleniyor; `price` birim fiyatı ile `extendedPrice` toplamı farklı. Birim fiyatın vergi bazını yalnızca oran veya alan adından çıkarmadık. A0 birim fiyatları `vat:unknown` olarak saklıyor; stok dışı üründe fiyat bulunması stok var anlamına gelmiyor. EUR fiyatları deterministik testlerde kapsandı; bu canlı Türkçe oturumlarda TRY/USD gözlendi.

### Direnc.net sonuçları

İlk 10 sorgu iki turda da aynı sonucu verdi:

- LM358P: bir ürün linki ve ürün bilgisi bulundu.
- LM324N: iki farklı ürün linki bulundu; birleştirilmedi.
- 1N4148: ilk iki sonuç okundu; ikinci ürün `1N4148W-HT`, aynı MPN sayılmadı. Sonuçlar ilk iki ürünle sınırlı; tam katalog değerlendirmesi değil.
- NE555P, iki Yageo tam MPN'si, `10K 0603`, `100nF 0603` ve iki negatif kimlik için site açık “sonuç yok” mesajı verdi. Bu, ürünün hiçbir ad/parametre altında satılmadığını kanıtlamaz.

Genişletilmiş pasif sorgular:

- `100nF`: iki gerçek kondansatör sayfası okundu; temel fiyat ve stok durumu alınabildi. Değer bir MPN gibi yorumlanmadı.
- `10K`: ilk iki sonuç 10 kg yük hücresi ürünleriydi. Teknik olarak arama/okuma çalışsa da ilgili direnç bulunmuş kabul edilmedi; arama bulunurluğu ile parça uygunluğu ayrıdır.

Örnek [LM358P sayfasından](https://www.direnc.net/lm358-single-supply-dual-operational-amplifiers) görünür temel 4,65 TRY KDV dahil ve 3,87 TRY + KDV fiyatları okunuyor. Bunlar son turdaki tarihsel örneklerdir; genel karşılaştırma önerisi değildir. Miktar kademeleri de okunuyor, ancak **KDV bazları bilinmiyor**.

Sınırlar:

1. Denenen dokuz ürün kaydının JSON-LD'sinde açık `mpn` alanı yok. Başlıkta LM358P yazması `candidate_mpn` olabilir; `exact_mpn` olamaz. “STM - Texas” gibi marka etiketi üreticiyi kesinleştirmez.
2. Schema.org ve DOM stok durumu okunuyor; sayı görünmediği için `stock_quantity:null`. Stokta etiketi yüksek miktarı karşılayabildiğini kanıtlamaz. Stok dışı bir Direnc.net ürününde de sayı uydurulmaz.
3. JSON-LD SKU ile gösterilen stok kodu farklı olabilir: örnek LM358P schema SKU'su T2220; görünür kod DSTK1120. A0 açık schema SKU'sunu kaynak etiketiyle tutuyor; sipariş dosyası SKU doğruluğu kanıtlanmış değil.
4. `Paket Tipi` bu ürünlerde entegre kılıfını anlatıyor. TUBE/reel/cut-tape gibi sevkiyat ambalajı diye yorumlanmadı.
5. Input `min`/`step` değerleri kamuya açık sipariş arayüzü kısıtlarıdır; tedarikçiyle yapılmış özel satın alma koşulu değildir.
6. Miktar tablosunda `data-vat=0` bazı ürünlerde görünür KDV dahil temel tutarla aynı değeri taşıdı. Belgelenmemiş bayrak doğrudan vergi durumu sayılmadı; kademeler `unknown`. Yalnız açık vergi etiketi olan temel fiyatlar included/excluded olabilir.
7. Sayfanın slug'ı eski teknik değer içerebilir; örneğin kondansatör URL'sinde 63V geçerken güncel başlık 50V olabilir. Teknik özellikler URL'den türetilmez. A0 teknik uygunluk kararı vermez.

## 4. Üç ortak tam MPN hedefi

**Üç doğrulanmış ortak tam MPN bulunamadı: doğrulanmış çift sayısı 0.** LM358P iki sitede aday olarak görünse de Direnc.net açık üretici MPN alanı ve net üretici kimliği sunmuyor. Özdisan'ın LM324N-TI ürünü Direnc.net'in LM324N başlığıyla eşit sayılmıyor. NE555P ve iki Yageo MPN'si Direnc.net'in denenen tam sorgularında sonuç vermedi.

Bu hedefi tamamlamak için son ek silme, SKU'yu MPN sayma, diğer üreticiyi aynı ilan etme veya modülü çıplak parçayla eşitleme yapılmadı. Örnekler, eksikliğin gerçek kanıtıdır; başarı kotasını doldurmak için veri üretilmedi. Yeni izinli veri kaynakları olmadan kapsamlı karşılaştırma MVP kabul kapısı geçilmiş değildir.

## 5. Otomatik testler ve doğrulama

**41/41 test geçti.** Son çalıştırma: `python -m unittest discover -s tests -v`, exit 0; [tam çıktı](evidence/test-results.txt). `pip check`: broken requirements yok. Kaynak ve testler Python derleme kontrolünden geçti.

Kapsanan davranışlar:

- JSON/DOM normalizasyonu; değişik veya eksik ürün formatı.
- Tam/partial MPN; son eklerin korunması; başlık adayının tam eşleşmeye yükseltilmemesi; değerlerin MPN sanılmaması.
- Eksik/gizli/çatışan fiyat veya stok; unknown / not_disclosed / out_of_stock ayrımı.
- TRY/USD/EUR; Decimal hassasiyeti; TR sayı ayracı.
- Açık KDV dahil/hariç temel fiyat; doğrulanmamış miktar kademelerinin VAT unknown kalması.
- Miktar kademesi, maksimum miktar, MOQ/kat, MPQ ve ambalaj ayrımı.
- Zaman aşımı, ağ hatası, 401/403/404/429/500, challenge ve beklenmeyen content type.
- Robots wildcard/agent/Allow önceliği; yasaklı URL ve yönlendirmeye istek gitmemesi; minimum hız sınırı.
- Timestamp/response hash ve eskilik kontrolü; canlı tur tamamlanmasının entegrasyon PASS diye sunulmaması; 429 sonrası tedarikçinin durdurulması.

Test fixture'ları açıkça sentetik ve küçük tutuldu. Canlı erişim testleri test suite'e katılmadı; rutin test çalıştırması sitelere trafik üretmez. Testler bütün ürün kataloğu veya bütün robot standardı için doğruluk garantisi değildir.

## 6. Tekrarlama ve dosyalar

Kurulum ve yürütülebilir PowerShell komutları [README](../README.md) içinde. Tekrarlama:

```powershell
.\.venv\Scripts\python.exe -m sonar_a0 search direnc LM358P --limit 2
.\.venv\Scripts\python.exe -m sonar_a0 search ozdisan LM358P
.\.venv\Scripts\python.exe -m sonar_a0 verify --cases examples/a0_cases.json --output live-output/new-run.json
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

`verify` exit 0, vakaların araştırıldığını anlatır; tedarikçi PASS değildir. Yeni dosya üretir ve eski canlı veriyi cache olarak kullanmaz. `fetched_at`, sunucunun veriyi güncellediği an değil, dokümanın alındığı andır. Kanıt dosyaları tarihsel olarak saklanır.

Dosya grupları:

- `pyproject.toml`, `requirements.lock`, `.gitignore`, `README.md`.
- `src/sonar_a0/`: modeller, normalizasyon, HTTP/politika, CLI, paket giriş noktaları.
- `src/sonar_a0/adapters/`: ortak sözleşme, Özdisan ve Direnc.net.
- `tests/`: dört test modülü ve üç sentetik HTML fixture; fixture açıklaması.
- `examples/a0_cases.json`: 27 vakalık canlı manifest.
- `docs/ARCHITECTURE.md`, bu rapor, `docs/evidence/`: üç canlı JSON, politika özeti, test çıktısı ve kanıt açıklaması.

Yerel commit çalışma sonunda oluşturulur; hash teslim özetinde verilir. **Push yapılmaz.** E-Komponent/Robotistan/Arkotek/Mouser/DigiKey bağlantıları, UI, BoM importer, hosted service veya A1 işleri eklenmedi.

## 7. Sonraki karar için gerekli koşullar

1. Özdisan'da izinli ve ücretsiz arama/keşif için resmi yöntem bulunmalı; veya ilk ürün kapsamı bilinen URL ile sınırlanmalı. Robot kısıtını aşmak çözüm değildir.
2. Direnc.net adaylarını kullanıcı tarafından doğrulanacak sonuçlar olarak ele al; daha iyi MPN/ambalaj/sayısal stok kaynağı olmadan otomatik satın alma uygunluğu iddia etme.
3. Fiyat kademelerinin KDV ve ambalaj anlamı netleşmeden iki site arasında kesin en ucuz önerisi üretme.
4. Tam karşılaştırma geliştirmeden önce en az üç ortak tam MPN, üretici/kılıf/ambalaj koşullarıyla doğrulanmalı; mevcut A0 bu kapıyı geçmiyor.
5. İleride public/ticari kullanım planlanırsa veri kullanım koşulları da netleştirilmeli. Bu araştırma için kullanıcıdan ücretli hizmet veya ek hesap istenmedi.

**A0 tamamlanma değerlendirmesi:** Her iki tedarikçi gerçek isteklerle araştırıldı; çalışan alanlar tekrarlanabilir komut ve kanıtlarla gösterildi; engeller/eksikler belgelendi; genişletilebilir sözleşme ve otomatik testler hazır; CONDITIONAL GO kararı kanıta dayanıyor. Engellerin varlığı A0 araştırmasını eksik yapmıyor, ancak başarılı tam entegrasyon iddiasını engelliyor.
