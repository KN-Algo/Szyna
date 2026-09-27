# Algorytmy/predykcja_wygladzanie_prosta.py
#
# ALGORYTM inspirowany polityką P_pre ("prediction-based policy") z pracy:
#   S. Chiaradonna, G. Masetti, F. Di Giandomenico, F. Righetti, C. Vallati,
#   "Enhancing sustainability of the railway infrastructure: Trading energy
#   saving and unavailability through efficient switch heating policies",
#   Sustainable Computing: Informatics and Systems 30 (2021) 100519, sekcja 4.2.3.
#
# IDEA (wg pracy): zamiast reagować na AKTUALNĄ temperaturę (jak histereza)
# albo na PEŁNĄ prognozę Kalmana ze zidentyfikowanego modelu obiektu (jak
# risk_function*/mpc_*), LEKKI, LOKALNY kontroler (bez dostępu do bogatszych
# zasobów "koordynatora") sam sobie prognozuje NASTĘPNĄ wartość temperatury
# prostym wygładzaniem wykładniczym (w pracy: Holt-Winters/TBATS na historii
# lokalnego czujnika) i porównuje PROGNOZĘ (nie odczyt bieżący) z progiem.
#
# KLUCZOWA IDEA PRACY (cytat, sekcja 4.2.3): najlepsza wartość progu T̃_thr to
# WŁASNY, NA BIEŻĄCO ŚLEDZONY błąd bezwzględny prognozy ε_f - margines
# dokładnie taki duży, żeby NIGDY nie zamarznąć (próg z zapasem pokrywającym
# typowy błąd prognozy), ale nie większy niż trzeba (żeby nie marnować
# energii). W tym algorytmie próg jest więc SAMOKALIBRUJĄCY SIĘ: rośnie, gdy
# prognoza ostatnio się myliła bardziej, maleje, gdy prognoza jest trafna -
# to jedyny algorytm w tym projekcie, w którym margines bezpieczeństwa NIE
# jest stałą, tylko wynika z historii własnej skuteczności prognozowania.
#
# RÓŻNICA względem mpc_prognoza_pogody/risk_function_pid (oba używają
# WSPÓLNEJ prognozy Kalmana z rdzen_kontrolera.py, zbudowanej z pełnej,
# scentralizowanej historii AT/CRT): tu prognoza jest CAŁKOWICIE OSOBNA,
# lekka (wygładzanie wykładnicze Holta - poziom + trend, O(1) na krok),
# licząca WYŁĄCZNIE na własnej historii HRT tego kontrolera - świadomie
# uboższa metoda, zgodnie z założeniem pracy "lokalny kontroler bez dostępu
# do bogatszych zasobów koordynatora".

from rdzen_kontrolera import KontrolerBazowy, RowData, NANOS_PER_BIN

ALPHA_POZIOM = 0.3     # Wygładzanie poziomu w metodzie Holta (0-1, większe = szybciej "goni" nowe dane).
BETA_TREND = 0.1       # Wygładzanie trendu w metodzie Holta.
MARGINES_POCZATKOWY_C = 2.0   # ε_f zanim zbierze się choć jeden błąd prognozy do uśrednienia (ostrożny start).
MAX_BLEDOW_W_PAMIECI = 50     # Ile ostatnich błędów |prognoza-rzeczywistość| trzymamy do liczenia ε_f (średnia ruchoma).
PROG_BAZOWY_C = 3.0    # Odpowiednik "prawie 0°C" z pracy (tam próg liczony wprost od zamarzania) przełożony na
                       # konwencję progu wyłączenia "na sucho" reszty algorytmów w tym projekcie (jak w
                       # histereza_pamiec_rosy.py/histereza_let1.hrt_off_dry) - efektywny próg = PROG_BAZOWY_C + ε_f.


class KontrolerPredykcjaWygladzanie(KontrolerBazowy):

    def __init__(self, max_switches_per_day=12):
        super().__init__()

        self.heating_on = False

        # --- LIMIT PRZEŁĄCZEŃ (jak histereza_let1.py) ---
        self.current_date = None
        self.switch_count_today = 0
        self.max_switches_per_day = max_switches_per_day

        # --- WYGŁADZANIE WYKŁADNICZE HOLTA (poziom + trend) NA WŁASNEJ HISTORII HRT,
        # w binach 15-minutowych (NANOS_PER_BIN, spójne z resztą projektu) - NIE na
        # surowych krokach symulacji, żeby prognoza "1 krok naprzód" znaczyła coś
        # fizycznie (kilkanaście minut naprzód), niezależnie od kroku sterowania dt. ---
        self._cur_bin_id = None
        self._cur_suma_hrt = 0.0
        self._cur_liczba_hrt = 0
        self._poziom = None
        self._trend = 0.0
        self._prognoza_na_biezacy_bin = None  # Prognoza (z POPRZEDNIEGO binu) na to, co WŁAŚNIE się dzieje.

        # --- ŚLEDZENIE WŁASNEGO BŁĘDU PROGNOZY (ε_f) - patrz nagłówek pliku. ---
        self._bledy_prognozy = []  # Lista (kolejka FIFO o max. rozmiarze MAX_BLEDOW_W_PAMIECI) ostatnich |błędów|.

    def _epsilon_f(self):
        if not self._bledy_prognozy:
            return MARGINES_POCZATKOWY_C
        return sum(self._bledy_prognozy) / len(self._bledy_prognozy)

    def compute_control(self, row_data):
        timestamp = row_data['Timestamp']
        hrt_temp = float(row_data['HRT_temp_grzana'])

        bin_id = timestamp.value // NANOS_PER_BIN
        if self._cur_bin_id is None:
            self._cur_bin_id = bin_id
        elif bin_id != self._cur_bin_id:
            # Bin się zamknął - mamy nową, faktyczną obserwację (średnia HRT w tym binie).
            srednia_hrt = self._cur_suma_hrt / self._cur_liczba_hrt
            self._dodaj_flopy(1)  # dzielenie (średnia binu)

            # Porównanie z prognozą wystawioną NA TEN bin (jeśli już jakąś mieliśmy) - to jest ε_f.
            if self._prognoza_na_biezacy_bin is not None:
                blad = abs(srednia_hrt - self._prognoza_na_biezacy_bin)
                self._bledy_prognozy.append(blad)
                if len(self._bledy_prognozy) > MAX_BLEDOW_W_PAMIECI:
                    self._bledy_prognozy.pop(0)
                self._dodaj_flopy(2)  # odejmowanie + wartość bezwzględna

            # Aktualizacja stanu Holta (poziom + trend) i prognoza NA KOLEJNY bin.
            if self._poziom is None:
                self._poziom = srednia_hrt
                self._trend = 0.0
            else:
                poziom_poprzedni = self._poziom
                self._poziom = ALPHA_POZIOM * srednia_hrt + (1.0 - ALPHA_POZIOM) * (self._poziom + self._trend)
                self._trend = BETA_TREND * (self._poziom - poziom_poprzedni) + (1.0 - BETA_TREND) * self._trend
                self._dodaj_flopy(8)  # 2 mnożenia + dodawanie dla poziomu, tyle samo dla trendu
            self._prognoza_na_biezacy_bin = self._poziom + self._trend

            self._cur_bin_id = bin_id
            self._cur_suma_hrt = 0.0
            self._cur_liczba_hrt = 0

        self._cur_suma_hrt += hrt_temp
        self._cur_liczba_hrt += 1

        # 1. Reset licznika przełączeń z nastaniem nowego dnia.
        active_date = timestamp.date()
        if self.current_date != active_date:
            self.current_date = active_date
            self.switch_count_today = 0

        # 2. Próg efektywny SAMOKALIBRUJĄCY SIĘ (patrz nagłówek pliku) - im gorzej
        # ostatnio prognoza trafiała, tym większy margines bezpieczeństwa.
        epsilon_f = self._epsilon_f()
        prog_efektywny = PROG_BAZOWY_C + epsilon_f

        # 3. Prognoza do porównania z progiem - dopóki nie zamknął się jeszcze ŻADEN
        # bin (samy początek przebiegu), nie ma jeszcze żadnej prognozy Holta - w tej
        # krótkiej fazie startowej używamy wprost bieżącego odczytu (ostrożny fallback,
        # analogicznie do "brak modelu -> regulator P" w innych adaptacyjnych algorytmach).
        prognoza = self._prognoza_na_biezacy_bin if self._prognoza_na_biezacy_bin is not None else hrt_temp

        # 4. Decyzja ON/OFF (histereza binarna na PROGNOZIE, nie na bieżącym odczycie).
        previous_state = self.heating_on
        target_state = prognoza <= prog_efektywny
        if target_state != previous_state:
            if self.switch_count_today < self.max_switches_per_day:
                self.heating_on = target_state
                self.switch_count_today += 1

        reading = RowData()
        reading.timestamp = timestamp
        reading.at_temp = float(row_data['AT_temp_powietrza'])
        reading.crt_temp = float(row_data['CRT_temp_niegrzana'])
        self._append_sensor_history(reading)
        self._dodaj_flopy(4)  # progi/porównania/limit przełączeń.

        diagnostics = {
            'target_temperature': prog_efektywny,
            'need_heat': self.heating_on,
            'epsilon_f': epsilon_f,
            'prognoza_hrt': prognoza,
        }
        return (100.0 if self.heating_on else 0.0), diagnostics
