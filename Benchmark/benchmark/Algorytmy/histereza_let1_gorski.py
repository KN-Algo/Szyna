# Algorytmy/histereza_let1_gorski.py
#
# ALGORYTM: wariant histereza_let1.py (compute_control) dla REJONÓW GÓRSKICH -
# instrukcja LET-1 PKP PLK S.A., pkt 2.4.18.7:
#
#   "W rejonach górskich gdzie występują bardzo intensywne opady śniegu oraz
#   w szczególnych przypadkach można ustawić temperaturę wyłączenia na +10°C."
#
# Dotyczy WYŁĄCZNIE progu WYŁĄCZENIA HRT PRZY OPADACH (Tabela nr 5, wariant
# dwuczujnikowy: standardowo +7°C) - podniesionego tu do +10°C. Wszystkie
# pozostałe progi (załączenie przy opadach, oba progi suchego mrozu z Tabeli
# nr 6) SĄ IDENTYCZNE jak w wariancie standardowym - norma nie wspomina o ich
# zmianie, więc ich nie ruszamy. Efekt praktyczny: grzanie trwa DŁUŻEJ przy
# opadach (wyłącza się dopiero przy wyższej HRT), co lepiej wytapia bardzo
# intensywny/obfity śnieg typowy dla terenów górskich, kosztem większego
# zużycia energii.

from histereza_let1 import KontrolerHisterezaLET1

HRT_OFF_PRECIP_GORSKI_C = 10.0  # Pkt 2.4.18.7 - podniesiony próg wyłączenia HRT przy opadach dla rejonów górskich.


class KontrolerHisterezaLET1Gorski(KontrolerHisterezaLET1):

    def __init__(self, max_switches_per_day=12):
        super().__init__(max_switches_per_day=max_switches_per_day)
        self.hrt_off_precip = HRT_OFF_PRECIP_GORSKI_C
