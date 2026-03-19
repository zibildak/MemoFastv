from PyQt5.QtCore import QThread, pyqtSignal
from scanner import GameEngineScanner

class ScanWorker(QThread):
    """
    Arka planda oyun taraması yapan iş parçacığı.
    UI donmasını engellemek için kullanılır.
    """
    finished = pyqtSignal(list)
    progress = pyqtSignal(str)
    
    def __init__(self):
        super().__init__()
        
    def run(self):
        try:
            if self.progress: self.progress.emit("Tarayıcı başlatılıyor...")
            
            scanner = GameEngineScanner()
            # Callback ile progress ilet
            results = scanner.scan(callback=self.handle_callback)
            
            if self.progress: self.progress.emit("Tamamlandı.")
            self.finished.emit(results)
            
        except Exception as e:
            print(f"ScanWorker Error: {e}")
            self.finished.emit([])

    def handle_callback(self, msg):
        if self.progress:
            self.progress.emit(msg)
