import runpy
from pathlib import Path

watcher = Path(__file__).resolve().parent / 'scripts/watch-serato-native-startup.py'
raise SystemExit(runpy.run_path(str(watcher))['run_registered']('1113ad06346f399a526ed784776c55e12c0531e93ca292f6ec41a89d5a7f950f'))
