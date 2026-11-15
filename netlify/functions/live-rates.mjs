// netlify/functions/live-rates.mjs
const CURRENCIES = [
  "EUR", "JPY", "GBP", "CHF", "CAD", "AUD", "NZD", "SEK", "NOK",
  "BRL", "MXN", "ZAR", "PLN", "CZK", "HUF", "INR", "KRW"
];

export default async (req) => {
  try {
    // Source 1 : Open ER-API (Rapide, gratuit, sans clé, couvre 160+ devises)
    const res = await fetch("https://open.er-api.com/v6/latest/USD", {
      headers: { "User-Agent": "FX-Macro-Terminal/2.0" }
    });

    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();

    if (data.result !== "success" || !data.rates) {
      throw new Error("Invalid payload from FX provider");
    }

    // Normalisation : on stocke "Combien de USD vaut 1 unité de devise" (convention uniforme)
    const usdPerUnit = { USD: 1.0 };
    for (const cur of CURRENCIES) {
      const unitsPerUsd = data.rates[cur];
      if (unitsPerUsd && unitsPerUsd > 0) {
        usdPerUnit[cur] = +(1.0 / unitsPerUsd).toFixed(6);
      }
    }

    return new Response(
      JSON.stringify({
        status: "live",
        timestamp: new Date().toISOString(),
        providerTime: data.time_last_update_utc,
        rates: usdPerUnit
      }),
      {
        status: 200,
        headers: {
          "Content-Type": "application/json",
          "Cache-Control": "public, max-age=60, s-maxage=300, stale-while-revalidate=600",
          "Access-Control-Allow-Origin": "*"
        }
      }
    );
  } catch (err) {
    return new Response(
      JSON.stringify({ status: "fallback", error: err.message }),
      {
        status: 502,
        headers: {
          "Content-Type": "application/json",
          "Cache-Control": "no-store"
        }
      }
    );
  }
};
