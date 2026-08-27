#!/bin/bash
# slurm_wrazliwosc_transmitancji.sh
#
# ANALIZA WRAŻLIWOŚCI na niepewność modelu obiektu (transmitancja GRZANIA,
# SOPDT K/T1/T2/L - patrz symulacja_fizyczna.przygotuj_modele_stanowe): PEŁNY
# przegląd (43 lokalizacje x 23 algorytmy, pełny zakres dat) powtórzony dla 8
# scenariuszy, w których PRAWDZIWY symulowany obiekt (nie założenia żadnego
# algorytmu) ma zaburzone parametry względem nominalnych:
#
#   0) nominal        - bez zaburzenia (referencja/baseline)
#   1) K+5%           - wzmocnienie grzałki +5%
#   2) K+10%
#   3) K+15%
#   4) T1+5%          - pierwsza stała czasowa +5%
#   5) T1+10%
#   6) T1+15%
#   7) K+10% i T1+10% JEDNOCZEŚNIE (mieszanie parametrów)
#
# Sens: algorytmy ADAPTACYJNE (autotest + cyfrowy bliźniak) same identyfikują
# PRAWDZIWY (zaburzony) obiekt z pomiarów, więc powinny się do niego
# dostroić - algorytmy NIEADAPTACYJNE (np. norma_pid, ze stałymi SIMC
# policzonymi OFFLINE z nominalnych parametrów) NIE wiedzą o zaburzeniu i będą
# działać na niedopasowanych nastawach. To jest właśnie to, co ta analiza ma
# pokazać: która strategia (adaptacyjna vs nie) jest odporniejsza na
# niepewność/dryf parametrów rzeczywistego obiektu.
#
# KOSZT: to jest 8x pełny przegląd (patrz slurm_pelny_przeglad.sh) - upewnij
# się, że masz na to wystarczający budżet CPU-godzin (service-balance) PRZED
# zleceniem całej tablicy zadań na raz. Każdy element tablicy to osobne
# zadanie SLURM z WŁASNYM budżetem czasu/rdzeni - kolejkują się niezależnie,
# nie muszą liczyć się jednocześnie.
#
# Wyniki każdego scenariusza lądują w OSOBNYM podfolderze
# wyniki/wrazliwosc_transmitancji/<scenariusz>/ (własny PRZEGLAD_ZBIORCZY.csv +
# Podsumowanie_wynikow.xlsx) - kolumna 'scenariusz'/'perturb_*_pct' w każdym
# CSV pozwala je później bezpiecznie scalić w jedną analizę porównawczą.
#
# WAŻNE: zlecaj TYLKO przez `sbatch` (kolejka SLURM), NIGDY przez `sh`/`bash`
# bezpośrednio w terminalu.
#
# Uruchomienie (z katalogu Benchmark/benchmark na klastrze):
#   sbatch slurm_wrazliwosc_transmitancji.sh
# Podgląd wybranego scenariusza osobno (np. tylko K+10%, indeks 2):
#   sbatch --array=2 slurm_wrazliwosc_transmitancji.sh

#SBATCH -J szyna_wrazliwosc
#SBATCH --account=hpc-wikjan2416-1787599067
#SBATCH -N 1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=48
#SBATCH --mem=1000G
#SBATCH --time=2-16:00:00
#SBATCH -p lem-cpu
#SBATCH --array=0-7
#SBATCH --output=szyna_wrazliwosc_%A_%a.log

set -euo pipefail

SCRIPT_DIR="$SLURM_SUBMIT_DIR"
cd "$SCRIPT_DIR"

if [ ! -d "$HOME/szyna_venv" ]; then
    python3 -m venv "$HOME/szyna_venv"
fi
source "$HOME/szyna_venv/bin/activate"
pip install --upgrade pip
pip install -r "$SCRIPT_DIR/requirements.txt"

# Mapowanie indeksu tablicy SLURM (SLURM_ARRAY_TASK_ID, 0-7) na konkretny
# scenariusz zaburzenia - patrz opis scenariuszy w nagłówku pliku.
case "$SLURM_ARRAY_TASK_ID" in
    0) export SZYNA_SCENARIUSZ="nominal";    export SZYNA_PERTURB_K=0;  export SZYNA_PERTURB_T1=0 ;;
    1) export SZYNA_SCENARIUSZ="K_plus5";    export SZYNA_PERTURB_K=5;  export SZYNA_PERTURB_T1=0 ;;
    2) export SZYNA_SCENARIUSZ="K_plus10";   export SZYNA_PERTURB_K=10; export SZYNA_PERTURB_T1=0 ;;
    3) export SZYNA_SCENARIUSZ="K_plus15";   export SZYNA_PERTURB_K=15; export SZYNA_PERTURB_T1=0 ;;
    4) export SZYNA_SCENARIUSZ="T1_plus5";   export SZYNA_PERTURB_K=0;  export SZYNA_PERTURB_T1=5 ;;
    5) export SZYNA_SCENARIUSZ="T1_plus10";  export SZYNA_PERTURB_K=0;  export SZYNA_PERTURB_T1=10 ;;
    6) export SZYNA_SCENARIUSZ="T1_plus15";  export SZYNA_PERTURB_K=0;  export SZYNA_PERTURB_T1=15 ;;
    7) export SZYNA_SCENARIUSZ="K10_T1_10";  export SZYNA_PERTURB_K=10; export SZYNA_PERTURB_T1=10 ;;
    *) echo "Nieznany SLURM_ARRAY_TASK_ID=$SLURM_ARRAY_TASK_ID"; exit 1 ;;
esac

echo "Scenariusz: $SZYNA_SCENARIUSZ (K${SZYNA_PERTURB_K:+}% T1${SZYNA_PERTURB_T1:+}%)"

# Celowo NIE ustawiamy SZYNA_MAX_DNI/SZYNA_LOKALIZACJE/SZYNA_ALGORYTMY -
# pełny zakres dat, wszystkie 43 lokalizacje, wszystkie 23 algorytmy (zgodnie
# z decyzją użytkownika - patrz uzasadnienie kosztu w nagłówku pliku).
export SZYNA_FOLDER_WYNIKOW="$SCRIPT_DIR/wyniki/wrazliwosc_transmitancji/$SZYNA_SCENARIUSZ"

python test_wszystkie_rownolegle.py
