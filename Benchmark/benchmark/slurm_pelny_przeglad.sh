#!/bin/bash
# slurm_pelny_przeglad.sh
#
# PEŁNY przegląd (wszystkie lokalizacje x wszystkie algorytmy, PEŁNY zakres dat
# każdego pliku pogodowego - MAX_DNI_NA_LOKALIZACJE=None) na klastrze WCSS.
#
# Uruchamiaj DOPIERO po udanym slurm_smoke_test.sh - upewnij się w jego logu,
# że pojawiła się linia "Wykryto limit rdzeni ze zmiennej
# SLURM_CPUS_PER_TASK=... -> N procesów" z N zgodnym z --cpus-per-task poniżej
# (patrz uzasadnienie w nagłówku test_wszystkie_rownolegle.py: to jedyny
# niezawodny sposób wykrycia przydzielonych rdzeni na klastrze).
#
# Partycja: lem-cpu (meta-partycja - SLURM sam kieruje do lem-cpu-short/normal
# na podstawie zadeklarowanego --time, patrz
# https://man.e-science.pl/pl/kdm/slurm/partycje-slurm). Węzły lem-cpu mają do
# 128 rdzeni i 1430G RAM.
#
# --mem=1200G: --mem NIE liczy się do budżetu CPU-godzin konta (tylko
# cpus x czas się liczy - patrz niżej), więc nie ma powodu go oszczędzać -
# dajemy z dużym zapasem. Zmierzone bezpośrednio: JEDNO zadanie na PEŁNYM
# zakresie dat (~13 mln kroków) szczytowo zużywało ok. 9.4GB (pierwsza,
# nieoptymalna wersja symulacja_fizyczna.py budująca listę słowników Pythona -
# to właśnie spowodowało pierwszy OOM na klastrze przy 48 procesach i za
# ciasnym --mem=450G). Po optymalizacji (tablice numpy zamiast listy słowników)
# realne zużycie na zadanie jest wielokrotnie niższe, ale 1200G i tak zostaje -
# to tani, praktycznie darmowy zapas bezpieczeństwa (node ma 1430G limitu).
#
# --cpus-per-task=48 / --time=12:00:00 (12h) = 576 CPU-h - ZMIERZONE (nie
# szacowane) na podstawie realnych testów lokalnych z krokiem symulacji 10s
# (patrz KROK_SYMULACJI_S w teście_wszystkie_rownolegle.py): 56 zadań (28
# algorytmów x 2 lokalizacje, okno 2 dni) zajęło 1.4 min na 4 rdzeniach, co
# ekstrapolowane na pełny zakres dat (43 lokalizacje x 28 algorytmów, ~151 dni)
# daje szacunek rzędu 150-300 CPU-h - 576h (12h x 48 rdzeni) to bezpieczny
# zapas ponad to, NIE ślepe zgadywanie jak poprzednia wersja (2-16:00:00 =
# 3072h), która ledwo nie zmieściła się w dostępnym budżecie konta
# (QOSGrpCPUMinutesLimit). Jeśli mimo to zabraknie czasu w trakcie liczenia,
# zadanie zostanie przerwane - patrz mechanizm wznawiania (SZYNA_WZNOW) w
# test_wszystkie_rownolegle.py, nic się wtedy nie zmarnuje, wystarczy zlecić
# to samo zadanie jeszcze raz.
#
# Przed odpaleniem: sprawdź dostępne godziny CPU usługi (service-balance --check-cpu)
# i dostępność węzłów (check-partitions) - patrz
# https://man.e-science.pl/pl/kdm/rejestr_zuzycia_zasobow.
#
# WAŻNE: zlecaj TYLKO przez `sbatch` (kolejka SLURM), NIGDY przez `sh`/`bash`
# bezpośrednio w terminalu - uruchomienie bezpośrednie ignoruje WSZYSTKIE
# dyrektywy #SBATCH powyżej (zero rdzeni/RAM ponad to, co ma Twoja bieżąca
# sesja) i wykonuje się w środowisku sesji OnDemand, a nie nowego zadania.
#
# Uruchomienie (z katalogu Benchmark/benchmark na klastrze):
#   sbatch slurm_pelny_przeglad.sh

#SBATCH -J szyna_pelny_przeglad
#SBATCH --account=hpc-wikjan2416-1787599067
#SBATCH -N 1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=48
#SBATCH --mem=1000G
#SBATCH --time=12:00:00
#SBATCH -p lem-cpu
#SBATCH --output=szyna_pelny_%j.log
# 48 rdzeni x 64h = 3072 CPU-h - dopasowane pod dostępny budżet konta
# (service-balance: ~3315h wolne). WIĘCEJ rdzeni/czasu = SLURM odrzuci
# zgłoszenie (QOSGrpCPUMinutesLimit), bo iloczyn cpus x time przekroczy limit
# konta niezależnie od tego, ile faktycznie zostanie zużyte. Jeśli po tym
# zadaniu dojdzie zwiększenie puli godzin, można podnieść oba te parametry.

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

# Celowo NIE ustawiamy SZYNA_MAX_DNI/SZYNA_LOKALIZACJE/SZYNA_ALGORYTMY -
# domyślnie: pełny zakres dat, wszystkie lokalizacje, wszystkie algorytmy.
# SZYNA_LICZBA_WATKOW też nie jest konieczne - autodetekcja złapie
# SLURM_CPUS_PER_TASK ustawione przez --cpus-per-task powyżej.
export SZYNA_FOLDER_WYNIKOW="$SCRIPT_DIR/wyniki/przeglad_wielu_lokalizacji"

python test_wszystkie_rownolegle.py
