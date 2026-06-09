import subprocess

from simplace_controller import SimplaceDailyController


def parse_simdate_from_line(line: str) -> str:
    """
    Extract simDate from a line like:
      SafeCrop.HiSafeToStics: HiSFeDay=3 SimplaceDay=3 simDate=03.01.2000
    Returns the date string '03.01.2000'.
    """
    tokens = line.strip().split()
    for t in tokens:
        if t.startswith("simDate="):
            return t.split("=", 1)[1]
    raise ValueError(f"simDate= not found in line: {line}")


def run_hisafe_with_simplace():
    # 1) Start Hi-sAFe (capsis) as subprocess
    capsis_dir = "/home/hydros/capsis4"
    sim_file = "/home/hydros/mysim/exemple2/exemple.sim"

    cmd = [
        "sh",
        "capsis.sh",
        "-p",
        "script",
        "safe.pgms.ScriptGen",
        sim_file,
    ]

    proc = subprocess.Popen(
        cmd,
        cwd=capsis_dir,
        stdout=subprocess.PIPE,
        stdin=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )

    sim_ctrl = None
    waiting_for_biomass = False
    simplace_day_counter = 0

    try:
        assert proc.stdout is not None
        for raw_line in proc.stdout:
            line = raw_line.rstrip("\n")
            print(line)

            # First time we see simDate, initialise SIMPLACE controller
            if "SafeCrop.HiSafeToStics:" in line and "simDate=" in line and sim_ctrl is None:
                simdate = parse_simdate_from_line(line)  # e.g. "03.01.2000"
                print(f"[PYTHON] Initializing SIMPLACE from simDate={simdate}")
                sim_ctrl = SimplaceDailyController(
                    startdate=simdate,
                    enddate="31.12.2000",  # adjust as needed
                )
                continue

            # Track that Hi-sAFe is about to ask for biomass
            if "MANUAL BIOMASS ENTRY REQUEST" in line:
                waiting_for_biomass = True
                continue

            # Actual prompt where we must reply with biomass
            if waiting_for_biomass and "Enter biomass (t/ha)" in line:
                if sim_ctrl is None:
                    raise RuntimeError("SIMPLACE controller not initialized before biomass request")

                simplace_day_counter += 1

                # One daily SIMPLACE step
                biomass_t_ha = sim_ctrl.step_and_get_biomass()
                print(f"[PYTHON] Simplace day {simplace_day_counter}, biomass={biomass_t_ha:.4f} t/ha")

                # Send biomass value back to Hi-sAFe
                if proc.stdin is not None:
                    proc.stdin.write(f"{biomass_t_ha}\n")
                    proc.stdin.flush()

                waiting_for_biomass = False

        proc.wait()
    finally:
        if sim_ctrl is not None:
            sim_ctrl.close()
        if proc.poll() is None:
            proc.terminate()


if __name__ == "__main__":
    run_hisafe_with_simplace()
