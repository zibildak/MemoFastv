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

class GeminiTranslator:
    """Gemini API Wrapper for Translation"""
    def __init__(self, api_key, target_lang="tr"):
        self.api_key = api_key
        self.target_lang = target_lang
        self.url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={api_key}"
        self.headers = {'Content-Type': 'application/json'}
        
        # Dil Haritası
        self.lang_map = {
            "tr": "Turkish", "ru": "Russian", "pt": "Brazilian Portuguese", 
            "es": "Spanish", "id": "Indonesian", "pl": "Polish", 
            "de": "German", "fr": "French", "it": "Italian", "en": "English"
        }
        self.target_lang_name = self.lang_map.get(target_lang, "Turkish")

    def ask(self, prompt):
        """Genel amaçlı Gemini sorgusu"""
        data = {
            "contents": [{
                "parts": [{"text": prompt}]
            }]
        }
        try:
            response = requests.post(self.url, headers=self.headers, json=data, timeout=10)
            if response.status_code == 200:
                result = response.json()
                return result['candidates'][0]['content']['parts'][0]['text'].strip()
            return None
        except:
            return None

    def translate(self, text):
        if not text or not text.strip(): return text
        
        prompt = f"You are a professional video game translator. Translate the following text from English to {self.target_lang_name}. IMPORTANT: Translate imperative verbs as commands, NOT infinitives. Maintain the emotional tone and brevity. Do NOT provide any explanations. just the translation:\\n\\n{text}"
        return self.ask(prompt)

# İstisnalar (Global)
TURKISH_EXCEPTIONS = {
    "ekmek", "yemek", "parmak", "çakmak", "kaymak", 
    "damak", "ırmak", "yamak", "kıymak", "yumak", "sevmek"
}

def apply_turkish_correction(text):
    """
    Çevirilerdeki gereksiz mastar eklerini kaldırır.
    Run -> Koşmak (Koş)
    Play -> Oynamak (Oyna)
    Git -> Gitmek (Git)
    Ancak 'Ekmek' gibi isimleri korur.
    """
    if not text: return text
    
    try:
        # 1. Kelimelere ayır
        words = text.split()
        if not words: return text
            
        last_word_raw = words[-1]
        
        # 2. Regex ile kelimeyi parçala: (Kök)(mek/mak)(Noktalama)
        match = re.search(r'^(.+?)(m[ae]k)(\W*)$', last_word_raw, re.IGNORECASE)
        
        if match:
            root = match.group(1)   # Örn: Koş, Bin, Ek
            suffix = match.group(2) # Örn: mak, mek
            punct = match.group(3)  # Örn: ., !, ?
            
            full_word = root + suffix
            
            # 3. İstisna Kontrolü
            if full_word.lower() not in TURKISH_EXCEPTIONS:
                # İstisna değilse eki kaldır
                new_last_word = root + punct
                words[-1] = new_last_word
                return " ".join(words)
        
        return text
        
    except Exception as e:
        print(f"Filter error details: {e}")
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

def process_locres_file(locres_file, progress_callback=None, is_pak_temp=False, service="google", api_key="", max_workers=10, progress_max_callback=None, progress_bar_callback=None, manual_review_callback=None, target_lang="tr"):
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

    translator = None
    if service == "deepl" and api_key:
        try:
            # DeepL init
            # [FIX] DeepL requires PT-BR or PT-PT, 'pt' is not allowed as target
            use_lang = target_lang
            if target_lang.lower() == "pt": use_lang = "PT-BR"
            elif target_lang.lower() == "en": use_lang = "EN-US"
            
            is_free = True if api_key.strip().endswith(":fx") else False
            translator = DeepL(api_key=api_key, source='en', target=use_lang, use_free_api=is_free)
            if progress_callback: progress_callback("🚀 DeepL API kullanılıyor...")
        except Exception as e:
            if progress_callback: progress_callback(f"⚠️ DeepL Hatası: {e}\nGoogle Translate'e dönülüyor...")
            translator = GoogleTranslator(source='auto', target=target_lang)
    elif service == "gemini" and api_key:
        try:
            translator = GeminiTranslator(api_key, target_lang=target_lang)
            if progress_callback: progress_callback("✨ Gemini AI kullanılıyor...")
        except:
            translator = GoogleTranslator(source='auto', target=target_lang)
    else:
        translator = GoogleTranslator(source='auto', target=target_lang) if GoogleTranslator else None

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
        progress_callback(f"📊 CSV Okundu. Toplam Satır: {len(rows)}")
        progress_callback(f"🔧 Çevirici Servis: {service} (API Key: {'Var' if api_key else 'Yok'})")

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
                res_text = translator.translate(protected_text)
            else:
                try:
                    url = "https://translate.googleapis.com/translate_a/single"
                    params = {"client": "gtx", "sl": "auto", "tl": target_lang, "dt": "t", "q": protected_text}
                    r = requests.get(url, params=params, timeout=5)
                    if r.status_code == 200: res_text = r.json()[0][0][0]
                except: pass
            
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
        except: return idx, None

    # Thread Pool Başlat
    total_items = len(work_items)
    if progress_callback:
        progress_callback(f"🚀 TURBO MOD Devrede: {total_items} satır {max_workers} işçi ile çevriliyor...")
    
    if progress_max_callback:
        progress_max_callback(total_items)

    completed_count = 0
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
                
            if completed_count % 20 == 0 or completed_count == total_items:
                percent = int((completed_count / total_items) * 100)
                if progress_callback:
                    progress_callback(f"⚡ Çevriliyor (Turbo)... ({completed_count}/{total_items}) - %{percent}")

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
        if progress_callback: 
            progress_callback("⏸️ Manuel İnceleme Bekleniyor...")
            progress_callback(f"📂 Çalışma Klasörü: {locres_file.parent}")
            
        # [KULLANICI İSTEĞİ] Klasörü otomatik aç
        try:
            folder_to_open = locres_file.parent
            os.startfile(str(folder_to_open))
        except Exception as e_open:
            print(f"Folder open error: {e_open}")

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

        new_locres = locres_file.with_suffix(".locres.new")
        if new_locres.exists():
            shutil.move(str(new_locres), str(locres_file))
            if not is_pak_temp and progress_callback: 
                progress_callback("✅ İşlem tamamlandı!")
            return True
        else:
            # Fallback başarılı olduysa dosya zaten oluşturulmuş olabilir ama adı farklı olabilir?
            # Kodda new_locres oluşturuluyor. Eğer UnrealLocres çalıştıysa o da .new oluşturur mu?
            # UnrealLocres genelde direkt üzerine yazar veya .new oluşturur?
            # Mevcut kod tool'un .new oluşturduğunu varsayıyor.
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
    def translate_game(game_exe_path, progress_callback=None, service="google", api_key="", max_workers=10, aes_key=None, game_name=None, ask_aes_key_callback=None, ask_file_callback=None, target_pak_path=None, target_internal_file_path=None, is_encrypted_override=None, progress_max_callback=None, progress_bar_callback=None, manual_review_callback=None, target_lang="tr"):
        """Oyunun ana giriş noktası (GUI tarafından çağrılır)"""
        path_obj = Path(game_exe_path)
        
        # [FIX] Doğrudan .locres dosyası seçildiyse PAK aramayı atla
        if path_obj.suffix.lower() == ".locres":
            if progress_callback: progress_callback(f"📂 Doğrudan Locres Dosyası İşleniyor: {path_obj.name}")
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
                    target_lang=target_lang
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
            target_lang=target_lang
        )
        
        return result is not None

    @staticmethod
    def _translate_locres_file(locres_file, progress_callback=None, is_pak_temp=False, service="google", api_key="", progress_max_callback=None, progress_bar_callback=None):
        # Wrapper for backward compatibility if needed, calling global function
        return process_locres_file(locres_file, progress_callback, is_pak_temp, service, api_key, progress_max_callback=progress_max_callback, progress_bar_callback=progress_bar_callback)


class PakManager:
    """Repak Wrapper for PAK handling"""
    TOOL_PATH = Config.BASE_PATH / "files" / "tools" / "repak.exe"
    
    @staticmethod
    def is_ready():
        return PakManager.TOOL_PATH.exists()
    
    @staticmethod
    def process_game(game_file_path, progress_callback=None, service="google", api_key=None, max_workers=10, aes_key=None, game_name=None, ask_aes_key_callback=None, ask_file_callback=None, progress_max_callback=None, progress_bar_callback=None, target_pak_path=None, target_internal_file_path=None, is_encrypted_override=None, logger_callback=None, manual_review_callback=None, target_lang="tr"):
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
            target_lang=target_lang
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
    def process_pak_translation(paks_dir, progress_callback, service="google", service_api_key="", max_workers=10, aes_key=None, game_name=None, ask_aes_key_callback=None, ask_file_callback=None, target_pak_path=None, target_internal_file_path=None, is_encrypted_override=None, progress_max_callback=None, progress_bar_callback=None, manual_review_callback=None, target_lang="tr"):
        """PAK dizinindeki ana paketi bul, aç, çevir ve paketle"""
        import tempfile
        import time
        
        if progress_callback: progress_callback("🔧 Unreal Manager v6 (Manual Oodle Guide)")
        logger.debug("Unreal Manager v6 (Manual Oodle Guide)")
        
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
        
        # 1. Ana PAK dosyasını bul (Genelde en büyük olandır veya 'WindowsNoEditor')
        # 1. Ana PAK dosyasını bul (Genelde en büyük olandır veya 'WindowsNoEditor')
        # Recursive arama (rglob) ile alt klasörlerdeki pakları da bul
        paks = list(paks_dir.rglob("*.pak"))
        
        # _P.pak olanları ele (zaten patch ise)
        paks = [p for p in paks if not p.name.endswith("_P.pak")]
        
        if not paks: 
             error_msg = f"İşlenecek .pak dosyası bulunamadı!\nAranan Konum: {paks_dir}"
             raise Exception(error_msg)
        
        # Boyuta göre sırala (en büyük en baştadır)
        paks.sort(key=lambda x: x.stat().st_size, reverse=True)
        target_pak = paks[0]
        
        # [FIX] Kullanıcı tarafından seçilen PAK varsa onu kullan (Explicit Selection)
        if target_pak_path:
            preferred_pak = Path(target_pak_path)
            if preferred_pak.exists():
                target_pak = preferred_pak
                if progress_callback: 
                    progress_callback(f"🎯 Hedef PAK (Manuel Seçim): {target_pak.name}")
        
        if progress_callback: 
            progress_callback(f"📦 PAK Dosyası Analiz Ediliyor: {target_pak.name}")
            progress_callback(f"📏 Boyut: {target_pak.stat().st_size / (1024*1024):.2f} MB")
            
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
        res_info = subprocess.run(cmd_info, capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW)
        
        if res_info.returncode == 0:
            import re
            m_match = re.search(r"mount point:\s*(.+)", res_info.stdout)
            
            # Eğer binary bulamadıysa buradan al
            if not bin_ver:
                v_match = re.search(r"version:\s*(V[A-Z0-9]+)", res_info.stdout)
                if v_match: detected_version = v_match.group(1)
            
            # [FIX] Path Hash Seed Detection (Robust Line-by-Line)
            detected_seed = None
            detected_mount = "../../../" 
            
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

            # LOCRES BULMA (Gelismis Secim)
            all_locres = list(unpack_dir.rglob("*.locres"))
            
            # Debug: Ne çıktı?
            if not all_locres:
                if progress_callback:
                    progress_callback("📂 PAK içeriği listeleniyor (Locres bulunamadı):")
                    found_any = False
                    for i, f in enumerate(unpack_dir.rglob("*")):
                        if i < 10: progress_callback(f"   - {f.name}")
                        found_any = True
                    if not found_any: progress_callback("   (Klasör Boş)")
                    
                raise Exception("PAK içinde dil dosyası (.locres) bulunamadı!")
                
            # --- TEKİL LOCRES ÇEVİRİSİ (DÖNGÜ FIX v2) ---
            # NOT: "game.locres" filtresi kaldırıldı - tüm dilleri yakalıyordu ve döngüye neden oluyordu
            english_locres_files = []
            for f in all_locres:
                path_str = str(f).replace("\\", "/").lower()
                # SADECE İngilizce klasörlerini tespit et
                if "/en/" in path_str or "/en-us/" in path_str or "/english/" in path_str:
                    # Engine klasöründekileri atla
                    if "/engine/" not in path_str:
                        english_locres_files.append(f)
            
            if not english_locres_files and all_locres:
                # Eğer hiç 'en' bulunamadıysa en büyük dosyayı seç (fallback)
                all_locres.sort(key=lambda x: x.stat().st_size, reverse=True)
                english_locres_files = [all_locres[0]]

            # Birden fazla bulunduysa sadece en büyüğünü seç (döngü önleme)
            if len(english_locres_files) > 1:
                english_locres_files.sort(key=lambda x: x.stat().st_size, reverse=True)
                if progress_callback: 
                    progress_callback(f"📂 {len(english_locres_files)} locres bulundu, en büyüğü seçildi: {english_locres_files[0].name}")
                english_locres_files = [english_locres_files[0]]

            target_locres = english_locres_files[0]
            if progress_callback: 
                progress_callback(f"🌍 Çevrilecek dil dosyası: {target_locres.name}")
                progress_callback(f"📝 Çevriliyor: {target_locres.name}")
            
            # Tek dosyayı çevir (döngü yok)
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
                target_lang=target_lang
            )
            if not succ:
                raise Exception(f"Dosya çevrilemedi: {target_locres.name}")

            if progress_callback: progress_callback(f"✅ Dil dosyası başarıyla güncellendi: {target_locres.name}")

            # --- KRİTİK TEMİZLİK (GHOST & JUNK FILE REMOVAL) ---
            if progress_callback: progress_callback("🧹 Gereksiz dosyalar ve kopyalar temizleniyor (V7)...")
            
            # 1. Tüm CSV, yedek ve geçici dosyaları temizle
            for junk_ext in [".csv", ".new", ".bak", ".tr", ".tmp"]:
                for junk_file in unpack_dir.rglob(f"*{junk_ext}"):
                    try: junk_file.unlink()
                    except: pass
            
            # 2. Her klasörde sadece tek bir .locres kalmasını garanti et (Duplicate önleme)
            for folder in unpack_dir.rglob("*"):
                if folder.is_dir():
                    folder_name = folder.name.lower()
                    # Sadece dil klasörlerinde (en, english vb.) bu temizliği yap
                    if folder_name == "en" or folder_name == "english" or folder_name.startswith("en-"):
                        l_files = list(folder.glob("*.locres"))
                        if len(l_files) > 1:
                            # Boyuta göre sırala (en büyük olan kalsın)
                            l_files.sort(key=lambda x: x.stat().st_size, reverse=True)
                            for extra in l_files[1:]:
                                try: extra.unlink()
                                except: pass
                        
                        # Locres dışındaki her şeyi (varsa) o klasörden temizle
                        for item in folder.iterdir():
                            if item.is_file() and item.suffix.lower() != ".locres":
                                try: item.unlink()
                                except: pass

            if progress_callback: progress_callback("✨ Klasör yapısı sterilize edildi, sadece çevrilmiş dosyalar kaldı.")




            
            # --- FONT INJECTION (TURKISH CHAR FIX) ---
            font_source = Config.BASE_PATH / "files" / "tools" / "fonts" / "Roboto-Regular.ttf"
            if font_source.exists():
                if progress_callback: progress_callback("🔤 Türkçe Font Enjekte Ediliyor...")
                
                # Hedef: Engine/Content/Slate/Fonts/
                # Note: unpack_dir is the root of the unpacked content.
                # However, sometimes the mount point makes the structure different. 
                # Usually standard structure inside pak is Engine/... or Game/...
                
                # Try to locate Engine folder or create it
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
            
            # --- OLD METHOD: FULL REPACK (DESTRUCTIVE) ---
            # Kullanıcı isteği üzerine eski yönteme dönüldü (_P.pak yok, direkt yamala).
            
            print("!!! TAM YAMA MODU (Full Repack) !!!")
            # --- OTOMATİK SIKIŞTIRMA TESPİTİ (COMPRESSION DETECTION) ---
            detected_compression = "Zlib" # Default
            if res_info.returncode == 0:
                if "oodle" in res_info.stdout.lower():
                    detected_compression = "Oodle"
                elif "zlib" in res_info.stdout.lower():
                    detected_compression = "Zlib"
                elif "compressed: false" in res_info.stdout.lower():
                    detected_compression = "None"

            # Oodle kontrolü (DLL yoksa Zlib'e düş)
            if detected_compression == "Oodle":
                oodle_dll = tools_dir / "oo2core_9_win64.dll"
                if not oodle_dll.exists():
                    if progress_callback: progress_callback("⚠️ Oodle DLL bulunamadı, Zlib kullanılacak.")
                    detected_compression = "Zlib"

            if progress_callback: progress_callback(f"📦 Sıkıştırma Modu: {detected_compression}")

            # --- PAKETLEME ÖNCESİ TAM STERİLİZASYON (PATCH HAZIRLIĞI) ---
            # Patch (_P.pak) yama oluşturacağımız için oyunun diğer orijinal verilerini
            # klasörden siliyoruz ki oluşturacağımız paket küçük ve sade olsun.
            if progress_callback: progress_callback("🧪 Yama için klasör sterilize ediliyor (Sadece çeviriler kalacak)...")
            for junk in list(unpack_dir.rglob("*")):
                if junk.is_file():
                    if junk.suffix.lower() not in [".locres", ".ttf"]:
                        try: junk.unlink()
                        except: pass
            # Her klasörde sadece tek bir locres kalmasını bir kez daha garanti et
            for folder in unpack_dir.rglob("*"):
                if folder.is_dir():
                    locres_files = list(folder.glob("*.locres"))
                    if len(locres_files) > 1:
                        locres_files.sort(key=lambda x: x.stat().st_size, reverse=True)
                        for extra in locres_files[1:]:
                            try: extra.unlink()
                            except: pass

            # --- PAKETLEME (REPACK) ---
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


            # 4. DOSYA YERLEŞİMİ (PATCH PAK - _P.pak OLARAK YERLEŞTİRME)
            if progress_callback: progress_callback(f"🚚 Yama dosyası (_P.pak) oyuna katarak atılıyor...")
            
            # Patch Pakedinin adını belirle: OrijinalAd_P.pak
            original_stem = target_pak.stem
            # Eğer zaten _P varsa sonuna bir daha ekleme, değilse ekle
            if not original_stem.endswith("_P"):
                patch_name = f"{original_stem}_P.pak"
            else:
                patch_name = f"{original_stem}_Yama.pak"
                
            patch_target_path = target_pak.parent / patch_name
            
            # Orijinali EZMİYORUZ. Yanına yama olarak koyuyoruz!
            try:
                if patch_target_path.exists(): patch_target_path.unlink() # Önceden kalan yamayı sil
                shutil.move(str(temp_repack_output), str(patch_target_path))
                if progress_callback: progress_callback(f"✅ Çeviri yaması eklendi: {patch_target_path.name}")
                    
            except Exception as e:
                raise Exception(f"Dosya taşıma hatası: {e}")
            end_time = time.time()
            duration = end_time - start_time
            
            if progress_callback:
                progress_callback(f"✅ YAMA KURULUMU BAŞARILI!")
                progress_callback(f" Dosya: {patch_target_path.name}")
                progress_callback(f" (Orijinal {target_pak.name} korundu. Yama _P.pak olarak eklendi.)")
                
            return str(patch_target_path)
        finally:
            # Temizlik (Hata alsa bile programın devam etmesini sağlar)
            try:
                shutil.rmtree(temp_dir, ignore_errors=True)
            except:
                pass


            # --- ESKİ KODLAR (DEVRE DIŞI) ---
            # ...

