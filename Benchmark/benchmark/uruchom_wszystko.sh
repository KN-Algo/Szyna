#!/bin/bash
# uruchom_wszystko.sh
#
# Zleca WSZYSTKIE 4 zadania SLURM NARAZ, w ŁAŃCUCHU ZALEŻNOŚCI
# (sbatch --dependency=afterok:<job_id>) - każde kolejne odpala się
# AUTOMATYCZNIE dopiero gdy POPRZEDNIE zakończy się SUKCESEM (exit 0), bez
# żadnej ręcznej interwencji między nimi. Jeśli którekolwiek zawiedzie, SLURM
# automatycznie ANULUJE resztę łańcucha (stan "DependencyNeverSatisfied") -
# to celowe zabezpieczenie: nie ma sensu zlecać drogiego pełnego przeglądu,
# jeśli nawet smoke test nie przeszedł.
#
# Kolejność (sekwencyjna - jedno na raz, żeby nie mnożyć jednoczesnej
# rezerwacji CPU-godzin i nie trafić znów na QOSGrpCPUMinutesLimit):
#   1) slurm_smoke_test.sh                  (~30 min, weryfikacja środowiska)
#   2) slurm_pelny_przeglad.sh               (pełny przegląd, główny wynik)
#   3) slurm_wrazliwosc_transmitancji.sh     (analiza wrażliwości, 8 scenariuszy)
#   4) slurm_test_awarie.sh                  (odporność na awarie czujników)
#
# WAŻNE: ten plik uruchamiasz BEZPOŚREDNIO (`bash`), NIE przez `sbatch` - to
# zwykły skrypt powłoki, który tylko SKŁADA 4 zadania do kolejki z zależnościami
# i od razu kończy działanie (samo liczenie leci już niezależnie w SLURM-ie,
# możesz spokojnie wylogować się zaraz po odpaleniu tego skryptu).
#
# Uruchomienie (z katalogu Benchmark/benchmark na klastrze):
#   bash uruchom_wszystko.sh

set -euo pipefail

echo "1/4 Zlecam smoke_test..."
JOB1=$(sbatch --parsable slurm_smoke_test.sh)
echo "    -> job $JOB1"

echo "2/4 Zlecam pelny_przeglad (odpali się automatycznie po sukcesie $JOB1)..."
JOB2=$(sbatch --parsable --dependency=afterok:$JOB1 slurm_pelny_przeglad.sh)
echo "    -> job $JOB2"

echo "3/4 Zlecam wrazliwosc_transmitancji (odpali się automatycznie po sukcesie $JOB2)..."
JOB3=$(sbatch --parsable --dependency=afterok:$JOB2 slurm_wrazliwosc_transmitancji.sh)
echo "    -> job $JOB3"

echo "4/4 Zlecam test_awarie (odpali się automatycznie po sukcesie $JOB3)..."
JOB4=$(sbatch --parsable --dependency=afterok:$JOB3 slurm_test_awarie.sh)
echo "    -> job $JOB4"

echo ""
echo "Wszystkie 4 zadania zlecone w łańcuchu zależności:"
echo "  $JOB1  smoke_test"
echo "  $JOB2  pelny_przeglad              (start po sukcesie $JOB1)"
echo "  $JOB3  wrazliwosc_transmitancji    (start po sukcesie $JOB2)"
echo "  $JOB4  test_awarie                 (start po sukcesie $JOB3)"
echo ""
echo "Dalej nic nie musisz robić ręcznie - leci samo, jedno po drugim."
echo "Monitoruj: squeue -u \$USER"
echo "Jeśli któreś zadanie w łańcuchu zawiedzie, kolejne NIE odpalą się"
echo "(status w squeue: DependencyNeverSatisfied) - sprawdź log tego, które padło."
