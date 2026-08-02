import os  # Obsługa ścieżek plików i sprawdzanie istnienia CSV.
import matplotlib.pyplot as plt  # Biblioteka do rysowania wykresów końcowych.
import numpy as np  # Obliczenia numeryczne, macierze i maski logiczne.
import pandas as pd  # Wczytywanie, czyszczenie i resampling danych.


# Ta klasa enkapsuluje cały model prognozy temperatury oparty o filtr Kalmana.
class KalmanTemperatureForecaster:
    # Konstruktor ustawia parametry modelu, czyli jak bardzo ufamy dynamice i pomiarom.
    def __init__(self, process_variance=0.05, measurement_variance=0.25):
        self.process_variance = process_variance  # Szum procesu: jak bardzo temperatura może sama „dryfować”.
        self.measurement_variance = measurement_variance  # Szum pomiaru: jak bardzo odczyt może być niedokładny.

    # Funkcja pomocnicza zamienia wejście na czystą serię liczbową.
    @staticmethod
    def _normalize_series(values):
        series = pd.Series(values)  # Konwertujemy dowolny input na serię pandas.
        series = series.dropna()  # Usuwamy braki danych, bo Kalman nie lubi pustych punktów.
        series = series.astype(float)  # Wymuszamy typ liczbowy, żeby działały obliczenia.
        return series  # Zwracamy oczyszczoną serię, gotową do filtrowania.

    # Ta metoda uczy filtr na historii i produkuje prognozę do przodu.
    def _kalman_forecast_series(self, values, steps):
        series = self._normalize_series(values)  # Czyścimy dane wejściowe.
        if series.empty:  # Jeżeli nie ma danych, nie da się przewidywać.
            return []  # Zwracamy pustą listę prognoz.

        # Ustawiamy startowy poziom i trend z ostatnich punktów historii.
        if len(series) == 1:  # Gdy mamy tylko jeden punkt, trend ustawiamy na zero.
            level = float(series.iloc[0])  # Poziom startowy bierzemy z jedynej dostępnej wartości.
            trend = 0.0  # Bez drugiego punktu nie znamy nachylenia.
        else:  # Gdy mamy co najmniej dwa punkty, wyznaczamy prosty trend z różnicy.
            level = float(series.iloc[-1])  # Poziom startowy to ostatnia znana temperatura.
            trend = float(series.iloc[-1] - series.iloc[-2])  # Trend to różnica między dwoma ostatnimi punktami.

        # Budujemy wektor stanu: poziom + trend.
        state = np.array([[level], [trend]], dtype=float)  # Stan bieżący filtra.
        covariance = np.array([[1.0, 0.0], [0.0, 1.0]], dtype=float)  # Macierz niepewności początkowej.
        transition = np.array([[1.0, 1.0], [0.0, 1.0]], dtype=float)  # Model przejścia: poziom + trend.
        observation = np.array([[1.0, 0.0]], dtype=float)  # Obserwujemy tylko poziom temperatury.
        process_noise = np.array([[self.process_variance, 0.0], [0.0, self.process_variance]], dtype=float)  # Szum procesu.
        observation_noise = float(self.measurement_variance)  # Szum pojedynczego pomiaru.
        identity = np.eye(2)  # Macierz jednostkowa potrzebna w aktualizacji Kalmana.

        # Przepuszczamy przez filtr całą historię, żeby ustalić aktualny stan modelu.
        for measurement in series:  # Iterujemy po kolejnych pomiarach temperatury.
            predicted_state = transition @ state  # Predykcja stanu przed zobaczeniem nowego pomiaru.
            predicted_covariance = transition @ covariance @ transition.T + process_noise  # Predykcja niepewności.
            innovation = float(measurement - (observation @ predicted_state)[0, 0])  # Różnica między obserwacją a prognozą.
            innovation_covariance = float((observation @ predicted_covariance @ observation.T)[0, 0] + observation_noise)  # Łączna niepewność innowacji.
            kalman_gain = predicted_covariance @ observation.T / innovation_covariance  # Wzmocnienie Kalmana.
            state = predicted_state + kalman_gain * innovation  # Korekta stanu o nowy pomiar.
            covariance = (identity - kalman_gain @ observation) @ predicted_covariance  # Korekta niepewności po pomiarze.

        # Mając ustalony stan, generujemy punkty prognozy do przodu.
        forecasts = []  # Lista kolejnych przewidywanych temperatur.
        for _ in range(int(steps)):  # Powtarzamy tyle razy, ile punktów chcemy wyliczyć.
            state = transition @ state  # Przesuwamy stan o jeden krok do przodu.
            forecasts.append(float(state[0, 0]))  # Zapisujemy tylko przewidywany poziom temperatury.
            covariance = transition @ covariance @ transition.T + process_noise  # Aktualizujemy niepewność prognozy.

        return forecasts  # Oddajemy listę wartości temperatury w przyszłości, krok po kroku.

    # Ta metoda bierze dowolny wycinek danych i zwraca prognozę z osią czasu.
    def forecast_from_frame(self, weather_df, temp_col='temperatura_powietrza_C', steps=None, history_points=None, step_minutes=10):
        if weather_df is None or len(weather_df) == 0:  # Gdy nie ma danych, zwracamy pusty wynik.
            return {'timestamps': [], temp_col: []}  # Pusty wynik, gdy wejście nie istnieje.

        df = weather_df.copy()  # Pracujemy na kopii, żeby nie zmieniać wejścia.
        if 'Timestamp' in df.columns:  # Jeśli czas jest zwykłą kolumną, przenosimy go do indeksu.
            df['Timestamp'] = pd.to_datetime(df['Timestamp'])  # Konwertujemy tekst na typ czasu.
            df = df.set_index('Timestamp')  # Ustawiamy czas jako indeks, żeby łatwo robić forecast po czasie.
        elif not isinstance(df.index, pd.DatetimeIndex):  # Jeśli nie ma ani kolumny, ani indeksu czasu, przerywamy.
            raise ValueError('weather_df musi zawierać kolumnę Timestamp albo indeks datetime')  # Bez czasu nie da się przewidywać kolejnych punktów.

        if temp_col not in df.columns:  # Sprawdzamy, czy kolumna temperatury naprawdę istnieje.
            raise ValueError(f'Brak kolumny {temp_col} w danych')  # Temperatura jest jedynym wejściem do modelu.

        if history_points is None:  # Jeśli nie podano długości historii, ustawiamy sensowny domyślny limit.
            history_points = max(2, min(96, len(df)))  # Domyślnie bierzemy rozsądną porcję historii.
        history_points = max(2, min(history_points, len(df)))  # Historia musi być przynajmniej dwupunktowa i nie dłuższa niż dane.
        history = df[[temp_col]].tail(history_points)  # Wycinamy ostatni fragment danych jako pamięć modelu.

        if steps is None:  # Jeśli nie podano liczby kroków, ustawiamy ją na długość dostarczonego wycinka.
            steps = len(df)  # Gdy nie podano horyzontu, przyjmujemy tyle kroków, ile ma wycinek.

        last_timestamp = history.index[-1]  # Bierzemy ostatni znany moment czasu.
        step_delta = pd.Timedelta(minutes=int(step_minutes))  # Definiujemy, ile czasu mija między punktami prognozy.
        forecast_timestamps = [last_timestamp + step_delta * step for step in range(1, steps + 1)]  # Budujemy listę przyszłych timestampów.

        return {  # Zwracamy słownik z czasem i wartościami temperatury.
            'timestamps': forecast_timestamps,
            temp_col: self._kalman_forecast_series(history[temp_col], steps),
        }


# Funkcja ładuje CSV i zostawia tylko kolumny potrzebne do prognozy.
def load_temperature_data(file_path):
    if not os.path.exists(file_path):  # Najpierw sprawdzamy, czy plik w ogóle jest na dysku.
        raise FileNotFoundError(f'Plik nie istnieje: {file_path}')  # Twardy błąd, bo bez CSV nie ma co liczyć.

    df = pd.read_csv(file_path)  # Wczytujemy dane z pliku CSV do ramki danych.
    if 'data_czas' in df.columns:  # Jeśli w CSV czas nazywa się inaczej, normalizujemy nazwę.
        df = df.rename(columns={'data_czas': 'Timestamp'})  # Normalizujemy nazwę pola czasu.

    required_columns = {'Timestamp', 'temperatura_powietrza_C'}  # Bez tych kolumn nie zbudujemy prognozy.
    missing_columns = required_columns - set(df.columns)  # Liczymy brakujące nazwy kolumn.
    if missing_columns:  # Jeśli brakuje kolumn, kończymy z czytelnym błędem.
        missing_text = ', '.join(sorted(missing_columns))  # Łączymy brakujące kolumny w czytelny tekst.
        raise ValueError(f'Brakuje kolumn: {missing_text}')  # Zgłaszamy problem użytkownikowi.

    df['Timestamp'] = pd.to_datetime(df['Timestamp'])  # Zamieniamy tekst czasu na format datetime.
    df = df[['Timestamp', 'temperatura_powietrza_C']].copy()  # Zostawiamy tylko pola potrzebne do prognozy.
    df = df.sort_values('Timestamp').drop_duplicates(subset='Timestamp')  # Sortujemy czas i usuwamy duplikaty pomiarów.
    df = df.set_index('Timestamp')  # Czas trafia do indeksu, aby wygodnie resamplować.
    return df  # Zwracamy gotowe dane.


# Główna funkcja uruchamiająca eksperyment i rysująca wynik.
def run_kalman_forecast(file_path):
    df = load_temperature_data(file_path)  # Ładujemy i oczyszczamy dane wejściowe.

    df_10min = df[['temperatura_powietrza_C']].resample('10min').mean().interpolate(method='time')  # Budujemy siatkę 10-minutową i uzupełniamy ją czasowo.

    if len(df_10min) < 2:  # Bez minimum dwóch punktów nie da się ustawić trendu.
        raise ValueError('Za mało danych, żeby uruchomić filtr Kalmana')  # Bez historii model jest zbyt słaby.

    first_timestamp = df_10min.index.min()  # Najwcześniejszy znacznik czasu w zbiorze.
    first_hour_end = first_timestamp + pd.Timedelta(hours=1)  # Początkowy warm-up: pierwsza godzina historii.

    train_df = df_10min[df_10min.index < first_hour_end].copy()  # Pierwsza godzina służy jako historia startowa filtra.
    future_df = df_10min[df_10min.index >= first_hour_end].copy()  # Wszystko po tej granicy służy do testu i wizualizacji.

    if len(train_df) < 2:  # Bez minimum dwóch punktów nie da się ustawić trendu.
        raise ValueError('Za mało danych z pierwszej godziny, żeby uruchomić filtr Kalmana')  # Bez historii model jest zbyt słaby.

    forecaster = KalmanTemperatureForecaster()  # Tworzymy obiekt prognozujący.
    step_minutes = 10  # Kroki prognozy są ustawione na 10 minut.
    horizon_steps = 12  # Dwie godziny = 12 punktów po 10 minut.
    rolling_history_points = min(36, len(train_df))  # Ograniczamy pamięć do kilku godzin, żeby model nie był zbyt „ciężki”.
    rolling_forecasts = []  # Lista do składania prognoz z kolejnych godzin.

    if len(future_df) < 1:  # Jeśli po pierwszej godzinie nie ma żadnych danych, nie ma czego pokazywać.
        raise ValueError('Za mało danych po pierwszej godzinie, żeby pokazać prognozę godzinową')  # Bez przyszłych danych nie ma porównania.

    segment_start = future_df.index[0]  # Pierwszy punkt po pierwszej godzinie historii.
    segment_end = future_df.index[-1]  # Ostatni punkt rzeczywiście obecny w CSV.
    simulation_end = segment_end + pd.Timedelta(hours=1)  # Jeszcze jedna godzina prognozy po końcu danych.

    while segment_start <= simulation_end:  # Pętla idzie godzinami aż do końca symulacji.
        segment_history = df_10min[df_10min.index < segment_start].tail(rolling_history_points)  # Bierzemy historię sprzed bieżącej godziny.
        if len(segment_history) < 2:  # Jeśli historia jest za krótka, kończymy.
            break  # Jeżeli nie ma historii, nie ma sensu dalej liczyć.

        forecast = forecaster.forecast_from_frame(  # Uruchamiamy prognozę dla tego konkretnego godzinnego segmentu.
            segment_history,
            temp_col='temperatura_powietrza_C',
            steps=horizon_steps,
            history_points=len(segment_history),
            step_minutes=step_minutes,
        )

        for idx, timestamp in enumerate(forecast['timestamps']):  # Przechodzimy po punktach co 10 minut.
            if timestamp > simulation_end:  # Nie chcemy wykraczać poza dodatkową godzinę po CSV.
                break  # Kończymy, gdy wyszliśmy poza zakres wizualizacji.

            actual_value = float(future_df.loc[timestamp, 'temperatura_powietrza_C']) if timestamp in future_df.index else np.nan  # Pobieramy wartość rzeczywistą, jeśli istnieje.
            rolling_forecasts.append({  # Zapisujemy jeden punkt prognozy do wspólnej listy.
                'Timestamp': timestamp,  # Czas punktu prognozy.
                'predicted': float(forecast['temperatura_powietrza_C'][idx]),
                'actual': actual_value,
                'segment_start': segment_start,  # Początek godziny, z której zrobiono prognozę.
            })

        segment_start = segment_start + pd.Timedelta(hours=1)  # Przesuwamy się o jedną godzinę i odświeżamy stan.

    if not rolling_forecasts:  # Gdy nic nie udało się policzyć, zgłaszamy błąd.
        raise ValueError('Nie udało się wygenerować żadnego odcinka prognozy')  # Gdy pętla nie zwróciła żadnego punktu.

    rolling_df = pd.DataFrame(rolling_forecasts)  # Sklejamy wszystkie punkty prognozy do jednej ramki.
    rolling_df = rolling_df.sort_values('Timestamp')  # Sortujemy po czasie.
    rolling_df = rolling_df.drop_duplicates(subset='Timestamp')  # Usuwamy ewentualne powtórki timestampów.
    predicted = rolling_df['predicted'].to_numpy(dtype=float)  # Zmieniamy prognozy na tablicę NumPy.
    timestamps = pd.to_datetime(rolling_df['Timestamp'])  # Oś czasu dla wszystkich punktów prognozy.
    actual_series = rolling_df['actual'].astype(float)  # Wartości rzeczywiste tam, gdzie dało się je pobrać.
    valid_mask = actual_series.notna().to_numpy()  # Maska pokazująca, gdzie mamy dane prawdziwe.
    actual = actual_series.to_numpy(dtype=float)  # Zmieniamy serię rzeczywistą na tablicę NumPy.
    errors = np.abs(actual[valid_mask] - predicted[valid_mask]) if valid_mask.any() else np.array([])  # Liczymy błąd tylko tam, gdzie mamy porównanie.
    if valid_mask.any():
        actual_valid = actual[valid_mask]
        predicted_valid = predicted[valid_mask]
        ss_res = float(np.sum((actual_valid - predicted_valid) ** 2))
        ss_tot = float(np.sum((actual_valid - np.mean(actual_valid)) ** 2))
        r_squared = 1.0 - (ss_res / ss_tot) if ss_tot > 0 else 1.0
    else:
        r_squared = np.nan
    rolling_df = rolling_df.copy()
    rolling_df['day'] = rolling_df['Timestamp'].dt.floor('D')
    daily_errors = []
    if valid_mask.any():
        for day, group in rolling_df[valid_mask].groupby('day'):
            day_errors = np.abs(group['actual'].to_numpy(dtype=float) - group['predicted'].to_numpy(dtype=float))
            daily_errors.append({
                'day': day,
                'mae': float(np.mean(day_errors)),
                'max_error': float(np.max(day_errors)),
                'points': int(len(day_errors)),
            })

    print('\n🔮 Prognoza Kalmana temperatury co 10 minut, odświeżana co godzinę:')  # Nagłówek w konsoli.
    print(f"{'Czas':<20} | {'Temp prognoza [°C]':<18} | {'Temp rzeczywista [°C]':<20} | {'Błąd [°C]':<10}")  # Tabela kolumn.
    print('-' * 78)  # Linia oddzielająca nagłówek od danych.

    preview_steps = min(6, len(timestamps))  # Pokazujemy tylko kilka pierwszych wierszy, żeby nie zaśmiecać konsoli.
    for idx in range(preview_steps):  # Iterujemy po pierwszych punktach prognozy.
        actual_text = f"{actual[idx]:20.2f}" if not np.isnan(actual[idx]) else f"{'brak':>20}"  # Tekst z wartością rzeczywistą albo informacją o braku.
        error_text = f"{abs(actual[idx] - predicted[idx]):10.2f}" if not np.isnan(actual[idx]) else f"{'brak':>10}"  # Tekst z błędem lub jego brakiem.
        print(  # Wypisujemy jeden wiersz tabeli.
            f"{timestamps[idx].strftime('%Y-%m-%d %H:%M'):<20} | "
            f"{predicted[idx]:18.2f} | {actual_text} | {error_text}"
        )

    if len(errors) > 0:  # Jeżeli istnieją punkty porównawcze, liczymy statystyki błędu.
        print('\n📏 Backtest prognozy po pierwszej dobie:')  # Sekcja z jakościowym podsumowaniem.
        print(f'- MAE: {errors.mean():.3f} °C')  # Średni błąd bezwzględny: średnia odległość między prognozą a prawdą.
        print(f'- Maksymalny błąd: {errors.max():.3f} °C')  # Najgorszy odchył w całym zbiorze.
        print(f'- R^2: {r_squared:.3f}')  # Współczynnik determinacji: jak dobrze prognoza dopasowuje rzeczywiste dane.
        if daily_errors:
            print('\n📅 Błąd dla każdej doby osobno:')
            for item in daily_errors:
                print(f"- {item['day'].strftime('%Y-%m-%d')}: MAE={item['mae']:.3f} °C, max_error={item['max_error']:.3f} °C, punkty={item['points']}")

    plt.figure(figsize=(14, 6))  # Tworzymy nowe okno wykresu.
    plt.plot(df.index, df['temperatura_powietrza_C'], label='Rzeczywista temperatura (15 min)', color='green', linewidth=2, alpha=0.75)  # Surowe dane 15-minutowe.
    plt.plot(df_10min.index, df_10min['temperatura_powietrza_C'], label='Rzeczywista temperatura 10 min', color='green', linewidth=1.0, alpha=0.25)  # Gęstsza wersja rzeczywistych danych.
    plt.plot(timestamps, predicted, color='red', linestyle='--', linewidth=1.2, alpha=0.7)  # Łączymy punkty prognozy linią.
    plt.scatter(timestamps, predicted, label='Prognoza Kalmana co 10 min', color='red', s=24, zorder=3)  # Zaznaczamy same punkty prognozy.
    if np.isnan(actual).any():  # Jeśli część punktów wychodzi poza CSV, oznaczamy je osobno.
        forecast_only_mask = np.isnan(actual)  # Maskujemy punkty bez rzeczywistej temperatury.
        plt.scatter(timestamps[forecast_only_mask], predicted[forecast_only_mask], color='darkred', s=32, zorder=4, label='Prognoza po końcu CSV')  # Pokazujemy odcinek poza danymi.
    plt.title('Temperatura z całego okresu i prognoza Kalmana od pierwszej godziny historii')  # Tytuł wykresu.
    plt.xlabel('Czas')  # Opis osi X.
    plt.ylabel('Temperatura [°C]')  # Opis osi Y.
    plt.grid(True, linestyle=':', alpha=0.6)  # Siatka pomaga czytać wykres.
    plt.legend()  # Legenda wyjaśnia kolory i style linii.
    plt.tight_layout()  # Dopasowanie układu, żeby etykiety się nie nakładały.
    plt.show()  # Pokazujemy wykres.


# Punkt startowy programu, gdy plik jest uruchamiany bezpośrednio.
if __name__ == '__main__':
    sciezka_do_pliku = os.path.normpath(  # Normalizujemy ścieżkę do pliku wejściowego.
        os.path.join(  # Sklejamy ścieżkę z folderów względem bieżącego pliku.
            os.path.dirname(__file__),  # Bierzemy katalog, w którym leży ten skrypt.
            '..',  # Wychodzimy poziom wyżej do katalogu benchmark.
            'Pogoda_pomiary_15_minut',  # Wchodzimy do folderu z danymi pogodowymi.
            'suwalki_pogoda_15_min_model_2010.csv',  # Wskazujemy konkretny plik CSV.
        )
    )
    run_kalman_forecast(sciezka_do_pliku)  # Uruchamiamy cały eksperyment na wskazanym pliku.