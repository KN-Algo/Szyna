# algorytmy/algorytm_z_normy.py
#
# Referencyjny automat pogodowy zaimplementowany WYŁĄCZNIE na podstawie
# instrukcji Iet-1 PKP Polskie Linie Kolejowe S.A. "Instrukcja eksploatacji
# i utrzymania urządzeń elektrycznego ogrzewania rozjazdów" (Załącznik do
# uchwały Nr 1091/2025), rozdział 2.4 "Automaty pogodowe", pkt 2.4.12-2.4.19,
# wariant z DWOMA czujnikami (szyna ogrzewana HRT + szyna nieogrzewana CRT).
#
# Ten plik CELOWO nie zawiera żadnej logiki spoza normy: brak pamięci,
# prognozy, oceny ryzyka 0-10 czy ciągłego PID - to czysta implementacja
# progów załączenia/wyłączenia z Tabeli nr 5 (opady) i Tabeli nr 6 (bez
# opadów), służąca jako punkt odniesienia przy porównaniu z pozostałymi
# algorytmami (histereza_let1.py, funkcja_ryzyka_binarna.py,
# funkcja_ryzyka_pid.py) w test_wszystkie_algorytmy_jedna_lokalizacja.py.
#
# Zasady załączania/wyłączania (dokładnie wg normy):
#   2.4.13 (przy opadach, załączenie): opad WYKRYTY (czujnik wilgoci/śniegu)
#     ORAZ CRT <= próg załączenia CRT ORAZ HRT <= próg załączenia HRT.
#   2.4.14 (przy opadach, wyłączenie): opad USTAŁ LUB CRT > próg wyłączenia
#     CRT LUB HRT > próg wyłączenia HRT.
#   2.4.15 (bez opadów, załączenie): CRT <= próg załączenia CRT (dwa czujniki)
#     ORAZ HRT <= próg załączenia HRT.
#   2.4.16 (bez opadów, wyłączenie): CRT > próg wyłączenia CRT LUB
#     HRT > próg wyłączenia HRT.
#
# Wartości progów - Tabela nr 5 (dwa czujniki): CRT zał=+2, wył=+3;
# HRT zał=+4, wył=+7. Tabela nr 6 (dwa czujniki): CRT zał=-5..-20 (przyjęto
# środek najbardziej zachowawczego końca zakresu: -5°C), wył = zał+3°C;
# HRT zał=+1, wył=+3. Próg opadu wg pkt 2.4.18.3: śnieg występuje do +4°C.

from dataclasses import dataclass
from datetime import datetime


@dataclass
class RowDataNorma:
    """Struktura odczytu zgodna z RowData z rdzen_kontrolera.py (dla spójności interfejsu)."""

    timestamp: datetime = None
    crt_temp: float = 0.0
    hrt_temp: float = 0.0
    at_temp: float = 0.0
    rh_humidity: float = 0.0
    pressure: float = 0.0
    precip: float = 0.0
    snow: float = 0.0


class AutomatPogodowyNorma:
    """Automat pogodowy dwuczujnikowy wg Iet-1, bez żadnych dodatków spoza normy."""

    def __init__(self, max_switches_per_day=12):
        self.heating_on = False
        self.row_data = RowDataNorma()
        self._flops_licznik = 0  # Licznik RZECZYWISTYCH FLOPs - patrz rdzen_kontrolera.KontrolerBazowy._dodaj_flopy.

        # --- LIMIT PRZEŁĄCZEŃ ---
        # Norma nie opisuje limitu dobowego przełączeń - dodany tu wyłącznie
        # dla uczciwego porównania w symulacji 1-sekundowej (żeby wszystkie
        # porównywane algorytmy miały tę samą osłonę przed "pstrykaniem" na
        # granicy progu, a różnice w wynikach odzwierciedlały logikę pogodową,
        # nie artefakty próbkowania).
        self.current_date = None
        self.switch_count_today = 0
        self.max_switches_per_day = max_switches_per_day

        # --- TABELA NR 5: progi przy opadach (dwa czujniki) ---
        self.at_threshold_precip = 4.0   # Pkt 2.4.18.3: śnieg w naszym klimacie do +4°C.
        self.crt_on_precip = 2.0
        self.crt_off_precip = 3.0
        self.hrt_on_precip = 4.0
        self.hrt_off_precip = 7.0

        # --- TABELA NR 6: progi bez opadów / suchy mróz (dwa czujniki) ---
        self.crt_on_dry = -5.0           # Zalecany zakres -5..-20°C - przyjęto koniec zachowawczy.
        self.crt_off_dry = self.crt_on_dry + 3.0  # "o 3°C wyższa od temperatury załączenia" (Tabela 6).
        self.hrt_on_dry = 1.0
        self.hrt_off_dry = 3.0

    def compute_control(self, row_data):
        self.row_data = RowDataNorma()
        self.row_data.timestamp = row_data['Timestamp']
        self.row_data.crt_temp = float(row_data['CRT_temp_niegrzana'])
        self.row_data.hrt_temp = float(row_data['HRT_temp_grzana'])
        self.row_data.at_temp = float(row_data['AT_temp_powietrza'])
        self.row_data.precip = float(row_data['PRECIP_opad'])
        self.row_data.snow = float(row_data['SNOW_snieg'])
        self.row_data.rh_humidity = float(row_data.get('RH_wilgotnosc_wzgledna', 0.0))
        self.row_data.pressure = float(row_data.get('PRES_cisnienie', 0.0))

        # 1. Reset licznika przełączeń z nastaniem nowego dnia.
        active_date = self.row_data.timestamp.date()
        if self.current_date != active_date:
            self.current_date = active_date
            self.switch_count_today = 0

        # 2. Wykrycie opadu (czujnik wilgoci / śniegu nawiewanego - tu: PRECIP_opad/SNOW_snieg > 0),
        #    ograniczone do temperatur, w których w naszym klimacie w ogóle występuje opad śniegu
        #    (pkt 2.4.18.3).
        opad_wykryty = (self.row_data.precip > 0.0 or self.row_data.snow > 0.0) \
            and self.row_data.at_temp <= self.at_threshold_precip

        previous_state = self.heating_on
        target_state = self.heating_on

        # 3. LOGIKA DECYZYJNA AUTOMATU POGODOWEGO (pkt 2.4.13 - 2.4.16, wariant dwa czujniki).
        if opad_wykryty:
            if not self.heating_on:
                # Pkt 2.4.13.3: obie temperatury muszą być poniżej progów załączenia.
                if self.row_data.crt_temp <= self.crt_on_precip and self.row_data.hrt_temp <= self.hrt_on_precip:
                    target_state = True
            else:
                # Pkt 2.4.14.3: wystarczy, że jedna przekroczy próg wyłączenia.
                if self.row_data.crt_temp > self.crt_off_precip or self.row_data.hrt_temp > self.hrt_off_precip:
                    target_state = False
        else:
            if not self.heating_on:
                # Pkt 2.4.15.2: obie temperatury muszą być poniżej progów załączenia bez opadów.
                if self.row_data.crt_temp <= self.crt_on_dry and self.row_data.hrt_temp <= self.hrt_on_dry:
                    target_state = True
            else:
                # Pkt 2.4.16.2: wystarczy, że jedna przekroczy próg wyłączenia bez opadów.
                if self.row_data.crt_temp > self.crt_off_dry or self.row_data.hrt_temp > self.hrt_off_dry:
                    target_state = False

        # 4. Limit dobowy przełączeń (patrz komentarz w __init__).
        if target_state != previous_state:
            if self.switch_count_today < self.max_switches_per_day:
                self.heating_on = target_state
                self.switch_count_today += 1
            # W przeciwnym razie limit wyczerpany - zostajemy przy poprzednim stanie.

        # 5. Wyjście binarne: automat pogodowy wg normy zna tylko załącz/wyłącz.
        self._flops_licznik += 18  # Porównania progów + logika stanu (stały koszt/krok).
        return 100.0 if self.heating_on else 0.0
