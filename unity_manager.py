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
            # Kullanıcı doğrudan .assets seçtiyse
            files_to_process = [target]
        else:
            if progress_callback: progress_callback(f"Oyun klasörü taranıyor: {target.name} ...")
            files_to_process = list(target.rglob("*.assets"))

        total_translated = 0
        for f in files_to_process:
            if f.stat().st_size > 300 * 1024 * 1024: # Skip files > 300MB
                continue

            # I2Languages çevirisi dene
            count = UnityManager._process_i2languages(f, service, api_key, progress_callback, target_lang, source_lang)
            if count > 0:
                total_translated += count
                
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
                if progress_callback: progress_callback("❌ Hata: Bu dosyada I2Languages tablosu bulunamadı. (Sadece TextAsset içeriyor olabilir, henüz desteklenmiyor).")
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
                text = trans_list[source_idx] if source_idx < len(trans_list) else ""
                
                # Sadece hedef dil boşsa veya İngilizce ise çevir
                existing_target = trans_list[target_idx] if target_idx < len(trans_list) else ""
                if text and isinstance(text, str) and text.strip():
                    if not existing_target or existing_target == text:
                        to_translate.append((idx, text))
            
            total_to_translate = len(to_translate)
            if progress_callback: progress_callback(f"I2Languages Çevrilecek: {total_to_translate}")
            
            if not to_translate:
                if progress_callback: progress_callback("ℹ️ Bilgi: Hedef dil için çevrilecek eksik metin bulunamadı (Zaten çevrilmiş olabilir).")
                return 0
                
            translated_count = 0
            batch_size = 50
            batches = [to_translate[i:i + batch_size] for i in range(0, len(to_translate), batch_size)]
            translator = GoogleTranslator(source=source_lang, target=target_lang)
            
            for b_idx, batch in enumerate(batches):
                protected_batch = []
                batch_tags = []
                for term_idx, orig_text in batch:
                    protected_text, tags = UnityManager._protect_tags(orig_text)
                    protected_batch.append(protected_text)
                    batch_tags.append((term_idx, orig_text, tags))
                    
                try:
                    translated_batch = translator.translate_batch(protected_batch)
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
                    if progress_callback: progress_callback(f"[{translated_count}/{total_to_translate}] Çevrildi. (Batch {b_idx+1}/{len(batches)})")
                except Exception as ex:
                    if progress_callback: progress_callback(f"Batch {b_idx+1} Hatası ({ex}). Tekli çeviri...")
                    for term_idx, orig_text, tags in batch_tags:
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
                        except:
                            translated_count += 1
                            
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
