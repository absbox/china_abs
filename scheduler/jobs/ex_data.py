"""External reference-data jobs.

Ports of ``flow/dags/download_ex_data.py``,
``flow/dags/datasource/sync_bond_issuance_chinabond.py`` and the chinabond bond
fetchers from ``flow/dags/datasource/chinabond.py``.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime

import requests
import toolz as tz

from . import db

log = logging.getLogger("scheduler.ex_data")


# --------------------------------------------------------------------------
# chinabond fetchers (port of datasource/chinabond.py)
# --------------------------------------------------------------------------

def _fetch_query_list(year, pg_num: int = 1, pg_size: int = 1000):
    """``_fetchQueryList`` -- bond login query for one issuance year."""
    url = "https://www.chinabond.com.cn/cbiw/GetBase/bondCompositeQueryForChinese"
    headers = {
        "Accept": "*/*",
        "Content-Type": "application/json",
        "Host": "www.chinabond.com.cn",
        "Origin": "https://www.chinabond.com.cn",
        "Referer": "https://www.chinabond.com.cn/chinaBond_dong/zqzlfhcx/",
        "User-Agent": (
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36"
        ),
        "X-Requested-With": "XMLHttpRequest",
    }
    data = {
        "bondCode": "",
        "bondNameAbbr": "",
        "issuer": "",
        "issueDateStart": f"{year}-01-01",
        "issueDateEnd": f"{year}-12-31",
        "currencyCode": "",
        "transcVenueCode": "",
        "intrstAccrlMethNo": "",
        "bondTermNoStart": "",
        "bondTermNoEnd": "",
        "periodValDateStart": "",
        "periodValDateEnd": "9999-12-31",
        "bondMaturityDateStart": "",
        "bondMaturityDateEnd": "9999-12-31",
        "couponIntrstRateStart": "",
        "couponIntrstRateEnd": "",
        "remainingTermStart": "",
        "remainingTermEnd": "",
        "additionalIssuance": False,
        "bondFeatureNo": "10,36",
        "sortInfo": [],
        "pageNum": pg_num,
        "pageSize": pg_size,
    }
    r = requests.post(url, json=data, headers=headers, timeout=60)
    if r.status_code != 200:
        log.error("error %s: %s", r.status_code, r.text[:200])
        return None
    return r.json()


def fetch_query_list(year, pg_num: int = 1, pg_size: int = 100):
    """``fetchQueryList`` -- all pages for one issuance year."""
    r = _fetch_query_list(year, pg_num, pg_size)
    total_pages = int(r["data"]["pages"])
    if total_pages > 1:
        acc = []
        for i in range(pg_num + 1, total_pages + 1):
            acc = acc + _fetch_query_list(year, i, pg_size)["data"]["list"]
        return r["data"]["list"] + acc
    return r["data"]["list"]


def query_zxjg(zqdm: str):
    """``query_zxjg`` -- latest trading price for a bond code."""
    url = "https://www.chinabond.com.cn/cbiw/GetBase/queryZxjg"
    headers = {
        "Accept": "*/*",
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "Host": "www.chinabond.com.cn",
        "Origin": "https://www.chinabond.com.cn",
        "Referer": f"https://www.chinabond.com.cn/chinaBond_dong/zqzycxylb/?zqdm={zqdm}",
        "User-Agent": (
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36"
        ),
        "X-Requested-With": "XMLHttpRequest",
    }
    try:
        response = requests.post(url, headers=headers, data=f"zqdm={zqdm}", timeout=60)
        response.raise_for_status()
        return json.loads(response.text)
    except requests.exceptions.RequestException as e:
        return f"request failed: {e}"


# --------------------------------------------------------------------------
# China government bond yield curve
# --------------------------------------------------------------------------

def fetch_new_curves(sd: str):
    import akshare as ak

    assert isinstance(sd, str), f"start date should be a date but got {sd}"
    ed = datetime.today().strftime("%Y%m%d")
    log.info("pulling data with dates %s %s", sd, ed)
    bond_china_yield_df = ak.bond_china_yield(start_date=sd, end_date=ed)
    log.info("Got data with shape%s", bond_china_yield_df.shape)
    return bond_china_yield_df


def pull_interest_rate():
    """Port of ``pullInterestRate``."""
    last = db.fetchall("select max(日期) from chinacurves;")
    last_sync_date = last[0][0].strftime("%Y%m%d")
    log.info("[RateSync] Last sync date %s", last_sync_date)
    new_df = fetch_new_curves(last_sync_date)
    columns = new_df.columns.to_list()
    column_str = '","'.join(columns)
    rows = list(new_df.itertuples())
    vals = ",".join(["%s "] * len(columns))
    with db.get_conn() as conn:
        with conn.cursor() as cur:
            for _row in rows:
                row = list(_row)
                insert_sql = f'INSERT INTO chinacurves ("{column_str}") VALUES ({vals})'
                cur.execute(insert_sql, row[1:])
        conn.commit()


# --------------------------------------------------------------------------
# Trading prices
# --------------------------------------------------------------------------

def insert_cbond_lastprice(seccode, data_list):
    fullprice, cleanprice, settlecount, _, settleamount_str, settledate = data_list
    if settleamount_str:
        settleamount = float(settleamount_str.replace(",", ""))
    else:
        settleamount = None
    try:
        with db.get_conn() as conn:
            with conn.cursor() as cursor:
                insert_query = """
                    INSERT INTO public.cbond_lastprice
                    (fullprice, cleanprice, settlecount, settleamount, settledate, seccode)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    ON CONFLICT (seccode, settledate) DO UPDATE SET
                        fullprice = EXCLUDED.fullprice,
                        cleanprice = EXCLUDED.cleanprice,
                        settlecount = EXCLUDED.settlecount,
                        settleamount = EXCLUDED.settleamount;
                """
                cursor.execute(
                    insert_query,
                    (fullprice, cleanprice, settlecount, settleamount, settledate, seccode),
                )
            conn.commit()
    except Exception as e:  # noqa: BLE001
        log.error("Error inserting data: %s", e)


def scan_new_prices():
    """Port of ``scanNewPrices`` using the backout active-bond view."""
    active_bond_codes = db.q_with_m("v_active_bond_code_backout", ["bondcode"])
    for b_code in active_bond_codes:
        resp = query_zxjg(b_code["bondcode"])
        log.info("%s getting %s", b_code["bondcode"], resp)
        if resp:
            log.info("Insertting %s", b_code)
            insert_cbond_lastprice(b_code["bondcode"], resp)


def pull_china_bond_data():
    """Port of ``pullChinaBondData``."""
    log.info("[Pull ChinaBond Data] start")
    pull_cb_query_list()
    log.info("[Pull ChinaBond Trading] start")
    scan_new_prices()


# --------------------------------------------------------------------------
# Issuance list
# --------------------------------------------------------------------------

def existing_bond_codes() -> list[str]:
    r = db.fetchall("select bondCode from cbond_issuance ;")
    return list(tz.concat(r))


def pull_cb_query_list(yr=None):
    """Port of ``pullCBQueryList`` (new issuance codes -> ``cbond_issuance``)."""
    existing_codes = set(existing_bond_codes())

    def calculate_new_data(z):
        return [
            _ for _ in z if (_["bondCode"] not in existing_codes) and (_["bondCode"] is not None)
        ]

    this_year = datetime.now().year if yr is None else yr
    try:
        zz = fetch_query_list(str(this_year), pg_size=100)
        log.info("pull bond list with size: %s", len(zz))
        to_insert = calculate_new_data(zz)
        log.info("new data with size: %s", len(to_insert))

        with db.get_conn() as conn:
            with conn.cursor() as cur:
                for p in to_insert:
                    assert p["bondCode"] is not None, f"p code shouldn't be none but {p}"
                    data_obj = json.dumps(p, ensure_ascii=False)
                    cur.execute(
                        "INSERT INTO cbond_issuance (bondcode,data) VALUES (%s, %s::jsonb)",
                        (p["bondCode"], data_obj),
                    )
            conn.commit()
    except Exception as e:  # noqa: BLE001
        log.error("Failed to fetch %s", e)
