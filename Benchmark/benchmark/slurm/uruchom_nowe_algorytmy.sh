#!/bin/bash
# uruchom_nowe_algorytmy.sh
#
# Dolicza TYLKO 8 nowych algorytmów (dodanych 2026-09-15: mpc_liniowy_zabezpieczony/
# mpc_prognoza_pogody_zabezpieczony/mpc_miekkie_ograniczenia_zabezpieczony,
# mpc_binarny/mpc_prognoza_binarny/mpc_miekkie_binarny, fuzzy_ryzyko_adaptacyjny/
# fuzzy_ryzyko_agresywny) do JUŻ POLICZONYCH wyników pozostałych 37 algorytmów -
# NIE liczy niczego od nowa, NIE dotyka istniejących wierszy.
#
# JAK TO DZIAŁA: każdy skrypt testowy ma wbudowany mechanizm wznowienia/scalania
# (SZYNA_WZNOW=1, domyślne) - czyta ISTNIEJĄCY zbiorczy CSV w swoim folderze
# wyników, i liczy TYLKO kombinacje (lokalizacja, algorytm[, scenariusz]), których
# tam jeszcze nie ma. Ustawiając SZYNA_ALGORYTMY (lub SZYNA_ALGORYTMY_KROK dla
# kroku sterowania - INNA nazwa zmiennej, patrz test_wrazliwosc_kroku_sterowania.py)
# na TYLKO tych 8 nazw, każdy skrypt "widzi" WSZYSTKIE ich kombinacje jako
# brakujące (bo nigdy wcześniej nie policzone), dolicza JE, po czym zapisuje
# SCALONY CSV (stare 37 + nowe 8) i NADPISUJE Podsumowanie_*.xlsx zaktualizowaną,
# KOMPLETNĄ wersją - dokładnie to, o co prosił użytkownik ("zaktualizować o nowe
# dane excele, nie liczyć wszystkiego od nowa").
#
# WAŻNE ZAŁOŻENIE: to działa TYLKO jeśli w $SLURM_SUBMIT_DIR/wyniki/... na
# KLASTRZE nadal leżą te same zbiorcze CSV, z których pochodzą pliki, które masz
# lokalnie (PRZEGLAD_ZBIORCZY.csv/AWARIE_ZBIORCZY.csv/itd.) - jeśli je stamtąd
# usunięto, skrypty policzą WSZYSTKO od zera (drogo!). Sprawdź PRZED zleceniem:
#   wc -l wyniki/przeglad_wielu_lokalizacji/PRZEGLAD_ZBIORCZY.csv
# powinno pokazać >1628 linii (1628 = 37 algorytmów x 44 lokalizacje + nagłówek).
#
# BUDŻET (na życzenie użytkownika, ~700 CPU-h pozostało na koncie 2026-09-15):
# każde z 5 zadań niżej skaluje się w przybliżeniu proporcjonalnie do 8/37 (~22%)
# względem oryginalnego PEŁNEGO przebiegu (patrz komentarze "KOSZT" w poszczególnych
# slurm_*.sh) - RAZEM szacunkowo 130-180 core-h:
#   pelny_przeglad        192-384 core-h (pełne 37 alg.) -> ~42-83 core-h (8 nowych)
#   wrazliwosc_2lok        72-108 core-h                 -> ~16-23 core-h
#   krok_sterowania           ~167 core-h                 -> ~36 core-h
#   szum_wielu_czujnikow      ~164 core-h                 -> ~35 core-h
#   test_awarie             (mały, kilka core-h)          -> ~2-5 core-h
# CELOWO BEZ slurm_wrazliwosc_transmitancji.sh (8x pełny przegląd) - to
# NAJDROŻSZY test (szacunkowo 330-660 core-h SAMO dla 8 nowych algorytmów, może
# zjeść większość pozostałego budżetu) - zlecaj GO OSOBNO (patrz komunikat na
# końcu tego skryptu), po sprawdzeniu dostępnego budżetu
# (service-balance --check-cpu), żeby jeden drogi test nie zablokował tańszych.
#
# WAŻNE: uruchamiasz ten plik BEZPOŚREDNIO (`bash`), NIE przez `sbatch` - to
# zwykły skrypt powłoki, który tylko SKŁADA zadania do kolejki z zależnościami.
#
# Uruchomienie (z katalogu Benchmark/benchmark na klastrze):
#   bash slurm/uruchom_nowe_algorytmy.sh

set -euo pipefail

NOWE_ALGORYTMY="mpc_liniowy_zabezpieczony,mpc_prognoza_pogody_zabezpieczony,mpc_miekkie_ograniczenia_zabezpieczony,mpc_binarny,mpc_prognoza_binarny,mpc_miekkie_binarny,fuzzy_ryzyko_adaptacyjny,fuzzy_ryzyko_agresywny"

# WAŻNE (dodane 2026-09-15 po realnym incydencie QOSGrpCPUMinutesLimit na
# klastrze): --time PONIŻEJ nadpisuje #SBATCH --time W KAŻDYM slurm_*.sh (flagi
# sbatch z linii poleceń mają pierwszeństwo nad dyrektywami w pliku) - CELOWO
# dużo mniejsze niż oryginalne 12h/6h/4h (te były dobrane pod PEŁNY przebieg 37
# algorytmów) - żeby zadeklarowana rezerwacja (rdzenie x czas) NIE przekroczyła
# dostępnego budżetu konta przy zlecaniu (SLURM sprawdza DEKLAROWANY, nie
# rzeczywisty czas) - realny szacunek dla 8 algorytmów to 42-83/16-23/36/35 core-h
# (patrz nagłówek pliku), więc te limity mają WCIĄŻ 2-4x zapas, nie są "na styk".
CZAS_PELNY_PRZEGLAD=03:00:00      # 64 rdzenie x 3h = 192 core-h ceiling (realnie ~42-83).
CZAS_WRAZLIWOSC_2LOK=01:30:00     # 64 rdzenie x 1.5h = 96 core-h ceiling (realnie ~16-23).
CZAS_KROK_STEROWANIA=02:00:00     # 64 rdzenie x 2h = 128 core-h ceiling (realnie ~36).
CZAS_SZUM_CZUJNIKOW=02:00:00      # 64 rdzenie x 2h = 128 core-h ceiling (realnie ~35).
CZAS_TEST_AWARIE=01:00:00         # 16 rdzeni x 1h = 16 core-h ceiling (realnie kilka).

echo "Dolicz TYLKO nowe algorytmy: $NOWE_ALGORYTMY"
echo ""

# WAŻNE (dodane 2026-09-15 po realnym incydencie - PIERWSZY przebieg policzył
# TYLKO 1 z 8 algorytmów): --export=ALL,ZMIENNA="a,b,c" NIE DZIAŁA gdy wartość
# zmiennej SAMA zawiera przecinki - sbatch parsuje CAŁĄ wartość --export po
# przecinkach (cudzysłowy są zdejmowane przez shell PRZED tym, jak sbatch
# zobaczy argument, więc nie chronią przecinków wewnątrz wartości), więc
# SZYNA_ALGORYTMY dostawało tylko pierwszą nazwę do pierwszego przecinka, a
# reszta nazw trafiała jako bezsensowne dodatkowe tokeny bez "=" i była po
# cichu ignorowana. POPRAWKA: ustawiamy zmienną w środowisku BASH-a (export)
# PRZED wywołaniem sbatch, i używamy WYŁĄCZNIE --export=ALL (bez dopisywania
# wartości) - ALL przenosi WSZYSTKIE zmienne środowiskowe procesu, w tym tę,
# bez żadnego dodatkowego parsowania po przecinkach.
export SZYNA_ALGORYTMY="$NOWE_ALGORYTMY"

echo "1/5 Zlecam pelny_przeglad (tylko nowe algorytmy)..."
JOB1=$(sbatch --parsable --time=$CZAS_PELNY_PRZEGLAD --export=ALL slurm/slurm_pelny_przeglad.sh)
echo "    -> job $JOB1"

echo "2/5 Zlecam wrazliwosc_2lok (start po sukcesie $JOB1)..."
JOB2=$(sbatch --parsable --dependency=afterok:$JOB1 --time=$CZAS_WRAZLIWOSC_2LOK --export=ALL slurm/slurm_wrazliwosc_2lok.sh)
echo "    -> job $JOB2"

# test_wrazliwosc_kroku_sterowania.py czyta INNĄ zmienną (SZYNA_ALGORYTMY_KROK,
# nie SZYNA_ALGORYTMY) - patrz komentarz w nagłówku tego pliku.
export SZYNA_ALGORYTMY_KROK="$NOWE_ALGORYTMY"

echo "3/5 Zlecam krok_sterowania (start po sukcesie $JOB2)..."
JOB3=$(sbatch --parsable --dependency=afterok:$JOB2 --time=$CZAS_KROK_STEROWANIA --export=ALL slurm/slurm_krok_sterowania.sh)
echo "    -> job $JOB3"

echo "4/5 Zlecam szum_wielu_czujnikow (start po sukcesie $JOB3)..."
JOB4=$(sbatch --parsable --dependency=afterok:$JOB3 --time=$CZAS_SZUM_CZUJNIKOW --export=ALL slurm/slurm_szum_wielu_czujnikow.sh)
echo "    -> job $JOB4"

echo "5/5 Zlecam test_awarie (start po sukcesie $JOB4)..."
JOB5=$(sbatch --parsable --dependency=afterok:$JOB4 --time=$CZAS_TEST_AWARIE --export=ALL slurm/slurm_test_awarie.sh)
echo "    -> job $JOB5"

echo ""
echo "Zlecono 5 zadań w łańcuchu (tylko nowe algorytmy, szacunkowo 130-180 core-h):"
echo "  $JOB1  pelny_przeglad"
echo "  $JOB2  wrazliwosc_2lok        (start po sukcesie $JOB1)"
echo "  $JOB3  krok_sterowania        (start po sukcesie $JOB2)"
echo "  $JOB4  szum_wielu_czujnikow   (start po sukcesie $JOB3)"
echo "  $JOB5  test_awarie            (start po sukcesie $JOB4)"
echo ""
echo "Monitoruj: squeue -u \$USER"
echo "Każde zadanie NADPISZE istniejący Podsumowanie_*.xlsx w swoim folderze"
echo "zaktualizowaną wersją (stare 37 algorytmów + 8 nowych) - nic więcej nie"
echo "musisz robić dla tych 5 testów."
echo ""
echo "======================================================================"
echo "Wrażliwość transmitancji (8x pełny przegląd) CELOWO NIE jest w tym"
echo "łańcuchu - to NAJDROŻSZY test (szacunkowo 330-660 core-h TYLKO dla 8"
echo "nowych algorytmów). Sprawdź budżet PRZED zleceniem:"
echo "  service-balance --check-cpu"
echo "Jeśli starczy - zlecaj OSOBNO (nie musi czekać na 5 zadań wyżej). SZYNA_ALGORYTMY"
echo "jest już ustawione w tej sesji shella (export wyżej), więc --export=ALL wystarczy:"
echo "  sbatch --export=ALL slurm/slurm_wrazliwosc_transmitancji.sh"
echo "Po jej zakończeniu (wszystkie 8 elementów tablicy, sprawdź squeue) zbuduj"
echo "skonsolidowany Excel (8 scenariuszy w jednym pliku):"
echo "  python generatory_excel/generuj_excel_wrazliwosc_transmitancji.py"
echo "======================================================================"
echo ""
echo "Na koniec (opcjonalnie, odświeża zbiorcze podsumowanie WSZYSTKICH testów):"
echo "  python generatory_excel/generuj_excel_master.py"
