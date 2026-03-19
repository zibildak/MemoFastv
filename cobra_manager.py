"""
MemoFast - Cobra Engine Lokalizasyon Yöneticisi
================================================
Frontier Developments'ın Cobra Engine oyunları için çeviri boru hattı.

Desteklenen oyunlar:
  - Planet Zoo
  - Jurassic World Evolution 1/2/3
  - Planet Coaster 1/2
  - RollerCoaster Tycoon 3
  - Elite Dangerous ve diğer Cobra tabanlı oyunlar

Dosya yapısı:
  [Oyun]/win64/ovldata/loc.ovl  → Dil metinleri

Akış:
  loc.ovl  → [Çıkar] → loc.csv → [Çevir] → loc_TR.csv → [Paketle] → loc_TR.ovl → [Kopyala]

Notlar:
  - cobra-tools Python kütüphanesi files/tools/cobra/ klasöründe olmalı
  - Yoksa basit binary ayrıştırıcı (fallback) kullanılır
"""

import os
import re
import csv
import sys
import time
import shutil
import struct
import requests
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from random import uniform
from config import Config
from logger import setup_logger

logger = setup_logger(__name__)

# --- Cobra-tools kütüphanesi yükleme (opsiyonel) ---
COBRA_TOOLS_PATH = Config.BASE_PATH / "files" / "tools" / "cobra"
_cobra_available = False

if COBRA_TOOLS_PATH.exists():
    sys.path.insert(0, str(COBRA_TOOLS_PATH))
    try:
        # cobra-tools modüllerini yüklemeyi dene
        import ovl_tool  # noqa: F401
        _cobra_available = True
        logger.info("cobra-tools kütüphanesi yüklendi.")
    except ImportError:
        logger.warning("cobra-tools klasörü var ama import edilemedi. Fallback parser kullanılacak.")

# --- Çeviri kütüphaneleri ---
try:
    from deep_translator import GoogleTranslator, DeepL
except ImportError:
    GoogleTranslator = None
    DeepL = None

# --- Unreal Manager'dan ortak araçları al ---
try:
    from unreal_manager import GeminiTranslator, VariableProtector, apply_turkish_correction
except ImportError:
    GeminiTranslator = None
    VariableProtector = None
    apply_turkish_correction = lambda x: x  # noqa: E731


class CobraManager:
    """
    Cobra Engine Lokalizasyon Yöneticisi.
    Unreal Manager ile aynı arayüzü kullanır (translate_game / process_game).
    """

    TOOLS_PATH = Config.BASE_PATH / "files" / "tools" / "cobra"

    # ------------------------------------------------------------------ #
    #  Araç Hazır Mı?                                                      #
    # ------------------------------------------------------------------ #
    @staticmethod
    def is_ready():
        """cobra-tools klasörünün var olup olmadığını kontrol et (zorunlu değil)."""
        return True  # Fallback parser her zaman çalışır

    # ------------------------------------------------------------------ #
    #  OVL Dosyası Bulma                                                   #
    # ------------------------------------------------------------------ #
    # İngilizce klasör öncelik listesi (küçük harf karşılaştırma yapılır)
    _ENGLISH_KEYWORDS = ("english", "en_us", "en_gb", "eng", "/en/")

    @staticmethod
    def find_loc_ovl(game_path, progress_callback=None):
        """
        Oyun klasöründe loc.ovl dosyasını bul.

        Öncelik sırası:
          1. win64/ovldata/loc.ovl                   (standart Cobra konumu)
          2. win64/ovldata/**/loc.ovl - English önce (alt klasörler - dil öncelikli)
          3. **/loc.ovl               - English önce (geniş arama - dil öncelikli)
        """
        game_path = Path(game_path)
        if game_path.is_file():
            game_path = game_path.parent

        # Standart konum (dil alt klasörü olmayan)
        standard = game_path / "win64" / "ovldata" / "loc.ovl"
        if standard.exists():
            if progress_callback:
                progress_callback(f"✅ loc.ovl bulundu: {standard}")
            return standard

        def _sort_english_first(paths):
            """İngilizce yolu içerenleri listeye başa taşır."""
            english = []
            others  = []
            for p in paths:
                lower = str(p).lower()
                if any(kw in lower for kw in CobraManager._ENGLISH_KEYWORDS):
                    english.append(p)
                else:
                    others.append(p)
            return english + others

        # win64/ovldata altında recursive ara
        ovldata = game_path / "win64" / "ovldata"
        candidates = []
        if ovldata.exists():
            candidates += _sort_english_first(ovldata.rglob("loc.ovl"))

        # Geniş arama (ovldata dışı)
        all_found = list(game_path.rglob("loc.ovl"))
        candidates += _sort_english_first(all_found)

        for c in candidates:
            if c.exists():
                if progress_callback:
                    progress_callback(f"✅ loc.ovl bulundu: {c}")
                return c

        if progress_callback:
            progress_callback("❌ loc.ovl bulunamadı!")
        return None

    # ------------------------------------------------------------------ #
    #  OVL → CSV (Çıkarma)                                                 #
    # ------------------------------------------------------------------ #
    @staticmethod
    def extract_ovl_to_csv(ovl_path, output_csv=None, progress_callback=None):
        """
        loc.ovl dosyasından metin stringlerini CSV'ye çıkarır.

        Önce cobra-tools kullanmayı dener, başarısız olursa
        basit binary tarayıcı (fallback) kullanır.

        CSV Formatı: key, source_text, target_text
        """
        ovl_path = Path(ovl_path)
        if output_csv is None:
            output_csv = ovl_path.with_name("loc_extracted.csv")
        else:
            output_csv = Path(output_csv)

        if progress_callback:
            progress_callback(f"📤 {ovl_path.name} çıkarılıyor...")

        rows = []

        # --- Yöntem 1: cobra-tools ---
        if _cobra_available:
            try:
                rows = CobraManager._extract_via_cobra_tools(ovl_path, progress_callback)
                if rows:
                    if progress_callback:
                        progress_callback(f"✅ cobra-tools ile {len(rows)} string çıkarıldı.")
            except Exception as e:
                if progress_callback:
                    progress_callback(f"⚠️ cobra-tools hatası: {e}. Fallback deneniyor...")
                rows = []

        # --- Yöntem 2: Binary Tarayıcı (Fallback) ---
        if not rows:
            if progress_callback:
                mb = Path(ovl_path).stat().st_size / (1024 * 1024)
                progress_callback(f"⚙️ Regex parser ile taranıyor... ({mb:.1f} MB, lütfen bekleyin)")
            try:
                rows = CobraManager._extract_fallback(ovl_path, progress_callback)
                if progress_callback:
                    progress_callback(f"✅ Fallback parser ile {len(rows)} string çıkarıldı.")
            except Exception as e:
                raise Exception(f"OVL çıkarma başarısız: {e}")

        if not rows:
            raise Exception(
                "OVL dosyasından hiç metin çıkarılamadı!\n"
                "Dosya şifreli veya desteklenmiyor olabilir."
            )

        # CSV'ye yaz
        with open(output_csv, "w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["key", "source", "target"])
            writer.writerows(rows)

        if progress_callback:
            progress_callback(f"📄 CSV oluşturuldu: {output_csv} ({len(rows)} satır)")
        return output_csv, rows

    @staticmethod
    def _extract_via_cobra_tools(ovl_path, progress_callback=None):
        """cobra-tools kütüphanesiyle OVL'den string çıkar."""
        rows = []
        try:
            import ovl_tool
            ovl = ovl_tool.OvlFile()
            ovl.load(str(ovl_path))

            for entry in ovl.entries:
                # Lokalizasyon verisi genellikle .fct veya .motiongraph uzantılı olur
                # ya da doğrudan string tablosu olarak gelir
                if hasattr(entry, "text") and entry.text:
                    key = getattr(entry, "name", f"str_{len(rows)}")
                    rows.append([key, entry.text, ""])
        except Exception as e:
            raise e
        return rows

    @staticmethod
    def _extract_fallback(ovl_path, progress_callback=None):
        """
        Regex tabanlı hızlı binary tarayıcı.
        OVL içindeki UTF-16LE ve UTF-8 stringlerini bulur.
        cobra-tools yoksa ya da başarısız olursa kullanılır.
        """
        MIN_LEN = 4
        MAX_LEN = 512
        found_strings = set()

        try:
            with open(ovl_path, "rb") as f:
                data = f.read()

            # --- 1. UTF-16LE regex (en hızlı yöntem) ---
            # Geçerli UTF-16LE null-terminated string pattern
            # En az MIN_LEN karakter, sadece yazdırılabilir BMP aralığı
            pattern_16 = re.compile(
                b"(?:[\x20-\x7e\x00-\x00]|[\x80-\xff][\x00-\xff]){" + str(MIN_LEN).encode() + b"," + str(MAX_LEN).encode() + b"}\x00\x00"
            )
            for m in pattern_16.finditer(data):
                raw = m.group()
                # Çift-bayt hizalamasını kontrol et
                try:
                    decoded = raw.rstrip(b"\x00").decode("utf-16-le", errors="ignore").strip()
                    if MIN_LEN <= len(decoded) <= MAX_LEN and any(c.isalpha() for c in decoded):
                        found_strings.add(decoded)
                except Exception:
                    pass

            if progress_callback and found_strings:
                progress_callback(f"🔍 UTF-16LE: {len(found_strings)} string bulundu, UTF-8 taranıyor...")

            # --- 2. UTF-8 / ASCII regex (ikincil) ---
            pattern_8 = re.compile(b"[\x20-\x7e]{" + str(MIN_LEN).encode() + b"," + str(MAX_LEN).encode() + b"}")
            for m in pattern_8.finditer(data):
                try:
                    decoded = m.group().decode("utf-8", errors="ignore").strip()
                    if MIN_LEN <= len(decoded) <= MAX_LEN and any(c.isalpha() for c in decoded):
                        found_strings.add(decoded)
                except Exception:
                    pass

            if not found_strings:
                raise Exception(
                    "OVL dosyasından hiç metin çıkarılamadı.\n"
                    "Bu dosya özel formatlı olabilir. cobra-tools kütüphanesi gerekli."
                )

            # Satır oluştur
            rows = [[f"str_{idx:04d}", s, ""] for idx, s in enumerate(sorted(found_strings))]

        except Exception as e:
            raise Exception(f"Binary tarayıcı hatası: {e}")

        return rows

    # ------------------------------------------------------------------ #
    #  Çeviri                                                              #
    # ------------------------------------------------------------------ #
    @staticmethod
    def translate_csv(
        csv_path,
        service="google",
        api_key="",
        max_workers=10,
        progress_callback=None,
        progress_max_callback=None,
        progress_bar_callback=None,
        target_lang="tr",
    ):
        """
        CSV dosyasındaki source sütununu çevirerek target sütununu doldurur.
        Unreal Manager ile aynı turbo+resume mantığını kullanır.
        """
        csv_path = Path(csv_path)
        translated_csv = csv_path.with_name(csv_path.stem + f"_{target_lang.upper()}.csv")

        # Resume verisi yükle
        resume_dict = {}
        if translated_csv.exists():
            try:
                with open(translated_csv, "r", encoding="utf-8", newline="") as f:
                    for row in csv.reader(f):
                        if len(row) >= 3 and row[1] and row[2]:
                            resume_dict[row[1]] = row[2]
                if progress_callback:
                    progress_callback(f"♻️ {len(resume_dict)} satır resume'dan yüklendi.")
            except Exception as e:
                logger.debug("Resume yükleme hatası: %s", e)

        # CSV oku
        rows = []
        with open(csv_path, "r", encoding="utf-8", newline="") as f:
            rows = list(csv.reader(f))

        if progress_callback:
            progress_callback(f"📊 {len(rows) - 1} satır okundu.")

        # Çevirici başlat (Unreal ile aynı mantık)
        translator = None
        if service == "deepl" and api_key:
            try:
                use_lang = target_lang.upper()
                if target_lang.lower() == "pt":
                    use_lang = "PT-BR"
                is_free = api_key.strip().endswith(":fx")
                translator = DeepL(api_key=api_key, source="en", target=use_lang, use_free_api=is_free)
                if progress_callback:
                    progress_callback("🚀 DeepL API kullanılıyor...")
            except Exception as e:
                if progress_callback:
                    progress_callback(f"⚠️ DeepL hatası: {e}. Google'a geçiliyor...")
                translator = GoogleTranslator(source="auto", target=target_lang) if GoogleTranslator else None
        elif service == "gemini" and api_key and GeminiTranslator:
            try:
                translator = GeminiTranslator(api_key, target_lang=target_lang)
                if progress_callback:
                    progress_callback("✨ Gemini AI kullanılıyor...")
            except Exception:
                translator = GoogleTranslator(source="auto", target=target_lang) if GoogleTranslator else None
        else:
            translator = GoogleTranslator(source="auto", target=target_lang) if GoogleTranslator else None

        # İş listesi
        work_items = []
        for i, row in enumerate(rows):
            if i == 0:
                continue  # Header
            while len(row) < 3:
                row.append("")
            source = row[1]
            if not source or len(source) < 2:
                continue
            if source in resume_dict:
                rows[i][2] = resume_dict[source]
                continue
            work_items.append((i, source))

        total = len(work_items)
        if progress_max_callback:
            progress_max_callback(total)
        if progress_callback:
            progress_callback(f"🚀 TURBO MOD: {total} satır {max_workers} işçi ile çevriliyor...")

        def translate_worker(idx, text):
            try:
                if service == "google":
                    time.sleep(uniform(0.1, 0.4))
                protector = VariableProtector() if VariableProtector else None
                protected = protector.protect(text) if protector else text
                result = None
                if translator:
                    result = translator.translate(protected)
                else:
                    try:
                        url = "https://translate.googleapis.com/translate_a/single"
                        params = {"client": "gtx", "sl": "auto", "tl": target_lang, "dt": "t", "q": protected}
                        r = requests.get(url, params=params, timeout=5)
                        if r.status_code == 200:
                            result = r.json()[0][0][0]
                    except Exception:
                        pass
                if result:
                    if protector:
                        result = protector.restore(result)
                    if target_lang == "tr":
                        result = apply_turkish_correction(result)
                return idx, result
            except Exception:
                return idx, None

        completed = 0
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_map = {executor.submit(translate_worker, idx, txt): idx for idx, txt in work_items}
            for future in as_completed(future_map):
                try:
                    r_idx, r_text = future.result()
                    if r_text and len(rows[r_idx]) > 2:
                        rows[r_idx][2] = r_text
                except Exception:
                    pass
                completed += 1
                if progress_bar_callback:
                    progress_bar_callback(completed)
                if completed % 20 == 0 or completed == total:
                    pct = int((completed / total) * 100) if total else 100
                    if progress_callback:
                        progress_callback(f"⚡ Çevriliyor... ({completed}/{total}) - %{pct}")

        # Çevrilen CSV'yi yaz
        cleaned = []
        for row in rows:
            cleaned.append([str(c).replace("\n", " ").replace("\r", "").strip() for c in row])

        with open(translated_csv, "w", encoding="utf-8", newline="") as f:
            csv.writer(f, quoting=csv.QUOTE_MINIMAL).writerows(cleaned)

        # Dump
        try:
            dump = Config.BASE_PATH / "Cobra_Translated_Dump.csv"
            shutil.copy2(translated_csv, dump)
        except Exception:
            pass

        if progress_callback:
            progress_callback(f"✅ Çeviri tamamlandı: {translated_csv}")
        return translated_csv

    # ------------------------------------------------------------------ #
    #  CSV → OVL (Paketleme)                                               #
    # ------------------------------------------------------------------ #
    @staticmethod
    def repack_ovl(original_ovl, translated_csv, output_ovl=None, progress_callback=None):
        """
        Çevrilmiş CSV'yi OVL dosyasına geri yazar.

        Strateji:
          1. cobra-tools varsa → doğrudan OVL API ile yaz
          2. Yoksa → orijinal OVL'i kopyala, string'leri binary olarak patch et
        """
        original_ovl = Path(original_ovl)
        translated_csv = Path(translated_csv)

        if output_ovl is None:
            # Orijinalin yanına _TR.ovl olarak kaydet
            output_ovl = original_ovl.with_name(f"loc_{translated_csv.stem.split('_')[-1]}.ovl")
        else:
            output_ovl = Path(output_ovl)

        if progress_callback:
            progress_callback("📥 OVL dosyası paketleniyor...")

        # Çeviri haritasını oku
        translation_map = {}
        with open(translated_csv, "r", encoding="utf-8", newline="") as f:
            reader = csv.reader(f)
            for i, row in enumerate(reader):
                if i == 0:
                    continue  # Header
                if len(row) >= 3 and row[1] and row[2]:
                    translation_map[row[1]] = row[2]

        if progress_callback:
            progress_callback(f"📋 {len(translation_map)} çeviri yüklendi.")

        # --- Yöntem 1: cobra-tools ---
        if _cobra_available:
            try:
                CobraManager._repack_via_cobra_tools(
                    original_ovl, translation_map, output_ovl, progress_callback
                )
                if progress_callback:
                    progress_callback(f"✅ cobra-tools ile paketlendi: {output_ovl}")
                return output_ovl
            except Exception as e:
                if progress_callback:
                    progress_callback(f"⚠️ cobra-tools paketleme hatası: {e}. Fallback deneniyor...")

        # --- Yöntem 2: Binary Patch (Fallback) ---
        try:
            CobraManager._repack_fallback(original_ovl, translation_map, output_ovl, progress_callback)
            if progress_callback:
                progress_callback(f"✅ Binary patch ile paketlendi: {output_ovl}")
            return output_ovl
        except Exception as e:
            raise Exception(f"OVL paketleme başarısız: {e}")

    @staticmethod
    def _repack_via_cobra_tools(original_ovl, translation_map, output_ovl, progress_callback=None):
        """cobra-tools ile OVL string'lerini güncelle."""
        import ovl_tool
        ovl = ovl_tool.OvlFile()
        ovl.load(str(original_ovl))

        updated = 0
        for entry in ovl.entries:
            if hasattr(entry, "text") and entry.text:
                if entry.text in translation_map:
                    entry.text = translation_map[entry.text]
                    updated += 1

        ovl.save(str(output_ovl))
        if progress_callback:
            progress_callback(f"🔄 {updated} string güncellendi (cobra-tools).")

    @staticmethod
    def _repack_fallback(original_ovl, translation_map, output_ovl, progress_callback=None):
        """
        Basit binary patch:
        Orijinal OVL'i kopyala, bulunan UTF-16LE string'leri patch et.
        Aynı uzunlukta veya daha kısa string'ler yerine geçirilir.
        """
        shutil.copy2(original_ovl, output_ovl)

        with open(output_ovl, "rb") as f:
            data = bytearray(f.read())

        patched = 0
        for source, target in translation_map.items():
            src_bytes = source.encode("utf-16-le") + b"\x00\x00"
            tgt_bytes = target.encode("utf-16-le") + b"\x00\x00"

            pos = 0
            while True:
                idx = data.find(src_bytes, pos)
                if idx == -1:
                    break
                if len(tgt_bytes) <= len(src_bytes):
                    # Aynı uzunlukta veya daha kısa: doğrudan yaz, kalan baytları null ile doldur
                    padded = tgt_bytes + b"\x00" * (len(src_bytes) - len(tgt_bytes))
                    data[idx: idx + len(src_bytes)] = padded
                    patched += 1
                pos = idx + len(src_bytes)

        with open(output_ovl, "wb") as f:
            f.write(data)

        if progress_callback:
            progress_callback(f"🔄 {patched} string binary patch ile güncellendi.")

    # ------------------------------------------------------------------ #
    #  Kurulum: Çevrilen OVL'yi oyun klasörüne yerleştir                   #
    # ------------------------------------------------------------------ #
    @staticmethod
    def install_translation(original_ovl, translated_ovl, progress_callback=None):
        """
        Orijinal loc.ovl'nin yedeğini alır, çevrilen sürümü yerine koyar.
        """
        original_ovl  = Path(original_ovl)
        translated_ovl = Path(translated_ovl)

        # Yedek
        backup = original_ovl.with_suffix(".ovl.backup")
        if not backup.exists():
            shutil.copy2(original_ovl, backup)
            if progress_callback:
                progress_callback(f"💾 Yedek oluşturuldu: {backup.name}")

        # Yerleştir
        shutil.copy2(translated_ovl, original_ovl)
        if progress_callback:
            progress_callback(f"✅ Çeviri oyuna kuruldu: {original_ovl}")

    # ------------------------------------------------------------------ #
    #  Ana Giriş Noktası (GUI tarafından çağrılır → Unreal ile aynı imza) #
    # ------------------------------------------------------------------ #
    @staticmethod
    def translate_game(
        game_exe_path,
        progress_callback=None,
        service="google",
        api_key="",
        max_workers=10,
        target_lang="tr",
        progress_max_callback=None,
        progress_bar_callback=None,
        # Unreal ile API uyumluluğu için ek parametreler (kullanılmaz)
        aes_key=None,
        game_name=None,
        ask_aes_key_callback=None,
        ask_file_callback=None,
        target_pak_path=None,
        target_internal_file_path=None,
        is_encrypted_override=None,
        manual_review_callback=None,
        **kwargs,
    ):
        """
        Cobra Engine oyununu çevir.
        Unreal Manager.translate_game ile birebir aynı imzayı paylaşır.
        GUI'nin herhangi bir değişiklik yapmasına gerek yoktur.
        """
        try:
            path_obj = Path(game_exe_path)
            game_dir = path_obj.parent if path_obj.is_file() else path_obj

            if progress_callback:
                progress_callback(f"🐍 Cobra Engine Çeviri Başlatılıyor: {game_dir.name}")

            # 1. loc.ovl bul
            ovl_path = CobraManager.find_loc_ovl(game_dir, progress_callback)
            if not ovl_path:
                raise FileNotFoundError(
                    "loc.ovl bulunamadı!\n\n"
                    f"Taranan klasör: {game_dir}\n"
                    "Beklenen konum: win64/ovldata/loc.ovl\n\n"
                    "Lütfen oyunun ana klasörünü veya exe dosyasını seçtiğinizden emin olun."
                )

            # 2. OVL → CSV
            work_dir = Config.BASE_PATH / "temp" / "cobra" / game_dir.name
            work_dir.mkdir(parents=True, exist_ok=True)

            extracted_csv = work_dir / "loc_extracted.csv"
            _, rows = CobraManager.extract_ovl_to_csv(ovl_path, extracted_csv, progress_callback)

            if not rows:
                raise Exception("OVL dosyasından hiç metin çıkarılamadı.")

            # 3. Çeviri
            translated_csv = CobraManager.translate_csv(
                extracted_csv,
                service=service,
                api_key=api_key,
                max_workers=max_workers,
                progress_callback=progress_callback,
                progress_max_callback=progress_max_callback,
                progress_bar_callback=progress_bar_callback,
                target_lang=target_lang,
            )

            # 4. Manuel İnceleme (varsa)
            if manual_review_callback:
                if progress_callback:
                    progress_callback("⏸️ Manuel İnceleme Bekleniyor...")
                try:
                    os.startfile(str(work_dir))
                except Exception:
                    pass
                result = manual_review_callback(str(translated_csv))
                if not result:
                    raise Exception("Manuel inceleme kullanıcı tarafından iptal edildi.")
                if progress_callback:
                    progress_callback("▶️ İşleme Devam Ediliyor...")

            # 5. CSV → OVL
            output_ovl = work_dir / f"loc_{target_lang.upper()}.ovl"
            CobraManager.repack_ovl(ovl_path, translated_csv, output_ovl, progress_callback)

            # 6. Oyuna kur
            CobraManager.install_translation(ovl_path, output_ovl, progress_callback)

            if progress_callback:
                progress_callback("🎉 Cobra Engine çevirisi tamamlandı! Oyunu başlatabilirsiniz.")

            return True

        except Exception as e:
            if progress_callback:
                progress_callback(f"❌ Cobra Çeviri Hatası: {e}")
            import traceback
            traceback.print_exc()
            return False

    @staticmethod
    def process_game(
        game_file_path,
        progress_callback=None,
        service="google",
        api_key=None,
        max_workers=10,
        target_lang="tr",
        progress_max_callback=None,
        progress_bar_callback=None,
        manual_review_callback=None,
        # Unreal ile uyumluluk
        aes_key=None,
        game_name=None,
        ask_aes_key_callback=None,
        ask_file_callback=None,
        target_pak_path=None,
        target_internal_file_path=None,
        is_encrypted_override=None,
        logger_callback=None,
        **kwargs,
    ):
        """GUI → Manager köprüsü (Unreal PakManager.process_game ile aynı imza)."""
        def unified_cb(msg):
            if progress_callback:
                progress_callback(msg)
            if logger_callback:
                logger_callback(msg)

        success = CobraManager.translate_game(
            game_file_path,
            progress_callback=unified_cb,
            service=service,
            api_key=api_key or "",
            max_workers=max_workers,
            target_lang=target_lang,
            progress_max_callback=progress_max_callback,
            progress_bar_callback=progress_bar_callback,
            manual_review_callback=manual_review_callback,
        )
        return success, ("İşlem başarıyla tamamlandı" if success else "İşlem sırasında hata oluştu")
