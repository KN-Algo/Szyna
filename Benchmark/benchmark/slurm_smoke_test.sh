#!/bin/bash
# slurm_smoke_test.sh
#
# MAŁY test przed pełnym przeglądem (43 lokalizacje x 23 algorytmy) - sprawdza
# na klastrze WCSS (https://man.e-science.pl/pl/kdm/slurm/gpu,
# https://man.e-science.pl/pl/kdm/slurm/partycje-slurm):
#   1) że środowisko Pythona (venv + pakiety) się stawia,
#   2) że test_wszystkie_rownolegle.py FAKTYCZNIE wykrywa liczbę rdzeni ze
#      SLURM_CPUS_PER_TASK (patrz log: "Wykryto limit rdzeni ze zmiennej
#      SLURM_CPUS_PER_TASK=... -> N procesów") - to jest dowód, że
#      wielowątkowość naprawdę działa, zanim zleci się kosztowne pełne zadanie,
#   3) że symulacja na 2 lokalizacjach/kilku algorytmach kończy się bez błędu.
#
# WAŻNE: zlecaj TYLKO przez `sbatch` (kolejka SLURM), NIGDY przez `sh`/`bash`
# bezpośrednio w terminalu - uruchomienie bezpośrednie ignoruje WSZYSTKIE
# dyrektywy #SBATCH poniżej i wykonuje się w środowisku bieżącej sesji
# OnDemand, a nie nowego zadania.
#
# Uruchomienie (z katalogu Benchmark/benchmark na klastrze):
#   sbatch slurm_smoke_test.sh

#SBATCH -J szyna_smoke_test
#SBATCH --account=hpc-wikjan2416-1787599067
#SBATCH -N 1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=8
#SBATCH --mem=16G
#SBATCH --time=0-00:30:00
#SBATCH -p lem-cpu-short
#SBATCH --output=szyna_smoke_%j.log

set -euo pipefail

# SLURM_SUBMIT_DIR - katalog, z którego wywołano `sbatch` (ustawiane PRZEZ
# SLURM dla poprawnie zleconego zadania). Celowo NIE liczymy tego z
# ${BASH_SOURCE[0]}/$0 - SLURM KOPIUJE zlecony skrypt do katalogu spool na
# przydzielonym węźle (/var/spool/slurmd/<węzeł>/job<id>/) i uruchamia go
# STAMTĄD, więc samo-namierzanie się przez ścieżkę własnego pliku wykryłoby
# katalog spool (gdzie nie ma reszty projektu), nie katalog z kodem.
SCRIPT_DIR="$SLURM_SUBMIT_DIR"
cd "$SCRIPT_DIR"

# Środowisko Pythona: jeśli ambientny python3 (ten z sesji OnDemand) nie
# wystarcza, sprawdź `module avail python` i ewentualnie dodaj tu odpowiedni
# `module load` - pomijamy to domyślnie, bo w środowisku OnDemand VSCode próba
# załadowania modułu python potrafi kolidować z już załadowanym GCCcore.
#
# Tworzymy venv TYLKO jeśli go jeszcze nie ma, ale `pip install` odpalamy
# ZAWSZE (jest bezpieczne/idempotentne - jeśli pakiety już są, po prostu nic
# nie robi w kilka sekund) - inaczej częściowo/nieudanie postawiony venv z
# wcześniejszej przerwanej próby zostałby cicho aktywowany BEZ pakietów.
if [ ! -d "$HOME/szyna_venv" ]; then
    python3 -m venv "$HOME/szyna_venv"
fi
source "$HOME/szyna_venv/bin/activate"
pip install --upgrade pip
pip install -r "$SCRIPT_DIR/requirements.txt"

# Ograniczony zakres - tylko test poprawności/wielowątkowości, nie wyniki do analizy.
export SZYNA_MAX_DNI=1
export SZYNA_LOKALIZACJE="abisko_60min_2021,abisko_60min_2022"
export SZYNA_ALGORYTMY="algorytm_z_normy,risk_function,risk_function_pid,fuzzy_ryzyko_1_opad"
export SZYNA_FOLDER_WYNIKOW="$SCRIPT_DIR/wyniki/smoke_test_klaster"

python test_wszystkie_rownolegle.py
