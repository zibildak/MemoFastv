
import os
import shutil
import zipfile
import sys
import urllib.request
import ssl
from pathlib import Path
from config import Config
from logger import setup_logger

logger = setup_logger(__name__)

class TranslatorManager:
    """
    XUnity.AutoTranslator ve BepInEx/MelonLoader yönetim sınıfı.
    
    Özellikleri:
    - BepInEx ve MelonLoader kurulumu/kaldırması
    - XUnity.AutoTranslator kurulumu
    - IL2CPP ve Mono desteği
    - x86/x64 mimarileri
    - ZIP dosya yönetimi
    """
    
    TOOLS_PATH = Config.BASE_PATH / "files" / "tools"
    
    # Patterns - BepInEx
    BEPINEX_X64_PATTERN = "BepInEx_x64_*.zip"                      # 5.4.x Stable (Mono, eski Unity)
    BEPINEX_X86_PATTERN = "BepInEx_x86_*.zip"                      # 5.4.x Stable x86
    BEPINEX_MONO_BE_X64_PATTERN = "BepInEx-Unity.Mono-win-x64-*.zip"  # 6.x BE Mono x64
    BEPINEX_MONO_BE_X86_PATTERN = "BepInEx-Unity.Mono-win-x86-*.zip"  # 6.x BE Mono x86
    BEPINEX_IL2CPP_LEGACY_PATTERN = "BepInEx*UnityIL2CPP*.zip"     # IL2CPP Legacy (pre.1)
    BEPINEX_IL2CPP_MODERN_PATTERN = "BepInEx-Unity.IL2CPP-*.zip"   # IL2CPP Modern BE
    BEPINEX_NETCORECLR_PATTERN = "BepInEx-NET.CoreCLR-*.zip"        # .NET 6/CoreCLR oyunlar

    TRANSLATOR_PATTERN = "XUnity.AutoTranslator-BepInEx-*.zip"
    TRANSLATOR_IL2CPP_PATTERN = "XUnity.AutoTranslator-BepInEx-IL2CPP-*.zip"
    
    # MelonLoader Patterns
    MELON_X64_PATTERN = "MelonLoader*.zip"
    MELON_X86_PATTERN = "MelonLoader*.zip"
    MELON_UNITY6_PATTERN = "MelonLoader*.zip"
    TRANSLATOR_MELON_PATTERN = "XUnity.AutoTranslator-MelonMod-*.zip"
    TRANSLATOR_MELON_IL2CPP_PATTERN = "XUnity.AutoTranslator-MelonMod-IL2CPP-*.zip"

    # Anti-Cheat imzaları (bunlar varsa loader çalışmaz)
    ANTICHEAT_SIGNATURES = {
        "EasyAntiCheat": ["EasyAntiCheat", "EasyAntiCheat_launcher.exe", "EasyAntiCheat_Setup.exe"],
        "BattlEye":      ["BattlEye", "BEClient.dll", "BEService.exe"],
        "Vanguard":      ["vgc.exe", "vanguard"],
        "nProtect":      ["npgamemon.exe", "GameGuard"],
        "XIGNCODE3":     ["xigncode", "x3.xem"],
        "EQU8":          ["equ8.dll", "equ8"],
    }

    @staticmethod
    def get_tool_files():
        """
        Sistemdeki mevcut araç dosyalarını bul.
        
        Bulur:
        - BepInEx (x64/x86, Mono/IL2CPP)
        - MelonLoader (x64/x86, Unity 6)
        - XUnity.AutoTranslator (BepInEx/Melon, Mono/IL2CPP)
        
        Returns:
            dict: {
                'bepinex_x64': [...],
                'bepinex_x86': [...],
                'bepinex_il2cpp_legacy': [...],
                'bepinex_il2cpp_modern': [...],
                'translator': [...],
                'translator_il2cpp': [...],
                'melon_x64': [...],
                'translator_melon': [...],
                ...
            }
            
        Note:
            Dosyalar versiyon'a göre sıralanır (en yeni önce)
        """
        tools = {
            'bepinex_x64': [],           # BepInEx 5.4.x Stable (Mono eski)
            'bepinex_x86': [],           # BepInEx 5.4.x x86
            'bepinex_mono_be_x64': [],   # BepInEx 6.x BE Mono x64
            'bepinex_mono_be_x86': [],   # BepInEx 6.x BE Mono x86
            'bepinex_il2cpp_legacy': [], # IL2CPP pre.1 (eski)
            'bepinex_il2cpp_modern': [], # IL2CPP BE (modern)
            'bepinex_netcoreclr': [],    # .NET CoreCLR oyunlar
            'translator': [],
            'translator_il2cpp': [],
            'melon_x64': [],
            'melon_x86': [],
            'translator_melon': [],
            'translator_melon_il2cpp': []
        }
        
        if not TranslatorManager.TOOLS_PATH.exists():
            return tools

        def sort_files(file_list):
            file_list.sort(key=lambda x: x.name, reverse=True)
            return file_list

        tools['bepinex_x64']         = sort_files(list(TranslatorManager.TOOLS_PATH.glob(TranslatorManager.BEPINEX_X64_PATTERN)))
        tools['bepinex_x86']         = sort_files(list(TranslatorManager.TOOLS_PATH.glob(TranslatorManager.BEPINEX_X86_PATTERN)))
        tools['bepinex_mono_be_x64'] = sort_files(list(TranslatorManager.TOOLS_PATH.glob(TranslatorManager.BEPINEX_MONO_BE_X64_PATTERN)))
        tools['bepinex_mono_be_x86'] = sort_files(list(TranslatorManager.TOOLS_PATH.glob(TranslatorManager.BEPINEX_MONO_BE_X86_PATTERN)))
        tools['bepinex_il2cpp_legacy'] = sort_files(list(TranslatorManager.TOOLS_PATH.glob(TranslatorManager.BEPINEX_IL2CPP_LEGACY_PATTERN)))
        tools['bepinex_il2cpp_modern'] = sort_files(list(TranslatorManager.TOOLS_PATH.glob(TranslatorManager.BEPINEX_IL2CPP_MODERN_PATTERN)))
        tools['bepinex_netcoreclr']  = sort_files(list(TranslatorManager.TOOLS_PATH.glob(TranslatorManager.BEPINEX_NETCORECLR_PATTERN)))

        all_translators   = list(TranslatorManager.TOOLS_PATH.glob(TranslatorManager.TRANSLATOR_PATTERN))
        il2cpp_translators = list(TranslatorManager.TOOLS_PATH.glob(TranslatorManager.TRANSLATOR_IL2CPP_PATTERN))
        standard_translators = [f for f in all_translators if "-IL2CPP-" not in f.name]
        
        tools['translator']            = sort_files(standard_translators)
        tools['translator_il2cpp']     = sort_files(il2cpp_translators)
        tools['melon_x64']             = sort_files(list(TranslatorManager.TOOLS_PATH.glob(TranslatorManager.MELON_X64_PATTERN)))
        tools['melon_x86']             = sort_files(list(TranslatorManager.TOOLS_PATH.glob(TranslatorManager.MELON_X86_PATTERN)))
        tools['translator_melon']      = sort_files(list(TranslatorManager.TOOLS_PATH.glob(TranslatorManager.TRANSLATOR_MELON_PATTERN)))
        tools['translator_melon_il2cpp'] = sort_files(list(TranslatorManager.TOOLS_PATH.glob(TranslatorManager.TRANSLATOR_MELON_IL2CPP_PATTERN)))
        
        return tools

    @staticmethod
    def get_arch_from_filename(filename):
        """
        Dosya isminden mimari (x86/x64) tahmini yap.
        
        Args:
            filename: İncelenecek dosya adı
            
        Returns:
            str: 'x64', 'x86', veya 'unknown'
        """
        filename = filename.lower()
        if "x64" in filename or "win-x64" in filename or "64.zip" in filename: return "x64"
        if "x86" in filename or "win-x86" in filename or "32.zip" in filename: return "x86"
        return "unknown"

    @staticmethod
    def is_ready():
        """
        Sistem çeviri için hazır mı kontrol et.
        
        En az bir BepInEx/MelonLoader ve bir Translator kurulu olması gerekir.
        
        Returns:
            bool: True ise tüm gerekli dosyalar var
        """
        f = TranslatorManager.get_tool_files()
        has_mono = (f['bepinex_x64'] or f['bepinex_x86'])
        has_il2cpp = (f['bepinex_il2cpp_legacy'] or f['bepinex_il2cpp_modern'])
        has_trans = (f['translator'] or f['translator_il2cpp'])
        return (has_mono or has_il2cpp) and has_trans

    @staticmethod
    def analyze_pe_header(exe_path):
        """
        PE Header okuyarak executable'ın mimarisini tespit et.
        
        Args:
            exe_path: Kontrol edilecek EXE dosyasının yolu
            
        Returns:
            str: 'x86', 'x64', veya 'unknown'
            
        PE Machine Types:
            0x14c (332) = x86 (32-bit)
            0x8664 (34404) = x64 (64-bit)
        """
        try:
            with open(exe_path, 'rb') as f:
                # MZ signature check
                if f.read(2) != b'MZ': return "unknown"
                
                # PE Header offset
                f.seek(60)
                pe_offset = int.from_bytes(f.read(4), 'little')
                
                # PE Signature check (PE\0\0)
                f.seek(pe_offset)
                if f.read(4) != b'PE\0\0': return "unknown"
                
                # Machine Type (2 bytes)
                machine = int.from_bytes(f.read(2), 'little')
                
                if machine == 0x14c: return "x86"
                if machine == 0x8664: return "x64"
        except Exception as e:
            print(f"PE Header Analysis Error: {e}")
        return "x64" # Default fallback

    @staticmethod
    def detect_game_architecture(exe_path):
        """Oyunun x86 mı x64 mü olduğunu döner"""
        return TranslatorManager.analyze_pe_header(exe_path)

    @staticmethod
    def get_unity_version(game_path):
        """
        Oyunun Unity versiyonunu tespit et.
        
        Arar:
        - globalgamemanagers dosyası
        - UnityPlayer.dll
        
        Args:
            game_path: Oyun ana klasörü
            
        Returns:
            str: Unity versiyonu (örn: '2022.3.15f1'), yoksa None
            
        Note:
            Yıl bazlı IL2CPP vs Mono ayrımı yapabilmek için kullanılır
        """
        import re
        try:
            game_path = Path(game_path)
            candidates = []
            
            # 1. globalgamemanagers
            data_folders = list(game_path.glob("*_Data"))
            if data_folders:
                candidates.append(data_folders[0] / "globalgamemanagers")
                candidates.append(data_folders[0] / "mainData")
            
            # 2. UnityPlayer.dll
            candidates.append(game_path / "UnityPlayer.dll")

            version_pattern = re.compile(b'\\d{4}\\.\\d+\\.\\d+[abfp]\\d+|\\d+\\.\\d+\\.\\d+[abfp]\\d+')
            
            for cand in candidates:
                if not cand.exists(): continue
                try:
                    with open(cand, 'rb') as f:
                        data = f.read(20 * 1024 * 1024) # Ilk 20MB
                        matches = version_pattern.findall(data)
                        if matches:
                            for m in matches:
                                v_str = m.decode('utf-8')
                                if len(v_str) > 5:
                                    return v_str
                except: pass
        except: pass
        return "Unknown"

    @staticmethod
    def detect_game_backend(game_path):
        """
        Oyunun Mono mu yoksa IL2CPP mi olduğunu tespit eder.
        Data/il2cpp_data veya GameAssembly.dll -> IL2CPP
        Data/Managed -> Mono
        """
        try:
            game_path = Path(game_path)
            # 1. Klasör bazlı kontrol (Managed öncelikli - Mono false negative'i önlemek için)
            for item in game_path.iterdir():
                if item.is_dir() and item.name.endswith("_Data"):
                    if (item / "Managed").exists(): return "mono"
                    if (item / "il2cpp_data").exists(): return "il2cpp"
            
            # 2. DLL bazlı kontrol (Yedek)
            if (game_path / "GameAssembly.dll").exists(): return "il2cpp"
            
            # 3. MonoBleedingEdge kontrolü
            if (game_path / "MonoBleedingEdge").exists(): return "mono"
            
            if (game_path / "UnityPlayer.dll").exists():
                 pass
        except: pass
        return "mono" # Default candidate

    @staticmethod
    def is_unity_6_or_newer(unity_version):
        """Unity versiyonunun 6 veya daha yeni olup olmadığını kontrol eder"""
        if not unity_version or unity_version == "Unknown":
            return False
        try:
            # Unity 6 formatı: "6000.x.x" veya "6.x.x"
            parts = unity_version.split('.')
            if len(parts) > 0:
                major = int(parts[0])
                # 6000.x.x formatı (Unity 6)
                if major >= 6000:
                    return True
                # 6.x.x formatı
                if major >= 6:
                    return True
        except:
            pass
        return False

    @staticmethod
    def extract_melon_version(filename):
        """
        MelonLoader dosya isminden versiyon numarasını çıkarır.
        3 parçalı (0.6.6, 0.7.1) ve 4 parçalı (0.7.2.2394) formatları destekler.
        Her zaman 4 elemanlı tuple döndürür: (major, minor, patch, build)
        Örn: '0.6.6' -> (0, 6, 6, 0), '0.7.2.2394' -> (0, 7, 2, 2394)
        """
        import re
        # 4 parçalı: 0.7.2.2394
        match4 = re.search(r'(\d+)\.(\d+)\.(\d+)\.(\d+)', filename)
        if match4:
            return (int(match4.group(1)), int(match4.group(2)), int(match4.group(3)), int(match4.group(4)))
        # 3 parçalı: 0.6.6, 0.7.1
        match3 = re.search(r'(\d+)\.(\d+)\.(\d+)', filename)
        if match3:
            return (int(match3.group(1)), int(match3.group(2)), int(match3.group(3)), 0)
        return None

    @staticmethod
    def select_best_melon_for_unity(melon_files, unity_version, arch):
        """
        Unity versiyonuna göre en uygun MelonLoader dosyasını seçer.

        Unity 6 için öncelik sırası:
          1. 0.7.2.xxxx  (en DÜŞÜK build önerilir - daha fazla oyunla uyumlu, ör: 2384)
          2. 0.7.x       (diğer 0.7 sürümleri, en yeni)
          3. 0.6.x       (eski fallback, en yeni)
          4. versiyonsuz dosyalar

        Unity 5 ve altı için: en yeni versiyon seçilir.
        """
        if not melon_files:
            return None

        # Mimariye göre filtrele (x64 veya x86)
        arch_filtered = []
        for f in melon_files:
            fname_lower = f.name.lower()
            if arch.lower() == "x64":
                if "x64" in fname_lower or "64" in fname_lower:
                    arch_filtered.append(f)
            elif arch.lower() == "x86":
                if "x86" in fname_lower or ("32" in fname_lower and "64" not in fname_lower):
                    arch_filtered.append(f)

        # Mimariye uygun dosya yoksa tümünü kullan
        if not arch_filtered:
            arch_filtered = melon_files

        # Unity 6 kontrolü
        is_unity_6 = TranslatorManager.is_unity_6_or_newer(unity_version)

        if is_unity_6:
            # Sürümlere göre gruplara ayır
            group_0_7_2 = []   # 0.7.2.xxxx - build numaralı en yeni
            group_0_7   = []   # 0.7.x (build numarasız)
            group_0_6   = []   # 0.6.x (eski uyumlu)
            no_version  = []

            for f in arch_filtered:
                version = TranslatorManager.extract_melon_version(f.name)
                if version:
                    major, minor, patch, build = version
                    if major == 0 and minor == 7 and patch == 2 and build > 0:
                        group_0_7_2.append((f, version))
                    elif major == 0 and minor == 7:
                        group_0_7.append((f, version))
                    elif major == 0 and minor == 6:
                        group_0_6.append((f, version))
                    else:
                        group_0_7_2.append((f, version))  # bilinmeyen ama versiyonlu → en yeni gruba
                else:
                    no_version.append(f)

            # Öncelik: 0.7.2.x (en düşük build) > 0.7.x (en yeni) > 0.6.x (en yeni) > versiyonsuz
            if group_0_7_2:
                group_0_7_2.sort(key=lambda x: x[1], reverse=False)  # en düşük build önce
                return group_0_7_2[0][0]
            for group in [group_0_7, group_0_6]:
                if group:
                    group.sort(key=lambda x: x[1], reverse=True)  # diğerleri en yeni
                    return group[0][0]
            if no_version:
                return no_version[0]

        else:
            # Unity 6 değilse en yeni versiyonu seç
            versioned = []
            no_version = []

            for f in arch_filtered:
                version = TranslatorManager.extract_melon_version(f.name)
                if version:
                    versioned.append((f, version))
                else:
                    no_version.append(f)

            if versioned:
                versioned.sort(key=lambda x: x[1], reverse=True)
                return versioned[0][0]
            elif no_version:
                return no_version[0]

        # Son fallback
        return arch_filtered[0] if arch_filtered else (melon_files[0] if melon_files else None)

    @staticmethod
    def detect_unity_year(unity_version):
        """Unity versiyonundan yıl/major sayısını döndürür. Örn: '2021.3.5f1' -> 2021, '6000.0.1' -> 6000"""
        if not unity_version or unity_version == "Unknown":
            return 0
        try:
            return int(unity_version.split('.')[0])
        except:
            return 0

    @staticmethod
    def detect_dotnet_runtime(game_path):
        """
        Oyunun .NET runtime tipini tespit eder.
        Returns: 'net6', 'net4', 'netcore3' veya 'unknown'
        """
        game_path = Path(game_path)
        # .NET 6+ : UnityCrashHandler64.exe yanında libcoreclr.so veya coreclr.dll
        if (game_path / "coreclr.dll").exists():
            return "net6"
        # .NET 6 marker: MonoBleedingEdge klasörü YOK ama UnityPlayer var
        for item in game_path.glob("*_Data"):
            # net6/net47 ayırımı için runtime klasörü
            if (item / "boot.config").exists():
                try:
                    with open(item / "boot.config", "r", encoding="utf-8", errors="ignore") as f:
                        content = f.read()
                        if "scripting-runtime-version=latest" in content or "dotnet-runtime-version=net6" in content:
                            return "net6"
                        if "netframework" in content.lower():
                            return "net4"
                except:
                    pass
        if (game_path / "MonoBleedingEdge").exists():
            return "net4"
        return "unknown"

    @staticmethod
    def detect_anticheat(game_path):
        """
        Oyun klasöründe Anti-Cheat imzalarını tarar.
        Returns: list of str (bulunan AC isimleri), boşsa güvenli
        """
        game_path = Path(game_path)
        found = []
        try:
            all_entries = set()
            for item in game_path.rglob("*"):
                all_entries.add(item.name.lower())

            for ac_name, signatures in TranslatorManager.ANTICHEAT_SIGNATURES.items():
                for sig in signatures:
                    if sig.lower() in all_entries:
                        found.append(ac_name)
                        break
        except Exception as e:
            logger.debug("Anti-cheat scan error: %s", e)
        return list(set(found))  # tekrar yok

    @staticmethod
    def check_global_metadata(game_path):
        """
        IL2CPP oyunlar için global-metadata.dat varlığını kontrol eder.
        Returns: (bool exists, Path|None)
        """
        game_path = Path(game_path)
        candidates = [
            game_path / "il2cpp_data" / "Metadata" / "global-metadata.dat",
        ]
        for item in game_path.glob("*_Data"):
            candidates.append(item / "il2cpp_data" / "Metadata" / "global-metadata.dat")
        for path in candidates:
            if path.exists() and path.stat().st_size > 1000:
                return True, path
        return False, None

    @staticmethod
    def get_compatible_tools(exe_path):
        """
        Oyuna en uygun araçları tespit eder ve önerir (Gelişmiş Akıllı Seçim).

        Kural Seti:
          Unity 5.x – 2018.x (Mono)       → BepInEx 5.4.x Stable
          Unity 2019.x – 2021.x (Mono)    → BepInEx 6.x BE Mono
          Unity 2019.x – 2021.x (IL2CPP)  → MelonLoader 0.6.x (en kararlı)
          Unity 2022.x – Unity 6+ (Mono)  → BepInEx 6.x BE Mono
          Unity 2022.x – Unity 6+ (IL2CPP)→ MelonLoader 0.7.x
          x86 oyun                        → Her zaman BepInEx (ML x86 zayıf)
          .NET CoreCLR tespit edilirse     → BepInEx-NET.CoreCLR önerilir
          Anti-Cheat varsa                 → uyarı, kurulum önerilmez
          IL2CPP + global-metadata eksik  → uyarı

        Returns dict with full analysis + recommendations.
        """
        exe_path = Path(exe_path)
        game_path = exe_path.parent

        arch       = TranslatorManager.detect_game_architecture(exe_path)
        backend    = TranslatorManager.detect_game_backend(game_path)
        unity_ver  = TranslatorManager.get_unity_version(game_path)
        is_unity_6 = TranslatorManager.is_unity_6_or_newer(unity_ver)
        unity_year = TranslatorManager.detect_unity_year(unity_ver)
        dotnet     = TranslatorManager.detect_dotnet_runtime(game_path)
        anticheat  = TranslatorManager.detect_anticheat(game_path)

        all_tools = TranslatorManager.get_tool_files()

        rec_bep        = None
        rec_melon      = None
        rec_trans      = None
        rec_trans_melon = None
        recommended_loader = "bepinex"
        warnings = []
        info_notes = []

        # ── KURAL 1: Anti-Cheat uyarısı ──────────────────────────────────────
        if anticheat:
            warnings.append(f"🔴 Anti-Cheat Tespit Edildi: {', '.join(anticheat)} — Mod loader ÇALIŞMAYACAK!")

        # ── KURAL 2: x86 → MelonLoader desteksiz, BepInEx zorla ─────────────
        force_bepinex = (arch == "x86")
        if arch == "x86":
            warnings.append("⚠️ 32-bit (x86) oyun: MelonLoader x86 desteği zayıftır. BepInEx önerilir.")

        # ── KURAL 3: IL2CPP + global-metadata.dat kontrolü ───────────────────
        if backend == "il2cpp":
            meta_ok, meta_path = TranslatorManager.check_global_metadata(game_path)
            if not meta_ok:
                warnings.append("⚠️ global-metadata.dat bulunamadı! Oyun dosyaları eksik olabilir. Kurulumdan önce oyunu doğrulayın.")

        # ── KURAL 4: .NET CoreCLR tespiti ─────────────────────────────────────
        if dotnet == "net6" and all_tools['bepinex_netcoreclr']:
            info_notes.append("ℹ️ .NET CoreCLR runtime tespit edildi. BepInEx-NET.CoreCLR sürümü önerilir.")

        # ── KURAL 5: Loader seçim mantığı ─────────────────────────────────────
        if force_bepinex:
            # x86 → Her zaman BepInEx 5.4 x86
            recommended_loader = "bepinex"
            if all_tools['bepinex_x86']:
                rec_bep = all_tools['bepinex_x86'][0]
            if all_tools['translator']:
                rec_trans = all_tools['translator'][0]

        elif dotnet == "net6" and all_tools['bepinex_netcoreclr']:
            # .NET CoreCLR oyun → CoreCLR BepInEx
            recommended_loader = "bepinex"
            clr_candidates = [f for f in all_tools['bepinex_netcoreclr'] if arch in f.name]
            rec_bep = clr_candidates[0] if clr_candidates else (all_tools['bepinex_netcoreclr'][0] if all_tools['bepinex_netcoreclr'] else None)
            rec_trans = all_tools['translator'][0] if all_tools['translator'] else None

        elif is_unity_6 or unity_year >= 2022:
            # Unity 2022+ veya Unity 6 ──────────────────────────────────────
            if backend == "il2cpp":
                recommended_loader = "melon"
                melon_key = 'melon_x64' if arch == "x64" else 'melon_x86'
                melon_candidates = all_tools.get(melon_key, [])
                if melon_candidates:
                    rec_melon = TranslatorManager.select_best_melon_for_unity(melon_candidates, unity_ver, arch)
                trans_candidates = all_tools.get('translator_melon_il2cpp', [])
                rec_trans_melon = trans_candidates[0] if trans_candidates else None
            else:
                # Mono 2022+ → BepInEx 6.x BE Mono
                recommended_loader = "bepinex"
                be_key = 'bepinex_mono_be_x64' if arch == "x64" else 'bepinex_mono_be_x86'
                rec_bep = all_tools[be_key][0] if all_tools[be_key] else None
                # Fallback: eski 5.4
                if not rec_bep:
                    fb_key = 'bepinex_x64' if arch == "x64" else 'bepinex_x86'
                    rec_bep = all_tools[fb_key][0] if all_tools[fb_key] else None
                rec_trans = all_tools['translator'][0] if all_tools['translator'] else None

        elif 2019 <= unity_year <= 2021:
            # Unity 2019–2021 ─────────────────────────────────────────────────
            if backend == "il2cpp":
                # IL2CPP 2019-2021 → MelonLoader 0.6.x (0.5.7 LTS yoksa en yakın)
                recommended_loader = "melon"
                melon_key = 'melon_x64' if arch == "x64" else 'melon_x86'
                melon_candidates = all_tools.get(melon_key, [])
                # 0.6.x grubunu filtrele (en kararlı bu aralık için)
                group_06 = []
                for f in melon_candidates:
                    ver = TranslatorManager.extract_melon_version(f.name)
                    if ver and ver[0] == 0 and ver[1] == 6:
                        group_06.append(f)
                if group_06:
                    rec_melon = sorted(group_06, key=lambda f: TranslatorManager.extract_melon_version(f.name) or (0,0,0,0), reverse=True)[0]
                elif melon_candidates:
                    # Fallback: mevcut en iyi
                    rec_melon = TranslatorManager.select_best_melon_for_unity(melon_candidates, unity_ver, arch)
                trans_il2cpp = all_tools.get('translator_melon_il2cpp', [])
                rec_trans_melon = trans_il2cpp[0] if trans_il2cpp else None
                info_notes.append("ℹ️ Unity 2019–2021 IL2CPP: MelonLoader 0.6.x en kararlı seçimdir.")
            else:
                # Mono 2019–2021 → BepInEx 6.x BE Mono
                recommended_loader = "bepinex"
                be_key = 'bepinex_mono_be_x64' if arch == "x64" else 'bepinex_mono_be_x86'
                rec_bep = all_tools[be_key][0] if all_tools[be_key] else None
                if not rec_bep:
                    fb_key = 'bepinex_x64' if arch == "x64" else 'bepinex_x86'
                    rec_bep = all_tools[fb_key][0] if all_tools[fb_key] else None
                rec_trans = all_tools['translator'][0] if all_tools['translator'] else None

        else:
            # Unity 5.x – 2018.x (veya bilinmiyor) → BepInEx 5.4.x Stable ──
            recommended_loader = "bepinex"
            if backend == "il2cpp":
                legacy_cands = [f for f in all_tools['bepinex_il2cpp_legacy'] if arch in f.name]
                rec_bep = legacy_cands[0] if legacy_cands else (all_tools['bepinex_il2cpp_legacy'][0] if all_tools['bepinex_il2cpp_legacy'] else None)
                rec_trans = all_tools['translator_il2cpp'][0] if all_tools['translator_il2cpp'] else None
            else:
                stable_key = 'bepinex_x64' if arch == "x64" else 'bepinex_x86'
                rec_bep = all_tools[stable_key][0] if all_tools[stable_key] else None
                rec_trans = all_tools['translator'][0] if all_tools['translator'] else None
            if unity_year > 0:
                info_notes.append(f"ℹ️ Unity {unity_year}: BepInEx 5.4.x (Stable) öneriliyor.")

        return {
            'arch': arch,
            'backend': backend,
            'unity_version': unity_ver,
            'unity_year': unity_year,
            'is_unity_6': is_unity_6,
            'dotnet_runtime': dotnet,
            'anticheat': anticheat,
            'recommended_loader_type': recommended_loader,
            'recommended_bepinex': rec_bep,
            'recommended_melon': rec_melon,
            'recommended_translator': rec_trans,
            'recommended_translator_melon': rec_trans_melon,
            'warnings': warnings,
            'info_notes': info_notes,
            'all_files': all_tools
        }

    @staticmethod
    def install(game_exe_path, service="google", api_key="", progress_callback=None, target_bepinex_zip=None, target_translator_zip=None, loader_type="bepinex", target_lang="tr"):
        """Çeviri araçlarını seçilen oyuna kur (Loader Type: 'bepinex' veya 'melon')"""
        game_path = Path(game_exe_path).parent
        files = TranslatorManager.get_tool_files()
        
        # 1. Analiz
        arch = TranslatorManager.detect_game_architecture(game_exe_path)
        backend = TranslatorManager.detect_game_backend(game_path)
        unity_ver = TranslatorManager.get_unity_version(game_path)
        
        if progress_callback: 
            progress_callback(f"🖥️ Analiz: {arch.upper()} | {backend.upper()} | Unity v{unity_ver}")
        
        # 2. Uygun Zip Seçimi
        bepinex_zip = target_bepinex_zip
        translator_zip = target_translator_zip
        
        # Translator Seçimi
        if not translator_zip:
            if backend == "il2cpp":
                translator_zip = files['translator_il2cpp'][0] if files['translator_il2cpp'] else None
            else:
                translator_zip = files['translator'][0] if files['translator'] else None
        
        # BepInEx Seçimi
        if not bepinex_zip:
            if backend == "il2cpp":
                # IL2CPP: Yıla Göre Seçim (Modern vs Legacy)
                is_modern = False
                try:
                    # Versiyon "2022.x.x" gibi başlıyorsa
                    if unity_ver and unity_ver[0].isdigit():
                        parts = unity_ver.split('.')
                        year = int(parts[0])
                        if year >= 2022: is_modern = True
                except: pass

                if is_modern:
                    if progress_callback: progress_callback("ℹ️ Modern Unity Tespit Edildi (2022+). Bleeding Edge sürümü seçiliyor...")
                    bepinex_zip = files['bepinex_il2cpp_modern'][0] if files['bepinex_il2cpp_modern'] else None
                    if not bepinex_zip:
                         # Fallback to legacy is RISKY but user might not have BE downloaded.
                         # Better to fail and ask for file.
                         pass
                else:
                    if progress_callback: progress_callback("ℹ️ Eski Unity Tespit Edildi. Stabil sürüm seçiliyor...")
                    bepinex_zip = files['bepinex_il2cpp_legacy'][0] if files['bepinex_il2cpp_legacy'] else None
                
                # Hiçbiri yoksa hata ver
                if not bepinex_zip:
                    needed = "Modern (Bleeding Edge)" if is_modern else "Legacy (v6.0-pre.1)"
                    file_hint = "BepInEx-Unity.IL2CPP-win-x64-6.0.0-be*.zip" if is_modern else "BepInEx_UnityIL2CPP_x64_6.0.0-pre.1.zip"
                    error_msg = (
                        f"⚠️ Gerekli BepInEx ({needed}) bulunamadı!\n"
                        f"Oyununuz Unity v{unity_ver} kullanıyor.\n"
                        f"Lütfen şu dosyayı 'files/tools' klasörüne ekleyin:\n{file_hint}"
                    )
                    raise FileNotFoundError(error_msg)
                
                # Check Translator
                if not translator_zip:
                    raise FileNotFoundError("Gerekli 'XUnity.AutoTranslator-BepInEx-IL2CPP' eklentisi bulunamadı!")
            
            else:
                # MONO (Klasik)
                if arch == "x64": 
                    bepinex_zip = files['bepinex_x64'][0] if files['bepinex_x64'] else None
                else: 
                    bepinex_zip = files['bepinex_x86'][0] if files['bepinex_x86'] else None
                
                # Fallback (x64 yoksa x86 dene vs)
                if not bepinex_zip:
                    if arch == "x64" and files['bepinex_x86']:
                        bepinex_zip = files['bepinex_x86'][0]
                    elif arch == "x86" and files['bepinex_x64']:
                        bepinex_zip = files['bepinex_x64'][0]
            
            if not bepinex_zip:
                 raise FileNotFoundError(f"Gerekli BepInEx sürümü ({arch}) bulunamadı! Lütfen ilgili dosyayı ekleyin.")
            
            if not translator_zip:
                raise FileNotFoundError("Gerekli AutoTranslator eklentisi bulunamadı!")

        if progress_callback: progress_callback(f"📦 Kurulum Başlıyor: {game_path} ({arch})")
        
        # [YENİ] Temiz Kurulum (Her zaman temizle - Loader bağımsız)
        if progress_callback: progress_callback("🧹 Eski dosyalar temizleniyor...")
        TranslatorManager.cleanup_game_dir(game_exe_path)
        # --- MELONLOADER INSTALLATION STRATEGY (STRICT MANUAL ZIP) ---
        if loader_type == "melon":
            try:
                # 1. Mimari ve Zip Tespiti
                arch = TranslatorManager.detect_game_architecture(game_exe_path)
                
                melon_zip_path = None
                
                # [FIX] Kullacının seçtiği dosyayı kullan
                if target_bepinex_zip:
                    t_str = str(target_bepinex_zip)
                    # DURUM A: Doğrudan Dosya Yolu
                    if t_str.lower().endswith(".zip"):
                        melon_zip_path = Path(t_str)
                    
                    # DURUM B: Versiyon Seçimi (Örn: "DOWNLOAD:0.6.6")
                    elif t_str.startswith("DOWNLOAD:"):
                        ver = t_str.split(":")[-1] # 0.6.6
                        # Bu versiyona ve mimariye uygun dosyayı ara
                        search_pat = f"MelonLoader*{ver}*{arch}*.zip"
                        cands = list(TranslatorManager.TOOLS_PATH.glob(search_pat))
                        if cands:
                            melon_zip_path = cands[0]
                            logger.debug("Versiyon eşleşmesi bulundu: %s", melon_zip_path.name)
                        else:
                            logger.debug("İstenen versiyon (%s) yerelde bulunamadı, en iyi aday aranacak.", ver)
                
                if not melon_zip_path or not melon_zip_path.exists():
                     # Auto Detect (Fallback)
                     melon_key = 'melon_x64' if arch == "x64" else 'melon_x86'
                     # [SMART SORT] Yeni versiyonları (0.7.x) değil, uyumlu olanı seçmek zor ama 
                     # burada kullanıcı seçmediyse en yeniyi alıyoruz.
                     # Ancak 0.6.6'yı 0.7.1'in önüne geçirmek istiyorsak alfabetik sıralama ters tepiyor olabilir.
                     # Şimdilik varsayılan sıralama (files[key] sorted geliyordu)
                     melon_zip_path = files[melon_key][0] if files[melon_key] else None
                
                if not melon_zip_path:
                     raise FileNotFoundError(f"Gerekli MelonLoader dosyası ({arch}) bulunamadı.\nLütfen 'files/tools' klasörüne 'MelonLoader*{arch}*.zip' formatında bir dosya ekleyin.")

                if progress_callback: progress_callback(f"🍈 MelonLoader Kuruluyor ({melon_zip_path.name})...")

                # 2. MelonLoader ZIP Çıkarma
                if not melon_zip_path.exists():
                    raise FileNotFoundError(f"MelonLoader ZIP dosyası bulunamadı: {melon_zip_path}")
                
                with zipfile.ZipFile(melon_zip_path, 'r') as z:
                    z.extractall(game_path)
                if progress_callback: progress_callback("✅ MelonLoader dosyaları çıkarıldı.")

                # 3. XUnity AutoTranslator Kurulumu
                xunity_zip = None
                
                # Eğer kullanıcı manuel olarak XUnity zip'i seçtiyse
                if target_translator_zip:
                    t_str = str(target_translator_zip)
                    if t_str.lower().endswith(".zip") and os.path.exists(t_str):
                        xunity_zip = Path(t_str)
                
                # Otomatik bulma (Backend'e göre)
                if not xunity_zip:
                    current_dir = Path(__file__).parent
                    
                    if backend == "il2cpp":
                        # IL2CPP versiyonu ara
                        cands = list(TranslatorManager.TOOLS_PATH.glob(TranslatorManager.TRANSLATOR_MELON_IL2CPP_PATTERN))
                        if not cands:
                            # Fallback: mevcut dizinde ara
                            cands = list(current_dir.glob("XUnity*IL2CPP*.zip"))
                        if cands:
                            xunity_zip = cands[0]
                    else:
                        # Mono versiyonu ara
                        cands = list(TranslatorManager.TOOLS_PATH.glob(TranslatorManager.TRANSLATOR_MELON_PATTERN))
                        # IL2CPP olanları filtrele
                        mono_cands = [f for f in cands if "IL2CPP" not in f.name]
                        if not mono_cands:
                            # Fallback: mevcut dizinde ara
                            cands = list(current_dir.glob("XUnity*MelonMod*.zip"))
                            mono_cands = [f for f in cands if "IL2CPP" not in f.name]
                        if mono_cands:
                            xunity_zip = mono_cands[0]

                if xunity_zip and xunity_zip.exists():
                    if progress_callback: progress_callback(f"📦 XUnity AutoTranslator bulundu: {xunity_zip.name}")
                    with zipfile.ZipFile(xunity_zip, 'r') as z:
                        z.extractall(game_path)
                    if progress_callback: progress_callback("✅ XUnity AutoTranslator kuruldu.")
                else:
                    if progress_callback: progress_callback("⚠️ UYARI: Uygun XUnity AutoTranslator zip dosyası bulunamadı!")

                # 4. Mek-Mak Filtresi
                text_dir = game_path / "Translation" / target_lang / "Text"
                text_dir.mkdir(parents=True, exist_ok=True)
                
                subs_file = text_dir / "_Substitutions.txt"
                subs_content = '"mak$"=""\n"mek$"=""\n"mak\\b"=""\n"mek\\b"=""'
                
                with open(subs_file, 'w', encoding='utf-8') as f:
                    f.write(subs_content)
                if progress_callback: progress_callback("✂️ Mek-Mak Filtresi uygulandı.")

                # 5. Config Yazımı (AutoTranslator/Config.ini - MelonLoader formatı)
                at_dir = game_path / "AutoTranslator"
                at_dir.mkdir(parents=True, exist_ok=True)
                config_file = at_dir / "Config.ini"
                
                # Servis ayarı (service parametresine göre)
                endpoint = "GoogleTranslateV2"
                extra_section = ""
                
                if service == "deepl":
                    if api_key and len(api_key.strip()) > 5:
                        endpoint = "DeepLLegitimate"
                        is_free_key = api_key.strip().endswith(":fx")
                        is_free = "True" if is_free_key else "False"
                        extra_section = f"""
[DeepLLegitimate]
ApiKey={api_key.strip()}
Free={is_free}
MinFuzzyMatching=5
MaxFuzzyMatching=50
"""
                    else:
                        endpoint = "DeepLTranslate"
                        extra_section = """
[DeepLTranslate]
MinFuzzyMatching=5
MaxFuzzyMatching=50
MinDelay=1.5
"""
                
                config_content = f"""[Service]
Endpoint={endpoint}
FallbackEndpoint=

[General]
Language={target_lang}
FromLanguage=en

[Behaviour]
MaxTranslationsBeforeShutdown=4000
MaxDestinationsToQueue=5
MaxSecondsInQueue=5
Delay=0
KerbalSpaceProgram=False
ForceUIResizing=True
WhitespaceRemovalStrategy=TrimPerlineInToken
# Türkçe karakterleri destekleyen font (ğ, ü, ş, ı, ö, ç)
OverrideFont=Segoe UI
FallbackFont=Segoe UI
OverrideFontTextMeshPro=
FallbackFontTextMeshPro=Segoe UI SDF

[TextFrameworks]
EnableUGUI=True
EnableTextMeshPro=True
EnableNGUI=True
EnableTextMesh=True
{extra_section}"""
                
                with open(config_file, 'w', encoding='utf-8') as f:
                    f.write(config_content)
                
                if progress_callback: progress_callback(f"✅ Config oluşturuldu: {config_file}")

                return True
                
            except PermissionError:
                raise PermissionError("Erişim Reddedildi! Lütfen yazılımı YÖNETİCİ OLARAK çalıştırın.")
            except Exception as e:
                raise e
        # --- BEPINEX PATH (Existing Logic) ---
        bepinex_zip = target_bepinex_zip
        # ... logic continues below ...
        
        if progress_callback: progress_callback("🧹 BepInEx dosyaları hazırlanıyor...") # Replaced old cleaning logic below
        
        # (Existing BepInEx Logic Follows)
        
        import shutil
        bepinex_dir = game_path / "BepInEx"
        if bepinex_dir.exists():
            try:
                shutil.rmtree(bepinex_dir)
            except Exception as e:
                print(f"Silme hatası: {e}")
        
        # Silinecek dosyalar
        files_to_remove = ["doorstop_config.ini", "winhttp.dll", "version.dll", "changelog.txt"]
        for f in files_to_remove:
            fp = game_path / f
            if fp.exists():
                try:
                    fp.unlink()
                except: pass

        # 3. BepInEx Kurulumu
        with zipfile.ZipFile(bepinex_zip, 'r') as zip_ref:
            zip_ref.extractall(game_path)
        if progress_callback: progress_callback("- BepInEx kuruldu.")
            
        # 4. AutoTranslator Kurulumu
        with zipfile.ZipFile(translator_zip, 'r') as zip_ref:
            zip_ref.extractall(game_path)
        if progress_callback: progress_callback(f"- AutoTranslator ({'IL2CPP' if backend=='il2cpp' else 'Mono'}) kuruldu.")
            
        # [CRITICAL FIX] XUnity zip'i içinde eski bir winhttp.dll veya doorstop_config.ini varsa,
        # az önce kurduğumuz BepInEx 6 BE sürümünü bozmuş olabilir.
        # Bu yüzden kritik dosyaları BepInEx zip'inden TEKRAR çıkartıyoruz.
        if backend == "il2cpp":
            with zipfile.ZipFile(bepinex_zip, 'r') as zip_ref:
                for file_name in ["winhttp.dll", "doorstop_config.ini", "version.dll"]:
                    if file_name in zip_ref.namelist():
                        zip_ref.extract(file_name, game_path)
            if progress_callback: progress_callback("- BepInEx Loader dosyaları doğrulandı (Overwrite Fix).")

        # [FIX] Dual-Proxy Yöntemi (winhttp.dll + version.dll)
        # Bazı oyunlar winhttp.dll'i yüklemez, version.dll zorlaması yapılır.
        winhttp_path = game_path / "winhttp.dll"
        version_path = game_path / "version.dll"
        
        if winhttp_path.exists() and not version_path.exists():
            try:
                import shutil
                shutil.copy2(winhttp_path, version_path)
                if progress_callback: progress_callback("- Proxy DLL çoğaltıldı (winhttp -> version.dll).")
            except Exception as e:
                print(f"DLL Copy Error: {e}")

        # 5. Konfigürasyon ve Özel Ayarlar
        # Profilleri tekrar yükle (Hızlı erişim)
        special_settings = {}
        try:
             comps = TranslatorManager.analyze_game_components(game_path)
             special_settings = comps.get("special_settings", {})
        except: pass
        
        # B) AutoTranslator Config (BepInEx Path)
        config_dir = game_path / "BepInEx" / "config"
        config_dir.mkdir(parents=True, exist_ok=True)
        at_cfg = config_dir / "AutoTranslatorConfig.ini"
        
        # Servis ayarı (MelonLogic formatıyla paralel)
        endpoint = "GoogleTranslateV2"
        extra_section = ""
        
        if service == "deepl":
            if api_key and len(api_key.strip()) > 5:
                endpoint = "DeepLLegitimate"
                is_free = "True" if api_key.strip().endswith(":fx") else "False"
                extra_section = f"\n[DeepLLegitimate]\nApiKey={api_key.strip()}\nFree={is_free}\n"
            else:
                endpoint = "DeepLTranslate"
                extra_section = "\n[DeepLTranslate]\nMinDelay=1.5\n"
        elif service == "gemini":
            endpoint = "GeminiTranslate"
            extra_section = f"\n[GeminiTranslate]\nApiKey={api_key.strip()}\n"

        at_content = f"""[Service]
Endpoint={endpoint}
FallbackEndpoint=

[General]
Language={target_lang}
FromLanguage=en

[Behaviour]
MaxTranslationsBeforeShutdown=4000
MaxDestinationsToQueue=5
MaxSecondsInQueue=5
Delay=0
ForceUIResizing=True
WhitespaceRemovalStrategy=TrimPerlineInToken

[TextFrameworks]
EnableUGUI=True
EnableTextMeshPro=True
EnableNGUI=True
EnableTextMesh=True
{extra_section}
"""
        with open(at_cfg, 'w', encoding='utf-8') as f:
            f.write(at_content)
            
        if progress_callback: progress_callback(f"🌍 Çeviri dili yapılandırıldı: {target_lang}")

        if progress_callback: progress_callback("⚙️ BepInEx ayarları (Console vb.) yapılandırıldı.")

        # Eski Log Temizliği
        try:
            log_file = game_path / "BepInEx" / "LogOutput.log"
            if log_file.exists(): log_file.unlink()
        except: pass
        
        # DEBUG: Plugin klasörünü listele
        try:
             plugin_dir = game_path / "BepInEx" / "plugins"
             if plugin_dir.exists():
                 files = [f.name for f in plugin_dir.rglob("*") if f.is_file()]
                 if progress_callback:
                     progress_callback("Pluginler listelendi.")
                 logger.debug("Pluginler: %s", files)
                 logger.debug("Pluginler: %s", files)
        except: pass
        
        # 7. Regex Substitutions (XML) Oluştur (Merkezi Fonksiyon)
        # Varsayılan olarak Gramer düzeltmesi uygulanır (Mek/Mak -> Emir)
        # Eğer hedef dil Türkçe değilse (örn. ru, pt), Mek-Mak filtresini devre dışı bırak
        fix_gram = (target_lang == "tr")
        TranslatorManager.apply_local_filter(game_path, progress_callback, fix_grammar=fix_gram, fix_chars=False, target_lang=target_lang)
        
        return True

    @staticmethod
    def is_valid_translation_text(text):
        """
        [YENİ] Akıllı Filtre: Bir metnin çevrilmeye değer olup olmadığını kontrol eder.
        Kod, path, anlamsız veri vs. elenir.
        """
        if not text: return False
        text = text.strip()
        
        # 1. Uzunluk Kontrolü
        if len(text) < 2: return False # Tek harf (a, b, 1) çevrilmez
        if len(text) > 2000: return False # Çok uzun veri blokları
        
        # 2. Sadece Sayı/Sembol Kontrolü
        # İçinde hiç harf yoksa geç (1234, ...., ?!?)
        if not any(c.isalpha() for c in text):
            return False
            
        # 3. Dosya Yolu Kontrolü
        # / veya \ içeren ve boşluk içermeyen uzun metinler
        if ("/" in text or "\\" in text) and " " not in text:
            return False
            
        # 4. Kod/Teknik Terim Kontrolü
        # Boşluk yok ama çok uzunsa (muhtemelen camelCase veya snake_case method ismi)
        # Örn: "System.Collections.Generic.List" -> 31 karakter, 0 boşluk
        if " " not in text and len(text) > 25:
            return False
            
        # 5. Sesli Harf Kontrolü (En Belirleyici)
        # Anlamlı bir insan dilinde mutlaka sesli harf olur.
        # Hex kodları, binary dump vs. elemek için.
        # (Türkçe ve İngilizce sesliler)
        vowels = "aeıioöuüAEIİOÖUÜeaio" 
        if not any(c in vowels for c in text):
            # Hiç sesli harf yoksa (örn: "skrrrt", "bcdfgh")
            # Kısaltma olabilir ama genelde çöp veridir.
            # İstisna: "Shh!" gibi. Ama oyun için önemsiz.
            return False
            
        # 6. Değişken/Format Kontrolü
        # {0}, %s gibi ifadelerin yoğunluğu
        # Eğer metin sadece "{0} {1}" gibiyse çevirme
        # Basitçe: Harf sayısı / Toplam uzunluk oranı çok düşükse
        letter_count = sum(1 for c in text if c.isalpha())
        if letter_count / len(text) < 0.3: # %30'dan azı harfse (örn: "{0}: 1234 - %s")
            return False

        # 7. Pipe (|) Filtresi - BLACKLIST (Olası Log/Binary Verisi)
        # " | " (boşluklu pipe) içeren satırlar genelde dump verisidir, çevrilmez.
        if " | " in text or text.count("|") > 1:
            return False

        return True

        return True

    @staticmethod
    def cleanup_game_dir(exe_path):
        """
        Yüklenen tüm mod ve ayar dosyalarını temizler (BepInEx + MelonLoader).
        """
        game_dir = Path(exe_path).parent
        # Temizlenecek klasörler ve dosyalar
        to_delete = [
            "MelonLoader", "Mods", "Plugins", "UserData", "AutoTranslator", "UserLibs",
            "BepInEx", "doorstop_config.ini", "winhttp.dll", "version.dll", "dobby.dll",
            "winmm.dll", "MelonLoader.Support.Il2Cpp.Bootstrap.dll", "NOTICE.txt",
            "changelog.txt"
        ]
        
        deleted_count = 0
        for item in to_delete:
            path = game_dir / item
            if path.exists():
                try:
                    if path.is_dir(): shutil.rmtree(path)
                    else: path.unlink()
                    deleted_count += 1
                except: pass
        return deleted_count

    @staticmethod
    def uninstall(game_exe_path):
        """Oyun klasöründeki modları temizler (GUI için wrapper)"""
        count = TranslatorManager.cleanup_game_dir(game_exe_path)
        if count > 0:
            return True, f"{count} dosya/klasör temizlendi."
        else:
            return True, "Temizlenecek dosya bulunamadı."
        """
        AutoGeneratedTranslations.txt dosyasındaki çevirileri Gemini ile düzeltir.
        Sadece '-mek/-mak' ile bitenleri seçip düzeltmek üzere gönderir.
        Paralel (Worker) desteği ile hızlandırılmıştır.
        """
        import re
        import time
        import requests
        import json
        import os # Added for os.path.exists
        from concurrent.futures import ThreadPoolExecutor, as_completed
        
        # 1. Dosyayı Bul
        target_file = None
        
        if manual_file_path and os.path.exists(manual_file_path):
             target_file = Path(manual_file_path)
             if progress_callback: progress_callback(f"📂 Manuel dosya seçildi: {target_file.name}")
        else:
            search_paths = [
                Path(game_path) / "Translation" / "tr" / "Text" / "_AutoGeneratedTranslations.txt",
                Path(game_path) / "Translation" / "en" / "Text" / "_AutoGeneratedTranslations.txt", 
                Path(game_path) / "Translation" / "_AutoGeneratedTranslations.txt", 
                Path(game_path) / "Translation" / "AutoGeneratedTranslations.txt", 
                Path(game_path) / "BepInEx" / "Translation" / "tr" / "Text" / "_AutoGeneratedTranslations.txt",
                Path(game_path) / "BepInEx" / "Translation" / "en" / "Text" / "_AutoGeneratedTranslations.txt"
            ]
        
            for p in search_paths:
                if p.exists():
                    target_file = p
                    break
        
            if not target_file:
                if progress_callback: progress_callback("⚠️ Standart konumlarda bulunamadı, derinlemesine aranıyor...")
                candidates = ["AutoGeneratedTranslations.txt", "_AutoGeneratedTranslations.txt"]
                for candidate in candidates:
                    try:
                        found_files = list(Path(game_path).rglob(candidate))
                        if found_files:
                            found_files.sort(key=lambda p: len(str(p)))
                            target_file = found_files[0]
                            break
                    except: pass

        if not target_file:
            if progress_callback: progress_callback("❌ Çeviri dosyası bulunamadı!")
            return False

        if progress_callback: progress_callback(f"📂 Dosya bulundu: {target_file.name}")
        
        # 2. Dosyayı Oku
        lines = []
        try:
            with open(target_file, 'r', encoding='utf-8-sig') as f:
                lines = f.readlines()
        except Exception as e:
            if progress_callback: progress_callback(f"❌ Okuma hatası: {e}")
            return False

        # Key=Value analizi
        kv_pattern = re.compile(r'^(.+?)=(.*)$')
        candidates_pattern = re.compile(r'm[ae]k\W*$', re.IGNORECASE)
        
        to_fix_indices = [] # (index, original_value)
        
        for i, line in enumerate(lines):
            line = line.strip()
            if not line or line.startswith("//"): continue
            
            match = kv_pattern.match(line)
            if match:
                val = match.group(2)
                
                # AKILLI FİLTRE (BLACKLIST)
                if not TranslatorManager.is_valid_translation_text(val):
                     continue 
                
                if candidates_pattern.search(val):
                    to_fix_indices.append((i, val))
        
        total_fix_needed = len(to_fix_indices)
        if total_fix_needed == 0:
            if progress_callback: progress_callback("✅ Düzeltilecek satır bulunamadı.")
            return True
            
        if progress_callback: progress_callback(f"🔍 Düzeltilecek: {total_fix_needed} satır.")

        # 3. Paralel (Worker) İşleme
        batch_size = 25 
        max_workers = 8 # 8 İşçi
        
        batches = []
        for i in range(0, total_fix_needed, batch_size):
            batches.append(to_fix_indices[i : i + batch_size])
            
        total_batches = len(batches)
        if progress_callback: progress_callback(f"🚀 TURBO MOD: {total_batches} paket, {max_workers} işçi ile işleniyor...")

        # Worker Fonksiyonu
        def process_batch(batch_data, batch_idx):
            import requests # Thread safe import
            import json
            import time
            from random import uniform
            import re # Regex for parsing AI response
            
            # Rate limit koruması için rastgele bekleme
            time.sleep(uniform(0.1, 0.5))
            
            # Prompt Hazırla
            prompt_text = "Here is a list of game translations with ID and Text. Convert Turkish infinitive verbs (mek/mak) to imperative commands (Gitmek -> Git). DO NOT change nouns like 'Ekmek'. Return ONLY the ID and the Corrected Text in format 'ID: CorrectedText'.\\n\\n"
            
            local_map = {}
            for idx_in_batch, (line_idx, val) in enumerate(batch_data):
                # Fake ID: Batch içi index
                local_map[idx_in_batch] = line_idx
                prompt_text += f"{idx_in_batch}: {val}\\n"
                
            # API Çağrısı
            models_to_try = [
                "gemini-1.5-flash", 
                "gemini-1.5-flash-latest", 
                "gemini-1.5-pro",
                "gemini-pro"
            ]
            
            response = None
            last_error = None
            
            for model_name in models_to_try:
                try:
                    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key}"
                    headers = {'Content-Type': 'application/json'}
                    data = {
                        "contents": [{"parts": [{"text": prompt_text}]}]
                    }
                    
                    resp = requests.post(url, headers=headers, json=data, timeout=30)
                    
                    if resp.status_code == 404 or resp.status_code == 400:
                        # 400 bazen model not found için de dönebiliyor
                        error_detail = ""
                        try: error_detail = resp.json()['error']['message']
                        except: pass
                        last_error = f"{model_name}: {resp.status_code} - {error_detail}"
                        continue 
                    
                    response = resp
                    break 
                except Exception as e:
                    last_error = str(e)
                    continue
            
            if not response:
                 return []
            
            if response.status_code == 200:
                result = response.json()
                try:
                    answer = result.get('candidates', [{}])[0].get('content', {}).get('parts', [{}])[0].get('text', '')
                except: answer = ""
                
                # Cevabı Parse Et
                result_fixes = []
                for ans_line in answer.split('\\n'):
                    ans_line = ans_line.strip()
                    if not ans_line: continue
                    
                    # Regex ile ID ve Text'i ayır (Daha güvenli)
                    match = re.search(r'^\\**(\\d+)\\**\\s*[:.]\\s*(.+)$', ans_line)
                    if match:
                        try:
                            b_id = int(match.group(1))
                            new_text = match.group(2).strip()
                            
                            # Orijinal satır indexi
                            if b_id in local_map:
                                line_idx_real = local_map[b_id]
                                result_fixes.append((line_idx_real, new_text))
                        except ValueError: pass
                
                return result_fixes
                        
            return []

        processed_batches = 0
        correction_count = 0
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_batch = {executor.submit(process_batch, batch, idx): idx for idx, batch in enumerate(batches)}
            
            for future in as_completed(future_to_batch):
                batch_res = future.result()
                processed_batches += 1
                
                if batch_res:
                    for line_idx, corrected_text in batch_res:
                        # Satırı güncelle
                        original_line = lines[line_idx]
                        if '=' in original_line:
                            key_part = original_line.split('=', 1)[0]
                            lines[line_idx] = f"{key_part}={corrected_text}\\n"
                            correction_count += 1
                
                # İlerleme
                if total_batches > 0:
                    percent = int((processed_batches / total_batches) * 100)
                    if progress_callback and (processed_batches % 5 == 0 or processed_batches == total_batches): 
                        progress_callback(f"⚡ İşleniyor (%{percent}) - Düzeltilen: {correction_count}")

        # Sonuç Raporu
        if correction_count == 0:
            if progress_callback: 
                progress_callback("⚠️ AI yanıt verdi ama hiçbir değişiklik yapılmadı.")
                progress_callback("Olası nedenler: AI formatı bozdu veya zaten düzgündü.")
            return False
            
        if progress_callback: progress_callback(f"✅ Toplam {correction_count} satır düzeltildi.")

        # 4. Dosyayı Kaydet
        try:
            with open(target_file, 'w', encoding='utf-8') as f:
                f.writelines(lines)
            if progress_callback: progress_callback("✅ İşlem tamamlandı! Dosya güncellendi.")
            return True
        except Exception as e:
            if progress_callback: progress_callback(f"❌ Kaydetme hatası: {e}")
            return False

    @staticmethod
    def uninstall(exe_path):
        """Çeviri araçlarını kaldırır ve temizler"""
        import shutil
        try:
            game_dir = Path(exe_path).parent
            
            # Silinecek dosyalar/klasörler
            to_delete = [
                game_dir / "winhttp.dll",
                game_dir / "version.dll",
                game_dir / "doorstop_config.ini",
                game_dir / "chainloader.dll",
                game_dir / "BepInEx",
                game_dir / "AutoTranslator"
            ]
            
            deleted_count = 0
            for item in to_delete:
                if item.exists():
                    try:
                        if item.is_dir():
                            shutil.rmtree(item)
                        else:
                            item.unlink()
                        deleted_count += 1
                    except Exception as e:
                        print(f"Silme hatası ({item.name}): {e}")
                        
            return True, f"{deleted_count} öğe temizlendi."
        except Exception as e:
            return False, f"Kaldırma hatası: {e}"

    @staticmethod
    def update_config(game_path, section, key, value):
        """AutoTranslatorConfig.ini içinde ayar değiştirir"""
        config_path = Path(game_path) / "BepInEx" / "config" / "AutoTranslatorConfig.ini"
        if not config_path.exists():
            # Alternatif arama
            candidates = list(Path(game_path).rglob("AutoTranslatorConfig.ini"))
            if candidates: config_path = candidates[0]
            else: return False
            
        try:
            lines = []
            with open(config_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
                
            new_lines = []
            in_section = False
            found = False
            
            for line in lines:
                clean = line.strip()
                if clean.startswith("[") and clean.endswith("]"):
                    in_section = (clean == f"[{section}]")
                    new_lines.append(line)
                    continue
                    
                if in_section and clean.startswith(f"{key}="):
                    new_lines.append(f"{key}={value}\n")
                    found = True
                else:
                    new_lines.append(line)
            
            with open(config_path, 'w', encoding='utf-8') as f:
                f.writelines(new_lines)
            return True
        except:
            return False

    @staticmethod
    def get_config(game_path, section, key):
        """AutoTranslatorConfig.ini'den ayar okur"""
        config_path = Path(game_path) / "BepInEx" / "config" / "AutoTranslatorConfig.ini"
        if not config_path.exists():
            candidates = list(Path(game_path).rglob("AutoTranslatorConfig.ini"))
            if candidates: config_path = candidates[0]
            else: return None
            
        try:
            in_section = False
            with open(config_path, 'r', encoding='utf-8') as f:
                for line in f:
                    clean = line.strip()
                    if clean.startswith("[") and clean.endswith("]"):
                        in_section = (clean == f"[{section}]")
                        continue
                        
                    if in_section and clean.startswith(f"{key}="):
                        return clean.split("=", 1)[1].strip()
            return None
        except:
            return None


    @staticmethod
    def set_font(game_path, font_name="Segoe UI"):
        """
        OverrideFont ayarını günceller (Türkçe karakterleri destekleyen fontlar önerilir)
        Varsayılan: Segoe UI (Türkçe karakterleri mükemmel destekler)
        """
        # UGUI için Düz Font Adı
        TranslatorManager.update_config(game_path, "Behaviour", "OverrideFont", font_name)
        TranslatorManager.update_config(game_path, "Behaviour", "FallbackFont", font_name)
        
        # TMP için SDF Font Adı (TextMeshPro için SDF versiyonu)
        # Bilinen fontlar için SDF versiyonunu ayarla
        tmp_font = font_name
        if font_name == "Arial":
            tmp_font = "Arial SDF"
        elif font_name == "Segoe UI":
            tmp_font = "Segoe UI SDF"  # Türkçe karakterleri destekler
        elif font_name == "Calibri":
            tmp_font = "Calibri SDF"  # Türkçe karakterleri destekler
        elif font_name == "Tahoma":
            tmp_font = "Tahoma SDF"  # Türkçe karakterleri destekler
        # Diğer fontlar için font adı + " SDF" dene
        else:
            tmp_font = f"{font_name} SDF"
             
        TranslatorManager.update_config(game_path, "Behaviour", "FallbackFontTextMeshPro", tmp_font)
        # OverrideTextMeshPro'yu boşalt ki çakışmasın
        TranslatorManager.update_config(game_path, "Behaviour", "OverrideFontTextMeshPro", "")
        return True

    @staticmethod
    def apply_local_filter(game_path, progress_callback=None, manual_file_path=None, fix_grammar=True, fix_chars=False, loader_type="bepinex", target_lang="tr"):
        """
        Unity oyunları için _RegexSubstitutions.xml dosyasını oluşturur/günceller.
        Args:
            loader_type: "melon" ise AutoTranslator klasörüne bakar.
        """
        try:
            # 1. Hedef Klasörü Bul
            targets = []
            
            # [FIX] MelonLoader Priority -> TEST TOOL MATCHING
            # Test Tool "Translation" klasörünü Gamedir root'a atıyor.
            # Biz de öyle yapmalıyız.
            if loader_type == "melon":
                targets.append(Path(game_path) / "Translation")
                # Backup locations
                targets.append(Path(game_path) / "AutoTranslator" / "Translation")
            else:
                # BepInEx Defaults
                targets.append(Path(game_path) / "BepInEx" / "Translation")
                targets.append(Path(game_path) / "BepInEx" / "plugins" / "XUnity.AutoTranslator" / "Translation")
                targets.append(Path(game_path) / "Translation")
            
            target_dir = None
            for t in targets:
                if t.exists():
                    target_dir = t
                    break
            
            if not target_dir:
                if loader_type == "melon":
                     target_dir = Path(game_path) / "Translation"
                else:
                     target_dir = Path(game_path) / "Translation" # Default fall back
                     
                target_dir.mkdir(parents=True, exist_ok=True)

            # [FIX] Kullanıcının ÇALIŞAN dediği "Test Tool" formatını uygulayalım.
            # Test Tool: _Substitutions.txt oluşturuyor ve "mak$"="" formatını kullanıyor.
            
            # _RegexSubstitutions.xml yerine _Substitutions.txt kullanacağız.
            txt_path = target_dir / target_lang / "Text" / "_Substitutions.txt"
            txt_path.parent.mkdir(parents=True, exist_ok=True)
            
            if progress_callback: progress_callback(f"📂 Hedef: {txt_path}")
            
            # İçerik (Test Tool Aynısı)
            subs_content = '"mak$"=""\n"mek$"=""\n"mak\\b"=""\n"mek\\b"=""'
            
            # Eğer fix_grammar False ise boş yazabiliriz ama dosya oluşmalı
            if not fix_grammar:
                subs_content = ""

            with open(txt_path, 'w', encoding='utf-8') as f:
                f.write(subs_content)
                
            if progress_callback: progress_callback("✅ Mek-Mak Filtresi (TXT) uygulandı.")

            # 4. Config Güncelle
            config_path = None
            if loader_type == "melon":
                 # Test tool uses UserData/AutoTranslatorConfig.ini
                 config_path = Path(game_path) / "UserData" / "AutoTranslatorConfig.ini"
                 if not config_path.exists():
                     config_path = Path(game_path) / "AutoTranslator" / "Config.ini"
            else:
                 config_path = Path(game_path) / "BepInEx" / "config" / "AutoTranslatorConfig.ini"
            
            if not config_path or not config_path.exists():
                 candidates = list(Path(game_path).rglob("AutoTranslatorConfig.ini"))
                 if candidates: config_path = candidates[0]
                 # Melon için Config.ini de olabilir
                 if not config_path:
                     candidates = list(Path(game_path).rglob("Config.ini"))
                     if candidates: config_path = candidates[0]
            
            if config_path and config_path.exists():
                lines = []
                with open(config_path, 'r', encoding='utf-8') as f:
                    lines = f.readlines()
                
                new_lines = []
                for line in lines:
                    if line.strip().startswith("SubstitutionFile="):
                        # Config yoluna göre RELATIVE path vermemiz gerekebilir mi?
                        # Genellikle sadece dosya adı yeterli eğer aynı klasördeyse.
                        # Ama Translation/tr/Text altında..
                        # XUnity default: Translation\{Lang}\Text\_Substitutions.txt
                        # Default değer zaten bu olabilir. Biz sadece dosyanın orada olduğundan emin olduk.
                        new_lines.append(line) 
                    else:
                        new_lines.append(line)
                        
                with open(config_path, 'w', encoding='utf-8') as f:
                    f.writelines(new_lines)

            return True
        
        except Exception as e:
            if progress_callback: progress_callback(f"❌ Filter Hatası: {e}")
            return False

    @staticmethod
    def clean_turkish_text(text):
        """Metin içindeki 'mek/mak' eklerini temizler"""
        import re
        # Mek/Mak Filtresi için Kökler (Exceptions)
        # Bu kelimeler 'mek/mak' ile bitse de mastar eki değildir veya köktür, silinmemeli.
        exceptions = {
            "ek", "ye", "par", "cak", "çak", "kay", "da", "ir", "ır", "ya", "kiy", "kıy", "yu", 
            "tok", "basa", "tuta", "sigina", "sığına", "barına", "ha", "oy", "to", "sev", "de", "ye"
        }
        
        words = text.split(" ")
        new_words = []
        for w in words:
            # Temizlik (noktalama işaretlerini ayır)
            match = re.search(r"^(.*?)(m[ae]k)(\W*)$", w, re.IGNORECASE)
            if match:
                prefix = match.group(1) # Kelimenin başı
                suffix = match.group(2) # mek/mak
                punct = match.group(3)  # Noktalama
                
                # Prefix (Kök) istisna listesinde mi?
                # Sadece harfleri alıp bakmak lazım
                root_clean = re.sub(r"[^a-zA-ZğüşıöçĞÜŞİÖÇ]", "", prefix).lower()
                
                if root_clean in exceptions:
                    new_words.append(w) # Olduğu gibi ekle
                elif not prefix.strip(): 
                    # Kelime sadece "mek" veya "mak" ise dokunma (örn. "Make")
                    new_words.append(w)
                else:
                    # Değilse sil (Sadece prefix + punct)
                    new_words.append(f"{prefix}{punct}")
            else:
                new_words.append(w)
        
        return " ".join(new_words)

    @staticmethod
    def clean_translation_file(target_path, fix_grammar=True, fix_chars=True, loader_type="bepinex"):
        """
        AutoGeneratedTranslations.txt dosyasını bulur ve temizler.
        target_path: Oyun klasörü (EXE'nin olduğu yer) veya doğrudan dosya yolu
        fix_grammar: mek/mak düzeltmesi
        fix_chars: Türkçe karakterleri (ğ -> g) düzeltir
        """
        path = Path(target_path)
        
        # [CRITICAL FIX] Eğer EXE yolu verildiyse klasörüne git
        if path.is_file() and path.suffix.lower() == ".exe":
            path = path.parent

        # Eğer klasör verildiyse dosyayı bulmaya çalış
        if path.is_dir():
            # Olası konumlar
            candidates = []
            
            # [FIX] Loader tipine göre öncelik
            # User noted file name is "_AutoGeneratedTranslations.txt" (with underscore)
            if loader_type == "melon":
                candidates.append(path / "Translation" / "tr" / "Text" / "_AutoGeneratedTranslations.txt")
                candidates.append(path / "AutoTranslator" / "Translation" / "tr" / "Text" / "_AutoGeneratedTranslations.txt")
                # Fallback no underscore
                candidates.append(path / "Translation" / "tr" / "Text" / "AutoGeneratedTranslations.txt")
                candidates.append(path / "AutoTranslator" / "Translation" / "tr" / "Text" / "AutoGeneratedTranslations.txt")
            else:
                candidates.append(path / "BepInEx" / "Translation" / "tr" / "Text" / "_AutoGeneratedTranslations.txt")
                candidates.append(path / "BepInEx" / "Translation" / "tr" / "Text" / "AutoGeneratedTranslations.txt")
                
            # Fallback (Diğerleri)
            candidates.append(path / "Translation" / "tr" / "Text" / "_AutoGeneratedTranslations.txt")
            candidates.append(path / "Translation" / "tr" / "Text" / "AutoGeneratedTranslations.txt")

            target_file = None
            
            # 1. Hızlı Arama
            for c in candidates:
                if c.exists():
                    target_file = c
                    break
            
            # 2. Geniş Arama (Fallback)
            if not target_file:
                # Daha kapsamlı arama (Recursive)
                search_roots = [
                    path / "Translation",
                    path / "AutoTranslator",
                    path / "BepInEx",
                    path / "UserData" 
                ]
                patterns = ["_AutoGeneratedTranslations.txt", "AutoGeneratedTranslations.txt"]
                
                for root in search_roots:
                    if not root.exists(): continue
                    
                    for pat in patterns:
                        try:
                            found = list(root.rglob(pat))
                            if found:
                                best = found[0]
                                for f in found:
                                    if "Text" in str(f):
                                        best = f
                                        break
                                target_file = best
                                break
                        except: pass
                    
                    if target_file: break

            if not target_file:
                 return False, "Çeviri dosyası bulunamadı.\n(Arananlar: _AutoGeneratedTranslations.txt veya AutoGeneratedTranslations.txt)\n\nLütfen oyunun açık olduğundan ve çevirinin başladığından emin olun."
                 
            path = target_file
            
        if not path.exists(): return False, f"Dosya yok: {path}"
        
        try:
            # Dosya okuma/yazma hatası olmaması için (Oyun yazarken çakışabilir)
            # Basit retry mekanizması
            content = ""
            import time
            lines = []
            for i in range(3):
                try:
                    with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                        lines = f.readlines()
                    break
                except:
                    time.sleep(0.1)
            else:
                return False, "Dosya okunamadı (Kilitli olabilir)"

            new_lines = []
            changes = 0
            
            for line in lines:
                if "=" in line:
                    parts = line.split("=", 1)
                    original = parts[0]
                    translated = parts[1].strip() # Newline gider
                    
                    cleaned = translated
                    
                    # 1. Mek/Mak Temizle
                    if fix_grammar:
                        cleaned = TranslatorManager.clean_turkish_text(cleaned)
                    
                    # 2. Türkçe Karakter Temizle (İsteğe bağlı)
                    if fix_chars:
                        tr_map = str.maketrans("ğĞşŞıİ", "gGsSiI")
                        cleaned = cleaned.translate(tr_map)
                    
                    # Eğer değişiklik varsa
                    if cleaned != translated:
                        new_lines.append(f"{original}={cleaned}\n")
                        changes += 1
                    else:
                        new_lines.append(line)
                else:
                    new_lines.append(line)
            
            if changes > 0:
                for i in range(3):
                    try:
                        with open(path, 'w', encoding='utf-8') as f:
                            f.writelines(new_lines)
                        break
                    except:
                        time.sleep(0.1)
                
                return True, f"✅ {changes} satır düzeltildi."
            else:
                return True, "✅ Dosya temiz, sorun yok."
                
        except Exception as e:
            return False, str(e)

    @staticmethod
    def reset_game_settings(game_path, progress_callback=None):
        """
        Unity oyununun Kayıt Defteri (Registry) ayarlarını temizler (PlayerPrefs).
        Bu işlem, bozuk grafik ayarlarını (çözünürlük, pencere modu) sıfırlamak için kullanılır.
        """
        import winreg
        import subprocess
        
        game_path = Path(game_path)
        
        # 1. Company Name ve Product Name bul
        # Genellikle Game_Data/app.info dosyasında yazar
        app_info_path = None
        for f in game_path.glob("*_Data/app.info"):
            app_info_path = f
            break
            
        if not app_info_path:
            if progress_callback: progress_callback("❌ app.info dosyası bulunamadı, şirket bilgisi alınamıyor.")
            return False, "app.info bulunamadı"

        try:
            with open(app_info_path, 'r', encoding='utf-8') as f:
                content = f.read().strip()
                lines = content.splitlines()
                # Genellikle format:
                # CompanyName
                # ProductName
                if len(lines) >= 2:
                    company = lines[0].strip()
                    product = lines[1].strip()
                else:
                    if progress_callback: progress_callback("❌ app.info formatı geçersiz.")
                    return False, "app.info geçersiz"
        except Exception as e:
            if progress_callback: progress_callback(f"❌ app.info okuma hatası: {e}")
            return False, f"Okuma hatası: {e}"

        target_key_path = f"Software\\{company}\\{product}"
        if progress_callback: progress_callback(f"🔍 Hedef Registry: HKCU\\{target_key_path}")

        # 2. Registry Anahtarını Sil (reg delete ile)
        try:
            cmd = f'reg delete "HKCU\\{target_key_path}" /f'
            
            # CREATE_NO_WINDOW
            CREATE_NO_WINDOW = 0x08000000
            si = subprocess.STARTUPINFO()
            si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            si.wShowWindow = subprocess.SW_HIDE
            
            result = subprocess.run(cmd, startupinfo=si, capture_output=True, text=True, shell=True, creationflags=CREATE_NO_WINDOW)
            
            if result.returncode == 0:
                if progress_callback: progress_callback("✅ Kayıt defteri ayarları başarıyla silindi.")
                return True, "Silindi"
            else:
                if "ERROR: The system was unable to find the specified registry key" in result.stderr:
                     if progress_callback: progress_callback("ℹ️ Anahtar zaten yok.")
                     return True, "Zaten temiz"
                
                if progress_callback: progress_callback(f"❌ Silme başarısız: {result.stderr}")
                return False, result.stderr

        except Exception as e:
             if progress_callback: progress_callback(f"❌ Registry Hatası: {e}")
             return False, str(e)

    @staticmethod
    def analyze_game_components(game_path):
        """
        Oyunun bileşenlerini detaylı analiz eder (UI, Asset Sistemi vb.).
        Kullanıcı dostu raporlama ve uyumluluk skoru için kullanılır.
        """
        import json
        game_path = Path(game_path)
        game_name = game_path.stem # Exe adı veya klasör adı, hangisi gelirse
        
        components = {
            "ui_systems": [],
            "asset_systems": [],
            "compatibility_score": 100,
            "notes": [],
            "special_settings": {} 
        }
        
        # 0. Profil Kontrolü (Önce buna bak, override edebilir)
        profiles_path = Config.BASE_PATH / "files" / "profiles.json"
        if profiles_path.exists():
            try:
                with open(profiles_path, 'r', encoding='utf-8') as f:
                    profiles = json.load(f)
                    # Basit eşleşme (Tam ad veya içerir)
                    # Gerçek dünyada exe adı ile eşleşme daha güvenli olur
                    # Şimdilik game_name (exe name) dictionary key'inde var mı bakıyoruz.
                    # profiles.get(game_name) direkt eşleşme
                    
                    matched_profile = None
                    # Case insensitive search
                    for k, v in profiles.items():
                        if k.lower() == game_name.lower():
                            matched_profile = v
                            break
                            
                    if matched_profile:
                        components["special_settings"] = matched_profile.get("special_settings", {})
                        if "compatibility_score" in matched_profile:
                             components["compatibility_score"] = matched_profile["compatibility_score"]
                        if "user_message" in matched_profile:
                             components["notes"].append(f"⭐ {matched_profile['user_message']}")
                        components["notes"].append(f"ℹ️ Özel profil bulundu: {matched_profile.get('display_name', game_name)}")
            except Exception as e:
                print(f"Profil okuma hatası: {e}")
        
        # 1. Managed Klasörünü Bul
        # Mono: [Game]_Data/Managed
        # IL2CPP: [Game]_Data/Managed (bazen dummy dosyalar olur) veya GameAssembly.dll
        managed_dir = None
        for f in game_path.glob("*_Data/Managed"):
            if f.is_dir():
                managed_dir = f
                break
        
        if managed_dir:
            # 2. UI Tespiti
            if (managed_dir / "UnityEngine.UI.dll").exists():
                components["ui_systems"].append("UGUI (Standard)")
            
            if (managed_dir / "Unity.TextMeshPro.dll").exists():
                components["ui_systems"].append("TextMeshPro")
                
            if (managed_dir / "UnityEngine.UIElements.dll").exists():
                components["ui_systems"].append("UI Toolkit")
                # Eğer profil override etmediyse puan kır
                if not components["special_settings"]:
                    components["compatibility_score"] -= 30 
                    components["notes"].append("⚠️ UI Toolkit tespit edildi (Çeviri zor olabilir)")

        # 3. Asset Sistemi Tespiti
        streaming_assets = None
        for f in game_path.glob("*_Data/StreamingAssets"):
            streaming_assets = f
            break
            
        if streaming_assets and (streaming_assets / "aa").exists():
            components["asset_systems"].append("Addressables")
            if not components["special_settings"]:
                components["compatibility_score"] -= 10
            components["notes"].append("ℹ️ Addressables sistemi kullanılıyor")
            # Addressables için kritik config ayarı
            components["special_settings"]["ForceScenarioSelection"] = "True"

        # AssetBundles
        has_bundles = False
        for ext in ["*.bundle", "*.unity3d"]:
            if list(game_path.glob(ext)):
                has_bundles = True
                break
        if has_bundles:
            components["asset_systems"].append("AssetBundles")

        if not components["asset_systems"]:
            components["asset_systems"].append("Resources (Standard)")

        # 4. Anti-Cheat Tespiti (Uyumluluk skoru etkisi)
        anticheat_found = TranslatorManager.detect_anticheat(game_path)
        if anticheat_found:
            ac_str = ', '.join(anticheat_found)
            components["compatibility_score"] = max(0, components["compatibility_score"] - 60)
            components["notes"].append(f"🔴 Anti-Cheat Tespit Edildi: {ac_str} — Mod loader çalışmayabilir!")
            components["anticheat"] = anticheat_found
        else:
            components["anticheat"] = []

        # 5. x86 + MelonLoader uyumsuzluk notu
        try:
            for exe in game_path.glob("*.exe"):
                _arch = TranslatorManager.analyze_pe_header(exe)
                if _arch == "x86":
                    components["notes"].append("⚠️ 32-bit (x86) oyun: MelonLoader desteği zayıftır, BepInEx tercih edin.")
                    components["compatibility_score"] = max(0, components["compatibility_score"] - 5)
                break
        except:
            pass

        return components

    @staticmethod
    def download_melonloader(version, arch, progress_callback=None):
        """MelonLoader indirir ve cache'e kaydeder"""
        # URL Logic
        base_url = "https://github.com/LavaGang/MelonLoader/releases/download"
        
        # Mapping
        # v0.7.0 -> v0.6.1+ logic
        url = ""
        
        if version == "LATEST":
            # Direct link assumption:
            url = "https://github.com/LavaGang/MelonLoader/releases/latest/download/MelonLoader.x64.zip"
            if arch == "x86":
                url = "https://github.com/LavaGang/MelonLoader/releases/latest/download/MelonLoader.x86.zip"
            version = "latest" 
        else:
             # v0.7.2, v0.6.1 vb.
             # Github Release formatı çoğunlukla vX.Y.Z
             # Ancak bazen MelonLoader.x64.zip ana dizinde, bazen asset
             # Standart: https://github.com/LavaGang/MelonLoader/releases/download/v0.6.1/MelonLoader.x64.zip
             url = f"{base_url}/v{version}/MelonLoader.{arch}.zip"
            
        target_name = f"MelonLoader_{version}_{arch}.zip"
        target_path = TranslatorManager.TOOLS_PATH / target_name
        
        if target_path.exists():
            if progress_callback: progress_callback("Dosya önbellekten kullanılıyor.")
            return str(target_path)
            
        try:
            if progress_callback: progress_callback(f"İndiriliyor: {url}")
            
            # Github redirection handle + SSL
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            
            with urllib.request.urlopen(url, context=ctx) as u, open(target_path, 'wb') as f:
                f.write(u.read())
                
            return str(target_path)
        except Exception as e:
            if progress_callback: progress_callback(f"İndirme hatası: {e}")
            print(f"Download Error: {e}")
            return None
