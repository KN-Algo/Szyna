#!/bin/bash
# uruchom_crt_na_klastrze.sh
#
# JEDNO polecenie, które zleca PEŁNY przegląd CRT (wszystkie lokalizacje x wszystkie
# algorytmy) rozłożony na WIELE WĘZŁÓW klastra naraz, plus zadanie scalające wyniki
# i generujące Excel po zakończeniu wszystkich węzłów.
#
# Dlaczego wiele węzłów: jeden węzeł lem-cpu ma max 128 rdzeni. Budżet w CPU-godzinach
# (rdzenie x czas) jest ten sam niezależnie od podziału - ale 4 węzły x 128 rdzeni
# kończą tę samą pracę ok. 4x szybciej w czasie rzeczywistym niż jeden węzeł.
#
# Uruchomienie (z katalogu Benchmark_crt/benchmark NA KLASTRZE, na węźle logowania):
#   bash slurm/uruchom_crt_na_klastrze.sh
# Ten skrypt sam woła sbatch - NIE zlecaj go przez sbatch.
#
# Parametry (zmienne środowiskowe, wszystkie opcjonalne):
#   WEZLY=4            ile węzłów naraz (1 = jeden węzeł, jak dotąd)
#   CPUS=<auto>        rdzeni na węzeł; domyślnie wykrywane z sinfo (max w partycji), inaczej 128
#   BUDZET_CPU_H=780   ile CPU-godzin wolno "zarezerwować" (limit czasu = budżet / (WEZLY x CPUS));
#                      zużywane jest tylko tyle, ile faktycznie policzą - to sufit, nie koszt
#   MEM=1000G          pamięć na węzeł (--mem NIE liczy się do budżetu CPU-h)
#   PARTYCJA=lem-cpu   partycja
#   KONTO=hpc-wikjan2416-1787599067
#   PDDIR=/lustre/pd03/$KONTO   duży dysk na ciężkie CSV i referencje normy
#   STAMP=<data_godzina>        znacznik w nazwach folderów; PODAJ STARY, żeby WZNOWIĆ przebieg
#   SZYNA_LOKALIZACJE / SZYNA_ALGORYTMY   lista po przecinku; domyślnie WSZYSTKIE
#   DRY_RUN=1          tylko wypisz polecenia sbatch, niczego nie zlecaj
#
# WZNAWIANIE po przerwaniu (limit czasu, awaria węzła): uruchom to samo polecenie z tym
# samym STAMP, np.   STAMP=2026-09-30_14-05 bash slurm/uruchom_crt_na_klastrze.sh
# Policzone już pary (lokalizacja, algorytm) są pomijane.

set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
SCRIPT_DIR="$(pwd)"

KONTO="${KONTO:-hpc-wikjan2416-1787599067}"
PARTYCJA="${PARTYCJA:-lem-cpu}"
WEZLY="${WEZLY:-4}"
BUDZET_CPU_H="${BUDZET_CPU_H:-780}"
MEM="${MEM:-1000G}"
PDDIR="${PDDIR:-/lustre/pd03/$KONTO}"
STAMP="${STAMP:-$(date +%Y-%m-%d_%H-%M)}"
DRY_RUN="${DRY_RUN:-0}"

echo "=== Zasoby konta ==="
if command -v service-balance >/dev/null 2>&1; then
    service-balance --check-cpu || echo "(service-balance zwrócił błąd - sprawdź saldo ręcznie)"
else
    echo "(brak polecenia service-balance - sprawdź saldo CPU-h ręcznie na klastrze)"
fi
if command -v check-partitions >/dev/null 2>&1; then
    check-partitions || true
fi

# Rdzenie na węzeł: największa liczba CPU spośród węzłów partycji (sinfo %c), z odsianiem
# znaków typu "128+". Gdy sinfo niedostępne - 128 (limit lem-cpu).
if [ -z "${CPUS:-}" ]; then
    CPUS=""
    if command -v sinfo >/dev/null 2>&1; then
        CPUS="$(sinfo -h -p "$PARTYCJA" -o '%c' 2>/dev/null | tr -dc '0-9\n' | sort -n | tail -1 || true)"
    fi
    CPUS="${CPUS:-128}"
fi

# Limit czasu z budżetu: BUDZET_CPU_H godzin rdzenia rozłożone na WEZLY x CPUS rdzeni.
MINUTY=$(( BUDZET_CPU_H * 60 / (WEZLY * CPUS) ))
if [ "$MINUTY" -lt 30 ]; then MINUTY=30; fi
CZAS="$(( MINUTY / 1440 ))-$(printf '%02d:%02d:00' $(( (MINUTY % 1440) / 60 )) $(( MINUTY % 60 )))"
SUFIT_CPU_H=$(( WEZLY * CPUS * MINUTY / 60 ))

FOLDER_WYNIKOW="$SCRIPT_DIR/wyniki/przeglad_pelny_crt_$STAMP"
FOLDER_CSV="$PDDIR/szyna_csv_szczegolowe/przeglad_pelny_crt_$STAMP"

echo
echo "=== Plan ==="
echo "Węzłów: $WEZLY x $CPUS rdzeni = $(( WEZLY * CPUS )) procesów naraz"
echo "Limit czasu na węzeł: $CZAS  ->  sufit rezerwacji ${SUFIT_CPU_H} CPU-h (budżet ${BUDZET_CPU_H})"
echo "Folder wyników (Excel, CSV zbiorcze): $FOLDER_WYNIKOW"
echo "Folder ciężkich CSV + referencji normy: $FOLDER_CSV"
echo "Znacznik przebiegu (do wznowienia): STAMP=$STAMP"
echo

# Środowisko Pythona stawiamy TUTAJ, raz - gdyby robił to każdy węzeł osobno, równoległe
# 'pip install' do tego samego venv nawzajem by się psuły.
if [ "$DRY_RUN" != "1" ]; then
    if [ ! -d "$HOME/szyna_venv" ]; then
        python3 -m venv "$HOME/szyna_venv"
    fi
    # shellcheck disable=SC1091
    source "$HOME/szyna_venv/bin/activate"
    pip install --upgrade pip
    pip install -r "$SCRIPT_DIR/requirements.txt"
    mkdir -p "$FOLDER_WYNIKOW" "$FOLDER_CSV"
fi

export SZYNA_FOLDER_WYNIKOW="$FOLDER_WYNIKOW"
export SZYNA_FOLDER_CSV_SZCZEGOLOWE="$FOLDER_CSV"
export SZYNA_LOKALIZACJE="${SZYNA_LOKALIZACJE:-WSZYSTKIE}"
export SZYNA_ALGORYTMY="${SZYNA_ALGORYTMY:-WSZYSTKIE}"

SBATCH_WSPOLNE=(--account="$KONTO" -p "$PARTYCJA" --export=ALL)

CMD_WEZLY=(sbatch --parsable "${SBATCH_WSPOLNE[@]}"
    --array="0-$(( WEZLY - 1 ))" -N 1 --ntasks=1 --cpus-per-task="$CPUS"
    --mem="$MEM" --time="$CZAS"
    --output="$SCRIPT_DIR/szyna_crt_${STAMP}_wezel%a_%A.log"
    slurm/slurm_crt_wezel.sh)

if [ "$DRY_RUN" = "1" ]; then
    echo "[DRY_RUN] ${CMD_WEZLY[*]}"
    echo "[DRY_RUN] sbatch --dependency=afterany:<ID_tablicy> ... slurm/slurm_crt_scal.sh"
    exit 0
fi

ID_TABLICY="$("${CMD_WEZLY[@]}")"
ID_TABLICY="${ID_TABLICY%%;*}"
echo "Zlecono tablicę węzłów: job $ID_TABLICY ($WEZLY zadań)"

# 'afterany' (nie 'afterok'): scalanie ma ruszyć także wtedy, gdy któryś węzeł padł lub
# skończył się mu czas - dostaniesz częściowy Excel, a brakujące pary dokończy wznowienie.
ID_SCAL="$(sbatch --parsable "${SBATCH_WSPOLNE[@]}" -N 1 --ntasks=1 --cpus-per-task=4 \
    --mem=128G --time=0-03:00:00 --dependency="afterany:$ID_TABLICY" \
    --output="$SCRIPT_DIR/szyna_crt_${STAMP}_scalanie_%j.log" slurm/slurm_crt_scal.sh)"
echo "Zlecono scalanie + Excel: job ${ID_SCAL%%;*} (rusza po zakończeniu wszystkich węzłów)"

echo
echo "Podgląd kolejki:      squeue -u \$USER"
echo "Logi węzłów:          tail -f $SCRIPT_DIR/szyna_crt_${STAMP}_wezel0_${ID_TABLICY}.log"
echo "Wyniki po zakończeniu: $FOLDER_WYNIKOW"
