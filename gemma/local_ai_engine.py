import os
import sys
from pathlib import Path
try:
    from llama_cpp import Llama
    LLAMA_AVAILABLE = True
except ImportError:
    Llama = None
    LLAMA_AVAILABLE = False
    print("⚠️ 'llama-cpp-python' kütüphanesi bulunamadı! Yerel AI çalışmayacak.")

class LocalAIEngine:
    _shared_model = None
    _shared_model_path = None

    def __init__(self, model_filename=None):
        self.base_path = Path(__file__).parent
        self.models_dir = self.base_path / "models"
        
        if not model_filename:
            # Llama-3.1'e öncelik ver, yoksa diğerlerine bak
            llama_models = list(self.models_dir.glob("*Llama-3.1*"))
            if llama_models:
                self.model_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "models", os.path.basename(llama_models[0]))
            else:
                gguf_files = list(self.models_dir.glob("*.gguf"))
                self.model_path = str(gguf_files[0]) if gguf_files else None
        else:
            self.model_path = str(self.models_dir / model_filename)

    def load_model(self):
        if not LLAMA_AVAILABLE:
            return False, "llama-cpp-python kütüphanesi eksik. Lütfen 'pip install llama-cpp-python' komutunu çalıştırın."

        if not self.model_path or not os.path.exists(self.model_path):
            return False, f"Model dosyası bulunamadı: {self.model_path}"
        
        # Eğer model zaten yüklüyse ve aynı yoldaysa, tekrar yükleme
        if LocalAIEngine._shared_model is not None and LocalAIEngine._shared_model_path == self.model_path:
            return True, "Model zaten yüklü."

        try:
            import os
            # Fiziksel çekirdek sayısını tahmin et (yarısı genelde daha iyidir veya hepsi)
            cpus = os.cpu_count() or 4
            threads = max(4, min(cpus, 8))
            
            print(f"🔄 Model RAM'e aktarılıyor: {os.path.basename(self.model_path)} (Threads: {threads})...")
            LocalAIEngine._shared_model = Llama(
                model_path=str(self.model_path),
                n_ctx=2048,           
                n_threads=threads,          
                n_batch=256, 
                n_gpu_layers=0,       
                use_mmap=True,
                use_mlock=False,
                verbose=False         
            )
            LocalAIEngine._shared_model_path = self.model_path
            return True, "Model başarıyla yüklendi."
        except Exception as e:
            return False, f"Model yükleme hatası: {str(e)}"

    def translate(self, text, source_lang="English", target_lang="Turkish"):
        if not LocalAIEngine._shared_model: return "Hata: Model yüklenmedi!"

        # Hedef dili Türkçeleştir (Opsiyonel ama prompt için daha iyi olur)
        target_lang_str = target_lang
        if target_lang.lower() == "tr": target_lang_str = "Turkish"
        elif target_lang.lower() == "ru": target_lang_str = "Russian"
        elif target_lang.lower() == "de": target_lang_str = "German"
        elif target_lang.lower() == "fr": target_lang_str = "French"
        elif target_lang.lower() == "es": target_lang_str = "Spanish"
        elif target_lang.lower() == "it": target_lang_str = "Italian"
        elif target_lang.lower() == "pt": target_lang_str = "Portuguese"
        elif target_lang.lower() == "pl": target_lang_str = "Polish"

        # Llama-3.1 için Resmi Chat Formatı
        prompt = (
            f"<|begin_of_text|><|start_header_id|>system<|end_header_id|>\n\n"
            f"You are a professional game translator. Translate the user's text to {target_lang_str} using short, natural game terminology. "
            f"IMPORTANT: For buttons, menus, and actions, use IMPERATIVE forms (e.g., 'Exit' -> 'Çıkış Yap', 'Start' -> 'Başlat'). "
            f"Avoid infinitive forms ending in '-mak/-mek' unless it's a noun. Output ONLY the translation."
            f"<|eot_id|><|start_header_id|>user<|end_header_id|>\n\n"
            f"Translate: {text}<|eot_id|><|start_header_id|>assistant<|end_header_id|>\n\n"
        )
        
        try:
            # print(f"DEBUG Prompt: {prompt}") # Gerektiğinde açılabilir
            response = LocalAIEngine._shared_model(
                prompt,
                max_tokens=128,
                stop=["<|eot_id|>", "\n"],
                echo=False,
                temperature=0.0
            )
            translation = response['choices'][0]['text'].strip()
            # print(f"🤖 AI Çıktısı: {translation}")
            return translation
        except Exception as e:
            print(f"❌ AI Translation Error: {e}")
            return f"Çeviri hatası: {str(e)}"

if __name__ == "__main__":
    engine = LocalAIEngine()
    success, msg = engine.load_model()
    if success:
        test_text = "Quit to Main Menu"
        print(f"\n📝 Test Metni: {test_text}")
        result = engine.translate(test_text)
        print(f"🤖 Llama-3.1 Çevirisi: {result}")
