#!/bin/bash
# slurm_crt_wezel.sh
#
# Jeden WĘZEŁ przeglądu CRT - element tablicy zadań (job array) zlecanej przez
# slurm/uruchom_crt_na_klastrze.sh. Nie zlecaj go ręcznie bez tego launchera: zmienne
# SZYNA_FOLDER_WYNIKOW itd. są ustawiane tam i przekazywane przez --export=ALL.
#
# Węzeł dostaje wycinek zadań (indeks = numer elementu tablicy) i liczy go na WSZYSTKICH
# przydzielonych rdzeniach (runner wykrywa liczbę z SLURM_CPUS_PER_TASK - w logu szukaj
# linii "Wykryto limit rdzeni ze zmiennej SLURM_CPUS_PER_TASK=... -> N procesów").
#
# Domyślne dyrektywy poniżej są nadpisywane przez flagi launchera (--cpus-per-task, --mem,
# --time, --array) - wartości tutaj obowiązują tylko przy ręcznym sbatch.

#SBATCH -J szyna_crt_wezel
#SBATCH --account=hpc-wikjan2416-1787599067
#SBATCH -N 1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=128
#SBATCH --mem=1000G
#SBATCH --time=01:30:00
#SBATCH -p lem-cpu
#SBATCH --output=szyna_crt_wezel_%A_%a.log

set -euo pipefail

# SLURM kopiuje skrypt do katalogu spool - katalog z kodem to katalog, z którego zlecono sbatch.
cd "$SLURM_SUBMIT_DIR"

if [ ! -f "$HOME/szyna_venv/bin/activate" ]; then
    echo "BRAK środowiska $HOME/szyna_venv - uruchom najpierw slurm/uruchom_crt_na_klastrze.sh" >&2
    exit 1
fi
# shellcheck disable=SC1091
source "$HOME/szyna_venv/bin/activate"

: "${SZYNA_FOLDER_WYNIKOW:?brak SZYNA_FOLDER_WYNIKOW - zlecaj przez uruchom_crt_na_klastrze.sh}"

# Numer węzła i liczba węzłów z tablicy zadań.
export SZYNA_SHARD_INDEKS=$(( SLURM_ARRAY_TASK_ID - ${SLURM_ARRAY_TASK_MIN:-0} ))
export SZYNA_SHARD_LICZBA="${SLURM_ARRAY_TASK_COUNT:-1}"
export SZYNA_TYLKO_SCAL=0

# Jeden proces = jeden rdzeń (runner też to ustawia, tu jawnie dla czytelności).
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 NUMBA_NUM_THREADS=1
export PYTHONUNBUFFERED=1

echo "Węzeł $(hostname): część $((SZYNA_SHARD_INDEKS + 1))/$SZYNA_SHARD_LICZBA, ${SLURM_CPUS_PER_TASK:-?} rdzeni"
echo "Folder wyników: $SZYNA_FOLDER_WYNIKOW"

python -u testy/test_wszystkie_rownolegle_crt.py
