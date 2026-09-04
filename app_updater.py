# -*- coding: utf-8 -*-
"""MemoFast - Otomatik guncelleme (Kesat V3 tarifiyle kuruldu).

MANTIK: Dagitim paketinin neredeyse tamami (gomulu python, kutuphaneler,
araclar) surumden surume DEGISMEZ. Gercekten degisen sey kok dizindeki
.py dosyalaridir. Bu yuzden guncelleme koca paketi degil, sadece bu
.py dosyalarini (birkac yuz KB) indirir.

AKIS:
  1. Acilista arka planda surum.json okunur (birkac KB).
  2. Uzak surum yereldekinden buyukse kullaniciya pencere gosterilir.
  3. Onaylarsa kod paketi (.zip) indirilir.
  4. SHA-256 dogrulanir  -> tutmuyorsa islem iptal, hicbir dosyaya dokunulmaz.
  5. Icindeki her .py DERLENIR -> bozuk kod varsa iptal.
  6. Mevcut .py dosyalari yedeklenir.
  7. Yeni dosyalar kopyalanir; herhangi bir hatada yedek GERI YUKLENIR.
  8. Program kendini yeniden baslatir.

Bu dosyanin tamami "hata olursa hicbir sey yapma" prensibiyle yazilmistir:
internet yoksa, sunucu cevap vermezse, paket bozuksa kullaniciya hata
penceresi CIKMAZ; program normal calismaya devam eder.
"""

import os
import sys
import json
import time
import shutil
import hashlib
import tempfile
import zipfile
import py_compile
import urllib.request


# ─────────────────────────────────────────────────────────────────────
# AYARLAR
# ─────────────────────────────────────────────────────────────────────

# Surum bilgisinin okundugu adres (GitHub Pages -> API limiti yok).
# yayinla.py bu dosyayi zibildak/MemoFastv deposunun koklerine yazar,
# GitHub Pages onu bu adreste yayinlar.
SURUM_URL = "https://zibildak.github.io/MemoFastv/surum.json"

# Guncelleme paketi cok buyukse indirme (kotu niyetli/yanlis dosyaya karsi)
MAKS_PAKET_BOYUTU = 25 * 1024 * 1024      # 25 MB

_NET_TIMEOUT = 10


def SURUM():
    """Uygulamanin su anki surumu (config.py -> Config.VERSION)."""
    try:
        from config import Config
        return str(Config.VERSION).strip()
    except Exception:
        return "0.0.0"


def _uygulama_dizini():
    """app_updater.py'nin bulundugu klasor (guncellenecek .py'ler burada)."""
    return os.path.dirname(os.path.abspath(__file__))


def surum_tuple(s):
    """'1.10.2' -> (1, 10, 2). Karsilastirilabilir hale getirir.

    String karsilastirmasi YANLISTIR ('1.10' < '1.9' cikar); mutlaka
    sayi demetine cevrilir.
    """
    parcalar = []
    for p in str(s).strip().split("."):
        sayi = "".join(ch for ch in p if ch.isdigit())
        parcalar.append(int(sayi) if sayi else 0)
    return tuple(parcalar) or (0,)


def daha_yeni_mi(uzak, yerel=None):
    """Uzak surum yereldekinden yeni mi?"""
    return surum_tuple(uzak) > surum_tuple(yerel or SURUM())


# ─────────────────────────────────────────────────────────────────────
# 1) SURUM SORGUSU
# ─────────────────────────────────────────────────────────────────────

def surum_bilgisi_al():
    """surum.json'u okur. Basarisizsa None (sessiz).

    Beklenen bicim:
      {"surum": "1.1.3", "notlar": ["..."], "paket_url": "...",
       "sha256": "...", "boyut": 912345, "tam_kurulum_gerekli": false}
    """
    try:
        req = urllib.request.Request(
            SURUM_URL + "?t=" + str(int(time.time())),   # onbellek kirici
            headers={"User-Agent": "MemoFast/" + SURUM()})
        with urllib.request.urlopen(req, timeout=_NET_TIMEOUT) as r:
            bilgi = json.loads(r.read().decode("utf-8"))
    except Exception:
        return None

    if not isinstance(bilgi, dict) or not bilgi.get("surum"):
        return None
    return bilgi


# ─────────────────────────────────────────────────────────────────────
# 2) INDIRME + DOGRULAMA
# ─────────────────────────────────────────────────────────────────────

def paketi_indir(bilgi, ilerleme=None):
    """Kod paketini gecici dosyaya indirir ve SHA-256'sini dogrular.

    Doner: (gecici_zip_yolu, None) veya (None, "hata mesaji")
    """
    url = bilgi.get("paket_url") or ""
    beklenen = (bilgi.get("sha256") or "").lower().strip()

    if not url.startswith("https://"):
        return None, "Güncelleme adresi geçersiz."
    if len(beklenen) != 64:
        return None, "Güncelleme parmak izi eksik."

    try:
        req = urllib.request.Request(
            url, headers={"User-Agent": "MemoFast/" + SURUM()})
        with urllib.request.urlopen(req, timeout=60) as r:
            uzunluk = int(r.headers.get("Content-Length") or 0)
            if uzunluk > MAKS_PAKET_BOYUTU:
                return None, "Güncelleme paketi beklenenden büyük."

            fd, gecici = tempfile.mkstemp(suffix=".zip", prefix="memofast_upd_")
            os.close(fd)
            h = hashlib.sha256()
            inen = 0
            with open(gecici, "wb") as f:
                while True:
                    parca = r.read(64 * 1024)
                    if not parca:
                        break
                    inen += len(parca)
                    if inen > MAKS_PAKET_BOYUTU:
                        f.close()
                        os.remove(gecici)
                        return None, "Güncelleme paketi beklenenden büyük."
                    h.update(parca)
                    f.write(parca)
                    if ilerleme and uzunluk:
                        ilerleme(int(inen * 100 / uzunluk))
    except Exception as e:
        return None, f"İndirme başarısız: {e}"

    if h.hexdigest().lower() != beklenen:
        try:
            os.remove(gecici)
        except Exception:
            pass
        return None, "Paket doğrulaması başarısız (dosya bozuk olabilir)."

    return gecici, None


def _guvenli_isimler(zf):
    """ZIP icindeki girisleri denetler.

    Sadece .py dosyalarina izin verilir. ALT KLASOR ARTIK SERBEST
    (gui/, gemma/, unity/ gibi paketler de guncellenebilsin diye), ama
    dizin disina yazma saldirisina karsi su kurallar korunur:
      - mutlak yol yasak
      - '..' ile ust dizine cikma yasak
      - ters bolu (Windows yolu) yasak
      - surucu harfi (C:) yasak
      - cozulmus yol hedef dizinin ICINDE kalmali

    NOT: Eski surumler (<=1.1.7) '/' iceren her girdiyi reddediyordu.
    Bu yuzden alt klasorlu paketler ancak bu surum kullanicilara
    ulastiktan SONRA yayinlanabilir.
    """
    isimler = []
    for n in zf.namelist():
        if n.endswith("/"):          # klasor girdisi: gerek yok
            continue
        if "\\" in n or os.path.isabs(n) or ":" in n:
            return None
        parcalar = n.split("/")
        if any(p in ("", ".", "..") for p in parcalar):
            return None
        if not n.lower().endswith(".py"):
            return None
        isimler.append(n)
    return isimler or None


# ─────────────────────────────────────────────────────────────────────
# 3) UYGULAMA (yedek + geri alma)
# ─────────────────────────────────────────────────────────────────────

def paketi_uygula(zip_yolu, yeni_surum):
    """Indirilen paketi kurar. Doner: (True, "") veya (False, "hata").

    Once gecici klasore acar, her dosyayi DERLER; sorun yoksa mevcut
    dosyalari yedekleyip uzerine yazar. Kopyalama sirasinda hata olursa
    yedekten GERI YUKLER, yani yarim kalmis kurulum olmaz.
    """
    hedef_dizin = _uygulama_dizini()
    gecici_dizin = tempfile.mkdtemp(prefix="memofast_upd_")
    yedek_dizin = os.path.join(hedef_dizin, "_guncelleme_yedek")

    try:
        # --- ac ve denetle ---
        try:
            with zipfile.ZipFile(zip_yolu) as zf:
                isimler = _guvenli_isimler(zf)
                if not isimler:
                    return False, "Paket içeriği beklenmedik biçimde."
                zf.extractall(gecici_dizin)
        except zipfile.BadZipFile:
            return False, "Paket açılamadı (bozuk zip)."

        # --- her dosya derlenebiliyor mu? ---
        for ad in isimler:
            yol = os.path.join(gecici_dizin, *ad.split("/"))
            try:
                py_compile.compile(yol, doraise=True, cfile=yol + "c")
            except Exception as e:
                return False, f"Güncellemedeki {ad} hatalı, kurulmadı ({e})."

        # --- mevcut dosyalari yedekle ---
        if os.path.isdir(yedek_dizin):
            shutil.rmtree(yedek_dizin, ignore_errors=True)
        os.makedirs(yedek_dizin, exist_ok=True)
        yedeklenen = []
        for ad in isimler:
            mevcut = os.path.join(hedef_dizin, *ad.split("/"))
            if os.path.exists(mevcut):
                yedek_hedef = os.path.join(yedek_dizin, *ad.split("/"))
                os.makedirs(os.path.dirname(yedek_hedef), exist_ok=True)
                shutil.copy2(mevcut, yedek_hedef)
                yedeklenen.append(ad)

        # --- kopyala; hata olursa geri al ---
        try:
            for ad in isimler:
                hedef = os.path.join(hedef_dizin, *ad.split("/"))
                os.makedirs(os.path.dirname(hedef), exist_ok=True)
                shutil.copy2(os.path.join(gecici_dizin, *ad.split("/")), hedef)
        except Exception as e:
            for ad in yedeklenen:
                try:
                    shutil.copy2(os.path.join(yedek_dizin, *ad.split("/")),
                                 os.path.join(hedef_dizin, *ad.split("/")))
                except Exception:
                    pass
            return False, (f"Kurulum sırasında hata ({e}). Önceki sürüm "
                           "geri yüklendi, programınız çalışmaya devam eder.")

        return True, ""
    finally:
        shutil.rmtree(gecici_dizin, ignore_errors=True)
        try:
            os.remove(zip_yolu)
        except Exception:
            pass


def yeniden_baslat():
    """Programi kapatip yeniden acar (yeni kod ancak boyle devreye girer)."""
    try:
        import subprocess
        subprocess.Popen([sys.executable] + sys.argv,
                         cwd=_uygulama_dizini(), close_fds=True)
    except Exception:
        return False
    return True


# ─────────────────────────────────────────────────────────────────────
# 4) ARAYUZ: arka plan kontrolu + pencere
# ─────────────────────────────────────────────────────────────────────

from PyQt5.QtCore import QThread, pyqtSignal


class GuncellemeKontrolThread(QThread):
    """Acilista arka planda 'yeni surum var mi' diye bakar.

    Ag beklemesi UI'yi dondurmesin diye ayri thread'de calisir. Sonuc
    yoksa hicbir sinyal yayilmaz -> kullanici hicbir sey gormez.
    """

    bulundu = pyqtSignal(dict)

    def __init__(self, gecikme_ms=4000):
        super().__init__()
        # Acilisin ilk saniyeleri agir; kontrolu biraz geciktir
        self._gecikme = gecikme_ms
        self._running = True

    def stop(self):
        self._running = False

    def run(self):
        for _ in range(int(self._gecikme / 100)):
            if not self._running:
                return
            self.msleep(100)
        bilgi = surum_bilgisi_al()
        if not self._running or not bilgi:
            return
        if daha_yeni_mi(bilgi.get("surum")):
            self.bulundu.emit(bilgi)


class GuncellemeIndirThread(QThread):
    """Paketi indirir, dogrular ve kurar (hepsi arka planda)."""

    ilerleme = pyqtSignal(int)
    bitti = pyqtSignal(bool, str)

    def __init__(self, bilgi):
        super().__init__()
        self.bilgi = bilgi

    def run(self):
        zip_yolu, hata = paketi_indir(
            self.bilgi, ilerleme=lambda y: self.ilerleme.emit(y))
        if hata:
            self.bitti.emit(False, hata)
            return
        ok, mesaj = paketi_uygula(zip_yolu, self.bilgi.get("surum", ""))
        self.bitti.emit(ok, mesaj)


def guncelleme_penceresi(parent, bilgi):
    """Yeni surum penceresi. Kullanici isterse indirip kurar.

    Doner: True  -> kuruldu, program yeniden baslatilmali
           False -> kullanici erteledi / kurulmadi
    """
    from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel,
                                 QPushButton, QProgressBar)

    yeni = bilgi.get("surum", "?")
    notlar = bilgi.get("notlar") or []
    boyut_mb = (bilgi.get("boyut") or 0) / 1024 / 1024

    dlg = QDialog(parent)
    dlg.setWindowTitle("MemoFast — Güncelleme")
    dlg.setMinimumWidth(440)
    dlg.setStyleSheet(
        "QDialog { background:#14161c; } QLabel { color:#e6e6ea; } "
        "QPushButton { background:#2b3550; color:#cfe0ff; border-radius:6px; "
        "padding:9px 14px; } QPushButton:hover { background:#354064; } "
        "QPushButton#ana { background:#2b8a3e; color:#fff; font-weight:bold; } "
        "QPushButton#ana:hover { background:#237032; } "
        "QProgressBar { background:#1e2129; border:1px solid #3a3f4b; "
        "border-radius:5px; height:16px; text-align:center; color:#cfe0ff; } "
        "QProgressBar::chunk { background:#2b8a3e; border-radius:4px; }")

    lay = QVBoxLayout(dlg)
    lay.setContentsMargins(24, 20, 24, 18)
    lay.setSpacing(11)

    baslik = QLabel(f"🎉 Yeni sürüm hazır: {yeni}")
    baslik.setStyleSheet("font-size:17px; font-weight:bold;")
    lay.addWidget(baslik)

    if notlar:
        md = "\n".join("•  " + str(n) for n in notlar[:8])
        nl = QLabel(md)
        nl.setWordWrap(True)
        nl.setStyleSheet("color:#a9adba; font-size:13px;")
        lay.addWidget(nl)

    alt = QLabel(f"İndirme boyutu: {boyut_mb:.1f} MB — birkaç saniye sürer.")
    alt.setStyleSheet("color:#7c8190; font-size:11px;")
    lay.addWidget(alt)

    cubuk = QProgressBar()
    cubuk.setVisible(False)
    lay.addWidget(cubuk)

    durum = QLabel("")
    durum.setWordWrap(True)
    durum.setStyleSheet("color:#ff6b6b; font-size:12px;")
    lay.addWidget(durum)

    satir = QHBoxLayout()
    sonra_btn = QPushButton("Sonra")
    guncelle_btn = QPushButton("Güncelle ve Yeniden Başlat")
    guncelle_btn.setObjectName("ana")
    satir.addWidget(sonra_btn)
    satir.addStretch()
    satir.addWidget(guncelle_btn)
    lay.addLayout(satir)

    sonuc = {"kuruldu": False}
    tutucu = {}

    def _basla():
        # Buyuk guncelleme: kod paketiyle cozulemez, siteye yonlendir
        if bilgi.get("tam_kurulum_gerekli"):
            import webbrowser
            webbrowser.open(bilgi.get("site") or "https://zibildak.github.io/MemoFastv")
            dlg.reject()
            return
        guncelle_btn.setEnabled(False)
        sonra_btn.setEnabled(False)
        guncelle_btn.setText("İndiriliyor…")
        cubuk.setVisible(True)
        durum.setText("")

        t = GuncellemeIndirThread(bilgi)
        tutucu["t"] = t          # thread'in erken silinmesini onler
        t.ilerleme.connect(cubuk.setValue)
        t.bitti.connect(_bitti)
        t.start()

    def _bitti(ok, mesaj):
        if ok:
            sonuc["kuruldu"] = True
            dlg.accept()
        else:
            cubuk.setVisible(False)
            durum.setText(mesaj or "Güncelleme kurulamadı.")
            guncelle_btn.setEnabled(True)
            sonra_btn.setEnabled(True)
            guncelle_btn.setText("Tekrar Dene")

    guncelle_btn.clicked.connect(_basla)
    sonra_btn.clicked.connect(dlg.reject)
    dlg.exec_()

    t = tutucu.get("t")
    if t is not None and t.isRunning():
        t.wait(3000)
    return sonuc["kuruldu"]
