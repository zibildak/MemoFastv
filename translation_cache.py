"""
MEMOFAST - Kalıcı (Disk Tabanlı) Çeviri Önbelleği + Topluluk Paylaşımı

Amaç: Yazılımın tamamen ücretsiz kalması.
Bir kez çevrilen metin diske yazılır; aynı metin başka bir oyunda ya da
sonraki oturumda tekrar karşımıza çıktığında API'ye HİÇ istek atılmaz.

Topluluk paylaşımı:
- export_pack(): önbelleği tek tıkla sıkıştırılmış .mfcache paketine çevirir
- import_pack(): paylaşılan paketi SIKI doğrulamayla içe aktarır
- İçe aktarılan çeviriler AYRI dosyada tutulur → tek tıkla geri alınabilir
- Paket çalıştırılabilir kod içeremez: yalnızca metin→metin sözlüğü kabul edilir

Tüm servislerle (Google, DeepL, Gemini, Yerel AI) çalışır.
"""
import gzip
import json
import re
import threading
from pathlib import Path

from config import USER_DATA_PATH, Config
from logger import setup_logger

logger = setup_logger(__name__)

# Paket format tanımı
PACK_FORMAT = "mfcache1"
PACK_EXTENSION = ".mfcache"

# Doğrulama sınırları
MAX_PACK_ENTRIES = 500_000
MAX_KEY_LEN = 2000
MAX_VALUE_LEN = 4000

# Oltalama koruması: kaynakta olmayan link çeviriye eklenmişse at
_URL_RE = re.compile(r'(https?://|www\.)', re.IGNORECASE)
# Görünmez/kontrol karakterleri (\n ve \t hariç — oyun metinlerinde meşru)
_CTRL_RE = re.compile(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]')


class TranslationCache:
    """
    Dil çifti başına iki JSON dosyası:
      en-tr.json          → kullanıcının kendi ürettiği çeviriler
      en-tr.imported.json → topluluktan içe aktarılanlar (ayrı = silinebilir)

    - Thread-safe (paralel çeviri worker'ları aynı anda yazabilir)
    - Atomik kayıt (yarım dosya/bozulma olmaz)
    - Her 200 yeni kayıtta bir otomatik diske yazar
    - Kendi çeviriler her zaman içe aktarılanlardan ÖNCELİKLİDİR
    """

    MAX_ENTRIES = 200_000  # dosya başına üst sınır; en eski kayıtlar atılır

    def __init__(self, target_lang="tr", source_lang="en"):
        self.target_lang = target_lang
        self.source_lang = source_lang
        cache_dir = USER_DATA_PATH / ".cache" / "translations"
        cache_dir.mkdir(parents=True, exist_ok=True)
        self.file = cache_dir / f"{source_lang}-{target_lang}.json"
        self.imported_file = cache_dir / f"{source_lang}-{target_lang}.imported.json"
        self._lock = threading.Lock()
        self._dirty = 0
        self.data = self._load_file(self.file)
        self.imported = self._load_file(self.imported_file)
        total = len(self.data) + len(self.imported)
        if total:
            logger.info(f"Kalıcı çeviri önbelleği yüklendi: {len(self.data)} kendi + {len(self.imported)} topluluk kaydı")

    @staticmethod
    def _load_file(path):
        try:
            if path.exists():
                data = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    return data
        except Exception as e:
            logger.warning(f"Önbellek dosyası okunamadı ({path.name}), sıfırdan başlanıyor: {e}")
        return {}

    # ------------------------------------------------------------------ #
    #  Temel API                                                          #
    # ------------------------------------------------------------------ #
    def get(self, text):
        """Önbellekte varsa çeviriyi döndür (önce kendi, sonra topluluk)."""
        if not text:
            return None
        with self._lock:
            return self.data.get(text) or self.imported.get(text)

    def set(self, text, translated):
        """Yeni çeviriyi ekle. Kaynakla aynıysa (başarısız çeviri) eklemez."""
        if not text or not translated or text == translated:
            return
        with self._lock:
            self.data[text] = translated
            self._dirty += 1
            if self._dirty >= 200:
                self._save_locked()

    def save(self):
        """Bekleyen değişiklikleri diske yaz."""
        with self._lock:
            if self._dirty > 0:
                self._save_locked()

    def _save_locked(self):
        """(Kilit alınmışken çağrılır) Atomik yazma."""
        try:
            if len(self.data) > self.MAX_ENTRIES:
                excess = len(self.data) - self.MAX_ENTRIES
                for k in list(self.data.keys())[:excess]:
                    del self.data[k]
            self._atomic_write(self.file, self.data)
            self._dirty = 0
        except Exception as e:
            logger.error(f"Önbellek diske yazılamadı: {e}")

    @staticmethod
    def _atomic_write(path, data):
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        tmp.replace(path)

    def __len__(self):
        with self._lock:
            return len(self.data) + len(self.imported)

    # ------------------------------------------------------------------ #
    #  Topluluk Paylaşımı: Dışa Aktarma                                   #
    # ------------------------------------------------------------------ #
    def export_pack(self, out_path):
        """
        Önbelleği paylaşılabilir tek dosyaya (.mfcache, gzip) çevirir.

        Returns:
            (True, kayıt_sayısı) veya (False, hata_mesajı)
        """
        try:
            with self._lock:
                merged = dict(self.imported)
                merged.update(self.data)  # kendi çeviriler öncelikli

            if not merged:
                return False, "Önbellek boş — önce en az bir oyun çevirin."

            pack = {
                "format": PACK_FORMAT,
                "source_lang": self.source_lang,
                "target_lang": self.target_lang,
                "app_version": Config.VERSION,
                "count": len(merged),
                "entries": merged,
            }
            out_path = Path(out_path)
            # .gz uzantısı GitHub'a eklenti olarak yüklenebilir; ikisi de geçerli
            if out_path.suffix not in (PACK_EXTENSION, ".gz"):
                out_path = Path(str(out_path) + PACK_EXTENSION + ".gz")
            raw = json.dumps(pack, ensure_ascii=False).encode("utf-8")
            with gzip.open(out_path, "wb") as f:
                f.write(raw)
            logger.info(f"Çeviri paketi dışa aktarıldı: {out_path} ({len(merged)} kayıt)")
            return True, len(merged)
        except Exception as e:
            logger.error(f"Dışa aktarma hatası: {e}")
            return False, str(e)

    # ------------------------------------------------------------------ #
    #  Topluluk Paylaşımı: İçe Aktarma (SIKI DOĞRULAMA)                   #
    # ------------------------------------------------------------------ #
    @staticmethod
    def _read_pack_bytes(raw_bytes):
        """Gzip veya düz JSON baytlarını çözer."""
        try:
            raw_bytes = gzip.decompress(raw_bytes)
        except (OSError, gzip.BadGzipFile):
            pass  # düz JSON olabilir
        return json.loads(raw_bytes.decode("utf-8"))

    @classmethod
    def validate_pack(cls, pack, expected_source=None, expected_target=None):
        """
        Paketi güvenlik süzgecinden geçirir.

        Kurallar:
        - Yalnızca {metin: metin} girdileri (kod/nesne/binari kabul edilmez)
        - Uzunluk sınırları, kontrol karakteri temizliği
        - Oltalama koruması: kaynak metinde olmayan URL çeviriye eklenmişse atılır
        - Dil çifti uyuşmazlığında reddedilir

        Returns:
            (temiz_girdiler: dict, atlanan_sayısı: int, hata: str|None)
        """
        if not isinstance(pack, dict):
            return {}, 0, "Geçersiz paket: JSON nesnesi değil."

        # Eski/düz format desteği: doğrudan {kaynak: çeviri} sözlüğü
        entries = pack.get("entries") if pack.get("format") == PACK_FORMAT else pack

        if not isinstance(entries, dict):
            return {}, 0, "Geçersiz paket: çeviri listesi bulunamadı."
        if len(entries) > MAX_PACK_ENTRIES:
            return {}, 0, f"Paket çok büyük ({len(entries)} kayıt, sınır {MAX_PACK_ENTRIES})."

        if pack.get("format") == PACK_FORMAT:
            if expected_source and pack.get("source_lang") and pack["source_lang"] != expected_source:
                return {}, 0, f"Dil uyuşmazlığı: paket {pack.get('source_lang')} kaynaklı, sizin ayarınız {expected_source}."
            if expected_target and pack.get("target_lang") and pack["target_lang"] != expected_target:
                return {}, 0, f"Dil uyuşmazlığı: paket {pack.get('target_lang')} hedefli, sizin ayarınız {expected_target}."

        clean = {}
        skipped = 0
        for k, v in entries.items():
            # 1) Yalnızca metin→metin
            if not isinstance(k, str) or not isinstance(v, str):
                skipped += 1
                continue
            # 2) Boş/aynı/aşırı uzun
            if not k.strip() or not v.strip() or k == v:
                skipped += 1
                continue
            if len(k) > MAX_KEY_LEN or len(v) > MAX_VALUE_LEN:
                skipped += 1
                continue
            # 3) Kontrol karakterlerini temizle
            k2 = _CTRL_RE.sub("", k)
            v2 = _CTRL_RE.sub("", v)
            # 4) Oltalama koruması: kaynakta link yokken çeviriye link eklenmişse atla
            if _URL_RE.search(v2) and not _URL_RE.search(k2):
                skipped += 1
                continue
            clean[k2] = v2

        return clean, skipped, None

    def import_pack(self, pack_path):
        """
        Paylaşılan çeviri paketini doğrulayıp 'topluluk' katmanına ekler.
        Kullanıcının kendi çevirilerinin ÜZERİNE YAZMAZ.

        Returns:
            (True, {"added": x, "skipped": y, "total": z}) veya (False, hata)
        """
        try:
            raw = Path(pack_path).read_bytes()
            if len(raw) > 100 * 1024 * 1024:
                return False, "Dosya çok büyük (100 MB sınırı)."
            pack = self._read_pack_bytes(raw)
        except Exception as e:
            return False, f"Dosya okunamadı veya geçerli bir çeviri paketi değil: {e}"

        clean, skipped, err = self.validate_pack(
            pack, expected_source=self.source_lang, expected_target=self.target_lang
        )
        if err:
            return False, err
        if not clean:
            return False, f"Pakette geçerli çeviri bulunamadı ({skipped} kayıt güvenlik süzgecine takıldı)."

        with self._lock:
            added = 0
            for k, v in clean.items():
                if k not in self.imported:
                    added += 1
                self.imported[k] = v
            if len(self.imported) > self.MAX_ENTRIES:
                excess = len(self.imported) - self.MAX_ENTRIES
                for key in list(self.imported.keys())[:excess]:
                    del self.imported[key]
            self._atomic_write(self.imported_file, self.imported)

        logger.info(f"Çeviri paketi içe aktarıldı: {added} yeni, {skipped} süzgece takıldı")
        return True, {"added": added, "skipped": skipped, "total": len(clean)}

    def clear_imported(self):
        """Topluluktan içe aktarılan TÜM çevirileri siler (kendi çeviriler korunur)."""
        with self._lock:
            count = len(self.imported)
            self.imported = {}
            try:
                if self.imported_file.exists():
                    self.imported_file.unlink()
            except Exception as e:
                logger.error(f"İçe aktarılanlar silinemedi: {e}")
                return 0
        return count

    # ------------------------------------------------------------------ #
    #  Topluluk Sunucusundan Otomatik İndirme (tek tık)                   #
    # ------------------------------------------------------------------ #
    def fetch_community(self, index_url=None, progress_callback=None):
        """
        Resmi topluluk havuzundan çeviri paketlerini indirir ve içe aktarır.
        Kullanıcı hiçbir teknik ayrıntı görmez — index URL'i config'de tanımlıdır.

        Index formatı (JSON):
            {"packs": [{"name": "...", "source_lang": "en", "target_lang": "tr",
                        "url": "https://.../paket.mfcache"}]}

        Returns:
            (True, {"packs": n, "added": x, "skipped": y}) veya (False, hata)
        """
        import urllib.request

        url = index_url or getattr(Config, "COMMUNITY_CACHE_URL", "")
        if not url:
            return False, "Topluluk havuzu henüz yayında değil."

        try:
            req = urllib.request.Request(url, headers={"User-Agent": "MemoFast"})
            with urllib.request.urlopen(req, timeout=30) as r:
                index = json.loads(r.read().decode("utf-8"))
        except Exception as e:
            return False, f"Topluluk havuzuna ulaşılamadı: {e}"

        packs = index.get("packs", []) if isinstance(index, dict) else []
        matching = [
            p for p in packs
            if isinstance(p, dict) and p.get("url")
            and p.get("source_lang", self.source_lang) == self.source_lang
            and p.get("target_lang", self.target_lang) == self.target_lang
        ]
        if not matching:
            return False, "Dil çiftinize uygun topluluk paketi bulunamadı."

        total_added = 0
        total_skipped = 0
        ok_packs = 0
        for i, p in enumerate(matching):
            try:
                if progress_callback:
                    progress_callback(f"📥 İndiriliyor ({i+1}/{len(matching)}): {p.get('name', 'paket')}")
                req = urllib.request.Request(p["url"], headers={"User-Agent": "MemoFast"})
                with urllib.request.urlopen(req, timeout=60) as r:
                    raw = r.read(100 * 1024 * 1024)
                pack = self._read_pack_bytes(raw)
                clean, skipped, err = self.validate_pack(
                    pack, expected_source=self.source_lang, expected_target=self.target_lang
                )
                if err or not clean:
                    total_skipped += skipped
                    continue
                with self._lock:
                    for k, v in clean.items():
                        if k not in self.imported:
                            total_added += 1
                        self.imported[k] = v
                    self._atomic_write(self.imported_file, self.imported)
                total_skipped += skipped
                ok_packs += 1
            except Exception as e:
                logger.warning(f"Topluluk paketi indirilemedi ({p.get('name')}): {e}")

        if ok_packs == 0:
            return False, "Paketler indirilemedi veya doğrulamadan geçemedi."
        return True, {"packs": ok_packs, "added": total_added, "skipped": total_skipped}
