#!/usr/bin/env python3
"""
Institutional FX & Monetary Policy Data Pipeline
- 18 Currencies (G10 + Key EM)
- Multi-source cascade (Live Scraper + Official CB APIs + BIS + FRED)
- 60-Month aligned history for Cross-FX & Real Rate Z-Score modeling
"""

import csv
import io
import json
import os
import random
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import requests
import yfinance as yf
from bs4 import BeautifulSoup

# --- Configuration & Chemins ---
ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "public" / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

SNAPSHOT_FILE = DATA_DIR / "fx_macro_snapshot.json"
HISTORY_FILE = DATA_DIR / "fx_history.json"
MEETINGS_FILE = DATA_DIR / "meetings.json"

FRED_API_KEY = os.environ.get("FRED_API_KEY", "")
N_MONTHS = 60  # 5 ans d'historique mensuel aligné
MAX_CPI_AGE_MONTHS = 3

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_6) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64; rv:130.0) Gecko/20100101 Firefox/130.0",
]

# --- Référentiel des 18 Devises (G10 + EM) ---
CURRENCIES_CONFIG = {
    # === G10 ===
    "USD": dict(
        iso3="USA", group="G10", name="États-Unis", flag="🇺🇸",
        bank="Federal Reserve (Fed)", rateLabel="Fed Funds Target (Upper)", gov="Jerome Powell", target=2.0,
        fxTicker=None, yieldTicker="^IRX", teSlug="united-states",
        rate=[("fred", "DFEDTARU"), ("bis_rate", "US")],
        cpi=[("fred", "CPIAUCSL", "index"), ("bis_cpi", "US", "yoy")],
        core=[("fred", "CPILFESL", "index")],
        y2=[("fred", "DGS2")]
    ),
    "EUR": dict(
        iso3="FRA", group="G10", name="Zone Euro", flag="🇪🇺",
        bank="Banque Centrale Européenne (BCE)", rateLabel="Taux Facilité de Dépôt", gov="Christine Lagarde", target=2.0,
        fxTicker="EURUSD=X", teSlug="euro-area",
        rate=[("fred", "ECBDFR"), ("bis_rate", "XM")],
        cpi=[("bis_cpi", "XM", "yoy"), ("fred", "CP0000EZ19M086NEST", "index")],
        core=[("fred", "CPHPLA01EZM659N", "yoy")],
        y2=[("fred", "IRLTLT01EZM156N")]
    ),
    "JPY": dict(
        iso3="JPN", group="G10", name="Japon", flag="🇯🇵",
        bank="Bank of Japan (BoJ)", rateLabel="Uncollateralized Overnight Call", gov="Kazuo Ueda", target=2.0,
        fxTicker="JPY=X", teSlug="japan",
        rate=[("bis_rate", "JP")],
        cpi=[("bis_cpi", "JP", "yoy"), ("fred", "JPNCPIALLMINMEI", "index")],
        core=[("fred", "JPNCPICORMINMEI", "index")],
        y2=[]
    ),
    "GBP": dict(
        iso3="GBR", group="G10", name="Royaume-Uni", flag="🇬🇧",
        bank="Bank of England (BoE)", rateLabel="Official Bank Rate", gov="Andrew Bailey", target=2.0,
        fxTicker="GBPUSD=X", teSlug="united-kingdom",
        rate=[("bis_rate", "GB")],
        cpi=[("bis_cpi", "GB", "yoy"), ("fred", "GBRCPIALLMINMEI", "index")],
        core=[("fred", "GBRCPICORMINMEI", "index")],
        y2=[]
    ),
    "CHF": dict(
        iso3="CHE", group="G10", name="Suisse", flag="🇨🇭",
        bank="Banque Nationale Suisse (BNS)", rateLabel="Taux Directeur BNS", gov="Martin Schlegel", target=2.0,
        fxTicker="CHF=X", teSlug="switzerland",
        rate=[("bis_rate", "CH")],
        cpi=[("bis_cpi", "CH", "yoy"), ("fred", "CHECPIALLMINMEI", "index")],
        core=[("fred", "CHECPICORMINMEI", "index")],
        y2=[]
    ),
    "CAD": dict(
        iso3="CAN", group="G10", name="Canada", flag="🇨🇦",
        bank="Bank of Canada (BoC)", rateLabel="Target Overnight Rate", gov="Tiff Macklem", target=2.0,
        fxTicker="CAD=X", teSlug="canada",
        rate=[("boc", "V39079"), ("bis_rate", "CA")],
        cpi=[("bis_cpi", "CA", "yoy"), ("fred", "CANCPIALLMINMEI", "index")],
        core=[("fred", "CANCPICORMINMEI", "index")],
        y2=[("boc", "BD.CDN.2YR.DQ.YLD")]
    ),
    "AUD": dict(
        iso3="AUS", group="G10", name="Australie", flag="🇦🇺",
        bank="Reserve Bank of Australia (RBA)", rateLabel="Cash Rate Target", gov="Michele Bullock", target=2.5,
        fxTicker="AUDUSD=X", teSlug="australia",
        rate=[("bis_rate", "AU")],
        cpi=[("bis_cpi", "AU", "yoy"), ("fred", "AUSCPIALLQINMEI", "index")],
        core=[],
        y2=[]
    ),
    "NZD": dict(
        iso3="NZL", group="G10", name="Nouvelle-Zélande", flag="🇳🇿",
        bank="Reserve Bank of New Zealand (RBNZ)", rateLabel="Official Cash Rate (OCR)", gov="Adrian Orr", target=2.0,
        fxTicker="NZDUSD=X", teSlug="new-zealand",
        rate=[("bis_rate", "NZ")],
        cpi=[("bis_cpi", "NZ", "yoy"), ("fred", "NZLCPIALLQINMEI", "index")],
        core=[],
        y2=[]
    ),
    "SEK": dict(
        iso3="SWE", group="G10", name="Suède", flag="🇸🇪",
        bank="Sveriges Riksbank", rateLabel="Policy Rate", gov="Erik Thedéen", target=2.0,
        fxTicker="SEK=X", teSlug="sweden",
        rate=[("bis_rate", "SE")],
        cpi=[("bis_cpi", "SE", "yoy"), ("fred", "SWECPIALLMINMEI", "index")],
        core=[("fred", "SWECPICORMINMEI", "index")],
        y2=[]
    ),
    "NOK": dict(
        iso3="NOR", group="G10", name="Norvège", flag="🇳🇴",
        bank="Norges Bank", rateLabel="Sight Deposit Rate", gov="Ida Wolden Bache", target=2.0,
        fxTicker="NOK=X", teSlug="norway",
        rate=[("bis_rate", "NO")],
        cpi=[("bis_cpi", "NO", "yoy"), ("fred", "NORCPIALLMINMEI", "index")],
        core=[("fred", "NORCPICORMINMEI", "index")],
        y2=[]
    ),
    # === EMERGING MARKETS (EM) ===
    "BRL": dict(
        iso3="BRA", group="EM", name="Brésil", flag="🇧🇷",
        bank="Banco Central do Brasil (BCB)", rateLabel="Taxa Selic Meta", gov="Gabriel Galípolo", target=3.0,
        fxTicker="BRL=X", teSlug="brazil",
        rate=[("bcb", "432"), ("bis_rate", "BR")],
        cpi=[("bcb", "13522", "yoy"), ("bis_cpi", "BR", "yoy")],
        core=[("bcb", "11427", "yoy")],
        y2=[]
    ),
    "MXN": dict(
        iso3="MEX", group="EM", name="Mexique", flag="🇲🇽",
        bank="Banco de México (Banxico)", rateLabel="Tasa Objetivo", gov="Victoria Rodríguez Ceja", target=3.0,
        fxTicker="MXN=X", teSlug="mexico",
        rate=[("bis_rate", "MX")],
        cpi=[("bis_cpi", "MX", "yoy"), ("fred", "MEXCPIALLMINMEI", "index")],
        core=[("fred", "MEXCPICORMINMEI", "index")],
        y2=[]
    ),
    "ZAR": dict(
        iso3="ZAF", group="EM", name="Afrique du Sud", flag="🇿🇦",
        bank="South African Reserve Bank (SARB)", rateLabel="Repo Rate", gov="Lesetja Kganyago", target=4.5,
        fxTicker="ZAR=X", teSlug="south-africa",
        rate=[("bis_rate", "ZA")],
        cpi=[("bis_cpi", "ZA", "yoy"), ("fred", "ZAFCPIALLMINMEI", "index")],
        core=[],
        y2=[]
    ),
    "PLN": dict(
        iso3="POL", group="EM", name="Pologne", flag="🇵🇱",
        bank="Narodowy Bank Polski (NBP)", rateLabel="Reference Rate", gov="Adam Glapiński", target=2.5,
        fxTicker="PLN=X", teSlug="poland",
        rate=[("bis_rate", "PL")],
        cpi=[("bis_cpi", "PL", "yoy"), ("fred", "POLCPIALLMINMEI", "index")],
        core=[("fred", "POLCPICORMINMEI", "index")],
        y2=[]
    ),
    "CZK": dict(
        iso3="CZE", group="EM", name="Rép. Tchèque", flag="🇨🇿",
        bank="Česká národní banka (CNB)", rateLabel="2W Repo Rate", gov="Aleš Michl", target=2.0,
        fxTicker="CZK=X", teSlug="czech-republic",
        rate=[("bis_rate", "CZ")],
        cpi=[("bis_cpi", "CZ", "yoy"), ("fred", "CZECPIALLMINMEI", "index")],
        core=[("fred", "CZECPICORMINMEI", "index")],
        y2=[]
    ),
    "HUF": dict(
        iso3="HUN", group="EM", name="Hongrie", flag="🇭🇺",
        bank="Magyar Nemzeti Bank (MNB)", rateLabel="Base Rate", gov="Mihály Varga", target=3.0,
        fxTicker="HUF=X", teSlug="hungary",
        rate=[("bis_rate", "HU")],
        cpi=[("bis_cpi", "HU", "yoy"), ("fred", "HUNCPIALLMINMEI", "index")],
        core=[("fred", "HUNCPICORMINMEI", "index")],
        y2=[]
    ),
    "INR": dict(
        iso3="IND", group="EM", name="Inde", flag="🇮🇳",
        bank="Reserve Bank of India (RBI)", rateLabel="Policy Repo Rate", gov="Sanjay Malhotra", target=4.0,
        fxTicker="INR=X", teSlug="india",
        rate=[("bis_rate", "IN")],
        cpi=[("bis_cpi", "IN", "yoy"), ("fred", "INDCPIALLMINMEI", "index")],
        core=[],
        y2=[]
    ),
    "KRW": dict(
        iso3="KOR", group="EM", name="Corée du Sud", flag="🇰🇷",
        bank="Bank of Korea (BoK)", rateLabel="Base Rate", gov="Rhee Chang-yong", target=2.0,
        fxTicker="KRW=X", teSlug="south-korea",
        rate=[("bis_rate", "KR")],
        cpi=[("bis_cpi", "KR", "yoy"), ("fred", "KORCPIALLMINMEI", "index")],
        core=[("fred", "KORCPICORMINMEI", "index")],
        y2=[]
    ),
}

# --- Utilitaires HTTP & Dates ---
def http_get(url, as_json=False, tries=3):
    for attempt in range(tries):
        try:
            headers = {"User-Agent": random.choice(USER_AGENTS), "Accept-Language": "en-US,en;q=0.9"}
            resp = requests.get(url, headers=headers, timeout=20)
            resp.raise_for_status()
            return resp.json() if as_json else resp.text
        except Exception:
            if attempt < tries - 1:
                time.sleep(1.5 * (attempt + 1))
    return None

def get_month_axis(n=N_MONTHS):
    now = datetime.now(timezone.utc)
    y, m = now.year, now.month
    months = []
    for _ in range(n):
        months.append(f"{y}-{m:02d}")
        m -= 1
        if m == 0:
            y, m = y - 1, 12
    return months[::-1]

def ym_to_int(ym):
    return int(ym[:4]) * 12 + int(ym[5:7])

def to_yoy(series, kind):
    if kind == "yoy" or not series:
        return series
    out = {}
    for ym, val in series.items():
        prev_ym = f"{int(ym[:4]) - 1}-{ym[5:7]}"
        if prev_ym in series and series[prev_ym] > 0:
            out[ym] = round((val / series[prev_ym] - 1.0) * 100.0, 2)
    return out

# --- Niveau 1 : Scraper Temps Réel (Anti-Lag) ---
def scrape_live_macro_table():
    """
    Scrape les tableaux macro récapitulatifs (Taux directeur, CPI YoY, Core CPI, Rendement 2Y)
    pour combler le retard de 1-2 mois des bases BIS/FRED.
    """
    live_data = {}
    # 1. Taux directeurs mondiaux
    html_rates = http_get("https://tradingeconomics.com/country-list/interest-rate?continent=world", tries=2)
    if html_rates:
        soup = BeautifulSoup(html_rates, "html.parser")
        for tr in soup.select("table tr"):
            cols = [c.get_text(strip=True) for c in tr.find_all("td")]
            if len(cols) >= 3:
                country = cols[0].lower()
                try:
                    val = float(re.sub(r"[^\d.-]", "", cols[1]))
                    if -2.0 <= val <= 60.0:
                        live_data.setdefault(country, {})["rate"] = val
                except ValueError:
                    pass

    # 2. Inflation CPI YoY mondiale
    html_cpi = http_get("https://tradingeconomics.com/country-list/inflation-rate?continent=world", tries=2)
    if html_cpi:
        soup = BeautifulSoup(html_cpi, "html.parser")
        for tr in soup.select("table tr"):
            cols = [c.get_text(strip=True) for c in tr.find_all("td")]
            if len(cols) >= 3:
                country = cols[0].lower()
                try:
                    val = float(re.sub(r"[^\d.-]", "", cols[1]))
                    if -10.0 <= val <= 60.0:
                        live_data.setdefault(country, {})["cpi"] = val
                except ValueError:
                    pass

    # 3. Core Inflation Rate mondiale
    html_core = http_get("https://tradingeconomics.com/country-list/core-inflation-rate?continent=world", tries=2)
    if html_core:
        soup = BeautifulSoup(html_core, "html.parser")
        for tr in soup.select("table tr"):
            cols = [c.get_text(strip=True) for c in tr.find_all("td")]
            if len(cols) >= 3:
                country = cols[0].lower()
                try:
                    val = float(re.sub(r"[^\d.-]", "", cols[1]))
                    if -10.0 <= val <= 60.0:
                        live_data.setdefault(country, {})["core"] = val
                except ValueError:
                    pass

    # 4. Rendements souverains 2 ans (2Y Government Bond Yields)
    html_2y = http_get("https://tradingeconomics.com/bonds", tries=2)
    if html_2y:
        soup = BeautifulSoup(html_2y, "html.parser")
        for tr in soup.select("table tr"):
            cols = [c.get_text(strip=True) for c in tr.find_all("td")]
            if len(cols) >= 3 and "2y" in cols[0].lower():
                country = re.sub(r"\s*2y.*", "", cols[0], flags=re.I).strip().lower()
                try:
                    val = float(re.sub(r"[^\d.-]", "", cols[1]))
                    if -2.0 <= val <= 40.0:
                        live_data.setdefault(country, {})["y2"] = val
                except ValueError:
                    pass

    return live_data

# --- Niveau 2 : Connecteurs API Officielles & Institutionnelles ---
def src_fred(sid):
    if not FRED_API_KEY:
        return {}
    start = (datetime.now(timezone.utc) - timedelta(days=2300)).strftime("%Y-%m-%d")
    url = f"https://api.stlouisfed.org/fred/series/observations?series_id={sid}&api_key={FRED_API_KEY}&file_type=json&observation_start={start}"
    data = http_get(url, as_json=True)
    if not data:
        return {}
    out = {}
    for o in data.get("observations", []):
        if o["value"] not in (".", "", None):
            try:
                out[o["date"][:7]] = float(o["value"])
            except ValueError:
                pass
    return out

def src_boc(sid):
    data = http_get(f"https://www.bankofcanada.ca/valet/observations/{sid}/json?recent=1500", as_json=True)
    if not data:
        return {}
    out = {}
    for o in data.get("observations", []):
        v = o.get(sid, {}).get("v")
        if v not in (None, ""):
            try:
                out[o["d"][:7]] = float(v)
            except ValueError:
                pass
    return out

def src_bcb(sid):
    start = (datetime.now(timezone.utc) - timedelta(days=2300)).strftime("%d/%m/%Y")
    data = http_get(f"https://api.bcb.gov.br/dados/serie/bcdata.sgs.{sid}/dados?formato=json&dataInicial={start}", as_json=True)
    if not data:
        return {}
    out = {}
    for o in data:
        try:
            _, m, y = o["data"].split("/")
            out[f"{y}-{m}"] = float(o["valor"])
        except Exception:
            pass
    return out

def src_bis_rate(cc):
    txt = http_get(f"https://stats.bis.org/api/v1/data/WS_CBPOL/M.{cc}?startPeriod=2020-01&format=csv")
    if not txt:
        return {}
    out = {}
    for row in csv.DictReader(io.StringIO(txt)):
        ym, v = (row.get("TIME_PERIOD") or "")[:7], row.get("OBS_VALUE")
        if ym and v not in (None, ""):
            try:
                out[ym] = float(v)
            except ValueError:
                pass
    return out

def src_bis_cpi(cc):
    txt = http_get(f"https://stats.bis.org/api/v1/data/WS_LONG_CPI/M.{cc}?startPeriod=2020-01&format=csv")
    if not txt:
        return {}
    groups = {}
    for row in csv.DictReader(io.StringIO(txt)):
        ym, v = (row.get("TIME_PERIOD") or "")[:7], row.get("OBS_VALUE")
        if not ym or v in (None, ""):
            continue
        key = tuple(sorted((k, val) for k, val in row.items() if not k.startswith("OBS_") and k not in ("TIME_PERIOD", "TITLE", "TITLE_TS")))
        try:
            groups.setdefault(key, {})[ym] = float(v)
        except ValueError:
            pass
    best = {}
    for ser in groups.values():
        vals = sorted(ser.values())
        if not vals:
            continue
        median = vals[len(vals) // 2]
        yoy = to_yoy(ser, "index") if abs(median) > 40 else ser
        yoy = {k: v for k, v in yoy.items() if -10 <= v <= 50}
        if yoy and (not best or max(yoy) > max(best) or (max(yoy) == max(best) and len(yoy) > len(best))):
            best = yoy
    return best

SRC_MAP = {"fred": src_fred, "boc": src_boc, "bcb": src_bcb, "bis_rate": src_bis_rate, "bis_cpi": src_bis_cpi}

# --- FX Historique & Spot (60 mois alignés) ---
def fetch_fx_series(ticker, months):
    if not ticker:
        return 1.0, 0.0, [1.0] * len(months)
    try:
        df = yf.Ticker(ticker).history(period="6y")["Close"].dropna()
        if df.empty:
            return None, None, [None] * len(months)
        conv = (lambda p: p) if ticker.endswith("USD=X") else (lambda p: 1.0 / p)
        spot = round(conv(float(df.iloc[-1])), 6)
        prev_day = round(conv(float(df.iloc[-2])), 6) if len(df) >= 2 else spot
        chg_24h = round((spot / prev_day - 1.0) * 100.0, 3) if prev_day else 0.0

        monthly = df.groupby(df.index.strftime("%Y-%m")).last()
        hist = []
        last_val = None
        for m in months:
            if m in monthly.index:
                last_val = round(conv(float(monthly[m])), 6)
            hist.append(last_val)
        return spot, chg_24h, hist
    except Exception:
        return None, None, [None] * len(months)

# --- Traitement Parallèle par Devise ---
def process_currency(cur, cfg, months, live_macro, prev_snapshot, meetings_db):
    current_ym = months[-1]
    prev_ym = months[-2]
    slug_key = cfg["teSlug"].replace("-", " ")
    live_entry = live_macro.get(slug_key, {})
    prev_c = prev_snapshot.get("currencies", {}).get(cur, {})

    # 1. Taux Directeur Nominal
    rate_series = {}
    for s_name, s_id in cfg["rate"]:
        res = SRC_MAP[s_name](s_id)
        if res:
            rate_series.update(res)
            break

    # Injection temps réel si plausible (variation <= 2.5% vs dernier connu)
    if "rate" in live_entry:
        live_r = live_entry["rate"]
        last_hist_r = rate_series[max(rate_series)] if rate_series else prev_c.get("nominalRate")
        if last_hist_r is None or abs(live_r - last_hist_r) <= 2.5:
            rate_series[current_ym] = live_r

    if not rate_series and prev_c.get("nominalRate") is not None:
        rate_series[current_ym] = prev_c["nominalRate"]

    hist_rate = []
    last_r = None
    first_r = min(rate_series) if rate_series else current_ym
    for ym in months:
        if ym in rate_series:
            last_r = round(rate_series[ym], 2)
        elif ym_to_int(ym) < ym_to_int(first_r):
            last_r = None
        hist_rate.append(last_r)

    nominal_rate = hist_rate[-1] if hist_rate[-1] is not None else prev_c.get("nominalRate")

    # 2. Headline CPI (YoY %)
    cpi_series = {}
    for s_name, s_id, kind in cfg["cpi"]:
        raw = SRC_MAP[s_name](s_id)
        yoy = to_yoy(raw, kind)
        yoy = {k: round(v, 2) for k, v in yoy.items() if -10 <= v <= 50}
        if yoy:
            cpi_series = yoy
            break

    cpi_asof = max(cpi_series) if cpi_series else prev_c.get("cpiAsOf", prev_ym)
    if "cpi" in live_entry:
        live_cpi = live_entry["cpi"]
        last_cpi = cpi_series[cpi_asof] if cpi_series else prev_c.get("headlineCpi")
        if last_cpi is None or abs(live_cpi - last_cpi) <= 2.0:
            cpi_series[prev_ym] = live_cpi
            if cpi_asof < prev_ym:
                cpi_asof = prev_ym

    hist_cpi = []
    last_c = None
    for ym in months:
        if ym in cpi_series:
            last_c = round(cpi_series[ym], 2)
        hist_cpi.append(last_c)
    headline_cpi = last_c if last_c is not None else prev_c.get("headlineCpi")

    # 3. Core CPI (YoY %)
    core_series = {}
    for s_name, s_id, kind in cfg["core"]:
        raw = SRC_MAP[s_name](s_id)
        yoy = to_yoy(raw, kind)
        yoy = {k: round(v, 2) for k, v in yoy.items() if -10 <= v <= 50}
        if yoy:
            core_series = yoy
            break

    if "core" in live_entry:
        core_series[prev_ym] = live_entry["core"]

    hist_core = []
    last_core = None
    for ym in months:
        if ym in core_series:
            last_core = round(core_series[ym], 2)
        hist_core.append(last_core)
    core_cpi = last_core if last_core is not None else prev_c.get("coreCpi")

    # 4. Rendement Souverain 2 Ans (2Y Yield)
    y2_series = {}
    for s_name, s_id in cfg["y2"]:
        raw = SRC_MAP[s_name](s_id)
        if raw:
            y2_series = {k: round(v, 2) for k, v in raw.items() if -2 <= v <= 40}
            break

    if "y2" in live_entry:
        y2_series[current_ym] = live_entry["y2"]

    hist_y2 = []
    last_y2 = None
    for ym in months:
        if ym in y2_series:
            last_y2 = round(y2_series[ym], 2)
        hist_y2.append(last_y2)
    yield_2y = last_y2 if last_y2 is not None else prev_c.get("yield2Y")

    # 5. FX Spot & Historique 60M
    spot_usd, chg_24h, hist_fx = fetch_fx_series(cfg["fxTicker"], months)
    if spot_usd is None:
        spot_usd = prev_c.get("usdRate")
        chg_24h = 0.0

    # 6. Calcul des Taux Réels & Dernière Décision
    real_rate_std = round(nominal_rate - headline_cpi, 2) if (nominal_rate is not None and headline_cpi is not None) else None
    real_rate_core = round(nominal_rate - core_cpi, 2) if (nominal_rate is not None and core_cpi is not None) else None

    decision, change_bps, change_month = "HOLD", "0 bps", None
    valid_rates = [(months[i], hist_rate[i]) for i in range(len(hist_rate)) if hist_rate[i] is not None]
    for i in range(len(valid_rates) - 1, 0, -1):
        if valid_rates[i][1] != valid_rates[i - 1][1]:
            bps = round((valid_rates[i][1] - valid_rates[i - 1][1]) * 100)
            decision = "HIKE" if bps > 0 else "CUT"
            change_bps = f"{bps:+d} bps"
            change_month = valid_rates[i][0]
            break

    # 7. Réunions Banques Centrales
    today_iso = datetime.now(timezone.utc).date().isoformat()
    m_dates = sorted(meetings_db.get(cfg["iso3"], {}).get("dates", []))
    past_m = [d for d in m_dates if d <= today_iso]
    fut_m = [d for d in m_dates if d > today_iso]

    snapshot_item = {
        "currency": cur,
        "iso3": cfg["iso3"],
        "group": cfg["group"],
        "name": cfg["name"],
        "flag": cfg["flag"],
        "bank": cfg["bank"],
        "rateLabel": cfg["rateLabel"],
        "governor": cfg["gov"],
        "target": cfg["target"],
        "nominalRate": nominal_rate,
        "headlineCpi": headline_cpi,
        "coreCpi": core_cpi,
        "realRateStd": real_rate_std,
        "realRateCore": real_rate_core,
        "yield2Y": yield_2y,
        "cpiAsOf": cpi_asof,
        "lastDecision": decision,
        "lastChange": change_bps,
        "lastChangeMonth": change_month,
        "lastMeeting": past_m[-1] if past_m else "n.d.",
        "nextMeeting": fut_m[0] if fut_m else "n.d.",
        "usdRate": spot_usd,
        "chg24h": chg_24h,
    }

    history_item = {
        "rate": hist_rate,
        "cpi": hist_cpi,
        "core": hist_core,
        "y2": hist_y2,
        "fxUsd": hist_fx,
    }

    return cur, snapshot_item, history_item

def main():
    t0 = time.time()
    months = get_month_axis(N_MONTHS)

    prev_snapshot = json.loads(SNAPSHOT_FILE.read_text(encoding="utf-8")) if SNAPSHOT_FILE.exists() else {}
    meetings_db = json.loads(MEETINGS_FILE.read_text(encoding="utf-8")) if MEETINGS_FILE.exists() else {}

    print("[1/3] Scraping temps réel des taux directeurs, CPI, Core CPI & 2Y Yields...")
    live_macro = scrape_live_macro_table()
    print(f"      -> {len(live_macro)} pays extraits du flux live.")

    print("[2/3] Collecte parallèle multi-sources sur 18 devises (G10 + EM)...")
    snapshots = {}
    histories = {}

    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = {
            pool.submit(process_currency, cur, cfg, months, live_macro, prev_snapshot, meetings_db): cur
            for cur, cfg in CURRENCIES_CONFIG.items()
        }
        for fut in as_completed(futures):
            cur = futures[fut]
            try:
                c_code, snap, hist = fut.result()
                snapshots[c_code] = snap
                histories[c_code] = hist
                print(f"      ✓ {c_code} | Nom: {snap['nominalRate']}% | CPI: {snap['headlineCpi']}% | Real: {snap['realRateStd']}% | 2Y: {snap['yield2Y']}%")
            except Exception as exc:
                print(f"      ✗ Erreur critique sur {cur}: {exc}")

    # Garde-fou institutionnel : ne jamais écraser si moins de 14 devises valides
    if "USD" not in snapshots or len(snapshots) < 14:
        print("✗ Échec de validation globale : conservation des fichiers précédents.")
        sys.exit(1)

    now_utc = datetime.now(timezone.utc)
    ordered_snapshots = {k: snapshots[k] for k in CURRENCIES_CONFIG if k in snapshots}
    ordered_histories = {k: histories[k] for k in CURRENCIES_CONFIG if k in histories}

    snapshot_payload = {
        "meta": {
            "lastUpdatedUTC": now_utc.strftime("%Y-%m-%d %H:%M UTC"),
            "timestamp": now_utc.isoformat(),
            "currencyCount": len(ordered_snapshots),
            "historyMonths": N_MONTHS,
        },
        "currencies": ordered_snapshots,
    }

    history_payload = {
        "dates": months,
        "series": ordered_histories,
    }

    SNAPSHOT_FILE.write_text(json.dumps(snapshot_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    HISTORY_FILE.write_text(json.dumps(history_payload, ensure_ascii=False), encoding="utf-8")

    print(f"[3/3] Pipeline terminé en {time.time() - t0:.2f}s ({len(ordered_snapshots)} devises publiées).")

if __name__ == "__main__":
    main()
