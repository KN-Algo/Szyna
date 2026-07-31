import os
import time
import pandas as pd
import numpy as np
from scipy import signal
import matplotlib
import matplotlib.pyplot as plt
from matplotlib.widgets import Slider, Button
import matplotlib.gridspec as gridspec

# Wymuszenie interaktywnego okna dla GUI
matplotlib.use('TkAgg')  

# ==============================================================================
# JEDNA LINIKA DO ZMIANY ALGORYTMU
# ==============================================================================
from Algorytmy.Fuzzy_Logic_2 import RailHeatingController

# ==============================================================================
# CONFIG: AUTOMATYCZNE ŚCIEŻKI WZGLEDNE
# ==============================================================================
# Skrypt automatycznie wykrywa gdzie się znajduje i buduje ścieżki w dół struktury
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

NAZWA_PLIKU_CSV = os.path.join(BASE_DIR, "Pogoda_pomiary_15_minut", "suwalki_pogoda_15_min_model_2010.csv")
SCIEZKA_WYNIKOW = os.path.join(BASE_DIR, "wyniki", "wyniki_symualcji_1s.csv")

# Upewniamy się, że folder na wyniki istnieje
os.makedirs(os.path.dirname(SCIEZKA_WYNIKOW), exist_ok=True)

# ==============================================================================
# CONFIG: PARAMETRY ANALIZY (Z dawnego OLA.py)
# ==============================================================================
MOC_ZAMIANOWA_GRZALKI_KW = 14.0  # kW mocy na metr/rozjazd
WINDOW_SEC = 3600 * 2            # Szerokość okna podglądu (2 godziny)

# ==============================================================================
# 1. PARAMETRY MODELU OBIEKTU 
# ==============================================================================
K_W = 1.09075872; T1_W = 5771.977521; TZ_W = 780.0337376
K_H = 51.1163668; T1_H = 1120.914508; T2_H = 2450.968465; L_H = 1194.184089

tf_weather = signal.TransferFunction([K_W * TZ_W, K_W], [T1_W, 1])
tf_heating = signal.TransferFunction([K_H * 0.0, K_H], np.polymul([T1_H, 1], [T2_H, 1]).tolist())

# ==============================================================================
# SIMULATOR - POMOCNICZY FUNKCJONALNY BILANS ŚNIEGU/LODU
# ==============================================================================
class SnowIcePhysicalModel:
    def __init__(self):
        self.snow_layer_mm = 0.0
        self.ice_layer_mm = 0.0
        self.water_layer_mm = 0.0  # Warstwa wody
        
        # Fizyczne stałe
        self.snow_to_liquid_ratio = 10.0  # 1 mm wody = 10 mm puszystego śniegu
        self.melt_rate = 0.005            # Skorygowany współczynnik topnienia na sekundę per stopień
        self.freeze_rate = 0.008          # Szybkość zamarzania wody
        self.drain_evap_rate = 0.002      # Szybkość parowania/spływania

    def update(self, at_temp, hrt_temp, precip, dt=1.0):
        # precip przychodzi jako mm wody na sekundę
        current_snow_liquid = precip if at_temp <= 0.0 else 0.0
        current_rain_liquid = precip if at_temp > 0.0 else 0.0

        # 1. PRZYROST: Uwzględniamy, że śnieg zajmuje większą objętość niż woda
        if at_temp <= 0.0:
            self.snow_layer_mm += (current_snow_liquid * self.snow_to_liquid_ratio) * dt
            self.ice_layer_mm += current_rain_liquid * dt
        else:
            if current_rain_liquid > 0 and hrt_temp <= 0.0:
                self.ice_layer_mm += current_rain_liquid * dt
            elif current_rain_liquid > 0 and hrt_temp > 0.0:
                self.water_layer_mm += current_rain_liquid * dt

        # 2. TOPNIENIE: Następuje tylko, gdy szyna jest ciepła (hrt_temp > 0)
        if hrt_temp > 0.0:
            # Potencjał topnienia zależy od temperatury szyny
            melt_potential = hrt_temp * self.melt_rate * dt
            
            # Najpierw topimy śnieg
            if self.snow_layer_mm > 0:
                melted_snow = min(self.snow_layer_mm, melt_potential)
                self.snow_layer_mm -= melted_snow
                self.water_layer_mm += melted_snow / self.snow_to_liquid_ratio
                melt_potential -= melted_snow
            
            # Jeśli starczyło ciepła, topimy lód
            if self.ice_layer_mm > 0 and melt_potential > 0:
                # Lód topi się trudniej (jest gęstszy), powiedzmy 2x wolniej niż śnieg
                melted_ice = min(self.ice_layer_mm, melt_potential * 0.5)
                self.ice_layer_mm -= melted_ice
                self.water_layer_mm += melted_ice

        # ZAMARZANIE: Jeśli szyna już wystygła i jest woda
        if hrt_temp <= 0.0 and self.water_layer_mm > 0:
            freeze_potential = abs(hrt_temp) * self.freeze_rate * dt
            frozen_water = min(self.water_layer_mm, freeze_potential)
            self.water_layer_mm -= frozen_water
            self.ice_layer_mm += frozen_water

        #SCHNIĘCIE:
        if self.water_layer_mm > 0:
            temp_factor = max(1.0, hrt_temp)
            evaporation = self.drain_evap_rate * temp_factor * dt
            self.water_layer_mm = max(0.0, self.water_layer_mm - evaporation)

        return max(0.0, self.snow_layer_mm), max(0.0, self.ice_layer_mm), max(0.0, self.water_layer_mm)

# ==============================================================================
# 2. WCZYTYWANIE DANYCH POGODOWYCH I INTERPOLACJA DO 1 SEKUNDY
# ==============================================================================
print(f"📖 Wczytywanie danych pogodowych z pliku: {NAZWA_PLIKU_CSV} ...")
df_15min = pd.read_csv(NAZWA_PLIKU_CSV, sep=',')

if 'data_czas' in df_15min.columns:
    df_15min.rename(columns={'data_czas': 'Timestamp'}, inplace=True)

df_15min['Timestamp'] = pd.to_datetime(df_15min['Timestamp'])
df_15min.set_index('Timestamp', inplace=True)

print("⏳ Trwa gwałtowna interpolacja danych pogodowych z 15 minut do 1 sekundy...")
df_1s = df_15min.resample('1s').asfreq()

df_1s['temperatura_powietrza_C'] = df_1s['temperatura_powietrza_C'].interpolate(method='linear')
df_1s['punkt_rosy_C'] = df_1s['punkt_rosy_C'].interpolate(method='linear')
df_1s['wiatr_m_s'] = df_1s['wiatr_m_s'].interpolate(method='linear')
df_1s['naslonecznienie_sekundy'] = df_1s['naslonecznienie_sekundy'].interpolate(method='linear')
df_1s['opad_mm'] = df_1s['opad_mm'].ffill() / 900.0
df_1s.reset_index(inplace=True)
print(f"📊 Zagęszczono bazę. Liczba próbek 1-sekundowych: {len(df_1s)}\n")

# ==============================================================================
# 3. GŁÓWNA PĘTLA SEKUNDOWA - PEŁNY OKRES (Z OPTYMALIZACJĄ STANOWĄ)
# ==============================================================================
controller = RailHeatingController(max_switches_per_day=12)
ice_model = SnowIcePhysicalModel()

dt = 1.0

print("⚙️ Konwersja modeli transmitancyjnych do stabilnej przestrzeni stanów (State-Space)...")
sys_w_continuous = signal.tf2ss(tf_weather.num, tf_weather.den)
A_wd, B_wd, C_wd, D_wd, _ = signal.cont2discrete(sys_w_continuous, dt, method='zoh')

sys_h_continuous = signal.tf2ss(tf_heating.num, tf_heating.den)
A_hd, B_hd, C_hd, D_hd, _ = signal.cont2discrete(sys_h_continuous, dt, method='zoh')

print("🧮 Wyliczanie hurtowe wpływu środowiska (G_W) przy użyciu filtracji stanowej...")
at_array = df_1s['temperatura_powietrza_C'].to_numpy()
dew_array = df_1s['punkt_rosy_C'].to_numpy()

_, hrt_weather_all, _ = signal.dlsim((A_wd, B_wd, C_wd, D_wd, dt), at_array)
hrt_weather_all = hrt_weather_all.flatten()

x_h = np.zeros((A_hd.shape[0], 1))

current_hrt = 0.7  
current_crt = 0.9  

u_binary_history = []
historia_wynikow = []

print(f"🚀 Start pętli symulacji dla CAŁEGO OKRESU...")

timestamps = df_1s['Timestamp'].tolist()
precip_values = df_1s['opad_mm'].to_numpy()
punkty_opoznienia = int(round(L_H))

# Przygotowanie monitora postępu symulacji
total_steps = len(df_1s)
print_interval = max(1, total_steps // 20)  # Aktualizacja statusu co 5%
start_sim_time = time.time()

for index in range(total_steps):
    ts = timestamps[index]
    at_temp = at_array[index]
    dew_point = dew_array[index]
    precip_1s = precip_values[index]
    
    hrt_weather_comp = hrt_weather_all[index]
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

    sterowanie_procent = controller.compute_control(funkcja_wejscie)
    u_curr = sterowanie_procent / 100.0
    u_binary_history.append(u_curr)

    if index >= punkty_opoznienia:
        u_delayed = u_binary_history[index - punkty_opoznienia]
    else:
        u_delayed = 0.0

    x_h = A_hd @ x_h + B_hd * u_delayed
    hrt_heating_comp = (C_hd @ x_h + D_hd * u_delayed).item()

    current_hrt = hrt_weather_comp + hrt_heating_comp
    current_crt = hrt_weather_comp

    stan_sniegu_mm, stan_lodu_mm, stan_wody_mm = ice_model.update(at_temp, current_hrt, precip_1s, dt=1.0)
    
    historia_wynikow.append({
        'Timestamp': ts,
        'AT_temp_powietrza': at_temp,
        'HRT_temp_grzana': current_hrt,
        'CRT_temp_niegrzana': current_crt,
        'PRECIP_opad_1s': precip_1s,
        'SNOW_snieg_1s': snow_val,
        'Moc_procent': sterowanie_procent,
        'Snieg_na_szynie_mm': stan_sniegu_mm,
        'Lod_na_szynie_mm': stan_lodu_mm,
        'Woda_na_szynie_mm': stan_wody_mm
    })

    # --- NOWOŚĆ: LICZNIK PROCENTOWY ORAZ CZASU UKOŃCZENIA (ETA) ---
    if index % print_interval == 0 or index == total_steps - 1:
        procent_ukończenia = ((index + 1) / total_steps) * 100
        obecny_czas = time.time()
        minelo = obecny_czas - start_sim_time
        
        if procent_ukończenia > 0:
            szacowany_calkowity_czas = minelo / (procent_ukończenia / 100.0)
            eta_sekundy = szacowany_calkowity_czas - minelo
            print(f"▓▓ {procent_ukończenia:.0f}% ukończono symulację | Minęło: {minelo:.1f}s | Pozostały czas (ETA): {eta_sekundy:.1f}s")

# Zapis do CSV
df_wyniki = pd.DataFrame(historia_wynikow)
print(f"💾 Trwa zapisywanie danych do pamięci podręcznej pliku CSV...")
df_wyniki.to_csv(SCIEZKA_WYNIKOW, index=False)
print(f"✅ Sukces! Pełna historia zapisana w: {SCIEZKA_WYNIKOW}\n")

# ==============================================================================
# 4. GENEROWANIE RAPORTU STATYSTYCZNEGO (Z NOWYM PARAMETREM PRZEŁĄCZEŃ)
# ==============================================================================
df_wyniki['Grzanie_ON'] = df_wyniki['Moc_procent'] > 0.0
calkowity_czas_s = len(df_wyniki)
czas_grzania_s = df_wyniki['Grzanie_ON'].sum()
procent_czasu_grzania = (czas_grzania_s / calkowity_czas_s) * 100

df_wyniki['Energia_kWh_1s'] = (df_wyniki['Moc_procent'] / 100.0) * MOC_ZAMIANOWA_GRZALKI_KW * (1.0 / 3600.0)
calkowita_energia_kwh = df_wyniki['Energia_kWh_1s'].sum()

max_snieg = df_wyniki['Snieg_na_szynie_mm'].max()
max_lod = df_wyniki['Lod_na_szynie_mm'].max()
sekundy_ze_sniegiem = (df_wyniki['Snieg_na_szynie_mm'] > 0.0).sum()
sekundy_z_lodem = (df_wyniki['Lod_na_szynie_mm'] > 0.0).sum()

# --- NOWY PARAMETR: STATYSTYKA LICZBY PRZEŁĄCZEŃ ---
df_wyniki['Zmiana_Stanu'] = df_wyniki['Moc_procent'].diff().fillna(0) != 0
calkowita_liczba_przelaczen = df_wyniki['Zmiana_Stanu'].sum()
liczba_dni = max(1.0, calkowity_czas_s / 86400.0)
srednia_przelaczen_na_dobe = calkowita_liczba_przelaczen / liczba_dni

print("=" * 65)
print("📊       RAPORT STATYSTYCZNY Z PRACY TWOJEGO ALGORYTMU")
print("=" * 65)
print(f"⏱️  Całkowity czas analizy:       {calkowity_czas_s} sek. ({calkowity_czas_s/3600:.2f} godz.)")
print(f"🔥 Czas aktywnego grzania:       {czas_grzania_s} sek. ({czas_grzania_s/3600:.2f} godz.) -> {procent_czasu_grzania:.1f}%")
print(f"⚡ Przyjęta moc znamionowa:       {MOC_ZAMIANOWA_GRZALKI_KW} kW")
print(f"🔋 Szacunkowe zużycie energii:    {calkowita_energia_kwh:.3f} kWh")
print("-" * 65)
print(f"🔄 Całkowita liczba przełączeń:   {calkowita_liczba_przelaczen} razy")
print(f"📅 Średnia liczba przełączeń/dobę: {srednia_przelaczen_na_dobe:.2f} (Limit dobowy wynosił: 12)")
print("-" * 65)
print(f"❄️  Maksymalny śnieg na szynie:    {max_snieg:.2f} mm")
print(f"🧊 Maksymalny lód na szynie:     {max_lod:.2f} mm")
print(f"⏳ Czas zalegania śniegu:        {sekundy_ze_sniegiem} sek. ({sekundy_ze_sniegiem/3600:.2f} godz.)")
print(f"⏳ Czas zalegania lodu:          {sekundy_z_lodem} sek. ({sekundy_z_lodem/3600:.2f} godz.)")
print("=" * 65)

# ==============================================================================
# 5. INICJALIZACJA OKNA INTERAKTYWNEGO OLA (DARK MODE)
# ==============================================================================
print("\n📈 Uruchamianie zaawansowanego okna wykresu...")

df_wyniki['t_sec'] = np.arange(len(df_wyniki))
t_sec = df_wyniki['t_sec'].values
timestamps_gui = pd.to_datetime(df_wyniki['Timestamp']).values

colors = {
    'hrt':     '#e74c3c', 'crt':     '#95a5a6', 'at':      '#34495e',
    'moc':     '#f1c40f', 'opad':    '#3498db', 'snieg':   '#2ecc71',
    'lod':     '#9b59b6', 'bg_dark': '#0a0d14', 'bg_axes': '#0f1520',
    'grid':    '#1e2840', 'text':    '#7a8aaa',
    'woda':    '#00e5ff',
}

fig = plt.figure(figsize=(18, 11))
fig.patch.set_facecolor(colors['bg_dark'])

gs = gridspec.GridSpec(2, 1, figure=fig, left=0.06, right=0.93, top=0.94, bottom=0.18, hspace=0.12)
ax1 = fig.add_subplot(gs[0])
ax2 = fig.add_subplot(gs[1], sharex=ax1)

for ax in [ax1, ax2]:
    ax.set_facecolor(colors['bg_axes'])
    ax.tick_params(colors=colors['text'], labelsize=9)
    for sp in ax.spines.values():
        sp.set_edgecolor(colors['grid'])
    ax.grid(True, color=colors['grid'], alpha=0.7, lw=0.5)

fig.suptitle("Interaktywna analiza pracy układu grzewczego szyn", color='#c5cfe8', fontsize=14, fontweight='bold')

line_hrt, = ax1.plot([], [], color=colors['hrt'], linewidth=2, label='HRT (Szyna Ogrzewana)')
line_crt, = ax1.plot([], [], color=colors['crt'], linestyle='--', linewidth=1.5, label='CRT (Szyna Nieogrzewana)')
line_at,  = ax1.plot([], [], color=colors['at'], linestyle=':', linewidth=1.5, label='AT (Otoczenie)')
ax1.set_ylabel('Temperatura (°C)', color=colors['text'], fontweight='bold')

ax1_moc = ax1.twinx()
ax1_moc.tick_params(colors=colors['moc'], labelsize=9)
ax1_moc.set_ylabel('Wysterowanie mocy grzałki (%)', color=colors['moc'], fontweight='bold')
ax1_moc.set_ylim(-5, 105)
fill_moc = [None] 

line_opad, = ax2.plot([], [], color=colors['opad'], alpha=0.7, label='Intensywność opadów')
ax2.set_ylabel('Bieżący opad (mm/15min)', color=colors['opad'], fontweight='bold')

ax2_stan = ax2.twinx()
ax2_stan.tick_params(colors=colors['snieg'], labelsize=9)
line_snieg, = ax2_stan.plot([], [], color=colors['snieg'], linewidth=2, label='Śnieg na szynie (mm)')
line_lod,   = ax2_stan.plot([], [], color=colors['lod'], linewidth=2, linestyle='-.', label='Lód na szynie (mm)')
line_woda,  = ax2_stan.plot([], [], color=colors['woda'], linewidth=2, linestyle=':', label='Woda na szynie (mm)')
ax2_stan.set_ylabel('Grubość warstwy (mm)', color=colors['snieg'], fontweight='bold')

ax1.legend(loc='upper left', fontsize=9, facecolor='#151c2e', labelcolor='white', framealpha=0.8)
ax2.legend(loc='upper right', fontsize=9, facecolor='#151c2e', labelcolor='white', framealpha=0.8)

t_max = t_sec[-1]
slider_max = max(t_max - WINDOW_SEC, 1.0)

ax_slide = fig.add_axes([0.06, 0.08, 0.75, 0.035])
ax_btn_l = fig.add_axes([0.83, 0.08, 0.04, 0.035])
ax_btn_r = fig.add_axes([0.88, 0.08, 0.04, 0.035])

for ax in [ax_slide, ax_btn_l, ax_btn_r]:
    ax.set_facecolor(colors['bg_dark'])

slider = Slider(ax_slide, 'Czas →', 0, slider_max, valinit=0, valstep=max(1.0, WINDOW_SEC / 100), color='#00e5ff', track_color=colors['grid'])
slider.label.set_color(colors['text'])
slider.valtext.set_color('#00e5ff')

def format_axes():
    x0 = int(slider.val)
    x1 = int(x0 + WINDOW_SEC)
    
    mask = (t_sec >= x0) & (t_sec <= x1)
    df_sub = df_wyniki.iloc[mask]
    
    if len(df_sub) == 0:
        return

    step = max(1, len(df_sub) // 600)  
    df_resampled = df_sub.iloc[::step]
    
    sub_t = df_resampled['t_sec'].values

    line_hrt.set_data(sub_t, df_resampled['HRT_temp_grzana'])
    line_crt.set_data(sub_t, df_resampled['CRT_temp_niegrzana'])
    line_at.set_data(sub_t, df_resampled['AT_temp_powietrza'])
    
    if fill_moc[0] is not None:
        fill_moc[0].remove()
    fill_moc[0] = ax1_moc.fill_between(sub_t, df_resampled['Moc_procent'], color=colors['moc'], alpha=0.15)

    line_opad.set_data(sub_t, df_resampled['PRECIP_opad_1s'] * 900)
    line_snieg.set_data(sub_t, df_resampled['Snieg_na_szynie_mm'])
    line_lod.set_data(sub_t, df_resampled['Lod_na_szynie_mm'])
    line_woda.set_data(sub_t, df_resampled['Woda_na_szynie_mm'])

    ax1.set_xlim(x0, x1)
    try:
        y1_min = min(df_resampled['HRT_temp_grzana'].min(), df_resampled['AT_temp_powietrza'].min()) - 2
        y1_max = max(df_resampled['HRT_temp_grzana'].max(), df_resampled['CRT_temp_niegrzana'].max()) + 2
        ax1.set_ylim(y1_min, y1_max)
        
        y2_max = max(df_resampled['Snieg_na_szynie_mm'].max(), df_resampled['Lod_na_szynie_mm'].max(), df_resampled['Woda_na_szynie_mm'].max())
        ax2_stan.set_ylim(-0.2, max(y2_max + 0.5, 2.0))
        
        y2_opad_max = (df_resampled['PRECIP_opad_1s'] * 900).max()
        ax2.set_ylim(-0.1, max(y2_opad_max + 0.5, 1.0))
    except ValueError:
        pass 

    ticks = np.linspace(x0, x1, 6)
    ax2.set_xticks(ticks)
    
    i_arr = np.searchsorted(t_sec, ticks)
    i_arr = np.clip(i_arr, 0, len(timestamps_gui) - 1)
    labels = [pd.Timestamp(timestamps_gui[i]).strftime('%d.%m\n%H:%M:%S') for i in i_arr]
    ax2.set_xticklabels(labels, fontsize=8, color=colors['text'])

    fig.canvas.draw_idle()

slider.on_changed(lambda v: format_axes())

STEP = WINDOW_SEC // 4
btn_l = Button(ax_btn_l, '◀', color='#1a2235', hovercolor='#253050')
btn_r = Button(ax_btn_r, '▶', color='#1a2235', hovercolor='#253050')

for b in [btn_l, btn_r]:
    b.label.set_color('#c5cfe8')

btn_l.on_clicked(lambda e: slider.set_val(max(0, slider.val - STEP)))
btn_r.on_clicked(lambda e: slider.set_val(min(slider_max, slider.val + STEP)))

def on_scroll(event):
    if event.inaxes in [ax1, ax2, ax1_moc, ax2_stan]:
        delta = -(WINDOW_SEC // 6) if event.button == 'up' else (WINDOW_SEC // 6)
        slider.set_val(np.clip(slider.val + delta, 0, slider_max))

fig.canvas.mpl_connect('scroll_event', on_scroll)
format_axes()

print("💡 WSKAZÓWKA: Symulacja ukończona. Przewijaj rolką myszy nad wykresem, aby przeglądać dane z bieguna zimna!")
plt.show()