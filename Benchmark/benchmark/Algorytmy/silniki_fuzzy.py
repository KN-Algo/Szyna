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


def wnioskowanie_fl_podstawowe(blad_T, hrt, jest_snieg, jest_deszcz):
    """
    Rdzeń wnioskowania współdzielony przez FL1/FL2/FL3 (identyczny w oryginałach) -
    6 reguł Sugeno: OK/chłodno/mroźno x brak-opadu/opad + lodowato (niska HRT).
    Zwraca surowy wynik (0-100), PRZED jakąkolwiek binaryzacją/PWM - to należy do
    konkretnego wariantu wykonawczego (patrz klamra_fl1/binaryzuj/WykonawcaPWM).
    """
    t_ok = rampa_malejaca(blad_T, 0.0, 3.0)
    t_chlodno = trojkat(blad_T, 0.0, 3.0, 6.0)
    t_mrozno = rampa_rosnaca(blad_T, 3.0, 6.0)
    t_lodowato = rampa_malejaca(hrt, -15.0, -12.0)

    opad_aktywny = 1.0 if (jest_snieg or jest_deszcz) else 0.0
    opad_brak = 1.0 if not (jest_snieg or jest_deszcz) else 0.0

    r1 = t_ok
    r2 = min(t_chlodno, opad_brak)
    r3 = min(t_chlodno, opad_aktywny)
    r4 = min(t_mrozno, opad_brak)
    r5 = min(t_mrozno, opad_aktywny)
    r6 = t_lodowato

    licznik = (r1 * MOC_OFF + r2 * MOC_OFF + r3 * MOC_MED
               + r4 * MOC_LOW + r5 * MOC_HIGH + r6 * MOC_HIGH)
    mianownik = r1 + r2 + r3 + r4 + r5 + r6

    if mianownik == 0:
        return 0.0
    return licznik / mianownik


def wnioskowanie_fl2v2(blad_T, hrt, precip, jest_snieg, jest_deszcz):
    """
    Rdzeń wnioskowania FL2v2 (własny wariant) - 7 reguł: jak wyżej plus dodatkowa
    reguła r7 (śnieg + chłodno -> HIGH), a próg "lodowato" zależy od intensywności
    opadu R=precip zamiast być stały (-15..-12°C jak w podstawowym wariancie).
    """
    t_ok = rampa_malejaca(blad_T, 0.0, 3.0)
    t_chlodno = trojkat(blad_T, 0.0, 3.0, 6.0)
    t_mrozno = rampa_rosnaca(blad_T, 3.0, 6.0)
    r = precip
    prog_lodowato = -15.0 + r * 10.0 + (5.0 if r > 8 else 0.0)
    t_lodowato = rampa_malejaca(hrt, -15.0, prog_lodowato)

    opad_aktywny = 1.0 if (jest_snieg or jest_deszcz) else 0.0
    opad_brak = 1.0 if not (jest_snieg or jest_deszcz) else 0.0

    r1 = t_ok
    r2 = min(t_chlodno, opad_brak)
    r3 = min(t_chlodno, opad_aktywny)
    r4 = min(t_mrozno, opad_brak)
    r5 = min(t_mrozno, opad_aktywny)
    r6 = t_lodowato
    r7 = min(1.0 if jest_snieg else 0.0, t_chlodno)

    licznik = (r1 * MOC_OFF + r2 * MOC_OFF + r3 * MOC_MED + r4 * MOC_LOW
               + r5 * MOC_HIGH + r6 * MOC_HIGH + r7 * MOC_HIGH)
    mianownik = r1 + r2 + r3 + r4 + r5 + r6 + r7

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


def binaryzuj(wynik):
    """Twarde 0/100% wg progu 50%, jak w Fuzzy_Logic_2.py / Fuzzy_Logic_2v2.py."""
    return 100.0 if wynik >= 50.0 else 0.0


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
