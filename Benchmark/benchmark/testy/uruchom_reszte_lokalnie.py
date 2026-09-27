# uruchom_reszte_lokalnie.py
#
# Uruchamia LOKALNIE (pełna skala) wszystkie testy POZA głównym przeglądem
# (liczony na klastrze) i POZA wrażliwością na transmitancję (celowo pominięta):
#   prognoza  - skuteczność prognozy opadów (44 pliki, szybkie)
#   wraz      - wrażliwość transmitancji + szum, 2 lokalizacje (+ jego Excel)
#   krok      - wrażliwość na krok sterowania (4 lokalizacje, 45 algorytmów, 5 kroków)
#   awarie    - odporność na awarie czujników (1 lokalizacja)
#   szum      - szum wielu czujników (4 lokalizacje, 29 scenariuszy, 45 algorytmów)
# a na końcu buduje zbiorczy Excel wyniki/Podsumowanie_MASTER.xlsx.
# Każdy test sam wypisuje postęp: "[k/N] OK ... (upłynęło X min)".
#
# Uruchomienie (z katalogu Benchmark/benchmark):
#   python testy/uruchom_reszte_lokalnie.py
#   python testy/uruchom_reszte_lokalnie.py --tylko krok szum   # tylko wybrane etapy
#   python testy/uruchom_reszte_lokalnie.py --od-nowa           # wyrzuć poprzednie wyniki i licz od zera
#
# WZNAWIANIE: przy pierwszym uruchomieniu stare wyniki tych czterech testów
# (folder wyniki/wrazliwosc_2lokalizacje, wrazliwosc_kroku, awarie_czujnikow,
# szum_wielu_czujnikow) są PRZENOSZONE do wyniki/_stare_<data>/ - inaczej testy
# uznałyby je za "już policzone" (wznawianie) i pominęły. Kolejne uruchomienia
# (np. po Ctrl+C albo zamknięciu komputera) niczego nie ruszają i DOKOŃCZAJĄ
# tylko brakujące zadania. Znacznik: wyniki/.reszta_lokalnie_rozpoczeta.
#
# Koszt: ok. 160-220 rdzeniogodzin łącznie - liczba godzin zależy od liczby
# rdzeni (np. 4 rdzenie = kilkadziesiąt godzin). Można przerywać i wznawiać.

import argparse
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # benchmark/
PYTHON = sys.executable
FOLDER_WYNIKI = os.path.join(BASE_DIR, 'wyniki')
ZNACZNIK = os.path.join(FOLDER_WYNIKI, '.reszta_lokalnie_rozpoczeta')

# 4 najzimniejsze/najśnieżniejsze lokalizacje (jak w przeglądzie na klastrze).
LOKALIZACJE_4 = 'sodankyla_60min_2025,murmansk_60min_2025,quebec_city_60min_2025,norylsk_60min_2025'
ENV_WSPOLNE = {
    'SZYNA_LOKALIZACJE': LOKALIZACJE_4,        # krok sterowania
    'SZYNA_LOKALIZACJE_SZUM': LOKALIZACJE_4,   # szum wielu czujników
}

ETAPY = {
    'prognoza': ('Skuteczność prognozy opadów', ['testy/test_skutecznosc_prognozy_opadow.py'], []),
    'wraz': ('Wrażliwość transmitancji + szum, 2 lokalizacje', ['testy/test_wrazliwosc_dwie_lokalizacje.py'],
             ['generatory_excel/generuj_excel_wrazliwosc.py']),
    'krok': ('Wrażliwość na krok sterowania (4 lokalizacje)', ['testy/test_wrazliwosc_kroku_sterowania.py'], []),
    'awarie': ('Odporność na awarie czujników', ['testy/test_awarie_czujnikow.py'], []),
    'szum': ('Szum wielu czujników (4 lokalizacje)', ['testy/test_szum_wielu_czujnikow.py'], []),
}
FOLDERY_DO_ARCHIWIZACJI = ['wrazliwosc_2lokalizacje', 'wrazliwosc_kroku', 'awarie_czujnikow', 'szum_wielu_czujnikow']


def archiwizuj_stare_wyniki():
    cel = os.path.join(FOLDER_WYNIKI, f"_stare_{datetime.now():%Y-%m-%d_%H%M%S}")
    przeniesione = []
    for nazwa in FOLDERY_DO_ARCHIWIZACJI:
        zrodlo = os.path.join(FOLDER_WYNIKI, nazwa)
        if os.path.isdir(zrodlo):
            os.makedirs(cel, exist_ok=True)
            shutil.move(zrodlo, os.path.join(cel, nazwa))
            przeniesione.append(nazwa)
    if przeniesione:
        print(f"Stare wyniki ({', '.join(przeniesione)}) przeniesione do: {cel}")


def uruchom(polecenie, env):
    # -u: brak buforowania, żeby postęp ("[k/N] OK ...") było widać na bieżąco.
    return subprocess.run([PYTHON, '-u'] + polecenie, cwd=BASE_DIR, env=env).returncode == 0


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--tylko', nargs='+', choices=list(ETAPY), help='uruchom tylko wybrane etapy')
    parser.add_argument('--od-nowa', action='store_true', help='przenieś poprzednie wyniki i licz od zera')
    args = parser.parse_args()

    os.makedirs(FOLDER_WYNIKI, exist_ok=True)
    if args.od_nowa and os.path.exists(ZNACZNIK):
        os.remove(ZNACZNIK)
    if not os.path.exists(ZNACZNIK):
        archiwizuj_stare_wyniki()
        open(ZNACZNIK, 'w').write(datetime.now().isoformat())
    else:
        print("Wznawiam (znacznik istnieje) - policzone zadania zostaną pominięte.")

    env = dict(os.environ)
    for klucz, wartosc in ENV_WSPOLNE.items():
        env.setdefault(klucz, wartosc)

    wybrane = args.tylko or list(ETAPY)
    t_start = time.time()
    wyniki = []
    for i, klucz in enumerate(wybrane, start=1):
        nazwa, polecenie, nastepnie = ETAPY[klucz]
        print("\n" + "=" * 78)
        print(f"ETAP {i}/{len(wybrane)}: {nazwa}   (od startu: {(time.time() - t_start) / 60:.1f} min)")
        print("=" * 78, flush=True)
        t0 = time.time()
        ok = uruchom(polecenie, env)
        for kolejny in nastepnie:
            ok = uruchom([kolejny], env) and ok
        wyniki.append((nazwa, ok))
        print(f"-- {'OK' if ok else 'BŁĄD'} ({(time.time() - t0) / 60:.1f} min): {nazwa}", flush=True)

    print("\nBuduję zbiorczy Excel (wyniki/Podsumowanie_MASTER.xlsx)...", flush=True)
    ok_master = uruchom(['generatory_excel/generuj_excel_master.py'], env)

    print("\n" + "=" * 78)
    print(f"PODSUMOWANIE ({(time.time() - t_start) / 60:.1f} min łącznie)")
    for nazwa, ok in wyniki:
        print(f"  [{'OK' if ok else 'BŁĄD'}] {nazwa}")
    print(f"  [{'OK' if ok_master else 'BŁĄD'}] Excel zbiorczy")
    if not all(ok for _, ok in wyniki):
        print("Część etapów zakończyła się błędem - uruchom skrypt ponownie, dokończy brakujące zadania.")


if __name__ == '__main__':
    main()
