#!/bin/bash
# slurm_szum_wielu_czujnikow.sh
#
# Pełny test odporności na szum pomiarowy (test_szum_wielu_czujnikow.py) -
# 10 losowych lokalizacji (z puli 44, seed stały) x wszystkie 42 algorytmy
# (rejestr urósł z 29 do 35 - dodane 3 warianty MPC + 2 algorytmy inspirowane
# literaturą, 2026-09-03) x 29 scenariuszy szumu (7 czujników x 4 poziomy +
# brak_awarii) = 10150 zadań.
#
# KOSZT: zmierzone lokalnie (smoke test, 2 lokalizacje x 2 algorytmy, okno
# 2-dniowe) - ~0.19 core-min/zadanie. Przy domyślnym oknie 10-dniowym (5x) to
# ekstrapoluje się do ~0.97 core-min/zadanie, razem ~10150 zadań = ~164 core-h
# szacunkowo. --cpus-per-task=64 / --time=6:00:00 = 384 core-h - bezpieczny
# zapas ponad szacunek (64 rdzenie zamiast 48 na życzenie użytkownika
# 2026-09-07 - ta sama praca, krótszy czas ściany).
#
# WAŻNE: zlecaj TYLKO przez `sbatch`, NIGDY przez `sh`/`bash` bezpośrednio.
#
# Uruchomienie (z katalogu Benchmark/benchmark na klastrze):
#   sbatch slurm/slurm_szum_wielu_czujnikow.sh

#SBATCH -J szyna_szum_czujnikow
#SBATCH --account=hpc-wikjan2416-1787599067
#SBATCH -N 1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=64
#SBATCH --mem=500G
#SBATCH --time=01:30:00
#SBATCH -p lem-cpu
#SBATCH --output=szyna_szum_czujnikow_%j.log
# --time ZMNIEJSZONE 2026-09-15 (lokalizacje ograniczone do 4 JAWNE, zamiast
# 10 losowych - patrz SZYNA_LOKALIZACJE_SZUM niżej) - 64 rdzenie x 1.5h = 96
# CPU-h ceiling, realny koszt szacunkowo ~70 core-h (164 core-h oryginalne x
# 4/10 lok. x 45/42 alg.).

set -euo pipefail

SCRIPT_DIR="$SLURM_SUBMIT_DIR"
cd "$SCRIPT_DIR"

if [ ! -d "$HOME/szyna_venv" ]; then
    python3 -m venv "$HOME/szyna_venv"
fi
source "$HOME/szyna_venv/bin/activate"
pip install --upgrade pip
pip install -r "$SCRIPT_DIR/requirements.txt"

# Celowo NIE ustawiamy SZYNA_MAX_DNI_SZUM - okno 10 dni. SZYNA_LOKALIZACJE_SZUM
# ustawione na 4 JAWNE lokalizacje (2026-09-15, zamiast 10 losowych - jak w
# slurm_pelny_przeglad.sh, patrz tam pełne uzasadnienie wyboru) - wyłącza
# losowanie w test_szum_wielu_czujnikow.py.
export SZYNA_LOKALIZACJE_SZUM="sodankyla_60min_2025,murmansk_60min_2025,quebec_city_60min_2025,norylsk_60min_2025"
export SZYNA_FOLDER_WYNIKOW_SZUM="$SCRIPT_DIR/wyniki/szum_wielu_czujnikow"

python testy/test_szum_wielu_czujnikow.py
