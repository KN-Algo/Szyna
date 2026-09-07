#!/bin/bash
# wznow_od_transmitancji.sh
#
# WZNOWIENIE łańcucha zadań (patrz uruchom_wszystko.sh) OD KROKU 3
# (wrazliwosc_transmitancji) - do użycia, gdy kroki 1-2 (smoke_test,
# pelny_przeglad) już się skończyły sukcesem, ale łańcuch utknął/padł na
# wrazliwosc_transmitancji (dlatego kroki 4-7 nigdy nie wystartowały -
# --dependency=afterok wiąże się z KONKRETNYM, już nieistniejącym job ID,
# więc samo ponowne zlecenie samej wrazliwosc_transmitancji NIE wznowi
# automatycznie reszty - stąd ten osobny skrypt).
#
# BEZPIECZNE do wielokrotnego odpalania: wszystkie te skrypty mają wbudowane
# wznawianie z checkpointu (SZYNA_WZNOW=1 domyślnie - PRZEGLAD_ZBIORCZY.csv/
# odpowiedniki zapisywane po KAŻDYM zadaniu) - ponowne zlecenie
# wrazliwosc_transmitancji NIE liczy wszystkiego od zera, tylko dokańcza
# brakujące (lokalizacja, algorytm) w KAŻDYM z 8 scenariuszy z osobna.
#
# PRZED użyciem: sprawdź `squeue -u $USER` - jeśli wrazliwosc_transmitancji
# (job z --array=0-7) WCIĄŻ tam jest ze statusem R/PD, NIC NIE RÓB, łańcuch
# wznowi się sam automatycznie po jej sukcesie. Ten skrypt jest na wypadek,
# gdy zniknęła z kolejki (skończona/padła/anulowana), a kroki 4-7 NIE
# wystartowały same.
#
# Uruchomienie (z katalogu Benchmark/benchmark na klastrze - CWD musi być tam,
# NIE w slurm/, bo ścieżki do sbatch niżej są względem niego):
#   bash slurm/wznow_od_transmitancji.sh

set -euo pipefail

echo "3/7 Zlecam wrazliwosc_transmitancji (wznowienie z checkpointu, jeśli częściowo policzona)..."
JOB3=$(sbatch --parsable slurm/slurm_wrazliwosc_transmitancji.sh)
echo "    -> job $JOB3"

echo "4/7 Zlecam wrazliwosc_2lok (odpali się automatycznie po sukcesie $JOB3)..."
JOB4=$(sbatch --parsable --dependency=afterok:$JOB3 slurm/slurm_wrazliwosc_2lok.sh)
echo "    -> job $JOB4"

echo "5/7 Zlecam krok_sterowania (odpali się automatycznie po sukcesie $JOB4)..."
JOB5=$(sbatch --parsable --dependency=afterok:$JOB4 slurm/slurm_krok_sterowania.sh)
echo "    -> job $JOB5"

echo "6/7 Zlecam szum_wielu_czujnikow (odpali się automatycznie po sukcesie $JOB5)..."
JOB6=$(sbatch --parsable --dependency=afterok:$JOB5 slurm/slurm_szum_wielu_czujnikow.sh)
echo "    -> job $JOB6"

echo "7/7 Zlecam test_awarie (odpali się automatycznie po sukcesie $JOB6)..."
JOB7=$(sbatch --parsable --dependency=afterok:$JOB6 slurm/slurm_test_awarie.sh)
echo "    -> job $JOB7"

echo ""
echo "Wznowione 5 zadań (3-7) w łańcuchu zależności:"
echo "  $JOB3  wrazliwosc_transmitancji    (wznowienie z checkpointu)"
echo "  $JOB4  wrazliwosc_2lok             (start po sukcesie $JOB3)"
echo "  $JOB5  krok_sterowania             (start po sukcesie $JOB4)"
echo "  $JOB6  szum_wielu_czujnikow        (start po sukcesie $JOB5)"
echo "  $JOB7  test_awarie                 (start po sukcesie $JOB6)"
echo ""
echo "Monitoruj: squeue -u \$USER"
