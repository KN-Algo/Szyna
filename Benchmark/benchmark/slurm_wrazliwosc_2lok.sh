#!/bin/bash
# slurm_wrazliwosc_2lok.sh
#
# Pogłębiona analiza wrażliwości transmitancji + szumu pomiarowego NA DWÓCH
# lokalizacjach (Abisko - najwięcej opadu/śniegu, Ojmiakon - najzimniejsza) -
# patrz nagłówek test_wrazliwosc_dwie_lokalizacje.py po pełny opis 14
# scenariuszy transmitancji x 2 warianty szumu x wszystkie algorytmy.
#
# KOSZT: zmierzone lokalnie (smoke test, 3-dniowe okno, mieszanka
# algorytmów): ~0.15 core-min/zadanie. Przy oknie 45-dniowym (domyślne,
# SZYNA_MAX_DNI_WRAZ) to ekstrapoluje się do ~2.25 core-min/zadanie, razem
# ~1624 zadania (2 lokalizacje x 29 algorytmów x 14 scenariuszy x 2 warianty
# szumu) = ~60-90 core-h szacunkowo. --cpus-per-task=48 / --time=4:00:00 =
# 192 core-h - bezpieczny zapas ponad szacunek, NIE ślepe zgadywanie.
#
# WAŻNE: zlecaj TYLKO przez `sbatch`, NIGDY przez `sh`/`bash` bezpośrednio.
#
# Uruchomienie (z katalogu Benchmark/benchmark na klastrze):
#   sbatch slurm_wrazliwosc_2lok.sh

#SBATCH -J szyna_wrazliwosc_2lok
#SBATCH --account=hpc-wikjan2416-1787599067
#SBATCH -N 1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=48
#SBATCH --mem=1000G
#SBATCH --time=4:00:00
#SBATCH -p lem-cpu
#SBATCH --output=szyna_wrazliwosc_2lok_%j.log

set -euo pipefail

SCRIPT_DIR="$SLURM_SUBMIT_DIR"
cd "$SCRIPT_DIR"

if [ ! -d "$HOME/szyna_venv" ]; then
    python3 -m venv "$HOME/szyna_venv"
fi
source "$HOME/szyna_venv/bin/activate"
pip install --upgrade pip
pip install -r "$SCRIPT_DIR/requirements.txt"

# Celowo NIE ustawiamy SZYNA_LOKALIZACJE_WRAZ/SZYNA_SCENARIUSZE_WRAZ/SZYNA_ALGORYTMY -
# domyślnie: obie lokalizacje (Abisko + Ojmiakon), wszystkie 14 scenariuszy,
# wszystkie algorytmy. SZYNA_MAX_DNI_WRAZ też domyślne (45 dni, najzimniejszy
# wycinek) - podnieś na 151 (pełny zakres), jeśli chcesz pełną wiarygodność
# kosztem ~3.3x dłuższego czasu.
export SZYNA_FOLDER_WYNIKOW_WRAZ="$SCRIPT_DIR/wyniki/wrazliwosc_2lokalizacje"

python test_wrazliwosc_dwie_lokalizacje.py
python generuj_excel_wrazliwosc.py
