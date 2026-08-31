#!/bin/bash
# slurm_test_awarie.sh
#
# Test odporności wszystkich algorytmów na awarie czujników - patrz
# test_awarie_czujnikow.py (7 scenariuszy x wszystkie algorytmy, 1 lokalizacja,
# domyślnie 10 dni - szybkie dzięki krokowi symulacji 10s).
#
# WAŻNE: zlecaj TYLKO przez `sbatch`, NIGDY przez `sh`/`bash` bezpośrednio.
#
# Uruchomienie (z katalogu Benchmark/benchmark na klastrze):
#   sbatch slurm_test_awarie.sh

#SBATCH -J szyna_test_awarie
#SBATCH --account=hpc-wikjan2416-1787599067
#SBATCH -N 1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=16
#SBATCH --mem=100G
#SBATCH --time=0-02:00:00
#SBATCH -p lem-cpu-short
#SBATCH --output=szyna_test_awarie_%j.log

set -euo pipefail

SCRIPT_DIR="$SLURM_SUBMIT_DIR"
cd "$SCRIPT_DIR"

if [ ! -d "$HOME/szyna_venv" ]; then
    python3 -m venv "$HOME/szyna_venv"
fi
source "$HOME/szyna_venv/bin/activate"
pip install --upgrade pip
pip install -r "$SCRIPT_DIR/requirements.txt"

python test_awarie_czujnikow.py
