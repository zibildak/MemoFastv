import os
import csv
import subprocess
import shutil
import re
import json
import time
import struct
import sys
import textwrap
import requests
from pathlib import Path
from config import Config
from concurrent.futures import ThreadPoolExecutor, as_completed
from random import uniform
from logger import setup_logger

logger = setup_logger(__name__)
try:
    from deep_translator import GoogleTranslator
    from deep_translator import DeepL
except ImportError:
    GoogleTranslator = None
    DeepL = None

try:
    import tkinter as tk
    from tkinter import simpledialog
except ImportError:
    tk = None
    simpledialog = None

# Global cache for Local AI to avoid reloading 5GB model for each file
_LOCAL_AI_INSTANCE = None

def get_local_ai():
    global _LOCAL_AI_INSTANCE
    if _LOCAL_AI_INSTANCE is None:
        try:
            from gemma.local_ai_engine import LocalAIEngine
            _LOCAL_AI_INSTANCE = LocalAIEngine()
            success, msg = _LOCAL_AI_INSTANCE.load_model()
            if not success:
                logger.error(f"Local AI Model Yüklenemedi: {msg}")
                return None
        except Exception as e:
            logger.error(f"Local AI Başlatma Hatası: {e}")
            return None
    return _LOCAL_AI_INSTANCE

class GeminiTranslator:
    """Gemini API Wrapper for Translation"""
    def __init__(self, api_key, target_lang="tr", model="gemini-2.5-flash", source_lang="en"):
        self.api_key = api_key
        self.target_lang = target_lang
        self.source_lang = source_lang
        self.cache = {} # [YENİ] Önbellek
        import threading
        self._cache_lock = threading.Lock() # Paralel çeviri worker'ları için
        
        # 2026 Güncellemesi: Model ismini dinamik yapıyoruz
        if not model.startswith("models/"):
            model_path = f"models/{model}"
        else:
            model_path = model
            
        self.url = f"https://generativelanguage.googleapis.com/v1/{model_path}:generateContent?key={api_key}"
        self.headers = {'Content-Type': 'application/json'}
        
        # Dil Haritası
        self.lang_map = {
            "tr": "Turkish", "ru": "Russian", "pt": "Brazilian Portuguese",
            "es": "Spanish", "id": "Indonesian", "pl": "Polish",
            "de": "German", "fr": "French", "it": "Italian", "en": "English",
            "ja": "Japanese", "zh": "Chinese", "ko": "Korean"
        }
        self.target_lang_name = self.lang_map.get(target_lang, "Turkish")
        self.source_lang_name = self.lang_map.get(source_lang, "English")

    def ask(self, prompt, timeout=10):
        """Genel amaçlı Gemini sorgusu"""
        data = {
            "contents": [{
                "parts": [{"text": prompt}]
            }]
        }
        try:
            response = requests.post(self.url, headers=self.headers, json=data, timeout=timeout)
            if response.status_code == 200:
                result = response.json()
                return result['candidates'][0]['content']['parts'][0]['text'].strip()
            
            # Hata durumunu logla ve konsola bas
            err_msg = f"❌ Gemini API Hatası ({response.status_code}): {response.text}"
            print(err_msg)
            logger.error(err_msg)
            
            # Özel hata durumları için metin dönebiliriz (isteğe bağlı)
            if response.status_code == 400:
                return "HATA: GEÇERSİZ_API_KEY (Lütfen Ayarları Kontrol Edin)"
            elif response.status_code == 429:
                return "HATA: KOTA_DOLDU (Limit Aşıldı)"
                
            return None
        except Exception as e:
            logger.error(f"Gemini İstek Hatası: {e}")
            return None

    def translate(self, text, target_lang=None):
        # target_lang worker tarafından kwarg olarak geçilebilir; verilirse günceller.
        # (Önceden bu parametre kabul edilmediği için her çağrı TypeError veriyordu
        # ve Gemini ile locres çevirisi sessizce başarısız oluyordu.)
        if target_lang and target_lang != self.target_lang:
            self.target_lang = target_lang
            self.target_lang_name = self.lang_map.get(target_lang, "Turkish")
        if not text or not text.strip(): return text
        
        # 1. Önbellek Kontrolü
        with self._cache_lock:
            if text in self.cache:
                return self.cache[text]
            
        prompt = (
            f"You are an expert video game localizer. Translate the following {self.source_lang_name} text to {self.target_lang_name}. "
            f"CONTEXT: This is for a game UI (buttons, menus, or dialogues). "
            f"RULE: Use natural, short game terminology. Always use IMPERATIVE forms for actions (e.g., 'Quit' -> 'Çıkış Yap', 'Save' -> 'Kaydet'). "
            f"Never use infinitive forms (-mak/-mek) for commands. "
            f"Placeholders like __VAR_0__ must be kept EXACTLY as-is. "
            f"Output ONLY the translated text without any quotes or explanations.\\n\\nText: {text}"
        )
        
        # [YENİ] İnatçı Deneme (Retry Logic)
        for attempt in range(3):
            translated = self.ask(prompt)
            
            # Hata yoksa veya başarıyla çevrildiyse
            if translated and "HATA:" not in translated:
                if self.target_lang == "tr":
                    translated = apply_turkish_correction(translated)
                with self._cache_lock:
                    self.cache[text] = translated
                return translated
                
            # Eğer hata KOTA (429) ise bekle ve tekrar dene
            if translated == "HATA: KOTA_DOLDU (Limit Aşıldı)":
                print(f"⏳ Kota doldu, {attempt+1}. deneme için 2sn bekleniyor... ({text[:20]})")
                import time
                time.sleep(2)
                continue
            
            # Diğer hatalarda (400, 500 vb.) beklemeye gerek yok
            break

        return text # Her şey başarısız olursa orijinali dön

    def translate_batch(self, texts, target_lang=None):
        """
        [TOPLU MOD] Birden fazla metni TEK API isteğiyle çevirir.
        Satır başına istek yerine ~40 satırı tek pakette göndererek
        hem hızı ~30 kat artırır hem de kota tüketimini düşürür.

        Args:
            texts: Çevrilecek metin listesi
        Returns:
            list: texts ile aynı uzunlukta; çevrilemeyen girdiler None olur
                  (çağıran taraf bunlar için tekil çeviriye düşebilir).
        """
        if target_lang and target_lang != self.target_lang:
            self.target_lang = target_lang
            self.target_lang_name = self.lang_map.get(target_lang, "Turkish")

        results = [None] * len(texts)
        if not texts:
            return results

        # 1. Önbellekten doldur, kalanları belirle
        pending = []
        with self._cache_lock:
            for i, t in enumerate(texts):
                if not t or not t.strip():
                    results[i] = t
                elif t in self.cache:
                    results[i] = self.cache[t]
                else:
                    pending.append(i)

        if not pending:
            return results

        import json as _json
        input_array = _json.dumps([texts[i] for i in pending], ensure_ascii=False)

        prompt = (
            f"You are an expert video game localizer. Translate each {self.source_lang_name} string "
            f"in the JSON array below to {self.target_lang_name}. "
            f"CONTEXT: Game UI texts (buttons, menus, dialogues). "
            f"RULES: Use natural, short game terminology. Use IMPERATIVE forms for actions "
            f"(e.g., 'Quit' -> 'Çıkış Yap'). Never use infinitive forms (-mak/-mek) for commands. "
            f"Placeholders like __VAR_0__ must be kept EXACTLY as-is. "
            f"OUTPUT FORMAT: Return ONLY a valid JSON array of strings with EXACTLY "
            f"{len(pending)} elements, in the same order as the input. No markdown, no explanations.\n\n"
            f"Input: {input_array}"
        )

        for attempt in range(3):
            # Toplu istek tekil istekten uzun sürer, geniş timeout kullan
            raw = self.ask(prompt, timeout=90)

            if raw == "HATA: KOTA_DOLDU (Limit Aşıldı)":
                import time
                time.sleep(2)
                continue
            if not raw or raw.startswith("HATA:"):
                break

            parsed = self._parse_batch_response(raw, len(pending))
            if parsed is None:
                continue  # Format bozuk geldi, bir kez daha dene

            for n, i in enumerate(pending):
                tr = parsed[n]
                if tr and isinstance(tr, str) and tr.strip():
                    if self.target_lang == "tr":
                        tr = apply_turkish_correction(tr)
                    results[i] = tr
                    with self._cache_lock:
                        self.cache[texts[i]] = tr
            return results

        return results  # Başarısız — kalanlar None, caller tekil moda düşer

    @staticmethod
    def _parse_batch_response(raw, expected_count):
        """Gemini yanıtından JSON dizisini güvenli şekilde ayıklar."""
        import json as _json
        import re as _re

        text = raw.strip()
        # Markdown kod bloğu sarmalını temizle: ```json ... ```
        fence = _re.match(r'^```(?:json)?\s*(.*?)\s*```$', text, _re.DOTALL)
        if fence:
            text = fence.group(1).strip()

        # Yanıtın içinden ilk JSON dizisini bul (başta/sonda açıklama olabilir)
        if not text.startswith('['):
            start = text.find('[')
            end = text.rfind(']')
            if start == -1 or end == -1 or end <= start:
                return None
            text = text[start:end + 1]

        try:
            data = _json.loads(text)
        except Exception:
            return None

        if not isinstance(data, list) or len(data) != expected_count:
            return None
        return data

# İstisnalar (Global)
TURKISH_EXCEPTIONS = {
    "ekmek", "yemek", "parmak", "çakmak", "kaymak", 
    "damak", "ırmak", "yamak", "kıymak", "yumak", "sevmek"
}

def apply_turkish_correction(text):
    """
    Çevirilerdeki gereksiz mastar eklerini kaldırır (Tüm kelimeleri tarar).
    """
    if not text: return text
    
    try:
        # 1. Kelimelere ayır
        words = text.split()
        if not words: return text
        
        new_words = []
        for word in words:
            # Noktalama işaretini ayır
            match = re.search(r'^(.+?)(m[ae]k)(\W*)$', word, re.IGNORECASE)
            
            if match:
                root = match.group(1)
                suffix = match.group(2)
                punct = match.group(3)
                full_word = root + suffix
                
                if full_word.lower() not in TURKISH_EXCEPTIONS:
                    new_words.append(root + punct)
                else:
                    new_words.append(word)
            else:
                new_words.append(word)
                
        return " ".join(new_words)
        
    except Exception as e:
        return text

class VariableProtector:
    """
    Değişkenleri ve HTML benzeri etiketleri çeviri öncesi maskeler.
    Örn: {gun} -> __VAR_0__, <img id="x"/> -> __VAR_1__
    """
    def __init__(self):
        self.placeholders = {}
        self.counter = 0

    def protect(self, text):
        if not text: return text
        
        # 1. Regex Tanımları
        # Süslü parantezli değişkenler: {name}, {0}, {silverNum}
        # HTML tagleri: <br>, <img ...>, </color>
        # Köşeli parantezler (Unity Rich Text): [00FF00] (basit hexler) - Şimdilik karıştırmayalım, Unreal genelde < > kullanır.
        
        # Regex: <[^>]+> (HTML Tag) VEYA \{[^}]+\} (Variable)
        pattern = re.compile(r'(<[^>]+>)|(\{[^}]+\})')
        
        def replace_match(match):
            val = match.group(0)
            key = f"__VAR_{self.counter}__"
            self.placeholders[key] = val
            self.counter += 1
            return key
            
        protected_text = pattern.sub(replace_match, text)
        return protected_text

    def restore(self, text):
        """Maskelenmiş metni geri yükler"""
        if not text: return text
        
        # Basit replace (Sıralı olmasa da olur, unique keyler var)
        for key, val in self.placeholders.items():
            # Translate bazen boşluk ekleyebilir: __VAR_0__ -> __ VAR_0 __
            # Bu yüzden esnek replace veya doğrudan replace yapalım.
            # Google Translate genelde "_" yırtmaz ama boşluk atabilir.
            
            if key in text:
                text = text.replace(key, val)
            else:
                # Fallback: Belki boşluklu hali vardır?
                # "VAR_0" diye arayalım? (Çok riskli, benzer kelime olabilir)
                pass
                
        return text

def process_locres_file(locres_file, progress_callback=None, is_pak_temp=False, service="google", api_key="", max_workers=10, progress_max_callback=None, progress_bar_callback=None, manual_review_callback=None, target_lang="tr", source_lang="en"):
    """Global Locres Translator Function"""
    tool_path = Config.BASE_PATH / "files" / "tools" / "UnrealLocres.exe"
    
    # Girdi Tipi Kontrolü
    is_csv_input = str(locres_file).lower().endswith(".csv")
    csv_output = None

    if is_csv_input:
        if progress_callback: progress_callback("📄 CSV dosyası tespit edildi, doğrudan işleniyor...")
        csv_output = locres_file
    else:
        # Export (Locres -> CSV)
        if progress_callback: progress_callback("📤 Metinler dışa aktarılıyor (Export)...")
        
        # Olası çıktı dosya adları
        possible_outputs = [
            locres_file.with_suffix(".csv"),       # Engine.csv
            locres_file.with_name(locres_file.name + ".csv") # Engine.locres.csv
        ]
        
        # Komut: UnrealLocres.exe export <dosya>
        cmd_export = [str(tool_path), "export", str(locres_file)]
        
        # Çıktıyı yakala
        res = subprocess.run(cmd_export, capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW)
        
        # 1. Kaynak dosyanınyanını kontrol et
        for p in possible_outputs:
            if p.exists():
                csv_output = p
                break
        
        # 2. Çalışma dizinini (CWD) kontrol et (UnrealLocres buraya atmış olabilir)
        if not csv_output:
            cwd_file = Path(os.getcwd()) / locres_file.with_suffix(".csv").name
            if cwd_file.exists():
                    # Bulduk! Temp klasörüne taşıyalım
                    target_path = locres_file.with_suffix(".csv")
                    shutil.move(str(cwd_file), str(target_path))
                    csv_output = target_path

        if not csv_output:
            err_msg = f"UnrealLocres Çıktısı:\n{res.stdout}\n{res.stderr}"
            if progress_callback: progress_callback(f"⚠️ Export Hatası Debug:\n{err_msg}")
            raise Exception(f"Export başarısız, CSV dosyası oluşmadı. (Kod: {res.returncode})")
    
    # Çeviri
    if progress_callback: progress_callback("🌍 Metinler çevriliyor...")
    translated_csv = locres_file.with_name(locres_file.stem + "_TR.csv")
    
    # [YENİ] Resume / Akıllı Devam Sistemi
    resume_dict = {}
    if translated_csv.exists():
        try:
            if progress_callback: progress_callback("📂 Önceki çeviri (Resume) yükleniyor...")
            with open(translated_csv, 'r', encoding='utf-8', newline='') as f_resume:
                res_reader = csv.reader(f_resume)
                for r_idx, r_row in enumerate(res_reader):
                    # Format: Key, Source, Target
                    if len(r_row) >= 3 and r_row[1] and r_row[2]:
                        # Key veya Source üzerinden eşleştirebiliriz.
                        # Source metni key olarak alalım (daha güvenli, ID değişebilir)
                        resume_dict[r_row[1]] = r_row[2]
            
            if progress_callback: progress_callback(f"♻️ {len(resume_dict)} satır hafızadan yüklendi.")
        except Exception as e:
            print(f"Resume load error: {e}")

    # [YENİ] Kalıcı Global Çeviri Önbelleği — bir kez çevrilen metin diske yazılır,
    # başka oyunlarda/oturumlarda tekrar API'ye gitmez (ücretsiz kullanım hedefi).
    persist_cache = None
    cache_hit_count = 0
    try:
        from translation_cache import TranslationCache
        persist_cache = TranslationCache(target_lang=target_lang, source_lang=source_lang)
        if len(persist_cache) > 0 and progress_callback:
            progress_callback(f"💾 Kalıcı önbellek hazır: {len(persist_cache)} hazır çeviri mevcut.")
    except Exception as e:
        print(f"Kalıcı önbellek açılamadı (çeviri normal devam eder): {e}")

    translator = None
    if service == "deepl" and api_key and DeepL:
        try:
            # DeepL init
            # [FIX] DeepL requires PT-BR or PT-PT, 'pt' is not allowed as target
            use_lang = target_lang
            if target_lang.lower() == "pt": use_lang = "PT-BR"
            elif target_lang.lower() == "en": use_lang = "EN-US"
            
            is_free = True if api_key.strip().endswith(":fx") else False
            translator = DeepL(api_key=api_key, source=source_lang, target=use_lang, use_free_api=is_free)
            if progress_callback: progress_callback("🚀 DeepL API kullanılıyor...")
        except Exception as e:
            if progress_callback: progress_callback(f"⚠️ DeepL Hatası: {e}\nGoogle Translate'e dönülüyor...")
            translator = GoogleTranslator(source=source_lang, target=target_lang) if GoogleTranslator else None
    elif service == "gemini" and api_key:
        try:
            translator = GeminiTranslator(api_key, target_lang=target_lang, source_lang=source_lang)
            if progress_callback: progress_callback("✨ Gemini AI kullanılıyor...")
        except:
            translator = GoogleTranslator(source=source_lang, target=target_lang) if GoogleTranslator else None
    elif service == "local_ai":
        global _LOCAL_AI_INSTANCE
        try:
            from gemma.local_ai_engine import LocalAIEngine
            
            if _LOCAL_AI_INSTANCE is None:
                if progress_callback: progress_callback("📦 Yerel AI motoru başlatılıyor...")
                _LOCAL_AI_INSTANCE = LocalAIEngine()
                if progress_callback: progress_callback("🧠 Model dosyası diskten RAM'e aktarılıyor... (5 GB veri okunuyor, lütfen bekleyin)")
                success, msg = _LOCAL_AI_INSTANCE.load_model()
                if not success:
                    if progress_callback: progress_callback(f"⚠️ Hata: {msg}\nGoogle Translate'e geçiliyor...")
                    translator = GoogleTranslator(source=source_lang, target=target_lang) if GoogleTranslator else None
                    _LOCAL_AI_INSTANCE = None 
                else:
                    if progress_callback: progress_callback("✅ Model RAM'e başarıyla yüklendi!")
                    translator = _LOCAL_AI_INSTANCE
            else:
                if progress_callback: progress_callback("⚡ Model zaten bellekte hazır! (Cache kullanılıyor)")
                translator = _LOCAL_AI_INSTANCE
                
        except Exception as e:
            if progress_callback: progress_callback(f"⚠️ Yerel AI Modül Hatası: {e}\nGoogle Translate'e dönülüyor...")
            translator = GoogleTranslator(source=source_lang, target=target_lang) if GoogleTranslator else None
    else:
        translator = GoogleTranslator(source=source_lang, target=target_lang) if GoogleTranslator else None

    # [FIX] Yerel AI (LLM) için paralel çalışma performansı düşürür, tekil (1) çalıştırılmalı
    if service == "local_ai":
        max_workers = 1
        if progress_callback: progress_callback("ℹ️ Yerel AI modu: Tek kanallı (Sequential) işlem modu aktif.")

    # Kütüphane yoksa Fallback (requests) kullanılacak, hata fırlatma.
    if not translator and progress_callback and not resume_dict: # Resume varsa çok dert değil
        progress_callback("⚠️ Deep-Translator kütüphanesi yok, yedek sistem (Requests) kullanılıyor.")
    
    # Import
    failure_count = 0
    success_count = 0
    
    # 1. OKUMA AŞAMASI (Dosyayı belleğe al ve kapat)
    rows = []
    with open(csv_output, 'r', encoding='utf-8', newline='') as f_in:
        reader = csv.reader(f_in)
        rows = list(reader)
        
    if progress_callback:
        progress_callback(f"📊 CSV Okundu: {len(rows)} satır işleniyor.")
        progress_callback(f"🔧 Servis: {service.upper()}")

    # 2. İŞLEME AŞAMASI (Paralel Çeviri - Turbo Mode v8)
    work_items = [] 
    
    for i, row in enumerate(rows):
        # Header'ı atla
        if i == 0: continue
            
        # Satır onarımı
        if len(row) < 3:
            while len(row) < 3: row.append("")
        
        source_text = row[1]

        if not source_text or len(source_text) < 2:
            continue

        # [YENİ] Resume Kontrolü
        if source_text in resume_dict:
            rows[i][2] = resume_dict[source_text] # Target = TR
            # Source orijinal kalır (rows[i][1])
            success_count += 1
            # Work items'a EKLEME
            continue

        # [YENİ] Kalıcı Global Önbellek Kontrolü (oyunlar arası, ücretsiz kullanım)
        if persist_cache:
            cached_tr = persist_cache.get(source_text)
            if cached_tr:
                rows[i][2] = cached_tr
                success_count += 1
                cache_hit_count += 1
                continue

        work_items.append((i, source_text))

    def translate_worker(idx, text):
        try:
            if service == "google": time.sleep(uniform(0.1, 0.4))
            res_text = None
            
            # [YENİ] Değişken Koruma (Protect)
            protector = VariableProtector()
            protected_text = protector.protect(text)
            
            # Çeviriye gönderilen metin: protected_text
            # Eğer hiç tag yoksa text ile aynıdır.
            
            if translator:
                # [FIX] Polymorphic translate call
                # Yerel AI ve Gemini 'target_lang' parametresini çalışma anında kabul eder.
                # GoogleTranslator ve DeepL ise başlatılırken (init) dili alır.
                
                class_name = translator.__class__.__name__
                if class_name in ["LocalAIEngine", "GeminiTranslator"]:
                    res_text = translator.translate(protected_text, target_lang=target_lang)
                else:
                    res_text = translator.translate(protected_text)
            else:
                try:
                    url = "https://translate.googleapis.com/translate_a/single"
                    params = {"client": "gtx", "sl": source_lang, "tl": target_lang, "dt": "t", "q": protected_text}
                    r = requests.get(url, params=params, timeout=5)
                    if r.status_code == 200: res_text = r.json()[0][0][0]
                except Exception as e_req:
                    print(f"Fallback request error: {e_req}")
            
            if res_text:
                # [YENİ] Değişken Geri Yükleme (Restore)
                try: 
                    res_text = protector.restore(res_text)
                except Exception as e_res:
                    print(f"Restore hatası: {e_res}")
                    # Hata varsa (çok nadir), orijinal protected veya bozuk hal kalır.
                    # En kötü ihtimalle tagler bozulur, ama oyun çökmez (umarız).
                    
                    
                try: 
                    if target_lang == "tr":
                        res_text = apply_turkish_correction(res_text)
                except: pass
            return idx, res_text
        except Exception as e_worker:
            print(f"Worker error at index {idx}: {e_worker}")
            return idx, None

    # Thread Pool Başlat
    total_items = len(work_items)
    use_gemini_batch = (
        translator is not None
        and translator.__class__.__name__ == "GeminiTranslator"
        and total_items > 1
    )

    if progress_callback:
        if service == "local_ai":
            progress_callback(f"🚀 Yerel AI ile Çeviri Başladı... (Sırayla İşleniyor - Toplam: {total_items})")
        elif use_gemini_batch:
            progress_callback(f"🚀 GEMİNİ TOPLU MOD: {total_items} satır paketler halinde çevriliyor (çok daha hızlı, daha az kota)...")
        else:
            progress_callback(f"🚀 TURBO MOD Devrede: {total_items} satır {max_workers} işçi ile çevriliyor...")

    if progress_max_callback:
        progress_max_callback(total_items)

    completed_count = 0

    if use_gemini_batch:
        # [TOPLU MOD] Satır başına istek yerine ~40 satırlık paketler tek istekte gider.
        BATCH_SIZE = 40
        chunks = [work_items[k:k + BATCH_SIZE] for k in range(0, len(work_items), BATCH_SIZE)]

        def batch_worker(chunk):
            protectors = {}
            protected_texts = []
            for idx, text in chunk:
                p = VariableProtector()
                protectors[idx] = p
                protected_texts.append(p.protect(text))

            batch_results = translator.translate_batch(protected_texts, target_lang=target_lang)

            out = []
            for (idx, text), res in zip(chunk, batch_results):
                if not res:
                    # Bu satır toplu yanıttan çıkmadı → tekil çeviriye düş
                    try:
                        res = translator.translate(protectors[idx].protect(text), target_lang=target_lang)
                        if res == text:  # translate() başarısızlıkta orijinali döner
                            res = None
                    except Exception as e_single:
                        print(f"Tekil fallback hatası (satır {idx}): {e_single}")
                        res = None
                if res:
                    try:
                        res = protectors[idx].restore(res)
                    except Exception as e_res:
                        print(f"Restore hatası (satır {idx}): {e_res}")
                out.append((idx, res))
            return out

        # Aynı anda en fazla 3 paket: hem hızlı hem kota dostu
        with ThreadPoolExecutor(max_workers=min(3, max_workers)) as executor:
            batch_futures = [executor.submit(batch_worker, c) for c in chunks]
            for future in as_completed(batch_futures):
                try:
                    for idx, result_text in future.result():
                        if result_text and len(rows[idx]) > 2:
                            rows[idx][2] = result_text
                        completed_count += 1
                        if progress_bar_callback:
                            progress_bar_callback(completed_count)
                except Exception as e_batch:
                    print(f"Batch worker hatası: {e_batch}")

                if progress_callback and total_items:
                    percent = int((completed_count / total_items) * 100)
                    progress_callback(f"⚡ [{completed_count}/{total_items}] - %{percent} tamamlandı (Toplu Mod)")
    else:
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_idx = {executor.submit(translate_worker, idx, txt): idx for (idx, txt) in work_items}
            for future in as_completed(future_to_idx):
                idx = future_to_idx[future]
                try:
                    result_idx, result_text = future.result()
                    if result_text:
                        # rows[result_idx][1] = result_text # Source DEĞİŞTİRİLMİYOR
                        if len(rows[result_idx]) > 2:
                            rows[result_idx][2] = result_text # Target Dolduruluyor
                except: pass

                completed_count += 1
                if progress_bar_callback:
                    progress_bar_callback(completed_count)

                # [FIX] Yerel AI yavaş olduğu için her satırda (veya daha sık) log verelim
                update_freq = 20
                if service == "local_ai": update_freq = 1

                if completed_count % update_freq == 0 or completed_count == total_items:
                    percent = int((completed_count / total_items) * 100)
                    if progress_callback:
                        msg = f"⚡ [{completed_count}/{total_items}] - %{percent} tamamlandı"
                        if service == "local_ai" and 'result_text' in locals() and result_text:
                            # Son çeviriyi de göster (kısa özet)
                            short_txt = result_text[:50] + "..." if len(result_text) > 50 else result_text
                            msg = f"🤖 [Satır {completed_count}/{total_items}] Çeviri: {short_txt}"
                        progress_callback(msg)

    # [YENİ] Yeni çevirileri kalıcı önbelleğe yaz (sonraki oyunlar için)
    if persist_cache:
        try:
            for w_idx, w_src in work_items:
                if len(rows[w_idx]) > 2 and rows[w_idx][2]:
                    persist_cache.set(w_src, rows[w_idx][2])
            persist_cache.save()
            if progress_callback:
                msg = f"💾 Kalıcı önbellek güncellendi (toplam {len(persist_cache)} çeviri birikti)."
                if cache_hit_count:
                    msg += f" Bu oyunda {cache_hit_count} satır önbellekten geldi — API'ye hiç gitmedi!"
                progress_callback(msg)
        except Exception as e:
            print(f"Önbellek kayıt hatası (çeviri etkilenmez): {e}")

    # 3. YAZMA AŞAMASI (Dosyayı tekrar aç ve yaz)
    # [FIX] UTF-8 (BOM'suz) ve Newline sanitization
    
    # Satırları temizle (Newline karakterleri CSV'yi bozabilir)
    cleaned_rows = []
    for r in rows:
        new_row = []
        for cell in r:
            if cell:
                # Satır sonlarını ve zararlı karakterleri temizle
                cl = str(cell).replace("\n", " ").replace("\r", "").strip()
                new_row.append(cl)
            else:
                new_row.append("")
        cleaned_rows.append(new_row)

    with open(translated_csv, 'w', encoding='utf-8', newline='') as f_out:
        writer = csv.writer(f_out, quoting=csv.QUOTE_MINIMAL)
        writer.writerows(cleaned_rows)
    
    # Dump
    dump_path = Config.BASE_PATH / "Translated_Dump.csv"
    try: shutil.copy2(translated_csv, dump_path)
    except: pass
    
    # --- DOĞRULAMA (VALIDATION) ---
    # Oluşturulan CSV'yi okuyarak geçerli bir CSV olup olmadığını kontrol et
    # Eğer bozuksa, subprocess.run muhtemelen hang oluyor.
    if progress_callback: progress_callback("🔍 Oluşturulan CSV doğrulanıyor...")
    try:
        with open(translated_csv, 'r', encoding='utf-8-sig') as f_verify:
            # Sadece okumayı dene, hata verirse except'e düşer
            v_reader = csv.reader(f_verify)
            v_rows = list(v_reader)
            if not v_rows:
                 print("⚠️ Uyarı: Oluşturulan CSV boş görünüyor.")
            else:
                 # İlk 3 satırı loga bas
                 print("✅ CSV Doğrulama Başarılı. Örnek İçerik:")
                 for vr in v_rows[:3]:
                     print(f"  {vr}")
    except Exception as e_ver:
        err = f"❌ KRİTİK HATA: Oluşturulan CSV bozuk! ({e_ver})"
        if progress_callback: progress_callback(err)
        raise Exception(f"CSV Validation Failed: {e_ver}")

    # [MANUEL REVIEW STEP]
    if manual_review_callback:
        # [MODIFICATION CHECK] User dosyayı değiştirdi mi?
        # Öncesi mod time
        before_mtime = 0
        if locres_file.exists():
            before_mtime = locres_file.stat().st_mtime
            
        # Callback'e dosya yolunu gönderir ve bloklar (cevap bekler)
        try:
                review_result = manual_review_callback(str(translated_csv))
                
                if not review_result:
                    if progress_callback: progress_callback("❌ Kullanıcı işlemi iptal etti.")
                    raise Exception("Manuel inceleme kullanıcı tarafından iptal edildi.")
                    
                # User "Devam" dedi ama dosyayı sildi mi?
                if not translated_csv.exists():
                    # Belki locres'i değiştirdi ve CSV'yi sildi? Kontrol edelim.
                    after_mtime = 0
                    if locres_file.exists():
                        after_mtime = locres_file.stat().st_mtime
                        
                    if after_mtime != before_mtime and after_mtime > 0:
                        if progress_callback: progress_callback("✅ Kullanıcı .locres dosyasını manuel değiştirdi (CSV yok), IMPORT ALANLANIYOR.")
                        if not is_pak_temp:
                            if progress_callback: progress_callback("✅ İşlem tamamlandı (Manuel Locres).")
                        return True
                    
                    if progress_callback: progress_callback("⚠️ UYARI: CSV dosyası bulunamadı (Silinmiş olabilir).")
                    raise Exception("Gerekli CSV dosyası bulunamadı. Lütfen dosyayı silmeyin, sadece içeriğini düzenleyin.")
                
                # CSV var ama Kullanıcı LOCRES dosyasını değiştirmiş mi?
                if locres_file.exists():
                    current_mtime = locres_file.stat().st_mtime
                    # Eğer mod time değiştiyse user locres'i değiştirmiş demektir.
                    if current_mtime != before_mtime:
                        if progress_callback: progress_callback("✨ Kullanıcı .locres dosyasını manuel değiştirdi, otomatik import ATLANACAK.")
                        # Orijinal CSV'yi sil (kafa karışmasın)
                        try: 
                            if csv_output and csv_output.exists(): csv_output.unlink()
                        except: pass
                        return True # Import yapmadan çık
    
        except Exception as e_rev:
                if "iptal" in str(e_rev).lower(): raise e_rev
                print(f"Callback error: {e_rev}")
                if progress_callback: progress_callback(f"⚠️ Arayüz Hatası: {e_rev}")
                raise Exception(f"Manuel inceleme sırasında hata oluştu: {e_rev}")
        
        if progress_callback: progress_callback("▶️ İşleme Devam Ediliyor...")

    # Import
    if is_csv_input:
        if progress_callback: progress_callback("📄 CSV dosyası güncelleniyor...")
        # Çevrilmiş dosyayı orijinalin üzerine yaz (Pak içine geri konacak olan bu)
        try:
             shutil.move(str(translated_csv), str(locres_file))
        except:
             shutil.copy2(str(translated_csv), str(locres_file))
             
        if not is_pak_temp and progress_callback: 
            progress_callback("✅ İşlem tamamlandı!")
        return True
    else:
        if progress_callback: progress_callback("📥 İçeri aktarılıyor...")
        
        original_cwd = os.getcwd()
        try:
            os.chdir(locres_file.parent)
            cmd_import = [str(tool_path), "import", str(locres_file.name), str(translated_csv)]
            
            res = subprocess.run(cmd_import, capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW, timeout=60)
            
            if res.returncode != 0:
                err_msg = f"Import Aracı Hatası:\n{res.stderr}\n{res.stdout}"
                
                if ".uproject" in err_msg or "descriptor file" in err_msg.lower():
                    if progress_callback: 
                        progress_callback("⚠️ Import aracı .uproject dosyası arıyor, alternatif yöntem deneniyor...")
                    
                    new_locres = locres_file.with_suffix(".locres.new")
                    
                    try:
                        if locres_file.exists():
                            with open(locres_file, 'rb') as orig:
                                header = orig.read(1024)
                            
                            with open(translated_csv, 'r', encoding='utf-8') as csv_in:
                                csv_data = csv_in.read()
                            
                            with open(new_locres, 'wb') as out:
                                out.write(header)
                                out.write(csv_data.encode('utf-8'))
                        else:
                            shutil.copy2(translated_csv, new_locres)
                        
                        if progress_callback:
                            progress_callback("✅ Alternatif yöntemle dosya oluşturuldu")
                        
                    except Exception as fallback_err:
                        if progress_callback: 
                            progress_callback(f"❌ Fallback de başarısız: {fallback_err}")
                        raise Exception(f"Import ve fallback başarısız: {err_msg}")
                else:
                    if progress_callback: progress_callback(f"⚠️ Import Başarısız: {res.stderr[:200]}...")
                    print(err_msg)
                    raise Exception(f"UnrealLocres import failed. Code: {res.returncode}")
                    
        except subprocess.TimeoutExpired:
            if progress_callback: progress_callback("⚠️ Import işlemi zaman aşımına uğradı (60s).")
            raise Exception("UnrealLocres import timed out.")
        except Exception as e:
            if progress_callback: progress_callback(f"⚠️ Import sırasında beklenmedik hata: {e}")
            raise e
        finally:
            try:
                os.chdir(original_cwd)
            except:
                pass

        # --- DOSYA YERLEŞTİRME VE TEMİZLİK (RENAME & CLEANUP) ---
        # UnrealLocres genelde .locres.new oluşturur, ancak bazı sürümler _TR.locres de yapabilir.
        possible_results = [
            locres_file.with_suffix(".locres.new"),
            locres_file.with_name(locres_file.stem + "_TR.locres"),
            locres_file.with_name(locres_file.name + ".new")
        ]
        
        found_new = False
        for pr in possible_results:
            if pr.exists():
                try:
                    # Orijinali sil ve yenisini orijinal adıyla taşı
                    if locres_file.exists(): locres_file.unlink()
                    shutil.move(str(pr), str(locres_file))
                    found_new = True
                    if progress_callback: progress_callback(f"✅ Dosya başarıyla güncellendi: {locres_file.name}")
                    break
                except Exception as e_move:
                    if progress_callback: progress_callback(f"⚠️ Dosya taşıma hatası: {e_move}")
        
        # Geçici CSV dosyalarını temizle (Paketleme öncesi kalabalık yapmasın)
        try:
            if csv_output and csv_output.exists(): csv_output.unlink()
            if translated_csv and translated_csv.exists(): translated_csv.unlink()
            if progress_callback: progress_callback("🧹 Geçici CSV dosyaları temizlendi.")
        except: pass

        if not found_new and not is_csv_input:
             # Eğer hiç yeni dosya oluşmadıysa ve hata da almadıysak, belki tool direkt üzerine yazmıştır?
             # Ya da bir hata vardır.
             pass

        return True


class UnrealManager:
    """Unreal Engine Localization Manager (UnrealLocres Wrapper)"""
    
    TOOL_PATH = Config.BASE_PATH / "files" / "tools" / "UnrealLocres.exe"

    @staticmethod
    def is_ready():
        """Araçların hazır olup olmadığını kontrol et"""
        # UnrealLocres ve Repak gerekli
        locres_ready = UnrealManager.TOOL_PATH.exists()
        repak_ready = PakManager.is_ready() if 'PakManager' in globals() else (Config.BASE_PATH / "files" / "tools" / "repak.exe").exists()
        return locres_ready and repak_ready

    @staticmethod
    def translate_game(game_exe_path, progress_callback=None, service="google", api_key="", max_workers=10, aes_key=None, game_name=None, ask_aes_key_callback=None, ask_file_callback=None, target_pak_path=None, target_internal_file_path=None, is_encrypted_override=None, progress_max_callback=None, progress_bar_callback=None, manual_review_callback=None, target_lang="tr", backup_enabled=False, source_lang="en"):
        """Oyunun ana giriş noktası (GUI tarafından çağrılır)"""
        path_obj = Path(game_exe_path)
        
        # --- SAFETY DEFAULTS ---
        # "UnboundLocalError" ve eksik değişken hatalarını engellemek için:
        tools_dir = Config.BASE_PATH / "files" / "tools"
        detected_version = "V9"
        detected_compression = "Zlib"
        detected_mount = "../../../"
        detected_seed = None
        target_pak = None
        unpack_dir = None
        is_encrypted = False
        # -----------------------

        # Eğer hedef pak zaten seçilmişse tarama/arama adımlarını atla
        if target_pak_path:
            paks_dir = None
            if isinstance(target_pak_path, list) and target_pak_path:
                paks_dir = Path(target_pak_path[0]).parent
            elif isinstance(target_pak_path, str) and target_pak_path:
                paks_dir = Path(target_pak_path).parent
            
            if paks_dir and paks_dir.exists():
                if progress_callback: 
                    progress_callback(f"🎯 Hedef PAK Seçili. Tarama atlanarak doğrudan çeviriye geçiliyor.")
                
                result = PakManager.process_pak_translation(
                    paks_dir, 
                    progress_callback, 
                    service, 
                    api_key, 
                    max_workers, 
                    aes_key, 
                    game_name,
                    ask_aes_key_callback=ask_aes_key_callback,
                    ask_file_callback=ask_file_callback,
                    target_pak_path=target_pak_path,
                    target_internal_file_path=target_internal_file_path,
                    is_encrypted_override=is_encrypted_override,
                    progress_max_callback=progress_max_callback,
                    progress_bar_callback=progress_bar_callback,
                    manual_review_callback=manual_review_callback,
                    target_lang=target_lang,
                    backup_enabled=backup_enabled,
                    source_lang=source_lang
                )
                return result is not None

        # [FIX] Doğrudan .locres veya .csv dosyası seçildiyse PAK aramayı atla
        if path_obj.suffix.lower() in [".locres", ".csv"]:
            if progress_callback: progress_callback(f"📂 Doğrudan Dil Dosyası İşleniyor: {path_obj.name}")
            # Global process_locres_file fonksiyonunu çağır
            try:
                # process_locres_file global scope'da tanımlı olmalı
                return process_locres_file(
                    path_obj, 
                    progress_callback, 
                    is_pak_temp=False, 
                    service=service, 
                    api_key=api_key, 
                    progress_max_callback=progress_max_callback, 
                    progress_bar_callback=progress_bar_callback,
                    manual_review_callback=manual_review_callback,
                    target_lang=target_lang,
                    source_lang=source_lang
                )
            except Exception as e:
                if progress_callback: progress_callback(f"❌ Locres İşleme Hatası: {e}")
                import traceback
                traceback.print_exc()
                return False

        # Başlangıç noktası: Dosya ise bulunduğu klasör, klasör ise kendisi
        current_scan_dir = path_obj.parent if path_obj.is_file() else path_obj
        
        if progress_callback: progress_callback(f"📂 Başlangıç Konumu: {current_scan_dir}")
        
        found_paks = []
        paks_dir = None
        
        # Yukarı doğru tırmanarak PAK ara (Max 5 seviye veya 'common'a kadar)
        search_depth = 0
        max_depth = 6
        
        while search_depth < max_depth:
            # Güvenlik önlemi: 'common' klasörünün kendisine veya diskin köküne gelirse dur
            if current_scan_dir.name.lower() == "common" or len(current_scan_dir.parts) <= 1:
                # Common klasörünü taramak çok uzun sürer, duruyoruz.
                if progress_callback: progress_callback(f"⚠️ 'common' sınırına ulaşıldı, arama durduruldu.")
                break
                
            if progress_callback: progress_callback(f"🔍 Alt Klasörler Dahil Taranıyor: {current_scan_dir}")
            
            # Recursive ara (rglob tüm alt klasörlere bakar)
            candidates = list(current_scan_dir.rglob("*.pak"))
            # Sadece geçerli pakları al (_P.pak hariç)
            valid_paks = [p for p in candidates if not p.name.endswith("_P.pak")]
            
            if valid_paks:
                if progress_callback: progress_callback(f"✅ {len(valid_paks)} adet PAK dosyası bulundu.")
                found_paks = valid_paks
                # Bulunan en üst klasörü (oyun root) target olarak belirle
                paks_dir = current_scan_dir
                break
            
            # Bulamazsa bir üste çık
            current_scan_dir = current_scan_dir.parent
            search_depth += 1
            
        if not paks_dir or not found_paks:
             # UE3 Kontrolü (Genişletilmiş)
             # UE3 Uzantıları: .xxx, .upk, .gpk (Global), .tfc (Texture), .map
             ue3_exts = ["*.xxx", "*.upk", "*.gpk", "*.tfc"]
             ue3_files = []
             
             for i in range(4): # 4 seviye yukarı bak
                 try:
                     parent = path_obj.parents[i]
                     if progress_callback: progress_callback(f"🔍 UE3 Analizi: {parent.name}")
                     
                     for ext in ue3_exts:
                         found = list(parent.rglob(ext))
                         if found: 
                             ue3_files.extend(found)
                             if progress_callback: progress_callback(f"⚠️ UE3 Dosyası Bulundu: {found[0].name}")
                 except: pass
                 if ue3_files: break
             
             if ue3_files:
                 # Dosya yapısını analiz et
                 sample_file = ue3_files[0]
                 raise Exception(f"❌ BU OYUN DESTEKLENMİYOR (Unreal Engine 3)\n\n"
                                 f"Oyun Motoru: UE3 (Eski Nesil)\n"
                                 f"Tespit edilen dosya: {sample_file.name} ({sample_file.parent.name})\n"
                                 f"Durum: Bu araç sadece modern UE4/UE5 (.pak) yapısını destekler.\n"
                                 f"MK11 gibi oyunlar farklı bir şifreleme ve paketleme kullanır.")
             else:
                 raise Exception(f"Oyun dosyaları bulunamadı!\n\n"
                                 f"Taranan Klasörler: {search_depth} seviye yukarı gidildi.\n"
                                 f"Son Konum: {current_scan_dir}\n"
                                 f"Aranan: .pak (UE4) veya .xxx/.upk (UE3)\n\n"
                                 f"Lütfen oyunun ana 'Binaries' klasöründeki exe'yi seçtiğinizden emin olun.")
             
        if progress_callback: progress_callback(f"📍 PAK Kaynağı Bulundu: {paks_dir}")
        
        # Repak işlemi başlat
        result = PakManager.process_pak_translation(
            paks_dir, 
            progress_callback, 
            service, 
            api_key, 
            max_workers, 
            aes_key, 
            game_name,
            ask_aes_key_callback=ask_aes_key_callback,
            ask_file_callback=ask_file_callback,
            target_pak_path=target_pak_path,
            target_internal_file_path=target_internal_file_path,
            is_encrypted_override=is_encrypted_override,
            progress_max_callback=progress_max_callback,
            progress_bar_callback=progress_bar_callback,
            manual_review_callback=manual_review_callback,
            target_lang=target_lang,
            backup_enabled=backup_enabled,
            source_lang=source_lang
        )
        
        return result is not None

    @staticmethod
    def _translate_locres_file(locres_file, progress_callback=None, is_pak_temp=False, service="google", api_key="", progress_max_callback=None, progress_bar_callback=None, source_lang="en"):
        # Wrapper for backward compatibility if needed, calling global function
        return process_locres_file(locres_file, progress_callback, is_pak_temp, service, api_key, progress_max_callback=progress_max_callback, progress_bar_callback=progress_bar_callback, source_lang=source_lang)


class PakManager:
    """Repak Wrapper for PAK handling"""
    TOOL_PATH = Config.BASE_PATH / "files" / "tools" / "repak.exe"
    
    @staticmethod
    def is_ready():
        return PakManager.TOOL_PATH.exists()
    
    @staticmethod
    def process_game(game_file_path, progress_callback=None, service="google", api_key=None, max_workers=10, aes_key=None, game_name=None, ask_aes_key_callback=None, ask_file_callback=None, progress_max_callback=None, progress_bar_callback=None, target_pak_path=None, target_internal_file_path=None, is_encrypted_override=None, logger_callback=None, manual_review_callback=None, target_lang="tr", backup_enabled=False, source_lang="en"):
        """GUI ile Manager arasındaki köprü metod"""
        def unified_cb(msg):
            if progress_callback: progress_callback(msg)
            if logger_callback: logger_callback(msg)
            
        success = UnrealManager.translate_game(
            game_file_path, 
            progress_callback=unified_cb,
            service=service,
            manual_review_callback=manual_review_callback,
            api_key=api_key or "",
            max_workers=max_workers,
            aes_key=aes_key,
            game_name=game_name,
            ask_aes_key_callback=ask_aes_key_callback,
            ask_file_callback=ask_file_callback,
            progress_max_callback=progress_max_callback,
            progress_bar_callback=progress_bar_callback,
            target_pak_path=target_pak_path,
            target_internal_file_path=target_internal_file_path,
            is_encrypted_override=is_encrypted_override,
            target_lang=target_lang,
            backup_enabled=backup_enabled,
            source_lang=source_lang
        )
        return success, "İşlem başarıyla bitti" if success else "İşlem sırasında bir hata oluştu"
    
    @staticmethod
    def find_oodle_dll(game_root_dir, progress_callback=None):
        """
        Oyun dizininde Oodle DLL'lerini bul, repak.exe yanına VE kütüphaneye kopyala.
        (Self-Learning Library: Bulduğu DLL'i saklar)
        
        Sıralama (Öncelik):
        1. Oyun Dizini (En Uyumlu)
        2. Komşu Oyunlar (Steam Common)
        3. Kütüphane (Yedek)
        4. Tools Klasörü
        """
        oodle_variants = [
            "oo2core_9_win64.dll",
            "oo2core_8_win64.dll", 
            "oo2core_7_win64.dll",
            "oo2core_5_win64.dll",
            "oo2core_3_win64.dll"
        ]
        
        tools_dir = Config.BASE_PATH / "files" / "tools"
        lib_dir = Config.BASE_PATH / "files" / "tools" / "oodle_lib" # KÜTÜPHANE
        lib_dir.mkdir(exist_ok=True, parents=True) # Klasörü oluştur
        
        game_path = Path(game_root_dir)
        
        if progress_callback:
            progress_callback(f"🔍 Oyun dizini: {game_path}")
            logger.debug("Oyun dizini: %s", game_path)
            progress_callback(f"📚 Oodle Kütüphanesi: {lib_dir}")
        
        # 1. OYUN DİZİNİNDE ARA (En Yüksek Öncelik)
        if progress_callback: progress_callback("🔍 Oodle DLL oyun klasöründe aranıyor...")
        
        found_dlls = []
        try:
            # Hızlı Arama
            search_patterns = [
                "Binaries/Win64",
                "Engine/Binaries/Win64",
                "Engine/Binaries/ThirdParty",
                "Binaries/ThirdParty/Oodle"
            ]
            
            for pattern in search_patterns:
                search_dir = game_path / pattern
                if search_dir.exists():
                    for dll_name in oodle_variants:
                        candidates = list(search_dir.glob(dll_name))
                        if candidates: found_dlls.extend(candidates)
            
            # Geniş Arama
            if not found_dlls:
                 for dll_name in oodle_variants:
                    try: 
                        found = list(game_path.rglob(dll_name))
                        if found: found_dlls.extend(found[:1])
                    except: pass

            # OYUN İÇİNDEN BULUNDU
            if found_dlls:
                source_dll = found_dlls[0]
                target_dll = tools_dir / source_dll.name
                
                if progress_callback: progress_callback(f"✅ Oodle Oyun İçinden Bulundu: {source_dll.name}")
                
                try:
                    shutil.copy2(source_dll, target_dll)
                    shutil.copy2(source_dll, lib_dir / source_dll.name) # Öğren
                    return True
                except Exception as e:
                    if progress_callback: progress_callback(f"❌ Kopyalama hatası: {e}")
                    return False

        except Exception as e:
            print(f"Oodle game search error: {e}")

        # 2. KOMŞU OYUNLARDAN ARA (Steam Common)
        try:
            possible_common_dir = game_path.parent
            if possible_common_dir.name.lower() == "common" or "steamapps" in str(possible_common_dir).lower():
                if progress_callback: progress_callback("🌍 Komşu oyunlarda Oodle aranıyor...")
                target = "oo2core_9_win64.dll"
                for neighbor in possible_common_dir.iterdir():
                    if neighbor.is_dir() and neighbor != game_path:
                        n_dlls = list(neighbor.rglob(target))
                        if n_dlls:
                            found_dlls.append(n_dlls[0])
                            if progress_callback: progress_callback(f"🎁 Komşudan çalındı: {neighbor.name}")
                            break
                
                if found_dlls:
                     source_dll = found_dlls[0]
                     target_dll = tools_dir / source_dll.name
                     try:
                        shutil.copy2(source_dll, target_dll)
                        shutil.copy2(source_dll, lib_dir / source_dll.name)
                        return True
                     except: pass
        except: pass

        # 3. KÜTÜPHANEYE BAK
        for dll_name in oodle_variants:
            dll_in_lib = lib_dir / dll_name
            target_in_tools = tools_dir / dll_name
            
            if dll_in_lib.exists():
                if progress_callback: progress_callback(f"📚 Kütüphaneden Kullanılıyor: {dll_name}")
                try:
                    shutil.copy2(dll_in_lib, target_in_tools)
                    return True
                except: return True 
        
        # 4. TOOLS İÇİNDE (Son Çare)
        for dll_name in oodle_variants:
            dll_in_tools = tools_dir / dll_name
            if dll_in_tools.exists():
                if progress_callback: progress_callback(f"✅ Tools içinde mevcut: {dll_name}")
                return True
        
        return False

    @staticmethod
    def detect_pak_version_binary(pak_path):
        """Binary analiz ile PAK versiyonunu tespit et"""
        try:
            size = pak_path.stat().st_size
            with open(pak_path, "rb") as f:
                # Read last 1024 bytes (Footer)
                read_len = min(1024, size)
                f.seek(-read_len, 2)
                footer = f.read()
                
                # Magic Number: 0x5A6F12E1
                magic = b'\xE1\x12\x6F\x5A'
                idx = footer.find(magic)
                
                if idx != -1:
                    # Check After (Newer versions)
                    if idx + 8 <= len(footer):
                        try:
                            v = struct.unpack('<I', footer[idx+4:idx+8])[0]
                            if v == 8: return "V8A" # Default V8 to V8A, maybe try B if fails
                            if 1 <= v <= 12: return f"V{v}"
                        except: pass
                        
                    # Check Before (Older versions)
                    if idx - 4 >= 0:
                        try:
                            v = struct.unpack('<I', footer[idx-4:idx])[0]
                            if v == 8: return "V8A"
                            if 1 <= v <= 12: return f"V{v}"
                        except: pass
                        
                    # Heuristic scan nearby if exact location fails
                    for i in range(max(0, idx-64), min(len(footer)-4, idx+64)):
                        try:
                            val = struct.unpack('<I', footer[i:i+4])[0]
                            if val == 8: return "V8A"
                            if 1 <= val <= 11 and val != 0: return f"V{val}"
                        except: pass
                        
        except Exception as e:
            print(f"Binary detect error: {e}")
        return None

    @staticmethod
    def find_aes_keys_in_binary(binary_path, progress_callback=None):
        """Binary (EXE) dosyasında AES Key formatına uygun hex stringleri arar"""
        import re
        potential_keys = set()
        
        try:
            file_size = os.path.getsize(binary_path)
            # 200 MB'dan büyükse tamamını okumak yavaş olabilir ama key genelde data segmenttedir.
            # Memory mapping daha iyi olabilir ama basit tutalım.
            
            if progress_callback: progress_callback(f"🕵️‍♂️ EXE Analiz Ediliyor: {binary_path.name} ({file_size/1024/1024:.1f} MB)")
            
            # --- KNOWN KEYS INJECTION ---
            # Kullanıcının bulduğu veya bilinen keyleri buraya ekliyoruz.
            manual_injection = [
                "0xA896068444F496956900542A215367688B49B19C2537FCD2743D8585BA1EB128" # Black Myth: Wukong
            ]
            potential_keys.update(manual_injection)
            
            with open(binary_path, "rb") as f:
                content = f.read() 
                
                # 1. Pattern: 0x ile başlayan 64 hex karakter
                # b"0x" + 64 hex
                pattern_0x = re.compile(b"0x([A-Fa-f0-9]{64})")
                for match in pattern_0x.finditer(content):
                    key = "0x" + match.group(1).decode("ascii")
                    potential_keys.add(key)
                    
                # 2. Pattern: Düz 64 hex karakter (Fakat çok fazla false positive verebilir)
                # Bu yüzden sadece 'const char' gibi görünenleri almak lazım ama zor.
                # Şimdilik en yaygın olan 0x'i arayalım.
                # Ek olarak bazı oyunlar düz string tutar.
                pattern_plain = re.compile(b"(?<![A-Fa-f0-9])([A-Fa-f0-9]{64})(?![A-Fa-f0-9])")
                for match in pattern_plain.finditer(content):
                    # Genelde keyler 0-9 ve A-F karışık olur. Sadece 0 veya F ise at.
                    k = match.group(1)
                    if k.count(b'0') > 60 or k.count(b'F') > 60: continue
                    potential_keys.add("0x" + k.decode("ascii"))
                    
        except Exception as e:
            print(f"Gemini key ask error: {e}")
            return None
            
        return list(potential_keys) if potential_keys else None

    @staticmethod
    def ask_user_for_manual_key(game_name):
        """Kullanıcıdan manuel AES Key ister (Subprocess ile Güvenli Dialog)"""
        import textwrap

        # Tkinter'ı ayrı bir süreçte çalıştırarak Thread sorunlarını (CreateDIBSection failed) aşarız.
        # textwrap.dedent ile indentation hatasını önlüyoruz (f-string indentation'ı koda yansıtıyor çünkü)
        input_script = textwrap.dedent(f"""
import tkinter as tk
import webbrowser
import sys

def open_aes_site():
    webbrowser.open("https://illusory.dev/aesdumpster/")

def on_ok(event=None):
    if entry.get():
        print(entry.get().strip())
    else:
        print("NONE")
    root.quit()

def on_cancel(event=None):
    print("NONE")
    root.quit()

def center_window(win):
    win.update_idletasks()
    width = win.winfo_width()
    height = win.winfo_height()
    x = (win.winfo_screenwidth() // 2) - (width // 2)
    y = (win.winfo_screenheight() // 2) - (height // 2)
    win.geometry('{{}}x{{}}+{{}}+{{}}'.format(width, height, x, y))

try:
    root = tk.Tk()
    root.title("AES Key Gerekli - MemoFast")
    root.geometry("450x240")
    root.attributes('-topmost', True)
    
    # Modern look attempt (basic)
    bg_color = "#f0f0f0"
    root.configure(bg=bg_color)

    # 1. Label
    info_text = (f"'{game_name}' için otomatik şifre çözülemedi.\\n"
                 "Lütfen geçerli HEX AES anahtarını girin.")
    lbl = tk.Label(root, text=info_text, justify="center", bg=bg_color, font=("Segoe UI", 10))
    lbl.pack(pady=(15, 5))

    # 2. Online Button
    btn_online = tk.Button(root, text="🌍 Online Key Bulucu (AES Dumpster)", command=open_aes_site, 
                           bg="#2196F3", fg="white", font=("Segoe UI", 9, "bold"), padx=10, pady=5, cursor="hand2")
    btn_online.pack(pady=5)
    
    lbl_hint = tk.Label(root, text="(Siteye oyunun EXE dosyasını sürükleyin ve çıkan kodud kopyalayın)", 
                        font=("Segoe UI", 8), bg=bg_color, fg="#666")
    lbl_hint.pack(pady=(0, 10))

    # 3. Entry
    entry = tk.Entry(root, width=50, font=("Consolas", 10))
    entry.pack(pady=5)
    entry.focus_set()

    # 4. Buttons
    frame_btn = tk.Frame(root, bg=bg_color)
    frame_btn.pack(pady=10)

    btn_ok = tk.Button(frame_btn, text="✅ Kaydet", command=on_ok, width=12, bg="#4CAF50", fg="white", font=("Segoe UI", 9))
    btn_ok.pack(side="left", padx=5)

    btn_cancel = tk.Button(frame_btn, text="❌ İptal", command=on_cancel, width=12, bg="#f44336", fg="white", font=("Segoe UI", 9))
    btn_cancel.pack(side="left", padx=5)

    root.bind('<Return>', on_ok)
    root.bind('<Escape>', on_cancel)
    
    center_window(root)
    root.mainloop()

except Exception as e:
    print("NONE")
""")
        try:
            # Subprocess olarak çalıştır
            result = subprocess.run(
                [sys.executable, "-c", input_script],
                capture_output=True,
                text=True,
                creationflags=subprocess.CREATE_NO_WINDOW # Konsol penceresi açma
            )
            
            # Hata varsa yazdır (Debugging için)
            if result.stderr:
                print(f"Manual Input Logic Stderr: {result.stderr}")
            
            output = result.stdout.strip()
            if output and output != "NONE" and len(output) > 10:
                return output
            return None
            
        except Exception as e:
            print(f"Manual Input Subprocess Error: {e}")
            return None

    @staticmethod
    def find_aes_keys_in_memory(process_name, progress_callback=None):
        """Çalışan oyunun belleğini tarar (RAM Hunter via MemoryTrainer)"""
        try:
            from memory_tool import MemoryTrainer
            trainer = MemoryTrainer()
            
            if progress_callback: progress_callback(f"🧠 Bellek (RAM) Taranıyor: {process_name}...")
            
            # Tarama yap
            candidates = trainer.scan_for_aes_keys(process_name)
            
            if candidates:
                if progress_callback: progress_callback(f"✨ Bellekten {len(candidates)} olası anahtar bulundu!")
                return candidates
            return []
        except Exception as e:
            print(f"RAM Scan Error: {e}")
            return []

    @staticmethod
    def ask_gemini_for_aes_key(game_name, api_key, progress_callback=None):
        """Gemini'ye oyunun AES Key'ini sor"""
        if not api_key: return None
        
        try:
            agent = GeminiTranslator(api_key)
            prompt = (f"I need the AES decryption key (hex string starting with 0x, 64 chars) "
                      f"for the Unreal Engine game '{game_name}'. "
                      f"Respond ONLY with the key if you know it, or 'UNKNOWN'. "
                      f"Start your response with 'KEY: '")
            
            if progress_callback: progress_callback(f"🧠 Gemini'ye Soruluyor: {game_name} AES Key?")
            response = agent.ask(prompt)
            
            if response and "KEY:" in response:
                import re
                key_match = re.search(r"0x[A-Fa-f0-9]{64}", response)
                if key_match:
                    found = key_match.group(0)
                    if progress_callback: progress_callback(f"🧠 Gemini Cevap Verdi: {found}")
                    return found
            
            return None
        except Exception as e:
            print(f"Gemini key ask error: {e}")
            return None

    @staticmethod
    def brute_force_pak_key(pak_path, candidates, progress_callback=None):
        """Aday anahtarları PAK üzerinde dener"""
        repak_exe = PakManager.TOOL_PATH
        
        for i, key in enumerate(candidates):
            if progress_callback: progress_callback(f"🔓 Key Deneniyor ({i+1}/{len(candidates)}): {key[:10]}...")
            
            try:
                # repak info -k KEY "pak"
                cmd = [str(repak_exe), "info", "-k", key, str(pak_path)]
                
                # Windows escape sorunu olmasın diye shell=True DEĞİL, liste veriyoruz.
                result = subprocess.run(cmd, capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW)
                
                # Başarılı ise exit code 0 ve "Encrypted: True/False" yazar (False ise zaten key gerekmezdi)
                # Ama key yanlışsa "Failed to read index" veya "Bad AES Key" verir.
                
                if result.returncode == 0 and "mount point" in result.stdout:
                    return key
            except:
                pass
                
        return None

    @staticmethod
    def process_pak_translation(paks_dir, progress_callback, service="google", service_api_key="", max_workers=10, aes_key=None, game_name=None, ask_aes_key_callback=None, ask_file_callback=None, target_pak_path=None, target_internal_file_path=None, is_encrypted_override=None, progress_max_callback=None, progress_bar_callback=None, manual_review_callback=None, target_lang="tr", backup_enabled=False, source_lang="en"):
        """PAK dizinindeki ana paketi bul, aç, çevir ve paketle"""
        import tempfile
        import time
        import shutil
        
        if progress_callback: progress_callback(f"🔧 Unreal Manager v6 (Manual Oodle Guide) - Gelen AES Key: {aes_key}")
        logger.debug(f"Unreal Manager v6 (Manual Oodle Guide) - Gelen AES Key: {aes_key}")
        
        tools_dir = Config.BASE_PATH / "files" / "tools"
        
        # OODLE DLL OTOMATIK BULMA VE KOPYALAMA
        oodle_found = False
        try:
            oodle_found = PakManager.find_oodle_dll(paks_dir, progress_callback)
        except Exception as e:
            if progress_callback:
                progress_callback(f"⚠️ Oodle arama hatası (devam edilecek): {e}")
        
        # --- PROACTIVE CLEANUP (Kullanıcı İsteği) ---
        # Önceki denemelerden kalmış olabilecek 'unpacked' klasörünü temizle
        trash_path = paks_dir / "unpacked"
        if trash_path.exists() and trash_path.is_dir():
            try:
                shutil.rmtree(str(trash_path))
                if progress_callback: progress_callback(f"🧹 Önceki kalıntılar temizlendi: {trash_path.name}")
            except Exception as e:
                print(f"Cleanup error: {e}")
        
        # 1. PAK Dosyalarını Belirle
        paks_to_check = []
        if target_pak_path:
            if isinstance(target_pak_path, list):
                paks_to_check = [Path(p) for p in target_pak_path if Path(p).exists()]
                if progress_callback: progress_callback(f"📋 {len(paks_to_check)} adet puanlanmış PAK kontrol edilecek.")
            else:
                p_path = Path(target_pak_path)
                if p_path.exists():
                    paks_to_check = [p_path]
        
        # Eğer liste boşsa veya hiç verilmediyse rglob ile tara
        if not paks_to_check:
            paks = list(paks_dir.rglob("*.pak"))
            # _P.pak olanları ele (zaten patch ise)
            paks = [p for p in paks if not p.name.endswith("_P.pak")]
            # Boyuta göre sırala (en büyük en baştadır)
            paks.sort(key=lambda x: x.stat().st_size, reverse=True)
            paks_to_check = paks

        if not paks_to_check: 
             error_msg = f"İşlenecek .pak dosyası bulunamadı!\nAranan Konum: {paks_dir}"
             raise Exception(error_msg)

        # 2. .locres İçeren Doğru PAK'ı Bul (Dinamik Tarama)
        target_pak = None
        
        # Eğer kullanıcı özellikle bir iç dosya seçtiyse, o PAK'ı direkt kullan
        if target_internal_file_path:
             target_pak = paks_to_check[0] if paks_to_check else None
             if progress_callback: progress_callback(f"🎯 Özel dosya seçildi, PAK sabitlendi: {target_pak.name}")
        else:
            if progress_callback: progress_callback("🔍 PAK'lar içinde dil dosyası aranıyor (Öncelik: .locres > /en/ > .csv)...")
            
            fallback_pak = None
            for p_path in paks_to_check:
                if progress_callback: progress_callback(f"📦 Test ediliyor: {p_path.name}")
                
                # repak list ile içeriğe bak
                cmd_list = [str(PakManager.TOOL_PATH), "list", str(p_path)]
                if aes_key:
                    cmd_list.extend(["--aes-key", aes_key])
                
                try:
                    res_list = subprocess.run(cmd_list, capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW, timeout=30)
                    list_out = (res_list.stdout + res_list.stderr).lower()
                    
                    if res_list.returncode != 0:
                        if "encrypted" in list_out or "key" in list_out:
                            if progress_callback: progress_callback(f"🔒 {p_path.name} şifreli ve AES anahtarı yok, içeriği taranamadı.")
                        else:
                            if progress_callback: progress_callback(f"⚠️ {p_path.name} listelenirken hata oluştu (Kod: {res_list.returncode})")
                        continue

                    # 1. KESİN HEDEF (.locres)
                    if ".locres" in list_out:
                        target_pak = p_path
                        if progress_callback: progress_callback(f"✅ Kesin sonuç bulundu! (.locres mevcut): {target_pak.name}")
                        break
                    
                    # 2. GÜÇLÜ ADAYLAR (/en/ klasörü veya .csv)
                    if not fallback_pak:
                        if "/en/" in list_out or ".csv" in list_out:
                            fallback_pak = p_path
                            if progress_callback: progress_callback(f"📍 Aday PAK belirlendi (/en/ veya .csv): {fallback_pak.name}")
                except Exception as e:
                    if progress_callback: progress_callback(f"❌ Tarama hatası ({p_path.name}): {e}")

            # Eğer .locres bulunamadıysa ama aday PAK varsa onu kullan
            if not target_pak and fallback_pak:
                target_pak = fallback_pak
                if progress_callback: progress_callback(f"✨ .locres bulunamadı, en güçlü aday ile devam ediliyor: {target_pak.name}")
            
            # Eğer hiçbir şey bulunamadıysa ilkine (en yüksek puanlıya) dön
            if not target_pak:
                target_pak = paks_to_check[0]
                if progress_callback: progress_callback(f"⚠️ Kritik dosya bulunamadı veya PAK'lar şifreli. Varsayılan (Puanı en yüksek) PAK ile devam ediliyor: {target_pak.name}")

        if progress_callback: 
            progress_callback(f"📏 Seçilen PAK Boyutu: {target_pak.stat().st_size / (1024*1024):.2f} MB")
            
        # PAK Versiyonunu ve Mount Point'i öğren
        # PAK Versiyonunu ve Mount Point'i öğren
        detected_version = "V9" # Default fallback
        detected_mount = "../../../" # Default fallback
        
        # 1. Önce Binary Analiz Dene (Daha güvenilir)
        bin_ver = PakManager.detect_pak_version_binary(target_pak)

        # [FIX] Repak V12 Limitation
        if bin_ver and (bin_ver == 'V12' or (len(bin_ver)>1 and bin_ver[1:].isdigit() and int(bin_ver[1:]) > 11)):
             bin_ver = 'V11'

        if bin_ver:
            detected_version = bin_ver
            if progress_callback: progress_callback(f"ℹ️ Binary Analiz Versiyonu: {detected_version}")
        
        # 2. Repak Info (Mount point için gerekli)
        cmd_info = [str(PakManager.TOOL_PATH), "info", str(target_pak)]
        if aes_key:
            clean_key = aes_key.replace("0x", "").replace("0X", "").strip()
            cmd_info.extend(["--aes-key", clean_key])
            
        res_info = subprocess.run(cmd_info, capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW)
        
        # [FIX] Değişkenleri hata durumuna karşı önceden tanımlıyoruz
        detected_seed = None
        detected_mount = "../../../" 

        if res_info.returncode == 0:
            import re
            m_match = re.search(r"mount point:\s*(.+)", res_info.stdout)
            
            # Eğer binary bulamadıysa buradan al
            if not bin_ver:
                v_match = re.search(r"version:\s*(V[A-Z0-9]+)", res_info.stdout)
                if v_match: detected_version = v_match.group(1)
            
            # [FIX] Path Hash Seed Detection (Robust Line-by-Line)
            
            for line in res_info.stdout.splitlines():
                line = line.strip()
                if "mount point:" in line:
                    detected_mount = line.split(":", 1)[1].strip()
                
                if "path hash seed:" in line and "Some" in line:
                   # Otomatik algılamayı deniyoruz ama hata ihtimaline karşı:
                   # KESİN DOĞRU DEĞERİ (D5AB099B -> 3584854427) DEFAULT OLARAK ZORLUYORUZ
                   # Eğer okunan değer farklıysa bile, orijinalin bu olduğunu bildiğimiz için bunu kullanacağız.
                   detected_seed = "3584854427" 
                   if progress_callback: progress_callback(f"🔑 Hash Seed Zorlandı: 3584854427 (0xD5AB099B)")

            if progress_callback:
                progress_callback(f"ℹ️ Detected Mount Point: '{detected_mount}'")


                
            # --- AES ENCRYPTION CHECK & AUTO HUNT ---
            is_encrypted = "encrypted index: true" in res_info.stdout.lower()
            if is_encrypted:
                if progress_callback: progress_callback("🔒 Dosya Şifreli (AES Encrypted)")
                
                # Eğer kullanıcı key vermediyse AV BAŞLASIN
                if not aes_key:
                    if progress_callback: progress_callback("🕵️‍♂️ AES Key Araniyor (Auto Hunter v1.0)...")
                    
                    found_key = None
                    try:
                        # Oyun EXE'sini bul (Binaries içinde)
                        game_root = paks_dir.parent.parent # paks/content/Game -> GameRoot
                        exe_candidates = list(game_root.rglob("*.exe"))
                        # En büyük exe shipping exe'dir
                        if exe_candidates:
                            exe_candidates.sort(key=lambda x: x.stat().st_size, reverse=True)
                            target_exe = exe_candidates[0]
                            
                            # TARA
                            candidates = PakManager.find_aes_keys_in_binary(target_exe, progress_callback)
                            if candidates:
                                if progress_callback: progress_callback(f"🧪 {len(candidates)} adet aday anahtar test ediliyor...")
                                found_key = PakManager.brute_force_pak_key(target_pak, candidates, progress_callback)
                    except Exception as e:
                        print(f"Key hunt error: {e}")
                        
                    if found_key:
                        aes_key = found_key
                        if progress_callback: progress_callback(f"🎉 KEY BULUNDU: {aes_key}")
                    else:
                        if progress_callback: progress_callback("⚠️ Key otomatik bulunamadı, Gemini'ye sorulacak...")
        else:
             if progress_callback: progress_callback("⚠️ PAK mount point okunamadı, varsayılan (../../../) kullanılacak.")
        
        if progress_callback:
            progress_callback("⏳ Dosya açılıyor (Unpack)...")
            
        start_time = time.time()
        temp_dir = tempfile.mkdtemp()
        try:
            temp_path = Path(temp_dir)
            
            # Repak Fix: PAK'ı kendi yanına kopyala (Unique Temp Name)
            temp_pak_path = Path(temp_dir) / f"temp_{int(time.time())}.pak"
            
            # Kopyala
            shutil.copy2(target_pak, temp_pak_path)
            
            # Temp içinde 'unpacked' klasörü
            unpack_dir = temp_path / "unpacked"
            
            # RETRY LOOP (Şifreleme hatası durumunda tekrar denemek için)
            max_attempts = 2
            current_attempt = 0
            
            while current_attempt < max_attempts:
                current_attempt += 1
                
                if progress_callback: progress_callback(f"🔓 Paket açılıyor (Deneme {current_attempt})... Bu işlem pak boyutuna göre zaman alabilir.")
                
                # UNPACK (--force ile Oodle hatasını atla)
                cmd_unpack = [
                    str(PakManager.TOOL_PATH), 
                    "unpack", 
                    str(temp_pak_path), 
                    "-o", 
                    str(unpack_dir),
                    "--force"
                ]
                
                # KEY VARSA EKLE (Global argüman olduğu için komuttan önce eklenmeli)
                if aes_key:
                    # Hex format düzeltme (0x varsa kaldır)
                    clean_key = aes_key.replace("0x", "").replace("0X", "").strip()
                    
                    # repak.exe --aes-key KEY unpack ...
                    cmd_unpack.insert(1, "--aes-key")
                    cmd_unpack.insert(2, clean_key)
                
                process = subprocess.Popen(
                    cmd_unpack, 
                    stdout=subprocess.PIPE, 
                    stderr=subprocess.PIPE, 
                    text=True, 
                    encoding='utf-8', 
                    errors='replace',
                    creationflags=subprocess.CREATE_NO_WINDOW
                )
                try:
                    stdout, stderr = process.communicate(timeout=300)
                except subprocess.TimeoutExpired:
                    process.kill()
                    # Kalan çıktıları al (gerekirse)
                    try:
                        stdout, stderr = process.communicate(timeout=5)
                    except:
                        stdout, stderr = "", ""
                    try: temp_pak_path.unlink(missing_ok=True)
                    except: pass
                    raise Exception("Unpack işlemi zaman aşımına uğradı (5 dakika).")
                
                # Temizlik (Loop içinde silme, retry için kalsın. Loop sonunda silinecek)
                # try: temp_pak_path.unlink(missing_ok=True)
                # except: pass
                
                if process.returncode != 0:
                    err_msg = (stdout + stderr).lower()
                    
                    # 0. ŞİFRELEME HATASI VE AUTO-HUNT (YENİ)
                    if ("encrypted" in err_msg or "version unsupported" in err_msg) and not aes_key and current_attempt == 1:
                        if progress_callback: 
                            progress_callback("🔒 Şifreleme Tespit Edildi! Önce bilinen anahtarlar deneniyor...")
                        
                        found_key = None
                        
                        # --- PRIORITY KEY CHECK (WUKONG FIX) ---
                        priority_keys = [
                            "0xA896068444F496956900542A215367688B49B19C2537FCD2743D8585BA1EB128", # Manus AI Research (New)
                            "0x3bfa9cc97da10598521b342961df8f5f68c7388fa117345eeb516eaa837bb4d6"  # Old Candidate (Backup)
                        ]
                        
                        found_priority_key = False
                        for pk in priority_keys:
                             if PakManager.brute_force_pak_key(target_pak, [pk], progress_callback):
                                 aes_key = pk
                                 found_key = pk
                                 found_priority_key = True
                                 if progress_callback: progress_callback(f"🚀 Bilinen Key Çalıştı: {pk}")
                                 break
                        
                        if found_priority_key:
                            continue # Döngü başına dön ve unpack yap


                        # --- 1. AES LIST JSON KONTROLÜ (YENİ) ---
                        if progress_callback: 
                            progress_callback("📚 AES Listesi Kontrol Ediliyor (aes_list.json)...")
                        
                        try:
                            aes_json_path = Config.BASE_PATH / "files" / "tools" / "aes_list.json"
                            found_json_key = None
                            
                            if aes_json_path.exists():
                                # Oyun Adını Tahmin Et
                                paks_path_parts = paks_dir.parts
                                # Genelde: steamapps/common/OyunAdi/Content/Paks
                                # OyunAdi'ni bulmak için 'common'dan sonraki ilk klasörü veya Paks'tan 2-3 önceki klasörü alabiliriz
                                estimated_game_name = ""
                                
                                # Yöntem 1: Klasör adlarından meaningful olanı seç
                                ignore = ["paks", "content", "binaries", "win64", "game", "engine", "common", "steamapps"]
                                for part in reversed(paks_path_parts):
                                    if part.lower() not in ignore and len(part) > 2:
                                        estimated_game_name = part
                                        break
                                
                                if progress_callback: progress_callback(f"🕹️ Tahmin Edilen Oyun Adı: {estimated_game_name}")

                                with open(aes_json_path, 'r', encoding='utf-8') as f:
                                    data = json.load(f)
                                    
                                    # JSON içinde ara (Basit "in" kontrolü veya tam eşleşme)
                                    for key_name, key_val in data.items():
                                        # Basit normalizasyon
                                        norm_key = key_name.lower().replace(":", "").replace("-", "").replace(" ", "")
                                        
                                        # 1. PASSED GAME NAME (GUI'den gelen tam isim) - EN YÜKSEK ÖNCELİK
                                        if game_name:
                                            norm_passed = game_name.lower().replace(":", "").replace("-", "").replace(" ", "")
                                            # "Black Myth: Wukong" -> "blackmythwukong" == "blackmythwukong"
                                            if norm_passed == norm_key or norm_passed in norm_key or norm_key in norm_passed:
                                                found_json_key = key_val
                                                if progress_callback: progress_callback(f"✨ TAM İSİM Eşleşmesi: {key_name} (GUI: {game_name})")
                                                break
                                        
                                        # 2. ESTIMATED NAME (Klasörden tahmin) - YEDEK
                                        norm_est = estimated_game_name.lower().replace(":", "").replace("-", "").replace(" ", "")
                                        if norm_est and (norm_est in norm_key or norm_key in norm_est):
                                            found_json_key = key_val
                                            if progress_callback: progress_callback(f"✨ Klasör Tahmini Eşleşmesi: {key_name}")
                                            break
                            
                            if found_json_key:
                                if progress_callback: progress_callback(f"🗝️ Key Deneniyor: {found_json_key[:10]}...")
                                if PakManager.brute_force_pak_key(target_pak, [found_json_key], progress_callback):
                                     aes_key = found_json_key
                                     found_key = found_json_key
                                     if progress_callback: progress_callback(f"🎉 JSON Key Çalıştı!")
                                     
                        except Exception as e:
                            print(f"JSON check error: {e}")

                        if found_key:
                            continue # Döngü başına dön

                        # --- 2. MANUEL PROMPT (EĞER HİÇBİRİ ÇALIŞMAZSA) ---
                        if progress_callback: 
                           # progress_callback("🕵️‍♂️ Bilinen keyler başarısız. Auto Hunter v2 başlatılıyor...")
                           pass

                        
                        found_key = None
                        

                        # --- OTOMATİK TARAMA DEVRE DIŞI BIRAKILMIŞTI, ONUN YERİNE MANUEL SOR ---
                        pass


                        if False:
                             pass
                        
                        # Eğer yukarıdaki bloklar (priority, auto-hunt) key bulamazsa:
                        if not found_key:
                             # game_name belirle (Fallback)
                             try:
                                 game_name = paks_dir.parts[-3] 
                             except:
                                 game_name = "Unknown Game"
                                 
                             if progress_callback: progress_callback("⚠️ AES Key otomatik bulunamadı. Kullanıcıya soruluyor...")
                             
                             manual_key = PakManager.ask_user_for_manual_key(game_name)
                             if manual_key:
                                 if PakManager.brute_force_pak_key(target_pak, [manual_key], progress_callback):
                                     found_key = manual_key
                        
                        if found_key:
                            aes_key = found_key
                            if progress_callback: progress_callback(f"🎉 KEY BULUNDU ve Eklendi: {aes_key}")
                            continue # DÖNGÜYÜ BAŞA SAR VE TEKRAR DENE
                        else:
                            # Bulunamadıysa hata ver
                            # Arayüzün yakalaması için özel kod
                            if progress_callback: progress_callback("⛔ AES Key Bulunamadı! Kullanıcıdan istenmesi gerekiyor.")
                            try: temp_pak_path.unlink(missing_ok=True)
                            except: pass
                            raise Exception("AES_REQUIRED_BY_USER")

                    # 1. Oodle DLL Eksik Hatası (ÖZEL YAKALAMA)
                    if "oo2core" in err_msg and "not found" in err_msg:
                        clean_err = "🔴 EKSİK DOSYA HATASI: 'oo2core_9_win64.dll' (veya benzeri)\n\n"
                        clean_err += "Bu oyun Oodle sıkıştırması kullanıyor ancak gerekli kütüphane bulunamadı.\n"
                        clean_err += "Otomatik arama (oyun klasörü ve Steam kütüphanesi) da sonuç vermedi.\n\n"
                        clean_err += "✅ SON ÇARE (MANUEL İNDİRME):\n"
                        clean_err += "1. Google'da şu ifadeyi aratın: 'oo2core_9_win64.dll download'\n"
                        clean_err += "2. İndirdiğiniz dosyayı şu klasöre atın: \n"
                        clean_err += f"   {Config.BASE_PATH / 'files' / 'tools'}\n"
                        clean_err += "3. Tekrar başlatın."
                        try: temp_pak_path.unlink(missing_ok=True)
                        except: pass
                        raise Exception(clean_err)
                    
                    # 2. Oodle Hash Uyumsuzluğu (ÖZEL YAKALAMA)
                    if "oodle hash mismatch" in err_msg:
                        clean_err = "🔴 OODLE DLL UYUMSUZLUĞU\n\n"
                        clean_err += "Mevcut 'oo2core_9_win64.dll' dosyası, Repak'ın beklediği versiyonla uyuşmuyor (Hash Hatası).\n"
                        clean_err += "Repak, bu dosyanın bozuk veya yanlış versiyon olduğunu tespit etti.\n\n"
                        clean_err += "✅ ÇÖZÜM:\n"
                        clean_err += f"1. Şu dosyayı SİLİN: {Config.BASE_PATH / 'files' / 'tools' / 'oo2core_9_win64.dll'}\n"
                        clean_err += "2. İşlemi tekrar başlatın.\n" 
                        clean_err += "   (Repak doğru dosyayı internetten indirmeyi deneyebilir veya temiz bir dosya bulmanız gerekebilir.)"
                        try: temp_pak_path.unlink(missing_ok=True)
                        except: pass
                        raise Exception(clean_err)
                    
                    # Diğer hatalar
                    try: temp_pak_path.unlink(missing_ok=True)
                    except: pass
                    raise Exception(f"Repak Hatası (Unpack):\n{stderr}\n{stdout}")
                
                # Başarılı ise döngüden çık
                break
            
            # UNPACK BAŞARISINI KONTROL ET
            # Loop bitti, dosya artık silinebilir (Başarılı veya başarısız)
            try: temp_pak_path.unlink(missing_ok=True)
            except: pass
            
            if not unpack_dir.exists() or not any(unpack_dir.iterdir()):
                if progress_callback: 
                    progress_callback("⚠️ PAK dosyası açıldı ama içi boş görünüyor.")
                    progress_callback("🔒 Bu durum genellikle Şifreleme Anahtarı (AES Key) yanlış veya eksik olduğunda yaşanır.")
                
                # Eğer şifreleme hatası tespit edilirse manuel key iste
                if not aes_key:
                    raise Exception("AES_REQUIRED_BY_USER")
                else:
                    raise Exception("Verilen AES Key ile dosya açılamadı (Key yanlış olabilir).")

            # LOCRES & CSV BULMA (Gelismis Secim)
            all_locres = list(unpack_dir.rglob("*.locres")) + list(unpack_dir.rglob("*.csv"))
            
            # Debug: Ne çıktı?
            if not all_locres:
                if progress_callback: progress_callback("📂 PAK içeriği listeleniyor (Locres/CSV bulunamadı)...")
                raise Exception("PAK içinde dil dosyası (.locres veya .csv) bulunamadı!")
                
            selected_files = []
            
            # 1. KULLANICI GUI PANELINDEN BIR SEY SECTI MI (target_internal_file_path)
            if target_internal_file_path:
                if progress_callback: progress_callback(f"🖱️ Kullanıcı Özel Seçimi Algılandı...")
                if isinstance(target_internal_file_path, list):
                    selections = target_internal_file_path
                else:
                    selections = [s.strip() for s in target_internal_file_path.split(",")]
                    
                for sel in selections:
                    for loc in all_locres:
                        if sel.lower() in str(loc).lower():
                            if loc not in selected_files:
                                selected_files.append(loc)
            
            # 2. SECIM GELMEDIYSE ARAYUZE (GUI) SOR (ask_file_callback)
            if not selected_files and ask_file_callback:
                if progress_callback: progress_callback("🔄 Kullanıcının yan panelden seçimi dikkate alınıyor...")
                choices = [str(p.relative_to(unpack_dir)) for p in all_locres]
                try:
                    user_chosen_paths = ask_file_callback(choices)
                    if user_chosen_paths:
                        if isinstance(user_chosen_paths, str): user_chosen_paths = [user_chosen_paths]
                        for c in user_chosen_paths:
                            for p in all_locres:
                                if str(p.relative_to(unpack_dir)) == c:
                                    selected_files.append(p)
                except Exception as e:
                    print(f"Callback err: {e}")
            
            # 3. YINE DE SECILMEDIYSE (TUM INGILIZCELERI AL)
            if not selected_files:
                if progress_callback: progress_callback("⚠️ Özel seçim yapılmadı, dosyalar otomatik taranıyor...")
                for f in all_locres:
                    path_str = str(f).replace("\\", "/").lower()
                    if "/en/" in path_str or "/english/" in path_str or "/en-us/" in path_str:
                        if "/engine/" not in path_str:
                            selected_files.append(f)
                            
                # İngilizce adlı özel bir klasör yoksa hepsini veya en büyüğünü al
                if not selected_files and all_locres:
                     selected_files = all_locres

            if not selected_files:
                raise Exception("İşlenecek locres veya csv dosyası seçilemedi/bulunamadı.")

            if progress_callback: 
                progress_callback(f"📂 İşleme Alınacak Dil Dosyası Sayısı: {len(selected_files)}")
            
            # --- SEÇİLEN TÜM DOSYALARI SIRAYLA ÇEVİR ---
            for idx, target_locres in enumerate(selected_files):
                if progress_callback: 
                    progress_callback(f"📝 ({idx+1}/{len(selected_files)}) Çevriliyor: {target_locres.name} ({target_locres.parent.name})")
                
                succ = process_locres_file(
                    target_locres, 
                    progress_callback, 
                    is_pak_temp=True, 
                    service=service, 
                    api_key=service_api_key, 
                    max_workers=max_workers, 
                    progress_max_callback=progress_max_callback, 
                    progress_bar_callback=progress_bar_callback, 
                    manual_review_callback=manual_review_callback, 
                    target_lang=target_lang,
                    source_lang=source_lang
                )
                if not succ:
                    if progress_callback: progress_callback(f"⚠️ Dosya tam çevrilemedi: {target_locres.name}")
                else:
                    if progress_callback: progress_callback(f"✅ Başarılı: {target_locres.name}")

            if progress_callback: progress_callback(f"✨ Tüm seçili dil dosyaları başarıyla güncellendi!")

            # --- PAKETLEME ÖNCESİ TEMİZLİK (FINAL CLEANUP) ---
            # Unpack klasöründe kalan tüm .csv ve gereksiz dosyaları sil.
            # Sadece orijinal oyun dosyaları kalsın.
            if progress_callback: progress_callback("🧹 Paketleme öncesi son temizlik yapılıyor...")
            try:
                for junk in unpack_dir.rglob("*"):
                    if junk.is_file():
                        if junk.suffix.lower() in [".csv", ".txt", ".log", ".bak", ".tmp"]:
                            junk.unlink()
                if progress_callback: progress_callback("✅ Gereksiz dosyalar (CSV, Log vb.) temizlendi.")
            except Exception as e_clean:
                print(f"Final cleanup error: {e_clean}")

            # --- FONT INJECTION (TURKISH CHAR FIX) ---
            font_source = Config.BASE_PATH / "files" / "tools" / "fonts" / "Roboto-Regular.ttf"
            if font_source.exists():
                if progress_callback: progress_callback("🔤 Türkçe Font Enjekte Ediliyor...")
                
                # Hedef: Engine/Content/Slate/Fonts/
                font_target_dir = unpack_dir / "Engine" / "Content" / "Slate" / "Fonts"
                
                try:
                    font_target_dir.mkdir(parents=True, exist_ok=True)
                    
                    # Copy and Rename
                    shutil.copy2(font_source, font_target_dir / "Roboto-Regular.ttf")
                    shutil.copy2(font_source, font_target_dir / "Roboto-Bold.ttf") # Bold'u da ez
                    
                    if progress_callback: progress_callback("✅ Font dosyaları kopyalandı (Roboto-Regular & Bold).")
                except Exception as e_font:
                    print(f"Font inject error: {e_font}")
                    if progress_callback: progress_callback(f"⚠️ Font yüklenirken hata: {e_font}")
            
            # --- TAM YAMA MODU (Full Repack) ---
            if progress_callback: progress_callback("📦 Tam Paketleme Modu: Tüm dosyalar korunuyor...")
            
            # --- OTOMATİK SIKIŞTIRMA TESPİTİ (COMPRESSION DETECTION) ---
            detected_compression = "Zlib" # Default
            if res_info.returncode == 0:
                stdout_lower = res_info.stdout.lower()
                if "oodle" in stdout_lower:
                    detected_compression = "Oodle"
                elif "zlib" in stdout_lower:
                    detected_compression = "Zlib"
                elif "compressed: false" in stdout_lower:
                    detected_compression = "None"

            # Oodle kontrolü (DLL yoksa Zlib'e düş)
            if detected_compression == "Oodle":
                oodle_dll = tools_dir / "oo2core_9_win64.dll"
                if not oodle_dll.exists():
                    if progress_callback: progress_callback("⚠️ Oodle DLL bulunamadı, Zlib kullanılacak.")
                    detected_compression = "Zlib"

            if progress_callback: progress_callback(f"📦 Sıkıştırma Modu: {detected_compression}")

            # --- PAKETLEME (REPACK) ---
            # [YENİ] Kullanıcı isteği: Nasıl çıkardıysa öyle paketlemeli, tüm dosyaları koru.
            # Sterilizasyon bloğu (sadece locres bırakma) TAMAMEN kaldırıldı.
            
            if progress_callback: progress_callback(f"📦 Oyun dosyaları paketleniyor ({detected_compression})...")
            
            pack_source_dir = unpack_dir
            repack_pak_name = target_pak.name
            temp_repack_output = temp_path / repack_pak_name
            
            cmd_pack = [
                str(PakManager.TOOL_PATH), 
                "pack", 
                str(pack_source_dir), 
                str(temp_repack_output),
                "--version", detected_version,
                "--mount-point", detected_mount, 
                "--compression", detected_compression
            ]
            
            if detected_seed:
                cmd_pack.append("--path-hash-seed")
                cmd_pack.append(detected_seed)
                
            try:
                res_pack = subprocess.run(cmd_pack, capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW)
                if res_pack.returncode != 0:
                     raise Exception(f"Repak Hatası:\n{res_pack.stderr}")
            except Exception as e:
                raise e

            # 4. DOSYA YERLEŞİMİ (ORİJİNAL ÜZERİNE YAZMA)
            # [YENİ] Kullanıcı isteği: _P.pak patch yerine doğrudan orijinal üzerine (Yedek alındığını varsayıyoruz)
            if progress_callback: progress_callback(f"🚚 Orijinal PAK dosyası güncelleniyor: {target_pak.name}")
            
            try:
                # Orijinal dosyayı yedekle (Kullanıcı seçeneğine göre)
                if backup_enabled:
                    backup_pak = target_pak.with_suffix(target_pak.suffix + ".bak")
                    if not backup_pak.exists():
                        if progress_callback: progress_callback(f"🛡️ Güvenlik Yedeği Oluşturuluyor: {backup_pak.name}")
                        shutil.copy2(target_pak, backup_pak)
                else:
                    if progress_callback: progress_callback("⏩ Yedekleme devre dışı, doğrudan üzerine yazılıyor.")
                
                # Orijinal dosyayı sil ve yenisini taşı
                if target_pak.exists(): target_pak.unlink()
                shutil.move(str(temp_repack_output), str(target_pak))
                
                if progress_callback: progress_callback(f"✅ Orijinal dosya yamalandı: {target_pak.name}")
                    
            except Exception as e:
                raise Exception(f"Dosya taşıma hatası: {e}")
            
            end_time = time.time()
            duration = end_time - start_time
            
            if progress_callback:
                progress_callback(f"✅ ÇEVİRİ BAŞARIYLA TAMAMLANDI!")
                progress_callback(f"📍 Dosya: {target_pak.name}")
                progress_callback(f"⏱️ Süre: {duration:.2f} saniye")
                
            return str(target_pak)
        finally:
            # Temizlik (Hata alsa bile programın devam etmesini sağlar)
            try:
                shutil.rmtree(temp_dir, ignore_errors=True)
            except:
                pass


            # --- ESKİ KODLAR (DEVRE DIŞI) ---
            # ...

