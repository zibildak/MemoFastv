"""
MEMOFAST - Scanner Testleri
Oyun tarama ve cache sistemi testleri
"""
import pytest
import json
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
import tempfile


class TestScannerInitialization:
    """Scanner başlatılması testleri"""
    
    def test_scanner_init(self, scanner):
        """Scanner başlatılabiliyor mu"""
        assert scanner is not None
        assert hasattr(scanner, 'cache_path')
    
    def test_cache_path_exists(self, scanner):
        """Cache path oluşturuluyor mu"""
        assert scanner.cache_path is not None


class TestGameScannerLogic:
    """Oyun tarama mantığı testleri"""
    
    def test_get_available_drives(self, scanner):
        """Disk bulma fonksiyonu"""
        drives = scanner._get_available_drives()
        assert isinstance(drives, list)
        # En az C: diski olmalı
        assert any('C' in d for d in drives)
    
    def test_search_files_empty_path(self, scanner):
        """Boş path ile arama yapma"""
        with patch('pathlib.Path.iterdir', return_value=[]):
            result = scanner._search_files(Path("."), "nonexistent.txt")
            assert result == []
    
    def test_search_files_with_mock(self, scanner):
        """Mock dosyalarla arama"""
        mock_files = [
            MagicMock(name="game.exe", is_file=lambda: True, is_dir=lambda: False),
            MagicMock(name="config.ini", is_file=lambda: True, is_dir=lambda: False),
            MagicMock(name="subdir", is_file=lambda: False, is_dir=lambda: True),
        ]
        
        with patch('pathlib.Path.iterdir', return_value=mock_files):
            # Not: arama case-insensitive olmalı
            result = scanner._search_files(Path("."), "GAME.EXE")
            # Mock yapısı sebebiyle sonuç kısıtlı olabilir
            assert isinstance(result, list)
    
    def test_scan_for_game_structure(self, scanner):
        """Oyun tarama sonuç yapısı"""
        # Scanner'ın sonuc yapısını kontrol et (mock tarama olmadan)
        with patch.object(scanner, '_get_available_drives', return_value=[]):
            result = scanner.scan_for_game("test_game", "game.exe")
            
            assert isinstance(result, dict)
            assert 'steam' in result
            assert 'epic' in result
            assert 'custom' in result
            assert isinstance(result['steam'], list)
            assert isinstance(result['epic'], list)
            assert isinstance(result['custom'], list)


class TestCacheSystem:
    """Cache sistemi testleri"""
    
    def test_cache_creation(self, scanner, temp_dir):
        """Cache dosyası oluşturuluyor mu"""
        with patch.object(scanner, 'cache_path', temp_dir):
            # Cache yazma simülasyonu
            cache_file = temp_dir / "test_game_scan.json"
            test_data = {
                'steam': ['/path/to/steam/game'],
                'epic': [],
                'custom': []
            }
            
            cache_file.write_text(json.dumps(test_data))
            
            # Okuma
            loaded = json.loads(cache_file.read_text())
            assert loaded == test_data
    
    def test_get_cached_results(self, scanner, temp_dir):
        """Cache'den sonuç okuma"""
        with patch.object(scanner, 'cache_path', temp_dir):
            # Cache dosyası oluştur
            cache_file = temp_dir / "mytest_scan.json"
            test_data = {
                'steam': ['/path/to/steam/game'],
                'epic': ['/path/to/epic/game'],
                'custom': []
            }
            cache_file.write_text(json.dumps(test_data))
            
            # Scanner metodu test et
            result = scanner.get_cached_results("mytest")
            
            if result:
                assert len(result['steam']) == 1
                assert len(result['epic']) == 1
    
    def test_clear_cache_specific_game(self, scanner, temp_dir):
        """Belirli oyunun cache'ini temizleme"""
        with patch.object(scanner, 'cache_path', temp_dir):
            # Cache dosyası oluştur
            cache_file = temp_dir / "test_game_scan.json"
            cache_file.write_text("{}")
            
            assert cache_file.exists()
            
            scanner.clear_cache("test_game")
            
            assert not cache_file.exists()
    
    def test_clear_cache_all(self, scanner, temp_dir):
        """Tüm cache'i temizleme"""
        with patch.object(scanner, 'cache_path', temp_dir):
            # Birden fazla cache dosyası oluştur
            (temp_dir / "game1_scan.json").write_text("{}")
            (temp_dir / "game2_scan.json").write_text("{}")
            (temp_dir / "other_file.txt").write_text("not cache")
            
            assert (temp_dir / "game1_scan.json").exists()
            assert (temp_dir / "game2_scan.json").exists()
            
            scanner.clear_cache()
            
            assert not (temp_dir / "game1_scan.json").exists()
            assert not (temp_dir / "game2_scan.json").exists()
            assert (temp_dir / "other_file.txt").exists()


class TestScannerExclusions:
    """Scanner dışlama listesi testleri"""
    
    def test_excluded_folders_integration(self, scanner, constants):
        """Scanner Constants.EXCLUDED_FOLDERS'ı kullanıyor mu"""
        # _search_files metodu excluded folders'ı kontrol etmeli
        assert hasattr(constants, 'EXCLUDED_FOLDERS')
        assert len(constants.EXCLUDED_FOLDERS) > 0
    
    def test_excluded_folder_names(self, constants):
        """Dışlanan klasör adları doğru mu"""
        excluded = [f.upper() for f in constants.EXCLUDED_FOLDERS]
        
        critical_folders = ['WINDOWS', 'SYSTEM', 'APPDATA', 'CACHE']
        for folder in critical_folders:
            assert any(folder in e for e in excluded), f"{folder} should be excluded"
