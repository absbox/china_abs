"""Main APScheduler entry point.

Exact port of ``flow/dags/scheduler.py``: the same 14 jobs with the same cron
triggers, job ids and APScheduler configuration.  Job bodies now live in
:mod:`jobs` and are built on the new subprojects.

Run::

    python main.py          # start the blocking scheduler
    python main.py --list   # print registered jobs and exit
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from functools import partial
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

import pathsetup  # noqa: E402  (adds docToCloud to sys.path)
import china_model  # noqa: E402
from apscheduler.schedulers.blocking import BlockingScheduler  # noqa: E402

from jobs.cleanup import catch_up_pdf, delete_unused_files  # noqa: E402
from jobs.cloud import archieve_files  # noqa: E402
from jobs.docs import (  # noqa: E402
    download_issuance_pricing,
    download_pricing_outstanding_deal,
    pull_income_docs,
)
from jobs.ex_data import pull_china_bond_data, pull_interest_rate  # noqa: E402
from jobs.fill import (  # noqa: E402
    fill_deal_data_obj,
    llm_extract_deal_data,
    parse_issuance_pricing,
)
from jobs.health import write_health_report  # noqa: E402
from jobs.mineru import process_mineru_queue  # noqa: E402

# APScheduler configuration preserved from flow/dags/scheduler.py.  In flow this
# dict was defined but never passed to the scheduler (so the in-memory defaults
# were used).  The same is true here by default; set SCHEDULER_PERSIST=1 to
# enable the sqlalchemy jobstore / configured executors.
scheduler_params = {
    "apscheduler.jobstores.default": {
        "type": "sqlalchemy",
        "url": "sqlite:///jobs.sqlite",
    },
    "apscheduler.executors.default": {
        "class": "apscheduler.executors.pool:ThreadPoolExecutor",
        "max_workers": "20",
    },
    "apscheduler.executors.processpool": {
        "type": "processpool",
        "max_workers": "5",
    },
    "apscheduler.job_defaults.coalesce": "false",
    "apscheduler.job_defaults.max_instances": "3",
    "apscheduler.timezone": "UTC",
}

dl_today_fn = partial(download_issuance_pricing, cutDaysNum=1, docTypesList=["发行文件"])


def _log_dir() -> Path:
    d = Path(os.getenv("SCHEDULER_LOG_DIR", str(pathsetup.SCHEDULER_DIR / "logs")))
    d.mkdir(parents=True, exist_ok=True)
    return d


def _configure_logging() -> None:
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    if not any(
        isinstance(h, logging.StreamHandler)
        and not isinstance(h, TimedRotatingFileHandler)
        for h in root_logger.handlers
    ):
        console = logging.StreamHandler(sys.stdout)
        console.setFormatter(formatter)
        root_logger.addHandler(console)
    file_handler = TimedRotatingFileHandler(
        filename=_log_dir() / "scheduler.log",
        when="midnight",
        interval=1,
        backupCount=30,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    root_logger.addHandler(file_handler)


def build_scheduler() -> BlockingScheduler:
    """Register the same jobs as ``flow/dags/scheduler.py``."""
    if os.getenv("SCHEDULER_PERSIST", "0") == "1":
        sched = BlockingScheduler(gconfig=scheduler_params)
    else:
        sched = BlockingScheduler()

    # --- Clean up ---
    sched.add_job(catch_up_pdf, "cron", hour=5, minute=0, id="catchUpPdf", replace_existing=True)
    sched.add_job(
        delete_unused_files, "cron", hour="*/2", minute=0, id="deleteUnusedFiles", replace_existing=True
    )

    # --- Data builder ---
    sched.add_job(
        pull_interest_rate, "cron", hour=23, minute=0, id="pullInterestRate", replace_existing=True
    )

    # --- Deal docs download [eager mode] ---
    sched.add_job(
        dl_today_fn,
        "cron",
        minute=30,
        hour="9-21",
        day_of_week="mon-sat",
        id="eager_download_issue_file",
        replace_existing=True,
    )
    sched.add_job(
        download_pricing_outstanding_deal,
        "cron",
        minute=0,
        hour="9-21",
        day_of_week="mon-sat",
        id="eager_download_pricing_file",
        replace_existing=True,
    )
    sched.add_job(
        download_issuance_pricing,
        "cron",
        minute=0,
        hour=22,
        day_of_week="mon-sat",
        id="safenet_eager_download",
        replace_existing=True,
    )
    sched.add_job(
        parse_issuance_pricing,
        "cron",
        minute="*/15",
        day_of_week="mon-sat",
        id="eager_parse",
        replace_existing=True,
    )

    # --- Deal docs extract ---
    sched.add_job(pull_income_docs, "cron", hour=19, minute=0, id="pullIncomeDocs", replace_existing=True)
    sched.add_job(
        pull_china_bond_data, "cron", hour=15, minute=0, id="pullChinaBondData", replace_existing=True
    )
    sched.add_job(
        llm_extract_deal_data,
        "cron",
        hour=20,
        minute=30,
        id="llm_extract_deal_data",
        replace_existing=True,
    )
    sched.add_job(
        fill_deal_data_obj, "cron", minute="*/15", id="fill_deal_data_obj", replace_existing=True
    )

    # --- Health snapshot ---
    sched.add_job(
        write_health_report, "cron", minute="*/15", id="writeHealthReport", replace_existing=True
    )

    # --- MinerU queue ---
    sched.add_job(
        process_mineru_queue, "cron", minute="*/5", id="submitMineruQueue", replace_existing=True
    )

    # --- Archive files ---
    sched.add_job(
        archieve_files, "cron", day=26, hour=3, minute=0, id="archieveFiles", replace_existing=True
    )

    return sched


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="scheduler",
        description="APScheduler orchestration for the china-abs document pipeline.",
    )
    parser.add_argument("--list", action="store_true", help="list registered jobs and exit")
    args = parser.parse_args()

    _configure_logging()
    china_model.configure()
    sched = build_scheduler()

    if args.list:
        for job in sched.get_jobs():
            print(f"{job.id}\t{job.trigger}")
        return

    logging.info("Scheduler started")
    sched.start()


if __name__ == "__main__":
    main()
