#!/bin/bash
# slurm_crt_scal.sh
#
# Scala części wyników ze wszystkich węzłów (PRZEGLAD_ZBIORCZY_czesc_*.csv ->
# PRZEGLAD_ZBIORCZY.csv) i generuje Excel (Podsumowanie_calkowite_zmienione_crt_<data>.xlsx).
# Zlecane automatycznie przez slurm/uruchom_crt_na_klastrze.sh z zależnością
# afterany od tablicy węzłów, więc rusza dopiero, gdy wszystkie węzły skończą (albo padną -
# wtedy dostaniesz częściowy Excel, a wznowienie dokończy resztę).
#
# Ręcznie (np. po wznowieniu brakujących zadań):
#   SZYNA_FOLDER_WYNIKOW=<pełny folder z datą> SZYNA_FOLDER_CSV_SZCZEGOLOWE=<folder na PD> \
#       sbatch --export=ALL slurm/slurm_crt_scal.sh

#SBATCH -J szyna_crt_scal
#SBATCH --account=hpc-wikjan2416-1787599067
#SBATCH -N 1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=128G
#SBATCH --time=0-03:00:00
#SBATCH -p lem-cpu
#SBATCH --output=szyna_crt_scalanie_%j.log

set -euo pipefail
cd "$SLURM_SUBMIT_DIR"

if [ ! -f "$HOME/szyna_venv/bin/activate" ]; then
    echo "BRAK środowiska $HOME/szyna_venv" >&2
    exit 1
fi
# shellcheck disable=SC1091
source "$HOME/szyna_venv/bin/activate"

: "${SZYNA_FOLDER_WYNIKOW:?brak SZYNA_FOLDER_WYNIKOW}"

export SZYNA_TYLKO_SCAL=1
export SZYNA_SHARD_LICZBA=1
export PYTHONUNBUFFERED=1

python -u testy/test_wszystkie_rownolegle_crt.py
