#!/bin/bash
# slurm_krok_sterowania.sh
#
# Wrażliwość na krok sterowania (test_wrazliwosc_kroku_sterowania.py) w PEŁNEJ
# skali: wszystkie 44 lokalizacje x WSZYSTKIE 42 algorytmy (domyślna lista rozszerzona
# 2026-09-03 z curatorowanej 6-tki na pełny rejestr, na życzenie użytkownika - "żeby
# całość była bardziej miarodajna, nie tylko wybrane") x 5 kroków sterowania
# (1/10/60/300/600s) x okno 30 dni = 7700 zadań.
#
# KOSZT: zmierzone lokalnie (smoke test w ramach uruchom_wszystkie_testy.py,
# 1 lokalizacja x 3 algorytmy [bez MPC] x 2 kroki, okno 3 dni) - ~0.13 core-min/zadanie.
# Ekstrapolacja do pełnej skali (okno 30 dni, 10x) x 7700 zadań (~6x poprzedniej
# liczby po rozszerzeniu z 6 na 42 algorytmy i z 43 na 44 lokalizacji) ≈ 167 core-h
# szacunkowo - MPC nie zmierzone empirycznie osobno, ale QP na 8 zmiennych to
# pojedyncze ms/rozwiązanie, więc rząd wielkości powinien zostać podobny.
# --cpus-per-task=64 / --time=6:00:00 = 384 core-h - bezpieczny zapas (64
# rdzenie zamiast 48 na życzenie użytkownika 2026-09-07 - ta sama praca,
# krótszy czas ściany; wcześniej 2:00:00/96 core-h - ZA MAŁO na tę skalę).
#
# WAŻNE: zlecaj TYLKO przez `sbatch`, NIGDY przez `sh`/`bash` bezpośrednio.
#
# Uruchomienie (z katalogu Benchmark/benchmark na klastrze):
#   sbatch slurm/slurm_krok_sterowania.sh

#SBATCH -J szyna_krok_sterowania
#SBATCH --account=hpc-wikjan2416-1787599067
#SBATCH -N 1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=64
#SBATCH --mem=500G
#SBATCH --time=01:00:00
#SBATCH -p lem-cpu
#SBATCH --output=szyna_krok_sterowania_%j.log
# --time ZMNIEJSZONE 2026-09-15 (lokalizacje ograniczone do 4, patrz
# SZYNA_LOKALIZACJE niżej) - 64 rdzenie x 1h = 64 CPU-h ceiling, realny koszt
# szacunkowo ~16 core-h (167 core-h oryginalne x 4/44 lok. x 45/42 alg.).

set -euo pipefail

SCRIPT_DIR="$SLURM_SUBMIT_DIR"
cd "$SCRIPT_DIR"

if [ ! -d "$HOME/szyna_venv" ]; then
    python3 -m venv "$HOME/szyna_venv"
fi
source "$HOME/szyna_venv/bin/activate"
pip install --upgrade pip
pip install -r "$SCRIPT_DIR/requirements.txt"

# Celowo NIE ustawiamy SZYNA_ALGORYTMY_KROK/SZYNA_MAX_DNI - WSZYSTKIE algorytmy
# z rejestru, okno 30 dni. SZYNA_LOKALIZACJE ograniczone do 4 (2026-09-15, jak
# w slurm_pelny_przeglad.sh - patrz tam pełne uzasadnienie wyboru).
export SZYNA_LOKALIZACJE="sodankyla_60min_2025,murmansk_60min_2025,quebec_city_60min_2025,norylsk_60min_2025"
export SZYNA_FOLDER_WYNIKOW_KROK="$SCRIPT_DIR/wyniki/wrazliwosc_kroku"

python testy/test_wrazliwosc_kroku_sterowania.py
