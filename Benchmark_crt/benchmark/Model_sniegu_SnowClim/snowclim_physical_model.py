# ==============================================================================
# FIZYCZNY MODEL ŚNIEGU/LODU NA SZYNIE - MECHANIZMY Z pySnowClim
# (Abby Lute, https://abbylute.github.io/pySnowClim/, https://github.com/abbylute/pySnowClim)
#
# Zamiast prostego współczynnika topnienia (stary SnowIcePhysicalModel z
# main_test.py), tutaj pokrywa śnieżna jest symulowana pełnym BILANSEM ENERGII
# punktowym, krok 1-sekundowy, z mechanizmami przeportowanymi wprost z kodu
# źródłowego pySnowClim (src/*.py):
#   - podział opadu na śnieg/deszcz: regresja logistyczna Jennings i in. (2018)
#     (calcPhase.py) zamiast sztywnego progu 0°C,
#   - bilans energii pokrywy: promieniowanie krótkofalowe (z albedo),
#     długofalowe (prawo Stefana-Boltzmanna, calcLongwave.py), strumienie
#     turbulentne jawny/utajony metodą bulk-aerodynamiczną z korekcją
#     stabilności liczbą Richardsona (calcTurbulentFluxes.py), ciepło
#     adwekcyjne deszczu,
#   - kaskada energii: zawartość zimna (cold content) -> zamarzanie wody
#     w pokrywie -> topnienie (calcEnergyToCC.py, calcEnergyToRefreezing.py,
#     calcEnergyToMelt.py) - dokładnie te same stałe i wzory,
#   - sublimacja/kondensacja ze strumienia utajonego (calcSublimation.py),
#   - gęstość świeżego śniegu (Anderson 1976 / Essery i in. 2013,
#     calcFreshSnowDensity.py), łączenie gęstości po opadzie (Essery i in.
#     2013 eq.17, calcSnowDensityAfterSnow.py) i kompakcja/osiadanie w czasie
#     (Essery/Anderson/Boone, calcSnowDensity.py),
#   - albedo: wariant VIC (calcAlbedo.py, _calc_albedo_vic) - starzenie się
#     śniegu osobno dla fazy "zimnej" i "topniejącej", odświeżenie przy
#     świeżym opadzie, zanik przy cienkiej pokrywie w stronę albedo gruntu.
#
# RÓŻNICE WZGLĘDEM ORYGINAŁU (świadome adaptacje do naszego przypadku):
#   1. pySnowClim jest modelem SIATKOWYM z krokiem czasowym rzędu godzin/doby
#      (domyślnie hours_in_ts=24) do symulacji terenu. Tutaj model jest
#      PUNKTOWY (jedna szyna) z krokiem 1 s - wszystkie wzory energetyczne
#      pozostały identyczne (są niezależne od skali czasu, tylko mnożone przez
#      sec_in_ts), ale próg "świeżego śniegu" dla albedo (VIC: >0.01 m w JEDNYM
#      kroku) jest bez sensu przy kroku 1 s (0.01 m wody w ciągu sekundy to
#      ekstremalna ulewa) - dlatego świeży śnieg jest akumulowany w liczniku
#      kroczącym i próg jest sprawdzany na skumulowanej wartości.
#   2. pySnowClim potrzebuje wejść, których nie mamy w danych pogodowych
#      (promieniowanie długofalowe w dół, promieniowanie krótkofalowe wprost
#      w W/m2) - są tu SZACOWANE z dostępnych danych: nasłonecznienie
#      (sekundy słońca / 900 s = ułamek Angströma-Prescotta, FAO-56) daje
#      promieniowanie krótkofalowe, a wzór Brutsaerta (1975) + korekta
#      zachmurzenia (Crawford & Duchon, 1999) z tego samego ułamka słońca daje
#      promieniowanie długofalowe w dół.
#   3. Strumień gruntowy G w oryginale jest STAŁĄ (Walter i in. 2005, ciepło
#      geotermalne gleby). U nas "podłożem" pokrywy jest OGRZEWANA SZYNA (HRT)
#      - dużo lepsze, bo prawdziwe fizycznie źródło ciepła niż stała - więc G
#      zastąpiono przewodzeniem proporcjonalnym do zmierzonej/zasymulowanej
#      HRT: G_szyny = h_kontakt * max(0, HRT) (aktywne tylko gdy szyna cieplejsza
#      od 0°C). Współczynnik h_kontakt wymaga kalibracji do rzeczywistych
#      obserwacji zaniku śniegu na szynie - nie ma go w pySnowClim, bo ten
#      model nie zna pojęcia ogrzewanej infrastruktury.
#   4. Pominięto wygładzanie energii ("cold content tax") z oryginału, które
#      w pySnowClim tłumi ujemną energię uśrednioną z ok. doby, by uniknąć
#      artefaktów przy dużym kroku czasowym - przy kroku 1 s i tak dominującym
#      źródle ciepła (HRT) ten efekt jest pomijalny.
#   5. Szkliste oblodzenie z marznącego deszczu wprost na zimnej, gołej szynie
#      (bez zalegającego śniegu) to zjawisko INNE niż pokrywa śnieżna modelowana
#      przez pySnowClim (który nie modeluje oblodzenia obiektów) - zostawiono
#      je jako osobny, prosty kanał (jak w starym modelu), aktywny tylko gdy
#      na szynie nie ma jeszcze śniegu.
#
# WYDAJNOŚĆ: krok update() jest wołany raz na sekundę symulacji, dla KAŻDEGO
# testowanego algorytmu (miliony wywołań na pełny sezon x kilka lokalizacji) i
# zawiera sporo funkcji przestępnych (exp/log/potęgi) - profil pokazał, że to
# najkosztowniejsza część pojedynczego kroku symulacji (uruchom_kontroler w
# symulacja_fizyczna.py), więc cała logika jest skompilowana JIT-em numba
# (_snowclim_update_core) zamiast rozbita na metody Pythona. Stan obiektu jest
# trzymany w płaskiej tablicy float64 (nie w atrybutach), bo numba w trybie
# nopython nie obsługuje dowolnych obiektów Pythona (w tym pandas.Timestamp) -
# dlatego dzień roku/godzina dekadowa (potrzebne do geometrii słonecznej) są
# wyliczane z timestampu PRZED wejściem do funkcji JIT.
# ==============================================================================

import math

import numpy as np
from numba import njit

# ==== STAŁE FIZYCZNE (identyczne jak pySnowClim/src/constants.py) ====
WATERDENS = 1000.0      # gęstość wody [kg/m3]
LATHEATFREEZ = 333.3    # ciepło topnienia lodu [kJ/kg]
CI = 2.117              # ciepło właściwe śniegu [kJ/kg/K]
CW = 4.2                # ciepło właściwe wody [kJ/kg/K]
CA = 1.005              # ciepło właściwe powietrza [kJ/kg/K]
VON_KARMAN = 0.41
SB_CONST = 5.67e-11     # stała Stefana-Boltzmanna [kJ/m2/K4/s] (jak w calcLongwave.py)
K_2_C = 273.15

# --- Indeksy w tablicy stanu (mutowalne z kroku na krok) ---
S_SWE_M = 0             # snow water equivalent [m wody]
S_SNOW_DEPTH_M = 1      # grubość pokrywy [m]
S_PACK_DENSITY = 2      # [kg/m3]
S_PACK_WATER_M = 3      # ciekła woda zatrzymana w pokrywie [m wody]
S_PACK_CC = 4           # zawartość zimna (cold content) [kJ/m2], <= 0
S_SNOW_TEMP = 5         # reprezentatywna temperatura powierzchni śniegu [°C]
S_ALBEDO = 6
S_SNOW_AGE_S = 7
S_NEW_SNOW_ACCUM_M = 8  # licznik kroczący świeżego śniegu (adaptacja do kroku 1s)
S_ICE_M = 9             # osobny, prosty kanał oblodzenia (marznący deszcz na gołej szynie)
S_LAST_CLOUD_FRACTION = 10  # pamięć zachmurzenia w nocy (persystencja ostatniej dziennej obserwacji)
STATE_SIZE = 11

# --- Indeksy w tablicy parametrów (stałe przez cały czas życia obiektu) ---
P_SNOW_EMIS = 0
P_GROUND_ALBEDO = 1
P_MAX_ALBEDO = 2
P_WIND_HT = 3
P_TEMP_HT = 4
P_Z0 = 5
P_ZH = 6
P_STABILITY = 7          # 1.0 = True, 0.0 = False (numba nopython lubi floaty, nie booly w tablicach)
P_E0_VALUE = 8
P_LW_MAX_FRACTION = 9
P_SNOW_DENS_DEFAULT = 10
P_LATITUDE_RAD = 11
P_H_RAIL_CONTACT = 12
PARAMS_SIZE = 13


@njit(cache=True)
def _snowclim_update_core(state, params, day_of_year, hour_decimal,
                           at_temp, dew_point, wind_speed, pressure_hpa,
                           precip_mm, sunshine_seconds_per_900s, hrt_temp, dt):
    """
    Rdzeń kroku symulacji (patrz SnowClimPhysicalModel.update dla opisu
    parametrów) - identyczna logika i kolejność operacji co w oryginalnej
    implementacji obiektowej, tylko rozpisana na skalary + tablicę stanu,
    żeby numba mogła to skompilować w trybie nopython. Mutuje `state` w
    miejscu i zwraca (grubosc_sniegu_mm, grubosc_lodu_mm).
    """
    swe_m = state[S_SWE_M]
    snow_depth_m = state[S_SNOW_DEPTH_M]
    pack_density = state[S_PACK_DENSITY]
    pack_water_m = state[S_PACK_WATER_M]
    pack_cc = state[S_PACK_CC]
    snow_temp = state[S_SNOW_TEMP]
    albedo = state[S_ALBEDO]
    snow_age_s = state[S_SNOW_AGE_S]
    new_snow_accum_m = state[S_NEW_SNOW_ACCUM_M]
    ice_m = state[S_ICE_M]
    last_cloud_fraction = state[S_LAST_CLOUD_FRACTION]

    snow_emis = params[P_SNOW_EMIS]
    ground_albedo = params[P_GROUND_ALBEDO]
    max_albedo = params[P_MAX_ALBEDO]
    wind_ht = params[P_WIND_HT]
    temp_ht = params[P_TEMP_HT]
    z0 = params[P_Z0]
    zh = params[P_ZH]
    stability = params[P_STABILITY] > 0.5
    e0_value = params[P_E0_VALUE]
    lw_max_fraction = params[P_LW_MAX_FRACTION]
    snow_dens_default = params[P_SNOW_DENS_DEFAULT]
    latitude_rad = params[P_LATITUDE_RAD]
    h_rail_contact = params[P_H_RAIL_CONTACT]

    # --- _estimate_relative_humidity (Magnus/Bolton) ---
    es_t = 6.112 * math.exp((17.67 * at_temp) / (at_temp + 243.5))
    es_td = 6.112 * math.exp((17.67 * dew_point) / (dew_point + 243.5))
    rh = 100.0 * es_td / es_t
    rh = min(max(rh, 0.0), 100.0)

    # --- _calc_phase_snow_fraction (Jennings i in., 2018 - calcPhase.py) ---
    psnow = 1.0 / (1.0 + math.exp(-10.04 + 1.41 * at_temp + 0.09 * rh))

    precip_m = max(precip_mm, 0.0) / 1000.0
    snow_new_m = precip_m * psnow
    rain_m = precip_m * (1.0 - psnow)

    # --- Osobny kanał: marznący deszcz na gołej, zimnej szynie (bez zalegającego śniegu) ---
    if swe_m <= 0 and rain_m > 0 and hrt_temp <= 0.0:
        ice_m += rain_m

    if snow_new_m > 0:
        # --- _fresh_snow_density (Anderson 1976 / Essery i in. 2013) ---
        ef, pmin, df = 15.0, 50.0, 1.7
        capped = max(at_temp, -ef)
        new_density = pmin + max(df * (capped + ef) ** 1.5, 0.0)

        new_snow_temp = min(0.0, dew_point)
        snowfall_cc = WATERDENS * CI * snow_new_m * new_snow_temp  # <= 0

        if swe_m > 0:
            # --- _blend_density_after_snowfall (Essery i in. 2013 eq.17) ---
            pack_density = (swe_m + snow_new_m) / ((swe_m / pack_density) + (snow_new_m / new_density))
        else:
            pack_density = new_density
        swe_m += snow_new_m
        pack_cc += snowfall_cc
        new_snow_accum_m += snow_new_m
        snow_depth_m = swe_m * WATERDENS / pack_density

    exist_snow = swe_m > 0

    if exist_snow:
        snow_temp = min(dew_point + 2.0, 0.0)  # Ts_add=2 (pySnowClim default)

        # --- _turbulent_fluxes_kj_per_ts (bulk-aerodynamiczne, Essery i in. 2013) ---
        if wind_speed <= 0.0:
            h_sensible, e_mass, e_energy = 0.0, 0.0, 0.0
        else:
            r_gas, g_accel, c_stab = 287.0, 9.80616, 5.0
            pa = (pressure_hpa * 100.0) / (r_gas * (at_temp + K_2_C))
            # --- _specific_humidity (Bolton 1980), dla powietrza i dla śniegu ---
            e_air = 6.112 * math.exp((17.67 * dew_point) / (dew_point + 243.5))
            rho_air = (0.622 * e_air) / (pressure_hpa - (0.378 * e_air))
            e_snow = 6.112 * math.exp((17.67 * snow_temp) / (snow_temp + 243.5))
            rho_snow = (0.622 * e_snow) / (pressure_hpa - (0.378 * e_snow))

            ch_neutral = (VON_KARMAN ** 2) / (math.log(wind_ht / z0) * math.log(temp_ht / zh))

            if stability:
                rib = (g_accel * wind_ht * (at_temp - snow_temp)) / ((at_temp + K_2_C) * wind_speed ** 2)
                if rib < 0:
                    fh = 1 - (3 * c_stab * rib) / (1 + 3 * c_stab ** 2 * ch_neutral * (-rib * wind_ht / z0) ** 0.5)
                elif rib > 0:
                    fh = (1 + (2 * c_stab * rib) / (1 + rib) ** 0.5) ** -1
                else:
                    fh = 1.0
                ch = ch_neutral * fh
            else:
                rib = 0.0
                ch = ch_neutral

            # --- _lat_heat_vap / _lat_heat_sub ---
            lat_heat_vap = 2500.8 - 2.36 * snow_temp + 0.016 * snow_temp ** 2 + 0.00006 * snow_temp ** 3
            lat_heat_sub = 2834.1 - 0.29 * snow_temp - 0.004 * snow_temp ** 2

            ex = e0_value if (stability and rib > 0) else 0.0

            h_sensible = -(pa * CA * ch * wind_speed + ex) * (snow_temp - at_temp)
            e_mass = -(pa * ch * wind_speed) * (rho_snow - rho_air)  # kg/m2/s
            e_energy = e_mass * (lat_heat_vap if snow_temp >= 0 else lat_heat_sub)

            h_sensible *= dt
            e_mass *= dt
            e_energy *= dt

        q_precip = 0.0
        if rain_m > 0:
            q_precip = CW * WATERDENS * max(0.0, dew_point) * rain_m
            pack_water_m += rain_m  # deszcz na istniejący śnieg trafia do wody w pokrywie

        # --- _estimate_shortwave_kj_per_ts (Angstrom-Prescott, FAO-56) ---
        sunshine_fraction = sunshine_seconds_per_900s / 900.0
        # --- _extraterrestrial_irradiance_wm2 (FAO-56 / Duffie & Beckman) ---
        declination = math.radians(23.45 * math.sin(math.radians(360.0 / 365.0 * (284 + day_of_year))))
        dr = 1.0 + 0.033 * math.cos(math.radians(360.0 * day_of_year / 365.0))
        hour_angle = math.radians(15.0 * (hour_decimal - 12.0))
        cos_zenith = (math.sin(latitude_rad) * math.sin(declination)
                      + math.cos(latitude_rad) * math.cos(declination) * math.cos(hour_angle))
        cos_zenith = max(0.0, cos_zenith)
        ra_wm2 = 1361.0 * dr * cos_zenith  # solar_constant_wm2 = 1361.0

        sf_clamped = min(max(sunshine_fraction, 0.0), 1.0)
        rs_wm2 = (0.25 + 0.50 * sf_clamped) * ra_wm2
        rs_wm2 = min(max(rs_wm2, 0.0), ra_wm2)
        sw_kj = rs_wm2 * dt / 1000.0

        sw_net = sw_kj * (1.0 - albedo)

        # --- _estimate_longwave_down_kj_per_ts (Brutsaert 1975 + Crawford & Duchon 1999) ---
        e_a_hpa = 6.112 * math.exp((17.67 * dew_point) / (dew_point + 243.5))
        t_a_k = at_temp + K_2_C
        eps_clear = 1.24 * (e_a_hpa / t_a_k) ** (1.0 / 7.0)

        if ra_wm2 > 1.0:  # dzień - liczymy zachmurzenie z ułamka słońca
            cloud_fraction = min(max(1.0 - sunshine_fraction, 0.0), 1.0)
            last_cloud_fraction = cloud_fraction
        else:  # noc - brak obserwacji, ostatnia znana wartość dzienna
            cloud_fraction = last_cloud_fraction

        eps_eff = cloud_fraction * 1.0 + (1.0 - cloud_fraction) * eps_clear
        lw_down_wm2 = eps_eff * (SB_CONST * 1000.0) * t_a_k ** 4
        lw_down = lw_down_wm2 * dt / 1000.0

        snow_temp_k = snow_temp + K_2_C
        lw_up = (snow_emis * (SB_CONST * dt) * snow_temp_k ** 4
                 + (1 - snow_emis) * lw_down)
        lw_net = lw_down - lw_up

        # --- G_szyny: przewodzenie od ogrzewanej szyny (zastępuje stałą G z pySnowClim) ---
        g_rail = h_rail_contact * max(0.0, hrt_temp) * dt

        energy = sw_net + lw_net + h_sensible + e_energy + q_precip + g_rail

        # --- _energy_to_cold_content ---
        if -pack_cc > 0 and -pack_cc <= energy:
            energy += pack_cc
            pack_cc = 0.0
        elif -pack_cc > energy:
            pack_cc += energy
            energy = 0.0

        # --- _energy_to_refreezing ---
        if pack_water_m > 0 and swe_m > 0 and pack_cc < 0 and pack_density < 550:
            prf = WATERDENS * LATHEATFREEZ * pack_water_m
            if -pack_cc >= prf:
                refrozen = pack_water_m
                swe_m += refrozen
                pack_water_m = 0.0
                pack_cc += prf
            else:
                refrozen = -pack_cc / (WATERDENS * LATHEATFREEZ)
                swe_m += refrozen
                pack_water_m -= refrozen
                pack_cc = 0.0
            if snow_depth_m > 0:
                pack_density = swe_m * WATERDENS / snow_depth_m

        # --- _energy_to_melt ---
        if swe_m > 0 and energy > 0:
            potential_melt = energy / (LATHEATFREEZ * WATERDENS)
            melt = min(swe_m, potential_melt)
            pack_water_m += melt
            swe_m -= melt
            energy -= melt * LATHEATFREEZ * WATERDENS
        if swe_m > 0:
            snow_depth_m = swe_m * WATERDENS / pack_density
        else:
            snow_depth_m = 0.0

        # --- _apply_sublimation ---
        mass_flux_m = -(e_mass / WATERDENS)
        if mass_flux_m > 0:  # sublimacja/parowanie - ubytek masy
            loss = min(swe_m, mass_flux_m)
            swe_m -= loss
        else:  # kondensacja/osadzanie - przyrost masy
            swe_m += -mass_flux_m

        if swe_m > 0:
            # --- _compact_density (Essery/Anderson/Boone) ---
            c1, c2, c3, c4, c5, p0, n0, g_const = 2.8e-6, 0.042, 0.046, 0.081, 0.018, 150.0, 3.7e7, 9.81
            mass_kg_m2 = (swe_m / 2.0) * WATERDENS
            nu = n0 * math.exp(c4 * (-snow_temp) + c5 * pack_density)
            delta = pack_density * (
                (mass_kg_m2 * g_const) / nu
                + c1 * math.exp(-c2 * (-snow_temp) - c3 * max(0.0, pack_density - p0))
            )
            pack_density += delta * dt

            snow_depth_m = swe_m * WATERDENS / pack_density
            max_water = lw_max_fraction * swe_m
            if pack_water_m > max_water:
                pack_water_m = max_water  # nadmiar wody odpływa (runoff) - nie śledzimy go dalej
        else:
            # --- _reset_snowpack ---
            swe_m = 0.0
            snow_depth_m = 0.0
            pack_density = snow_dens_default
            pack_water_m = 0.0
            pack_cc = 0.0
            snow_age_s = 0.0
            new_snow_accum_m = 0.0
    else:
        new_snow_accum_m = 0.0

    # --- _update_albedo (wariant VIC - calcAlbedo.py::_calc_albedo_vic) ---
    SEC_PER_DAY = 86400.0
    ACCUM_A, ACCUM_B = 0.94, 0.58
    THAW_A, THAW_B = 0.82, 0.46
    if swe_m <= 0:
        albedo = ground_albedo
        snow_age_s = 0.0
        new_snow_accum_m = 0.0
    else:
        is_fresh_event = new_snow_accum_m > 0.01  # próg VIC (0.01 m), na akumulatorze
        if is_fresh_event and pack_cc < 0:
            snow_age_s = 0.0
            albedo = max_albedo
            new_snow_accum_m = 0.0
        else:
            snow_age_s += dt
            age_days = snow_age_s / SEC_PER_DAY
            if pack_cc < 0:
                albedo = max_albedo * (ACCUM_A ** (age_days ** ACCUM_B))
            else:
                albedo = max_albedo * (THAW_A ** (age_days ** THAW_B))

        # Zanik albedo przy bardzo cienkiej pokrywie w stronę albedo gruntu.
        z = snow_depth_m
        if z < 0.1:
            r = min(1.0, (1 - z / 0.1) * math.exp(-z / 0.2))
            albedo = r * ground_albedo + (1 - r) * albedo

        albedo = min(max(albedo, 0.0), max_albedo)

    # --- Topnienie kanału oblodzenia (ta sama fizyka przewodzenia od szyny) ---
    if ice_m > 0 and hrt_temp > 0.0:
        ice_melt_m = min(ice_m, (h_rail_contact * hrt_temp * dt) / (LATHEATFREEZ * WATERDENS))
        ice_m -= ice_melt_m

    state[S_SWE_M] = swe_m
    state[S_SNOW_DEPTH_M] = snow_depth_m
    state[S_PACK_DENSITY] = pack_density
    state[S_PACK_WATER_M] = pack_water_m
    state[S_PACK_CC] = pack_cc
    state[S_SNOW_TEMP] = snow_temp
    state[S_ALBEDO] = albedo
    state[S_SNOW_AGE_S] = snow_age_s
    state[S_NEW_SNOW_ACCUM_M] = new_snow_accum_m
    state[S_ICE_M] = ice_m
    state[S_LAST_CLOUD_FRACTION] = last_cloud_fraction

    return snow_depth_m * 1000.0, ice_m * 1000.0


class SnowClimPhysicalModel:
    """
    Punktowy, energo-bilansowy model śniegu/lodu na szynie (mechanizmy pySnowClim).

    Cienka, obiektowa otoczka nad _snowclim_update_core (JIT numba) - trzyma
    stan w tablicy float64 (self._state) zamiast w atrybutach, żeby rdzeń
    dało się skompilować, ale interfejs publiczny (konstruktor, .update(...),
    .snow_depth_m) jest identyczny jak przed refaktorem na numba.
    """

    def __init__(self, latitude_deg=54.1, h_rail_contact=0.01, snow_dens_default=250.0):
        ground_albedo = 0.25
        self._params = np.array([
            0.98,               # P_SNOW_EMIS - emisyjność śniegu (Snow and Climate, Armstrong & Brun)
            ground_albedo,      # P_GROUND_ALBEDO
            0.85,               # P_MAX_ALBEDO
            10.0,               # P_WIND_HT - wysokość pomiaru wiatru [m]
            2.0,                # P_TEMP_HT - wysokość pomiaru temperatury [m]
            1e-5,               # P_Z0 - szorstkość aerodynamiczna [m]
            1e-5 / 10.0,        # P_ZH - szorstkość termiczna [m]
            1.0,                # P_STABILITY (True)
            1.0 / 1000.0,       # P_E0_VALUE - bezwietrzny współczynnik wymiany [kJ/m2/K/s]
            0.1,                # P_LW_MAX_FRACTION - maks. udział wody ciekłej w pokrywie
            snow_dens_default,  # P_SNOW_DENS_DEFAULT
            math.radians(latitude_deg),  # P_LATITUDE_RAD
            h_rail_contact,     # P_H_RAIL_CONTACT [kJ/m2/s/°C] - do kalibracji w terenie
        ], dtype=np.float64)

        self._state = np.zeros(STATE_SIZE, dtype=np.float64)
        self._state[S_PACK_DENSITY] = snow_dens_default
        self._state[S_ALBEDO] = ground_albedo
        self._state[S_LAST_CLOUD_FRACTION] = 0.5

    # --- Właściwości tylko-do-odczytu, zgodne z dawnymi atrybutami instancji ---
    @property
    def swe_m(self):
        return self._state[S_SWE_M]

    @property
    def snow_depth_m(self):
        return self._state[S_SNOW_DEPTH_M]

    @property
    def pack_density(self):
        return self._state[S_PACK_DENSITY]

    @property
    def pack_water_m(self):
        return self._state[S_PACK_WATER_M]

    @property
    def pack_cc(self):
        return self._state[S_PACK_CC]

    @property
    def snow_temp(self):
        return self._state[S_SNOW_TEMP]

    @property
    def albedo(self):
        return self._state[S_ALBEDO]

    @property
    def ice_m(self):
        return self._state[S_ICE_M]

    # ------------------------------------------------------------------
    # GŁÓWNY KROK SYMULACJI
    # ------------------------------------------------------------------
    def update(self, timestamp, at_temp, dew_point, wind_speed, pressure_hpa,
               precip_mm, sunshine_seconds_per_900s, hrt_temp, dt=1.0):
        """
        Parametry:
          timestamp: znacznik czasu (do geometrii słonecznej)
          at_temp, dew_point: temperatura powietrza i punkt rosy [°C]
          wind_speed: prędkość wiatru [m/s]
          pressure_hpa: ciśnienie powietrza [hPa]
          precip_mm: opad w tym kroku [mm wody]
          sunshine_seconds_per_900s: "sekundy słońca" w 15-minutowym przedziale (0-900)
          hrt_temp: temperatura szyny ogrzewanej [°C] - zastępuje stałą G z pySnowClim
          dt: długość kroku [s]

        Zwraca: (grubosc_sniegu_mm, grubosc_lodu_mm)
        """
        day_of_year = timestamp.timetuple().tm_yday
        hour_decimal = timestamp.hour + timestamp.minute / 60.0 + timestamp.second / 3600.0
        return _snowclim_update_core(
            self._state, self._params, day_of_year, hour_decimal,
            at_temp, dew_point, wind_speed, pressure_hpa,
            precip_mm, sunshine_seconds_per_900s, hrt_temp, dt,
        )
