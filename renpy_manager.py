import os
import json
import shutil
import urllib.request
import zipfile
import io
import sys
import subprocess
from pathlib import Path
import re
import concurrent.futures
import ssl
from config import Constants, Config

try:
    from deep_translator import GoogleTranslator
except ImportError:
    GoogleTranslator = None

class RenPyManager:
    """
    Ren'Py oyunları için çeviri yöneticisi.
    """
    MAX_WORKERS = Constants.MAX_WORKERS

    @staticmethod
    def detect_engine(game_path):
        """
        Oyunun Ren'Py olup olmadığını esnek bir şekilde kontrol eder.
        """
        try:
            path = Path(game_path)
            if path.is_file():
                path = path.parent
                
            # 1. "renpy" ve "game" klasörü yan yanaysa
            if (path / "renpy").exists() and (path / "game").exists():
                return "Ren'Py"
                
            # 2. game klasörüne veya kendi içine bak
            game_dir = path / "game" if (path / "game").exists() else path
            
            # .rpa, .rpyc, .rpy uzantılarını case-insensitive kontrol et (örn: .RPA)
            rpa_files = list(game_dir.glob("*.[rR][pP][aA]")) + list(game_dir.glob("*.rpa.bak"))
            rpyc_files = list(game_dir.glob("*.[rR][pP][yY][cC]"))
            rpy_files = list(game_dir.glob("*.[rR][pP][yY]"))
            
            if rpa_files or rpyc_files or rpy_files:
                return "Ren'Py"
                
            # 3. Ana klasörde .py dosyası (DDLC.py gibi) ve game klasörü varsa
            if (path / "game").exists() and list(path.glob("*.py")):
                return "Ren'Py"
        except Exception:
            pass

        return None

    @staticmethod
    def _download_tools(progress_callback=None):
        tools_dir = Path(Config.BASE_PATH) / "tools" / "renpy_tools"
        tools_dir.mkdir(parents=True, exist_ok=True)
        
        unrpyc_dir = tools_dir / "unrpyc-master"
        unrpyc_script = unrpyc_dir / "unrpyc.py"
        rpatool_script = tools_dir / "rpatool"

        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE

        if not unrpyc_script.exists():
            if progress_callback: progress_callback("⏳ unrpyc aracı indiriliyor...")
            url = "https://github.com/CensoredUsername/unrpyc/archive/refs/heads/master.zip"
            try:
                req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
                res = urllib.request.urlopen(req, context=ctx, timeout=15)
                with zipfile.ZipFile(io.BytesIO(res.read())) as z:
                    z.extractall(tools_dir)
            except Exception as e:
                if progress_callback: progress_callback(f"❌ unrpyc indirilemedi: {e}")
                return False, None, None

        if not rpatool_script.exists():
            if progress_callback: progress_callback("⏳ rpatool indiriliyor...")
            url = "https://raw.githubusercontent.com/Shizmob/rpatool/master/rpatool"
            try:
                req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
                res = urllib.request.urlopen(req, context=ctx, timeout=15)
                with open(rpatool_script, "wb") as f:
                    f.write(res.read())
            except Exception as e:
                if progress_callback: progress_callback(f"❌ rpatool indirilemedi: {e}")
                return False, None, None

        return True, unrpyc_script, rpatool_script

    @staticmethod
    def _get_translator(service, api_key, target_lang):
        if service == "deepl" and api_key:
            import deepl
            return deepl.Translator(api_key)
        elif service == "gemini" and api_key:
            from unreal_manager import GeminiTranslator
            return GeminiTranslator(api_key, target_lang=target_lang)
        elif service == "google":
            if GoogleTranslator:
                return GoogleTranslator(source='auto', target=target_lang)
        return None

    @staticmethod
    def _translate_text(text, translator_obj, service, persist_cache=None):
        if not text or not text.strip() or len(text.strip()) < 2: return text
        if text.isdigit(): return text

        # [YENİ] Kalıcı önbellek: daha önce çevrildiyse API'ye hiç gitme
        if persist_cache:
            cached = persist_cache.get(text)
            if cached:
                return cached

        result = text
        try:
            if service == "deepl":
                res = translator_obj.translate_text(text, target_lang="TR")
                result = res.text
            elif service == "gemini":
                res = translator_obj.translate(text)
                result = res if res else text
            elif service == "google":
                result = translator_obj.translate(text)
        except:
            return text

        if persist_cache and result and result != text:
            persist_cache.set(text, result)
        return result

    @staticmethod
    def process_game(game_path, service="google", api_key="", max_workers=10, target_lang="tr", progress_callback=None, progress_max_callback=None, progress_bar_callback=None):
        path = Path(game_path)
        if path.is_file(): path = path.parent
        
        # Ren'Py oyunlarında scanner yanlışlıkla "lib/windows-i686" içindeki asıl motor exe'sini seçebilir.
        # Böyle bir durumda oyunun gerçek ana dizinine (kök klasörüne) çıkmamız gerekir.
        if path.parent.name.lower() == "lib":
            path = path.parent.parent
        elif path.name.lower() == "lib":
            path = path.parent
            
        engine = RenPyManager.detect_engine(path)
        if not engine:
            if progress_callback: progress_callback(f"❌ HATA: '{path}' dizininde Ren'Py oyunu tespit edilemedi. (Lütfen oyunun kısayolunu değil, ana exe dosyasını seçtiğinizden emin olun)")
            return False, f"Geçerli bir Ren'Py oyunu bulunamadı: {path}"

        if progress_callback: progress_callback(f"🎮 {engine} motoru tespit edildi. İşlem başlıyor...")

        game_dir = path / "game" if (path / "game").exists() else path
        
        # 1. Araçları İndir
        success, unrpyc_script, rpatool_script = RenPyManager._download_tools(progress_callback)
        if not success:
            return False, "Ren'Py çeviri araçları (unrpyc/rpatool) indirilemedi. İnternet bağlantınızı kontrol edin."

        # En güvenli Python yorumlayıcısını (kendimizi) kullanalım
        python_exe = sys.executable

        # Eğer daha önceki hatalı bir denemeden kalan .rpa.bak varsa, orijinaline çevirelim
        bak_rpa_files = list(game_dir.glob("*.rpa.bak"))
        for bak in bak_rpa_files:
            try:
                orig = bak.with_suffix("")
                if not orig.exists():
                    bak.rename(orig)
            except: pass

        # 2. RPA Dosyalarını Çıkar (unrpa / rpatool)
        rpa_files = list(game_dir.glob("*.rpa"))
        if rpa_files:
            unrpa_path = Path(Config.BASE_PATH) / "unrpa-2.3.0"
            if progress_callback: progress_callback(f"📦 {len(rpa_files)} RPA arşivi dışa aktarılıyor. Bu işlem dosya boyutuna göre uzun sürebilir...")
            for rpa in rpa_files:
                try:
                    startupinfo = subprocess.STARTUPINFO()
                    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                    startupinfo.wShowWindow = subprocess.SW_HIDE
                    
                    if unrpa_path.exists():
                        cmd = [python_exe, "-m", "unrpa", "-p", str(game_dir), str(rpa)]
                        env = os.environ.copy()
                        env["PYTHONPATH"] = str(unrpa_path)
                        subprocess.run(cmd, startupinfo=startupinfo, cwd=str(unrpa_path), check=True, env=env)
                    else:
                        cmd = [python_exe, str(rpatool_script), "-x", str(rpa), "-o", str(game_dir)]
                        subprocess.run(cmd, startupinfo=startupinfo, check=True)
                    
                    # Çıkarılan RPA dosyasını gizle/yedekle ki oyun rpy/rpyc dosyalarını okusun
                    backup_rpa = rpa.with_suffix(".rpa.bak")
                    if backup_rpa.exists():
                        backup_rpa.unlink()
                    rpa.rename(backup_rpa)
                except Exception as e:
                    if progress_callback: progress_callback(f"⚠️ RPA çıkarma hatası ({rpa.name}): {e}")

        # 3. RPYC Dosyalarını Decompile Et (unrpyc)
        rpyc_files = list(game_dir.rglob("*.rpyc"))
        if rpyc_files:
            if progress_callback: progress_callback(f"🔓 {len(rpyc_files)} RPYC scripti decompile ediliyor (RPY formatına dönüştürülüyor)...")
            failed_count = 0
            last_error = ""
            for rpyc in rpyc_files:
                try:
                    if progress_callback: progress_callback(f"🔓 {rpyc.name} decompile ediliyor...")
                    
                    # Scriptin adını direkt kullanalım, cwd o klasörde olduğu için modülleri bulacaktır
                    cmd = [python_exe, "-u", "unrpyc.py", "--clobber", str(rpyc.absolute())]
                    startupinfo = subprocess.STARTUPINFO()
                    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                    startupinfo.wShowWindow = subprocess.SW_HIDE
                    
                    env = os.environ.copy()
                    env["PYTHONPATH"] = str(unrpyc_script.parent) + os.pathsep + env.get("PYTHONPATH", "")
                    
                    result = subprocess.run(cmd, startupinfo=startupinfo, cwd=str(unrpyc_script.parent), capture_output=True, text=True, env=env)
                    if result.returncode != 0:
                        failed_count += 1
                        last_error = result.stderr.strip()
                except Exception as e:
                    failed_count += 1
                    last_error = str(e)
            
            if failed_count > 0 and progress_callback:
                progress_callback(f"⚠️ Uyarı: {failed_count} dosya decompile edilemedi (Oyun eski sürüm olabilir). Son Hata: {last_error[:200]}")

        # Yalnızca başarılı şekilde decompile edilmiş RPY dosyalarının eski RPYC hallerini silelim
        rpy_files_temp = list(game_dir.rglob("*.rpy"))
        for rpy in rpy_files_temp:
            rpyc = rpy.with_suffix(".rpyc")
            try:
                if rpyc.exists(): rpyc.unlink()
            except: pass

        # 4. Çeviri Aşaması
        rpy_files = list(game_dir.rglob("*.rpy"))
        # screens.rpy veya options.rpy gibi sistem dosyalarını filtreleyebiliriz ama şimdilik hepsi
        
        if not rpy_files:
            return False, "Çevrilecek .rpy kaynak dosyası bulunamadı."

        if progress_callback: progress_callback(f"🌐 {len(rpy_files)} RPY kaynak dosyasında çeviri işlemi başlatılıyor...")
        
        translator_obj = RenPyManager._get_translator(service, api_key, target_lang)
        if not translator_obj:
            return False, f"Çeviri servisi başlatılamadı ({service}). Lütfen API Anahtarınızı kontrol edin."

        # [YENİ] Kalıcı Global Çeviri Önbelleği (oyunlar arası, ücretsiz kullanım)
        persist_cache = None
        try:
            from translation_cache import TranslationCache
            persist_cache = TranslationCache(target_lang=target_lang)
            if len(persist_cache) > 0 and progress_callback:
                progress_callback(f"💾 Kalıcı önbellek hazır: {len(persist_cache)} hazır çeviri mevcut.")
        except Exception as e:
            print(f"Kalıcı önbellek açılamadı (çeviri normal devam eder): {e}")

        # Regex: (Boşluklar ve isteğe bağlı karakter ismi/tagleri) " (İçerik) " (Varsa :)
        # Desteklenenler: "Sadece Diyalog", karakter "Diyalog", karakter tag "Diyalog", "Karakter Adı" "Diyalog"
        dialogue_pattern = re.compile(r'^(\s*(?:(?:"[^"]+"\s+)|(?:[a-zA-Z0-9_]+\s+)*)?)(")(.*)(")(:?)\s*$')
        
        def process_rpy(rpy_file):
            try:
                # Sistem yapılandırma dosyalarını atlasak iyi olur, oyun motorunu bozabilir.
                if rpy_file.name in ["options.rpy", "gui.rpy", "screens.rpy"]:
                    return True
                    
                with open(rpy_file, "r", encoding="utf-8", errors="ignore") as f:
                    lines = f.readlines()
                
                changed = False
                ignore_keywords = {"old", "new", "image", "define", "default", "transform", "style", "screen", "python", "init", "label", "jump", "call", "scene", "show", "hide", "play", "stop", "voice"}
                
                for i, line in enumerate(lines):
                    r_line = line.rstrip('\r\n')
                    match = dialogue_pattern.match(r_line)
                    if match:
                        prefix, q1, text, q2, colon = match.groups()
                        
                        prefix_stripped = prefix.strip()
                        first_word = prefix_stripped.split()[0] if prefix_stripped else ""
                        
                        # Eğer bu bir çeviri anahtarı veya kod blokuysa atla
                        if first_word in ignore_keywords:
                            continue
                            
                        # Ren'Py menü seçenekleri veya kod satırları kontrolü
                        if " % " in text or text.startswith("%"):
                            continue
                            
                        # İçerik yeterince uzunsa çevir
                        if len(text.strip()) > 1:
                            tr_text = RenPyManager._translate_text(text, translator_obj, service, persist_cache=persist_cache)
                            if tr_text and tr_text != text:
                                # Çeviride sorun çıkmaması için çift tırnakları tek tırnağa çevir
                                tr_text = tr_text.replace('"', "'")
                                lines[i] = f"{prefix}{q1}{tr_text}{q2}{colon}\n"
                                changed = True
                                if progress_callback:
                                    progress_callback(f"📝 {text[:40]} ➔ {tr_text[:40]}")
                
                if changed:
                    with open(rpy_file, "w", encoding="utf-8") as f:
                        f.writelines(lines)
                return True
            except Exception as e:
                return False

        if progress_max_callback: progress_max_callback(len(rpy_files))
        
        completed = 0
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(process_rpy, f): f for f in rpy_files}
            for future in concurrent.futures.as_completed(futures):
                completed += 1
                if progress_bar_callback: progress_bar_callback(completed)

        # [YENİ] Önbelleği diske kaydet
        if persist_cache:
            try:
                persist_cache.save()
            except Exception:
                pass

        if progress_callback: progress_callback("✅ Çeviri başarıyla tamamlandı!")
        if progress_callback: progress_callback("ℹ️ BİLGİ: Oyunu başlattığınızda Ren'Py ilk açılışta çevrilmiş dosyaları derleyecektir, bu yüzden açılış biraz uzun sürebilir.")

        return True, "Başarılı! Ren'Py çevirisi tamamlandı."
