# Algorytmy/funkcja_ryzyka_model_adaptacyjny.py
#
# ALGORYTM: funkcja ryzyka (ta sama logika celu co risk_function_pid/risk_function_ladrc -
# patrz KontrolerRyzykaBazowy._evaluate_risk_setpoint, CRT jako wyznacznik), ale regulacja
# wykonawcza NIE opiera się na jednorazowym autoteście (K/T1/T2/L zidentyfikowane RAZ na
# starcie i potem zamrożone, jak w PID/ADRC/LADRC/NADRC) - tu obiekt (kanał moc->HRT,
# pogoda->HRT, słońce->HRT) jest identyfikowany NA ŻYWO metodą RLS (model_obiektu_rls.py -
# WSPÓLNY z funkcja_ryzyka_adrc_model_adaptacyjny.py i funkcja_mpc_model_adaptacyjny.py,
# 2026-10-02), więc model "się zmienia" przez cały przebieg, a nie tylko raz na starcie.
# Pomysł użytkownika (2026-10-01): sam model obiektu powinien też się uczyć, jak grzałka
# na niego reaguje oraz jak temperatura powietrza i nasłonecznienie wpływają na całość.
#
# STEROWANIE = ADAPTACYJNY FEEDFORWARD (z aktualnego a/b/c, odwrócony model: "jaka moc
# utrzyma HRT przy celu") + niewielka PI korekta na wierzchu (ten sam wzorzec
# anti-windup co funkcja_ryzyka_pid.py) - feedforward robi większość pracy i zmienia się
# na żywo z modelem, PI tylko sprząta resztę błędu (niedokładność modelu / szum RLS).
# Cel pętli wykonawczej jest w skali HRT (hrt_target_c), NIE w skali CRT z
# _evaluate_risk_setpoint (ten target jest kalibrowany do progów CRT, np. -5..7°C - użycie
# go bezpośrednio jako celu HRT powtórzyłoby błąd skali CRT/HRT znaleziony wcześniej w
# ADRC, patrz funkcja_ryzyka_adrc_wspolne.py). _evaluate_risk_setpoint odpowiada WYŁĄCZNIE
# za to, CZY grzać (need_heat) - ile i jak, decyduje already ten plik, w skali HRT.
#
# Parametry konstruktora (hrt_target_c/kp_tempo_podejscia/pi_kc_korekta_percent/
# pi_ti_korekta_s/lam_zapominania) - DOMYŚLNIE takie same liczby jak wcześniej (bez
# nadpisania zachowuje się identycznie jak przed refaktorem 2026-10-02) - wystawione jako
# argumenty, żeby testy/strojenie_modele_adaptacyjne.py mogło je przeszukiwać.

from funkcja_ryzyka_wspolne import KontrolerRyzykaBazowy
from model_obiektu_rls import ModelObiektuRLS, A_MIN, LAMBDA_ZAPOMINANIA_DOMYSLNA

# --- Cel pętli wykonawczej, w skali HRT (NIE CRT - patrz nagłówek). 5.0°C: bezpieczny
# margines nad progiem 2.0°C użytym w kara_bezpieczenstwa (symulacja_fizyczna.py) dla
# deficytu marznącego deszczu - utrzymanie HRT tutaj daje ~3°C zapasu. ---
HRT_TARGET_C_DOMYSLNE = 5.0
KP_TEMPO_PODEJSCIA_DOMYSLNE = 1.0 / 600.0   # Docelowe tempo podejścia do celu: stała czasowa ~600s (10 min).

# PI korekty NA WIERZCHU feedforward - małe, stałe nastawy (feedforward niesie większość
# pracy; to tylko "sprzątanie" resztek błędu modelu, nie główny regulator).
PI_KC_KOREKTA_PERCENT_DOMYSLNE = 0.8
PI_TI_KOREKTA_S_DOMYSLNE = 1800.0


class KontrolerRyzykaModelAdaptacyjny(KontrolerRyzykaBazowy):

    def _autotest_startowy(self, row_data):
        return False  # Brak jednorazowego autotestu - model RLS uczy się od pierwszego kroku.

    def __init__(self, max_switches_per_day=12, hrt_target_c=HRT_TARGET_C_DOMYSLNE,
                 kp_tempo_podejscia=KP_TEMPO_PODEJSCIA_DOMYSLNE,
                 pi_kc_korekta_percent=PI_KC_KOREKTA_PERCENT_DOMYSLNE,
                 pi_ti_korekta_s=PI_TI_KOREKTA_S_DOMYSLNE,
                 lam_zapominania=LAMBDA_ZAPOMINANIA_DOMYSLNA):
        super().__init__()
        self.max_switches_per_day = max_switches_per_day
        self.hrt_target_c = hrt_target_c
        self.kp_tempo_podejscia = kp_tempo_podejscia
        self.pi_kc_korekta_percent = pi_kc_korekta_percent
        self.pi_ti_korekta_s = pi_ti_korekta_s

        self._model = ModelObiektuRLS(lam=lam_zapominania)

        self._pid_integral = 0.0
        self._pid_prev_error = 0.0
        self._pid_prev_time = None

    def risk_function_model_adaptacyjny(self, row_data):
        czas_teraz = row_data['Timestamp']
        hrt_temp = float(row_data['HRT_temp_grzana'])
        at_temp = float(row_data['AT_temp_powietrza'])

        a, b, c, proxy = self._model.aktualizuj_i_pobierz(czas_teraz, hrt_temp, at_temp)

        target_temperature, need_heat, reason, forecast_min_c, warmup_soon = \
            self._evaluate_risk_setpoint(row_data)

        if not need_heat:
            self._pid_integral = 0.0
            self._pid_prev_error = 0.0
            self._pid_prev_time = czas_teraz
            power_percent = 0.0
        else:
            tempo_docelowe = self.kp_tempo_podejscia * (self.hrt_target_c - hrt_temp)
            feedforward_frac = (tempo_docelowe - b * (at_temp - hrt_temp) - c * proxy) / max(a, A_MIN)
            feedforward_percent = feedforward_frac * 100.0

            error = self.hrt_target_c - hrt_temp
            dt = (czas_teraz - self._pid_prev_time).total_seconds() if self._pid_prev_time else 1.0
            dt = max(dt, 1e-6)
            proportional = self.pi_kc_korekta_percent * error

            unclamped_estimate = feedforward_percent + proportional \
                + self.pi_kc_korekta_percent / self.pi_ti_korekta_s * self._pid_integral
            if 0.0 < unclamped_estimate < 100.0 or (unclamped_estimate <= 0.0 and error > 0) \
                    or (unclamped_estimate >= 100.0 and error < 0):
                self._pid_integral += error * dt

            integral_term = (self.pi_kc_korekta_percent / self.pi_ti_korekta_s) * self._pid_integral
            power_percent = feedforward_percent + proportional + integral_term
            power_percent = min(max(power_percent, 0.0), 100.0)

            self._pid_prev_error = error
            self._pid_prev_time = czas_teraz

        self._model.zapamietaj_regresor(czas_teraz, hrt_temp, at_temp, power_percent / 100.0, proxy)

        self._krok_modelu(power_percent)
        self._dodaj_flopy(40)  # RLS (3x3) + odwrócenie modelu (feedforward) + PI korekta.

        diagnostics = {
            'target_temperature': target_temperature,
            'need_heat': need_heat,
            'reason': reason,
            'forecast_min_c': forecast_min_c,
            'warmup_soon': warmup_soon,
            'model_a_grzalka': float(a),
            'model_b_pogoda': float(b),
            'model_c_slonce': float(c),
        }
        return power_percent, diagnostics
