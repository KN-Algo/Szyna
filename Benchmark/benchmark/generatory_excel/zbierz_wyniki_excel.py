# zbierz_wyniki_excel.py
#
# Skanuje wyniki/*.zip (paczki wyników pobrane z klastra/superkomputera) i wyciąga z
# KAŻDEGO tylko pliki .xlsx (pomijając ogromne surowe CSV per-krok - te zostają
# spakowane w oryginalnym zipie) do wyniki/wyniki_excela/<nazwa_zipa>/ - jeden folder
# na zip, żeby mieć wszystkie podsumowania wyników w jednym miejscu bez rozpakowywania
# całych (często >1GB) archiwów.
#
# Duplikaty: jeśli dwa zipy dają BAJT-IDENTYCZNY plik .xlsx (np. z przypadkowego
# podwójnego uruchomienia tego samego zadania SLURM), zachowywana jest TYLKO jedna
# kopia (ta z zipa, którego nazwa jest alfabetycznie pierwsza) - reszta pomijana z
# ostrzeżeniem, żeby folder nie puchł od identycznych plików.
#
# Uruchomienie (z katalogu Benchmark/benchmark):
#   python zbierz_wyniki_excel.py

import hashlib
import os
import zipfile

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # benchmark/ (rodzic generatory_excel/)
FOLDER_WYNIKOW = os.path.join(BASE_DIR, "wyniki")
FOLDER_WYJSCIOWY = os.path.join(FOLDER_WYNIKOW, "wyniki_excela")


def _sanitizuj_nazwe_folderu(nazwa_zipa):
    baza = os.path.splitext(nazwa_zipa)[0]
    # " (1)"/" (2)" itd. (typowy dopisek przeglądarki przy powtórnym pobraniu tego
    # samego pliku) - usuwamy nawiasy, ale zachowujemy numer, żeby foldery się nie
    # nadpisywały nawzajem, gdyby jednak NIE były identyczne.
    return baza.replace('(', '').replace(')', '').replace('  ', ' ').strip().replace(' ', '_')


def main():
    if not os.path.isdir(FOLDER_WYNIKOW):
        print(f"Brak folderu {FOLDER_WYNIKOW}.")
        return

    zipy = sorted(f for f in os.listdir(FOLDER_WYNIKOW) if f.lower().endswith('.zip'))
    if not zipy:
        print(f"Brak plików .zip w {FOLDER_WYNIKOW}.")
        return

    os.makedirs(FOLDER_WYJSCIOWY, exist_ok=True)

    hashe_zapisanych = {}  # md5 -> ścieżka już zapisanego pliku (do wykrywania duplikatów)
    zapisane = []
    pominiete_duplikaty = []
    bledy = []

    for nazwa_zipa in zipy:
        sciezka_zipa = os.path.join(FOLDER_WYNIKOW, nazwa_zipa)
        folder_docelowy = os.path.join(FOLDER_WYJSCIOWY, _sanitizuj_nazwe_folderu(nazwa_zipa))
        try:
            with zipfile.ZipFile(sciezka_zipa) as z:
                xlsx_wpisy = [n for n in z.namelist() if n.lower().endswith('.xlsx')]
                if not xlsx_wpisy:
                    print(f"UWAGA: {nazwa_zipa} nie zawiera żadnego pliku .xlsx - pomijam.")
                    continue
                for wpis in xlsx_wpisy:
                    dane = z.read(wpis)
                    h = hashlib.md5(dane).hexdigest()
                    if h in hashe_zapisanych:
                        pominiete_duplikaty.append((nazwa_zipa, wpis, hashe_zapisanych[h]))
                        continue
                    os.makedirs(folder_docelowy, exist_ok=True)
                    sciezka_wyjsciowa = os.path.join(folder_docelowy, os.path.basename(wpis))
                    with open(sciezka_wyjsciowa, 'wb') as f:
                        f.write(dane)
                    hashe_zapisanych[h] = sciezka_wyjsciowa
                    zapisane.append(sciezka_wyjsciowa)
        except Exception as e:
            bledy.append((nazwa_zipa, str(e)))

    print(f"Zapisano {len(zapisane)} plików .xlsx z {len(zipy)} zipów do {FOLDER_WYJSCIOWY}:")
    for s in zapisane:
        print(f"  - {os.path.relpath(s, BASE_DIR)}")

    if pominiete_duplikaty:
        print(f"\nPominięto {len(pominiete_duplikaty)} bajt-identycznych duplikatów:")
        for zip_nazwa, wpis, oryginal in pominiete_duplikaty:
            print(f"  - {zip_nazwa}::{wpis}  (identyczny z {os.path.relpath(oryginal, BASE_DIR)})")

    if bledy:
        print(f"\nBŁĘDY ({len(bledy)}):")
        for nazwa_zipa, blad in bledy:
            print(f"  - {nazwa_zipa}: {blad}")

    print(f"\nGotowe. Wszystkie podsumowania Excela w: {FOLDER_WYJSCIOWY}")


if __name__ == '__main__':
    main()
