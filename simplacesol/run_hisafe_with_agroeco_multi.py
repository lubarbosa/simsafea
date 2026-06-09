import subprocess
from typing import Optional, List, Dict, Any
from dataclasses import dataclass
import time
import re

from multi_cell_agroeco_controller import MultiCellAgroEcoController, CellWeather

# ---------------------------------------------------------------------------
# Cell layout MUST mirror exemple.sim ZONE definitions (5x5 = 25 cells):
#   ZONE main  1-2,4-7,9-12,14-17,19-22,24-25  maize.tec     -> crop cells
#   ZONE inter 3,8,13,18,23                    baresoil.tec  -> NO crop model
# Only the 20 maize cells are simulated in SIMPLACE.
# ---------------------------------------------------------------------------
CROP_CELL_IDS: List[int] = [
    1, 2, 4, 5, 6, 7, 9, 10, 11, 12,
    14, 15, 16, 17, 19, 20, 21, 22, 24, 25,
]
BARE_SOIL_CELL_IDS = {3, 8, 13, 18, 23}

N_CELLS = len(CROP_CELL_IDS)  # 20

# Hi-sAFe cellId  ->  SIMPLACE simulation index (0..N_CELLS-1)
cell_id_to_sim_idx: Dict[int, int] = {cid: idx for idx, cid in enumerate(CROP_CELL_IDS)}

# Bare-soil override sent back to Hi-sAFe when it asks about a non-crop cell.
# biomass, lai, root_depth_m, grain_biomass, plant_n, water_demand, n_demand
bare_soil_soil_water = ",".join(["0.0"] * 19)
BARE_SOIL_OVERRIDE = f"0.0,0.0,0.01,0.0,0.0,0.0,0.0|{bare_soil_soil_water}\n"


@dataclass
class CellWeatherBuffer:
    """Buffer to collect weather data for one CROP cell before stepping."""
    cell_rad: Optional[float] = None
    tmin: Optional[float] = None
    tmax: Optional[float] = None
    wind: Optional[float] = None
    cell_rain: Optional[float] = None

    def is_complete(self) -> bool:
        return all([
            self.cell_rad is not None,
            self.tmin is not None,
            self.tmax is not None,
            self.wind is not None,
            self.cell_rain is not None,
        ])

    def to_cell_weather(self) -> CellWeather:
        return CellWeather(
            cell_rad=self.cell_rad,
            tmin=self.tmin,
            tmax=self.tmax,
            wind=self.wind,
            cell_rain=self.cell_rain,
        )


def parse_stics_julian_day(line: str) -> int:
    if ":" in line:
        _, rest = line.split(":", 1)
    else:
        rest = line
    tokens = rest.strip().split()
    for t in tokens:
        if t.startswith("sticsJulianDay="):
            return int(t.split("=", 1)[1])
    raise ValueError(f"sticsJulianDay= not found in line: {line}")


def parse_cell_id(line: str) -> int:
    tokens = line.strip().split()
    for t in tokens:
        if t.startswith("cellId="):
            return int(t.split("=", 1)[1])
    raise ValueError(f"cellId= not found in line: {line}")


def parse_value(line: str, key: str) -> Optional[float]:
    tokens = line.strip().split()
    for t in tokens:
        if t.startswith(f"{key}="):
            try:
                return float(t.split("=", 1)[1])
            except ValueError:
                return None
    return None


def parse_hisafe_soil_water_from_output(proc_output):
    """
    Extract Hi-SAFE soil water state from process output
    Format: [HI-SAFE->SIMPLACE] Cell X soil_water: 17.18% 21.08% 24.90% 26.42% 0.00%
    """
    hisafe_soil_water = {}
    
    pattern = r'\[HI-SAFE->SIMPLACE\] Cell (\d+) soil_water: ([\d.]+)% ([\d.]+)% ([\d.]+)% ([\d.]+)% ([\d.]+)%'
    
    for line in proc_output.split('\n'):
        match = re.search(pattern, line)
        if match:
            cell_id = int(match.group(1))
            hisafe_soil_water[cell_id] = [
                float(match.group(2)),  # Layer 0: 0-40cm
                float(match.group(3)),  # Layer 1: 40-80cm
                float(match.group(4)),  # Layer 2: 80-140cm
                float(match.group(5)),  # Layer 3: 140-240cm
                float(match.group(6)),  # Layer 4: 240-340cm
            ]
    
    return hisafe_soil_water


def run_hisafe_with_agroeco_multi():
    capsis_dir = "/home/hydros/capsis4"
    sim_file = "/home/hydros/mysim/exemple2/exemple.sim"

    cmd = ["sh", "capsis.sh", "-p", "script", "safe.pgms.ScriptGen", sim_file]

    proc = subprocess.Popen(
        cmd,
        cwd=capsis_dir,
        stdout=subprocess.PIPE,
        stdin=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )

    sim_ctrl: Optional[MultiCellAgroEcoController] = None

    current_stics_day: Optional[int] = None
    previous_stics_day: Optional[int] = None

    # One buffer per CROP cell, indexed by SIMPLACE simulation index (0..19)
    current_day_weather: List[CellWeatherBuffer] = [
        CellWeatherBuffer() for _ in range(N_CELLS)
    ]

    # SIMPLACE results from PREVIOUS day, indexed by SIMPLACE simulation index
    previous_day_crop_state: List[Dict[str, Any]] = []

    weather_complete_for_current_day = False

    waiting_for_biomass = False
    last_requested_cell: Optional[int] = None

    try:
        assert proc.stdout is not None
        for raw_line in proc.stdout:
            line = raw_line.rstrip("\n")
            print(line)

            # --- Track STICS Julian day transitions -------------------------
            if "DEBUG SafeCrop.processGrowth1:" in line and "sticsJulianDay=" in line:
                stics_day = parse_stics_julian_day(line)

                if current_stics_day is None or stics_day != current_stics_day:
                    previous_stics_day = current_stics_day
                    current_stics_day = stics_day
                    weather_complete_for_current_day = False

                    print(f"[PYTHON] === New STICS day: {current_stics_day} ===")
                    current_day_weather = [CellWeatherBuffer() for _ in range(N_CELLS)]

                if sim_ctrl is None:
                    print(f"[PYTHON] Initializing MultiCellAgroEcoController with "
                          f"{N_CELLS} crop simulations (cells {CROP_CELL_IDS})")
                    # Pass the real Hi-sAFe IDs so logs/results carry them.
                    sim_ctrl = MultiCellAgroEcoController(
                        n_cells=N_CELLS,
                        cell_ids=CROP_CELL_IDS,
                    )

                continue

            # --- Parse weather variables ------------------------------------
            if "SafeCrop.HiSafeToStics:" in line and "cellId=" in line:
                cell_id = parse_cell_id(line)

                # Skip bare-soil / out-of-range cells: no crop model for them.
                sim_idx = cell_id_to_sim_idx.get(cell_id)
                if sim_idx is None:
                    continue

                buf = current_day_weather[sim_idx]

                cell_rad = parse_value(line, "cellRad")
                if cell_rad is not None:
                    buf.cell_rad = cell_rad
                tmin = parse_value(line, "Tmin")
                if tmin is not None:
                    buf.tmin = tmin
                tmax = parse_value(line, "Tmax")
                if tmax is not None:
                    buf.tmax = tmax
                wind = parse_value(line, "wind")
                if wind is not None:
                    buf.wind = wind
                cell_rain = parse_value(line, "cellRain")
                if cell_rain is not None:
                    buf.cell_rain = cell_rain

                # Step only once all 20 CROP cells are complete.
                if not weather_complete_for_current_day and all(
                    cell.is_complete() for cell in current_day_weather
                ):
                    if sim_ctrl is None:
                        raise RuntimeError("SIMPLACE controller not initialized")

                    weather_complete_for_current_day = True
                    print(f"[PYTHON] All {N_CELLS} crop-cell weather sets collected "
                          f"for STICS day {current_stics_day}, stepping SIMPLACE")

                    weather_data = [cell.to_cell_weather() for cell in current_day_weather]
                    results = sim_ctrl.step_and_get_results(weather_data)
                    previous_day_crop_state = results  # indexed by sim_idx

                    print(f"[PYTHON] SIMPLACE stepped for day {current_stics_day}:")
                    print(f"  Biomass:    [{min(r['biomass'] for r in results):.4f} - "
                          f"{max(r['biomass'] for r in results):.4f}] t/ha")
                    print(f"  LAI:        [{min(r['lai'] for r in results):.2f} - "
                          f"{max(r['lai'] for r in results):.2f}] m²/m²")
                    print(f"  Root depth: [{min(r['root_depth_m'] for r in results):.3f} - "
                          f"{max(r['root_depth_m'] for r in results):.3f}] m")

                continue

            # --- Crop state override requests -------------------------------
            if "MANUAL CROP STATE OVERRIDE REQUEST" in line:
                waiting_for_biomass = True
                last_requested_cell = None
                print("[PYTHON] Got override request, waiting for Cell ID...")
                continue

            if waiting_for_biomass and "Cell ID:" in line:
                try:
                    parts = line.replace(",", "").split()
                    for i, p in enumerate(parts):
                        if p == "ID:" and i + 1 < len(parts):
                            last_requested_cell = int(parts[i + 1])
                            print(f"[PYTHON] Parsed cell ID: {last_requested_cell}")
                            break
                except Exception as e:
                    print(f"[PYTHON ERROR] Failed to parse cell ID: {e}")
                continue

            if waiting_for_biomass and "Enter crop state" in line:
                print(f"[PYTHON] Got 'Enter crop state' prompt for cell {last_requested_cell}")
                try:
                    if last_requested_cell is None:
                        print("[PYTHON ERROR] Cell ID not parsed!")
                        if proc.stdin is not None:
                            proc.stdin.write(BARE_SOIL_OVERRIDE)
                            proc.stdin.flush()
                            time.sleep(0.2)
                        waiting_for_biomass = False
                        last_requested_cell = None
                        continue

                    # ===== CHECK IF BARE SOIL =====
                    if last_requested_cell in BARE_SOIL_CELL_IDS or last_requested_cell not in cell_id_to_sim_idx:
                        print(f"[PYTHON] Cell {last_requested_cell} is BARE SOIL -> sending override")
                        if proc.stdin is not None:
                            proc.stdin.write(BARE_SOIL_OVERRIDE)
                            proc.stdin.flush()
                            time.sleep(0.2)
                        waiting_for_biomass = False
                        last_requested_cell = None
                        continue

                    # ===== CHECK IF CROP CELL WITH RESULTS =====
                    if sim_ctrl is None:
                        print("[PYTHON ERROR] SIMPLACE controller not initialized!")
                        if proc.stdin is not None:
                            proc.stdin.write(BARE_SOIL_OVERRIDE)
                            proc.stdin.flush()
                            time.sleep(0.2)
                        waiting_for_biomass = False
                        last_requested_cell = None
                        continue

                    # No results yet (very first day before any step)
                    if not previous_day_crop_state:
                        print(f"[PYTHON WARNING] No SIMPLACE results yet for cell {last_requested_cell}")
                        if proc.stdin is not None:
                            proc.stdin.write(BARE_SOIL_OVERRIDE)
                            proc.stdin.flush()
                            time.sleep(0.2)
                        waiting_for_biomass = False
                        last_requested_cell = None
                        continue

                    # ===== GET CROP DATA =====
                    sim_idx = cell_id_to_sim_idx[last_requested_cell]
                    cell_data = previous_day_crop_state[sim_idx]

                    biomass = cell_data["biomass"]
                    lai = cell_data["lai"]
                    root_depth_m = cell_data["root_depth_m"]
                    grain_biomass = cell_data["grain_biomass"]
                    plant_n_kg_ha = cell_data["plant_n_kg_ha"]
                    water_demand_mm = cell_data["water_demand_mm"]
                    n_demand_kg_ha = cell_data["n_demand_kg_ha"]
                    soil_water_by_layer = cell_data.get("soil_water_by_layer", [0.0] * 19)

                    print(f"[PYTHON] Sending SIMPLACE crop data for cell {last_requested_cell} (sim_idx {sim_idx})")
                    print(f"  Biomass: {biomass:.4f} t/ha | LAI: {lai:.4f} | Yield: {grain_biomass:.4f} t/ha")

                    # Convert soil water to percentage if needed
                    soil_water_pct = []
                    for w in soil_water_by_layer[:19]:
                        if w <= 1.0:
                            soil_water_pct.append(w * 100.0)  # Convert to %
                        else:
                            soil_water_pct.append(w)

                    soil_water_str = ",".join([f"{x:.6f}" for x in soil_water_pct])
                    override_string = (
                        f"{biomass:.6f},{lai:.6f},{root_depth_m:.6f},{grain_biomass:.6f},"
                        f"{plant_n_kg_ha:.6f},{water_demand_mm:.6f},{n_demand_kg_ha:.6f}|"
                        f"{soil_water_str}\n"
                    )

                    if proc.stdin is not None:
                        proc.stdin.write(override_string)
                        proc.stdin.flush()
                        time.sleep(0.2)  # CRITICAL: Give Hi-SAFE time to process
                        print(f"[PYTHON] Override sent to Hi-SAFE, waiting...")

                    waiting_for_biomass = False
                    last_requested_cell = None

                except Exception as e:
                    print(f"[PYTHON ERROR] Exception during override: {e}")
                    import traceback
                    traceback.print_exc()
                    if proc.stdin is not None:
                        try:
                            proc.stdin.write(BARE_SOIL_OVERRIDE)
                            proc.stdin.flush()
                            time.sleep(0.2)
                        except:
                            pass
                    waiting_for_biomass = False
                    last_requested_cell = None

                continue

        proc.wait()
    finally:
        if sim_ctrl is not None:
            sim_ctrl.close()
        if proc.poll() is None:
            proc.terminate()


if __name__ == "__main__":
    run_hisafe_with_agroeco_multi()

