# Algorytmy/pid_baza.py
# ==============================================================================
#  WSPOLNA BAZA REGULATORA PID dla testow czterech regul strojenia.
#
#  Cztery reguly (ZN, Cohen-Coon, AMIGO, SIMC) roznia sie WYLACZNIE
#  nastawami (Kp, Ti, Td) - sam regulator, jego mechanizmy i interfejs sa
#  identyczne. Zeby porownanie na benchmarku bylo uczciwe, kazda regula
#  importuje TE SAMA klase z tego pliku i podaje tylko swoje nastawy.
#  Dzieki temu ewentualna roznica w wynikach pochodzi z nastaw, nie z kodu.
#
#  Nastawy policzone w strojenie_pid.py z modelu FOPDT kanalu grzania
#  benchmarku (K=51.1, T=2954 s, L=2001 s po redukcji metoda dwoch punktow):
#    Ziegler-Nichols: Kp=1.2T/(KL)         Ti=2L                 Td=0.5L
#    Cohen-Coon:      Kp=(1/Kr)(4/3+r/4)   Ti=L(32+6r)/(13+8r)   Td=4L/(11+2r)
#    AMIGO:           Kp=(0.2+0.45T/L)/K   Ti=L(0.4L+0.8T)/(L+0.1T)
#                                          Td=0.5LT/(0.3L+T)
#    SIMC (tau_c=L):  Kp=T/(K(tau_c+L))    Ti=min(T, 4(tau_c+L)) Td=0 (czyste PI)
#
#  Mechanizmy klasy (te same co w calym strojeniu):
#   - saturacja wyjscia do 0..100%
#   - anty-windup przez calkowanie warunkowe
#   - pochodna po pomiarze z filtrem 1. rzedu (N=8)
#   - dt z roznicy Timestampow (dziala przy dowolnym kroku benchmarku)
#  Konstruktor przyjmuje i ignoruje max_switches_per_day, zeby linia
#  `controller = RailHeatingController(max_switches_per_day=12)` w
#  main_test.py nie wymagala zmian.
# ==============================================================================


class PIDBaza:
    def __init__(self, Kp, Ti, Td, target_temp=4.0, **_ignorowane):
        self.cel = target_temp
        self.Kp, self.Ti, self.Td = Kp, Ti, Td
        self.N = 8.0
        self.calka = 0.0
        self.y_prev = None
        self.d_filt = 0.0
        self.t_prev = None
 
    def compute_control(self, row_data):
        y = float(row_data['HRT_temp_grzana'])
        t = row_data['Timestamp']
        dt = 1.0 if self.t_prev is None else max(1e-6, (t - self.t_prev).total_seconds())
        self.t_prev = t
        if self.y_prev is None:
            self.y_prev = y
 
        e = self.cel - y
        alfa = self.Td / (self.Td + self.N * dt) if self.Td > 0 else 0.0
        d_surowa = (y - self.y_prev) / dt
        self.d_filt = alfa * self.d_filt + (1.0 - alfa) * d_surowa
        self.y_prev = y
 
        u_raw = self.Kp * (e + self.calka / self.Ti - self.Td * self.d_filt)
        u = min(1.0, max(0.0, u_raw))
        nasycony = (u_raw >= 1.0 and e > 0) or (u_raw <= 0.0 and e < 0)
        if not nasycony:
            self.calka += e * dt
        return 100.0 * u
 
 
class PIDBazaDyskretna(PIDBaza):
    """Wariant DYSKRETNY: prawo PID liczone co Ts sekund (domyslnie 60 s),
    a miedzy probkami wyjscie jest TRZYMANE (sample-and-hold) - jak w
    sterowniku przemyslowym o okresie probkowania Ts.
 
    Nastawy: te same co w wersji ciaglej danej reguly. Uzasadnienie:
    reguly strojenia (ZN/CC/AMIGO/SIMC) nie znaja pojecia okresu
    probkowania - wyznaczaja nastawy dla obiektu ciaglego. Probkowanie
    dziala jak dodatkowe opoznienie ~Ts/2 = 30 s, co przy opoznieniu
    obiektu L = 2001 s zmienia efektywne L o 1.5% - czyli pomijalnie.
    (Gdyby Ts uroslo do minut, nalezaloby przeliczyc reguly z L' = L + Ts/2.)
    """
    def __init__(self, Kp, Ti, Td, target_temp=4.0, Ts=60.0, **_ignorowane):
        super().__init__(Kp, Ti, Td, target_temp=target_temp)
        self.Ts = Ts
        self.t_ostatni = None
        self.u_trzymane = 0.0
 
    def compute_control(self, row_data):
        t = row_data['Timestamp']
        if (self.t_ostatni is None
                or (t - self.t_ostatni).total_seconds() >= self.Ts - 1e-9):
            # jedno "tykniecie" regulatora dyskretnego: przekazujemy wiersz
            # do prawa PID bazowego, ktore samo wyznaczy dt = Ts z Timestampow
            self.u_trzymane = super().compute_control(row_data)
            self.t_ostatni = t
        return self.u_trzymane