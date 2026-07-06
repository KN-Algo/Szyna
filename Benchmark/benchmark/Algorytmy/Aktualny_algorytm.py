# algorytmy/histereza_limit.py

class RailHeatingController:
    def __init__(self, max_switches_per_day=12):
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

    def compute_control(self, row_data):
        timestamp = row_data['Timestamp']
        crt = float(row_data['CRT_temp_niegrzana'])
        hrt = float(row_data['HRT_temp_grzana'])
        at = float(row_data['AT_temp_powietrza'])
        precip = float(row_data['PRECIP_opad'])
        snow = float(row_data['SNOW_snieg'])
        
        # 1. Reset licznika z nastaniem nowego dnia (czysta karta na dobę)
        active_date = timestamp.date()
        if self.current_date != active_date:
            self.current_date = active_date
            self.switch_count_today = 0 

        # 2. Detekcja obecności opadu atmosferycznego (Pkt 2.4.13.1 & 2.4.18.3) [cite: 595, 623]
        has_precipitation = (precip > 0.0 or snow > 0.0) and (at <= self.at_threshold_precip)
        
        # Zapamiętujemy stan binarnego wyjścia przed podjęciem nowej decyzji
        previous_state = self.heating_on
        target_state = self.heating_on

        # 3. IMPLEMENTACJA LOGIKI DECYZYJNEJ AUTOMATU POGODOWEGO (ROZDZIAŁ 2.4) [cite: 553]
        if has_precipitation:
            # --- TRYB PRACY: OPADY (Sekcje 2.4.13 i 2.4.14) --- [cite: 594, 598]
            if not self.heating_on:
                # Załączenie: Obie temperatury (CRT i HRT) muszą spaść poniżej progów (Pkt 2.4.13.3) [cite: 597, 598]
                if crt <= self.crt_on_precip and hrt <= self.hrt_on_precip:
                    target_state = True
            else:
                # Wyłączenie: Wystarczy, że co najmniej jedna przekroczy próg (Pkt 2.4.14.3) [cite: 600]
                if crt > self.crt_off_precip or hrt > self.hrt_off_precip:
                    target_state = False
        else:
            # --- TRYB PRACY: SUCHY MRÓZ / BEZ OPADÓW (Sekcje 2.4.15 i 2.4.16) --- [cite: 601, 606]
            # Układ reaguje automatycznie tylko wtedy, gdy temperatura powietrza spadnie poniżej -5°C 
            if at <= self.at_low_freeze:
                if not self.heating_on:
                    # Załączenie bez opadów: Szyna nieogrzewana oraz ogrzewana w ryzach mrozu (Pkt 2.4.15.2) [cite: 605]
                    # Instrukcja wymaga, aby temperatura załączenia była niska, a HRT wynosiła max +1°C 
                    if hrt <= self.hrt_on_dry and crt <= (self.at_low_freeze + 3.0):
                        target_state = True
                else:
                    # Wyłączenie bez opadów: Gdy ogrzana szyna osiągnie bezpieczne +3°C (Pkt 2.4.16.2) [cite: 608, 621]
                    if hrt > self.hrt_off_dry:
                        target_state = False
            else:
                # Jeśli nie ma opadów, a temperatura otoczenia jest względnie wysoka (powyżej -5°C),
                # grzanie rozjazdu jest ekonomicznie nieuzasadnione i zostaje odcięte (Pkt 2.5.3)[cite: 557, 648].
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

        # 5. BINARNE WYJŚCIE STERUJĄCE: Zwraca wyłącznie 0.0% (wyłączony) lub 100.0% (pełna moc)
        return 100.0 if self.heating_on else 0.0