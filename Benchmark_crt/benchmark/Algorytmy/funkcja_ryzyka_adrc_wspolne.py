# Algorytmy/funkcja_ryzyka_adrc_wspolne.py
#
# Logika WSPÓLNA dla obu wariantów ADRC (Active Disturbance Rejection Control -
# regulacja z odrzucaniem zakłóceń, Han Jingqing 1998/2009): liniowego
# (funkcja_ryzyka_ladrc.py, "LADRC" - Gao 2003, bandwidth-parameterization) i
# nieliniowego (funkcja_ryzyka_nadrc.py, "NADRC" - oryginalna wersja Hana z
# funkcją fal()). Tu jest WYŁĄCZNIE matematyka wspólna (wyliczenie parametrów
# regulatora z modelu obiektu + funkcja fal()) - sama pętla ESO/prawa
# sterowania jest w każdym pliku osobno (różni się liniowość vs nieliniowość
# poprawek), żeby nie komplikować jednego wspólnego kodu warunkami if.
#
# IDEA ADRC W SKRÓCIE (w odróżnieniu od PID - patrz funkcja_ryzyka_pid.py):
# zamiast całkować błąd, Extended State Observer (ESO, rozszerzony obserwator
# stanu) w czasie rzeczywistym ESTYMUJE, obok samej temperatury szyny (z1),
# dodatkowy stan z2 = "całkowite zakłócenie" - sumę WSZYSTKICH efektów, których
# uproszczony model pierwszego rzędu (ẏ = f + b0*u) nie opisuje wprost:
# opóźnienie L, drugą stałą czasową T2, wpływ pogody, błąd identyfikacji K/T1.
# Prawo sterowania AKTYWNIE odejmuje tę estymatę z sygnału (stąd "odrzucanie
# zakłóceń"), więc regulator nie musi ZNAĆ dokładnego modelu obiektu - musi go
# tylko na bieżąco ŚLEDZIĆ. To fundamentalnie inny mechanizm odporności niż
# całka PID (która "pamięta" skumulowany błąd) czy MPC (który jawnie
# OPTYMALIZUJE na modelu) - tu obserwator w locie koryguje sam model.

# ==========================================
# WYPROWADZENIE PARAMETRÓW REGULATORA Z MODELU SOPDT (K/T1/T2/L, z autotestu -
# ten sam mechanizm identyfikacji co risk_function_pid, patrz
# funkcja_ryzyka_pid.py) - PRZYBLIŻENIE obiektu jako pierwszego rzędu:
#   ẏ = -y/tau + (K/tau)*u_frakcja + (zakłócenia), tau = T1+T2
# (różnica względem prawdziwego SOPDT - drugi biegun T2 i opóźnienie L - jest
# celowo WCHŁONIĘTA przez "całkowite zakłócenie" z2, które ESO i tak śledzi -
# to jest DOKŁADNIE punkt ADRC: nie trzeba doskonałego modelu).
#
# WAŻNE - jednostki mocy: K jest zdefiniowane jako °C w stanie ustalonym przy
# u_frakcja=1.0 (100% mocy) - DOKŁADNIE tak samo jak w cyfrowym bliźniaku
# (rdzen_kontrolera._krok_modelu: `u = moc_procent / 100.0`). Cały reszta tego
# pliku (i obu kontrolerów ADRC) operuje na moc_procent w skali 0-100, więc
# b0 MUSI być podzielone dodatkowo przez 100 (inaczej sterowanie wychodzi
# 100x za słabe - dokładnie taki błąd skalowania złapany empirycznie na
# smoke teście 2026-09-07: HRT schodziło daleko poniżej floora -10°C, bo
# obliczona moc_procent była rzędu 0.01-0.1% zamiast dziesiątek procent).
#
# Pasmo regulatora omega_c wyprowadzone z L (opóźnienie) tą samą konwencją
# "lambda=theta, średnio agresywnie", której risk_function_pid już używa do
# SIMC (Ti = min(tau, 4*(theta+lambda)), lambda=theta=L) - żeby obie rodziny
# (PID i ADRC) były porównywalne pod względem założonej agresywności regulacji,
# nie tylko przypadkowo podobne. Pasmo obserwatora omega_o = 5x omega_c (Gao
# 2003 - typowa separacja pasm 3-5x, żeby obserwator "nadążał" szybciej niż
# reguluje regulator).
# ==========================================
ADRC_OMEGA_O_MNOZNIK = 5.0

# Wartości ZAPASOWE (dopóki autotest się nie zakończy/gdyby się nie powiódł) -
# te same K/T1/T2/L co w funkcja_ryzyka_pid.py (patrz uzasadnienie w jej
# nagłówku - z wcześniejszego testu identyfikacji obiektu).
ADRC_FALLBACK_K = 51.1163668
ADRC_FALLBACK_T1 = 1120.914508
ADRC_FALLBACK_T2 = 2450.968465
ADRC_FALLBACK_L = 1194.184089

# Parametry funkcji fal() (WYŁĄCZNIE dla wariantu nieliniowego, NADRC) -
# wartości KLASYCZNE z oryginalnej pracy Hana (2009, "From PID to Active
# Disturbance Rejection Control"): alpha<1 w poprawce obserwatora stanu
# (alpha1) i zakłócenia (alpha2 - mniejsze niż alpha1, bo z2 zmienia się
# wolniej), alpha=0.5 w prawie sterowania (NLSEF). DELTA_C to szerokość
# "strefy liniowej" wokół zera - rzędu realnej rozdzielczości/szumu czujnika
# HRT (0.5°C), poniżej której fal() zachowuje się jak zwykłe wzmocnienie
# liniowe (zapobiega nadmiernemu wzmacnianiu szumu pomiarowego blisko zera,
# gdzie |e|^alpha przy alpha<1 miałoby NIESKOŃCZONĄ pochodną w e=0).
ADRC_NADRC_ALPHA1 = 0.5
ADRC_NADRC_ALPHA2 = 0.25
ADRC_NADRC_ALPHA_CTRL = 0.5
ADRC_NADRC_DELTA_C = 0.5


def wylicz_parametry_adrc(K, T1, T2, L):
    """
    Z (K, T1, T2, L) identyfikacji SOPDT wylicza (b0, omega_c, omega_o) -
    patrz uzasadnienie w nagłówku pliku. Używane identycznie przez LADRC i
    NADRC (przy starcie z wartości ADRC_FALLBACK_*, potem RAZ po zakończeniu
    autotestu ze świeżo zidentyfikowanych wartości - jak SIMC w
    funkcja_ryzyka_pid.py).
    """
    tau = T1 + T2
    b0 = K / (100.0 * tau)  # /100: b0 skalowane pod moc_procent [0,100], nie u_frakcja [0,1] - patrz nagłówek pliku
    omega_c = 1.0 / (2.0 * L)
    omega_o = ADRC_OMEGA_O_MNOZNIK * omega_c
    return b0, omega_c, omega_o


def fal(e, alpha, delta):
    """
    Funkcja Hana (2009) - "fast-slow" nieliniowe wzmocnienie błędu: poza
    strefą liniową (|e|>delta) rośnie jak |e|^alpha*sign(e) (dla alpha<1
    WOLNIEJ niż liniowo - łagodniejsza reakcja na duże błędy/skoki niż
    zwykłe wzmocnienie liniowe), wewnątrz strefy (|e|<=delta) jest zwykłym
    wzmocnieniem liniowym e/delta^(1-alpha) - tak dobranym, żeby fal() było
    CIĄGŁE na granicy |e|=delta (brak skoku wartości między dwiema gałęziami).
    """
    if abs(e) > delta:
        return (abs(e) ** alpha) * (1.0 if e >= 0.0 else -1.0)
    return e / (delta ** (1.0 - alpha))
