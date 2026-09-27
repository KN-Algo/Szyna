# Algorytmy/funkcja_ryzyka_pid_kaskada.py
#
# ALGORYTM: kaskada DWÓCH regulatorów PI wokół funkcji ryzyka (Kalman) -
# risk_function_cascade_pi w rejestr_algorytmow.py.
#
# DLACZEGO KASKADA: risk_function_pid (funkcja_ryzyka_pid.py) liczy błąd
# regulacji WPROST względem CRT, ale CRT reaguje na moc grzania bardzo słabo i
# wolno (K_H_CRT_KONTROLER/T1_H_CRT_KONTROLER w rdzen_kontrolera.py - ZAŁOŻENIE
# z 2026-09-28, na życzenie użytkownika: "generalnie CRT reaguje na grzałkę,
# tylko bardzo słabo, ponieważ to duży obiekt" - NIE pomiar, identyfikacja_crt_miso.py
# nie dała czystego sygnału w żadną stronę). Regulator z bezpośrednim
# sprzężeniem na tak słaby/wolny kanał może nasycić się na 100% mocy na długo,
# bo "nie widzi" efektu własnego działania w rozsądnym czasie - risk_function_pid
# zostaje jako świadomie badany przypadek tego zjawiska, NIE jest tu zmieniany.
#
# KASKADA (standardowy wzorzec sterowania procesowego - pętla zewnętrzna
# wyznacza SETPOINT pętli wewnętrznej, patrz notatki/funkcja_ryzyka_dokladnie.md):
#   - Pętla ZEWNĘTRZNA (wolna, CRT): błąd = target_crt (z _evaluate_risk_setpoint,
#     jak w risk_function_pid) minus CRT_temp_niegrzana. Regulator PI daje
#     KOREKTĘ do bieżącego HRT -> hrt_setpoint, ograniczony do
#     [RISK_HRT_ABSOLUTE_FLOOR_C, HRT_LIMIT_OSTRZEGAWCZY_C] (te same stałe
#     bezpieczeństwa co reszta projektu).
#   - Pętla WEWNĘTRZNA (szybka, HRT): błąd = hrt_setpoint minus HRT_temp_grzana.
#     Regulator PI -> power_percent (0-100%) - ta sama zmienna, na którą moc
#     REALNIE i szybko wpływa, więc to sprzężenie działa poprawnie.
#
# STROJENIE (SIMC), OBIE pętle przeliczane RAZEM, z tego samego
# zidentyfikowanego K_hrt (patrz _simc_inner_pi/_simc_outer_pi):
#   - Wewnętrzna: lambda=theta (konwencja "agresywna", jak w funkcja_ryzyka_pid.py),
#     z autotestu NA ŻYWO (K/T1/T2/L identyfikowane ze skoku HRT) - wyjście w % mocy.
#   - Zewnętrzna: lambda=4*tau (ŚWIADOMIE bardziej zachowawcza niż gdziekolwiek
#     indziej w projekcie - patrz uzasadnienie w _simc_outer_pi: przy tak małym
#     wzmocnieniu tego kanału "agresywna" konwencja nasycałaby hrt_setpoint
#     praktycznie zawsze). "Obiekt" to hrt_setpoint -> CRT, o wzmocnieniu
#     STOSUNKOWYM K_H_CRT_KONTROLER/K_hrt (oba w °C na 100% mocy, więc skala
#     mocy się upraszcza) i stałej czasowej T1_H_CRT_KONTROLER
#     (rdzen_kontrolera.py, ZAŁOŻONA, bo ten kanał jest zbyt słaby/wolny, żeby
#     identyfikować go żywym skokiem w rozsądnym czasie) - wyjście w °C
#     (hrt_setpoint), NIE %.
#
# UCZCIWA OBSERWACJA (zmierzone 2026-09-28, patrz
# notatki/funkcja_ryzyka_dokladnie.md sekcja 11): w PEŁNYCH przebiegach
# symulacji (Kraków, najzimniejsze i marginalne okna) trajektoria mocy tego
# algorytmu wyszła BIT-A-BIT identyczna z risk_function_pid - NIE dlatego, że
# kaskada jest "atrapą" (jednostkowy test niżej pokazuje realną, stopniowaną
# odpowiedź dla umiarkowanych błędów CRT, np. błąd 1°C -> hrt_setpoint=-1,34°C,
# moc=7,8%), tylko dlatego, że w tych scenariuszach priorytety funkcji ryzyka
# (progi na AT, nie na CRT) uruchamiają grzanie dopiero, gdy błąd CRT jest już
# duży (rzędu kilkunastu °C) - "wąskie okno" łagodnej regulacji bywa więc zbyt
# krótkie/rzadkie, żeby się uwidocznić w zagregowanych statystykach. Prawdziwa
# wartość kaskady w tym projekcie jest więc bardziej STRUKTURALNA (prawdziwe,
# ograniczone sprzężenie zamiast założonego K=0) niż widoczna od razu w
# trajektorii mocy na tych konkretnych, bardzo mroźnych lokalizacjach.

from funkcja_ryzyka_wspolne import KontrolerRyzykaBazowy, RISK_HRT_ABSOLUTE_FLOOR_C
from rdzen_kontrolera import K_H_CRT_KONTROLER, T1_H_CRT_KONTROLER

# BENCHMARK_CRT: ta sama wartość co symulacja_fizyczna.HRT_LIMIT_OSTRZEGAWCZY_C
# (45°C - zabezpieczenie termiczne realnego urządzenia) - zduplikowana tu
# zamiast importowana z symulacja_fizyczna.py, bo moduły Algorytmy/ nie
# importują "w górę" modułu, który sam importuje moduły Algorytmy/ (ten sam
# wzorzec co K_W_CRT/T1_W_CRT/TZ_W_CRT w rdzen_kontrolera.py, duplikujące
# K_W/T1_W/TZ_W z symulacja_fizyczna.py).
HRT_LIMIT_OSTRZEGAWCZY_C = 45.0

# Obiekt zidentyfikowany wcześniej (patrz funkcja_ryzyka_pid.py, ten sam
# obiekt/test) - wartości ZAPASOWE, używane dopóki WŁASNY autotest tego
# kontrolera się nie zakończy. Źródło prawdy dla OBU pętli (wewnętrznej I
# zewnętrznej - patrz _simc_inner_pi/_simc_outer_pi niżej), żeby nie trzymać
# dwóch osobnych, ręcznie policzonych nastaw fabrycznych.
FALLBACK_K = 51.1163668
FALLBACK_T1 = 1120.914508
FALLBACK_T2 = 2450.968465
FALLBACK_L = 1194.184089


def _simc_inner_pi(K, T1, T2, L):
    """
    SIMC (Skogestad), konwencja lambda=theta - dokładnie jak
    funkcja_ryzyka_pid.KontrolerRyzykaPID._przelicz_nastawy_simc. Wyjście tej
    pętli to moc_procent (0-100%), stąd mnożnik *100 (K jest w °C na PEŁNĄ
    (100%, u_frakcja=1.0) moc - patrz konwencja w rdzen_kontrolera._krok_modelu).
    """
    tau = T1 + T2
    theta = L
    lam = theta
    kc = (1.0 / K) * (tau / (theta + lam)) * 100.0
    ti = min(tau, 4.0 * (theta + lam))
    return kc, ti


def _simc_outer_pi(k_hrt, k_crt_slaby=K_H_CRT_KONTROLER, t1_crt_slaby=T1_H_CRT_KONTROLER):
    """
    SIMC dla pętli ZEWNĘTRZNEJ (CRT -> hrt_setpoint, w °C - BEZ mnożnika *100,
    w odróżnieniu od _simc_inner_pi, bo wyjście tej pętli to temperatura, nie
    procent mocy).

    "Obiekt" tej pętli to hrt_setpoint -> CRT: skoro pętla WEWNĘTRZNA szybko
    (relatywnie do T1_H_CRT_KONTROLER=4h) sprowadza HRT do hrt_setpoint,
    efektywne wzmocnienie statyczne tej pętli to STOSUNEK dwóch znanych
    wzmocnień "moc -> temperatura" (oba w °C na 100% mocy, więc skala mocy się
    upraszcza): K_outer = k_crt_slaby / k_hrt [°C_CRT na °C_HRT] - Z ZAŁOŻENIA
    BARDZO MAŁE (słaby kanał), rzędu 0,09 (°C CRT na °C HRT).

    lambda = 4*tau (NIE tau, jak w _simc_inner_pi/reszcie projektu przy L=0) -
    ŚWIADOMIE bardziej zachowawczy wybór niż wszędzie indziej: przy tak małym
    K_outer, "agresywna" konwencja lambda=tau dałaby Kc≈1/K_outer≈10,6°C
    hrt_setpoint na °C błędu CRT - to nasyca hrt_setpoint (zakres tylko 55°C:
    RISK_HRT_ABSOLUTE_FLOOR_C..HRT_LIMIT_OSTRZEGAWCZY_C) już przy błędzie CRT
    rzędu ~5°C, czyli PRAKTYCZNIE ZAWSZE w warunkach tego projektu (zmierzone
    2026-09-28: przy lambda=tau kaskada dawała IDENTYCZNĄ trajektorię mocy co
    jednopętlowy risk_function_pid - 0/100% bez stanów pośrednich). lambda=4*tau
    daje Kc≈2,7 - nasycenie dopiero przy błędzie CRT rzędu ~20°C, co w
    symulacjach tego projektu faktycznie pozostawia widoczny zakres mocy
    pośredniej (patrz notatki/funkcja_ryzyka_dokladnie.md, sekcja 11).

    k_hrt: AKTUALNIE znane wzmocnienie mocy na HRT (fallback albo świeżo
    zidentyfikowane autotestem) - ten SAM parametr, którego używa
    _simc_inner_pi, żeby obie pętle były przestrajane SPÓJNIE z tego samego
    źródła prawdy o obiekcie.
    """
    k_outer = k_crt_slaby / k_hrt
    tau = t1_crt_slaby
    lam = 4.0 * tau
    kc = (1.0 / k_outer) * (tau / lam)
    ti = min(tau, 4.0 * lam)
    return kc, ti


class KontrolerRyzykaPIDKaskada(KontrolerRyzykaBazowy):

    def __init__(self, max_switches_per_day=12):
        super().__init__()

        # max_switches_per_day przyjmowane wyłącznie dla spójności interfejsu z
        # rejestr_algorytmow.stworz_kontroler - regulator ciągły nie ma
        # dyskretnych przełączeń do ograniczania.
        self.max_switches_per_day = max_switches_per_day

        # --- Obie pętle - nastawy FABRYCZNE (z FALLBACK_K/T1/T2/L), dopóki
        # WŁASNY autotest się nie zakończy - patrz _simc_inner_pi/_simc_outer_pi. ---
        self._pid_in_kc, self._pid_in_ti = _simc_inner_pi(FALLBACK_K, FALLBACK_T1, FALLBACK_T2, FALLBACK_L)
        self._pid_in_integral = 0.0
        self._pid_in_prev_error = 0.0
        self._pid_in_prev_time = None

        self._pid_out_kc, self._pid_out_ti = _simc_outer_pi(FALLBACK_K)
        self._pid_out_integral = 0.0
        self._pid_out_prev_error = 0.0
        self._pid_out_prev_time = None

        self._nastawy_simc_przeliczone = False

    def risk_function_cascade_pi(self, row_data):
        """
        Zwraca: (moc_procent, diagnostyka) - jak risk_function_pid, plus
        'hrt_setpoint' (wyjście pętli zewnętrznej) i osobne pid_error/pid_integral
        dla obu pętli.
        """
        if self._autotest_startowy(row_data):
            return self._ostatnia_moc_autotestu, {'faza': 'autotest', 'autotest_wynik': self.autotest_result}

        # Przeliczenie nastaw OBU pętli metodą SIMC z ŚWIEŻO zidentyfikowanych
        # K/T1/T2/L - dokładnie RAZ, tuż po autoteście (jak w
        # funkcja_ryzyka_pid.py). Pętla zewnętrzna używa tego samego świeżego
        # K_hrt (patrz _simc_outer_pi) - obie pętle przestrajają się SPÓJNIE.
        if not self._nastawy_simc_przeliczone:
            wynik = self.autotest_result
            if wynik is not None and wynik['fit_ok']:
                self._pid_in_kc, self._pid_in_ti = _simc_inner_pi(wynik['K'], wynik['T1'], wynik['T2'], wynik['L'])
                self._pid_out_kc, self._pid_out_ti = _simc_outer_pi(wynik['K'])
            self._nastawy_simc_przeliczone = True

        timestamp = row_data['Timestamp']
        crt_temp = float(row_data['CRT_temp_niegrzana'])
        hrt_temp = float(row_data['HRT_temp_grzana'])
        target_temperature, need_heat, reason, forecast_min_c, warmup_soon = \
            self._evaluate_risk_setpoint(row_data)

        if not need_heat:
            # Brak zagrożenia - nie grzejemy, czyścimy obie całki (jak w
            # risk_function_pid), żeby żadna z pętli nie była "doładowana"
            # przy następnym zagrożeniu.
            self._pid_out_integral = 0.0
            self._pid_out_prev_error = 0.0
            self._pid_out_prev_time = timestamp
            self._pid_in_integral = 0.0
            self._pid_in_prev_error = 0.0
            self._pid_in_prev_time = timestamp
            power_percent = 0.0
            hrt_setpoint = hrt_temp
        else:
            # --- Pętla ZEWNĘTRZNA: błąd CRT -> korekta do hrt_setpoint. ---
            error_out = target_temperature - crt_temp
            dt_out = (timestamp - self._pid_out_prev_time).total_seconds() if self._pid_out_prev_time else 1.0
            dt_out = max(dt_out, 1e-6)

            proportional_out = self._pid_out_kc * error_out
            unclamped_out = hrt_temp + proportional_out + (self._pid_out_kc / self._pid_out_ti) * self._pid_out_integral
            # Anty-windup: całkujemy tylko, gdy wyjście nieograniczone nie jest
            # już w nasyceniu granic fizycznych HRT (floor/limit termiczny).
            if (RISK_HRT_ABSOLUTE_FLOOR_C < unclamped_out < HRT_LIMIT_OSTRZEGAWCZY_C
                    or (unclamped_out <= RISK_HRT_ABSOLUTE_FLOOR_C and error_out > 0)
                    or (unclamped_out >= HRT_LIMIT_OSTRZEGAWCZY_C and error_out < 0)):
                self._pid_out_integral += error_out * dt_out

            integral_term_out = (self._pid_out_kc / self._pid_out_ti) * self._pid_out_integral
            hrt_setpoint = hrt_temp + proportional_out + integral_term_out
            hrt_setpoint = min(max(hrt_setpoint, RISK_HRT_ABSOLUTE_FLOOR_C), HRT_LIMIT_OSTRZEGAWCZY_C)

            self._pid_out_prev_error = error_out
            self._pid_out_prev_time = timestamp

            # --- Pętla WEWNĘTRZNA: błąd HRT -> power_percent. ---
            error_in = hrt_setpoint - hrt_temp
            dt_in = (timestamp - self._pid_in_prev_time).total_seconds() if self._pid_in_prev_time else 1.0
            dt_in = max(dt_in, 1e-6)

            proportional_in = self._pid_in_kc * error_in
            unclamped_in = proportional_in + (self._pid_in_kc / self._pid_in_ti) * self._pid_in_integral
            if (0.0 < unclamped_in < 100.0 or (unclamped_in <= 0.0 and error_in > 0)
                    or (unclamped_in >= 100.0 and error_in < 0)):
                self._pid_in_integral += error_in * dt_in

            integral_term_in = (self._pid_in_kc / self._pid_in_ti) * self._pid_in_integral
            power_percent = proportional_in + integral_term_in
            power_percent = min(max(power_percent, 0.0), 100.0)

            self._pid_in_prev_error = error_in
            self._pid_in_prev_time = timestamp

        self._krok_modelu(power_percent)
        self._dodaj_flopy(25)  # 2x PI + anty-windup (na wierzchu setpointu/cyfrowego bliźniaka).

        diagnostics = {
            'target_temperature': target_temperature,
            'need_heat': need_heat,
            'reason': reason,
            'forecast_min_c': forecast_min_c,
            'warmup_soon': warmup_soon,
            'hrt_setpoint': hrt_setpoint,
            'pid_error': target_temperature - crt_temp,  # jak w risk_function_pid, dla wspólnych narzędzi diagnostycznych
            'pid_error_outer': target_temperature - crt_temp,
            'pid_error_inner': hrt_setpoint - hrt_temp,
            'pid_integral_outer': self._pid_out_integral,
            'pid_integral_inner': self._pid_in_integral,
        }
        return power_percent, diagnostics
