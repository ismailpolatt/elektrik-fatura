# Energy Insight — Elektrik Fatura

Flask, SQLite ve Türkçe OCR ile Lokanta, Koltukçu ve Emlak Ofisi elektrik giderlerini dağıtır. Android uygulaması aynı web arayüzünü açar.

## Docker kurulumunu güncelleme

Docker'ın çalıştığı VM/LXC içinde **mevcut `docker-compose.yml` dosyasının bulunduğu proje klasöründe** çalıştırın:

```bash
git pull --ff-only origin master
bash scripts/update.sh
```

Güncelleme betiği çalışan `elektrik` servisinin SQLite veritabanını çevrimiçi yedekleme API'siyle `data/backups/` altına alır, imajı derler, yalnız bu servisi yeniden oluşturur ve yerel API'yi kontrol eder. `data/` bind mount korunur. Derleme başarısızsa çalışan konteyner durdurulmaz. Sunucuda `git pull` yerel kaynak değişiklikleri nedeniyle durursa değişiklikleri inceleyin; `reset --hard` kullanmayın.

Güncelleme sonrası telefondaki uygulamayı kapatıp yeniden açın. **Kaydet paneli, sayı ayrıştırma ve sunucu düzeltmeleri için yeni APK gerekmez.** Durum çubuğu boşlukları, geri tuşu ve harici bağlantı yönlendirmeleri için Android 1.0.1 kaynak kodu ayrıca derlenmelidir. Depodaki kök `app-debug.apk` eski 1.0 sürümüdür; bu dosya bu güncellemede değiştirilmemiştir. APK güncellemesi önceki kurulumla aynı imzalama anahtarını gerektirir; uygulama verilerini silerek kaldırma gerekmez.

## 1.0.1 düzeltmeleri

- Sonuç paneli görünür ekran yüksekliğini piksel olarak izler. Düzenle/Kaydet düğmeleri kaydırılan içerikten ayrıdır; kısa ekranlarda da görünür.
- Faturayı **Hesapla → Kontrol et → Kaydet** adımlarıyla ekleyin. Önizleme veritabanına yazmaz.
- Sayaçlar en fazla 3, tutar en fazla 2 ondalık basamak kabul eder. Tek nokta/virgül ondalıktır: `878.350` = 878,35 kWh. Gruplu değerler için `1.500,75` veya `1,500.75` kullanın; tam sayı 1500 için `1500` yazın.
- Hatalı sayı, negatif endeks, geriye giden endeks, ana tüketimi aşan alt tüketimler ve geçersiz tarih reddedilir. Negatif ödeme oluşmaz, toplam kuruşu kuruşuna faturaya eşittir.
- Aynı tarih ve aynı sayısal girdiler tekrar gönderildiğinde mevcut kayıt döner; eşzamanlı istekler de ikinci kayıt oluşturmaz. Aynı tarihli farklı girdiler otomatik silinmez veya birleştirilmez. Eski yinelenen kayıtlar korunur.
- Son endeks ve panel, ekleme sırası yerine okuma tarihine göre seçilir.
- Gri tonlu/CMYK görseller RGB'ye dönüştürülür, fotoğraf yönü düzeltilir. Okunamayan dosyalarda JSON hata yanıtı, 16 MB yükleme sınırı ve 60 saniye OCR zaman aşımı vardır.
- Sunucu hata yanıtları önizleme olarak gösterilmez; ağ hatalarında düğmeler yeniden etkinleşir. Tarih telefonun yerel gününü kullanır.

## Yerel doğrulama

```bash
python -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python -m unittest discover -s tests -v
node tests/test_frontend.mjs
```

Testler geçici SQLite veritabanları kullanır. Gerçek OCR motorunu çağıran bir fatura kabul testi yerine, OCR çıkışı kontrollü örnekle doğrulanır. Android derlemesi Java 17 ve Android SDK 36 gerektirir:

```bash
cd energy-insight-android
bash gradlew assembleDebug
```
