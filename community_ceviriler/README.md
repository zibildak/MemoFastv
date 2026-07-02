# 🌐 MemoFast Topluluk Çeviri Havuzu

Bu klasör, MemoFast kullanıcılarının paylaştığı **hazır çeviri paketlerini** barındırır.
Uygulama içindeki **Ayarlar → Topluluk Çeviri Paylaşımı → 🌐 Topluluk Çevirilerini İndir**
butonu bu klasördeki `index.json` dosyasını okur ve paketleri otomatik indirir.

## 📤 Paket nasıl paylaşılır? (Kullanıcılar için)

1. MemoFast'te **Ayarlar → Topluluk Çeviri Paylaşımı → 📤 Paketi Dışa Aktar** deyin.
2. Oluşan `.mfcache.gz` dosyasını bu repoya **Issue** olarak açıp sürükleyin:
   👉 [Yeni paket gönder](https://github.com/zibildak/MemoFastv/issues/new?title=%5B%C3%87eviri%20Paketi%5D%20Oyun%20Ad%C4%B1&body=Oyun%3A%20...%0AKaynak%20dil%3A%20en%0AHedef%20dil%3A%20tr%0A%0APaket%20dosyas%C4%B1n%C4%B1%20buraya%20s%C3%BCr%C3%BCkleyin.)
3. Paket incelendikten sonra havuza eklenir ve herkes tek tıkla indirebilir.

## 🔒 Güvenlik

- Paketler **yalnızca metin** içerir (kaynak metin → çeviri eşlemesi), kod çalıştıramaz.
- Uygulama her paketi içe aktarmadan önce güvenlik süzgecinden geçirir:
  metin-dışı girdiler, şüpheli linkler ve bozuk kayıtlar otomatik ayıklanır.
- Havuza eklenen paketler proje sahibi tarafından gözden geçirilir.

## 🛠️ index.json formatı (Yöneticiler için)

```json
{
    "packs": [
        {
            "name": "Örnek Oyun Çevirisi",
            "source_lang": "en",
            "target_lang": "tr",
            "url": "https://raw.githubusercontent.com/zibildak/MemoFastv/main/community_ceviriler/paketler/ornek.mfcache.gz"
        }
    ]
}
```

Yeni paket eklemek için: dosyayı `paketler/` klasörüne koyun ve `index.json`'a
bir kayıt ekleyin. Uygulama, kullanıcının dil çiftine uyan paketleri otomatik indirir.
