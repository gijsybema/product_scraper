import sys
from pathlib import Path

log_file = Path(__file__).parent.parent / "data" / "task_scheduler.log"
sys.stdout = open(log_file, "a", encoding="utf-8")
sys.stderr = sys.stdout

print("SCHEDULER TEST OK")