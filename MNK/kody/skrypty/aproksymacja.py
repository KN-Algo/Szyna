import tkinter as tk
import pandas as pd
import tkinter.messagebox
from tkinter import ttk
import numpy as np
import matplotlib.pyplot as plt
import csv
import datetime
from datetime import datetime
from scipy.interpolate import UnivariateSpline
from scipy.interpolate import CubicSpline
from datetime import timedelta

SEP = "-----------------------------------"



def readFile():
    try:
        with open('szyna_filtered_5hr_diff.csv') as csvfile:
            file = csv.reader(csvfile, delimiter=';')
            data = list()
            for row in file:
                data.append(row)
        return data
    except FileNotFoundError:
        print('Nie znalieziono pliku')


def csvToList(data, y_col_idx):
    ans = []
    ans.append(dict())
    k = 0
    ans[k]['start'] = 1
    ans[k]['x'] = []
    ans[k]['y'] = []

    i = 0
    p = 1

    for row in data:
        if len(row) == 1:
            ans[k]['end'] = i
            ans[k]['len'] = i - p
            p = i + 1
            ans.append(dict())
            k += 1
            ans[k]['start'] = p
            ans[k]['x'] = []
            ans[k]['y'] = []

        elif row[0].find('data') == -1 and len(row) > 1:
            if i == p:
                time0 = datetime.strptime(f"{row[0]} {row[1]}", "%d.%m.%Y %H:%M:%S")

            time1 = datetime.strptime(f"{row[0]} {row[1]}", "%d.%m.%Y %H:%M:%S")
            ans[k]['x'].append((time1 - time0).total_seconds())

            value = float(row[y_col_idx].replace(',', '.'))
            ans[k]['y'].append(value)

        i += 1

    ans[k]['end'] = i - 1
    ans[k]['len'] = i - p - 1
    return ans


def aproksymacjaInterpolacja(data, idx):
    if idx == -1:
        tk.messagebox.showerror("Błąd", "Nie wybrano ciągu")
        return

    x = np.array(data[idx]['x'])
    y = np.array(data[idx]['y'])

    sort_idx = np.argsort(x)
    x = x[sort_idx]
    y = y[sort_idx]

    x_unique, unique_idx = np.unique(x, return_index=True)
    y_unique = y[unique_idx]

    spline = CubicSpline(x_unique, y_unique, bc_type="natural")

    x_dense = np.linspace(min(x_unique), max(x_unique), 1000)
    y_dense = spline(x_dense)

    plt.figure()
    plt.scatter(x_unique, y_unique, label="Dane")
    plt.plot(x_dense, y_dense, label="Interpolacja kubiczna")
    plt.legend()
    plt.show()







def userInterface(allData):
    root = tk.Tk()
    root.title('Program')
    root.geometry('869x669')

    selected_idx = -1
    selected_col = None
    data = None

    headers = allData[0]

    def updateData():
        nonlocal data
        if selected_col is None:
            return
        data = csvToList(allData, selected_col)

    def showColumn(event):
        nonlocal selected_col
        selected_col = colCombo.current()
        updateData()

    def showSequence(event):
        nonlocal selected_idx
        selected_idx = dataCombo.current()

    hello_text = tk.Label(root, text="Witaj w programie aproksymacji!")
    hello_text.pack()

    col_text = tk.Label(root, text="Wybierz kolumnę Y")
    col_text.pack()

    colCombo = ttk.Combobox(root, state='readonly', values=headers)
    colCombo.bind("<<ComboboxSelected>>", showColumn)
    colCombo.pack()

    data_text = tk.Label(root, text="Wybierz ciąg")
    data_text.pack()

    dataCombo = ttk.Combobox(root, state='readonly')
    dataCombo.bind("<<ComboboxSelected>>", showSequence)
    dataCombo.pack()

    def refreshSequences():
        if data is None:
            return
        values = []
        for i in range(len(data)):
            values.append(
                f"{i+1}. Od {data[i]['start']} do {data[i]['end']}, {data[i]['len']} elementów"
            )
        dataCombo["values"] = values

    def onColumnChange(event):
        showColumn(event)
        refreshSequences()

    colCombo.bind("<<ComboboxSelected>>", onColumnChange)

    startButton = tk.Button(
        root,
        text="Interpolacja",
        command=lambda: aproksymacjaInterpolacja(data, selected_idx)
    )
    startButton.pack()

    root.mainloop()


allData = readFile()
headers = allData[0]
userInterface(allData)

