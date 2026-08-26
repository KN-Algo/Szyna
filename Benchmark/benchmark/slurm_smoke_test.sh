#!/bin/bash
# slurm_smoke_test.sh
#
# MAŁY test przed pełnym przeglądem (43 lokalizacje x 23 algorytmy) - sprawdza
# na klastrze WCSS (https://man.e-science.pl/pl/kdm/slurm/gpu,
# https://man.e-science.pl/pl/kdm/slurm/partycje-slurm):
#   1) że środowisko Pythona (venv + pakiety) się stawia,
#   2) że test_wszystkie_rownolegle.py FAKTYCZNIE wykrywa liczbę rdzeni ze
#      SLURM_CPUS_PER_TASK (patrz log: "Wykryto limit rdzeni ze zmiennej
#      SLURM_CPUS_PER_TASK=... -> N procesów") - to jest dowód, że
#      wielowątkowość naprawdę działa, zanim zleci się kosztowne pełne zadanie,
#   3) że symulacja na 2 lokalizacjach/kilku algorytmach kończy się bez błędu.
#
# Uruchomienie (z katalogu Benchmark/benchmark na klastrze):
#   sbatch slurm_smoke_test.sh

#SBATCH -J szyna_smoke_test
#SBATCH -N 1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=8
#SBATCH --mem=16G
#SBATCH --time=0-00:30:00
#SBATCH -p lem-cpu-short
#SBATCH --output=szyna_smoke_%j.log

set -euo pipefail

# --- Środowisko Pythona: sprawdź `module avail python` po zalogowaniu i
# dostosuj nazwę modułu jeśli jest dostępny - poniższy venv działa niezależnie
# od tego, czy taki moduł istnieje.
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

# Ograniczony zakres - tylko test poprawności/wielowątkowości, nie wyniki do analizy.
export SZYNA_MAX_DNI=1
export SZYNA_LOKALIZACJE="abisko_60min_2021,abisko_60min_2022"
export SZYNA_ALGORYTMY="algorytm_z_normy,risk_function,risk_function_pid,fuzzy_ryzyko_1_opad"
export SZYNA_FOLDER_WYNIKOW="$SLURM_SUBMIT_DIR/wyniki/smoke_test_klaster"

python test_wszystkie_rownolegle.py
