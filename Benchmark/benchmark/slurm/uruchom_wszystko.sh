#!/bin/bash
# uruchom_wszystko.sh
#
# Zleca 7 zadań SLURM NARAZ, w ŁAŃCUCHU ZALEŻNOŚCI
# (sbatch --dependency=afterok:<job_id>) - każde kolejne odpala się
# AUTOMATYCZNIE dopiero gdy POPRZEDNIE zakończy się SUKCESEM (exit 0), bez
# żadnej ręcznej interwencji między nimi. Jeśli którekolwiek zawiedzie, SLURM
# automatycznie ANULUJE resztę łańcucha (stan "DependencyNeverSatisfied") -
# to celowe zabezpieczenie: nie ma sensu zlecać drogiego kolejnego zadania,
# jeśli poprzednie nie przeszło. SEKWENCYJNIE (jedno na raz), żeby nie mnożyć
# jednoczesnej rezerwacji CPU-godzin i nie trafić na QOSGrpCPUMinutesLimit
# (patrz historia tego problemu w AGENTS.md).
#
# Kolejność (lokalizacje ograniczone do 4 najbardziej ekstremalnych - sodankyla,
# murmansk, quebec_city, norylsk - 2026-09-15, patrz uzasadnienie w
# slurm_pelny_przeglad.sh - koszty core-h niżej ZNACZNIE spadły względem
# poprzednich 44-lokalizacyjnych szacunków):
#   1) slurm_smoke_test.sh                  (~30 min, weryfikacja środowiska)
#   2) slurm_pelny_przeglad.sh               (pełny przegląd, 4 lok. x wszystkie 45 algorytmów - główny wynik, ~21-43 core-h, ceiling 64h)
#   3) slurm_wrazliwosc_2lok.sh              (pogłębiona wrażliwość + szum, 2 lok. [abisko+ojmiakon, niezmienione] x 14 scenariuszy x szum, ~88-131 core-h)
#   4) slurm_krok_sterowania.sh              (wrażliwość na krok sterowania, 4 lok. x WSZYSTKIE 45 algorytmów x 5 kroków, ~16 core-h, ceiling 64h)
#   5) slurm_szum_wielu_czujnikow.sh         (szum wielu czujników, 4 lok. JAWNE x 29 scenariuszy x wszystkie 45 algorytmów, ~70 core-h, ceiling 96h)
#   6) slurm_test_awarie.sh                  (odporność na awarie czujników, 1 lok. [abisko, niezmieniona], ~kilka core-h)
#   7) slurm_master_excel.sh                 (składa JEDEN Excel wyniki/Podsumowanie_MASTER.xlsx; 1 rdzeń, ~minuty;
#                                             --dependency=afterany, czyli odpala się nawet gdy któryś test padł)
#
# CELOWO WYŁĄCZONE Z ŁAŃCUCHA (2026-09-17, na życzenie użytkownika - "te różne
# transmitancje możemy chyba sobie na razie pominąć"): slurm_wrazliwosc_transmitancji.sh
# (analiza wrażliwości na niepewność transmitancji, 8 scenariuszy - najdroższy
# i najmniej priorytetowy test na tę chwilę). Odpalaj GO OSOBNO, kiedy
# faktycznie będzie potrzebny:
#   sbatch slurm/slurm_wrazliwosc_transmitancji.sh
#
# WAŻNE: ten plik uruchamiasz BEZPOŚREDNIO (`bash`), NIE przez `sbatch` - to
# zwykły skrypt powłoki, który tylko SKŁADA zadania do kolejki z zależnościami
# i od razu kończy działanie (samo liczenie leci już niezależnie w SLURM-ie,
# możesz spokojnie wylogować się zaraz po odpaleniu tego skryptu).
#
# Uruchomienie (z katalogu Benchmark/benchmark na klastrze - CWD musi być tam,
# NIE w slurm/, bo ścieżki do sbatch niżej są względem niego):
#   bash slurm/uruchom_wszystko.sh

set -euo pipefail

echo "1/7 Zlecam smoke_test..."
JOB1=$(sbatch --parsable slurm/slurm_smoke_test.sh)
echo "    -> job $JOB1"

echo "2/7 Zlecam pelny_przeglad (odpali się automatycznie po sukcesie $JOB1)..."
JOB2=$(sbatch --parsable --dependency=afterok:$JOB1 slurm/slurm_pelny_przeglad.sh)
echo "    -> job $JOB2"

echo "3/7 Zlecam wrazliwosc_2lok (odpali się automatycznie po sukcesie $JOB2)..."
JOB3=$(sbatch --parsable --dependency=afterok:$JOB2 slurm/slurm_wrazliwosc_2lok.sh)
echo "    -> job $JOB3"

echo "4/7 Zlecam krok_sterowania (odpali się automatycznie po sukcesie $JOB3)..."
JOB4=$(sbatch --parsable --dependency=afterok:$JOB3 slurm/slurm_krok_sterowania.sh)
echo "    -> job $JOB4"

echo "5/7 Zlecam szum_wielu_czujnikow (odpali się automatycznie po sukcesie $JOB4)..."
JOB5=$(sbatch --parsable --dependency=afterok:$JOB4 slurm/slurm_szum_wielu_czujnikow.sh)
echo "    -> job $JOB5"

echo "6/7 Zlecam test_awarie (odpali się automatycznie po sukcesie $JOB5)..."
JOB6=$(sbatch --parsable --dependency=afterok:$JOB5 slurm/slurm_test_awarie.sh)
echo "    -> job $JOB6"

echo "7/7 Zlecam master_excel (odpali się po ZAKOŃCZENIU $JOB6 - także jeśli któryś test padł)..."
JOB7=$(sbatch --parsable --dependency=afterany:$JOB6 slurm/slurm_master_excel.sh)
echo "    -> job $JOB7"

echo ""
echo "Wszystkie 7 zadań zlecone w łańcuchu zależności (BEZ testu transmitancji -"
echo "celowo pominięty na tę chwilę, patrz nagłówek pliku):"
echo "  $JOB1  smoke_test"
echo "  $JOB2  pelny_przeglad              (start po sukcesie $JOB1)"
echo "  $JOB3  wrazliwosc_2lok             (start po sukcesie $JOB2)"
echo "  $JOB4  krok_sterowania             (start po sukcesie $JOB3)"
echo "  $JOB5  szum_wielu_czujnikow        (start po sukcesie $JOB4)"
echo "  $JOB6  test_awarie                 (start po sukcesie $JOB5)"
echo "  $JOB7  master_excel                (start po zakończeniu $JOB6, nawet jeśli któryś test padł)"
echo ""
echo "Dalej nic nie musisz robić ręcznie - leci samo, jedno po drugim."
echo "Monitoruj: squeue -u \$USER"
echo "Jeśli któreś zadanie w łańcuchu zawiedzie, kolejne NIE odpalą się"
echo "(status w squeue: DependencyNeverSatisfied) - sprawdź log tego, które padło."
echo ""
echo "Po zakończeniu łańcucha gotowy jest JEDEN zbiorczy Excel: wyniki/Podsumowanie_MASTER.xlsx"
echo "(plus szczegółowy Excel głównego przeglądu: wyniki/przeglad_wielu_lokalizacji/Podsumowanie_wynikow.xlsx)."
