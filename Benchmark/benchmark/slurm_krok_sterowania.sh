#!/bin/bash
# slurm_krok_sterowania.sh
#
# Wrażliwość na krok sterowania (test_wrazliwosc_kroku_sterowania.py) w PEŁNEJ
# skali: wszystkie 43 lokalizacje x 3 domyślne algorytmy (fuzzy_ryzyko_2v2_opad,
# fuzzy_normy_2v2, nauka_kary_opad - zwycięzcy wstępnego rankingu, patrz
# AGENTS.md) x 5 kroków sterowania (1/10/60/300/600s) x okno 30 dni = 645 zadań.
#
# KOSZT: zmierzone lokalnie (smoke test w ramach uruchom_wszystkie_testy.py,
# 1 lokalizacja x 3 algorytmy x 2 kroki, okno 3 dni) - ~0.13 core-min/zadanie.
# Ekstrapolacja do pełnej skali (okno 30 dni, 10x) x 645 zadań ≈ 14 core-h
# szacunkowo. --cpus-per-task=48 / --time=2:00:00 = 96 core-h - bezpieczny zapas.
#
# WAŻNE: zlecaj TYLKO przez `sbatch`, NIGDY przez `sh`/`bash` bezpośrednio.
#
# Uruchomienie (z katalogu Benchmark/benchmark na klastrze):
#   sbatch slurm_krok_sterowania.sh

#SBATCH -J szyna_krok_sterowania
#SBATCH --account=hpc-wikjan2416-1787599067
#SBATCH -N 1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=48
#SBATCH --mem=500G
#SBATCH --time=2:00:00
#SBATCH -p lem-cpu
#SBATCH --output=szyna_krok_sterowania_%j.log

set -euo pipefail

SCRIPT_DIR="$SLURM_SUBMIT_DIR"
cd "$SCRIPT_DIR"

if [ ! -d "$HOME/szyna_venv" ]; then
    python3 -m venv "$HOME/szyna_venv"
fi
source "$HOME/szyna_venv/bin/activate"
pip install --upgrade pip
pip install -r "$SCRIPT_DIR/requirements.txt"

# Celowo NIE ustawiamy SZYNA_ALGORYTMY_KROK/SZYNA_LOKALIZACJE/SZYNA_MAX_DNI -
# domyślnie: 3 zwycięzcy rankingu, wszystkie 43 lokalizacje, okno 30 dni.
export SZYNA_FOLDER_WYNIKOW_KROK="$SCRIPT_DIR/wyniki/wrazliwosc_kroku"

python test_wrazliwosc_kroku_sterowania.py
