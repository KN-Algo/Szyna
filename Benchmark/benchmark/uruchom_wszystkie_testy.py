# uruchom_wszystkie_testy.py
#
# JEDEN skrypt, który uruchamia PO KOLEI cały pakiet testów zbudowany w tym
# projekcie i na końcu buduje JEDEN skonsolidowany Excel ze wszystkich wyników
# (patrz generuj_excel_master.py) - na wyraźne życzenie użytkownika (2026-09-02):
# "włączę tylko jeden skrypt i wszystkie testy się odpalą".
#
# WAŻNE - to jest TRYB SZYBKIEJ WERYFIKACJI, nie zamiennik pełnych przebiegów:
# każdy test odpalany jest z DOMYŚLNIE ZMNIEJSZONYM zakresem (mniej dni/lokalizacji/
# scenariuszy niż jego "produkcyjne" ustawienia) - tak, żeby CAŁY pakiet skończył
# się w rozsądnym czasie lokalnie (orientacyjnie kilkadziesiąt minut, zależnie od
# liczby rdzeni), zamiast wielu godzin/dni pełnej skali. To celowy kompromis:
# potwierdza, że WSZYSTKO DZIAŁA END-TO-END i daje pierwszy, orientacyjny obraz
# wyników - pełne, statystycznie solidne przebiegi (43 lokalizacje, pełny zakres
# dat, wszystkie scenariusze) uruchamiasz OSOBNO, tymi samymi skryptami z
# ustawieniami domyślnymi (albo przez odpowiedni skrypt slurm_*.sh na klastrze).
#
# Każda zmienna środowiskowa "trybu szybkiego" poniżej jest ustawiana TYLKO
# jeśli jeszcze nie jest ustawiona (os.environ.setdefault) - czyli jeśli PRZED
# uruchomieniem tego skryptu sam ustawisz np. SZYNA_MAX_DNI=151, Twoja wartość
# WYGRYWA i ten konkretny test policzy się w pełnej skali.
#
# Uruchomienie: python uruchom_wszystkie_testy.py
# (z katalogu Benchmark/benchmark, z aktywnym środowiskiem/venv)

import os
import subprocess
import sys
import time

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PYTHON = sys.executable

# --- TRYB SZYBKI: ustawiane TYLKO jeśli użytkownik jeszcze nie ustawił sam. ---
_DOMYSLNE_SZYBKIE = {
    'SZYNA_MAX_DNI': '3',
    'SZYNA_LOKALIZACJE': 'abisko_60min_2024,ojmiakon_60min_2024,krakow_60min_2023,wroclaw_15min_2024,fairbanks_60min_2022',
    'SZYNA_MAX_DNI_WRAZ': '5',
    'SZYNA_SCENARIUSZE_WRAZ': 'nominal,K_plus20',
    'SZYNA_MAX_DNI_DIAG': '5',
    'SZYNA_LOKALIZACJA_DIAG': 'abisko_60min_2024',
    'SZYNA_ALGORYTMY_DIAG': 'risk_function_pid,risk_function_pid_auto',
    'SZYNA_MAX_DNI_AWARIE': '3',
    'SZYNA_LICZBA_LOKALIZACJI_SZUM': '2',
    'SZYNA_MAX_DNI_SZUM': '2',
}

# test_szum_wielu_czujnikow.py to 29 scenariuszy x wszystkie algorytmy x N
# lokalizacji - PRZY WSZYSTKICH 30 algorytmach nawet 2 lokalizacje x 2 dni to
# ~1740 zadań (za dużo na "szybki" przebieg, zmierzone ~0.19 core-min/zadanie
# przy 2-dniowym oknie -> rzędu godzin). Ograniczone do garstki reprezentatywnych
# algorytmów (po jednym z głównych rodzin) WYŁĄCZNIE na czas tego jednego etapu
# (patrz ETAPY niżej, 'env' per-etap - NIE globalnie, bo SZYNA_ALGORYTMY jest
# też czytane przez główny przegląd, który MA sprawdzić wszystkie 30).
_ALGORYTMY_SZUM_SZYBKI = 'algorytm_z_normy,risk_function_pid,risk_function_pid_auto,fuzzy_ryzyko_2v2_opad,nauka_kary_opad'
# Ta sama garstka reprezentatywnych algorytmów, z tego samego powodu, dla
# test_wrazliwosc_dwie_lokalizacje.py (30 algorytmów x scenariusze x 2
# lokalizacje x szum tak/nie też szybko rośnie - patrz komentarz wyżej).
_ALGORYTMY_WRAZ_SZYBKI = _ALGORYTMY_SZUM_SZYBKI
for _klucz, _wartosc in _DOMYSLNE_SZYBKIE.items():
    os.environ.setdefault(_klucz, _wartosc)

# Krok sterowania osobny (test_wrazliwosc_kroku_sterowania.py czyta SZYNA_MAX_DNI
# ogólne, ale chcemy go dodatkowo ograniczyć do 1 lokalizacji + 2 kroków, żeby
# nie mnożyć czasu razy 43 lokalizacje x 5 kroków x 3 algorytmy).
os.environ.setdefault('SZYNA_KROKI_S', '10,60')

ETAPY = [
    ('Skuteczność prognozy opadów (43 pliki, pełna skala - i tak szybkie)',
     ['test_skutecznosc_prognozy_opadow.py'], {}),
    ('Główny przegląd (tryb szybki: 5 lokalizacji, 3 dni, wszystkie algorytmy)',
     ['test_wszystkie_rownolegle.py'], {}),
    ('Wrażliwość transmitancji + szum, 2 lokalizacje (tryb szybki: 2 scenariusze, 5 dni, 5 algorytmów)',
     ['test_wrazliwosc_dwie_lokalizacje.py'],
     {'env': {'SZYNA_ALGORYTMY': _ALGORYTMY_WRAZ_SZYBKI}, 'nastepnie': ['generuj_excel_wrazliwosc.py']}),
    ('Diagnostyka funkcji ryzyka (tryb szybki: 5 dni)',
     ['test_diagnostyka_funkcji_ryzyka.py'], {}),
    ('Wrażliwość na krok sterowania (tryb szybki: 1 lokalizacja, 2 kroki)',
     ['test_wrazliwosc_kroku_sterowania.py'],
     {'env': {'SZYNA_LOKALIZACJE': 'abisko_60min_2024'}}),
    ('Test odporności na awarie czujników (tryb szybki: 3 dni)',
     ['test_awarie_czujnikow.py'], {}),
    ('Test szumu wielu czujników (tryb szybki: 2 lokalizacje, 2 dni, 5 reprezentatywnych algorytmów)',
     ['test_szum_wielu_czujnikow.py'],
     {'env': {'SZYNA_ALGORYTMY': _ALGORYTMY_SZUM_SZYBKI}}),
]


def uruchom_etap(nazwa, polecenie, opcje):
    print("\n" + "=" * 78)
    print(f"ETAP: {nazwa}")
    print("=" * 78)

    env_etapu = dict(os.environ)
    env_etapu.update(opcje.get('env', {}))

    t0 = time.time()
    wynik = subprocess.run([PYTHON] + polecenie, cwd=BASE_DIR, env=env_etapu)
    czas_min = (time.time() - t0) / 60.0

    sukces = wynik.returncode == 0
    print(f"-- {'OK' if sukces else 'BŁĄD'} ({czas_min:.1f} min): {' '.join(polecenie)}")

    for kolejne in opcje.get('nastepnie', []):
        wynik2 = subprocess.run([PYTHON, kolejne], cwd=BASE_DIR, env=env_etapu)
        sukces = sukces and (wynik2.returncode == 0)
        print(f"-- {'OK' if wynik2.returncode == 0 else 'BŁĄD'}: {kolejne}")

    return sukces


def main():
    print(f"Uruchamiam {len(ETAPY)} etapów testowych (tryb szybki - patrz nagłówek pliku).")
    print("Zmienne środowiskowe trybu szybkiego (nadpisz PRZED uruchomieniem, żeby wymusić pełną skalę):")
    for k, v in _DOMYSLNE_SZYBKIE.items():
        aktualna = os.environ.get(k)
        znacznik = ' (NADPISANE przez Ciebie)' if aktualna != v else ''
        print(f"  {k}={aktualna}{znacznik}")

    t_start = time.time()
    wyniki = []
    for nazwa, polecenie, opcje in ETAPY:
        sukces = uruchom_etap(nazwa, polecenie, opcje)
        wyniki.append((nazwa, sukces))

    czas_calkowity_min = (time.time() - t_start) / 60.0
    print("\n" + "=" * 78)
    print(f"PODSUMOWANIE ({czas_calkowity_min:.1f} min łącznie)")
    print("=" * 78)
    for nazwa, sukces in wyniki:
        print(f"  [{'OK' if sukces else 'BŁĄD'}] {nazwa}")

    liczba_bledow = sum(1 for _, s in wyniki if not s)
    if liczba_bledow:
        print(f"\nUWAGA: {liczba_bledow} etap(ów) zakończyło się błędem - sprawdź log powyżej. "
              "Reszta etapów i tak się wykonała (błąd jednego nie blokuje kolejnych).")

    print("\nBuduję skonsolidowany Excel ze wszystkich wyników...")
    wynik_master = subprocess.run([PYTHON, 'generuj_excel_master.py'], cwd=BASE_DIR, env=os.environ)
    if wynik_master.returncode != 0:
        print("!!! BŁĄD przy budowaniu skonsolidowanego Excela - poszczególne wyniki są bezpieczne "
              "w swoich folderach wyniki/*, spróbuj uruchomić generuj_excel_master.py osobno.")
    else:
        print(f"\nGotowe. Skonsolidowany Excel: {os.path.join(BASE_DIR, 'wyniki', 'Podsumowanie_MASTER.xlsx')}")


if __name__ == '__main__':
    main()
