// public/js/quant.js

// Ordre hiérarchique institutionnel des devises (convention de cotation prioritaire)
export const FX_PRIORITY = [
  "EUR", "GBP", "AUD", "NZD", "USD", "CAD", "CHF",
  "NOK", "SEK", "PLN", "CZK", "HUF", "ZAR", "MXN", "BRL", "CNY", "INR", "KRW", "JPY"
];

/**
 * Retourne le nombre de décimales standard selon la devise cotée
 */
export function getDecimals(quoteCur) {
  if (["JPY", "HUF", "KRW"].includes(quoteCur)) return 3;
  if (["INR", "MXN", "ZAR", "CZK", "SEK", "NOK"].includes(quoteCur)) return 4;
  return 5;
}

/**
 * Calcule le taux croisé exact Base / Cotée à partir des pivots USD
 * usdRate = Combien de USD vaut 1 unité de devise
 */
export function computeCrossRate(baseObj, quoteObj) {
  if (!baseObj?.usdRate || !quoteObj?.usdRate) return null;
  if (baseObj.currency === quoteObj.currency) return 1.0;
  return baseObj.usdRate / quoteObj.usdRate;
}

/**
 * Calcule la variation 24h d'une paire croisée à partir des variations vs USD
 */
export function computeCross24hChange(baseObj, quoteObj) {
  if (baseObj.currency === quoteObj.currency) return 0;
  const rBase = 1 + (baseObj.chg24h || 0) / 100;
  const rQuote = 1 + (quoteObj.chg24h || 0) / 100;
  return +((rBase / rQuote - 1) * 100).toFixed(3);
}

/**
 * Régression linéaire OLS (y = alpha + beta * x) et calcul du Z-Score des résidus sur 24 mois
 * y = Spot croisé, x = Spread de taux réels
 */
export function computeZScore24M(spotSeries, spreadSeries) {
  const pairs = [];
  const len = Math.min(spotSeries.length, spreadSeries.length);
  // On prend les 24 derniers mois valides
  for (let i = Math.max(0, len - 24); i < len; i++) {
    if (spotSeries[i] != null && spreadSeries[i] != null) {
      pairs.push({ x: spreadSeries[i], y: spotSeries[i] });
    }
  }
  if (pairs.length < 10) return { zScore: null, r2: null, signal: "Historique insuffisant" };

  const n = pairs.length;
  const meanX = pairs.reduce((s, p) => s + p.x, 0) / n;
  const meanY = pairs.reduce((s, p) => s + p.y, 0) / n;

  let num = 0, denX = 0, denY = 0;
  for (const p of pairs) {
    const dx = p.x - meanX;
    const dy = p.y - meanY;
    num += dx * dy;
    denX += dx * dx;
    denY += dy * dy;
  }

  const beta = denX > 0 ? num / denX : 0;
  const alpha = meanY - beta * meanX;
  const r2 = (denX > 0 && denY > 0) ? (num * num) / (denX * denY) : 0;

  const residuals = pairs.map(p => p.y - (alpha + beta * p.x));
  const stdErr = Math.sqrt(residuals.reduce((s, e) => s + e * e, 0) / (n - 2 || 1));
  const latestResidual = residuals[residuals.length - 1];

  if (stdErr === 0) return { zScore: 0, r2: +r2.toFixed(2), signal: "Équilibre parfait" };

  const z = +(latestResidual / stdErr).toFixed(2);
  let signal = "Valorisation neutre (Fair Value)";
  if (z >= 1.5) signal = "Paire surévaluée vs taux réels";
  else if (z >= 0.75) signal = "Légère prime spot vs taux";
  else if (z <= -1.5) signal = "Paire sous-évaluée vs taux réels";
  else if (z <= -0.75) signal = "Légère décote spot vs taux";

  return { zScore: z, r2: +r2.toFixed(2), signal };
}

/**
 * Génère une couleur HSL institutionnelle auto-calibrée selon le min/max du périmètre actif
 */
export function getHeatmapStyle(value, minVal, maxVal, metric) {
  if (value == null) {
    return { bg: "rgba(15, 23, 42, 0.8)", border: "rgba(51, 65, 85, 0.6)", text: "#94a3b8" };
  }
  const span = maxVal - minVal || 1;
  const norm = Math.max(0, Math.min(1, (value - minVal) / span));

  // Pour l'inflation : élevé = rouge/ambre (risque), bas = bleu/vert
  if (metric === "headlineCpi" || metric === "coreCpi") {
    const hue = Math.round(210 - norm * 205); // 210 (bleu) -> 5 (rouge)
    return {
      bg: `hsla(${hue}, 65%, 16%, 0.85)`,
      border: `hsla(${hue}, 75%, 45%, 0.45)`,
      text: `hsl(${hue}, 85%, 72%)`
    };
  }

  // Pour les taux (Réel, Nominal, 2Y) : négatif = rouge/corail, positif élevé = émeraude/cyan
  if (value < 0) {
    const intensity = Math.min(1, Math.abs(value) / 3.5);
    return {
      bg: `hsla(350, 65%, ${18 + intensity * 8}%, 0.85)`,
      border: `hsla(350, 75%, 50%, 0.45)`,
      text: `#fda4af`
    };
  }

  const hue = Math.round(205 - norm * 45); // 205 (sky) -> 160 (emerald)
  return {
    bg: `hsla(${hue}, 65%, ${14 + norm * 10}%, 0.9)`,
    border: `hsla(${hue}, 75%, 45%, 0.5)`,
    text: `hsl(${hue}, 85%, 72%)`
  };
}
