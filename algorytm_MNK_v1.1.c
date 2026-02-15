#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include <stdbool.h>
#include <time.h>

#define MAX_LINE_LENGTH 1024
#define MAX_ROWS 5000     
#define DEFAULT_TS 225.0         // Domyslny czas probkowania w sekundach

#define COL_DATE 0 // indeks kolumny z data
#define COL_TIME 1 // indeks kolumny z czasem
#define COL_INPUT 4 // indeks kolumny z danymi wejsciowymi
#define COL_OUTPUT 8 //indeks kolumny z danymi wyjsciowymi (8 dla starych danych, 3 dla nowych)

    double sum_yy = 0.0; // Suma y[k-1]^2
    double sum_yu = 0.0; // Suma y[k-1]*u[k-1]
    double sum_uu = 0.0; // Suma u[k-1]^2
    double sum_Yy = 0.0; // Suma y[k]*y[k-1] (część wektora prawej strony)
    double sum_Yu = 0.0; // Suma y[k]*u[k-1] (część wektora prawej strony)


void replace_comma_with_dot(char *str) {
    for (int i = 0; str[i]; i++) {
        if (str[i] == ',') {
            str[i] = '.';
        }
    }
}

bool parse_datetime_from_line(const char *line, int date_col, int time_col, time_t *out_time) {
    char temp_line[MAX_LINE_LENGTH];
    char date_str[MAX_LINE_LENGTH] = {0};
    char time_str[MAX_LINE_LENGTH] = {0};
    char *token;
    int current_col = 0;

    strcpy(temp_line, line);
    token = strtok(temp_line, "\t");
    while (token != NULL) {
        if (current_col == date_col) {
            strncpy(date_str, token, sizeof(date_str) - 1);
        } else if (current_col == time_col) {
            strncpy(time_str, token, sizeof(time_str) - 1);
        }
        token = strtok(NULL, "\t");
        current_col++;
    }

    if (date_str[0] == '\0' || time_str[0] == '\0') {
        return false;
    }

    int day = 0, month = 0, year = 0;
    int hour = 0, minute = 0, second = 0;

    if (sscanf(date_str, "%d.%d.%d", &day, &month, &year) != 3) {
        return false;
    }

    if (sscanf(time_str, "%d:%d:%d", &hour, &minute, &second) < 2) {
        return false;
    }

    struct tm tm_value;
    memset(&tm_value, 0, sizeof(tm_value));
    tm_value.tm_mday = day;
    tm_value.tm_mon = month - 1;
    tm_value.tm_year = year - 1900;
    tm_value.tm_hour = hour;
    tm_value.tm_min = minute;
    tm_value.tm_sec = second;
    tm_value.tm_isdst = -1;

    time_t ts = mktime(&tm_value);
    if (ts == (time_t)-1) {
        return false;
    }

    *out_time = ts;
    return true;
}

double get_column_value(char *line, int col_index) {
    char *token;
    char temp_line[MAX_LINE_LENGTH];
    strcpy(temp_line, line);

    token = strtok(temp_line, "\t");
    int current_col = 0;

    while (token != NULL) {
        if (current_col == col_index) {
            replace_comma_with_dot(token);
            return atof(token);
        }
        token = strtok(NULL, "\t");
        current_col++;
    }
    return 0.0;
}

void MNK(double *U, double *Y, int n, double ts) {
    printf("\nWczytano %d probek danych.\n", n);
    if (n<2) {
        printf("Za malo danych do obliczen.\n");
        return;
    }
    sum_uu = 0.0;
    sum_yy = 0.0; 
    sum_yu = 0.0;
    sum_Yy = 0.0; 
    sum_Yu = 0.0;
    
    // Model: y[k] = a*y[k-1] + b*u[k-1]
    for (int k = 1; k < n; k++) {
        double y_prev = Y[k-1];
        double u_prev = U[k-1];
        double y_curr = Y[k];

        // Elementy macierzy A
        sum_yy += y_prev * y_prev;
        sum_yu += y_prev * u_prev;
        sum_uu += u_prev * u_prev;

        // Elementy wektora B
        sum_Yy += y_curr * y_prev;
        sum_Yu += y_curr * u_prev;
    }

    double det = sum_yy * sum_uu - sum_yu * sum_yu;

    if (fabs(det) < 1e-9) {
        printf("Blad: Wyznacznik macierzy bliski zeru. Uklad osobliwy.\n");
        return;
    }

    double a = (sum_uu * sum_Yy - sum_yu * sum_Yu) / det;
    double b = (sum_yy * sum_Yu - sum_yu * sum_Yy) / det;

   // printf("\n--- Wyniki modelu dyskretnego ---\n");
   // printf("Parametr a: %.6f\n", a);
   // printf("Parametr b: %.6f\n", b);
    
    double K = 0.0;
    double T = 0.0;

    if (a <= 0.0) {
        printf("BLAD: Parametr 'a' jest ujemny lub zerowy (a = %.6f).\n", a);
    } else if (a >= 1.0) {
        printf("Uwaga: Uklad niestabilny lub calkujacy (a >= 1).\n");
        K = b / (1.0 - a);
        T = -ts / log(a);
    } else {
        K = b / (1.0 - a);
        T = -ts / log(a);
        
        printf("\n--- Wyniki ---\n");
        printf("Okres probkowania TS: %.4f\n", ts);
        printf("Wzmocnienie statyczne K: %.4f\n", K);
        printf("Stala czasowa T: %.2f s\n", T);
        printf("y(t) = %.4f * (1 - e^(-t / %.2f))\n", K, T);
    }
    
    // Zwolnienie pamięci
    free(U);
    free(Y);

}


int main() {
    FILE *file = fopen("pliktxt_filtr.txt", "r");
    if (!file) {
        printf("Blad: Nie mozna otworzyc pliku 'pliktxt_filtr.txt'.\n");
        return 1;
    }

    // Tablice na dane
    double *U = (double*)malloc(MAX_ROWS * sizeof(double)); // Wejście
    double *Y = (double*)malloc(MAX_ROWS * sizeof(double)); // Wyjście
    int n = 0; // Licznik probek
    bool ilosc_probek = true;
    double ts_sum = 0.0;
    int ts_count = 0;
    bool has_prev_ts = false;
    time_t prev_ts = 0;

    char line[MAX_LINE_LENGTH];

   // fgets(line, MAX_LINE_LENGTH, file);

    while (fgets(line, MAX_LINE_LENGTH, file) && n < MAX_ROWS) {
        if (strlen(line) < 5) continue;

        if (line[0] == '-')
        {
            ilosc_probek=false;

            double ts = (ts_count > 0) ? (ts_sum / ts_count) : DEFAULT_TS;
            MNK(U, Y, n, ts);

            U = (double*)malloc(MAX_ROWS * sizeof(double)); // Wejscie
            Y = (double*)malloc(MAX_ROWS * sizeof(double)); // Wyjscie

            n = 0; // Licznik probek
            ts_sum = 0.0;
            ts_count = 0;
            has_prev_ts = false;
            prev_ts = 0;
        }
        
        if(ilosc_probek==false)
        {
            fgets(line, MAX_LINE_LENGTH, file);
            time_t current_ts;
            if (parse_datetime_from_line(line, COL_DATE, COL_TIME, &current_ts)) {
                if (has_prev_ts) {
                    double diff = difftime(current_ts, prev_ts);
                    if (diff > 0.0) {
                        ts_sum += diff;
                        ts_count++;
                    }
                }
                prev_ts = current_ts;
                has_prev_ts = true;
            }
            U[n] = get_column_value(line, COL_INPUT);
            //printf("U[%d] = %.4f\n", n, U[n]);
            Y[n] = get_column_value(line, COL_OUTPUT);
            //printf("Y[%d] = %.4f\n", n, Y[n]);
            n++;
            ilosc_probek=true;
        } 
        else{
            time_t current_ts;
            if (parse_datetime_from_line(line, COL_DATE, COL_TIME, &current_ts)) {
                if (has_prev_ts) {
                    double diff = difftime(current_ts, prev_ts);
                    if (diff > 0.0) {
                        ts_sum += diff;
                        ts_count++;
                    }
                }
                prev_ts = current_ts;
                has_prev_ts = true;
            }
            U[n] = get_column_value(line, COL_INPUT);
            //printf("U[%d] = %.4f\n", n, U[n]);
            Y[n] = get_column_value(line, COL_OUTPUT);
            //printf("Y[%d] = %.4f\n", n, Y[n]);
            n++;
        }
        
    }
    {
        double ts = (ts_count > 0) ? (ts_sum / ts_count) : DEFAULT_TS;
        MNK(U, Y, n, ts);
    }
    fclose(file);

    return 0;
}
