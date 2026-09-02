#!/bin/bash
# uruchom_wszystko.sh
#
# Zleca WSZYSTKIE 7 zadań SLURM NARAZ, w ŁAŃCUCHU ZALEŻNOŚCI
# (sbatch --dependency=afterok:<job_id>) - każde kolejne odpala się
# AUTOMATYCZNIE dopiero gdy POPRZEDNIE zakończy się SUKCESEM (exit 0), bez
# żadnej ręcznej interwencji między nimi. Jeśli którekolwiek zawiedzie, SLURM
# automatycznie ANULUJE resztę łańcucha (stan "DependencyNeverSatisfied") -
# to celowe zabezpieczenie: nie ma sensu zlecać drogiego kolejnego zadania,
# jeśli poprzednie nie przeszło. SEKWENCYJNIE (jedno na raz), żeby nie mnożyć
# jednoczesnej rezerwacji CPU-godzin i nie trafić na QOSGrpCPUMinutesLimit
# (patrz historia tego problemu w AGENTS.md).
#
# Kolejność:
#   1) slurm_smoke_test.sh                  (~30 min, weryfikacja środowiska)
#   2) slurm_pelny_przeglad.sh               (pełny przegląd, 43 lok. x wszystkie algorytmy - główny wynik, ~576 core-h)
#   3) slurm_wrazliwosc_transmitancji.sh     (wrażliwość transmitancji, 43 lok. x 8 scenariuszy, do ~4608 core-h)
#   4) slurm_wrazliwosc_2lok.sh              (pogłębiona wrażliwość + szum, 2 lok. x 14 scenariuszy x szum, ~60-90 core-h)
#   5) slurm_krok_sterowania.sh              (wrażliwość na krok sterowania, 43 lok. x 3 algorytmy x 5 kroków, ~14 core-h)
#   6) slurm_szum_wielu_czujnikow.sh         (szum wielu czujników, 10 lok. x 29 scenariuszy x wszystkie algorytmy, ~135 core-h)
#   7) slurm_test_awarie.sh                  (odporność na awarie czujników, ~32 core-h)
#
# WAŻNE: ten plik uruchamiasz BEZPOŚREDNIO (`bash`), NIE przez `sbatch` - to
# zwykły skrypt powłoki, który tylko SKŁADA 7 zadań do kolejki z zależnościami
# i od razu kończy działanie (samo liczenie leci już niezależnie w SLURM-ie,
# możesz spokojnie wylogować się zaraz po odpaleniu tego skryptu).
#
# Uruchomienie (z katalogu Benchmark/benchmark na klastrze):
#   bash uruchom_wszystko.sh

set -euo pipefail

echo "1/7 Zlecam smoke_test..."
JOB1=$(sbatch --parsable slurm_smoke_test.sh)
echo "    -> job $JOB1"

echo "2/7 Zlecam pelny_przeglad (odpali się automatycznie po sukcesie $JOB1)..."
JOB2=$(sbatch --parsable --dependency=afterok:$JOB1 slurm_pelny_przeglad.sh)
echo "    -> job $JOB2"

echo "3/7 Zlecam wrazliwosc_transmitancji (odpali się automatycznie po sukcesie $JOB2)..."
JOB3=$(sbatch --parsable --dependency=afterok:$JOB2 slurm_wrazliwosc_transmitancji.sh)
echo "    -> job $JOB3"

echo "4/7 Zlecam wrazliwosc_2lok (odpali się automatycznie po sukcesie $JOB3)..."
JOB4=$(sbatch --parsable --dependency=afterok:$JOB3 slurm_wrazliwosc_2lok.sh)
echo "    -> job $JOB4"

echo "5/7 Zlecam krok_sterowania (odpali się automatycznie po sukcesie $JOB4)..."
JOB5=$(sbatch --parsable --dependency=afterok:$JOB4 slurm_krok_sterowania.sh)
echo "    -> job $JOB5"

echo "6/7 Zlecam szum_wielu_czujnikow (odpali się automatycznie po sukcesie $JOB5)..."
JOB6=$(sbatch --parsable --dependency=afterok:$JOB5 slurm_szum_wielu_czujnikow.sh)
echo "    -> job $JOB6"

echo "7/7 Zlecam test_awarie (odpali się automatycznie po sukcesie $JOB6)..."
JOB7=$(sbatch --parsable --dependency=afterok:$JOB6 slurm_test_awarie.sh)
echo "    -> job $JOB7"

echo ""
echo "Wszystkie 7 zadań zlecone w łańcuchu zależności:"
echo "  $JOB1  smoke_test"
echo "  $JOB2  pelny_przeglad              (start po sukcesie $JOB1)"
echo "  $JOB3  wrazliwosc_transmitancji    (start po sukcesie $JOB2)"
echo "  $JOB4  wrazliwosc_2lok             (start po sukcesie $JOB3)"
echo "  $JOB5  krok_sterowania             (start po sukcesie $JOB4)"
echo "  $JOB6  szum_wielu_czujnikow        (start po sukcesie $JOB5)"
echo "  $JOB7  test_awarie                 (start po sukcesie $JOB6)"
echo ""
echo "Dalej nic nie musisz robić ręcznie - leci samo, jedno po drugim."
echo "Monitoruj: squeue -u \$USER"
echo "Jeśli któreś zadanie w łańcuchu zawiedzie, kolejne NIE odpalą się"
echo "(status w squeue: DependencyNeverSatisfied) - sprawdź log tego, które padło."
echo ""
echo "Po zakończeniu WSZYSTKICH zadań, zbuduj skonsolidowany Excel lokalnie"
echo "(scp/rsync folder wyniki/ z klastra) albo bezpośrednio na klastrze:"
echo "  python generuj_excel_master.py"
