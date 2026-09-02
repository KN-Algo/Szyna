#!/bin/bash
# slurm_szum_wielu_czujnikow.sh
#
# Pełny test odporności na szum pomiarowy (test_szum_wielu_czujnikow.py) -
# 10 losowych lokalizacji x wszystkie 29 algorytmów x 29 scenariuszy szumu
# (7 czujników x 4 poziomy + brak_awarii) = 8410 zadań.
#
# KOSZT: zmierzone lokalnie (smoke test, 2 lokalizacje x 2 algorytmy, okno
# 2-dniowe) - ~0.19 core-min/zadanie. Przy domyślnym oknie 10-dniowym (5x) to
# ekstrapoluje się do ~0.97 core-min/zadanie, razem ~8410 zadań = ~135 core-h
# szacunkowo. --cpus-per-task=48 / --time=6:00:00 = 288 core-h - bezpieczny
# zapas ponad szacunek.
#
# WAŻNE: zlecaj TYLKO przez `sbatch`, NIGDY przez `sh`/`bash` bezpośrednio.
#
# Uruchomienie (z katalogu Benchmark/benchmark na klastrze):
#   sbatch slurm_szum_wielu_czujnikow.sh

#SBATCH -J szyna_szum_czujnikow
#SBATCH --account=hpc-wikjan2416-1787599067
#SBATCH -N 1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=48
#SBATCH --mem=500G
#SBATCH --time=6:00:00
#SBATCH -p lem-cpu
#SBATCH --output=szyna_szum_czujnikow_%j.log

set -euo pipefail

SCRIPT_DIR="$SLURM_SUBMIT_DIR"
cd "$SCRIPT_DIR"

if [ ! -d "$HOME/szyna_venv" ]; then
    python3 -m venv "$HOME/szyna_venv"
fi
source "$HOME/szyna_venv/bin/activate"
pip install --upgrade pip
pip install -r "$SCRIPT_DIR/requirements.txt"

# Celowo NIE ustawiamy SZYNA_LICZBA_LOKALIZACJI_SZUM/SZYNA_MAX_DNI_SZUM -
# domyślnie: 10 losowych lokalizacji (seed stały, powtarzalny), okno 10 dni.
export SZYNA_FOLDER_WYNIKOW_SZUM="$SCRIPT_DIR/wyniki/szum_wielu_czujnikow"

python test_szum_wielu_czujnikow.py
