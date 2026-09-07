# Algorytmy/funkcja_ryzyka_ladrc.py
#
# ALGORYTM: funkcja ryzyka + Liniowe ADRC (Active Disturbance Rejection
# Control, Gao 2003 - "Scaling and bandwidth-parameterization based controller
# tuning") zamiast PID wokół temperatury zadanej. Wyznaczanie temperatury
# zadanej jest WSPÓLNE z pozostałymi wariantami funkcji ryzyka - patrz
# funkcja_ryzyka_wspolne.py (KontrolerRyzykaBazowy._evaluate_risk_setpoint) -
# różni się WYŁĄCZNIE mechanizmem regulacji WOKÓŁ tego celu. Matematyka
# wspólna z wariantem nieliniowym (NADRC) - patrz funkcja_ryzyka_adrc_wspolne.py.
#
# W ODRÓŻNIENIU od risk_function_pid (PI - całkuje błąd w czasie), tu Extended
# State Observer (ESO, dwustanowy: z1≈HRT, z2≈"całkowite zakłócenie") w
# czasie rzeczywistym ŚLEDZI różnicę między uproszczonym modelem pierwszego
# rzędu a prawdziwym obiektem, i prawo sterowania AKTYWNIE ją odejmuje -
# regulator nie musi znać dokładnego modelu (opóźnienie L, drugi biegun T2),
# musi go tylko na bieżąco obserwować. Sterowanie liczone na ESTYMOWANYM z1,
# nie na surowym pomiarze HRT - ESO filtruje szum czujnika, zanim trafi do
# prawa sterowania (dodatkowa odporność, której PID nie ma wprost).
#
# PRZY STARCIE wykonuje ten sam JEDNORAZOWY autotest co risk_function_pid
# (patrz KontrolerRyzykaBazowy._autotest_startowy) - dopóki trwa, grzeje pełną
# mocą. Po udanej identyfikacji przelicza b0/omega_c/omega_o z ŚWIEŻO
# zidentyfikowanych K/T1/T2/L (patrz wylicz_parametry_adrc) - dostraja się
# więc do REALNEGO obiektu, nie do wartości poznanych wcześniej gdzie indziej.

from funkcja_ryzyka_wspolne import KontrolerRyzykaBazowy
from funkcja_ryzyka_adrc_wspolne import (
    wylicz_parametry_adrc, ADRC_FALLBACK_K, ADRC_FALLBACK_T1, ADRC_FALLBACK_T2, ADRC_FALLBACK_L,
)


class KontrolerRyzykaLADRC(KontrolerRyzykaBazowy):

    def __init__(self, max_switches_per_day=12):
        super().__init__()

        # max_switches_per_day przyjmowane wyłącznie dla spójności interfejsu z
        # rejestr_algorytmow.stworz_kontroler - regulator ciągły nie ma
        # dyskretnych przełączeń do ograniczania, więc parametr nie jest tu używany.
        self.max_switches_per_day = max_switches_per_day

        # --- NASTAWY ADRC - fabryczne (z ADRC_FALLBACK_*), dopóki autotest nie
        # zidentyfikuje obiektu na żywo (patrz risk_function_ladrc niżej). ---
        self._b0, self._omega_c, self._omega_o = wylicz_parametry_adrc(
            ADRC_FALLBACK_K, ADRC_FALLBACK_T1, ADRC_FALLBACK_T2, ADRC_FALLBACK_L)
        self._nastawy_adrc_przeliczone = False

        # --- STAN ESO (Extended State Observer) ---
        self._z1 = None      # estymata HRT [°C] - None dopóki pierwszy pomiar nie zainicjalizuje
        self._z2 = 0.0        # estymata "całkowitego zakłócenia" [°C/s]
        self._poprzednia_moc_procent = 0.0   # moc FAKTYCZNIE zadziałana w poprzednim kroku - wejście ESO
        self._adrc_prev_time = None

    def risk_function_ladrc(self, row_data):
        """
        Ta sama logika ryzyka co risk_function/risk_function_pid (patrz
        KontrolerRyzykaBazowy._evaluate_risk_setpoint), ale regulacja wokół
        temperatury zadanej przez liniowe ADRC (ESO + liniowe prawo
        sterowania) zamiast PI.

        Zwraca:
            (moc_procent, diagnostyka) - moc_procent w zakresie [0, 100] (float),
            diagnostyka jak w risk_function_pid plus 'adrc_z1_est_hrt'
            (estymata ESO temperatury szyny) i 'adrc_z2_est_zaklocenie'
            (estymata "całkowitego zakłócenia", °C/s) - (albo tylko
            {'faza': 'autotest', ...} dopóki trwa autotest startowy).
        """
        if self._autotest_startowy(row_data):
            return self._ostatnia_moc_autotestu, {'faza': 'autotest', 'autotest_wynik': self.autotest_result}

        # Przeliczenie nastaw ADRC ze ŚWIEŻO zidentyfikowanych K/T1/T2/L -
        # dokładnie RAZ, tuż po zakończeniu autotestu (jak SIMC w
        # funkcja_ryzyka_pid.py). Jeśli identyfikacja się nie powiodła
        # (fit_ok=False), zostajemy przy nastawach fabrycznych.
        if not self._nastawy_adrc_przeliczone:
            wynik = self.autotest_result
            if wynik is not None and wynik['fit_ok']:
                self._b0, self._omega_c, self._omega_o = wylicz_parametry_adrc(
                    wynik['K'], wynik['T1'], wynik['T2'], wynik['L'])
            self._nastawy_adrc_przeliczone = True

        timestamp = row_data['Timestamp']
        hrt_temp = float(row_data['HRT_temp_grzana'])
        target_temperature, need_heat, reason, forecast_min_c, warmup_soon = \
            self._evaluate_risk_setpoint(row_data)

        if self._z1 is None:
            self._z1 = hrt_temp  # inicjalizacja ESO pierwszym prawdziwym pomiarem, nie zerem

        dt = (timestamp - self._adrc_prev_time).total_seconds() if self._adrc_prev_time else 1.0
        dt = max(dt, 1e-6)
        beta01 = 2.0 * self._omega_o          # wzmocnienia ESO z rozmieszczenia biegunów w -omega_o (podwójny biegun)
        beta02 = self._omega_o ** 2

        # --- Extended State Observer - liczony ZAWSZE, niezależnie od
        # need_heat, żeby estymata zakłócenia była aktualna, gdy grzanie znów
        # będzie potrzebne. Wejście b0*u używa mocy z POPRZEDNIEGO kroku (to,
        # co faktycznie zadziałało na obiekt między poprzednim a bieżącym
        # pomiarem), nie mocy dopiero co wyliczanej w tym kroku. ---
        e_obserwatora = self._z1 - hrt_temp
        z1_nowe = self._z1 + dt * (self._z2 - beta01 * e_obserwatora + self._b0 * self._poprzednia_moc_procent)
        z2_nowe = self._z2 + dt * (-beta02 * e_obserwatora)
        self._z1, self._z2 = z1_nowe, z2_nowe

        if not need_heat:
            power_percent = 0.0
        else:
            # Prawo sterowania liczone na ESTYMOWANYM stanie z1 (nie na
            # surowym pomiarze) - ESO filtruje szum czujnika. Odejmowanie z2
            # to samo "odrzucanie zakłócenia" - reguluje tak, jakby obiekt
            # był idealnym integratorem ẏ=b0*u, kompensując resztę na bieżąco.
            error = target_temperature - self._z1
            u0 = self._omega_c * error
            power_percent = (u0 - self._z2) / self._b0
            power_percent = min(max(power_percent, 0.0), 100.0)

        self._poprzednia_moc_procent = power_percent
        self._adrc_prev_time = timestamp

        self._krok_modelu(power_percent)
        self._dodaj_flopy(20)  # ESO (2 stany liniowe) + prawo sterowania - na wierzchu setpointu z _evaluate_risk_setpoint.

        diagnostics = {
            'target_temperature': target_temperature,
            'need_heat': need_heat,
            'reason': reason,
            'forecast_min_c': forecast_min_c,
            'warmup_soon': warmup_soon,
            'adrc_z1_est_hrt': self._z1,
            'adrc_z2_est_zaklocenie': self._z2,
        }
        return power_percent, diagnostics
