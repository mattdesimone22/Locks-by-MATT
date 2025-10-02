# update_scheduler.py
import time, subprocess, logging
from datetime import datetime, timezone, timedelta

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("update_scheduler")

def run_every_day_at(hour_utc=13, minute=0):
    while True:
        now = datetime.now(timezone.utc)
        target = now.replace(hour=hour_utc, minute=minute, second=0, microsecond=0)
        if target < now:
            target = target + timedelta(days=1)
        wait_seconds = (target - now).total_seconds()
        logger.info("Sleeping %.0f seconds until next run at %s", wait_seconds, target.isoformat())
        time.sleep(wait_seconds)
        logger.info("Running generate_picks.py at %s", datetime.now(timezone.utc).isoformat())
        subprocess.run(["python", "generate_picks.py"], check=True)

if __name__ == "__main__":
    run_every_day_at(hour_utc=13, minute=0)  # 9 AM EST -> 13:00 UTC (non-DST aware)
