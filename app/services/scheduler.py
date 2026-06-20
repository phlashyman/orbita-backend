"""
scheduler.py
============
Scheduled jobs for automatic data fetching — keeps Orbita data fresh.

Jobs:
  - Daily 18:00: Check BODIVA for new daily bulletin
  - Daily 19:00: Fetch USD/AOA, EUR/AOA from public sources
  - Weekly Mon 08:00: Generate weekly AI newsletter
  - Monthly day 5: Fetch BODIVA monthly report
  - Monthly day 15: Update CRP (Damodaran), inflation (INE)

Uses APScheduler for in-process job scheduling.
In production, this would run alongside the FastAPI app.

To start: python -m app.services.scheduler
"""
from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime, timedelta
from typing import Any, Dict, Optional, List

logger = logging.getLogger("orbita.scheduler")


# ═══════════════════════════════════════════════════════════════════════════
# Data fetching functions
# ═══════════════════════════════════════════════════════════════════════════

async def fetch_bodiva_boletim() -> Dict[str, Any]:
    """
    Check BODIVA website for the latest daily bulletin.
    If a new one is found, download and import it.

    BODIVA URL pattern: https://www.bodiva.ao/.../boletim-diario
    For MVP: placeholder that logs intent.
    """
    logger.info("[BODIVA] Checking for new daily bulletin...")
    # TODO: implement actual HTTP fetch when BODIVA publishes a stable URL
    return {
        "job": "bodiva_boletim",
        "status": "placeholder",
        "message": "BODIVA daily bulletin fetch — URL not yet configured.",
        "timestamp": datetime.utcnow().isoformat(),
    }


async def fetch_fx_rates() -> Dict[str, Any]:
    """
    Fetch USD/AOA, EUR/AOA, ZAR/AOA from BNA (Banco Nacional de Angola)
    or a public FX API.

    For MVP: uses an approximation from known sources.
    """
    logger.info("[FX] Fetching exchange rates...")
    import httpx

    rates = {"usd_aoa": 650.0, "eur_aoa": 710.0, "zar_aoa": 35.0, "source": "bna_approximation"}
    try:
        # Try BNA API (if available)
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get("https://www.bna.ao/api/...")
            if resp.status_code == 200:
                data = resp.json()
                rates = {"usd_aoa": data.get("USD", 650), "eur_aoa": data.get("EUR", 710),
                         "zar_aoa": data.get("ZAR", 35), "source": "bna"}
    except Exception:
        logger.warning("[FX] BNA API not available, using default rates.")

    logger.info(f"[FX] Rates: USD/AOA={rates['usd_aoa']}, EUR/AOA={rates['eur_aoa']}")
    return {
        "job": "fx_rates",
        "status": "ok",
        "rates": rates,
        "timestamp": datetime.utcnow().isoformat(),
    }


async def update_country_risk() -> Dict[str, Any]:
    """
    Update Angola country risk metrics — CRP from Damodaran, CDS, rating.

    Damodaran URL: http://pages.stern.nyu.edu/~adamodar/
    For MVP: placeholder that logs intent.
    """
    logger.info("[RISK] Updating country risk metrics...")
    return {
        "job": "country_risk",
        "status": "placeholder",
        "message": "Country risk update — data source URL not yet configured.",
        "timestamp": datetime.utcnow().isoformat(),
    }


async def generate_weekly_newsletter() -> Dict[str, Any]:
    """
    Generate the weekly market newsletter via AI.
    For MVP: placeholder that logs intent.
    """
    logger.info("[NEWS] Checking weekly newsletter...")
    return {
        "job": "weekly_newsletter",
        "status": "placeholder",
        "message": "News generation not yet wired to scheduler.",
        "timestamp": datetime.utcnow().isoformat(),
    }


async def fetch_bodiva_monthly_report() -> Dict[str, Any]:
    """Fetch BODIVA monthly report (PDF) if available."""
    logger.info("[BODIVA] Checking for monthly report...")
    return {
        "job": "bodiva_monthly",
        "status": "placeholder",
        "message": "Monthly report fetch — URL not yet configured.",
        "timestamp": datetime.utcnow().isoformat(),
    }


# ═══════════════════════════════════════════════════════════════════════════
# Job registry
# ═══════════════════════════════════════════════════════════════════════════

JOBS = [
    {
        "name": "bodiva_boletim",
        "func": fetch_bodiva_boletim,
        "cron": "0 18 * * *",
        "description": "Fetch BODIVA daily bulletin (daily 18:00)",
    },
    {
        "name": "fx_rates",
        "func": fetch_fx_rates,
        "cron": "0 19 * * *",
        "description": "Fetch USD/AOA, EUR/AOA rates (daily 19:00)",
    },
    {
        "name": "weekly_newsletter",
        "func": generate_weekly_newsletter,
        "cron": "0 8 * * 1",
        "description": "Generate weekly AI newsletter (Monday 08:00)",
    },
    {
        "name": "bodiva_monthly",
        "func": fetch_bodiva_monthly_report,
        "cron": "0 6 5 * *",
        "description": "Fetch BODIVA monthly report (day 5)",
    },
    {
        "name": "country_risk",
        "func": update_country_risk,
        "cron": "0 7 15 * *",
        "description": "Update Angola country risk metrics (day 15)",
    },
]


# ═══════════════════════════════════════════════════════════════════════════
# Scheduler runner
# ═══════════════════════════════════════════════════════════════════════════

async def run_job_once(job_name: str) -> Dict[str, Any]:
    """Run a single job by name (useful for testing)."""
    for job in JOBS:
        if job["name"] == job_name:
            func = job["func"]
            if asyncio.iscoroutinefunction(func):
                return await func()
            return func()
    return {"error": f"Job '{job_name}' not found."}


def start_scheduler() -> None:
    """
    Start the APScheduler background scheduler.
    Call this once during application startup.

    Usage: from app.services.scheduler import start_scheduler
           start_scheduler()
    """
    try:
        from apscheduler.schedulers.asyncio import AsyncIOScheduler
        from apscheduler.triggers.cron import CronTrigger

        scheduler = AsyncIOScheduler()

        for job in JOBS:
            scheduler.add_job(
                func=job["func"],
                trigger=CronTrigger.from_crontab(job["cron"]),
                id=job["name"],
                name=job["name"],
                replace_existing=True,
                misfire_grace_time=3600,
            )

        scheduler.start()
        logger.info(f"[SCHEDULER] Started {len(JOBS)} jobs.")
    except ImportError:
        logger.warning("[SCHEDULER] APScheduler not installed. Skipping scheduler start.")
        logger.info("Install: pip install apscheduler")
    except Exception as e:
        logger.error(f"[SCHEDULER] Failed to start: {e}")


# ═══════════════════════════════════════════════════════════════════════════
# CLI entry point
# ═══════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")
    logger.info("Orbita Scheduler — manual CLI mode")
    logger.info("Available jobs: %s", [j["name"] for j in JOBS])
    logger.info("")

    import sys
    if len(sys.argv) > 1:
        job_name = sys.argv[1]
        logger.info(f"Running job: {job_name}")
        result = asyncio.run(run_job_once(job_name))
        print(result)
    else:
        logger.info("Usage: python -m app.services.scheduler <job_name>")
        logger.info("Jobs: %s", ", ".join(j["name"] for j in JOBS))
