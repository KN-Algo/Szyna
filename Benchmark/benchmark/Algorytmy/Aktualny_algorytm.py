# algorytmy/histereza_limit.py

from dataclasses import dataclass
from datetime import datetime

@dataclass
class RowData:
    """Struktura danych reprezentująca pojedynczy odczyt z czujników."""

    timestamp: datetime = None
    crt_temp: float = 0.0  # Temperatura szyny nieogrzewanej (CRT_temp_niegrzana)
    hrt_temp: float = 0.0  # Temperatura szyny ogrzewanej (HRT_temp_grzana)
    at_temp: float = 0.0  # Temperatura powietrza (AT_temp_powietrza)
    rh_humidity: float = 0.0  # Wilgotność względna (RH_wilgotnosc_wzgledna)
    pressure: float = 0.0  # Ciśnienie atmosferyczne (PRES_cisnienie)
    precip: float = 0.0  # Opad atmosferyczny (PRECIP_opad)
    snow: float = 0.0  # Śnieg (SNOW_snieg)
    pwr_l1: float = 0.0  # Moc L1 (PWR_L1)
    pwr_l2: float = 0.0  # Moc L2 (PWR_L2)


class RailHeatingController: 

    sensor_history = []  # Lista przechowująca historię odczytów z czujników

    def __init__(self, max_switches_per_day=12):

        self.row_data = RowData()

        self.heating_on = False
        
        # --- LIMIT PRZEŁĄCZEŃ ---
        self.current_date = None      # Śledzenie bieżącego dnia
        self.switch_count_today = 0   # Licznik przełączeń w danym dniu
        self.max_switches_per_day = max_switches_per_day

        # --- PARAMETRY ZGODNIE Z INSTRUKCJĄ LET-1 PKP PLK S.A. ---
        # 1. Warunki przy opadach (Tabela nr 5, wariant dla dwóch czujników: CRT i HRT)
        self.at_threshold_precip = 4.0      # Śnieg występuje w naszym klimacie do +4°C (Pkt 2.4.18.3) [cite: 623]
        self.crt_on_precip = 2.0            # CRT załączenie przy opadzie: +2°C (Tabela nr 5) 
        self.crt_off_precip = 3.0           # CRT wyłączenie przy opadach: +3°C (Tabela nr 5) 
        self.hrt_on_precip = 4.0            # HRT załączenie przy opadach: +4°C (Tabela nr 5) 
        self.hrt_off_precip = 7.0           # HRT wyłączenie przy opadach: +7°C (Tabela nr 5) 

        # 2. Warunki bez opadów / suchy mróz (Tabela nr 6, wariant dla dwóch czujników)
        self.at_low_freeze = -5.0           # Suchy mróz dolna granica: -5°C (Tabela nr 6) 
        self.hrt_on_dry = 1.0               # HRT załączenie bez opadów: +1°C (Tabela nr 6) 
        self.hrt_off_dry = 3.0              # HRT wyłączenie bez opadów: +3°C (Tabela nr 6)


    

    def raining_prediction(self):
        """
        Metoda będzie zwraca tablice z 8 wartościami i wartością predyckji od 0 do 3 infomrujaca 
        o intesywności opadu w najbliższych 2 godzinach (krok 15 minutowy).
        """
        array = [0, 0, 0, 0, 0, 0, 0, 0]
        return array

    def temperature_prediction(self):
        """
        Metoda będzie zwraca tablice z 8 wartościami i wartością predyckji od -10 do 10 infomrujaca 
        o temperaturze w najbliższych 2 godzinach (krok 15 minutowy).
        """
        array = [0, 0, 0, 0, 0, 0, 0, 0]
        return array

    def calculate_risk_level(self, row_data) -> int:
        """
        Metoda oceniająca ryzyko oblodzenia/zamarzania w skali od 0 do 10.
        """

        # Progi detekcji opadu (wartości w mm/s bywają bardzo małe)
        is_raining = self.precip > 0.0001
        is_snowing = self.snow > 0.0001

        # --- 10 & 9: MARZNĄCY DESZCZ (Krytyczne zagrożenie) ---
        if is_raining and (self.crt_temp <= 1.0 or self.at_temp <= 1.0):
            return 10 if self.precip > 0.001 else 9  # 10 dla ulewy, 9 dla mniejszego opadu

        # --- 8 & 7: INTENSYWNY ŚNIEG (Wysokie zagrożenie zasypaniem/zablokowaniem) ---
        if is_snowing and self.crt_temp <= 2.0:
            return 8 if self.snow > 0.001 else 7    # 8 dla śnieżycy, 7 dla lekkiego śniegu

        # --- 6 & 5: WILGOĆ I MRÓZ (Średnie zagrożenie - szron, szadź, gołoledź) ---
        if self.crt_temp <= 0.5 and self.rh_humidity > 85.0:
            return 6 if self.rh_humidity > 95.0 else 5       # 6 przy ekstremalnej wilgotności

        # --- 4 & 3: SUCHY MRÓZ (Niskie/Średnie zagrożenie - profilaktyka przed wychłodzeniem stali) ---
        if self.crt_temp <= -3.0:
            return 4                           # Głęboki mróz, stal jest bardzo zimna
        if self.crt_temp <= 0.0:
            return 3                           # Lekki mróz wokół zera

        # --- 2 & 1: POTENCJALNE ZAGROŻENIE (Niskie ryzyko) ---
        if (is_raining or is_snowing) and self.crt_temp <= 3.0:
            return 2                           # Opad przy lekkim plusie (może zaraz zamarznąć)
        if self.at_temp <= 3.0:
            return 1                           # Po prostu zimno, ale sucho i bez krytycznej wilgoci

        # --- 0: PEŁNE BEZPIECZEŃSTWO ---
        return 0

    def compute_control(self, row_data):
        self.row_data = RowData()
        self.row_data.timestamp = row_data['Timestamp']
        self.row_data.crt_temp = float(row_data['CRT_temp_niegrzana'])
        self.row_data.hrt_temp = float(row_data['HRT_temp_grzana'])
        self.row_data.at_temp = float(row_data['AT_temp_powietrza'])
        self.row_data.precip = float(row_data['PRECIP_opad'])
        self.row_data.snow = float(row_data['SNOW_snieg'])
        self.row_data.rh_humidity = float(row_data['RH_wilgotnosc_wzgledna'])
        self.row_data.pressure = float(row_data['PRES_cisnienie'])
        self.row_data.pwr_l1 = float(row_data['PWR_L1'])
        self.row_data.pwr_l2 = float(row_data['PWR_L2'])


        risk = self.calculate_risk_level(row_data)

        
        # 1. Reset licznika z nastaniem nowego dnia (czysta karta na dobę)
        active_date = self.row_data.timestamp.date()
        if self.current_date != active_date:
            self.current_date = active_date
            self.switch_count_today = 0 

        # 2. Detekcja obecności opadu atmosferycznego (Pkt 2.4.13.1 & 2.4.18.3) 
        has_precipitation = (self.row_data.precip > 0.0 or self.row_data.snow > 0.0) and (self.row_data.at_temp <= self.row_data.at_threshold_precip)
        
        # Zapamiętujemy stan binarnego wyjścia przed podjęciem nowej decyzji
        previous_state = self.heating_on
        target_state = self.heating_on

        # 3. IMPLEMENTACJA LOGIKI DECYZYJNEJ AUTOMATU POGODOWEGO (ROZDZIAŁ 2.4)
        if has_precipitation:
            # --- TRYB PRACY: OPADY (Sekcje 2.4.13 i 2.4.14) --- 
            if not self.heating_on:
                # Załączenie: Obie temperatury (CRT i HRT) muszą spaść poniżej progów (Pkt 2.4.13.3) 
                if self.row_data.crt_temp <= self.row_data.crt_on_precip and self.row_data.hrt_temp <= self.row_data.hrt_on_precip:
                    target_state = True
            else:
                # Wyłączenie: Wystarczy, że co najmniej jedna przekroczy próg (Pkt 2.4.14.3)
                if self.row_data.crt_temp > self.row_data.crt_off_precip or self.row_data.hrt_temp > self.row_data.hrt_off_precip:
                    target_state = False
        else:
            # --- TRYB PRACY: SUCHY MRÓZ / BEZ OPADÓW (Sekcje 2.4.15 i 2.4.16) --- 
            # Układ reaguje automatycznie tylko wtedy, gdy temperatura powietrza spadnie poniżej -5°C 
            if self.row_data.at_temp <= self.row_data.at_low_freeze:
                if not self.heating_on:
                    # Załączenie bez opadów: Szyna nieogrzewana oraz ogrzewana w ryzach mrozu (Pkt 2.4.15.2)
                    # Instrukcja wymaga, aby temperatura załączenia była niska, a HRT wynosiła max +1°C 
                    if self.row_data.hrt_temp <= self.row_data.hrt_on_dry and self.row_data.crt_temp <= (self.row_data.at_low_freeze + 3.0):
                        target_state = True
                else:
                    # Wyłączenie bez opadów: Gdy ogrzana szyna osiągnie bezpieczne +3°C (Pkt 2.4.16.2) 
                    if self.row_data.hrt_temp > self.row_data.hrt_off_dry:
                        target_state = False
            else:
                # Jeśli nie ma opadów, a temperatura otoczenia jest względnie wysoka (powyżej -5°C),
                # grzanie rozjazdu jest ekonomicznie nieuzasadnione i zostaje odcięte (Pkt 2.5.3)
                if self.heating_on:
                    target_state = False

        # 4. BEZPIECZNIK SPRZĘTOWY: Sprawdzenie i blokada limitu dobowego przełączeń
        if target_state != previous_state:
            if self.switch_count_today < self.max_switches_per_day:
                self.heating_on = target_state
                self.switch_count_today += 1
            else:
                # Limit wyczerpany na dany dzień. Ignorujemy chęć przełączenia, zostajemy przy poprzednim stanie.
                pass

        self.sensor_history.append(self.row_data)  # Zapisujemy aktualny odczyt do historii

        # 5. BINARNE WYJŚCIE STERUJĄCE: Zwraca wyłącznie 0.0% (wyłączony) lub 100.0% (pełna moc)
        return 100.0 if self.heating_on else 0.0