# Receipt Game Printer (Windows - 58mm ESC/POS)

Bu proje **yalnızca oyun amaçlı** gerçekçi görünümlü fiş basımı içindir. Ticari kullanım için değildir.

## Kurulum

1. Python 3.10+ kurun.
2. Proje klasörüne girin:
   ```bash
   cd receipt_game_printer
   ```
3. Bağımlılıkları yükleyin:
   ```bash
   pip install -r requirements.txt
   ```

## Python sürümü
- Önerilen: Python 3.10 veya üstü.

## Yazıcı sürücüsü kurulumu
- 58mm ESC/POS USB yazıcınızı Windows'a takın.
- Üretici sürücüsünü veya genel POS sürücüsünü kurun.
- Yazıcı, Windows "Yazıcılar ve Tarayıcılar" listesinde görünmelidir.

## Windows yazıcı adı nasıl bulunur
- Program içindeki **Yazıcıları Yenile** butonuna basın ve listeden seçin.
- Alternatif olarak Windows Ayarlar > Yazıcılar bölümünden tam adı alın ve manuel alana yazın.

## Programı çalıştırma
- `run.bat` dosyasına çift tıklayın.
- Ya da terminalden:
  ```bash
  python main.py
  ```

## Test fişi nasıl basılır
1. Yazıcı seçin veya manuel yazıcı adı girin.
2. Firma seçin.
3. Ürün, tutar, KDV ve ödeme tipini girin.
4. **Tek Fiş Bas** tuşuna basın.
5. Fiş metni aynı anda `receipts_output/` içine TXT olarak kaydedilir.

## Seri fiş nasıl basılır
1. Fiş sayısı girin (örn. 100).
2. Firma seçim modu seçin: Sırayla / Rastgele / Tek firma.
3. Gerekirse "Aynı firma üst üste gelmesin" işaretleyin.
4. Tutar modunu seçin: Sabit / Rastgele / Firma bazlı.
5. Tarih-saat başlangıcını ve fişler arası zamanı ayarlayın.
6. **Seri Baskı Başlat** tuşuna basın.
7. Sayaçtan basılan fiş sayısını takip edin.

## 58mm yazıcı ayarları
- Fiş tasarımı yaklaşık 32 karakter genişliğe göre hazırlanmıştır.
- Monospace (eşit aralıklı) görünüm esas alınmıştır.
- RAW gönderim ile ESC/POS kesme komutu eklenir.

## Fiş şablonu
- Varsayılan temiz şablonda otomatik alt bilgi veya ticari geçerlilik uyarısı basılmaz.
- **Fiş Şablonu** sekmesinden üst bilgi, alt bilgi, EKU No formatı, Z No, ayraç karakteri, fiş genişliği ve görünür alanlar düzenlenebilir.
- Alt bilgi tamamen isteğe bağlıdır; boş bırakılırsa fişin altında ekstra açıklama basılmaz.
- İsterseniz gerçekçi görünüm için `TESEKKUR EDERIZ`, `YINE BEKLERIZ`, `IYI GUNLER` gibi alt bilgi satırları yazabilirsiniz.
- Şablon ayarları `receipt_template.json` dosyasında saklanır.


## Mobil uyumlu web panel (2. aşama modül)
- `web_panel.py` ile mobil tarayıcıdan açılabilen responsive panel eklendi.
- Firma bazlı seri fiş üretimi, rastgele/sırayla/tek firma modları ve tarih-saat varyasyonu desteklenir.
- Üretilen fişler `receipts_output/` klasörüne TXT olarak kaydedilir.
- Doğrudan mobilde yazdırma yerine panel, Windows ana makinedeki yerel baskı API uç noktasına (`/api/print`) gönderim yapar.

### Web panel çalıştırma
```bash
python web_panel.py
```
- Aynı ağdaki telefondan: `http://<windows_pc_ip>:5050`

### Local API uçları
- `POST /api/generate` : Seri fiş üretir ve TXT kaydeder.
- `GET /api/printers` : Windows yazıcı listesini döner.
- `POST /api/print` : Gelen fiş metnini belirtilen yazıcıya RAW gönderir.


## Telefondan bağlanma adımları (Web Panel)
1. PC ve telefon aynı Wi-Fi ağına bağlı olmalı.
2. Windows Güvenlik Duvarı'nda Flask portu için (5050) izin verilmeli.
3. Web paneli başlatın:
   ```bash
   python web_panel.py
   ```
4. Telefonda tarayıcı açıp PC'nin yerel IP adresine gidin:
   - Örnek: `http://192.168.1.25:5050`
5. Panelde **Bağlantı Testi** ile yazıcı listesini çekin ve açılır listeden yazıcı seçin.

## Masaüstü firma yönetimi
- Ana uygulamada sekmeli yapı bulunur: **Tek Fiş**, **Seri Baskı**, **Firma Yönetimi**, **Fiş Şablonu**, **Ayarlar**.
- Üst menüden **Firma Yönetimi > Firma Ekle / Seçili Firmayı Düzenle / Seçili Firmayı Sil / Toplu Firma Düzenle** işlemleri yapılabilir.
- Firma Yönetimi sekmesindeki butonlarla firma ekleme, düzenleme, silme, kaydetme ve yeniden yükleme işlemleri yapılır.
- Toplu Firma Düzenle formatı:
  ```text
  Firma Adı | Sektör | Adres | Oyun Kodu | Ürün | KDV | Tutar
  ```
- Termal yazıcıda temiz baskı için Türkçe karakter kullanmayın: Ç yerine C, Ğ yerine G, İ yerine I, Ş yerine S, Ü yerine U, Ö yerine O.

## Tarih rastgeleleştirme
- **Seri Baskı** sekmesindeki **Tarih-saat modu** alanından `Rastgele tarih-saat üret` seçilebilir veya **Rastgele tarih-saat kullan** kutusu işaretlenebilir.
- Ay (1-12) ve yıl seçilerek o ay içindeki günler rastgele üretilebilir; fiş numaraları yine sıralı artmaya devam eder.
- **Gece saatlerini kullanma** açıkken saatler 08:00 - 22:59 aralığına sıkıştırılır.
- Bu seçenek kapalıyken başlangıç/bitiş saatleri 00:00 - 23:59 gibi tüm gün aralıklarına ayarlanabilir.
- **Aynı gün tekrar kullanılabilsin** kapalıysa seri baskıda mümkün olduğunca aynı gün tekrar edilmez; fiş sayısı ayın gün sayısını aşarsa günler yeniden kullanılabilir.
- Önizleme ve örnek tarih listesi ayar değiştikçe otomatik güncellenir.
