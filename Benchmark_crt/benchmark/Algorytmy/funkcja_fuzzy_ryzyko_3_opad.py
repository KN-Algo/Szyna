# Algorytmy/funkcja_fuzzy_ryzyko_3_opad.py
#
# Jak funkcja_fuzzy_ryzyko_3.py (cel z funkcji ryzyka, wykonawczo silnik FL3 -
# moc rozmyta liczona RAZ na okno 60s, rozdzielona w czasie PWM), ale setpoint
# liczony przez KontrolerRyzykaOpadBazowy._evaluate_risk_setpoint_z_opadem -
# dokłada prognozę OPADU (przewidywanie_opadow.py) jako dodatkowy warunek
# zwalniający z grzania przy cienkiej, zanikającej pokrywie śniegu (patrz
# funkcja_ryzyka_wspolne.KontrolerRyzykaOpadBazowy). _evaluate_risk_setpoint_z_opadem
# jest wołane co sekundę niezależnie od cyklu PWM (żeby pamięć/prognoza
# Kalmana widziała KAŻDĄ próbkę), ale nowy cel dla silnika rozmytego pobierany
# jest tylko na początku każdego cyklu PWM.

from funkcja_ryzyka_wspolne import KontrolerRyzykaOpadBazowy
from silniki_fuzzy import wnioskowanie_fl_podstawowe, WykonawcaPWM


class KontrolerFuzzyRyzyko3Opad(KontrolerRyzykaOpadBazowy):

    def __init__(self, max_switches_per_day=12):
        super().__init__()
        self.max_switches_per_day = max_switches_per_day
        self.pwm = WykonawcaPWM(okres_cyklu=60)

    def fuzzy_ryzyko_opad(self, row_data):
        if self._autotest_startowy(row_data):
            return self._ostatnia_moc_autotestu, {'faza': 'autotest', 'autotest_wynik': self.autotest_result}

        hrt_temp = float(row_data['HRT_temp_grzana'])
        precip = float(row_data['PRECIP_opad'])
        snow = float(row_data['SNOW_snieg'])
        target_temperature, need_heat, reason, forecast_min_c, warmup_soon = \
            self._evaluate_risk_setpoint_z_opadem(row_data)

        if self.pwm.na_poczatku_cyklu:
            if not need_heat:
                self.pwm.ustaw_moc_cyklu(0.0)
            else:
                jest_snieg = snow > 0.0
                jest_deszcz = precip > 0.0
                blad_T = target_temperature - hrt_temp
                wynik = wnioskowanie_fl_podstawowe(blad_T, hrt_temp, jest_snieg, jest_deszcz)
                self.pwm.ustaw_moc_cyklu(wynik)
                self._dodaj_flopy(40)  # Silnik FL1, liczony RAZ na początku cyklu PWM (60s).

        power_percent = self.pwm.krok()
        self._dodaj_flopy(2)  # Krok PWM.
        self._krok_modelu(power_percent)

        diagnostics = {
            'target_temperature': target_temperature,
            'need_heat': need_heat,
            'reason': reason,
            'forecast_min_c': forecast_min_c,
            'warmup_soon': warmup_soon,
        }
        return power_percent, diagnostics
