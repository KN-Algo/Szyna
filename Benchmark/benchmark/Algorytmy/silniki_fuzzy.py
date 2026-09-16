# Algorytmy/silniki_fuzzy.py
#
# WSPÓLNY rdzeń wnioskowania rozmytego (Sugeno) używany przez:
#   - fuzzy_logic_1.py, fuzzy_logic_2.py, fuzzy_logic_2v2.py, fuzzy_logic_3.py
#     (samodzielne wersje, cel = stały T_ZADANA)
#   - funkcja_fuzzy_ryzyko.py (cel = setpoint z funkcji ryzyka, Kalman+kara za śnieg)
#   - funkcja_fuzzy_normy.py (cel = setpoint z normy LET-1)
#
# Trzymanie samej matematyki rozmytej w jednym miejscu gwarantuje, że wszystkie
# warianty jednego "silnika" (np. FL1 samodzielny, FL1+ryzyko, FL1+norma) liczą
# DOKŁADNIE to samo wnioskowanie - różnią się WYŁĄCZNIE źródłem celu (blad_T)
# i tym, czy w ogóle trzeba grzać (need_heat).

# Singletony Sugeno (moc wyjściowa dla każdej reguły) - identyczne we wszystkich wariantach.
MOC_OFF = 0.0
MOC_LOW = 25.0
MOC_MED = 60.0
MOC_HIGH = 100.0


def rampa_rosnaca(x, x0, x1):
    if x <= x0:
        return 0.0
    if x >= x1:
        return 1.0
    return (x - x0) / (x1 - x0)


def rampa_malejaca(x, x0, x1):
    if x <= x0:
        return 1.0
    if x >= x1:
        return 0.0
    return 1.0 - ((x - x0) / (x1 - x0))


def trojkat(x, x0, x_srodek, x1):
    if x <= x0 or x >= x1:
        return 0.0
    if x == x_srodek:
        return 1.0
    if x < x_srodek:
        return (x - x0) / (x_srodek - x0)
    return 1.0 - ((x - x_srodek) / (x1 - x_srodek))


# Domyślne progi funkcji przynależności FL1
PROG_CHLODNO_DOMYSLNY = 3.0
PROG_MROZNO_DOMYSLNY = 6.0
PROG_LODOWATO_DOLNY_DOMYSLNY = -10.0
PROG_LODOWATO_GORNY_DOMYSLNY = -7.0


def wnioskowanie_fl_parametryzowane(blad_T, hrt, jest_snieg, jest_deszcz,
                                     prog_chlodno=PROG_CHLODNO_DOMYSLNY,
                                     prog_mrozno=PROG_MROZNO_DOMYSLNY,
                                     prog_lodowato_dolny=PROG_LODOWATO_DOLNY_DOMYSLNY,
                                     prog_lodowato_gorny=PROG_LODOWATO_GORNY_DOMYSLNY,
                                     moc_low=MOC_LOW, moc_med=MOC_MED):
    """
    Jak wnioskowanie_fl_podstawowe, ale z progami funkcji przynależności ORAZ
    singletonami mocy LOW/MED jako PARAMETRAMI zamiast literałów.
    """

    if hrt >= 15.0:
        return 0.0

    t_ok = rampa_malejaca(blad_T, 0.0, prog_chlodno)
    t_chlodno = trojkat(blad_T, 0.0, prog_chlodno, prog_mrozno)
    t_mrozno = rampa_rosnaca(blad_T, prog_chlodno, prog_mrozno)
    t_lodowato = rampa_malejaca(hrt, prog_lodowato_dolny, prog_lodowato_gorny)
    t_goraco = rampa_rosnaca(hrt, 15.0, 20.0)

    opad_aktywny = 1.0 if (jest_snieg or jest_deszcz) else 0.0
    opad_brak = 1.0 if not (jest_snieg or jest_deszcz) else 0.0

    r1 = t_ok
    r2 = min(t_chlodno, opad_brak)
    r3 = min(t_chlodno, opad_aktywny)
    r4 = min(t_mrozno, opad_brak)
    r5 = min(t_mrozno, opad_aktywny)
    r6 = t_lodowato
    r_goraco = t_goraco

    licznik = (r1 * MOC_OFF + r2 * MOC_OFF + r3 * MOC_MED
               + r4 * MOC_LOW + r5 * MOC_HIGH + r6 * MOC_HIGH
               + r_goraco * MOC_OFF)
    mianownik = r1 + r2 + r3 + r4 + r5 + r6 + r_goraco

    if mianownik == 0:
        return 0.0
    return licznik / mianownik


# Progi/singletony AGRESYWNEGO wariantu
PROG_CHLODNO_AGRESYWNY = 1.5
PROG_MROZNO_AGRESYWNY = 3.5
PROG_LODOWATO_DOLNY_AGRESYWNY = -12.0
PROG_LODOWATO_GORNY_AGRESYWNY = -8.0
MOC_LOW_AGRESYWNA = 50.0
MOC_MED_AGRESYWNA = 85.0


def wnioskowanie_fl_agresywne(blad_T, hrt, jest_snieg, jest_deszcz):
    """Wariant FL1 reagujący MOCNIEJ i WCZEŚNIEJ na złe warunki."""
    return wnioskowanie_fl_parametryzowane(
        blad_T, hrt, jest_snieg, jest_deszcz,
        prog_chlodno=PROG_CHLODNO_AGRESYWNY, prog_mrozno=PROG_MROZNO_AGRESYWNY,
        prog_lodowato_dolny=PROG_LODOWATO_DOLNY_AGRESYWNY, prog_lodowato_gorny=PROG_LODOWATO_GORNY_AGRESYWNY,
        moc_low=MOC_LOW_AGRESYWNA, moc_med=MOC_MED_AGRESYWNA,
    )


def wnioskowanie_fl_podstawowe(blad_T, hrt, jest_snieg, jest_deszcz):
    """Rdzeń wnioskowania współdzielony przez FL1/FL2/FL3."""
    return wnioskowanie_fl_parametryzowane(blad_T, hrt, jest_snieg, jest_deszcz)



def wnioskowanie_fl2v2(blad_T, hrt, ryzyko, jest_snieg, jest_deszcz, at_temp):
    """Rdzeń wnioskowania FL2v2."""
    if hrt >= 3.0:
        return 0.0
    if hrt > 0.0 and at_temp < 0.0:
        return 0.0
    if hrt <= -8.0:
        return 100.0
    if at_temp >= 3.0:
        return 0.0

    t_ok = rampa_malejaca(blad_T, 0.0, 3.0)
    t_chlodno = trojkat(blad_T, 0.0, 3.0, 6.0)
    t_mrozno = rampa_rosnaca(blad_T, 3.0, 6.0)
    prog_lodowato = -10.0 + ryzyko*3.0 + (5.0 if ryzyko > 8 else 0)
    t_lodowato = rampa_malejaca(hrt, -10.0, prog_lodowato)
    t_goraco = rampa_rosnaca(hrt, 10.0, 15.0)

    opad_aktywny = 1.0 if (jest_snieg or jest_deszcz) else 0.0
    opad_brak = 1.0 if not (jest_snieg or jest_deszcz) else 0.0

    r1 = t_ok
    r2 = min(t_chlodno, opad_brak)
    r3 = min(t_chlodno, opad_aktywny)
    r4 = min(t_mrozno, opad_brak)
    r5 = min(t_mrozno, opad_aktywny)
    r6 = t_lodowato
    r7 = min(1.0 if jest_snieg else 0.0, t_chlodno)
    r_goraco = t_goraco
    r_powietrze_mrozi = 1.0 if (at_temp < -5.0) else 0.0

    licznik = (
                r1 * MOC_OFF
               + r2 * MOC_OFF
               + r3 * (MOC_MED if ryzyko < 5.0 else MOC_HIGH)
               + r4 * (MOC_LOW if ryzyko < 5.0 else MOC_MED)
               + r5 * MOC_HIGH
               + r6 * MOC_HIGH
               + r7 * MOC_HIGH
               + r_powietrze_mrozi * (MOC_MED if ryzyko < 5.0 else MOC_HIGH)
               + r_goraco * MOC_OFF)
    mianownik = r1 + r2 + r3 + r4 + r5 + r6 + r7 + r_powietrze_mrozi + r_goraco

    if mianownik == 0:
        return 0.0
    return licznik / mianownik


def klamra_fl1(wynik):
    """Miękkie obcięcie krańców jak w Fuzzy_Logic_1.py: <10% -> 0%, >90% -> 100%."""
    if wynik < 10.0:
        return 0.0
    if wynik > 90.0:
        return 100.0
    return wynik


def binaryzuj(wynik, stan_poprzedni=0.0, prog_dolny=40.0, prog_gorny=50.0):
    """
    Binaryzacja z histerezą (20% / 40%):
    - Jeśli stanem poprzednim było ON (>= 100.0) i wynik > 20.0 -> zostaje ON (100.0).
    - Jeśli stanem poprzednim było OFF (< 100.0) i wynik < 40.0 -> zostaje OFF (0.0).
    """
    if stan_poprzedni >= 100.0:
        return 100.0 if wynik > prog_dolny else 0.0
    else:
        return 100.0 if wynik >= prog_gorny else 0.0


class BinaryzatorHistereza:
    """
    Zapamiętuje stan między krokami symulacji (klasa stanowa dla binaryzacji z histerezą).
    """
    def __init__(self, prog_dolny=40.0, prog_gorny=50.0, stan_poczatkowy=0.0):
        self.prog_dolny = prog_dolny
        self.prog_gorny = prog_gorny
        self.stan = stan_poczatkowy

    def krok(self, wynik):
        self.stan = binaryzuj(wynik, self.stan, self.prog_dolny, self.prog_gorny)
        return self.stan


class WykonawcaPWM:
    """
    Mechanizm PWM (modulacja szerokości impulsu) z Fuzzy_Logic_3.py: moc % przelicza
    się RAZ na początku okna czasowego (okres_cyklu sekund) na czas załączenia w tym
    oknie, z kwantyzacją (<15s -> 0, >45s -> pełen cykl), a każdy krok() zwraca
    binarne 0/100% w zależności od tego, w którym miejscu okna aktualnie jesteśmy.
    """

    def __init__(self, okres_cyklu=60):
        self.okres_cyklu = okres_cyklu
        self.sekunda_cyklu = 0
        self.wyliczona_moc = 0.0

    @property
    def na_poczatku_cyklu(self):
        return self.sekunda_cyklu == 0

    def ustaw_moc_cyklu(self, moc_procentowa):
        self.wyliczona_moc = moc_procentowa

    def krok(self):
        czas_wlaczenia = self.okres_cyklu * (self.wyliczona_moc / 100.0)
        if czas_wlaczenia < 15.0:
            czas_wlaczenia = 0.0
        if czas_wlaczenia > 45.0:
            czas_wlaczenia = float(self.okres_cyklu)

        output = 100.0 if self.sekunda_cyklu < czas_wlaczenia else 0.0

        self.sekunda_cyklu += 1
        if self.sekunda_cyklu >= self.okres_cyklu:
            self.sekunda_cyklu = 0

        return output