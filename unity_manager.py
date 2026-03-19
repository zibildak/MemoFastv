
import os
import shutil
import xml.etree.ElementTree as ET
import json
from pathlib import Path
import re
import concurrent.futures
import time

# 3. Parti Kütüphaneler
try:
    from deep_translator import GoogleTranslator
except ImportError:
    GoogleTranslator = None
    
try:
    import UnityPy
except ImportError:
    UnityPy = None

from config import Constants

class UnityManager:
    """
    Unity oyunları için Gelişmiş Çeviri Yöneticisi.
    
    YENİLİKLER:
    - Crash Fix: {0} gibi değişkenleri onarır.
    - Stop Logic: İngilizce dil dosyasını bulunca diğerlerini atlar.
    - Backup: Orijinal dosyayı silmez, kopyasını (.bak) alır.
    """
    
    MAX_WORKERS = Constants.MAX_WORKERS 
    
    @staticmethod
    def is_available():
        return True

    @staticmethod
    def _should_translate(text):
        if not text or not isinstance(text, str): return False
        if len(text) < 2: return False
        # Teknik/Kod filtreleri
        if text.startswith("{") or text.startswith("http") or "www." in text: return False
        if re.match(r'^[\d\W_]+$', text): return False
        if " " not in text and len(text) > 20: return False
        if "/" in text and "." in text and " " not in text: return False
        return True

    @staticmethod
    def _apply_turkish_filter(text):
        """Mek/Mak temizler: Oynamak -> Oyna"""
        if not text: return text
        exceptions = ["ekmek", "yemek", "kıymak", "kaymak", "çakmak", "kıymık", "ırmak", "damak", "yamak"]
        words = text.split()
        if not words: return text
        last_word = words[-1]
        
        # Noktalama işaretini ayır (Oynamak. -> Oynamak)
        punctuation = ""
        if last_word and last_word[-1] in ".,!?;:":
            punctuation = last_word[-1]
            last_word = last_word[:-1]

        if last_word.lower() in exceptions: return text
        
        match = re.search(r'(.{2,})(mek|mak)$', last_word, re.IGNORECASE)
        if match:
            new_word = match.group(1) + punctuation
            words[-1] = new_word
            return " ".join(words)
        return text

    @staticmethod
    def _normalize_turkish_chars(text):
        """
        Fontu desteklemeyen oyunlar için Türkçe karakterleri ASCII'ye çevirir.
        ğ -> g, ş -> s, ı -> i vb.
        """
        replacements = {
            'ğ': 'g', 'Ğ': 'G',
            'ş': 's', 'Ş': 'S',
            'ı': 'i', 'İ': 'I',
            'ç': 'c', 'Ç': 'C',
            'ö': 'o', 'Ö': 'O',
            'ü': 'u', 'Ü': 'U'
        }
        for tr, en in replacements.items():
            text = text.replace(tr, en)
        return text

    @staticmethod
    def _repair_translation(original, translated, target_lang="tr"):
        """
        KRİTİK: Oyunun çökmesine neden olan bozuk formatları onarır.
        """
        if not translated: return original
        
        corrected = translated
        
        # 0. Karakter Normalizasyonu (Kullanıcı İsteği: Font Sorunu) - Sadece Türkçe için
        if target_lang == "tr":
            corrected = UnityManager._normalize_turkish_chars(corrected)
        
        # 1. Değişken Onarımı: { 0 } -> {0}
        corrected = re.sub(r'\{\s*(\d+)\s*\}', r'{\1}', corrected)
        
        # 2. Tag Onarımı: < b > -> <b>
        corrected = re.sub(r'<\s*(/?\s*([a-zA-Z0-9_]+)([^>]*)\>', r'<\1\2\3>', corrected)
        
        # 3. Yüzde Onarımı: % s -> %s
        corrected = re.sub(r'%\s+([sd])', r'%\1', corrected)

        corrected = corrected.strip()
        
        return corrected

    @staticmethod
    def _translate_batch_concurrent(text_list, translator, progress_callback=None):
        results = {}
        total = len(text_list)
        if total == 0: return results
        completed = 0
        with concurrent.futures.ThreadPoolExecutor(max_workers=UnityManager.MAX_WORKERS) as executor:
            future_to_text = {executor.submit(translator.translate, text): text for text in text_list}
            for future in concurrent.futures.as_completed(future_to_text):
                original = future_to_text[future]
                try:
                    translated = future.result()
                    if translated and translated != original:
                        # [YENİ] Hedef Dil Tespiti
                        t_lang = "tr"
                        if hasattr(translator, 'target_lang'): t_lang = translator.target_lang.lower()
                        elif hasattr(translator, 'target'): t_lang = translator.target.lower()

                        # 1. Filtre (Mek/Mak) - Sadece Türkçe için
                        filtered = translated
                        if t_lang == "tr":
                            filtered = UnityManager._apply_turkish_filter(translated)
                        
                        # 2. Tamir (Crash Fix)
                        repaired = UnityManager._repair_translation(original, filtered, target_lang=t_lang)
                        
                        results[original] = repaired
                except: pass 
                completed += 1
                if progress_callback and (completed % 10 == 0 or completed == total):
                    percent = int((completed / total) * 100)
                    progress_callback(f"⚡ Turbo Çeviri: {completed}/{total} - %{percent}")
        return results

    @staticmethod
    def scan_and_process_game(game_folder, translator=None, progress_callback=None, service="google", api_key=None, target_lang="tr"):
        game_path = Path(game_folder)
        if not game_path.exists():
            return 0
        
        if not translator:
            # Service seçimine göre çevirmen oluştur
            if service == "deepl" and api_key:
                try:
                    # DeepL Helper entegrasyonu (Basit)
                    from deepl_helper import DeepLTranslator
                    if target_lang != "tr":
                         if progress_callback: progress_callback(f"⚠️ DeepL için şimdilik sadece Türkçe destekleniyor (Target={target_lang})")
                    translator = DeepLTranslator(api_key, target_lang=target_lang)
                    if progress_callback: progress_callback("🌍 DeepL API aktif.")
                except:
                    if progress_callback: progress_callback("⚠️ DeepL başlatılamadı, Google kullanılıyor.")
                    if GoogleTranslator:
                        translator = GoogleTranslator(source='auto', target=target_lang)
            elif GoogleTranslator:
                translator = GoogleTranslator(source='auto', target=target_lang)
            else:
                 if progress_callback: progress_callback("❌ Çeviri modülü (google/deepl) bulunamadı.")
                 return 0
        
        if progress_callback: progress_callback(f"🔍 Dosyalar taranıyor...")
        
        target_files = []
        priority_keywords = ["english", "_en_", "_en.", "_eng", "language_en", "language_eng", "loc_en"] 
        secondary_keywords = ["lang", "loc", "data", "text", "localization"]
        
        # Blacklist (Gereksiz dosyalar - Kullanıcı Geri Bildirimi)
        files_blacklist = ["enemy", "enemies", "audio", "sound", "music", "texture", 
                           "material", "mesh", "anim", "video", "font", "shader", "scene", "credit"]
        
        # Tam Eşleşme Öncelikleri (Kullanıcı İsteği)
        specific_targets = ["localization.assets", "translations.assets", "language.assets", "languages.assets"]

        valid_exts = [".xml", ".bundle", ".assets", ".json", ".txt", ".bak"]
        
        # [FIX] TEK DOSYA MODU
        if game_path.is_file():
            # Eğer kullanıcı direkt dosya verdiyse, walk yapmaya gerek yok.
            if progress_callback: progress_callback(f"📂 Tek dosya modu: {game_path.name}")
            ext = game_path.suffix.lower()
            if ext in valid_exts or ext == ".sharedassets": # sharedassets eklendi
                target_files.append( {'path': game_path, 'score': 100, 'type': ext} )
        else:
            # KLASÖR MODU (Eski Logic)
            for root, dirs, files in os.walk(game_path):
                for file in files:
                    name_lower = file.lower()
                    
                    # Blacklist Check
                    if any(x in name_lower for x in files_blacklist): continue
                    
                    ext = os.path.splitext(name_lower)[1]
                    
                    if ext in valid_exts:
                        score = 0
                    
                    # 1. Tam İsim Kontrolü (En Yüksek Öncelik)
                    if name_lower in specific_targets:
                        score += 50
                    # 2. İngilizce İşaretçileri
                    elif any(k in name_lower for k in priority_keywords): 
                        score += 20
                    # 3. Genel Kelimeler
                    elif any(k in name_lower for k in secondary_keywords): 
                        score += 10
                    
                    # EN içeren XML/BAK kontrolü
                    if (ext == ".xml" or ext == ".bak") and "en" in name_lower:
                        score += 5
                    
                    # XML StreamingAssets bonusu
                    if ext == ".xml" and "streamingassets" in root.lower(): score += 5
                    
                    if score > 0:
                        target_files.append( {'path': Path(root) / file, 'score': score, 'type': ext} )

        target_files.sort(key=lambda x: x['score'], reverse=True)
        
        if not target_files:
            if progress_callback: progress_callback("⚠️ Uygun dosya bulunamadı.")
            return 0
            
        # Stop on English
        max_score = target_files[0]['score']
        if max_score >= 20:
            final_targets = [t for t in target_files if t['score'] >= 20]
            if progress_callback: progress_callback("🎯 İngilizce dosyalar belirlendi (Diğerleri atlanacak).")
        else:
            final_targets = target_files
            
        total_translated_global = 0
        translation_cache = {}

        for i, target in enumerate(final_targets):
            file_path = target['path']
            f_type = target['type']
            
            if progress_callback: progress_callback(f"📂 İşleniyor: {file_path.name}")
            
            # YEDEKLEME (Copy, don't move)
            # Dosya: file.xml -> Yedek: file.xml.bak_original
            backup_path = file_path.with_suffix(file_path.suffix + ".bak_default")
            if not backup_path.exists():
                try:
                    shutil.copy2(file_path, backup_path)
                except Exception as e:
                    if progress_callback: progress_callback(f"⚠️ Yedekleme Hatası: {e}")
            
            try:
                # Format Tahmini
                actual_type = f_type
                # .bak ise içini kokla
                if f_type == ".bak":
                    try:
                        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                            head = f.read(100).strip()
                            if head.startswith("<"): actual_type = ".xml"
                            elif head.startswith("{") or head.startswith("["): actual_type = ".json"
                    except: pass
                
                changes = 0
                if actual_type == ".xml":
                    changes = UnityManager._process_xml(file_path, translator, progress_callback, translation_cache)
                elif actual_type in [".json", ".txt"]:
                    changes = UnityManager._process_json_file(file_path, translator, progress_callback, translation_cache)
                elif actual_type in [".bundle", ".assets"]:
                    if UnityPy:
                        changes = UnityManager._process_unity_bundle(file_path, translator, progress_callback, translation_cache)
                    else:
                        if progress_callback: progress_callback("⚠️ Bundle modülü eksik.")
                
                total_translated_global += changes
                
                # --- ÇIKIŞ MANTIĞI (STOP LOGIC) ---
                # Eğer önemli bir dosyayı (Puan >= 20) başarıyla çevirdiysek dur.
                if changes > 0 and target['score'] >= 20:
                     if progress_callback: progress_callback("🛑 Ana dil dosyası tamamlandı. İşlem bitiriliyor.")
                     break
                
            except Exception as e:
                 if progress_callback: progress_callback(f"HS Hata: {e}")
                
        return total_translated_global

    @staticmethod
    def _process_xml(xml_path, translator, progress_callback, cache):
        try:
            tree = ET.parse(xml_path)
            root = tree.getroot()
            items_to_translate = []
            target_attrs = ['value', 'val', 'text', 'content', 'string', 'desc', 'data']
            for elem in root.iter():
                if elem.text and UnityManager._should_translate(elem.text.strip()):
                    items_to_translate.append( (elem, None, elem.text.strip()) )
                for attr in target_attrs:
                    if attr in elem.attrib and UnityManager._should_translate(elem.attrib[attr]):
                        items_to_translate.append( (elem, attr, elem.attrib[attr]) )
            
            if not items_to_translate: return 0
            
            unique_texts = list(set(item[2] for item in items_to_translate if item[2] not in cache))
            if unique_texts:
                cache.update(UnityManager._translate_batch_concurrent(unique_texts, translator, progress_callback))
            
            changes = 0
            for elem, attr, text in items_to_translate:
                if text in cache:
                    val = cache[text]
                    if attr: elem.attrib[attr] = val
                    else: elem.text = val
                    changes += 1
            
            if changes > 0:
                # Orijinal dosyanın üzerine yaz
                tree.write(xml_path, encoding="utf-8", xml_declaration=True)
                if progress_callback: progress_callback(f"✅ KAYDEDİLDİ: {xml_path.name}")
            return changes
        except: return 0

    @staticmethod
    def _process_json_file(json_path, translator, progress_callback, cache):
        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            texts_to_translate = []
            def recurse_find(obj):
                if isinstance(obj, dict):
                    for k, v in obj.items():
                        if isinstance(v, str) and UnityManager._should_translate(v):
                            texts_to_translate.append(v)
                        elif isinstance(v, (dict, list)): recurse_find(v)
                elif isinstance(obj, list):
                    for item in obj:
                        if isinstance(item, str) and UnityManager._should_translate(item):
                            texts_to_translate.append(item)
                        elif isinstance(item, (dict, list)): recurse_find(item)
            recurse_find(data)
            
            if not texts_to_translate: return 0
            
            unique_texts = list(set(t for t in texts_to_translate if t not in cache))
            if unique_texts:
                 if progress_callback: progress_callback(f"🚀 JSON: {len(unique_texts)} satır...")
                 cache.update(UnityManager._translate_batch_concurrent(unique_texts, translator, progress_callback))
            
            changes = 0
            def recurse_replace(obj):
                nonlocal changes
                if isinstance(obj, dict):
                    for k, v in obj.items():
                        if isinstance(v, str) and v in cache:
                            obj[k] = cache[v]
                            changes += 1
                        elif isinstance(v, (dict, list)): recurse_replace(v)
                elif isinstance(obj, list):
                    for i, item in enumerate(obj):
                        if isinstance(item, str) and item in cache:
                            obj[i] = cache[item]
                            changes += 1
                        elif isinstance(item, (dict, list)): recurse_replace(item)
            recurse_replace(data)
            
            if changes > 0:
                with open(json_path, 'w', encoding='utf-8') as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)
                if progress_callback: progress_callback(f"✅ JSON: {changes} satır kaydedildi.")
            return changes
        except: return 0

    @staticmethod
    def _process_unity_bundle(bundle_path, translator, progress_callback, cache):
        """Bundle TextAsset Manipülasyonu (UnityPy)"""
        try:
            if progress_callback: progress_callback(f"📦 UnityPy Yükleniyor: {Path(bundle_path).name}")
            
            try:
                env = UnityPy.load(str(bundle_path))
            except Exception as e:
                if progress_callback: progress_callback(f"❌ UnityPy Yükleme Hatası (Dosya Açılmadı): {e}")
                return 0
                
            changes = 0
            modified = False
            
            obj_count = len(env.objects)
            if progress_callback: progress_callback(f"📊 Toplam Obje: {obj_count}")
            
            # İstatistik
            text_asset_count = 0
            mono_count = 0
            
            # Sayım Döngüsü (Hızlı)
            try:
                for obj in env.objects:
                    if obj.type.name == "TextAsset": text_asset_count += 1
                    elif obj.type.name == "MonoBehaviour": mono_count += 1
                
                if progress_callback: 
                    progress_callback(f"ℹ️ Bulunan: TextAsset={text_asset_count}, MonoBehaviour={mono_count}")
            except Exception as e:
                 if progress_callback: progress_callback(f"⚠️ Obje Sayım Hatası: {e}")
            
            if text_asset_count == 0 and mono_count == 0:
                 if progress_callback: progress_callback("⚠️ Bu dosyada çevrilebilir metin bloğu görünmüyor.")
                 return 0

            # Batch Translate için liste
            to_translate_map = {} # {obj_path_id: content_str}
            
            # 1. TARAMA ADIMI (TextAsset ve MonoBehaviour)
            for obj in env.objects:
                if obj.type.name == "TextAsset":
                    data = obj.read()
                    if hasattr(data, "script") and data.script:
                        try:
                            content_str = data.script.tobytes().decode('utf-8')
                            if not content_str or len(content_str) < 2: continue
                            
                            # JSON mu Text mi?
                            is_json = content_str.strip().startswith("{") or content_str.strip().startswith("[")
                            
                            if is_json:
                                # JSON ise parse edip metinleri çıkaralım
                                try:
                                    json_data = json.loads(content_str)
                                    # JSON Helper kullanarak metinleri bul
                                    # (Burada basit recursive find yapıp cache'e atacağız)
                                    pass # _process_json_memory de yapılabilir ama karmaşık.
                                    # Şimdilik basitçe tüm stringi çevirmek yerine JSON mantığını kullanalım.
                                    # Ancak UnityPy içinde JSON parse edip geri dump etmek güvenlidir.
                                    # Şimdilik JSON desteğini pas geçip pure text'e odaklanalım veya
                                    # JSON'u string olarak komple çevirmek yanlış olur.
                                    # TODO: JSON içindeki value'ları ayıklamak lazım.
                                except: pass
                            else:
                                # Düz Metin
                                if UnityManager._should_translate(content_str):
                                    if content_str not in cache:
                                        # Çeviriye gönder (Tek tek veya batch)
                                        pass 
                        except: pass

            # Şimdilik basitçe TextAsset -> Read -> Translate -> Write yapalım
            # JSON desteği ekleyelim çünkü çoğu oyun JSON tutar.
            
            # 1. TARAMA ADIMI (TextAsset ve MonoBehaviour)
            
            # Debug Counters
            debug_typetree_fail = 0
            debug_typetree_ok = 0
            debug_text_found_but_rejected = 0
            debug_sample_logged = False
            
            for obj in env.objects:
                try:
                    # A) TextAsset
                    if obj.type.name == "TextAsset":
                        data = obj.read()
                        if hasattr(data, "script") and data.script:
                            try:
                                content_bytes = data.script.tobytes()
                                # Try decoding
                                try:
                                    content_str = content_bytes.decode('utf-8')
                                    if not debug_sample_logged:
                                        if progress_callback: progress_callback(f"📝 Örnek TextAsset: {content_str[:50]}...")
                                        debug_sample_logged = True
                                except:
                                    # Binary text asset?
                                    continue

                                new_content_str = content_str
                                local_change = 0
                                
                                # ... (TextAsset Logic: JSON/Text) ...
                                # Restore logic from previous step efficiently
                                # ...
                                # (Since I replaced the whole block, I need to keep the logic working)
                                # RE-IMPLEMENTING TextAsset LOGIC FOR SAFETY
                                
                                if content_str.strip().startswith(("{", "[")):
                                    try:
                                        json_data = json.loads(content_str)
                                        # ... (JSON Logic from before) ...
                                        pass # Keeping it brief for log focus, assumes prev logic remains or I re-paste it? 
                                        # ACTUALLY, replace_file_content replaces the whole range. I MUST INCLUDE LOGIC.
                                        
                                        # (Recopying JSON logic lightly)
                                        texts = []
                                        def gather_texts(o):
                                            if isinstance(o, dict):
                                                for k,v in o.items():
                                                    if isinstance(v, str) and UnityManager._should_translate(v): texts.append(v)
                                                    elif isinstance(v, (dict, list)): gather_texts(v)
                                            elif isinstance(o, list):
                                                for x in o:
                                                    if isinstance(x, str) and UnityManager._should_translate(x): texts.append(x)
                                                    elif isinstance(x, (dict, list)): gather_texts(x)
                                        gather_texts(json_data)
                                        
                                        if texts:
                                            # Translate logic...
                                            missing = [t for t in texts if t not in cache]
                                            for m in missing:
                                                tr = translator.translate(m)
                                                if tr: cache[m] = tr
                                            
                                            def replace_texts_j(o):
                                                c = 0
                                                if isinstance(o, dict):
                                                    for k,v in o.items():
                                                        if isinstance(v, str) and v in cache: o[k] = cache[v]; c+=1
                                                        elif isinstance(v, (dict, list)): c+=replace_texts_j(v)
                                                elif isinstance(o, list):
                                                    for i, x in enumerate(o):
                                                        if isinstance(x, str) and x in cache: o[i] = cache[x]; c+=1
                                                        elif isinstance(x, (dict, list)): c+=replace_texts_j(x)
                                                return c
                                            
                                            local_change = replace_texts_j(json_data)
                                            if local_change > 0:
                                                new_content_str = json.dumps(json_data, ensure_ascii=False)
                                    except: pass
                                
                                else:
                                    # Plain Text
                                    if UnityManager._should_translate(content_str):
                                        if content_str not in cache:
                                            res = translator.translate(content_str)
                                            if res: cache[content_str] = res
                                        if content_str in cache:
                                            new_content_str = cache[content_str]
                                            local_change = 1
                                    else:
                                        debug_text_found_but_rejected += 1

                                if local_change > 0 and new_content_str != content_str:
                                    data.script = new_content_str.encode('utf-8')
                                    data.save()
                                    changes += local_change
                                    modified = True 
                            except: pass

                    # B) MonoBehaviour
                    elif obj.type.name == "MonoBehaviour":
                        tree = None
                        try:
                            tree = obj.read_typetree()
                            debug_typetree_ok += 1
                        except:
                            debug_typetree_fail += 1
                            continue
                            
                        if not tree: continue
                        
                        local_change = 0
                        # Recurse
                        def recurse_tree(item):
                            nonlocal local_change
                            c = 0
                            if isinstance(item, dict):
                                for k, v in item.items():
                                    if k == "m_Name": continue # Isim değiştirmeyelim
                                    if isinstance(v, str):
                                        if UnityManager._should_translate(v):
                                            if v not in cache:
                                                try:
                                                    tr = translator.translate(v)
                                                    if tr: cache[v] = tr
                                                except: pass
                                            if v in cache:
                                                item[k] = cache[v]; c += 1
                                        else:
                                             # Debug log for rejected strings (sample)
                                             # nonlocal debug_text_found_but_rejected
                                             # debug_text_found_but_rejected += 1
                                             pass
                                    elif isinstance(v, (dict, list)):
                                        c += recurse_tree(v)
                            elif isinstance(item, list):
                                for i, x in enumerate(item):
                                    if isinstance(x, str):
                                        if UnityManager._should_translate(x):
                                            if x not in cache:
                                                try:
                                                    tr = translator.translate(x)
                                                    if tr: cache[x] = tr
                                                except: pass
                                            if x in cache:
                                                item[i] = cache[x]; c += 1
                                    elif isinstance(x, (dict, list)):
                                        c += recurse_tree(x)
                            return c

                        local_change = recurse_tree(tree)
                        if local_change > 0:
                            obj.save_typetree(tree)
                            changes += local_change
                            modified = True
                            
                except Exception as e:
                    pass

            # LOG REPORT
            if progress_callback:
                if debug_typetree_fail > 0:
                    progress_callback(f"⚠️ TypeTree Hatası: {debug_typetree_fail} obje okunamadı (Data şifreli veya struct eksik).")
                if debug_typetree_ok > 0:
                    progress_callback(f"✅ TypeTree Okundu: {debug_typetree_ok} obje.")
                if debug_text_found_but_rejected > 0:
                    progress_callback(f"ℹ️ Filtrelenen Metin: {debug_text_found_but_rejected} adet (Kısa veya anlamsız).")
            
            if modified:
                if progress_callback: progress_callback(f"💾 Bundle kaydediliyor... ({changes} değişiklik)")
                with open(bundle_path, "wb") as f:
                    f.write(env.file.save())
                return changes
            else:
                return 0

        except Exception as e:
            if progress_callback: progress_callback(f"Bundle Error: {e}")
            return 0

    @staticmethod
    def get_available_tmp_fonts(game_path):
        """
        Oyun dosyalarını tarayarak (UnityPy ile) mevcut TextMeshPro fontlarını bulur.
        Dönüş: ["LiberationSans SDF", "OyunFontu SDF", ...]
        """
        if not UnityPy: return []
        
        found_fonts = set()
        game_dir = Path(game_path).parent if os.path.isfile(game_path) else Path(game_path)
        data_dir = None
        
        # Data klasörünü bul
        for item in game_dir.iterdir():
            if item.is_dir() and item.name.endswith("_Data"):
                data_dir = item
                break
                
        if not data_dir: return []
        
        # Taranacak öncelikli dosyalar
        scan_list = ["resources.assets", "globalgamemanagers"]
        # sharedassets0.assets ... sharedassets5.assets (İlk bölümdekiler genelde UI)
        scan_list.extend([f"sharedassets{i}.assets" for i in range(10)])
        
        for fname in scan_list:
            fpath = data_dir / fname
            if not fpath.exists(): continue
            
            try:
                env = UnityPy.load(str(fpath))
                
                for obj in env.objects:
                    # TextMeshProFont Asset'lerini ara
                    # ClassID: 114 (MonoBehaviour) ama Script'i TMP_FontAsset olmalı
                    # Basitçe Adında " SDF" geçen veya FontAsset olanları ayırt etmeye çalışalım
                    # UnityPy exact type check (TMP_FontAsset) bazen script referansı ister.
                    
                    if obj.type.name == "MonoBehaviour":
                        # İsimden tahmin etmeye çalış (Hızlı yöntem)
                        try:
                            data = obj.read()
                            if hasattr(data, "name") and data.name:
                                if " SDF" in data.name or "Font Asset" in data.name:
                                    found_fonts.add(data.name)
                        except: pass
                        
                    elif obj.type.name == "Font":
                        # Normal Fontları da ekle (Belki Legacy lazımdır)
                        try:
                            data = obj.read()
                            if data.name: found_fonts.add(data.name)
                        except: pass
                        
            except Exception as e:
                # print(f"Scan Error ({fname}): {e}")
                pass
                
        return sorted(list(found_fonts))

    @staticmethod
    def apply_turkish_font_fix(game_folder):
        """
        XUnity.AutoTranslator Config.ini dosyasını Türkçe karakterler için düzenler.
        
        ARAŞTIRMA SONUCU - EN ÇALIŞAN YÖNTEM:
        - OverrideFontTextMeshPro=LiberationSans SDF (XUnity'nin kendi fontu, Türkçe destekli)
        - FallbackFontTextMeshPro=LiberationSans SDF
        """
        try:
            game_path = Path(game_folder)
            
            # Eğer oyun klasörü değil de dosya seçildiyse parent al
            if game_path.is_file():
                game_path = game_path.parent

            # BepInEx, MelonLoader veya AutoTranslator config yolu
            config_path = game_path / "BepInEx" / "config" / "AutoTranslatorConfig.ini"
            
            if not config_path.exists():
                # MelonLoader dene
                config_path = game_path / "UserData" / "AutoTranslatorConfig.ini"
            
            if not config_path.exists():
                # AutoTranslator (Direkt) dene
                config_path = game_path / "AutoTranslator" / "Config.ini"
            
            if not config_path.exists():
                return False, f"AutoTranslatorConfig.ini bulunamadı!\nBepInEx veya MelonLoader kurulu değil."
            
            with open(config_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            
            # [Behaviour] bölümünü bul veya oluştur
            behaviour_index = -1
            for i, line in enumerate(lines):
                if line.strip() == "[Behaviour]":
                    behaviour_index = i
                    break
            
            if behaviour_index == -1:
                # [Behaviour] yoksa ekle
                lines.append("\n[Behaviour]\n")
                behaviour_index = len(lines) - 2
            
            # Font ayarlarını ekle/güncelle
            font_settings = {
                "OverrideFontTextMeshPro": "LiberationSans SDF",
                "FallbackFontTextMeshPro": "LiberationSans SDF"
            }
            
            # Mevcut ayarları güncelle veya ekle
            for key, value in font_settings.items():
                found = False
                for i in range(behaviour_index + 1, len(lines)):
                    # Başka bir section başladıysa dur
                    if lines[i].strip().startswith("["):
                        break
                    
                    if lines[i].startswith(key + "="):
                        lines[i] = f"{key}={value}\n"
                        found = True
                        break
                
                if not found:
                    # [Behaviour] section'ından sonra ekle
                    lines.insert(behaviour_index + 1, f"{key}={value}\n")
                    behaviour_index += 1
            
            # Dosyayı kaydet
            with open(config_path, 'w', encoding='utf-8') as f:
                f.writelines(lines)
                
            return True, "✅ Türkçe font desteği eklendi!\n\nKullanılan Font: LiberationSans SDF\n(XUnity'nin kendi Türkçe destekli fontu)"
            
        except Exception as e:
            return False, f"İşlem sırasında hata oluştu: {e}"

if __name__ == "__main__":
    import sys
    target = sys.argv[1] if len(sys.argv) > 1 else "."
    UnityManager.scan_and_process_game(target, progress_callback=print)
