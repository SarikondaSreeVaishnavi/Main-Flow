import os
import time


os.environ["RUN_SCHEDULER"] = "true"

from backend.app2 import ensure_scheduler_started


if __name__ == "__main__":
    ensure_scheduler_started()
    print("[*] Scheduler worker is running", flush=True)

    while True:
        time.sleep(60)
