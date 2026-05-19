import pandas as pd
import numpy as np
from scipy import signal

# ==============================================================================
# 1. PARAMETRY MODELU OBIEKTU (Z TWOJEGO KODU)
# ==============================================================================
K_W = 1.09075872; T1_W = 5771.977521; TZ_W = 780.0337376
K_H = 51.1163668; T1_H = 1120.914508; T2_H = 2450.968465; L_H = 1194.184089

tf_weather = signal.TransferFunction([K_W * TZ_W, K_W], [T1_W, 1])
tf_heating = signal.TransferFunction([K_H * 0.0, K_H], np.polymul([T1_H, 1], [T2_H, 1]).tolist())

# ==============================================================================
# 2. KLASA STEROWNIKA (OCZEKUJE PEŁNEGO WEKTORA ZGODNIE Z ŻĄDANIEM)
# ==============================================================================
class RailHeatingController:
    def __init__(self, target_temp=4.0, hysteresis=1.0):
        self.target_temp = target_temp
        self.hysteresis = hysteresis
        self.heating_on = False

    def compute_control(self, row_data):
        timestamp = row_data['Timestamp']
        crt = row_data['CRT_temp_niegrzana']
        hrt = row_data['HRT_temp_grzana']
        at = row_data['AT_temp_powietrza']
        rh = row_data['RH_wilgotnosc']
        press = row_data['PRESS_cisnienie']
        precip = row_data['PRECIP_opad']
        snow = row_data['SNOW_snieg']
        pwrl1 = row_data['PWRL1_moc']
        pwrl2 = row_data['PWRL2_moc']

        # Logika regulacji dwustanowej z histerezą
        if self.heating_on:
            if hrt >= (self.target_temp + self.hysteresis):
                self.heating_on = False
        else:
            if hrt <= (self.target_temp - self.hysteresis) or (at < 2.0 and (precip > 0 or snow > 0)):
                self.heating_on = True

        return 100.0 if self.heating_on else 0.0


# ==============================================================================
# SIMULATOR - POMOCNICZY FUNKCJONALNY BILANS ŚNIEGU/LODU
# ==============================================================================
class SnowIcePhysicalModel:
    def __init__(self):
        self.snow_layer_mm = 0.0
        self.ice_layer_mm = 0.0
        self.melt_rate = 0.0001  # dopasowane do kroku 1-sekundowego

    def update(self, at_temp, hrt_temp, precip, dt=1.0):
        current_snow = precip if at_temp <= 0.0 else 0.0
        current_rain = precip if at_temp > 0.0 else 0.0

        if at_temp <= 0.0:
            self.snow_layer_mm += current_snow * dt
            self.ice_layer_mm += current_rain * dt
        else:
            if current_rain > 0 and hrt_temp <= 0.0:
                self.ice_layer_mm += current_rain * dt

        # Wytapianie przez grzałkę (HRT)
        if hrt_temp > 0.0:
            melt_potential = hrt_temp * self.melt_rate * dt
            if self.snow_layer_mm > 0:
                melted = min(self.snow_layer_mm, melt_potential)
                self.snow_layer_mm -= melted
                melt_potential -= melted
            if self.ice_layer_mm > 0 and melt_potential > 0:
                self.ice_layer_mm -= min(self.ice_layer_mm, melt_potential)

        return max(0.0, self.snow_layer_mm), max(0.0, self.ice_layer_mm)


def simulate_step_dlsim(tf_c, u_history, dt=1.0):
    if len(u_history) == 0: 
        return 0.0
    # Konwersja transmitancji ciągłej na dyskretną metodą Tustina (Bilinear)
    tf_d = tf_c.to_discrete(dt, method='bilinear')
    # Symulacja dyskretna - odporna na błędy kroków czasowych
    _, y = signal.dlsim(tf_d, u_history)
    return float(y[-1][0])


# ==============================================================================
# 3. WCZYTYWANIE TWOJEGO PLIKU CSV I INTERPOLACJA DO 1 SEKUNDY
# ==============================================================================
NAZWA_PLIKU_CSV = "D:\\Pulpit\\KN ALGO\\Szyna\\benchmark\\wroclaw_pogoda_15min_model.csv" 

print(f"📖 Wczytywanie danych pogodowych z pliku: {NAZWA_PLIKU_CSV} ...")
df_15min = pd.read_csv(NAZWA_PLIKU_CSV, sep=',')

if 'data_czas' in df_15min.columns:
    df_15min.rename(columns={'data_czas': 'Timestamp'}, inplace=True)

df_15min['Timestamp'] = pd.to_datetime(df_15min['Timestamp'])
df_15min.set_index('Timestamp', inplace=True)

# # Ograniczenie do 1 dnia testowego (zapobiega zawieszeniu pamięci przy krokach 1s)
# pierwszy_dzien = df_15min.index[0].strftime('%Y-%m-%d')
# print(f"✂️ Ograniczam symulację do pierwszego dnia ({pierwszy_dzien}) dla celów testowych...")
# df_15min = df_15min.loc[pierwszy_dzien]

print("⏳ Trwa gwałtowna interpolacja danych pogodowych z 15 minut do 1 sekundy...")
df_1s = df_15min.resample('1s').asfreq()

# Interpolacja liniowa 1-sekundowa
df_1s['temperatura_powietrza_C'] = df_1s['temperatura_powietrza_C'].interpolate(method='linear')
df_1s['punkt_rosy_C'] = df_1s['punkt_rosy_C'].interpolate(method='linear')
df_1s['wiatr_m_s'] = df_1s['wiatr_m_s'].interpolate(method='linear')
df_1s['naslonecznienie_sekundy'] = df_1s['naslonecznienie_sekundy'].interpolate(method='linear')

# Opady rozdzielone równomiernie: wartość z 15 minut (900 sekund) dzielona na sekundy
df_1s['opad_mm'] = df_1s['opad_mm'].ffill() / 900.0
df_1s.reset_index(inplace=True)
print(f"📊 Zagęszczono bazę. Liczba próbek 1-sekundowych: {len(df_1s)}\n")


# ==============================================================================
# 4. GŁÓWNA PĘTLA SEKUNDOWA - PEŁNY OKRES (WERSJA ULTRA SZYBKA)
# ==============================================================================
controller = RailHeatingController(target_temp=4.0)
ice_model = SnowIcePhysicalModel()

# --- 1. DYSKRETYZACJA TRANSMITANCJI TYLKO RAZ ---
dt = 1.0
tf_weather_d = tf_weather.to_discrete(dt, method='bilinear')
tf_heating_d = tf_heating.to_discrete(dt, method='bilinear')

# --- 2. OBLICZENIE CAŁEJ POGODY NA RAZ ---
print("🧮 Wyliczanie hurtowe wpływu środowiska (G_W) dla całego okresu...")
at_array = df_1s['temperatura_powietrza_C'].to_numpy()
dew_array = df_1s['punkt_rosy_C'].to_numpy() # Pobieramy realną tablicę punktu rosy

_, hrt_weather_all = signal.dlsim(tf_weather_d, at_array)
hrt_weather_all = hrt_weather_all.flatten()

# --- Instrukcje pamięciowe dla układu grzania ---
num_h, den_h = tf_heating_d.num, tf_heating_d.den
u_hist = [0.0, 0.0]
y_hist = [0.0, 0.0]

current_hrt = 0.7  
current_crt = 0.9  

u_binary_history = []
historia_wynikow = []

print(f"🚀 Start szybkiej pętli dla CAŁEGO OKRESU. Liczba sekund do przeliczenia: {len(df_1s)}...")

timestamps = df_1s['Timestamp'].tolist()
precip_values = df_1s['opad_mm'].to_numpy()
punkty_opoznienia = int(round(L_H))

for index in range(len(df_1s)):
    ts = timestamps[index]
    at_temp = at_array[index]
    dew_point = dew_array[index] # Korzystamy z realnego punktu rosy z pliku CSV
    precip_1s = precip_values[index]
    
    # Składnik pogodowy z przygotowanej tablicy
    hrt_weather_comp = hrt_weather_all[index]
    
    # Obliczenie wilgotności względnej RH na bazie prawdziwych danych
    calculated_rh = max(0.0, min(100.0, 100.0 - 5.0 * (at_temp - dew_point)))
    
    snow_val = precip_1s if at_temp <= 0.0 else 0.0
    rain_val = precip_1s if at_temp > 0.0 else 0.0

    funkcja_wejscie = {
        'Timestamp': ts,
        'CRT_temp_niegrzana': hrt_weather_comp, 
        'HRT_temp_grzana': current_hrt,       
        'AT_temp_powietrza': at_temp,
        'RH_wilgotnosc': round(calculated_rh, 1),
        'PRESS_cisnienie': 1009.0,             
        'PRECIP_opad': rain_val,
        'SNOW_snieg': snow_val,
        'PWRL1_moc': 0.0,                      
        'PWRL2_moc': 0.0
    }

    # Decyzja sterownika
    sterowanie_procent = controller.compute_control(funkcja_wejscie)
    u_curr = sterowanie_procent / 100.0
    u_binary_history.append(u_curr)

    # Równanie różnicowe dla grzałki z opóźnieniem transportowym L_H
    if index >= punkty_opoznienia:
        u_delayed = u_binary_history[index - punkty_opoznienia]
    else:
        u_delayed = 0.0

    if index == 0:
        hrt_heating_comp = 0.0
    else:
        hrt_heating_comp = (num_h[0]*u_delayed + num_h[1]*u_hist[0] + num_h[2]*u_hist[1] 
                            - den_h[1]*y_hist[0] - den_h[2]*y_hist[1]) / den_h[0]

    # Przesunięcie rejestrów pamięci
    u_hist = [u_delayed, u_hist[0]]
    y_hist = [hrt_heating_comp, y_hist[0]]

    # Ostateczny stan szyn
    current_hrt = hrt_weather_comp + hrt_heating_comp
    current_crt = hrt_weather_comp

    # Fizyka lodu i śniegu
    stan_sniegu_mm, stan_lodu_mm = ice_model.update(at_temp, current_hrt, precip_1s, dt=1.0)
    
    # Zapis do historii
    historia_wynikow.append({
        'Timestamp': ts,
        'AT_temp_powietrza': at_temp,
        'HRT_temp_grzana': current_hrt,
        'CRT_temp_niegrzana': current_crt,
        'PRECIP_opad_1s': precip_1s,
        'SNOW_snieg_1s': snow_val,
        'Moc_procent': sterowanie_procent,
        'Snieg_na_szynie_mm': stan_sniegu_mm,
        'Lod_na_szynie_mm': stan_lodu_mm
    })

# --- PO ZAKOŃCZENIU CAŁEJ PĘTLI FOR ---
df_wyniki = pd.DataFrame(historia_wynikow)
df_wyniki.to_csv("D:\\Pulpit\\KN ALGO\\Szyna\\benchmark\\wyniki_symualcji_1s.csv", index=False)
print(f"\n💾 Zapisano pełną historię ({len(df_wyniki)} sek.) do pliku CSV!")