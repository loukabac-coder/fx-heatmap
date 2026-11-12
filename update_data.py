import json
import os
from datetime import datetime
import requests
import yfinance as yf

FRED_API_KEY = os.environ.get("FRED_API_KEY")

# Mapping des séries FRED officielles (Taux directeurs & Inflation YoY ou CPI)
COUNTRIES_CONFIG = {
    "USA": {
        "name": "États-Unis", "currency": "USD", "bank": "Federal Reserve (Fed)",
        "governor": "Jerome Powell", "target": 2.00,
        "lastMeeting": "04 Nov 2026", "nextMeeting": "16 Déc 2026",
        "rate_series": "DFEDTARU", "cpi_series": "CPIAUCSL", "yf_ticker": None
    },
    "FRA": {
        "name": "Zone Euro", "currency": "EUR", "bank": "Banque Centrale Européenne (BCE)",
        "governor": "Christine Lagarde", "target": 2.00,
        "lastMeeting": "29 Oct 2026", "nextMeeting": "17 Déc 2026",
        "rate_series": "ECBDFR", "cpi_series": "CP0000EZ19M086NEST", "yf_ticker": "EURUSD=X"
    },
    "GBR": {
        "name": "Royaume-Uni", "currency": "GBP", "bank": "Bank of England (BoE)",
        "governor": "Andrew Bailey", "target": 2.00,
        "lastMeeting": "05 Nov 2026", "nextMeeting": "17 Déc 2026",
        "rate_series": "BOERUKM", "cpi_series": "GBRCPIALLMINMEI", "yf_ticker": "GBPUSD=X"
    },
    "JPN": {
        "name": "Japon", "currency": "JPY", "bank": "Bank of Japan (BoJ)",
        "governor": "Kazuo Ueda", "target": 2.00,
        "lastMeeting": "30 Oct 2026", "nextMeeting": "18 Déc 2026",
        "rate_series": "IRSTCI01JPM156N", "cpi_series": "JPNCPIALLMINMEI", "yf_ticker": "JPY=X"
    },
    "CHE": {
        "name": "Suisse", "currency": "CHF", "bank": "Banque Nationale Suisse (BNS)",
        "governor": "Martin Schlegel", "target": 2.00,
        "lastMeeting": "24 Sep 2026", "nextMeeting": "10 Déc 2026",
        "rate_series": "IRSTCI01CHM156N", "cpi_series": "CHECPIALLMINMEI", "yf_ticker": "CHF=X"
    },
    "CAN": {
        "name": "Canada", "currency": "CAD", "bank": "Bank of Canada (BoC)",
        "governor": "Tiff Macklem", "target": 2.00,
        "lastMeeting": "28 Oct 2026", "nextMeeting": "09 Déc 2026",
        "rate_series": "IRSTCI01CAM156N", "cpi_series": "CANCPIALLMINMEI", "yf_ticker": "CAD=X"
    },
    "AUS": {
        "name": "Australie", "currency": "AUD", "bank": "Reserve Bank of Australia (RBA)",
        "governor": "Michele Bullock", "target": 2.50,
        "lastMeeting": "03 Nov 2026", "nextMeeting": "08 Déc 2026",
        "rate_series": "IRSTCI01AUM156N", "cpi_series": "AUSCPIALLQINMEI", "yf_ticker": "AUDUSD=X"
    },
    "BRA": {
        "name": "Brésil", "currency": "BRL", "bank": "Banco Central do Brasil (BCB)",
        "governor": "Gabriel Galípolo", "target": 3.00,
        "lastMeeting": "04 Nov 2026", "nextMeeting": "16 Déc 2026",
        "rate_series": "IRSTCI01BRM156N", "cpi_series": "BRACPIALLMINMEI", "yf_ticker": "BRL=X"
    },
    "MEX": {
        "name": "Mexique", "currency": "MXN", "bank": "Banco de México (Banxico)",
        "governor": "Victoria Rodríguez Ceja", "target": 3.00,
        "lastMeeting": "12 Nov 2026", "nextMeeting": "17 Déc 2026",
        "rate_series": "IRSTCI01MXM156N", "cpi_series": "MEXCPIALLMINMEI", "yf_ticker": "MXN=X"
    },
    "CHN": {
        "name": "Chine", "currency": "CNY", "bank": "People's Bank of China (PBoC)",
        "governor": "Pan Gongsheng", "target": 3.00,
        "lastMeeting": "20 Oct 2026", "nextMeeting": "20 Nov 2026",
        "rate_series": "IRSTCI01CNM156N", "cpi_series": "CHNCPIALLMINMEI", "yf_ticker": "CNY=X"
    },
    "IND": {
        "name": "Inde", "currency": "INR", "bank": "Reserve Bank of India (RBI)",
        "governor": "Sanjay Malhotra", "target": 4.00,
        "lastMeeting": "09 Oct 2026", "nextMeeting": "04 Déc 2026",
        "rate_series": "IRSTCI01INM156N", "cpi_series": "INDCPIALLMINMEI", "yf_ticker": "INR=X"
    }
}

def fetch_fred_series(series_id, limit=48):
    url = f"https://api.stlouisfed.org/fred/series/observations?series_id={series_id}&api_key={FRED_API_KEY}&file_type=json&sort_order=desc&limit={limit}"
    r = requests.get(url, timeout=15).json()
    obs = [o for o in r.get("observations", []) if o["value"] != "."]
    obs.reverse()
    return obs

def get_fx_metrics(ticker):
    if not ticker:
        return 1.0, {"m1": "0.0%", "m6": "0.0%", "y1": "0.0%"}
    try:
        hist = yf.Ticker(ticker).history(period="1y")["Close"].dropna()
        current = float(hist.iloc[-1])
        # Si ticker est XXX=X (ex: JPY=X = USD/JPY), on inverse pour avoir valeur de 1 devise en USD
        invert = not ticker.endswith("USD=X")
        spot_usd = (1.0 / current) if invert else current

        def calc_perf(days_ago):
            idx = max(0, len(hist) - days_ago)
            past = float(hist.iloc[idx])
            past_usd = (1.0 / past) if invert else past
            pct = ((spot_usd - past_usd) / past_usd) * 100
            return f"{pct:+.1f}%"

        return round(spot_usd, 5), {
            "m1": calc_perf(22),
            "m6": calc_perf(126),
            "y1": calc_perf(250)
        }
    except Exception:
        return 1.0, {"m1": "N/A", "m6": "N/A", "y1": "N/A"}

def main():
    output = {
        "last_updated": datetime.utcnow().strftime("%d %b %Y - %H:%M UTC"),
        "dates": [],
        "countries": {}
    }

    for iso, cfg in COUNTRIES_CONFIG.items():
        print(f"Fetching {iso}...")
        rates_obs = fetch_fred_series(cfg["rate_series"], limit=36)
        cpi_obs = fetch_fred_series(cfg["cpi_series"], limit=48)

        # Calcul de l'inflation annuelle (YoY %) à partir de l'indice CPI
        yoy_inf = []
        dates_list = []
        for i in range(12, len(cpi_obs)):
            curr_cpi = float(cpi_obs[i]["value"])
            prev_cpi = float(cpi_obs[i - 12]["value"])
            inf_val = round(((curr_cpi - prev_cpi) / prev_cpi) * 100, 2)
            yoy_inf.append(inf_val)
            dates_list.append(cpi_obs[i]["date"][:7])

        # Alignement des 18 derniers points (3 ans bimestriels ou 18 derniers mois)
        n_points = min(18, len(yoy_inf), len(rates_obs))
        hist_inf = yoy_inf[-n_points:]
        hist_rate = [round(float(x["value"]), 2) for x in rates_obs[-n_points:]]
        if not output["dates"]:
            output["dates"] = dates_list[-n_points:]

        nom_rate = hist_rate[-1]
        prev_rate = hist_rate[-2] if len(hist_rate) > 1 else nom_rate
        diff_bps = round((nom_rate - prev_rate) * 100)

        if diff_bps > 0:
            decision, change_str = "HIKE", f"+{diff_bps} bps"
        elif diff_bps < 0:
            decision, change_str = "CUT", f"{diff_bps} bps"
        else:
            decision, change_str = "HOLD", "0 bps"

        spot_usd, fx_perf = get_fx_metrics(cfg["yf_ticker"])

        output["countries"][iso] = {
            "iso3": iso,
            "name": cfg["name"],
            "currency": cfg["currency"],
            "bank": cfg["bank"],
            "governor": cfg["governor"],
            "nominalRate": nom_rate,
            "inflation": hist_inf[-1],
            "target": cfg["target"],
            "lastDecision": decision,
            "lastChange": change_str,
            "lastMeeting": cfg["lastMeeting"],
            "nextMeeting": cfg["nextMeeting"],
            "fxPerf": fx_perf,
            "usdRate": spot_usd,
            "histRate": hist_rate,
            "histInf": hist_inf
        }

    with open("data.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print("data.json généré avec succès !")

if __name__ == "__main__":
    main()
