# Algorytmy/histereza_pamiec_rosy.py
#
# ALGORYTM inspirowany polityką P_mem (+ progiem "koordynatora") z pracy:
#   S. Chiaradonna, G. Masetti, F. Di Giandomenico, F. Righetti, C. Vallati,
#   "Enhancing sustainability of the railway infrastructure: Trading energy
#   saving and unavailability through efficient switch heating policies",
#   Sustainable Computing: Informatics and Systems 30 (2021) 100519.
#
# RÓŻNICA względem WSZYSTKICH pozostałych algorytmów w tym projekcie: to
# PIERWSZY algorytm, który faktycznie UŻYWA punktu rosy (PUNKT_ROSY_C) w
# logice decyzyjnej (żaden inny algorytm go dotąd nie czytał - potwierdzone
# empirycznie w teście szumu wielu czujników: szum na tym czujniku miał 0.00%
# wpływu na WSZYSTKIE 33 algorytmy, patrz AGENTS.md).
#
# LOGIKA (wg pracy, sekcja 4.1 "policy under functional communication
# channels" - próg referencyjny T_thr):
#   załącz grzanie, gdy HRT <= punkt_rosy + T_thr  ORAZ  HRT <= T_thr
#   wyłącz grzanie, gdy HRT >  punkt_rosy + T_thr  LUB   HRT >  T_thr
# (w oryginale to koordynator z pełnym dostępem do stacji pogodowej liczy tę
# regułę i wysyła komendę ON/OFF do lokalnego kontrolera przez sieć PLC).
#
# MECHANIZM "PAMIĘCI" (P_mem, sekcja 4.2.2) - w oryginale: gdy kanał PLC
# między koordynatorem a lokalnym kontrolerem ulega awarii, kontroler używa
# OSTATNIEJ znanej wartości punktu rosy przez Δm kroków, a POTEM przechodzi
# na politykę bazową P_bas (sam próg temperatury, bez punktu rosy - bo
# przetrzymywana wartość jest już zbyt nieaktualna, żeby jej ufać). W tym
# projekcie nie ma osobnego modelu awarii komunikacji - zamiast tego
# wykrywamy "zawieszenie" odczytu punktu rosy WPROST z danych: jeśli
# PUNKT_ROSY_C nie zmienia się przez DELTA_M_KROKOW kolejnych kroków, to
# DOKŁADNIE ten sam objaw, jaki daje realna awaria/rozłączenie czujnika
# (patrz test_awarie_czujnikow._zrob_rozlaczenie - też "zamraża" ostatnią
# wartość) - więc ten sam mechanizm wykrywania działa organicznie, bez
# potrzeby osobnej symulacji sieci PLC.

from rdzen_kontrolera import KontrolerBazowy, RowData

# Próg referencyjny T_thr - w pracy testowany przy dwóch skrajnych wartościach
# (0°C i 5°C) jako analiza wrażliwości, BEZ jednoznacznej rekomendacji "tej
# jedynej słusznej" wartości (zależy od operatora/lokalizacji). Przyjmujemy tu
# 3.0°C - spójne z konwencją progu wyłączenia "na sucho" reszty algorytmów w
# tym projekcie (histereza_let1.hrt_off_dry).
T_THR_C = 3.0

# Δm z pracy - liczba kolejnych kroków identycznego odczytu punktu rosy, po
# których uznajemy go za "zawieszony" i przechodzimy na politykę P_bas (sam
# próg temperatury). W pracy Δm było wyrażone w wielokrotności okresu
# odświeżania danych pogodowych (t^w) - tutaj w krokach STEROWANIA.
DELTA_M_KROKOW = 20


class KontrolerHisterezaPamiecRosy(KontrolerBazowy):

    def __init__(self, max_switches_per_day=12):
        super().__init__()

        self.heating_on = False
        self.t_thr = T_THR_C

        # --- LIMIT PRZEŁĄCZEŃ (jak histereza_let1.py) ---
        self.current_date = None
        self.switch_count_today = 0
        self.max_switches_per_day = max_switches_per_day

        # --- STAN "PAMIĘCI" PUNKTU ROSY (P_mem) ---
        self._ostatni_punkt_rosy = None
        self._licznik_niezmiennosci = 0

    def compute_control(self, row_data):
        timestamp = row_data['Timestamp']
        hrt_temp = float(row_data['HRT_temp_grzana'])
        punkt_rosy = float(row_data['PUNKT_ROSY_C'])

        # 1. Reset licznika przełączeń z nastaniem nowego dnia.
        active_date = timestamp.date()
        if self.current_date != active_date:
            self.current_date = active_date
            self.switch_count_today = 0

        # 2. Wykrycie "zawieszenia" odczytu punktu rosy (patrz nagłówek pliku).
        if self._ostatni_punkt_rosy is not None and punkt_rosy == self._ostatni_punkt_rosy:
            self._licznik_niezmiennosci += 1
        else:
            self._licznik_niezmiennosci = 0
        self._ostatni_punkt_rosy = punkt_rosy
        punkt_rosy_swiezy = self._licznik_niezmiennosci < DELTA_M_KROKOW

        # 3. Decyzja ON/OFF - "koordynator" (z punktem rosy) albo P_bas (fallback).
        previous_state = self.heating_on
        if punkt_rosy_swiezy:
            prog_wylaczenia = min(punkt_rosy + self.t_thr, self.t_thr)
            if not self.heating_on:
                target_state = hrt_temp <= punkt_rosy + self.t_thr and hrt_temp <= self.t_thr
            else:
                target_state = not (hrt_temp > punkt_rosy + self.t_thr or hrt_temp > self.t_thr)
        else:
            prog_wylaczenia = self.t_thr
            target_state = hrt_temp <= self.t_thr

        # 4. Bezpiecznik sprzętowy: limit dobowy przełączeń (jak w histereza_let1.py).
        if target_state != previous_state:
            if self.switch_count_today < self.max_switches_per_day:
                self.heating_on = target_state
                self.switch_count_today += 1

        reading = RowData()
        reading.timestamp = timestamp
        reading.at_temp = float(row_data['AT_temp_powietrza'])
        reading.crt_temp = float(row_data['CRT_temp_niegrzana'])
        self._append_sensor_history(reading)
        # Śledzenie zmiany punktu rosy (2) + próg podwójny (4) + limit przełączeń (2).
        self._dodaj_flopy(8)

        # --- DIAGNOSTYKA (IAE/ISE/ITAE) - cel = próg wyłączenia AKTYWNEJ gałęzi
        # (z punktem rosy, gdy odczyt świeży, albo sam próg temperatury po
        # wykryciu "zawieszenia") - ten próg kończy epizod grzania. ---
        diagnostics = {
            'target_temperature': prog_wylaczenia,
            'need_heat': self.heating_on,
            'punkt_rosy_swiezy': punkt_rosy_swiezy,
        }
        return (100.0 if self.heating_on else 0.0), diagnostics
