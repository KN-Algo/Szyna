class RailHeatingController:
    def __init__(self, target_temp=4.0, hysteresis=1.0):
        self.target_temp = target_temp
        self.hysteresis = hysteresis
        self.heating_on = False
        
        # --- NOWE ZMIENNE DLA LIMITU PRZEŁĄCZEŃ ---
        self.current_date = None      # Śledzenie bieżącego dnia (np. "2024-11-01")
        self.switch_count_today = 0   # Licznik przełączeń w danym dniu
        self.max_switches_per_day = 5 # Maksymalny limit

    def compute_control(self, row_data):
        timestamp = row_data['Timestamp']
        crt = float(row_data['CRT_temp_niegrzana'])
        hrt = float(row_data['HRT_temp_grzana'])
        at = float(row_data['AT_temp_powietrza'])
        rh = float(row_data['RH_wilgotnosc'])
        press = float(row_data['PRESS_cisnienie'])
        precip = float(row_data['PRECIP_opad'])
        snow = float(row_data['SNOW_snieg'])
        
        # 1. Sprawdzenie/Reset licznika przy nowym dniu
        active_date = timestamp.date()
        if self.current_date != active_date:
            self.current_date = active_date
            self.switch_count_today = 0 # Nowy dzień, czysta karta

        # 2. Wyznaczenie warunków algorytmu (tak jak miałeś)
        ice_risk = (at <= 2.0) and (precip > 0.0 or snow > 0.0 or rh > 80.0)
        
        # Zapamiętujemy stan sprzed decyzji, żeby sprawdzić, czy nastąpiło przełączenie
        previous_state = self.heating_on

        # 3. Logika wyznaczenia CHĘCI przełączenia stanu
        target_state = self.heating_on
        if self.heating_on:
            if hrt >= (self.target_temp + self.hysteresis):
                target_state = False
        else:
            if hrt <= (self.target_temp - self.hysteresis) or ice_risk:
                target_state = True

        # 4. Blokada: Jeśli stan ma się zmienić, sprawdź czy nie przekroczono limitu 5 razy
        if target_state != previous_state:
            if self.switch_count_today < self.max_switches_per_day:
                self.heating_on = target_state
                self.switch_count_today += 1
                # Opcjonalnie: można logować w pliku, że nastąpiło przełączenie nr X
            else:
                # Limit wyczerpany! Zostajemy przy starym stanie (blokada)
                pass

        # Zwraca moc od 0.0 do 100.0 %
        control_power = 100.0 if self.heating_on else 0.0
        return control_power