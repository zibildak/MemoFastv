# 🤝 MemoFast'a Katkıda Bulunma Rehberi / Contributing Guide

[Türkçe](#türkçe) | [English](#english)

---

## Türkçe

MemoFast'a katkıda bulunmak istediğin için teşekkürler! 🎉

### 🚀 Nasıl Katkıda Bulunurum?

1. Bu repoyu **Fork**'layın (sağ üstteki Fork butonu)
2. Kendi fork'unuzda yeni bir branch oluşturun:
   ```bash
   git checkout -b ozellik/yeni-ozellik-adi
   ```
3. Değişikliklerinizi yapın ve commit'leyin:
   ```bash
   git commit -m "Yeni özellik: Açıklama"
   ```
4. Branch'inizi push'layın:
   ```bash
   git push origin ozellik/yeni-ozellik-adi
   ```
5. GitHub'da **Pull Request** açın

### 📋 Kurallar

- **Bir PR = Bir özellik/düzeltme.** Birden fazla şeyi aynı PR'da yapmayın.
- **Mevcut özellikleri silmeyin.** Hata varsa düzeltin, silmeyin.
- **Türkçe karakter desteğini bozmayın.** Bu uygulama Türkçe odaklıdır.
- **Test edin.** Değişikliğinizin mevcut özellikleri bozmadığından emin olun.

### 🎯 Katkı Yapılabilecek Alanlar

- 🐛 **Bug düzeltme** → Hata buldunuz mu? Düzeltin!
- 🌍 **Yeni çeviri motoru** → Yeni bir çeviri API'si entegrasyonu
- 🎮 **Yeni oyun motoru desteği** → Godot, RPG Maker vb.
- ⚡ **Performans iyileştirme** → Daha hızlı çeviri, daha az bellek kullanımı
- 🎨 **UI iyileştirme** → Daha güzel arayüz
- 📖 **Dokümantasyon** → README, wiki, kod yorumları
- 🌐 **Çoklu dil desteği** → Arayüzün farklı dillere çevrilmesi

### 🏗️ Proje Yapısı

| Dosya | Görev |
|-------|-------|
| `memofast_gui.py` | Ana GUI uygulaması |
| `unreal_manager.py` | Unreal Engine çeviri |
| `unity_manager.py` | Unity Engine çeviri |
| `cobra_manager.py` | Cobra Engine çeviri |
| `translator_manager.py` | BepInEx/MelonLoader kurulum |
| `scanner.py` | Oyun tarayıcı |
| `screen_translator.py` | OCR ekran çeviri |
| `config.py` | Ayarlar ve sabitler |

### 🛠️ Geliştirme Ortamı

```bash
# Repoyu klonla
git clone https://github.com/KULLANICI_ADIN/MemoFastv.git
cd MemoFastv

# Bağımlılıkları kur
pip install -r requirements.txt

# Çalıştır
python memofast_gui.py
```

### 🐛 Bug Bildirme

GitHub'da **Issue** açarak bug bildirebilirsiniz:
1. **Issues** sekmesine gidin
2. **New Issue** tıklayın
3. Şunları belirtin:
   - Ne olması gerekiyordu?
   - Ne oldu?
   - Hangi oyunu/motoru kullanıyordunuz?
   - Hata mesajı varsa ekran görüntüsü

---

## English

Thanks for wanting to contribute to MemoFast! 🎉

### 🚀 How to Contribute

1. **Fork** this repository
2. Create a new branch:
   ```bash
   git checkout -b feature/your-feature-name
   ```
3. Make your changes and commit:
   ```bash
   git commit -m "Feature: Description"
   ```
4. Push your branch:
   ```bash
   git push origin feature/your-feature-name
   ```
5. Open a **Pull Request** on GitHub

### 📋 Rules

- **One PR = One feature/fix.** Don't mix multiple changes.
- **Don't remove existing features.** Fix bugs, don't delete functionality.
- **Don't break Turkish character support.** This app is Turkish-focused.
- **Test your changes.** Make sure existing features still work.

### 🎯 Areas for Contribution

- 🐛 **Bug fixes**
- 🌍 **New translation engines** → Integrate new translation APIs
- 🎮 **New game engine support** → Godot, RPG Maker, etc.
- ⚡ **Performance improvements** → Faster translation, less memory usage
- 🎨 **UI improvements** → Better interface design
- 📖 **Documentation** → README, wiki, code comments
- 🌐 **Localization** → Translate the UI to other languages

### 🐛 Reporting Bugs

Open a GitHub **Issue** with:
- What should have happened?
- What actually happened?
- Which game/engine were you using?
- Screenshot of error message (if any)

---

<p align="center">Her katkı değerlidir! / Every contribution matters! ❤️</p>
