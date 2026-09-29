# ==============================================================================
# Benchmark_crt/benchmark/wejscie_slonca.py
#
# WEJŚCIE NASŁONECZNIENIA do modelu obiektu (2026-09-28, na życzenie użytkownika:
# "dodaj słońce do całości obiektu"). Wspólne dla symulatora (symulacja_fizyczna.py)
# i skryptów identyfikacji (Identyfikacja/Identyfikacja/dopasowanie_nasloneczenia.py),
# żeby oba liczyły wejście DOKŁADNIE tak samo.
#
#   wejście_słońca(t) = ułamek_słońca(t) * sin(wysokość_słońca(t))          [0..1]
#
#   ułamek_słońca: naslonecznienie_sekundy / długość_kroku_źródła (0 = brak słońca -
#     noc albo pełne zachmurzenie, 1 = pełne słońce przez cały krok: 900 s dla danych
#     15-minutowych, 3600 s dla godzinowych). Open-Meteo podaje sumę sekund słońca za
#     POPRZEDNIĄ godzinę (znacznik = koniec przedziału), więc wartość jest średnim
#     ułamkiem z przedziału [T-krok, T] i jest ustawiana w ŚRODKU tego przedziału;
#     między takimi punktami interpolowana liniowo do siatki symulacji (dane gęstsze
#     niż godzinowe nie są dostępne dla wszystkich lokalizacji, patrz notatki).
#   sin(wysokość słońca): geometria słońca (NOAA, uproszczona) ze współrzędnych
#     lokalizacji i czasu UTC - kształt dobowy natężenia, którego same sekundy słońca
#     nie niosą (0/900 wygląda jak prostokąt, a rano/wieczorem słońce jest słabe).
#     Zmierzone na danych z Wrocławia: bez tego czynnika RMSE CRT 1,9 °C, z nim 1,2 °C.
# ==============================================================================

import os
import re

import numpy as np
import pandas as pd

# Współrzędne lokalizacji = te same co w Generowanie_pogody/zaciaganie_pogody.py (STACJE),
# plus Wrocław (plik 15-minutowy z historical-forecast-api, czas lokalny Europe/Warsaw).
# Pozostałe pliki (Open-Meteo /v1/archive, ERA5-Land) mają znaczniki czasu w UTC.
_STACJE = {
    'abisko': (68.3556, 18.7877), 'fairbanks': (64.8378, -147.7164), 'jakuck': (62.0355, 129.6755),
    'krakow': (50.0647, 19.9450), 'ojmiakon': (63.4608, 142.7858), 'old_crow': (67.5667, -139.8333),
    'oslo': (59.9139, 10.7522), 'puszcza_bialowieska': (52.7000, 23.8500), 'suwalki': (54.1004, 22.9296),
    'ushuaia': (-54.8019, -68.3030), 'san_carlos_de_bariloche': (-41.1335, -71.3103),
    'punta_arenas': (-53.1638, -70.9171), 'coyhaique': (-45.5752, -72.0662), 'harbin': (45.8038, 126.5349),
    'mohe': (53.4715, 122.3378), 'urumczi': (43.8256, 87.6168), 'lhasa': (29.6500, 91.1000),
    'norylsk': (69.3535, 88.2027), 'wladywostok': (43.1332, 131.9113), 'murmansk': (68.9585, 33.0827),
    'rovaniemi': (66.5039, 25.7294), 'sodankyla': (67.4166, 26.5901), 'kiruna': (67.8558, 20.2253),
    'ostersund': (63.1792, 14.6357), 'tromso': (69.6492, 18.9553), 'roros': (62.5750, 11.3844),
    'reykjavik': (64.1466, -21.9426), 'akureyri': (65.6885, -18.1262), 'banff': (51.1784, -115.5708),
    'yellowknife': (62.4540, -114.3718), 'quebec_city': (46.8139, -71.2080), 'anchorage': (61.2181, -149.9003),
    'duluth': (46.7867, -92.1005), 'garmisch_partenkirchen': (47.4917, 11.0956), 'oberstdorf': (47.4021, 10.2793),
    'aviemore': (57.1930, -3.8270), 'braemar': (57.0064, -3.3970), 'sapporo': (43.0618, 141.3545),
    'nagano': (36.6513, 138.1810), 'manali': (32.2432, 77.1892), 'gulmarg': (34.0484, 74.3805),
    'sutherland': (-32.3833, 20.6667), 'mount_hotham': (-36.9833, 147.1333),
}
LOKALIZACJE = {k: (lat, lon, 'UTC') for k, (lat, lon) in _STACJE.items()}
LOKALIZACJE['wroclaw'] = (51.121933, 17.005006, 'Europe/Warsaw')   # Wrocław Popowice (szyna z identyfikacji)


def _ns(znaczniki):
    """Znaczniki czasu -> nanosekundy od epoki (float). Jawnie [ns]: pandas 2/3 potrafi trzymać [us] albo [s],
    a wtedy .asi8 dałby inną jednostkę dla źródła i dla siatki (błąd wykryty 2026-09-28)."""
    return np.asarray(pd.DatetimeIndex(znaczniki).to_numpy().astype('datetime64[ns]').astype('int64'), dtype=float)


def klucz_lokalizacji(sciezka_csv):
    """'.../krakow_60min_2025.csv' -> 'krakow' (None, gdy plik nie ma takiego wzorca)."""
    nazwa = os.path.splitext(os.path.basename(sciezka_csv))[0].lower()
    return re.sub(r'_\d+min_\d{4}$', '', nazwa)


def wspolrzedne(sciezka_csv):
    """(lat, lon, strefa) dla pliku pogodowego albo None, gdy lokalizacji nie znamy."""
    return LOKALIZACJE.get(klucz_lokalizacji(sciezka_csv))


def na_utc(znaczniki, strefa):
    """Naiwne znaczniki czasu -> naiwne UTC. 'UTC' bez zmian; Europe/Warsaw: CEST (+2 h) od kwietnia
    do października, CET (+1 h) poza tym (przybliżenie - błąd co najwyżej w dwóch dniach przejścia)."""
    idx = pd.DatetimeIndex(znaczniki)
    if strefa == 'UTC':
        return idx
    przesuniecie = np.where((idx.month >= 4) & (idx.month <= 10), 2, 1)
    return idx - pd.to_timedelta(przesuniecie, unit='h')


def sinus_wysokosci_slonca(ts_utc, lat, lon):
    """Sinus wysokości słońca nad horyzontem (NOAA, uproszczone); ts_utc = naiwne UTC. Może być < 0 (noc)."""
    idx = pd.DatetimeIndex(ts_utc)
    godz = np.asarray(idx.hour + idx.minute / 60.0 + idx.second / 3600.0, dtype=float)
    gamma = 2 * np.pi / 365.0 * (np.asarray(idx.dayofyear, dtype=float) - 1 + (godz - 12) / 24.0)
    eqtime = 229.18 * (0.000075 + 0.001868 * np.cos(gamma) - 0.032077 * np.sin(gamma)
                       - 0.014615 * np.cos(2 * gamma) - 0.040849 * np.sin(2 * gamma))
    decl = (0.006918 - 0.399912 * np.cos(gamma) + 0.070257 * np.sin(gamma) - 0.006758 * np.cos(2 * gamma)
            + 0.000907 * np.sin(2 * gamma) - 0.002697 * np.cos(3 * gamma) + 0.00148 * np.sin(3 * gamma))
    tst = godz * 60.0 + eqtime + 4.0 * lon                      # czas słoneczny prawdziwy [min], UTC
    ha = np.deg2rad(tst / 4.0 - 180.0)
    lat_r = np.deg2rad(lat)
    return np.sin(lat_r) * np.sin(decl) + np.cos(lat_r) * np.cos(decl) * np.cos(ha)


def frakcja_slonca_na_siatce(t_zrodlo_utc, sekundy, krok_zrodla_s, t_siatki_utc):
    """Średni ułamek słońca (0..1) dla wartości źródłowych 'suma sekund za poprzedni krok' (znacznik =
    koniec przedziału): punkt w środku przedziału, interpolacja liniowa na siatkę t_siatki_utc."""
    t_zr = _ns(t_zrodlo_utc) - 0.5 * krok_zrodla_s * 1e9
    f = np.clip(np.nan_to_num(np.asarray(sekundy, float)) / krok_zrodla_s, 0.0, 1.0)
    return np.interp(_ns(t_siatki_utc), t_zr, f)


def wejscie_slonca(t_zrodlo_utc, sekundy, krok_zrodla_s, t_siatki_utc, lat, lon):
    """(ułamek, sin_wysokości_dodatni, wejście=ułamek*sin_wysokości_dodatni) na siatce t_siatki_utc."""
    frakcja = frakcja_slonca_na_siatce(t_zrodlo_utc, sekundy, krok_zrodla_s, t_siatki_utc)
    sin_el = np.clip(sinus_wysokosci_slonca(t_siatki_utc, lat, lon), 0.0, None)
    return frakcja, sin_el, frakcja * sin_el
