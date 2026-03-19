import sys
import os
import struct
import psutil
from logger import setup_logger
from exceptions import ProcessError, ProcessNotFound, MemoryScanError, MemoryWriteError
from config import Constants

# Logger ayarı
logger = setup_logger(__name__)

# Add local libs path
current_dir = os.path.dirname(os.path.abspath(__file__))
libs_path = os.path.join(current_dir, "files", "libs")
if libs_path not in sys.path:
    sys.path.append(libs_path)

try:
    from pymem import Pymem
    from pymem import process
    from pymem import pattern
    from pymem.exception import ProcessNotFound, ProcessError
    PYMEM_AVAILABLE = True
except ImportError:
    PYMEM_AVAILABLE = False
    logger.warning("Pymem kütüphanesi bulunamadı! 'files/libs' klasörünü kontrol edin.")

class MemoryTrainer:
    """
    Pymem kütüphanesi kullanarak bellek taraması ve manipülasyonu yapan sınıf.
    
    Özellikleri:
    - Process'e bağlanıp ayrılma
    - Bellek taraması (değer arama)
    - Bellek filtreleme (Next Scan)
    - Bellek yazması (değer değiştirme)
    - AES Key taraması
    """
    
    def __init__(self):
        """MemoryTrainer'ı başlat"""
        self.pm = None
        self.process_name = ""
        self.found_addresses = []
        
    def attach(self, process_name):
        """İsmi verilen process'e bağlan"""
        if not PYMEM_AVAILABLE:
            raise ProcessError("Pymem kütüphanesi yüklü değil!")

        self.process_name = process_name
        try:
            self.pm = Pymem(process_name)
            logger.info(f"[✓] {process_name} (PID: {self.pm.process_id}) sürecine bağlandı (Pymem)")
            return True
        except ProcessNotFound:
            raise ProcessNotFound(f"{process_name} işlemi bulunamadı!")
        except Exception as e:
            raise ProcessError(f"Process'e bağlanılamadı: {e}")

    def detach(self):
        """Process bağlantısını kes ve verileri temizle"""
        if self.pm:
            # Pymem otomatik handle kapatır ama biz referansı boşaltalım
            self.pm = None
            self.found_addresses = []

    def list_processes(self):
        """
        Sistemde çalışan process'leri listele.
        
        Returns:
            list: {'pid': int, 'name': str} dictlerinin listesi (ad'a göre sıralanmış)
        """
        procs = []
        excluded = ["svchost.exe", "System", "Registry", "smss.exe", "csrss.exe", 
                   "wininit.exe", "services.exe", "lsass.exe", "winlogon.exe", 
                   "fontdrvhost.exe", "Memory Compression"]
        
        for proc in psutil.process_iter(['pid', 'name', 'username']):
            try:
                p_name = proc.info['name']
                if p_name and p_name not in excluded:
                    if p_name.lower().endswith(".exe"):
                        procs.append({'pid': proc.info['pid'], 'name': p_name})
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                pass
                
        procs.sort(key=lambda x: x['name'].lower())
        return procs

    def scan_memory(self, value, data_type="int"):
        """
        Belleğe aranacak değeri tara (Cheat Engine Exact Value benzeri).
        
        Args:
            value: Aranacak değer (int olarak dönüştürülür)
            data_type: Veri tipi (şu an sadece 'int' destekleniyor)
            
        Returns:
            int: Bulunan adres sayısı
            
        Raises:
            Exception: Process bağlı değilse veya Pymem yüklü değilse
            
        Note:
            Sonuçlar self.found_addresses listesinde saklanır
        """
        if not self.pm:
            raise ProcessError("Önce bir sürece bağlanmalısınız!")
        
        # Bellek sınırlaması kontrolü
        try:
            process = psutil.Process(self.pm.process_id)
            process_memory_mb = process.memory_info().rss / (1024 * 1024)
            system_memory_percent = psutil.virtual_memory().percent
            
            if process_memory_mb > Constants.MEMORY_SCAN_MAX_PROCESS_MB:
                raise MemoryScanError(
                    f"Process bellek kullanımı çok yüksek ({process_memory_mb:.0f}MB > {Constants.MEMORY_SCAN_MAX_PROCESS_MB}MB). "
                    "Tarama dahil edilemez."
                )
            
            if system_memory_percent > Constants.MEMORY_SCAN_MAX_SYSTEM_PERCENT:
                raise MemoryScanError(
                    f"Sistem belleği (%{system_memory_percent:.1f}) sınırını aştı (%{Constants.MEMORY_SCAN_MAX_SYSTEM_PERCENT}). "
                    "Tarama iptal edildi."
                )
                
            logger.debug(f"Memory Check: Process {process_memory_mb:.0f}MB, System %{system_memory_percent:.1f}")
        except MemoryScanError:
            raise
        except Exception as e:
            logger.warning(f"Memory limit check warning: {e}")
            
        target_val = int(value)
        self.found_addresses = []
        
        logger.info(f"[*] Değer aranıyor (Pymem): {value}")
        
        # Pattern oluştur (Little Endian integer)
        # Örn: 1234 -> \xd2\x04\x00\x00
        byte_pattern = struct.pack('<i', target_val)
        
        # Pymem pattern scan string kabul eder (regex style), ama biz raw bytes aramak istiyoruz.
        # Pymem'in 'pattern_scan_all' metodu genellikle module module tarar veya pattern string bekler.
        # Biz manuel scan yaparsak daha iyi olabilir ama Pymem'in gücünü kullanalım.
        
        # Pymem pattern scan regex formatı: rb'\x00\x00...'
        # Pymem.pattern.pattern_scan_all(handle, pattern, return_multiple=True)
        
        try:
            # Tüm memory region'larını tara
            # Bu işlem biraz uzun sürebilir, basit bir pattern scan yapıyoruz.
            
            # NOT: Pymem pattern_scan_all modül bazlı çalışır (tüm modüller).
            # Eğer tüm heap/stack taranacaksa custom loop gerekir.
            # Şimdilik "pattern_scan_all" (tüm modüller) deneyelim.
            # Eğer yetersiz kalırsa bellek haritası (memory map) üzerinden gideceğiz.
            
            # Pattern'i regex string'e çevir (Pymem style)
            # Ama Pymem pattern string'i genelde string olarak bekler.
            # Ancak biz 'scan_pattern_page' gibi metodlar kullanabiliriz.
            
            # --- CUSTOM SCAN LOGIC WITH PYMEM ---
            # Pymem doğrudan "scan all memory for int" fonksiyonuna sahip değil (wrapperlarda var).
            # Biz Memory Regions üzerinden gidelim, Pymem handle'ını kullanarak.
            
            # System info
            # Pymem process objesi handle'ı verir: self.pm.process_handle
            
            # Hızlı çözüm: Pymem 'pattern_scan_all' fonksiyonunu kullanalım. 
            # Bu fonksiyon varsayılan olarak yüklenen modülleri (EXE ve DLL) tarar.
            # Oyun verileri genelde dinamik bellekte (Heap) olur, modül sectionlarında olmayabilir.
            # Bu yüzden manuel region taraması daha garantidir.
            
            self.found_addresses = []
            
            # Pymem ile region taraması
            # VirtualQueryEx wrapper'ı yok ama ctypes ile çağırabiliriz veya pymem.memory kullanabiliriz.
            # Ancak elimizde zaten çalışan ctypes kodu vardı, onu Pymem handle ile birleştirelim mi?
            # VEYA basitçe Pymem'in "read_int" metodunu kullanarak scan yapalım.
            
            # Python döngüsü hızı düşük olabilir.
            # Byte pattern ile eşleşen yerleri bulmak için tüm belleği okumak lazım.
            
            # HIZLI YOL: Tüm okunabilir regionları bul ve `bytes.find` yap.
            # Pymem bunu kolaylaştırır.
            
            import ctypes
            from pymem import memory
            
            # Process handle
            handle = self.pm.process_handle
            
            # Min/Max Address
            # (Basitçe 0'dan 0x7FFFFFFFFFFF'e kadar region region oku)
            
            next_region = 0
            max_addr = 0x7FFFFFFFFFFF
            
            regions_scanned = 0
            
            # Bellek okuma tamponu boyutu optimize edilebilir
            
            while next_region < max_addr:
                try:
                    mbi = memory.virtual_query(handle, next_region)
                except:
                    break
                    
                if not mbi: break
                
                # Sadece COMMIT ve READWRITE/READONLY alanları
                # PAGE_GUARD korumasını atla
                is_read = (mbi.Protect & 0x100) == 0 and \
                          (mbi.Protect & (0x02 | 0x04 | 0x20 | 0x40)) # ReadOnly, ReadWrite, ExecRead, ExecReadWrite
                
                if mbi.State == 0x1000 and is_read: # MEM_COMMIT
                    # Oku
                    try:
                        page_bytes = self.pm.read_bytes(mbi.BaseAddress, mbi.RegionSize)
                        if page_bytes:
                            # Python'un hızlı find metodu
                            offset = 0
                            while True:
                                idx = page_bytes.find(byte_pattern, offset)
                                if idx == -1: break
                                
                                addr = mbi.BaseAddress + idx
                                self.found_addresses.append(addr)
                                offset = idx + 1
                                
                                # Sonuç sayısı limitini kontrol et
                                if len(self.found_addresses) >= Constants.MEMORY_SCAN_MAX_RESULTS:
                                    logger.warning(
                                        f"[!] Tarama limiti ({Constants.MEMORY_SCAN_MAX_RESULTS}) aşıldı. "
                                        f"Sonuçlar kısıtlanmıştır."
                                    )
                                    return len(self.found_addresses)
                    except:
                        pass
                
                next_region = mbi.BaseAddress + mbi.RegionSize
                regions_scanned += 1
                
                if regions_scanned > 10000: break # Sonsuz döngü koruması

        except Exception as e:
            logger.error(f"Scan Error: {e}")
            raise MemoryScanError(f"Bellek taraması başarısız: {e}")
            
        logger.info(f"[✓] Tarama tamamlandı (Pymem Engine)! Bulunan: {len(self.found_addresses)}")
        return len(self.found_addresses)

    def filter_memory(self, value, data_type="int"):
        """
        Sonraki tarama (Next Scan) - önceki sonuçları filtrele.
        
        Args:
            value: Yeni aranacak değer
            data_type: Veri tipi (şu an sadece 'int' destekleniyor)
            
        Returns:
            int: Filtrelemeden sonra kalan adres sayısı
            
        Note:
            self.found_addresses listesi güncellenir
        """
        if not self.found_addresses:
            logger.warning("[!] Filtrelenecek adres yok!")
            return 0
            
        target_val = int(value)
        new_list = []
        
        # Pymem ile tek tek oku ve kontrol et
        logger.info(f"[*] {len(self.found_addresses)} adres filtreleniyor...")
        
        for addr in self.found_addresses:
            try:
                # int oku
                val = self.pm.read_int(addr)
                if val == target_val:
                    new_list.append(addr)
            except:
                pass # Okuma hatası olursa (memory free olduysa) atla
                
        self.found_addresses = new_list
        logger.info(f"[✓] Filtreleme tamamlandı: {len(self.found_addresses)} adres kaldı")
        return len(self.found_addresses)

    def write_memory(self, value, data_type="int"):
        """
        Bulunan adresler'e değer yaz (Bellek değiştirme).
        
        Args:
            value: Yazılacak değer (int olarak dönüştürülür)
            data_type: Veri tipi (şu an sadece 'int' destekleniyor)
            
        Returns:
            int: Başarıyla yazılan adres sayısı
            
        Note:
            Yazma hatası olan adresler sessizce atlanır (memory freed olmuş olabilir)
        """
        if not self.found_addresses:
            return 0
            
        target_val = int(value)
        count = 0
        
        for addr in self.found_addresses:
            try:
                self.pm.write_int(addr, target_val)
                count += 1
            except:
                pass
                
        logger.info(f"[✓] {count} adrese yazıldı")
        return count
    
    def get_value_at_address(self, address):
        """
        Belirli bir adresten tek bir int değeri oku.
        
        Args:
            address: Okunacak bellek adresi (hex string veya int)
            
        Returns:
            int: Adresteki değer, veya None hata olursa
        """
        if not self.pm: return None
        try:
            return self.pm.read_int(address)
        except:
            return None
    
    def scan_for_aes_keys(self, process_name=None):
        """
        Process belleğinde AES anahtarlarını ara.
        
        Arar:
        - 64 hex karakterlik değerler (256-bit AES key)
        - 0x ön eki olan veya olmayan anahtarlar
        
        Args:
            process_name: Taranacak process adı (None ise mevcut bağlı process)
            
        Returns:
            list: Bulunan AES anahtar adaylarının listesi
            
        Raises:
            Exception: Process'e bağlı değilse
            
        Note:
            Fake key'ler filtrelenir (0x0000... gibi)
        """
        """
        AES Key Taraması (RAM Hunter)
        Bellekte '0x' ile başlayan 64 karakterlik hex string desenlerini arar.
        """
        if process_name:
            self.attach(process_name)
            
        if not self.pm:
            raise ProcessError("Process'e bağlı değil!")
            
        logger.info(f"[*] {self.process_name} üzerinde AES Key Taraması başlatılıyor...")
        
        found_keys = set()
        
        # Hızlı tarama için bellek haritasını kullan
        import ctypes
        from pymem import memory
        import re
        
        handle = self.pm.process_handle
        next_region = 0
        max_addr = 0x7FFFFFFFFFFF
        buffer_size = 1024 * 1024 * 10 # 10MB Chunks
        
        # Regex güncellendi: 0x ön eki OLMADAN da 64 hex karakteri yakala
        # Ancak 0x ile başlayanları önceliklendir.
        # İki pattern kullanalım.
        aes_pattern_with_prefix = re.compile(rb'0x[A-Fa-f0-9]{64}')
        aes_pattern_raw = re.compile(rb'(?<![A-Fa-f0-9])[A-Fa-f0-9]{64}(?![A-Fa-f0-9])') # Tam 64 char
        
        try:
            while next_region < max_addr:
                try:
                    mbi = memory.virtual_query(handle, next_region)
                except:
                    break
                    
                if not mbi: break
                
                # Sadece Okunabilir ve Commit edilmiş alanlar
                is_read = (mbi.Protect & 0x02) or (mbi.Protect & 0x04) or (mbi.Protect & 0x20) or (mbi.Protect & 0x40)
                if mbi.State == 0x1000 and is_read:
                    # Büyük regionları parça parça oku
                    current_addr = mbi.BaseAddress
                    end_addr = current_addr + mbi.RegionSize
                    
                    while current_addr < end_addr:
                        chunk_size = min(buffer_size, end_addr - current_addr)
                        try:
                            # Belleği oku
                            chunk_data = self.pm.read_bytes(current_addr, chunk_size)
                            if chunk_data:
                                # 1. Önce 0x'li ara (Daha güvenilir)
                                for match in aes_pattern_with_prefix.finditer(chunk_data):
                                    key_str = match.group(0).decode('utf-8', errors='ignore')
                                    if self.is_valid_key(key_str):
                                        found_keys.add(key_str)
                                
                                # 2. Sonra ham 64 char ara
                                for match in aes_pattern_raw.finditer(chunk_data):
                                    raw_key = match.group(0).decode('utf-8', errors='ignore')
                                    # 0x ekleyerek kaydet
                                    key_str = f"0x{raw_key}"
                                    if self.is_valid_key(key_str):
                                        found_keys.add(key_str)
                                        
                                if len(found_keys) >= 50: break
                        except:
                            pass
                            
                        current_addr += chunk_size
                        if len(found_keys) >= 50: break
                        
                next_region = mbi.BaseAddress + mbi.RegionSize

        except Exception as e:
            logger.error(f"AES Scan Error: {e}")
            raise MemoryScanError(f"AES Key taraması başarısız: {e}")
            
        results = list(found_keys)
        logger.info(f"[✓] Tarama Bitti. Bulunan Adaylar: {len(results)}")
        return results

    def is_valid_key(self, key_str):
        """
        AES key'in geçerliliğini kontrol et.
        
        Filtreler:
        - Sahte key'ler (0x00010203 gibi art arda artan baytlar)
        - Tekrarlayan karakterler (0x0000... veya 0xFFFF...)
        
        Args:
            key_str: Kontrol edilecek hex string
            
        Returns:
            bool: True ise geçerli, False ise sahte key
        """
        # SAHTE KEY FİLTRESİ
        if "00010203" in key_str or "01020304" in key_str: return False
        
        # Çok fazla tekrar (0x0000... veya 0xFFFF...)
        payload = key_str[2:] # 0x hariç
        if len(set(payload)) < 5: return False
        
        # Sadece harf veya sadece rakam olanları şüpheli bulabiliriz ama şimdilik kalsın.
        return True


if __name__ == "__main__":
    # Test
    trainer = MemoryTrainer()
    # Wukong test (eğer çalışıyorsa)
    # trainer.scan_for_aes_keys("b1-Win64-Shipping.exe")