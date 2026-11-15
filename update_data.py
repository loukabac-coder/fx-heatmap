import csv, io, json, os, sys, time
from datetime import datetime, timedelta, timezone
import requests
import yfinance as yf

FRED_API_KEY = os.environ.get("FRED_API_KEY")
HEADERS = {"User-Agent": "Mozilla/5.0 (fx-heatmap-bot)"}
N_MONTHS = 24
MAX_CPI_AGE_MONTHS = 3  # au-delà, l'inflation est considérée périmée

# ---------- Config : chaque pays a une LISTE de sources (la 1re valide gagne) ----------
# rate : (source, id)      cpi : (source, id, "yoy"|"index")
C = {
 "USA": dict(name="États-Unis", cur="USD", bank="Federal Reserve (Fed)", gov="Jerome Powell", target=2.0,
   last="04 Nov 2026", next="16 Déc 2026", fx=None,
   rate=[("fred","DFEDTARU"),("bis_rate","US")], cpi=[("fred","CPIAUCSL","index"),("bis_cpi","US","yoy")]),
 "FRA": dict(name="Zone Euro", cur="EUR", bank="Banque Centrale Européenne (BCE)", gov="Christine Lagarde", target=2.0,
   last="29 Oct 2026", next="17 Déc 2026", fx="EURUSD=X",
   rate=[("fred","ECBDFR"),("bis_rate","XM")], cpi=[("bis_cpi","XM","yoy"),("fred","CP0000EZ19M086NEST","index")]),
 "GBR": dict(name="Royaume-Uni", cur="GBP", bank="Bank of England (BoE)", gov="Andrew Bailey", target=2.0,
   last="05 Nov 2026", next="17 Déc 2026", fx="GBPUSD=X",
   rate=[("bis_rate","GB")], cpi=[("bis_cpi","GB","yoy"),("fred","GBRCPIALLMINMEI","index")]),
 "CAN": dict(name="Canada", cur="CAD", bank="Bank of Canada (BoC)", gov="Tiff Macklem", target=2.0,
   last="28 Oct 2026", next="09 Déc 2026", fx="CAD=X",
   rate=[("boc","V39079"),("bis_rate","CA")], cpi=[("bis_cpi","CA","yoy"),("fred","CANCPIALLMINMEI","index")]),
 "BRA": dict(name="Brésil", cur="BRL", bank="Banco Central do Brasil (BCB)", gov="Gabriel Galípolo", target=3.0,
   last="04 Nov 2026", next="16 Déc 2026", fx="BRL=X",
   rate=[("bcb","432"),("bis_rate","BR")], cpi=[("bcb","13522","yoy"),("bis_cpi","BR","yoy")]),
 "MEX": dict(name="Mexique", cur="MXN", bank="Banco de México (Banxico)", gov="Victoria Rodríguez Ceja", target=3.0,
   last="12 Nov 2026", next="17 Déc 2026", fx="MXN=X",
   rate=[("bis_rate","MX")], cpi=[("bis_cpi","MX","yoy"),("fred","MEXCPIALLMINMEI","index")]),
 "IND": dict(name="Inde", cur="INR", bank="Reserve Bank of India (RBI)", gov="Sanjay Malhotra", target=4.0,
   last="09 Oct 2026", next="04 Déc 2026", fx="INR=X",
   rate=[("bis_rate","IN")], cpi=[("bis_cpi","IN","yoy"),("fred","INDCPIALLMINMEI","index")]),
 "CHN": dict(name="Chine", cur="CNY", bank="People's Bank of China (PBoC)", gov="Pan Gongsheng", target=3.0,
   last="20 Oct 2026", next="20 Nov 2026", fx="CNY=X",
   rate=[("bis_rate","CN")], cpi=[("bis_cpi","CN","yoy"),("fred","CHNCPIALLMINMEI","index")]),
 "JPN": dict(name="Japon", cur="JPY", bank="Bank of Japan (BoJ)", gov="Kazuo Ueda", target=2.0,
   last="30 Oct 2026", next="18 Déc 2026", fx="JPY=X",
   rate=[("bis_rate","JP")], cpi=[("bis_cpi","JP","yoy"),("fred","JPNCPIALLMINMEI","index")]),
 "AUS": dict(name="Australie", cur="AUD", bank="Reserve Bank of Australia (RBA)", gov="Michele Bullock", target=2.5,
   last="03 Nov 2026", next="08 Déc 2026", fx="AUDUSD=X",
   rate=[("bis_rate","AU")], cpi=[("bis_cpi","AU","yoy"),("fred","AUSCPIALLQINMEI","index")]),
 "RUS": dict(name="Russie", cur="RUB", bank="Bank of Russia (CBR)", gov="Elvira Nabiullina", target=4.0,
   last="23 Oct 2026", next="18 Déc 2026", fx="RUB=X",
   rate=[("bis_rate","RU")], cpi=[("bis_cpi","RU","yoy"),("fred","RUSCPIALLMINMEI","index")]),
 "CHE": dict(name="Suisse", cur="CHF", bank="Banque Nationale Suisse (BNS)", gov="Martin Schlegel", target=2.0,
   last="24 Sep 2026", next="10 Déc 2026", fx="CHF=X",
   rate=[("bis_rate","CH")], cpi=[("bis_cpi","CH","yoy"),("fred","CHECPIALLMINMEI","index")]),
}

# ---------- Utilitaires ----------
def get(url, js=False, tries=3):
    for i in range(tries):
        try:
            r = requests.get(url, timeout=25, headers=HEADERS)
            r.raise_for_status()
            return r.json() if js else r.text
        except Exception as e:
            print(f"   ! {url[:90]}… essai {i+1}/{tries}: {e}")
            time.sleep(2 * (i + 1))
    return None

def month_list(n):
    t = datetime.now(timezone.utc); y, m = t.year, t.month; out = []
    for _ in range(n):
        out.append(f"{y}-{m:02d}"); m -= 1
        if m == 0: y, m = y - 1, 12
    return out[::-1]

def mnum(ym): return int(ym[:4]) * 12 + int(ym[5:7])
def age_months(ym): return mnum(month_list(1)[0]) - mnum(ym)

# ---------- Sources (retournent {"YYYY-MM": valeur}, {} si échec) ----------
def src_fred(sid):
    start = (datetime.now(timezone.utc) - timedelta(days=1200)).strftime("%Y-%m-%d")
    j = get(f"https://api.stlouisfed.org/fred/series/observations?series_id={sid}&api_key={FRED_API_KEY}"
            f"&file_type=json&observation_start={start}", js=True)
    if not j: return {}
    obs = sorted(j.get("observations", []), key=lambda o: o["date"])
    return {o["date"][:7]: float(o["value"]) for o in obs if o["value"] not in (".", "", None)}

def src_boc(sid):
    j = get(f"https://www.bankofcanada.ca/valet/observations/{sid}/json?recent=1000", js=True)
    if not j: return {}
    out = {}
    for o in j.get("observations", []):
        v = o.get(sid, {}).get("v")
        if v not in (None, ""): out[o["d"][:7]] = float(v)
    return out

def src_bcb(sid):
    start = (datetime.now(timezone.utc) - timedelta(days=1200)).strftime("%d/%m/%Y")
    j = get(f"https://api.bcb.gov.br/dados/serie/bcdata.sgs.{sid}/dados?formato=json&dataInicial={start}", js=True)
    if not j: return {}
    out = {}
    for o in j:
        d, m, y = o["data"].split("/")
        out[f"{y}-{m}"] = float(o["valor"])
    return out

def _bis(flow, key, unit=None):
    txt = get(f"https://stats.bis.org/api/v1/data/{flow}/{key}?startPeriod=2023-06&format=csv")
    if not txt: return {}
    out = {}
    for row in csv.DictReader(io.StringIO(txt)):
        if unit and row.get("UNIT_MEASURE") not in (None, unit): continue
        ym, v = (row.get("TIME_PERIOD") or "")[:7], row.get("OBS_VALUE")
        if ym and v not in (None, ""): out[ym] = float(v)
    return out

def src_bis_rate(cc): return _bis("WS_CBPOL", f"M.{cc}")
def src_bis_cpi(cc):  return _bis("WS_LONG_CPI", f"M.{cc}", unit="628")  # 628 = variation annuelle en %

SRC = {"fred": src_fred, "boc": src_boc, "bcb": src_bcb, "bis_rate": src_bis_rate, "bis_cpi": src_bis_cpi}

def to_yoy(series, kind):
    if kind == "yoy": return series
    out = {}
    for ym, v in series.items():
        prev = f"{int(ym[:4]) - 1}-{ym[5:7]}"
        if prev in series and series[prev]: out[ym] = round((v / series[prev] - 1) * 100, 2)
    return out

# ---------- FX réel (plus de courbe inventée) ----------
def get_fx(ticker, months):
    if not ticker: return 1.0, {"m1": "0.0%", "m6": "0.0%", "y1": "0.0%"}, [1.0] * len(months)
    try:
        d = yf.Ticker(ticker).history(period="3y")["Close"].dropna()
        conv = (lambda p: p) if ticker.endswith("USD=X") else (lambda p: 1.0 / p)
        spot = conv(float(d.iloc[-1]))
        def ago(days):
            s = d.loc[:d.index[-1] - timedelta(days=days)]
            return conv(float(s.iloc[-1])) if len(s) else None
        perf = lambda p: f"{(spot / p - 1) * 100:+.1f}%" if p else "n.d."
        monthly = d.groupby(d.index.strftime("%Y-%m")).last()
        hist = [round(conv(float(monthly[m])), 5) if m in monthly.index else None for m in months]
        return round(spot, 5), {"m1": perf(ago(30)), "m6": perf(ago(182)), "y1": perf(ago(365))}, hist
    except Exception as e:
        print(f"   ! FX {ticker}: {e}")
        return None, {"m1": "n.d.", "m6": "n.d.", "y1": "n.d."}, [None] * len(months)

# ---------- Main ----------
def main():
    months = month_list(N_MONTHS)
    out = {"last_updated": datetime.now(timezone.utc).strftime("%d %b %Y - %H:%M UTC"), "dates": months, "countries": {}}

    for iso, c in C.items():
        print(f"== {iso}")
        warn = []

        # Taux directeur : 1re source qui répond
        rate_map, rate_src = {}, None
        for s, sid in c["rate"]:
            rate_map = SRC[s](sid)
            if rate_map: rate_src = s; break
        if not rate_map:
            print(f"   ✗ {iso} ignoré : aucun taux récupéré"); continue
        first = min(rate_map); last_known = None; hist_rate = []
        for ym in months:
            if ym in rate_map: last_known = round(rate_map[ym], 2)
            elif mnum(ym) < mnum(first): last_known = None
            hist_rate.append(last_known)
        rate_asof = max(rate_map)
        if age_months(rate_asof) > 3: warn.append(f"taux : dernière donnée {rate_asof}")

        # Inflation : 1re source FRAÎCHE, sinon la moins périmée (signalée)
        best = None
        for s, sid, kind in c["cpi"]:
            yoy = to_yoy(SRC[s](sid), kind)
            if not yoy: continue
            asof = max(yoy)
            if best is None or asof > best[1]: best = (yoy, asof, s)
            if age_months(asof) <= MAX_CPI_AGE_MONTHS: break
        if best:
            yoy, inf_asof, inf_src = best
            hist_inf = [round(yoy[m], 2) if m in yoy else None for m in months]  # PAS de remplissage
            if age_months(inf_asof) > MAX_CPI_AGE_MONTHS: warn.append(f"inflation périmée (dernière : {inf_asof})")
            tail = [v for v in hist_inf if v is not None][-6:]
            if len(tail) == 6 and len(set(tail)) == 1: warn.append("inflation suspecte (6 valeurs identiques)")
        else:
            hist_inf, inf_asof, inf_src = [None] * len(months), None, None
            warn.append("inflation indisponible")
        known = [v for v in hist_inf if v is not None]
        inflation = known[-1] if known else None

        # Dernière décision RÉELLE (dernier changement dans l'historique)
        decision, change, change_m = "HOLD", "0 bps", None
        for i in range(len(hist_rate) - 1, 0, -1):
            if hist_rate[i] is not None and hist_rate[i - 1] is not None and hist_rate[i] != hist_rate[i - 1]:
                bps = round((hist_rate[i] - hist_rate[i - 1]) * 100)
                decision = "HIKE" if bps > 0 else "CUT"
                change = f"{bps:+d} bps"
                change_m = months[i]
                break

        spot, perf, hist_fx = get_fx(c["fx"], months)
        if warn: print("   ⚠", " | ".join(warn))

        out["countries"][iso] = {
            "iso3": iso, "name": c["name"], "currency": c["cur"], "bank": c["bank"], "governor": c["gov"],
            "nominalRate": hist_rate[-1], "inflation": inflation, "target": c["target"],
            "lastDecision": decision, "lastChange": change, "lastChangeMonth": change_m,
            "lastMeeting": c["last"], "nextMeeting": c["next"],
            "fxPerf": perf, "usdRate": spot, "histRate": hist_rate, "histInf": hist_inf, "histFx": hist_fx,
            "rateAsOf": rate_asof, "inflationAsOf": inf_asof, "sources": {"rate": rate_src, "cpi": inf_src},
            "warnings": warn,
        }

    # Garde-fou : ne jamais écraser un bon data.json avec un mauvais
    if "USA" not in out["countries"] or len(out["countries"]) < 10:
        print("✗ Trop de pays manquants : data.json NON écrasé."); sys.exit(1)

    with open("data.json", "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    bad = [k for k, v in out["countries"].items() if v["warnings"]]
    print(f"✓ data.json écrit ({len(out['countries'])} pays). Pays avec avertissements : {bad or 'aucun'}")

if __name__ == "__main__":
    main()
