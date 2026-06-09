import pandas as pd
import matplotlib.pyplot as plt

trees = pd.read_csv("exemple_trees.txt", sep="\t")

trees["Date"] = pd.to_datetime(
    trees["Date"],
    dayfirst=True
)

plt.figure(figsize=(12,6))
plt.plot(trees["Date"], trees["dbh"])
plt.xlabel("Date")
plt.ylabel("DBH")
plt.title("DBH vs Date")
plt.grid(True)
plt.show()

import pandas as pd
import matplotlib.pyplot as plt

# -------------------------
# TREE DBH
# -------------------------
trees = pd.read_csv("exemple_trees.txt", sep="\t")

trees["Date"] = pd.to_datetime(
    trees["Date"],
    dayfirst=True
)

plt.figure(figsize=(12,5))
plt.plot(trees["Date"], trees["dbh"], lw=1)
plt.xlabel("Date")
plt.ylabel("DBH")
plt.title("Tree DBH")
plt.grid(True)

# -------------------------
# SIMPLACE OUTPUT
# -------------------------

rows = []

with open("simplace_outputs.txt") as f:
    for line in f:
        parts = line.split()

        # data rows start with YYYY-MM-DD
        if len(parts) > 5 and parts[0][:4].isdigit():
            rows.append(parts[:10])  # ignore soil_water

sim = pd.DataFrame(rows)

sim.columns = [
    "Date",
    "Cell",
    "Var1",
    "Var2",
    "Var3",
    "Var4",
    "Var5",
    "Var6",
    "Var7",
    "Var8",
]

sim["Date"] = pd.to_datetime(sim["Date"])

for c in sim.columns[1:]:
    sim[c] = pd.to_numeric(sim[c])

# Example: plot Var1
daily = sim.groupby("Date")["Var1"].mean()

plt.figure(figsize=(12,5))
plt.plot(daily.index, daily.values)
plt.xlabel("Date")
plt.ylabel("Var1")
plt.title("SIMPLACE Variable 1 vs Date")
plt.grid(True)

plt.show()
