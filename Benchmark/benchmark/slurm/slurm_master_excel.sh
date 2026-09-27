#!/bin/bash
# slurm_master_excel.sh
#
# OSTATNI element łańcucha (patrz uruchom_wszystko.sh): składa JEDEN
# skonsolidowany Excel wyniki/Podsumowanie_MASTER.xlsx ze wszystkich
# dotychczasowych wyników (podsumowanie + pełne dane każdego testu w osobnych
# zakładkach) - patrz generatory_excel/generuj_excel_master.py. Lekkie (1 rdzeń,
# minuty), więc rezerwacja ~0.25 CPU-h.
#
# Zlecany z `--dependency=afterany` (NIE afterok): ma się wykonać także wtedy,
# gdy któryś z wcześniejszych testów padł albo wyczerpał limit czasu/CPU-h -
# generator pomija bez błędu testy bez wyników i buduje Excel z tego, co jest.
#
# Uruchomienie samodzielne (z katalogu Benchmark/benchmark na klastrze):
#   sbatch slurm/slurm_master_excel.sh

#SBATCH -J szyna_master_excel
#SBATCH --account=hpc-wikjan2416-1787599067
#SBATCH -N 1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=1
#SBATCH --mem=8G
#SBATCH --time=0-00:15:00
#SBATCH -p lem-cpu-short
#SBATCH --output=szyna_master_excel_%j.log

set -euo pipefail

SCRIPT_DIR="$SLURM_SUBMIT_DIR"
cd "$SCRIPT_DIR"

if [ ! -d "$HOME/szyna_venv" ]; then
    python3 -m venv "$HOME/szyna_venv"
fi
source "$HOME/szyna_venv/bin/activate"
pip install --upgrade pip
pip install -r "$SCRIPT_DIR/requirements.txt"

python generatory_excel/generuj_excel_master.py
