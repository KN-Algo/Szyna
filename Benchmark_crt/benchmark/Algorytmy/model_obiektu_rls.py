# Algorytmy/model_obiektu_rls.py
#
# WSPÓLNY model obiektu identyfikowany NA ŻYWO (RLS - Rekurencyjne Najmniejsze Kwadraty,
# z zapominaniem) - wydzielony z funkcja_ryzyka_model_adaptacyjny.py (2026-10-01), żeby
# TA SAMA maszyneria (i te samej naprawione błędy - patrz P_RESET_MNOZNIK niżej) służyła
# wszystkim "obiekt się adaptuje" wariantom (PID/ADRC/MPC - 2026-10-02), bez trojenia kodu.
#
# MODEL (liniowy, pierwszego rzędu, dyskretny - jeden krok do przodu):
#   (HRT[k] - HRT[k-1]) / dt = a * moc_frac[k-1] + b * (AT[k-1] - HRT[k-1]) + c * proxy_slonca[k-1]
#     a = wzmocnienie grzałki [°C/s na jednostkę mocy 0..1]       - "jak grzałka na niego reaguje"
#     b = współczynnik relaksacji do pogody [1/s, Newtonowskie stygnięcie do AT] - "jak powietrze wpływa"
#     c = wzmocnienie słoneczne [°C/s na jednostkę proxy_slonca]  - "jak nasłonecznienie wpływa"
#
# proxy_slonca(t): PRZYBLIŻENIE geometrii słońca z samego znacznika czasu (godzina dnia +
# dzień roku), BEZ szerokości/długości geograficznej i bez zachmurzenia - kontroler nie
# dostaje w row_data żadnego surowego sygnału nasłonecznienia (patrz wejscie_slonca.py,
# które liczy to z RAW danych źródłowych, niedostępnych na poziomie kontrolera).

from math import cos, pi

import numpy as np

# --- Priory startowe - TYLKO punkt startowy (model i tak zacznie się zmieniać od
# pierwszego kroku). a0/b0 z ADRC_FALLBACK_K/T1 (ten sam obiekt, kanał moc->HRT,
# zidentyfikowany wcześniej - patrz funkcja_ryzyka_adrc_wspolne.py). c0=0.0 - brak
# wcześniejszej oceny wpływu słońca, RLS uczy się od zera. ---
from funkcja_ryzyka_adrc_wspolne import ADRC_FALLBACK_K, ADRC_FALLBACK_T1

A0_DOMYSLNE = ADRC_FALLBACK_K / ADRC_FALLBACK_T1
B0_DOMYSLNE = 1.0 / ADRC_FALLBACK_T1
C0_DOMYSLNE = 0.0

A_MIN = 1e-4                        # Dolna granica |a| przy dzieleniu (feedforward/K=a/b) - patrz 1/(2L) w ADRC, ta sama lekcja.
LAMBDA_ZAPOMINANIA_DOMYSLNA = 0.999  # <1: model może "zapominać" stare dane i dalej się zmieniać (nie zbiega i zamraża się).
P0_DIAG_DOMYSLNE = np.array([10.0, 1e-3, 10.0])  # Startowa niepewność theta - rząd wielkości dopasowany do a0/b0/c0.
REGRESOR_MIN_NORM2 = 1e-6           # Regresor "martwy" (wszystko ~0) - nie aktualizuj P (blow-up guard).
P_RESET_MNOZNIK = 100.0             # "Covariance resetting": gdy wariancja przekroczy tyle x P0 (RLS z zapominaniem
                                      # bez wzbudzenia w danym kierunku - np. c/słońce nocą - rośnie bez ograniczeń,
                                      # czysto matematyczny efekt /LAMBDA bez korekty danymi, NIE błąd fizyki),
                                      # resetuj P do P0 (theta ZOSTAJE - nie gubimy czego się nauczono).


def proxy_slonca(timestamp):
    """Przybliżenie geometrii słońca z samego znacznika czasu (godzina doby + sezon).
    Zwraca 0 (noc) do ~1 (południe, listopad/marzec - sezonowo mniej w grudniu/styczniu)."""
    godz = timestamp.hour + timestamp.minute / 60.0 + timestamp.second / 3600.0
    wysokosc = cos(2.0 * pi * (godz - 12.0) / 24.0)          # szczyt w południe, dno o północy
    dzien_roku = timestamp.timetuple().tm_yday
    sezon = 0.5 + 0.5 * cos(2.0 * pi * (dzien_roku - 172.0) / 365.0)
    return max(0.0, wysokosc) * sezon


class ModelObiektuRLS:
    """Jeden model (a,b,c) identyfikowany na żywo metodą RLS z zapominaniem.
    Użycie w kontrolerze (co krok symulacji):
        a, b, c, proxy = model.aktualizuj_i_pobierz(timestamp, hrt_teraz, at_teraz)
        ... (prawo sterowania, wyznacz power_percent) ...
        model.zapamietaj_regresor(timestamp, hrt_teraz, at_teraz, power_percent / 100.0, proxy)
    """

    def __init__(self, a0=A0_DOMYSLNE, b0=B0_DOMYSLNE, c0=C0_DOMYSLNE,
                 p0_diag=P0_DIAG_DOMYSLNE, lam=LAMBDA_ZAPOMINANIA_DOMYSLNA):
        self.lam = lam
        self.p0_diag = np.asarray(p0_diag, dtype=float)
        self.theta = np.array([a0, b0, c0], dtype=float)
        self.P = np.diag(self.p0_diag)

        self._poprzedni_regresor = None
        self._poprzednie_hrt = None
        self._poprzedni_czas = None

    def aktualizuj_i_pobierz(self, timestamp, hrt_teraz, at_teraz):
        """Na początku kroku: RLS update z obserwacji od poprzedniego kroku (jeśli jest),
        potem zwraca (a, b, c, proxy_slonca_teraz) do użycia w prawie sterowania."""
        if self._poprzedni_regresor is not None and self._poprzednie_hrt is not None \
                and self._poprzedni_czas is not None:
            dt = (timestamp - self._poprzedni_czas).total_seconds()
            if dt > 0:
                phi = self._poprzedni_regresor
                if float(phi @ phi) >= REGRESOR_MIN_NORM2:
                    y = (hrt_teraz - self._poprzednie_hrt) / dt
                    Pphi = self.P @ phi
                    mianownik = self.lam + float(phi @ Pphi)
                    K = Pphi / mianownik
                    blad_predykcji = y - float(phi @ self.theta)
                    self.theta = self.theta + K * blad_predykcji
                    self.P = (self.P - np.outer(K, Pphi)) / self.lam
                    self.P = (self.P + self.P.T) / 2.0  # symetryzacja (błędy zmiennoprzecinkowe psują ją w czasie)

                    if np.any(np.diag(self.P) > self.p0_diag * P_RESET_MNOZNIK):
                        self.P = np.diag(self.p0_diag)

                    # a>=A_MIN, b>=0 - znak/skala fizycznie sensowne (grzałka grzeje, pogoda nie
                    # "chłodzi w stronę AT ujemnie") i bezpieczne jako mianownik. c celowo NIE
                    # jest przycinane - rzadko używane jako dzielnik.
                    self.theta[0] = max(self.theta[0], A_MIN)
                    self.theta[1] = max(self.theta[1], 0.0)

        proxy = proxy_slonca(timestamp)
        return self.theta[0], self.theta[1], self.theta[2], proxy

    def zapamietaj_regresor(self, timestamp, hrt_teraz, at_teraz, moc_frac_teraz, proxy_teraz):
        """Na końcu kroku: zapisuje regresor użyty TERAZ, do rozliczenia w NASTĘPNYM kroku."""
        self._poprzedni_regresor = np.array([moc_frac_teraz, at_teraz - hrt_teraz, proxy_teraz])
        self._poprzednie_hrt = hrt_teraz
        self._poprzedni_czas = timestamp
