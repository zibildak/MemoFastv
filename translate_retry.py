"""
MEMOFAST - Ortak Çeviri Dayanıklılık Katmanı

Neden var:
  1) deep_translator'ın GoogleTranslator'ı THREAD-SAFE DEĞİL. translate() her çağrıda
     paylaşılan self._url_params sözlüğüne yazıyor. Tek nesne N thread'e paylaştırılınca
     thread'ler birbirinin 'q' parametresini eziyor.
     Ölçüm (120 istek / 16 işçi): paylaşımlı nesne 65 hata, thread başına nesne 15 hata.

  2) Google'ın ücretsiz uç noktası aşırı yüklendiğinde 429 yerine "sonuç kabı olmayan
     HTML" döndürüyor; deep_translator bunu TranslationNotFound olarak fırlatıyor.
     Bu GEÇİCİ bir durum, ama retry olmadığı için satır KALICI olarak çevrilmemiş kalıyordu.
     Ölçüm (300 gerçek satır): tek deneme 104 hata (%35), 4 denemeli backoff 8 hata (%2.7).

Kullanım:
    rt = ResilientTranslator(translator, source_lang="en", target_lang="tr")
    sonuc = rt.translate(metin)      # başarısızsa None döner, ASLA orijinali döndürmez
    ...
    print(rt.report())               # "N satır çevrilemedi" dürüst raporu
"""
import threading
import time
from random import uniform

from logger import setup_logger

logger = setup_logger(__name__)

# Google'ın geçici throttle yanıtını atlatmak için deneme sayısı ve bekleme tabanı.
# Beklemeler: 0.6 / 1.2 / 2.4 sn (+ 0-0.4 sn rastgele dağıtma)
TRANSLATE_MAX_RETRIES = 4
TRANSLATE_BACKOFF_BASE = 0.6

# deep_translator, çeviri kaynakla aynı çıktığında (özel isim, saf tag, "- - - -" gibi
# noktalama satırları) fonksiyon sonuna düşüp None döner. Bu KALICI bir durumdur;
# 4 kez denemek boşuna istek olur.
NONE_MAX_ATTEMPTS = 2

# Bu motorlar tek nesne olarak paylaşılmalı: model RAM'de tutuluyor ya da oturum
# durumu var, her thread için yeniden kurmak hem pahalı hem yanlış.
SHARED_CLASSES = ("LocalAIEngine", "GeminiTranslator")


class ResilientTranslator:
    """
    Herhangi bir çevirmen nesnesini sarar ve iki şeyi garanti eder:
      - her thread kendi çevirmen örneğini kullanır (paylaşım yarışı yok)
      - geçici hatalar üstel backoff ile yeniden denenir

    Sayaçları (success_count / failure_count / retry_rescued) thread-safe tutar,
    böylece iş bitince kullanıcıya dürüst bir rapor verilebilir.
    """

    def __init__(self, translator, source_lang="en", target_lang="tr"):
        self._base = translator
        self._source_lang = source_lang
        self._target_lang = target_lang
        self._tls = threading.local()
        self._lock = threading.Lock()

        self.class_name = translator.__class__.__name__ if translator is not None else ""
        # Paylaşılması gerekenler ve None dışındaki her şey thread başına kurulur
        self._share = (translator is None) or (self.class_name in SHARED_CLASSES)

        self.success_count = 0
        self.failure_count = 0
        self.retry_rescued = 0

    def _instance(self):
        """Bu thread'e ait çevirmen örneğini döndürür (gerekiyorsa kurar)."""
        if self._share:
            return self._base
        if getattr(self._tls, "tr", None) is None:
            try:
                self._tls.tr = self._base.__class__(
                    source=self._source_lang, target=self._target_lang
                )
            except Exception as e:
                # Kurulamadıysa paylaşımlıya düş: yarış riski var ama çeviri hiç durmasın
                logger.debug(f"Thread'e ozel cevirmen kurulamadi, paylasimliya dusuldu: {e}")
                self._tls.tr = self._base
        return self._tls.tr

    def translate(self, text):
        """
        Metni çevirir. Başarısızsa None döner.

        ÖNEMLİ: başarısızlıkta orijinal metni DÖNDÜRMEZ. Çağıran taraf böylece
        "çevrildi" ile "çevrilemedi"yi ayırt edebilir; eskiden orijinali döndüren
        kod yüzünden İngilizce kalan satırlar başarı sayılıyordu.
        """
        if self._base is None or not text:
            return None

        tr = self._instance()

        for attempt in range(TRANSLATE_MAX_RETRIES):
            try:
                if self.class_name in SHARED_CLASSES:
                    result = tr.translate(text, target_lang=self._target_lang)
                else:
                    result = tr.translate(text)

                if result:
                    with self._lock:
                        self.success_count += 1
                        if attempt:
                            self.retry_rescued += 1
                    return result

                # None döndü: çevrilebilir bir metin değil, ısrar etme
                if attempt + 1 >= NONE_MAX_ATTEMPTS:
                    break
            except Exception as e:
                if attempt == TRANSLATE_MAX_RETRIES - 1:
                    logger.debug(f"Cevrilemedi ({TRANSLATE_MAX_RETRIES} deneme): {type(e).__name__}")

            if attempt < TRANSLATE_MAX_RETRIES - 1:
                time.sleep((TRANSLATE_BACKOFF_BASE * (2 ** attempt)) + uniform(0, 0.4))

        with self._lock:
            self.failure_count += 1
        return None

    def report(self, total=None):
        """İş bitiminde kullanıcıya gösterilecek dürüst özet metnini üretir."""
        total = total or (self.success_count + self.failure_count)
        if not total:
            return ""
        if self.failure_count:
            oran = self.failure_count / total * 100
            msg = (f"⚠️ {self.failure_count} satır çevrilemedi (%{oran:.1f}). "
                   f"Bu satırlar İngilizce kalacak. Hız ayarını düşürüp tekrar "
                   f"çalıştırırsanız sadece eksikler denenir.")
            logger.warning(f"Cevrilemedi: {self.failure_count}/{total} satir")
        else:
            msg = f"✅ {total} satırın tamamı çevrildi (hata yok)."
        if self.retry_rescued:
            msg += f" ({self.retry_rescued} satır yeniden deneme ile kurtarıldı.)"
        return msg
