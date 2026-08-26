#!/bin/bash
# slurm_pelny_przeglad.sh
#
# PEŁNY przegląd (wszystkie lokalizacje x wszystkie algorytmy, PEŁNY zakres dat
# każdego pliku pogodowego - MAX_DNI_NA_LOKALIZACJE=None) na klastrze WCSS.
#
# Uruchamiaj DOPIERO po udanym slurm_smoke_test.sh - upewnij się w jego logu,
# że pojawiła się linia "Wykryto limit rdzeni ze zmiennej
# SLURM_CPUS_PER_TASK=... -> N procesów" z N zgodnym z --cpus-per-task poniżej
# (patrz uzasadnienie w nagłówku test_wszystkie_rownolegle.py: to jedyny
# niezawodny sposób wykrycia przydzielonych rdzeni na klastrze).
#
# Partycja: lem-cpu (meta-partycja - SLURM sam kieruje do lem-cpu-short/normal
# na podstawie zadeklarowanego --time, patrz
# https://man.e-science.pl/pl/kdm/slurm/partycje-slurm). Węzły lem-cpu mają do
# 128 rdzeni i 1430G RAM.
#
# --mem=1200G: JEDNO zadanie na PEŁNYM zakresie dat buduje w pamięci listę ~13
# mln słowników (historia) przed konwersją do tabeli - szczytowo ok. 7GB na
# zadanie. Przy 128 równoległych procesach (--cpus-per-task poniżej) to daje
# szczytowo do ~900GB, stąd 1200G z zapasem (node ma 1430G limit). Dla porównania:
# lokalnie na 16GB RAM zadania na PEŁNYM zakresie dat wywoływały MemoryError
# już przy 3 równoległych procesach (3 x 7GB > 16GB) - to jest właśnie ten
# problem, który to zadanie na klastrze rozwiązuje.
#
# Przed odpaleniem: sprawdź dostępne godziny CPU usługi (service-balance --check-cpu)
# i dostępność węzłów (check-partitions) - patrz
# https://man.e-science.pl/pl/kdm/rejestr_zuzycia_zasobow.
#
# Uruchomienie (z katalogu Benchmark/benchmark na klastrze):
#   sbatch slurm_pelny_przeglad.sh

#SBATCH -J szyna_pelny_przeglad
#SBATCH -N 1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=128
#SBATCH --mem=1200G
#SBATCH --time=2-00:00:00
#SBATCH -p lem-cpu
#SBATCH --output=szyna_pelny_%j.log

set -euo pipefail

module load python 2>/dev/null || true
if [ ! -d "$HOME/szyna_venv" ]; then
    python3 -m venv "$HOME/szyna_venv"
    source "$HOME/szyna_venv/bin/activate"
    pip install --upgrade pip
    pip install -r "$SLURM_SUBMIT_DIR/requirements.txt"
else
    source "$HOME/szyna_venv/bin/activate"
fi

cd "$SLURM_SUBMIT_DIR"

# Celowo NIE ustawiamy SZYNA_MAX_DNI/SZYNA_LOKALIZACJE/SZYNA_ALGORYTMY -
# domyślnie: pełny zakres dat, wszystkie lokalizacje, wszystkie algorytmy.
# SZYNA_LICZBA_WATKOW też nie jest konieczne - autodetekcja złapie
# SLURM_CPUS_PER_TASK ustawione przez --cpus-per-task powyżej.
export SZYNA_FOLDER_WYNIKOW="$SLURM_SUBMIT_DIR/wyniki/przeglad_wielu_lokalizacji"

python test_wszystkie_rownolegle.py
