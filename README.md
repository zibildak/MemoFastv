<p align="center">
  <img src="assets/app_icon.png" width="120" alt="MemoFast Logo">
</p>

<h1 align="center">🎮 MemoFast - Game Translation & Optimization Tool</h1>

<p align="center">
  <b>Translate your games to Turkish, optimize, and patch them!</b>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/version-1.1.2-blue?style=for-the-badge" alt="Version">
  <img src="https://img.shields.io/badge/python-3.8+-green?style=for-the-badge&logo=python" alt="Python">
  <img src="https://img.shields.io/badge/platform-Windows-0078D6?style=for-the-badge&logo=windows" alt="Platform">
  <img src="https://img.shields.io/badge/license-MIT-orange?style=for-the-badge" alt="License">
</p>

---

## 🚀 Features

### 🔄 Multi-Engine Support
- **Unreal Engine** → Open, translate, and repackage PAK files (automatic AES key detection)
- **Unity Engine** → Asset bundle translation, font fixing
- **Cobra Engine** → OVL translation for Planet Zoo, Jurassic World, etc.

### 🌍 Translation Engines
- **Google Translate** → Free, fast
- **DeepL** → High-quality translation
- **Gemini AI** → Context-aware intelligent translation

### 🖥️ Screen Translation (OCR)
- In-game text recognition and instant translation
- Support for Windows OCR, Tesseract, and EasyOCR
- Text-to-speech (TTS) feature
- Quick access with hotkeys

### 🎯 Additional Tools
- **Game Scanner** → Auto-detect games from Steam, Epic Games, GOG, and Xbox
- **Backup Center** → Backup/restore original files
- **Auto Updates** → Automatic application update checks
- **Game Optimization** → Performance improvement tools

---

## 📦 Download & Installation

### 🎯 Pre-built Release (Recommended)

If you don't know Python, you can download and use it directly:

<p align="center">
  <a href="https://github.com/zibildak/memofast/releases/download/memofast1.1.2/MemoFast.1.1.2.zip">
    <img src="https://img.shields.io/badge/⬇️_Download-MemoFast_v1.1.2-00cc66?style=for-the-badge&logo=windows" alt="Download">
  </a>
</p>

1. Download the ZIP file
2. Extract it to a folder
3. Run `MemoFast.exe` — that's it!

---

### 🛠️ Running from Source Code (For Developers)

```bash
# 1. Clone the repository
git clone https://github.com/zibildak/MemoFastv.git
cd MemoFastv

# 2. Install dependencies
pip install -r requirements.txt

# 3. Run the application
python memofast_gui.py
```

**Requirements:** Windows 10/11, Python 3.8+

---

## 🖼️ Screenshots

> Coming soon...

---

## 📁 Project Structure

```
MemoFast/
├── memofast_gui.py        # Main GUI application
├── unreal_manager.py      # Unreal Engine translation engine
├── unity_manager.py       # Unity Engine translation engine
├── cobra_manager.py       # Cobra Engine translation engine
├── translator_manager.py  # BepInEx/MelonLoader installation
├── scanner.py             # Game scanner
├── screen_translator.py   # OCR screen translation
├── patcher.py             # Backup and patching
├── config.py              # Settings and constants
├── logger.py              # Logging system
├── app_updater.py         # Auto-update feature
├── crypto_manager.py      # Encryption manager
├── security_utils.py      # Security tools
├── deepl_helper.py        # DeepL API helper
├── requirements.txt       # Python dependencies
└── gui/                   # GUI components
    ├── dialogs/           # Dialog windows
    ├── widgets/           # Custom widgets
    ├── pages/             # Page components
    └── styles/            # Themes and styles
```

---

## 🤝 Contributing

We welcome your contributions!

1. **Fork** this repository
2. Create a new **branch** (`git checkout -b new-feature`)
3. **Commit** your changes (`git commit -m 'Add new feature'`)
4. **Push** your branch (`git push origin new-feature`)
5. Open a **Pull Request**

---

## 📺 Contact

- **YouTube**: [@MehmetariTv](https://www.youtube.com/@MehmetariTv)

---

## 📄 License

This project is licensed under the [MIT License](LICENSE).

---

<p align="center">
  ⭐ Don't forget to star if you like it!
</p>