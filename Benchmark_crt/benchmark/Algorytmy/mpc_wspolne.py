# Algorytmy/mpc_wspolne.py
#
# Wspólny rdzeń regulatora predykcyjnego (MPC - Model Predictive Control):
# na KAŻDYM 15-minutowym bloku (siatka HORIZON_STEPS/STEP_SECONDS, ta sama co
# prognoza Kalmana i cyfrowy bliźniak w rdzen_kontrolera.py) rozwiązuje QP
# (przez scipy.optimize.minimize, L-BFGS-B, box-constraints 0-100%) na 8
# przyszłych wartościach mocy, minimalizując energię + karę za spadek poniżej
# progu bezpieczeństwa (setpoint z funkcji ryzyka) + karę za skoki mocy -
# i APLIKUJE STAŁĄ moc z PIERWSZEGO bloku planu przez CAŁY ten blok (move
# blocking o długości = horyzont planowania = 900s), zanim przeplanuje od nowa.
#
# W ODRÓŻNIENIU od funkcja_nauka_kary_pid_blizniak.py/_ryzyko.py (cyfrowy
# bliźniak używany TYLKO jako feedforward do korekty POJEDYNCZEGO kroku), tu
# cyfrowy bliźniak jest PODSTAWĄ OPTYMALIZACJI CAŁEJ TRAJEKTORII na horyzoncie.
#
# Dwie konkretne klasy dziedziczą _MPCMachineryMixin RAZEM z odpowiednim
# wariantem funkcji ryzyka (patrz funkcja_mpc_liniowy.py/funkcja_mpc_prognoza.py):
#   KontrolerMPCBazowy      = _MPCMachineryMixin + KontrolerRyzykaBazowy
#   KontrolerMPCBazowyOpad  = _MPCMachineryMixin + KontrolerRyzykaOpadBazowy
#
# OTWARTE PYTANIA Z PROPOZYCJI (rozstrzygnięte tutaj, patrz AGENTS.md):
#   1) Częstotliwość ponownego rozwiązywania QP: co JEDEN blok 15-minutowy
#      (STEP_SECONDS=900s), NIE co krok symulacji - dla dt_sterowania=1s to
#      i tak 900 kroków między przeplanowaniami. Zamiast klasycznego "receding
#      horizon z aplikowaniem tylko pierwszego elementu i przeplanowaniem co
#      krok" (nierealne obliczeniowo przy dt=1s x rok x 43 lokalizacje), plan
#      ma "move blocking" o długości JEDNEGO bloku - decyzyjne QP ma zawsze
#      TYLKO 8 zmiennych (moc na 8 przyszłych bloków 15-min), niezależnie od
#      dt_sterowania. Model wewnętrzny MPC jest zbudowany BEZPOŚREDNIO w
#      rozdzielczości bloku (dt=STEP_SECONDS, patrz _zbuduj_model_blokowy) -
#      NIE w rozdzielczości dt_sterowania jak "cyfrowy bliźniak" reszty
#      algorytmów - to świadomy kompromis wydajność/optymalność (patrz punkt
#      1 propozycji), a nie przeoczenie.
#   2) Solver QP: scipy.optimize.minimize (L-BFGS-B) - BEZ nowej zależności
#      (scipy już jest w requirements.txt, używane też przez _identify_sopdt).
#      Problem jest wypukły (koszt kwadratowy, ograniczenia to tylko boxy),
#      więc L-BFGS-B z różniczkowaniem numerycznym w pełni wystarcza - nie ma
#      potrzeby dedykowanego solvera QP (osqp/cvxpy).
#   3) Fallback przy niepowodzeniu solvera (wyjątek, NaN w wyniku): OSTATNIA
#      ZASTOSOWANA moc (nie 0%, nie algorytm_z_normy) - najbardziej "gładkie"
#      zachowanie awaryjne, spójne z tym, że MPC i tak kara duże skoki mocy w
#      swojej funkcji celu (MPC_WAGA_ZMIANY_MOCY); status trafia do diagnostyki.
#
# BEZPIECZEŃSTWO: niezależnie od zaplanowanej mocy bloku, jeśli w BIEŻĄCEJ
# chwili (dowolny krok, nie tylko granica bloku) funkcja ryzyka mówi
# need_heat=False, moc jest NATYCHMIAST zerowana (patrz _krok_mpc) - MPC
# planuje trajektorię TYLKO gdy grzanie jest w ogóle potrzebne w danym bloku;
# wyłączenie reaguje od razu (fail-safe szybkie wyłączenie, celowe/rozważne
# załączenie - asymetria uzasadniona w AGENTS.md).

import itertools

import numpy as np
from scipy import signal
from scipy.optimize import minimize

from rdzen_kontrolera import HORIZON_STEPS, STEP_SECONDS, NANOS_PER_BIN
from funkcja_ryzyka_adrc_wspolne import ADRC_FALLBACK_K, ADRC_FALLBACK_T1, ADRC_FALLBACK_T2, ADRC_FALLBACK_L

MPC_WAGA_ENERGIA = 0.01          # w1: kara za pobór mocy [na (%)^2] - energia zużyta w bloku.
MPC_WAGA_BEZPIECZENSTWO = 20.0   # w2: kara za spadek przewidywanej HRT poniżej progu bezpieczeństwa [na (°C)^2].
MPC_WAGA_ZMIANY_MOCY = 0.02      # w3: kara za skok mocy między kolejnymi blokami [na (%)^2] - ogranicza zużycie przekaźnika.
# UWAGA: wagi to rozsądny punkt startowy (ten sam rząd wielkości co pozostałe
# człony kosztu przy typowych deficytach rzędu kilku °C), NIE wynik strojenia -
# dobry kandydat do (planowanego, patrz AGENTS.md) grid searchu z Części 2.

MPC_FALLBACK_KC_PERCENT_NA_C = 3.0  # Prosty regulator P (°C -> %) używany, dopóki autotest się nie powiódł/nie zbudował modelu blokowego.
MPC_MAX_ITER_SOLVER = 60            # Limit iteracji L-BFGS-B na jedno przeplanowanie (koszt vs. dokładność).
MPC_HISTORIA_U_MAX_BLOKOW = 64      # Zapas ponad typowe opóźnienie L w blokach (L~1200s / 900s ~ 1-2 bloki).

# BEZPIECZEŃSTWO (patrz _wiarygodny_pomiar_hrt niżej i notatki/algorytmy/mpc.md,
# sekcja "Zabezpieczenie przed obciążonym czujnikiem HRT"): próg rozbieżności
# pomiar-vs-model powyżej którego NIE ufamy zmierzonemu HRT_temp_grzana przy
# wyznaczaniu progu/celu. Dobrany z zapasem nad typowy błąd dopasowania SOPDT
# w warunkach bezawaryjnych (rzędu ułamków-pojedynczych °C), ale wyraźnie
# poniżej wstrzykiwanego w testach awaryjności bias=5°C (test_awarie_czujnikow.py)
# - łapie bias, nie łapie zwykłego szumu pomiarowo-modelowego.
MPC_SANITY_HRT_DELTA_C = 3.0

# Próg jakości dopasowania SOPDT dla wariantu Z ZABEZPIECZENIAMI (patrz
# _MPCMachineryMixinZabezpieczony niżej) - T1/T2 DOKŁADNIE (lub blisko) dolnej
# granicy solvera (rdzen_kontrolera._identify_sopdt: bounds_lower=[0.1,5.0,5.0,0.0])
# to jednoznaczny odcisk palca ucięcia autotestu w połowie transjentu (patrz
# notatki/algorytmy/mpc.md) - prawdziwe stałe czasowe grzałki rozjazdu są rzędu
# 10^3 s, więc żadne poprawne dopasowanie nie ląduje tu przez przypadek.
MPC_MIN_STALA_CZASOWA_S = 5.5
MPC_MIN_R_KWADRAT = 0.8


class _MPCMachineryMixin:
    """
    Mixin (BEZ własnej klasy bazowej - dziedziczy się go RAZEM z
    KontrolerRyzykaBazowy/KontrolerRyzykaOpadBazowy, patrz nagłówek pliku)
    zawierający całą maszynerię MPC: budowę modelu blokowego z wyniku
    autotestu, symulację trajektorii w przód, funkcję kosztu i rozwiązywanie
    QP. NIE zawiera logiki wyznaczania celu (target_temperature/need_heat) -
    to dostarcza klasa funkcji ryzyka, po której się dziedziczy.
    """

    def __init__(self):
        super().__init__()
        self._mpc_model_zbudowany = False
        self._mpc_model_A = None
        self._mpc_model_B = None
        self._mpc_model_C = None
        self._mpc_model_D = None
        self._mpc_model_opoznienie_bloki = 0
        self._mpc_model_x = None
        self._mpc_model_u_history = []

        self._mpc_bin_id = None            # Id bieżącego bloku 15-minutowego (patrz NANOS_PER_BIN).
        self._mpc_plan_power_pct = 0.0     # Moc [%] zaplanowana na BIEŻĄCY blok (pierwszy element ostatniego planu).
        self._mpc_ostatnia_trajektoria = None  # Ostatnio rozwiązana trajektoria (do warm-startu kolejnego QP).
        self._mpc_ostatni_status = 'brak_planu'

    def _zbuduj_model_blokowy_jesli_trzeba(self):
        """
        Buduje dyskretny model stanowy grzałki W ROZDZIELCZOŚCI BLOKU (dt=
        STEP_SECONDS=900s) z parametrów SOPDT zidentyfikowanych przez autotest
        (self.autotest_result) - RAZ, po udanym autoteście. Ta sama metoda co
        rdzen_kontrolera.KontrolerBazowy._zbuduj_model_z_autotestu (tf2ss +
        cont2discrete, zoh), tylko z INNYM krokiem dyskretyzacji - MPC planuje
        na siatce 15-minutowej (patrz uzasadnienie w nagłówku pliku), więc
        model od razu budowany w tej rozdzielczości (1 krok modelu = 1 blok),
        zamiast symulować tysiące podkroków dt_sterowania wewnątrz QP.
        """
        if self._mpc_model_zbudowany or self.autotest_result is None or not self.autotest_result['fit_ok']:
            return

        wynik = self.autotest_result
        K, T1, T2, L = wynik['K'], wynik['T1'], wynik['T2'], wynik['L']
        tf = signal.TransferFunction([K * 0.0, K], np.polymul([T1, 1], [T2, 1]).tolist())
        sys_ss = signal.tf2ss(tf.num, tf.den)
        A_d, B_d, C_d, D_d, _ = signal.cont2discrete(sys_ss, STEP_SECONDS, method='zoh')

        self._mpc_model_A = A_d
        self._mpc_model_B = B_d
        self._mpc_model_C = C_d
        self._mpc_model_D = D_d
        self._mpc_model_opoznienie_bloki = max(int(round(L / STEP_SECONDS)), 0)
        self._mpc_model_x = np.zeros((A_d.shape[0], 1))
        self._mpc_model_u_history = []
        self._mpc_model_zbudowany = True

    def _przewiduj_trajektorie(self, u_blocks_frac):
        """
        Symuluje model blokowy W PRZÓD na len(u_blocks_frac) bloków, BEZ
        mutowania stanu instancji (self._mpc_model_x/_mpc_model_u_history
        pozostają nietknięte - to jest próbna symulacja wewnątrz optymalizacji,
        wywoływana wielokrotnie na jedno rozwiązanie QP). Zwraca tablicę
        wartości 'y' (składowa grzewcza HRT-CRT) NA KONIEC każdego bloku -
        rzeczywisty stan po zastosowaniu mocy tego bloku przez cały jego czas
        trwania (w odróżnieniu od rdzen_kontrolera._krok_modelu, gdzie y jest
        liczone PRZED przesunięciem stanu - tu, dla MPC, bardziej naturalne
        jest przewidywanie temperatury NA KONIEC bloku, czyli PO jego wpływie).
        """
        x = self._mpc_model_x.copy()
        historia = self._mpc_model_u_history
        u_pelna = historia + list(u_blocks_frac)
        opoznienie = self._mpc_model_opoznienie_bloki
        start_idx = len(historia)

        n_bloki = len(u_blocks_frac)
        y = np.empty(n_bloki, dtype=np.float64)
        for i in range(n_bloki):
            idx = start_idx + i
            u_delayed = u_pelna[idx - opoznienie] if idx - opoznienie >= 0 else 0.0
            x = self._mpc_model_A @ x + self._mpc_model_B * u_delayed
            y[i] = float((self._mpc_model_C @ x + self._mpc_model_D * u_delayed)[0, 0])
        return y

    def _koszt_mpc(self, u_blocks_pct, crt_forecast, target_temperature, ostatnia_moc_pct):
        """J = suma po blokach horyzontu: energia + kara bezpieczeństwa (hook, patrz
        _kara_bezpieczenstwa_mpc) + kara za skok mocy."""
        u_blocks_pct = np.asarray(u_blocks_pct, dtype=np.float64)
        y_blocks = self._przewiduj_trajektorie(u_blocks_pct / 100.0)
        hrt_pred = crt_forecast + y_blocks
        kara_bezpieczenstwa = self._kara_bezpieczenstwa_mpc(hrt_pred, target_temperature)
        poprzednie = np.concatenate(([ostatnia_moc_pct], u_blocks_pct))
        delta_u = np.diff(poprzednie)

        return float(
            MPC_WAGA_ENERGIA * np.sum(u_blocks_pct ** 2)
            + kara_bezpieczenstwa
            + MPC_WAGA_ZMIANY_MOCY * np.sum(delta_u ** 2)
        )

    def _kara_bezpieczenstwa_mpc(self, hrt_pred, target_temperature):
        """
        Domyślny kształt kary za zbliżanie się do progu bezpieczeństwa: kwadratowa
        PROGOWA - dokładnie ZERO, dopóki przewidywana HRT jest powyżej progu, kwadrat
        deficytu poniżej (patrz MPC_WAGA_BEZPIECZENSTWO). Nadpisywane przez warianty z
        INNĄ filozofią kary (patrz funkcja_mpc_miekkie.py - bariera wykładnicza, rosnąca
        już PRZED przekroczeniem progu, nie tylko po nim) - hook istnieje właśnie po to,
        żeby taki wariant dzielił CAŁĄ resztę maszynerii MPC (model, solver, fallback)
        bez duplikacji kodu.
        """
        deficyt = np.maximum(target_temperature - hrt_pred, 0.0)
        return MPC_WAGA_BEZPIECZENSTWO * float(np.sum(deficyt ** 2))

    def _rozwiaz_mpc(self, crt_forecast, target_temperature, ostatnia_moc_pct):
        """Rozwiązuje QP (L-BFGS-B, boxy 0-100%) na horyzoncie min(len(crt_forecast), HORIZON_STEPS) bloków."""
        horizon = min(len(crt_forecast), HORIZON_STEPS) if crt_forecast else 0
        if horizon == 0:
            return np.array([ostatnia_moc_pct]), 'brak_prognozy_crt_fallback_ostatnia_moc'

        crt_arr = np.asarray(crt_forecast[:horizon], dtype=np.float64)

        x0 = self._mpc_ostatnia_trajektoria
        if x0 is None or len(x0) != horizon:
            x0 = np.full(horizon, max(ostatnia_moc_pct, 10.0))
        else:
            x0 = np.concatenate([x0[1:], x0[-1:]])  # Warm-start: przesuń poprzedni plan o jeden blok.

        try:
            wynik = minimize(
                self._koszt_mpc, x0, args=(crt_arr, target_temperature, ostatnia_moc_pct),
                method='L-BFGS-B', bounds=[(0.0, 100.0)] * horizon,
                options={'maxiter': MPC_MAX_ITER_SOLVER},
            )
        except Exception:
            return np.full(horizon, ostatnia_moc_pct), 'solver_wyjatek_fallback_ostatnia_moc'

        # Przybliżony koszt liczenia: nfev wywołań kosztu, każde ~O(horizon*n^2) (symulacja modelu) +
        # O(horizon) (redukcja kosztu) - n=wymiar stanu modelu blokowego (zwykle 2).
        n = self._mpc_model_A.shape[0]
        self._dodaj_flopy(int(wynik.nfev) * horizon * (2 * n * n + 4 * n + 6))

        u_opt = np.clip(wynik.x, 0.0, 100.0)
        if not np.all(np.isfinite(u_opt)):
            return np.full(horizon, ostatnia_moc_pct), 'solver_nan_fallback_ostatnia_moc'

        self._mpc_ostatnia_trajektoria = u_opt
        return u_opt, ('ok' if wynik.success else 'solver_niepelna_zbieznosc')

    def _wiarygodny_pomiar_hrt(self, row_data):
        """
        Zabezpieczenie przed obciążonym/uszkodzonym czujnikiem HRT (patrz
        testy/test_awarie_czujnikow.py, scenariusz HRT_bias, i
        notatki/algorytmy/mpc.md). W ODRÓŻNIENIU od regulatorów PID/histereza,
        MPC nie ma naturalnej kompensacji błędu czujnika: próg/cel
        (_evaluate_risk_setpoint) zależy od ZMIERZONEGO hrt_temp (może
        "przepchnąć" priorytet 3 - tani cel ochrony floora -5°C - w priorytet 4
        - droższy suchy mróz +1°C, gdy bias maskuje niski odczyt), ale sam człon
        regulacyjny MPC liczy błąd względem WŁASNEJ predykcji modelu blokowego
        (_przewiduj_trajektorie), NIE względem zmierzonego hrt_temp - więc, w
        przeciwieństwie do PID, nie dostaje kompensującej "ulgi" tego samego
        znaku co bias. Zmierzone empirycznie jako >140% wzrostu zużycia energii
        pod HRT_bias przed tym zabezpieczeniem.

        Krzyżowa kontrola: porównuje zmierzony hrt_temp z WŁASNĄ predykcją
        modelu blokowego NA BIEŻĄCĄ chwilę (ten sam model, zero dodatkowego
        kosztu - D=0, transmitancja ściśle właściwa, więc predykcja to po
        prostu C @ x, bez potrzeby feedthrough). Rozbieżność powyżej
        MPC_SANITY_HRT_DELTA_C -> NIE ufamy pomiarowi, podstawiamy pod
        'HRT_temp_grzana' własną predykcję modelu (zwraca SKOPIOWANY row_data,
        oryginał nietknięty) na potrzeby wyznaczenia progu/celu.

        Dostępne dopiero PO zbudowaniu modelu blokowego (_mpc_model_zbudowany) -
        wcześniej brak punktu odniesienia, ufamy pomiarowi jak każdy inny
        kontroler w tej fazie.

        Zwraca (row_data_do_oceny, czy_odrzucono_pomiar).
        """
        if not self._mpc_model_zbudowany:
            return row_data, False

        crt_temp = float(row_data['CRT_temp_niegrzana'])
        hrt_zmierzone = float(row_data['HRT_temp_grzana'])
        hrt_przewidywane = crt_temp + float((self._mpc_model_C @ self._mpc_model_x)[0, 0])
        self._dodaj_flopy(6)  # C @ x (2 mnożenia + dodawanie dla stanu 2-wymiarowego) + porównanie.

        if abs(hrt_zmierzone - hrt_przewidywane) <= MPC_SANITY_HRT_DELTA_C:
            return row_data, False

        row_skorygowany = dict(row_data)
        row_skorygowany['HRT_temp_grzana'] = hrt_przewidywane
        return row_skorygowany, True

    def _moc_fallback_p(self, target_temperature, hrt_temp):
        """Prosty regulator P (°C -> %), wyjście ciągłe [0,100] - patrz _krok_mpc. Nadpisywane w _MPCMachineryMixinBinarny."""
        return float(np.clip((target_temperature - hrt_temp) * MPC_FALLBACK_KC_PERCENT_NA_C, 0.0, 100.0))

    def _commit_blok_do_modelu(self, moc_pct_zastosowana):
        """Wołane RAZ na przejście do nowego bloku - dopisuje moc FAKTYCZNIE zastosowaną w POPRZEDNIM bloku do stanu modelu blokowego (analogicznie do rdzen_kontrolera._krok_modelu, w rozdzielczości bloku)."""
        u = moc_pct_zastosowana / 100.0
        self._mpc_model_u_history.append(u)
        if len(self._mpc_model_u_history) > MPC_HISTORIA_U_MAX_BLOKOW * 2:
            self._mpc_model_u_history = self._mpc_model_u_history[-MPC_HISTORIA_U_MAX_BLOKOW:]

        idx = len(self._mpc_model_u_history) - 1
        opoznienie = self._mpc_model_opoznienie_bloki
        u_delayed = self._mpc_model_u_history[idx - opoznienie] if idx - opoznienie >= 0 else 0.0
        self._mpc_model_x = self._mpc_model_A @ self._mpc_model_x + self._mpc_model_B * u_delayed
        n = self._mpc_model_A.shape[0]
        self._dodaj_flopy(2 * n * n + 2 * n)

    def _krok_mpc(self, row_data, target_temperature, need_heat, crt_forecast_fn):
        """
        Rdzeń decyzyjny wspólny dla obu wariantów MPC - wołany PO
        _autotest_startowy/_zbuduj_model_blokowy_jesli_trzeba i PO wyznaczeniu
        target_temperature/need_heat (funkcja ryzyka, jawnie z zewnątrz - patrz
        funkcja_mpc_liniowy.py/funkcja_mpc_prognoza.py, każdy z INNYM
        crt_forecast_fn: stała wartość vs prognoza Kalmana).

        Przeplanowuje TYLKO na granicy bloku 15-minutowego (patrz nagłówek
        pliku, punkt 1) - między granicami zwraca moc zaplanowaną na bieżący
        blok, chyba że need_heat akurat teraz jest False (patrz sekcja
        BEZPIECZEŃSTWO w nagłówku pliku).

        Zwraca (moc_procent, status_string).
        """
        timestamp = row_data['Timestamp']
        hrt_temp = float(row_data['HRT_temp_grzana'])
        bin_id = timestamp.value // NANOS_PER_BIN

        if self._mpc_bin_id is None or bin_id != self._mpc_bin_id:
            if self._mpc_bin_id is not None and self._mpc_model_zbudowany:
                self._commit_blok_do_modelu(self._mpc_plan_power_pct)

            if need_heat and self._mpc_model_zbudowany:
                crt_forecast = crt_forecast_fn()
                u_plan, status = self._rozwiaz_mpc(crt_forecast, target_temperature, self._mpc_plan_power_pct)
                self._mpc_plan_power_pct = float(np.clip(u_plan[0], 0.0, 100.0))
            elif need_heat:
                # Autotest się jeszcze nie powiódł/model blokowy nie zbudowany - prosty regulator P jako telefon
                # awaryjny (analogicznie do "wywołujący ma wrócić do zachowania bez cyfrowego bliźniaka" w
                # rdzen_kontrolera._autotest_startowy), zamiast czekać bezczynnie na model. Wydzielone do
                # _moc_fallback_p (hook) - _MPCMachineryMixinBinarny go nadpisuje, żeby TEN fallback też był
                # binarny (bez tego, moc mogłaby wyjść ciągła w krótkim oknie między autotestem a pierwszym blokiem).
                self._mpc_plan_power_pct = self._moc_fallback_p(target_temperature, hrt_temp)
                status = 'brak_modelu_blokowego_fallback_p'
            else:
                self._mpc_plan_power_pct = 0.0
                status = 'brak_potrzeby_grzania'

            self._mpc_bin_id = bin_id
            self._mpc_ostatni_status = status

        power = self._mpc_plan_power_pct if need_heat else 0.0
        return power, self._mpc_ostatni_status


class _MPCMachineryMixinZabezpieczony(_MPCMachineryMixin):
    """
    Wariant Z ZABEZPIECZENIAMI przed uszkodzonym czujnikiem/identyfikacją - patrz
    notatki/algorytmy/mpc_liniowy_zabezpieczony.md (pełna diagnoza z liczbami, w
    tym HISTORIA NIEUDANEJ pierwszej wersji tego zabezpieczenia - ważna lekcja,
    nie tylko ciekawostka). Dwie NIEZALEŻNE warstwy (obie potrzebne - chronią
    przed RÓŻNYMI awariami, patrz testy/test_awarie_czujnikow.py):

      1) KONTROLA JAKOŚCI DOPASOWANIA SOPDT (_dopasowanie_wiarygodne) - autotest()
         (rdzen_kontrolera.py) przerywa skok grzania 0->100% na PIERWSZYM z trzech
         zdarzeń: zmierzone HRT >= próg bezpieczeństwa, naturalna stabilizacja,
         limit czasu. Pod HRT_bias zmierzone HRT osiąga próg SZTUCZNIE wcześniej
         niż w rzeczywistości, ucinając test w połowie transjentu - identyfikacja
         wtedy trafia w DOLNE OGRANICZENIA solvera (_identify_sopdt:
         bounds_lower=[0.1, 5.0, 5.0, 0.0]), dając PRAKTYCZNIE ZDEGENEROWANY model.
         Zmierzone empirycznie (mpc_liniowy, lokalizacja abisko, HRT_bias+5°C):
         K=5.06, T1=T2=5.0, L~0 - zamiast prawidłowych K~51.1, T1~1129, T2~2443,
         L~1185. Regularny MPC (_MPCMachineryMixin, BEZ zabezpieczeń - patrz
         funkcja_mpc_liniowy.py i in., celowo zostawione bez zmian na życzenie
         użytkownika 2026-09-15, jako punkt odniesienia w teście awaryjności) ufa
         takiemu dopasowaniu bezkrytycznie: obiekt "wygląda" jak słaby, prawie
         natychmiastowy grzejnik, QP utyka przy 100% mocy próbując dogonić
         nieosiągalny cel - zmierzone jako +157% energii w tym samym teście.

         WAŻNE - PIERWSZA WERSJA tej warstwy (odrzuć dopasowanie -> zostań NA
         ZAWSZE na regulatorze P, MPC_FALLBACK_KC_PERCENT_NA_C) była ZMIERZONA
         jako NIEBEZPIECZNA, nie tylko "mniej optymalna": ten regulator P liczy
         błąd względem TEGO SAMEGO zmierzonego (obciążonego) HRT, który jest
         PRZYCZYNĄ odrzucenia dopasowania - żadnej ochrony przed sensorem. Pod
         HRT_bias dawało to min_hrt=-17.0°C (GŁĘBOKO pod bezwzględnym floorem
         -10°C!) i karę bezpieczeństwa ~4.2 mln - GORZEJ niż niezabezpieczony
         wariant (min_hrt=-5.4°C, kara=0), mimo mniejszej energii. "Bezpieczne"
         okazało się mniej bezpieczne niż "marnotrawne". Poprawka: gdy
         dopasowanie jest niewiarygodne, model blokowy jest budowany z
         BEZPIECZNYCH, wcześniej zidentyfikowanych wartości domyślnych
         (ADRC_FALLBACK_K/T1/T2/L z funkcja_ryzyka_adrc_wspolne.py - ten sam
         obiekt fizyczny, ta sama grzałka, sprawdzone jako reprezentatywne)
         ZAMIAST porzucać model - dzięki temu QP dalej planuje na SENSOWNYCH
         parametrach, i (kluczowe) warstwa 2 niżej staje się AKTYWNA (wymaga
         zbudowanego modelu), więc może korygować bieżący pomiar w czasie
         rzeczywistym. `_mpc_model_odrzucony` zostaje jako flaga DIAGNOSTYCZNA
         (dopasowanie było odrzucone - patrz diagnostics['model_blokowy_odrzucony']),
         NIE jako "porzuć model na zawsze".

      2) KRZYŻOWA KONTROLA BIEŻĄCEGO POMIARU HRT (_wiarygodny_pomiar_hrt,
         odziedziczone z _MPCMachineryMixin) - NIEZALEŻNA druga warstwa: nawet
         gdy model JEST wiarygodny (lub podstawiony bezpiecznymi domyślnymi -
         patrz warstwa 1), chroni przed BIEŻĄCYM obciążonym/uszkodzonym
         odczytem wpływającym na wybór progu/celu (_evaluate_risk_setpoint) -
         patrz tam pełny opis mechanizmu. To WŁAŚNIE ta warstwa - AKTYWNA teraz,
         bo model istnieje - faktycznie chroni przed niedogrzaniem pod HRT_bias
         (w odróżnieniu od czystego regulatora P, który nie ma z czym porównać
         zmierzonego HRT).
    """

    def __init__(self):
        super().__init__()
        self._mpc_model_odrzucony = False  # Diagnostyka - czy PIERWOTNE dopasowanie SOPDT było niewiarygodne (patrz wyżej).

    def _dopasowanie_wiarygodne(self, wynik):
        if wynik is None or not wynik.get('fit_ok'):
            return False
        if wynik['T1'] <= MPC_MIN_STALA_CZASOWA_S or wynik['T2'] <= MPC_MIN_STALA_CZASOWA_S:
            return False
        if wynik['r_squared'] is None or wynik['r_squared'] < MPC_MIN_R_KWADRAT:
            return False
        return True

    def _zbuduj_model_blokowy_jesli_trzeba(self):
        if self._mpc_model_zbudowany:
            return
        if self.autotest_result is None:
            return
        if not self._dopasowanie_wiarygodne(self.autotest_result):
            self._mpc_model_odrzucony = True
            # NIE mutujemy self.autotest_result w miejscu (mogliby czytać go inni
            # konsumenci tej samej instancji) - podstawiamy kopię z bezpiecznymi
            # wartościami domyślnymi TYLKO do budowy modelu blokowego.
            wynik_bezpieczny = dict(self.autotest_result)
            wynik_bezpieczny.update(K=ADRC_FALLBACK_K, T1=ADRC_FALLBACK_T1, T2=ADRC_FALLBACK_T2,
                                     L=ADRC_FALLBACK_L, fit_ok=True)
            oryginalny_wynik = self.autotest_result
            self.autotest_result = wynik_bezpieczny
            try:
                super()._zbuduj_model_blokowy_jesli_trzeba()
            finally:
                self.autotest_result = oryginalny_wynik
            return
        super()._zbuduj_model_blokowy_jesli_trzeba()


MPC_BINARNE_POZIOMY = (0.0, 100.0)  # Dopuszczalna moc na blok - TYLKO załącz/wyłącz (patrz _MPCMachineryMixinBinarny).


class _MPCMachineryMixinBinarny(_MPCMachineryMixin):
    """
    Wariant BINARNY - zamiast rozwiązywać QP z wyjściem ciągłym [0,100]% (scipy
    L-BFGS-B), PRZESZUKUJE WYCZERPUJĄCO wszystkie kombinacje {0%, 100%} na
    horyzoncie planowania (2^HORIZON_STEPS = 2^8 = 256 kombinacji - tanie
    obliczeniowo, bo przeplanowanie i tak następuje raz na blok 900s, patrz
    nagłówek pliku) i wybiera tę o NAJNIŻSZYM koszcie wg _koszt_mpc - TEJ SAMEJ
    funkcji celu co wariant ciągły (energia + kara bezpieczeństwa + kara za
    skoki mocy). Różni się WYŁĄCZNIE dopuszczalny zbiór mocy (przekaźnik
    załącz/wyłącz, jak w większości pozostałych algorytmów projektu, zamiast
    SSR/PWM), NIE model/kara/częstotliwość przeplanowania - to celowe, żeby
    porównanie z mpc_liniowy (patrz funkcja_mpc_binarny.py) izolowało WYŁĄCZNIE
    wpływ dyskretyzacji mocy, nie żadnej innej różnicy.

    Wyczerpujące przeszukanie (nie relaksacja LP + zaokrąglenie, nie MILP) jest
    tu UZASADNIONE, nie tylko wygodne: przy horyzoncie=8 daje DOKŁADNE optimum
    globalne (nie tylko lokalne, w odróżnieniu od L-BFGS-B na problemie ciągłym,
    które i tak nie ma gwarancji globalności przy nieliniowej barierze - patrz
    funkcja_mpc_miekkie.py) - 256 wywołań _koszt_mpc (każde O(horyzont)) na
    JEDNO przeplanowanie co 900s jest znikomym kosztem.
    """

    def _rozwiaz_mpc(self, crt_forecast, target_temperature, ostatnia_moc_pct):
        horizon = min(len(crt_forecast), HORIZON_STEPS) if crt_forecast else 0
        if horizon == 0:
            return np.array([ostatnia_moc_pct]), 'brak_prognozy_crt_fallback_ostatnia_moc'

        crt_arr = np.asarray(crt_forecast[:horizon], dtype=np.float64)

        najlepszy_koszt = np.inf
        najlepsza_sekwencja = None
        for kombinacja in itertools.product(MPC_BINARNE_POZIOMY, repeat=horizon):
            u = np.array(kombinacja, dtype=np.float64)
            koszt = self._koszt_mpc(u, crt_arr, target_temperature, ostatnia_moc_pct)
            if koszt < najlepszy_koszt:
                najlepszy_koszt = koszt
                najlepsza_sekwencja = u

        # Przybliżony koszt liczenia: 2^horyzont ewaluacji _koszt_mpc, każda O(horyzont*n^2)
        # (symulacja modelu, jak w _rozwiaz_mpc ciągłym) - n=wymiar stanu modelu blokowego.
        n = self._mpc_model_A.shape[0]
        self._dodaj_flopy(len(MPC_BINARNE_POZIOMY) ** horizon * horizon * (2 * n * n + 4 * n + 6))

        self._mpc_ostatnia_trajektoria = najlepsza_sekwencja
        return najlepsza_sekwencja, 'ok_przeszukanie_wyczerpujace'

    def _moc_fallback_p(self, target_temperature, hrt_temp):
        """Jak w _MPCMachineryMixin, ale BINARYZOWANE (próg 50%, jak silniki_fuzzy.binaryzuj) - patrz nagłówek klasy."""
        ciagla = super()._moc_fallback_p(target_temperature, hrt_temp)
        return 100.0 if ciagla >= 50.0 else 0.0
