import os
import sys
import struct
import re
import json
from pathlib import Path
try:
    import UnityPy
    UNITY_AVAILABLE = True
except ImportError:
    UNITY_AVAILABLE = False

from deep_translator import GoogleTranslator

class UnityManager:
    @staticmethod
    def is_available():
        return UNITY_AVAILABLE

    @staticmethod
    def get_preview(assets_path):
        try:
            env = UnityPy.load(str(assets_path))
            items = []
            for o in env.objects:
                type_str = str(getattr(o, 'type', ''))
                if hasattr(o.type, 'name'):
                    type_str = o.type.name
                elif type_str.startswith('ClassIDType.'):
                    type_str = type_str.split('.')[-1]
                    
                if type_str == "MonoBehaviour":
                    try:
                        tree = o.read_typetree()
                        if tree and json.dumps(tree).lower().find("i2languages") != -1:
                            items.append(f"I2Languages Objesi (ID: {o.path_id})")
                    except:
                        try:
                            raw = o.get_raw_data()
                            if b"I2Languages" in raw:
                                items.append(f"I2Languages Binary (ID: {o.path_id})")
                        except: pass
                elif type_str == "TextAsset":
                    try:
                        tree = o.read_typetree()
                        if tree and tree.get("m_Name"):
                            items.append(f"TextAsset: {tree.get('m_Name')}")
                    except: pass
            if not items:
                return ["(Metin içeriği tespit edildi ancak isim okunamadı)"]
            return items
        except Exception as e:
            return [f"(Önizleme hatası: {e})"]

    @staticmethod
    def scan_and_process_game(target_path, service="google", api_key="", progress_callback=None, target_lang="tr", source_lang="en"):
        if not UNITY_AVAILABLE:
            if progress_callback: progress_callback("UnityPy kurulu değil!")
            return 0

        target = Path(target_path)
        if target.is_file():
            # Kullanıcı doğrudan .assets veya .bundle seçtiyse
            files_to_process = [target]
        else:
            if progress_callback: progress_callback(f"Oyun klasörü taranıyor: {target.name} ...")
            files_to_process = list(target.rglob("*.assets")) + list(target.rglob("*.bundle"))

        total_translated = 0
        for f in files_to_process:
            if f.stat().st_size > 2000 * 1024 * 1024: # Skip files > 2GB
                continue

            # 1. I2Languages çevirisi dene
            count = UnityManager._process_i2languages(f, service, api_key, progress_callback, target_lang, source_lang)
            if count > 0:
                total_translated += count

            # 2. TextAsset (JSON/XML/Diyalog) çevirisi dene
            count_text = UnityManager._process_text_assets(f, service, api_key, progress_callback, target_lang, source_lang)
            if count_text > 0:
                total_translated += count_text
                
        return total_translated

    @staticmethod
    def _to_english_chars(text):
        if not text: return text
        mapping = {'ç': 'c', 'Ç': 'C', 'ğ': 'g', 'Ğ': 'G', 'ı': 'i', 'İ': 'I', 'ö': 'o', 'Ö': 'O', 'ş': 's', 'Ş': 'S', 'ü': 'u', 'Ü': 'U'}
        for tr, en in mapping.items():
            text = text.replace(tr, en)
        return text

    @staticmethod
    def _protect_tags(text):
        if not text: return text, []
        patterns = [r'<[^>]+>', r'\{[^}]+\}', r'\[[^]]+\]']
        tags = []
        def replace_match(match):
            val = match.group(0)
            placeholder = f" _TAG_{len(tags)}_ "
            tags.append((placeholder.strip(), val))
            return placeholder
        protected_text = text
        for pattern in patterns:
            protected_text = re.sub(pattern, replace_match, protected_text)
        return protected_text, tags

    @staticmethod
    def _restore_tags(text, tags):
        if not text: return text
        restored = text
        for placeholder, val in tags:
            restored = restored.replace(placeholder, val)
            ph_clean = placeholder.replace(" ", "")
            regex_parts = []
            for char in ph_clean:
                if char in ['_', '-']: regex_parts.append(char)
                else: regex_parts.append(re.escape(char))
            pattern = r'\s*' + r'\s*'.join(regex_parts) + r'\s*'
            restored = re.sub(pattern, val, restored)
        return restored

    @staticmethod
    def _read_string(data, offset):
        length = struct.unpack_from("<I", data, offset)[0]
        if length == 0: return "", offset + 4
        str_bytes = data[offset + 4 : offset + 4 + length]
        s = str_bytes.decode('utf-8', errors='replace')
        aligned_len = (length + 3) // 4 * 4
        return s, offset + 4 + aligned_len

    @staticmethod
    def _write_string(s):
        if not s: return struct.pack("<I", 0)
        s_bytes = s.encode('utf-8')
        length = len(s_bytes)
        aligned_len = (length + 3) // 4 * 4
        padding_len = aligned_len - length
        return struct.pack("<I", length) + s_bytes + b'\x00' * padding_len

    @staticmethod
    def _unpack_dat(data):
        name_idx = data.find(b"I2Languages")
        if name_idx == -1: return None
        
        header_bytes = data[:name_idx - 4]
        offset = name_idx + 12
        val1 = struct.unpack_from("<I", data, offset)[0]
        offset += 4
        val2 = struct.unpack_from("<I", data, offset)[0]
        offset += 4
        val3 = struct.unpack_from("<I", data, offset)[0]
        offset += 4
        num_terms = struct.unpack_from("<I", data, offset)[0]
        offset += 4
        
        terms = []
        for _ in range(num_terms):
            term_name, offset = UnityManager._read_string(data, offset)
            term_type = struct.unpack_from("<I", data, offset)[0]
            offset += 4
            num_translations = struct.unpack_from("<I", data, offset)[0]
            offset += 4
            translations = []
            for _ in range(num_translations):
                trans_str, offset = UnityManager._read_string(data, offset)
                translations.append(trans_str)
            num_flags = struct.unpack_from("<I", data, offset)[0]
            offset += 4
            flags = []
            for _ in range(num_flags):
                flag_val = struct.unpack_from("<B", data, offset)[0]
                offset += 1
                flags.append(flag_val)
            offset = (offset + 3) // 4 * 4
            description, offset = UnityManager._read_string(data, offset)
            terms.append({"term": term_name, "type": term_type, "description": description, "translations": translations, "flags": flags})
            
        val_l1 = struct.unpack_from("<I", data, offset)[0]
        offset += 4
        val_l2 = struct.unpack_from("<I", data, offset)[0]
        offset += 4
        val_l3 = struct.unpack_from("<I", data, offset)[0]
        offset += 4
        num_languages = struct.unpack_from("<I", data, offset)[0]
        offset += 4
        
        languages = []
        for _ in range(num_languages):
            lang_name, offset = UnityManager._read_string(data, offset)
            lang_code, offset = UnityManager._read_string(data, offset)
            lang_flags = struct.unpack_from("<I", data, offset)[0]
            offset += 4
            languages.append({"name": lang_name, "code": lang_code, "flags": lang_flags})
            
        footer_bytes = data[offset:]
        return {"header_bytes": header_bytes, "val1": val1, "val2": val2, "val3": val3, "terms": terms, "val_l1": val_l1, "val_l2": val_l2, "val_l3": val_l3, "languages": languages, "footer_bytes": footer_bytes}

    @staticmethod
    def _repack_dat(tree):
        out = bytearray()
        out.extend(tree["header_bytes"])
        out.extend(UnityManager._write_string("I2Languages"))
        out.extend(struct.pack("<I", tree["val1"]))
        out.extend(struct.pack("<I", tree["val2"]))
        out.extend(struct.pack("<I", tree["val3"]))
        terms = tree["terms"]
        out.extend(struct.pack("<I", len(terms)))
        for term in terms:
            out.extend(UnityManager._write_string(term["term"]))
            out.extend(struct.pack("<I", term["type"]))
            translations = term["translations"]
            out.extend(struct.pack("<I", len(translations)))
            for trans in translations:
                out.extend(UnityManager._write_string(trans))
            flags = term["flags"]
            out.extend(struct.pack("<I", len(flags)))
            for f in flags:
                out.extend(struct.pack("<B", f))
            aligned_len = (len(flags) + 3) // 4 * 4
            padding_len = aligned_len - len(flags)
            out.extend(b'\x00' * padding_len)
            out.extend(UnityManager._write_string(term["description"]))
        out.extend(struct.pack("<I", tree["val_l1"]))
        out.extend(struct.pack("<I", tree["val_l2"]))
        out.extend(struct.pack("<I", tree["val_l3"]))
        languages = tree["languages"]
        out.extend(struct.pack("<I", len(languages)))
        for lang in languages:
            out.extend(UnityManager._write_string(lang["name"]))
            out.extend(UnityManager._write_string(lang["code"]))
            out.extend(struct.pack("<I", lang["flags"]))
        out.extend(tree["footer_bytes"])
        return bytes(out)

    @staticmethod
    def _process_i2languages(assets_path, service, api_key, progress_callback, target_lang, source_lang="en"):
        import time
        try:
            env = UnityPy.load(str(assets_path))
            
            # Nesneyi bul
            obj = None
            for o in env.objects:
                try:
                    tree = o.read_typetree()
                    if tree and json.dumps(tree).lower().find("i2languages") != -1:
                        obj = o
                        break
                except:
                    try:
                        raw_data = o.get_raw_data()
                        if b"I2Languages" in raw_data:
                            obj = o
                            break
                    except: pass
            
            if not obj:
                if progress_callback: progress_callback("❌ Hata: Bu dosyada I2Languages tablosu bulunamadı.")
                return 0
                
            raw_data = obj.get_raw_data()
            tree = UnityManager._unpack_dat(raw_data)
            if not tree:
                if progress_callback: progress_callback("❌ Hata: I2Languages verisi çözümlenemedi (Bozuk veya şifreli olabilir).")
                return 0
                
            languages = tree["languages"]
            target_idx = -1
            target_lang_full = "Turkish" if target_lang == "tr" else target_lang.capitalize()
            for idx, lang in enumerate(languages):
                if lang["code"].lower() == target_lang or lang["name"].lower() == target_lang_full.lower():
                    target_idx = idx
                    break
                    
            if target_idx == -1:
                if progress_callback: progress_callback(f"{target_lang_full} dili ekleniyor: {assets_path.name}")
                target_idx = len(languages)
                languages.append({"name": target_lang_full, "code": target_lang, "flags": 0})
                for term in tree["terms"]:
                    while len(term["translations"]) < len(languages):
                        term["translations"].append("")
                    while len(term["flags"]) < len(languages):
                        term["flags"].append(0)
                        
            source_idx = 1
            # First try exact match with source_lang, then fallback to general checks
            for idx, lang in enumerate(languages):
                if source_lang.lower() in lang["code"].lower():
                    source_idx = idx
                    break
            else:
                for idx, lang in enumerate(languages):
                    if "en" in lang["code"].lower() or "english" in lang["name"].lower():
                        source_idx = idx
                        break
            
            terms = tree["terms"]
            to_translate = []
            for idx, term in enumerate(terms):
                trans_list = term["translations"]
                # 1. Öncelikli kaynak dilden metni al
                text = trans_list[source_idx] if source_idx < len(trans_list) else ""
                
                # 2. Kaynak metin boşsa diğer dillerden dolu olan ilk metni bul
                if not text or not isinstance(text, str) or not text.strip():
                    for t_val in trans_list:
                        if t_val and isinstance(t_val, str) and t_val.strip():
                            text = t_val
                            break

                existing_target = trans_list[target_idx] if target_idx < len(trans_list) else ""
                if text and isinstance(text, str) and text.strip():
                    # Hedef dil boşsa, sadece boşluktan oluşuyorsa veya kaynak ile aynıysa çevir
                    if not existing_target or not isinstance(existing_target, str) or not existing_target.strip() or existing_target == text:
                        to_translate.append((idx, text))
            
            total_to_translate = len(to_translate)
            if progress_callback: progress_callback(f"I2Languages Çevrilecek: {total_to_translate}")
            
            if not to_translate:
                if progress_callback: progress_callback("ℹ️ Bilgi: Hedef dil için çevrilecek eksik metin bulunamadı (Zaten çevrilmiş olabilir).")
                return 0
                
            translated_count = 0
            batch_size = 15  # Google API rate limit koruması için 15
            batches = [to_translate[i:i + batch_size] for i in range(0, len(to_translate), batch_size)]
            translator = GoogleTranslator(source=source_lang, target=target_lang)
            
            for b_idx, batch in enumerate(batches):
                protected_batch = []
                batch_tags = []
                for term_idx, orig_text in batch:
                    protected_text, tags = UnityManager._protect_tags(orig_text)
                    protected_batch.append(protected_text)
                    batch_tags.append((term_idx, orig_text, tags))
                    
                batch_success = False
                for attempt in range(2):
                    try:
                        translated_batch = translator.translate_batch(protected_batch)
                        if translated_batch and len(translated_batch) == len(batch_tags):
                            for i, trans_text in enumerate(translated_batch):
                                term_idx, orig_text, tags = batch_tags[i]
                                if trans_text:
                                    final_text = UnityManager._restore_tags(trans_text, tags)
                                    final_text = UnityManager._to_english_chars(final_text)
                                    trans_list = terms[term_idx]["translations"]
                                    while len(trans_list) <= target_idx:
                                        trans_list.append("")
                                    trans_list[target_idx] = final_text
                            translated_count += len(batch)
                            batch_success = True
                            break
                    except Exception:
                        time.sleep(1.0)

                if not batch_success:
                    if progress_callback: progress_callback(f"Batch {b_idx+1} tekli çeviriye geçiliyor (Kota korumalı)...")
                    for term_idx, orig_text, tags in batch_tags:
                        single_success = False
                        for single_attempt in range(3):
                            try:
                                protected_text, tags = UnityManager._protect_tags(orig_text)
                                trans_text = translator.translate(protected_text)
                                if trans_text:
                                    final_text = UnityManager._restore_tags(trans_text, tags)
                                    final_text = UnityManager._to_english_chars(final_text)
                                    trans_list = terms[term_idx]["translations"]
                                    while len(trans_list) <= target_idx:
                                        trans_list.append("")
                                    trans_list[target_idx] = final_text
                                    translated_count += 1
                                    single_success = True
                                    time.sleep(0.15)
                                    break
                            except Exception:
                                time.sleep(0.8)
                        if not single_success:
                            if progress_callback: progress_callback(f"⚠️ Terim çevrilemedi: '{orig_text[:20]}...'")

                if progress_callback: progress_callback(f"[{translated_count}/{total_to_translate}] Çevrildi. (Batch {b_idx+1}/{len(batches)})")
                time.sleep(0.2)
                            
            # Kaydet
            if progress_callback: progress_callback(f"Unity paketi yeniden oluşturuluyor: {assets_path.name}")
            new_bytes = UnityManager._repack_dat(tree)
            obj.set_raw_data(new_bytes)
            
            # Yedek oluştur
            bak_path = assets_path.with_suffix(assets_path.suffix + ".bak")
            if not bak_path.exists():
                import shutil
                shutil.copy2(assets_path, bak_path)
                if progress_callback: progress_callback(f"Yedek alındı: {bak_path.name}")
            
            with open(assets_path, "wb") as f:
                f.write(env.file.save())
                
            return translated_count
        except Exception as e:
            if progress_callback: progress_callback(f"I2Languages işlenirken hata: {e}")
            return 0

    @staticmethod
    def _is_translatable_string(s, key_name=""):
        if not s or not isinstance(s, str):
            return False
        s_strip = s.strip()
        if len(s_strip) < 2:
            return False
        # Do not translate URLs or asset file paths
        if s_strip.startswith(("http://", "https://", "ftp://")) or s_strip.endswith((".png", ".jpg", ".wav", ".mp3", ".prefab", ".asset", ".mat", ".mesh", ".unity3d")):
            return False
        # Do not translate 32-char hex GUIDs
        if len(s_strip) == 32 and all(c in "0123456789abcdefABCDEF" for c in s_strip):
            return False
        # Skip technical keys if they are strict metadata like "guid", "hash", "url"
        skip_strict_keys = {"guid", "hash", "url", "iso"}
        if key_name and str(key_name).lower() in skip_strict_keys:
            return False
        # Must contain at least one letter
        if not any(c.isalpha() for c in s_strip):
            return False
        return True

    @staticmethod
    def _translate_json_object(obj, translator, progress_callback=None, asset_name="", target_lang="tr"):
        items_to_translate = []

        def collect(container, key_or_index, value):
            if isinstance(value, str):
                if UnityManager._is_translatable_string(value, str(key_or_index)):
                    items_to_translate.append((container, key_or_index, value))
            elif isinstance(value, dict):
                for k, v in value.items():
                    collect(value, k, v)
            elif isinstance(value, list):
                for idx, item in enumerate(value):
                    collect(value, idx, item)

        if isinstance(obj, dict):
            # Special handling for {"English": {...}} multi-language maps
            if "English" in obj and isinstance(obj["English"], dict):
                target_key = "Turkish" if target_lang == "tr" else target_lang.capitalize()
                if target_key not in obj and "TR" not in obj:
                    import copy
                    obj[target_key] = copy.deepcopy(obj["English"])
                actual_target = target_key if target_key in obj else ("TR" if "TR" in obj else "English")
                for k, v in obj[actual_target].items():
                    collect(obj[actual_target], k, v)
            else:
                for k, v in obj.items():
                    collect(obj, k, v)
        elif isinstance(obj, list):
            for idx, item in enumerate(obj):
                collect(obj, idx, item)

        if not items_to_translate:
            return 0

        total = len(items_to_translate)
        if progress_callback:
            progress_callback(f"📝 {asset_name} (JSON/Diyalog): {total} metin çevriliyor...")

        translated_count = 0
        batch_size = 15
        batches = [items_to_translate[i:i + batch_size] for i in range(0, len(items_to_translate), batch_size)]

        import time
        for batch in batches:
            protected_batch = []
            batch_tags = []
            for container, k_idx, orig_text in batch:
                prot_text, tags = UnityManager._protect_tags(orig_text)
                protected_batch.append(prot_text)
                batch_tags.append((container, k_idx, orig_text, tags))

            batch_success = False
            for attempt in range(2):
                try:
                    translated_batch = translator.translate_batch(protected_batch)
                    if translated_batch and len(translated_batch) == len(batch_tags):
                        for i, trans_text in enumerate(translated_batch):
                            container, k_idx, orig_text, tags = batch_tags[i]
                            if trans_text:
                                final_text = UnityManager._restore_tags(trans_text, tags)
                                final_text = UnityManager._to_english_chars(final_text)
                                container[k_idx] = final_text
                        translated_count += len(batch)
                        batch_success = True
                        break
                except Exception:
                    time.sleep(0.5)

            if not batch_success:
                for container, k_idx, orig_text, tags in batch_tags:
                    try:
                        prot_text, tags = UnityManager._protect_tags(orig_text)
                        trans_text = translator.translate(prot_text)
                        if trans_text:
                            final_text = UnityManager._restore_tags(trans_text, tags)
                            final_text = UnityManager._to_english_chars(final_text)
                            container[k_idx] = final_text
                            translated_count += 1
                        time.sleep(0.1)
                    except: pass

            time.sleep(0.15)

        return translated_count

    @staticmethod
    def _process_text_assets(assets_path, service, api_key, progress_callback, target_lang, source_lang="en"):
        import time
        try:
            env = UnityPy.load(str(assets_path))
            modified = False
            total_count = 0
            translator = GoogleTranslator(source=source_lang, target=target_lang)

            for o in env.objects:
                type_str = str(getattr(o, 'type', ''))
                if hasattr(o.type, 'name'):
                    type_str = o.type.name
                elif type_str.startswith('ClassIDType.'):
                    type_str = type_str.split('.')[-1]

                if type_str != "TextAsset":
                    continue

                try:
                    tree = o.read_typetree()
                    if not tree or not tree.get("m_Script"):
                        continue

                    script_content = tree.get("m_Script")
                    if isinstance(script_content, bytes):
                        try:
                            script_text = script_content.decode('utf-8', errors='ignore')
                        except:
                            continue
                    else:
                        script_text = str(script_content)

                    if not script_text.strip():
                        continue

                    asset_name = tree.get("m_Name", "Unnamed")

                    # Try parsing JSON first
                    translated_in_asset = 0
                    try:
                        data = json.loads(script_text)
                        translated_in_asset = UnityManager._translate_json_object(
                            data, translator, progress_callback, asset_name, target_lang
                        )
                        if translated_in_asset > 0:
                            new_text = json.dumps(data, ensure_ascii=False, indent=2)
                            tree["m_Script"] = new_text
                            o.save_typetree(tree)
                            modified = True
                            total_count += translated_in_asset
                    except json.JSONDecodeError:
                        pass

                except Exception:
                    continue

            if modified:
                if progress_callback: progress_callback(f"Unity paketi güncelleniyor: {assets_path.name}")
                bak_path = assets_path.with_suffix(assets_path.suffix + ".bak")
                if not bak_path.exists():
                    import shutil
                    shutil.copy2(assets_path, bak_path)
                with open(assets_path, "wb") as f:
                    f.write(env.file.save())

            return total_count
        except Exception as e:
            if progress_callback: progress_callback(f"TextAsset işlenirken hata: {e}")
            return 0

    @staticmethod
    def apply_turkish_font_fix(game_folder):
        """
        XUnity.AutoTranslator Config.ini dosyasını Türkçe karakterler için düzenler.
        """
        try:
            game_path = Path(game_folder)
            if game_path.is_file():
                game_path = game_path.parent

            config_path = game_path / "BepInEx" / "config" / "AutoTranslatorConfig.ini"
            if not config_path.exists():
                config_path = game_path / "UserData" / "AutoTranslatorConfig.ini"
            if not config_path.exists():
                config_path = game_path / "AutoTranslator" / "Config.ini"
            if not config_path.exists():
                return False, "AutoTranslatorConfig.ini bulunamadı!\nBepInEx veya MelonLoader kurulu değil."

            with open(config_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()

            behaviour_index = -1
            for i, line in enumerate(lines):
                if line.strip() == "[Behaviour]":
                    behaviour_index = i
                    break

            if behaviour_index == -1:
                lines.append("\n[Behaviour]\n")
                behaviour_index = len(lines) - 2

            font_settings = {
                "OverrideFontTextMeshPro": "LiberationSans SDF",
                "FallbackFontTextMeshPro": "LiberationSans SDF"
            }

            for key, value in font_settings.items():
                found = False
                for i in range(behaviour_index + 1, len(lines)):
                    if lines[i].strip().startswith("["):
                        break
                    if lines[i].startswith(key + "="):
                        lines[i] = f"{key}={value}\n"
                        found = True
                        break
                if not found:
                    lines.insert(behaviour_index + 1, f"{key}={value}\n")
                    behaviour_index += 1

            with open(config_path, 'w', encoding='utf-8') as f:
                f.writelines(lines)

            return True, "✅ Türkçe font desteği eklendi!\n\nKullanılan Font: LiberationSans SDF"
        except Exception as e:
            return False, f"İşlem sırasında hata oluştu: {e}"
