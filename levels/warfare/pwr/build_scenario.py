"""Write PWR's classic CE scenario through the established checked TST writer."""
import importlib.util
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[2] / "test" / "tst" / "build_scenario.py"
spec = importlib.util.spec_from_file_location("pwr_scenario_writer", SOURCE)
writer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(writer)
writer.TST_TAG = r"levels\warfare\pwr\pwr"

if __name__ == "__main__":
    writer.main()
