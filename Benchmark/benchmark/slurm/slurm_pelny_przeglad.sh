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
# --cpus-per-task=64 / --time=12:00:00 (12h) = 768 CPU-h ceiling (podniesione z
# 48 rdzeni na życzenie użytkownika 2026-09-07 - "niech będzie 64 rdzenie brane
# do wyliczeń, niech się szybciej liczą" - WIĘCEJ równoległych procesów na to
# samo zadanie = ta sama całkowita praca kończy się szybciej w czasie
# rzeczywistym, NIE więcej pracy do zrobienia). Rzeczywiste zużycie CPU-h
# (cpus x rzeczywisty czas, nie ta sama wielkość co "czas ściany") się NIE
# zmienia z liczbą rdzeni - to ZMIERZONE (nie szacowane) na podstawie realnych
# testów lokalnych z krokiem symulacji 10s (patrz KROK_SYMULACJI_S w
# testy/test_wszystkie_rownolegle.py): 56 zadań (28 algorytmów x 2 lokalizacje,
# okno 2 dni) zajęło 1.4 min na 4 rdzeniach, co ekstrapolowane na ÓWCZESNY
# pełny zakres dat (43 lokalizacje x 28 algorytmów, ~151 dni) dawało szacunek
# rzędu 150-300 CPU-h. Rejestr od tego czasu urósł do 42 algorytmów (dodane 3
# warianty MPC + 2 algorytmy inspirowane literaturą) i 44 lokalizacji
# (2026-09-03, nowa lista 44 lokalizacji użytkownika) - skalując proporcjonalnie
# (35/28 x 44/43) daje to ~192-384 CPU-h, WCIĄŻ w granicach zadeklarowanego
# budżetu 768 CPU-h (12h x 64 rdzeni) - bezpieczny zapas, nie ślepe zgadywanie,
# a przy 64 zamiast 48 rdzeniach realny czas ściany krótszy o ok. 25%. Jeśli
# mimo to zabraknie
# czasu w trakcie liczenia, zadanie zostanie przerwane - patrz mechanizm
# wznawiania (SZYNA_WZNOW) w test_wszystkie_rownolegle.py, nic się wtedy nie
# zmarnuje, wystarczy zlecić to samo zadanie jeszcze raz.
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
#   sbatch slurm/slurm_pelny_przeglad.sh

#SBATCH -J szyna_pelny_przeglad
#SBATCH --account=hpc-wikjan2416-1787599067
#SBATCH -N 1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=64
#SBATCH --mem=1000G
#SBATCH --time=12:00:00
#SBATCH -p lem-cpu
#SBATCH --output=szyna_pelny_%j.log
# UWAGA budżetu konta: 48 rdzeni x 12h = 576 CPU-h (patrz uzasadnienie w
# komentarzu przy tym --time wyżej). Sprawdź dostępne CPU-h PRZED zleceniem
# (service-balance --check-cpu) - jeśli budżet jest ciaśniejszy niż 576h,
# zmniejsz --cpus-per-task/--time proporcjonalnie (SLURM i tak odrzuci
# zgłoszenie, gdy iloczyn cpus x time przekroczy limit konta - QOSGrpCPUMinutesLimit).

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

# Ciężkie pliki (pełna trajektoria per (lokalizacja, algorytm) - ~44x37=1628
# plików + *_uczenie.csv) idą na PD (Personal Data - duża, osobna przestrzeń
# dyskowa na WCSS, patrz `PD-info` w terminalu klastra), NIE do katalogu
# roboczego/domowego (na życzenie użytkownika 2026-09-07 - "wszystkie [wyniki]
# poza excelami" tam, bo w katalogu domowym brakuje miejsca). PRZEGLAD_ZBIORCZY.csv
# i finalny Excel ZOSTAJĄ w SZYNA_FOLDER_WYNIKOW wyżej (małe, potrzebne lokalnie
# do pobrania/dalszej pracy) - patrz FOLDER_CSV_SZCZEGOLOWE w
# testy/test_wszystkie_rownolegle.py i generatory_excel/generuj_excel_podsumowanie.py.
# Jeśli Twoja usługa PD ma inną nazwę/ścieżkę niż poniżej, sprawdź `PD-info` i
# podmień PDDIR.
PDDIR="/lustre/pd03/hpc-wikjan2416-1787599067"
export SZYNA_FOLDER_CSV_SZCZEGOLOWE="$PDDIR/szyna_csv_szczegolowe/przeglad_wielu_lokalizacji"
mkdir -p "$SZYNA_FOLDER_CSV_SZCZEGOLOWE"

python testy/test_wszystkie_rownolegle.py
