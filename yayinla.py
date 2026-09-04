# -*- coding: utf-8 -*-
"""MemoFast - Yeni surum yayinlama araci (SADECE GELISTIRICI ICIN).

Bu dosya kullanicilara DAGITILMAZ (paketleme disinda birakilir).

KULLANIM:
    python yayinla.py 1.1.3 "Su hata duzeltildi" "Su eklendi"

NE YAPAR:
  1. Yeni surumu PAKETE giren config.py kopyasina yazar (senin diskteki
     config.py'ne DOKUNMAZ; yerel surumun sabit kalir, test edebilirsin).
  2. Kok dizindeki tum .py dosyalarini (gelistirici araclari haric)
     memofast_kod_<surum>.zip icine koyar  (~1 MB).
  3. SHA-256 hesaplar.
  4. Zip'i GitHub release'ine yukler (etiket: guncelleme).
  5. surum.json'u siteye (zibildak.github.io/MemoFastv) yazar.

Kullanicilar programi bir sonraki acislarinda guncelleme penceresini gorur.

GEREKSINIM: gh (GitHub CLI) kurulu ve 'gh auth login' yapilmis olmali.
            zibildak/MemoFastv deposunda GitHub Pages ACIK olmali.
"""

import os
import re
import sys
import json
import base64
import hashlib
import zipfile
import subprocess

REPO = "zibildak/MemoFastv"
ETIKET = "guncelleme"          # kod paketlerinin durdugu release etiketi
GH = r"C:\Program Files\GitHub CLI\gh.exe"

KOK = os.path.dirname(os.path.abspath(__file__))

# Pakete GIRMEYECEK .py dosyalari (gelistirici araclari / test / gecici)
HARIC = {
    "yayinla.py", "update_builder.py",
    "test_gui_integration.py", "test_ocr.py", "test_scan.py",
    "test_guncelleme.py", "tmp_steam_scrape.py", "scrape_keys.py",
}

# Uygulamanin calisma aninda kullandigi ama KOKTE OLMAYAN python paketleri.
# memofast_gui.py bunlari import eder:
#   gui/    -> ana pencere, sayfalar, dialoglar, widget'lar
#   gemma/  -> yerel AI motoru
#   unity/  -> asset_viewer (Unity tam ceviri)
# Bunlar pakete girmedigi surece buradaki duzeltmeler kullaniciya ULASMAZ.
ALT_PAKETLER = ["gui", "gemma", "unity"]

# Alt paketler ancak alt klasor destekli app_updater (>=1.1.8) kullanicilara
# yayildiktan SONRA gonderilebilir. Eski updater '/' iceren girdiyi reddedip
# guncellemenin TAMAMINI iptal eder. Hazir olunca --altpaketler ile ac.
ALT_PAKET_VARSAYILAN = False


def gh_calistir(argv, girdi=None):
    """gh komutunu calistirir; hata olursa programi durdurur."""
    exe = GH if os.path.exists(GH) else "gh"
    r = subprocess.run([exe] + argv, capture_output=True, text=True,
                       input=girdi, encoding="utf-8")
    if r.returncode != 0:
        print("HATA (gh):", (r.stderr or r.stdout or "").strip()[:500])
        sys.exit(1)
    return (r.stdout or "").strip()


def _config_surumlu(surum):
    """config.py'yi diskten okur, VERSION'i yeni surume cevirip METIN doner.
    Diskteki config.py'ye DOKUNMAZ; sadece pakete girecek kopyayi hazirlar."""
    yol = os.path.join(KOK, "config.py")
    with open(yol, "r", encoding="utf-8") as f:
        icerik = f.read()
    yeni, adet = re.subn(r'^(\s*VERSION\s*=\s*)"[^"]*"',
                         r'\g<1>"' + surum + '"', icerik, count=1, flags=re.M)
    if adet != 1:
        print("HATA: config.py icinde VERSION satiri bulunamadi.")
        sys.exit(1)
    return yeni


def _alt_paket_dosyalari():
    """gui/, gemma/, unity/ altindaki .py dosyalarini (zip ici yol, disk yolu)
    ciftleri olarak doner. __pycache__ ve test/gecici dosyalar haric."""
    cikti = []
    for paket in ALT_PAKETLER:
        kok = os.path.join(KOK, paket)
        if not os.path.isdir(kok):
            continue
        for dizin, alt_dizinler, dosyalar in os.walk(kok):
            alt_dizinler[:] = [a for a in alt_dizinler if a != "__pycache__"]
            for d in sorted(dosyalar):
                if not d.lower().endswith(".py") or d in HARIC:
                    continue
                tam = os.path.join(dizin, d)
                zip_yolu = os.path.relpath(tam, KOK).replace(os.sep, "/")
                cikti.append((zip_yolu, tam))
    return sorted(cikti)


def paket_yap(surum, alt_paketler=ALT_PAKET_VARSAYILAN):
    """Kok dizindeki .py dosyalarini tek zip'e koyar.
    config.py pakete YENI surumle girer; diskteki config.py degismez.

    alt_paketler=True ise gui/, gemma/, unity/ de eklenir. DIKKAT: bunu
    yalnizca alt klasor destekli updater (>=1.1.8) yayildiktan sonra ac,
    yoksa eski istemciler paketi komple reddeder."""
    dosyalar = sorted(
        d for d in os.listdir(KOK)
        if d.lower().endswith(".py") and d not in HARIC
        and os.path.isfile(os.path.join(KOK, d)))
    if not dosyalar:
        print("HATA: paketlenecek .py dosyasi yok.")
        sys.exit(1)

    zip_yolu = os.path.join(KOK, f"memofast_kod_{surum}.zip")
    with zipfile.ZipFile(zip_yolu, "w", zipfile.ZIP_DEFLATED,
                         compresslevel=9) as z:
        for d in dosyalar:
            if d == "config.py":
                z.writestr("config.py", _config_surumlu(surum))  # surum enjekte
            else:
                z.write(os.path.join(KOK, d), d)

        if alt_paketler:
            alt = _alt_paket_dosyalari()
            for ic_yol, disk_yolu in alt:
                z.write(disk_yolu, ic_yol)
            print(f"  alt paketler: {len(alt)} dosya "
                  f"({', '.join(ALT_PAKETLER)})")
        else:
            print("  alt paketler: KAPALI (gui/, gemma/, unity/ "
                  "gonderilmiyor - --altpaketler ile acilir)")

    with open(zip_yolu, "rb") as f:
        veri = f.read()
    print(f"  paket: {os.path.basename(zip_yolu)}  "
          f"({len(dosyalar)} dosya, {len(veri)/1024:.0f} KB)")
    return zip_yolu, hashlib.sha256(veri).hexdigest(), len(veri)


def release_hazirla():
    """'guncelleme' etiketli release yoksa olusturur."""
    exe = GH if os.path.exists(GH) else "gh"
    r = subprocess.run([exe, "release", "view", ETIKET, "--repo", REPO],
                       capture_output=True, text=True)
    if r.returncode != 0:
        print("  release olusturuluyor…")
        # --prerelease: kod paketleri "latest" olarak gorunmesin; "latest"
        # her zaman tam kurulum release'ine (v1.x.x) isaret etsin.
        gh_calistir(["release", "create", ETIKET, "--repo", REPO,
                     "--title", "MemoFast kod guncellemeleri", "--prerelease",
                     "--notes", "Programin otomatik guncelleme paketleri."])


def surum_json_yaz(bilgi):
    """surum.json'u siteye yazar (GitHub Contents API uzerinden)."""
    icerik = json.dumps(bilgi, ensure_ascii=False, indent=2)
    b64 = base64.b64encode(icerik.encode("utf-8")).decode("ascii")

    # dosya varsa mevcut sha lazim (uzerine yazmak icin)
    exe = GH if os.path.exists(GH) else "gh"
    r = subprocess.run(
        [exe, "api", f"repos/{REPO}/contents/surum.json",
         "--jq", ".sha"], capture_output=True, text=True)
    eski_sha = r.stdout.strip() if r.returncode == 0 else ""

    argv = ["api", f"repos/{REPO}/contents/surum.json", "-X", "PUT",
            "-f", f"message=surum {bilgi['surum']}",
            "-f", f"content={b64}"]
    if eski_sha:
        argv += ["-f", f"sha={eski_sha}"]
    gh_calistir(argv)
    print("  surum.json siteye yazildi")


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    argv = list(sys.argv[1:])
    alt_paketler = ALT_PAKET_VARSAYILAN
    if "--altpaketler" in argv:
        argv.remove("--altpaketler")
        alt_paketler = True

    surum = argv[0].strip()
    notlar = [n.strip() for n in argv[1:] if n.strip()]
    if not re.match(r"^\d+(\.\d+)*$", surum):
        print("HATA: surum '1.1.3' gibi olmali.")
        sys.exit(1)

    print(f"\n=== MemoFast — surum {surum} yayinlaniyor ===")
    zip_yolu, sha, boyut = paket_yap(surum, alt_paketler=alt_paketler)

    release_hazirla()
    print("  paket yukleniyor…")
    gh_calistir(["release", "upload", ETIKET, zip_yolu,
                 "--repo", REPO, "--clobber"])

    bilgi = {
        "surum": surum,
        "notlar": notlar or ["Kücük düzeltmeler"],
        "paket_url": (f"https://github.com/{REPO}/releases/download/"
                      f"{ETIKET}/{os.path.basename(zip_yolu)}"),
        "sha256": sha,
        "boyut": boyut,
        "tam_kurulum_gerekli": False,
        "site": "https://zibildak.github.io/MemoFastv",
    }
    surum_json_yaz(bilgi)

    os.remove(zip_yolu)
    print(f"\nBITTI. Kullanicilar programi acinca {surum} guncellemesini "
          f"gorecek.\n")


if __name__ == "__main__":
    main()
