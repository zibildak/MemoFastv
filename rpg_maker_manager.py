
import os
import json
import shutil
from pathlib import Path
import re
import concurrent.futures
from config import Constants

# Bağımlılıklar
try:
    from deep_translator import GoogleTranslator
except ImportError:
    GoogleTranslator = None

try:
    import yaml # PyYAML varsa daha gelişmiş destek için
except ImportError:
    yaml = None

class RPGMakerManager:
    """
    RPG Maker (MV, MZ, XP, VX, Ace) oyunları için Çeviri Yöneticisi.
    Şu an için MV/MZ (JSON tabanlı) ve Modlanmış (YAML tabanlı) sürümler desteklenmektedir.
    """
    
    MAX_WORKERS = Constants.MAX_WORKERS

    @staticmethod
    def detect_engine(game_path):
        """
        Oyunun hangi RPG Maker sürümü olduğunu tespit eder.
        """
        path = Path(game_path)
        if path.is_file():
            path = path.parent

        # 1. Klasör yapısını tara (www klasörünü de hesaba kat)
        roots = [path, path / "www"]
        
        for r in roots:
            if not r.exists(): continue
            
            # MV/MZ Kontrolü (data klasöründeki .json dosyaları)
            data_dir = r / "data"
            if data_dir.exists() and (data_dir / "System.json").exists():
                if (r.parent / "js" / "rmmz_core.js").exists() or (r / "js" / "rmmz_core.js").exists():
                    return "MZ"
                return "MV"

            # Modlu/Özel Motor Kontrolü (OMORI / OneLoader / HERO)
            if (r / "languages").exists() or (r / "mod.json").exists():
                return "Modded-MV" # OMORI gibi yapılar

            # XP/VX/Ace Kontrolü (Data klasöründeki .rxdata, .rvdata, .rvdata2)
            old_data_dir = r / "Data"
            if old_data_dir.exists():
                if list(old_data_dir.glob("*.rvdata2")): return "Ace"
                if list(old_data_dir.glob("*.rvdata")): return "VX"
                if list(old_data_dir.glob("*.rxdata")): return "XP"

        return None

    @staticmethod
    def _is_translatable(text):
        if not text or not isinstance(text, str): return False
        if len(text.strip()) < 1: return False
        # Sayısal veya sadece sembol içerenleri atla
        if re.match(r'^[\d\W_]+$', text): return False
        # Teknik/Kod filtreleri
        if text.startswith("http") or "www." in text: return False
        # Sadece \ karakterleri içerenleri atla (RPG Maker kodları)
        if re.match(r'^[\\]+[a-zA-Z0-9]+$', text.strip()): return False
        return True

    @staticmethod
    def extract_from_json(json_data, file_name=""):
        """
        RPG Maker MV/MZ JSON verisinden çevrilebilir metinleri çıkarır.
        """
        extracted = []

        def walk(obj, parent_key=""):
            if isinstance(obj, dict):
                # MV/MZ Standart Alanlar
                for key in ["name", "description", "message1", "message2", "nickname", "profile"]:
                    if key in obj and RPGMakerManager._is_translatable(obj[key]):
                        extracted.append(obj[key])
                
                # Event Listesi (code 401: Message, 102: Choice, 405: Message Cont.)
                if "list" in obj and isinstance(obj["list"], list):
                    for cmd in obj["list"]:
                        if not isinstance(cmd, dict): continue
                        code = cmd.get("code")
                        params = cmd.get("parameters", [])
                        
                        if code in [401, 405] and params:
                            if RPGMakerManager._is_translatable(params[0]):
                                extracted.append(params[0])
                        elif code == 102 and params:
                            choices = params[0]
                            if isinstance(choices, list):
                                for choice in choices:
                                    if RPGMakerManager._is_translatable(choice):
                                        extracted.append(choice)

                for k, v in obj.items():
                    walk(v, k)
            elif isinstance(obj, list):
                for item in obj:
                    walk(item)

        walk(json_data)
        return list(set(extracted))

    @staticmethod
    def extract_from_yaml(yaml_content):
        """
        YAML dosyalarından (özellikle OMORI tarzı) metinleri çıkarır.
        PyYAML yoksa regex kullanır (daha güvenli ve hızlı).
        """
        # Regex: text: "..." veya text: '...' eşleşmeleri
        # OMORI formatı: text: "Mesaj"
        pattern = r'text:\s*["\'](.*?)["\']'
        matches = re.findall(pattern, yaml_content, re.DOTALL)
        
        extracted = []
        for m in matches:
            # YAML escape karakterlerini ufaktan temizleyelim (çevirmen için)
            clean_text = m.replace('\\"', '"').replace("\\'", "'")
            if RPGMakerManager._is_translatable(clean_text):
                extracted.append(clean_text)
        return list(set(extracted))

    @staticmethod
    def apply_to_yaml(yaml_content, translations):
        """
        Çevirileri YAML içeriğine geri enjekte eder.
        """
        def replace_func(match):
            prefix = 'text: "'
            text = match.group(1)
            suffix = '"'
            
            # Eğer ' ile başlıyorsa ona göre ayarla
            if match.group(0).startswith("text: '"):
                prefix = "text: '"
                suffix = "'"

            clean_text = text.replace('\\"', '"').replace("\\'", "'")
            if clean_text in translations:
                new_text = translations[clean_text]
                # Tekrar escape edelim
                new_text = new_text.replace('"', '\\"').replace("'", "\\'")
                return f"{prefix}{new_text}{suffix}"
            return match.group(0)

        pattern = r'text:\s*["\'](.*?)["\']'
        updated_content = re.sub(pattern, replace_func, yaml_content, flags=re.DOTALL)
        return updated_content

    @staticmethod
    def apply_to_json(json_data, translations):
        """
        Çevirileri JSON verisine geri uygular.
        """
        def walk(obj):
            if isinstance(obj, dict):
                for key in ["name", "description", "message1", "message2", "nickname", "profile"]:
                    if key in obj and obj[key] in translations:
                        obj[key] = translations[obj[key]]
                
                if "list" in obj and isinstance(obj["list"], list):
                    for cmd in obj["list"]:
                        if not isinstance(cmd, dict): continue
                        code = cmd.get("code")
                        params = cmd.get("parameters", [])
                        
                        if code in [401, 405] and params:
                            if params[0] in translations:
                                params[0] = translations[params[0]]
                        elif code == 102 and params:
                            choices = params[0]
                            if isinstance(choices, list):
                                for i in range(len(choices)):
                                    if choices[i] in translations:
                                        choices[i] = translations[choices[i]]

                for k, v in obj.items():
                    walk(v)
            elif isinstance(obj, list):
                for item in obj:
                    walk(item)

        walk(json_data)
        return json_data

    @staticmethod
    def process_game(game_path, target_lang="tr", progress_callback=None):
        """
        Oyunu tarar ve çeviri işlemini başlatır.
        """
        path = Path(game_path)
        if path.is_file(): path = path.parent
        
        engine = RPGMakerManager.detect_engine(path)
        if not engine:
            # Belki sadece data/ veya languages/ klasörünü seçti?
            if (path / "System.json").exists(): engine = "MV"
            elif list(path.glob("*.yml")): engine = "Modded-MV"
            else:
                if progress_callback: progress_callback("❌ HATA: RPG Maker oyunu tespit edilemedi.")
                return False, "Geçerli bir RPG Maker oyunu bulunamadı."

        if progress_callback: progress_callback(f"🎮 {engine} motoru/yapısı tespit edildi. İşlem başlıyor...")

        # Çalışma klasörlerini belirle
        search_dirs = [path, path / "www"]
        all_translations = {}
        all_files = []

        # JSON Dosyalarını tara
        for d in search_dirs:
            data_dir = d / "data"
            if data_dir.exists():
                all_files.extend(list(data_dir.glob("*.json")))

        # YAML/Mod Dosyalarını tara (Örn: languages/ klasörü)
        for d in search_dirs:
            lang_dir = d / "languages"
            if lang_dir.exists():
                # Tüm dillerdeki yml dosyalarını tarayalım (Genelde 'en' ana kaynaktır)
                all_files.extend(list(lang_dir.rglob("*.yml")))

        if not all_files:
            return False, "Çevrilecek veri dosyası bulunamadı."

        if progress_callback: progress_callback(f"🔍 {len(all_files)} dosya analiz ediliyor...")

        # Metin Çıkarma
        all_texts = set()
        file_map = {}

        for file_path in all_files:
            try:
                suffix = file_path.suffix.lower()
                content = ""
                with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                    if suffix == ".json":
                        data = json.load(f)
                        texts = RPGMakerManager.extract_from_json(data, file_path.name)
                    elif suffix == ".yml" or suffix == ".yaml":
                        content = f.read()
                        texts = RPGMakerManager.extract_from_yaml(content)
                    else: continue
                
                if texts:
                    file_map[file_path] = {"texts": texts, "is_yaml": (suffix != ".json")}
                    all_texts.update(texts)
            except Exception as e:
                if progress_callback: progress_callback(f"⚠️ {file_path.name} okunamadı: {e}")

        if not all_texts:
            return False, "Çevrilecek metin bulunamadı."

        if progress_callback: progress_callback(f"📝 Toplam {len(all_texts)} benzersiz metin çıkarıldı.")

        # [YENİ] Kalıcı Global Çeviri Önbelleği (oyunlar arası, ücretsiz kullanım)
        persist_cache = None
        try:
            from translation_cache import TranslationCache
            persist_cache = TranslationCache(target_lang=target_lang)
            if len(persist_cache) > 0 and progress_callback:
                progress_callback(f"💾 Kalıcı önbellek hazır: {len(persist_cache)} hazır çeviri mevcut.")
        except Exception as e:
            print(f"Kalıcı önbellek açılamadı (çeviri normal devam eder): {e}")

        # Çeviri İşlemi
        if GoogleTranslator:
            translator = GoogleTranslator(source='auto', target=target_lang)
            translations = {}
            text_list = []
            cache_hits = 0

            # Önbellekte olanları doğrudan kullan, sadece kalanları API'ye gönder
            for t in all_texts:
                cached = persist_cache.get(t) if persist_cache else None
                if cached:
                    translations[t] = cached
                    cache_hits += 1
                else:
                    text_list.append(t)

            if cache_hits and progress_callback:
                progress_callback(f"💾 {cache_hits} metin önbellekten geldi — API'ye hiç gitmedi!")

            total = len(text_list)
            completed = 0

            with concurrent.futures.ThreadPoolExecutor(max_workers=RPGMakerManager.MAX_WORKERS) as executor:
                def translate_single(text):
                    try:
                        return text, translator.translate(text)
                    except: return text, None

                future_to_text = {executor.submit(translate_single, t): t for t in text_list}
                for future in concurrent.futures.as_completed(future_to_text):
                    orig, trans = future.result()
                    if trans and trans != orig:
                        translations[orig] = trans
                        if persist_cache:
                            persist_cache.set(orig, trans)
                    completed += 1
                    if progress_callback and (completed % 50 == 0 or completed == total):
                        progress_callback(f"⚡ Çeviri: {completed}/{total}")

            if persist_cache:
                try: persist_cache.save()
                except Exception: pass

            if not translations:
                return False, "Çeviri yapılamadı (Bağlantı veya metin sorunu)."

            # Kaydetme
            if progress_callback: progress_callback("💾 Dosyalar güncelleniyor...")
            success_count = 0
            for f_path, info in file_map.items():
                try:
                    # Yedekle
                    bak = f_path.with_suffix(f_path.suffix + ".bak")
                    if not bak.exists(): shutil.copy2(f_path, bak)
                    
                    if info["is_yaml"]:
                        with open(f_path, 'r', encoding='utf-8', errors='ignore') as f:
                            content = f.read()
                        updated = RPGMakerManager.apply_to_yaml(content, translations)
                        with open(f_path, 'w', encoding='utf-8') as f:
                            f.write(updated)
                    else:
                        with open(f_path, 'r', encoding='utf-8', errors='ignore') as f:
                            data = json.load(f)
                        updated = RPGMakerManager.apply_to_json(data, translations)
                        with open(f_path, 'w', encoding='utf-8') as f:
                            json.dump(updated, f, ensure_ascii=False, indent=0)
                    
                    success_count += 1
                except Exception as e:
                    if progress_callback: progress_callback(f"❌ {f_path.name}: {e}")

            return True, f"Başarılı! {success_count} dosya çevrildi."
        else:
            return False, "GoogleTranslator modülü bulunamadı."

