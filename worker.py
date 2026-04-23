import time

from backend.app2 import RUN_SCHEDULER, ensure_scheduler_started


if __name__ == "__main__":
    if not RUN_SCHEDULER:
        raise RuntimeError("Set RUN_SCHEDULER=true before starting worker.py")

    ensure_scheduler_started()
    print("[*] Scheduler worker is running", flush=True)

    while True:
        time.sleep(60)
