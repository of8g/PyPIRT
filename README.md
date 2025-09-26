# PyPIRT - Android Uzaktan Kontrol Uygulaması

PyPIRT (Python İnternet Rehber Telefon veya Python Phone Integration System), Android cihazları Wi-Fi üzerinden uzaktan kontrol etmek için geliştirilmiş bir masaüstü uygulamasıdır. ADB (Android Debug Bridge) teknolojisini kullanarak telefonunuzu bilgisayarınızdan kontrol edebilmenizi sağlar.

## 🚀 Özellikler

### 📞 Rehber Yönetimi
- Kişi ekleme, düzenleme ve silme
- Profil fotoğrafı desteği
- Favori kişiler işaretleme
- Etiket sistemi ile kategorilendirme
- Gelişmiş arama ve filtreleme

### 📱 Telefon Kontrolü
- **Anında Arama**: Seçili kişiyi hemen arayın
- **Telefon Uygulaması**: Numarayı telefon uygulamasında açın
- **SMS Gönderme**: Önceden yazılmış mesajlarla SMS gönderin

### 📲 Uygulama Yönetimi
- Yüklü uygulamaları listele
- Uygulamaları uzaktan başlatın
- Sistem ve kullanıcı uygulamalarını filtreleyin
- Uygulama bilgilerini görüntüleyin

### 🔧 Gelişmiş ADB İşlemleri
- Wi-Fi üzerinden ADB bağlantısı
- Cihaz bilgilerini görüntüleme
- Ekran görüntüsü alma
- Dosya transferi (push/pull)
- Pil durumu ve sistem bilgileri

## 📋 Gereksinimler

### Sistem Gereksinimleri
- **İşletim Sistemi**: Windows 10/11
- **Python**: 3.7 veya üzeri
- **ADB**: Android Platform Tools yüklü olmalı

### Python Kütüphaneleri
```bash
pip install customtkinter
pip install Pillow
```

### Android Cihaz Gereksinimleri
- **Geliştirici Seçenekleri**: Etkinleştirilmeli
- **USB Hata Ayıklama**: Açık olmalı
- **Kablosuz ADB**: Etkinleştirilmeli (Android 11+)

## ⚙️ Kurulum

1. **Depoyu klonlayın:**
   ```bash
   git clone https://github.com/of8g/pypirt.git
   cd pypirt
   ```

2. **Gerekli kütüphaneleri yükleyin:**
   ```bash
   pip install -r requirements.txt
   ```

3. **Android Platform Tools'u yükleyin:**
   - [Android Developer](https://developer.android.com/studio/releases/platform-tools) sitesinden indirin
   - `adb.exe` dosyasının PATH'te olduğundan emin olun

4. **Uygulamayı çalıştırın:**
   ```bash
   python PyPIRT.py
   ```

## 🔌 Android Cihaz Bağlantısı

### Wi-Fi ADB Kurulumu

1. **Telefonunuzda:**
   - Ayarlar → Geliştirici Seçenekleri
   - "Kablosuz hata ayıklama"yı etkinleştirin
   - IP adresini ve portu not edin

2. **PyPIRT'te:**
   - IP:Port alanına cihaz bilgilerini girin (örn: `192.168.1.100:5555`)
   - "🔌 Bağlan" butonuna tıklayın
   - Durum "🟢 Bağlı" olarak değişmeli

### İlk Bağlantı İçin USB Kurulumu

```bash
# Cihazı USB ile bağlayın
adb devices

# Wi-Fi ADB'yi etkinleştirin
adb tcpip 5555

# Cihazın IP adresini öğrenin
adb shell ip route

# Wi-Fi üzerinden bağlanın
adb connect 192.168.1.100:5555
```

## 📱 Kullanım

### Rehber İşlemleri
1. **Kişi Ekleme**: "➕ Ekle" butonu ile yeni kişi ekleyin
2. **Profil Fotoğrafı**: Kişi düzenlerken "📷 Resim Seç" ile fotoğraf ekleyin
3. **Etiketleme**: Kişileri kategorilere ayırmak için etiket kullanın
4. **Arama**: Üst kısımdaki arama kutusundan kişi bulun

### Telefon İşlemleri
- **Hemen Ara**: Kişiyi seçip "📞 Hemen Ara" ile direkt arayın
- **Telefon Uygulaması**: Numara telefon uygulamasında açılır
- **SMS**: Mesaj yazıp "✉️ SMS Gönder" ile SMS uygulamasını açın

### Uygulama Yönetimi
1. "📱 Uygulamalar" sekmesine geçin
2. "🔄 Yenile" ile uygulama listesini güncelleyin
3. Uygulamaya tıklayıp "🚀 Başlat" ile çalıştırın

## 📁 Dosya Yapısı

```
PyPIRT/
├── PyPIRT.py              # Ana uygulama dosyası
├── PyPIRT.settings.json   # Uygulama ayarları (İlk Kullanımda Gelir)
├── PyPIRT.log            # İşlem logları (İlk Kullanımda Gelir)
├── rehber.json           # Rehber verileri
├── resimler/             # Profil fotoğrafları
│   └── 112.jpg          # Örnek profil fotoğrafı
└── README.md            # Bu dosya
```

## ⚠️ Güvenlik Notları

- **Wi-Fi ADB** sadece güvendiğiniz ağlarda kullanın
- Kullanım sonrası ADB bağlantısını kapatmayı unutmayın
- Geliştirici seçeneklerini gerekmedikçe açık bırakmayın
- Bilinmeyen kaynaklardan APK yüklemeyin

## 🐛 Sorun Giderme

### Bağlantı Sorunları
```bash
# ADB servisini yeniden başlatın
adb kill-server
adb start-server

# Cihaz listesini kontrol edin
adb devices

# Bağlantıyı sıfırlayın
adb disconnect
adb connect <IP>:5555
```

### Yaygın Hatalar
- **"adb bulunamadı"**: Android Platform Tools PATH'e eklenmiş mi?
- **"Bağlantı reddedildi"**: Kablosuz ADB etkin mi?
- **"Cihaz yetkisiz"**: USB ile bağlanıp yetki verin
- **"Kütüphane eksik"**: `pip install customtkinter Pillow`

## 🔄 Güncelleme Notları

### v1.0 Özellikleri
- ✅ Temel rehber yönetimi
- ✅ Wi-Fi ADB desteği
- ✅ Arama ve SMS işlemleri
- ✅ Uygulama başlatma
- ✅ Profil fotoğrafı desteği
- ✅ Modern karanlık tema

## 📄 Lisans

Bu proje MIT lisansı altında yayınlanmıştır. Detaylar için `LICENSE` dosyasına bakın.

## 🤝 Katkıda Bulunma

1. Projeyi fork edin
2. Feature branch oluşturun (`git checkout -b feature/AmazingFeature`)
3. Değişikliklerinizi commit edin (`git commit -m 'Add some AmazingFeature'`)
4. Branch'inizi push edin (`git push origin feature/AmazingFeature`)
5. Pull Request oluşturun

## 📞 İletişim

Sorularınız için issue açabilir veya doğrudan iletişime geçebilirsiniz.

---

**⚡ PyPIRT ile Android cihazınızı masaüstünden kontrol edin!**