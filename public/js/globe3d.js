// public/js/globe3d.js
// Globe 3D WebGL interactif avec polygones pays, Zone Euro unifiée et balises capitales cliquables

const COUNTRY_COORDS = {
  USD: { lat: 38.9, lng: -77.0, camLat: 38, camLng: -95 },
  EUR: { lat: 50.1, lng: 8.7,   camLat: 48, camLng: 10 },
  JPY: { lat: 35.7, lng: 139.7, camLat: 36, camLng: 138 },
  GBP: { lat: 51.5, lng: -0.1,  camLat: 53, camLng: -2 },
  CHF: { lat: 46.9, lng: 7.4,   camLat: 47, camLng: 8 },
  CAD: { lat: 45.4, lng: -75.7, camLat: 54, camLng: -102 },
  AUD: { lat: -35.3, lng: 149.1, camLat: -26, camLng: 135 },
  NZD: { lat: -41.3, lng: 174.8, camLat: -41, camLng: 173 },
  SEK: { lat: 59.3, lng: 18.1,  camLat: 61, camLng: 16 },
  NOK: { lat: 59.9, lng: 10.7,  camLat: 62, camLng: 10 },
  BRL: { lat: -15.8, lng: -47.9, camLat: -14, camLng: -52 },
  MXN: { lat: 19.4, lng: -99.1, camLat: 23, camLng: -102 },
  ZAR: { lat: -25.7, lng: 28.2, camLat: -29, camLng: 25 },
  PLN: { lat: 52.2, lng: 21.0,  camLat: 52, camLng: 19 },
  CZK: { lat: 50.1, lng: 14.4,  camLat: 50, camLng: 15 },
  HUF: { lat: 47.5, lng: 19.0,  camLat: 47, camLng: 19 },
  INR: { lat: 28.6, lng: 77.2,  camLat: 22, camLng: 79 },
  KRW: { lat: 37.6, lng: 127.0, camLat: 36, camLng: 128 }
};

const EUROZONE_ISO3 = new Set([
  "FRA", "DEU", "ITA", "ESP", "NLD", "BEL", "PRT", "AUT", "FIN", "IRL",
  "GRC", "LUX", "SVK", "SVN", "EST", "LVA", "LTU", "CYP", "MLT", "HRV"
]);

let globeInstance = null;
let worldGeoJson = null;
let isSpinning = true;

function getColorForValue(val, minVal, maxVal, metric) {
  if (val == null) return "rgba(30, 41, 59, 0.45)";
  const span = maxVal - minVal || 1;
  const norm = Math.max(0, Math.min(1, (val - minVal) / span));

  if (metric === "headlineCpi" || metric === "inflationGap") {
    if (norm < 0.35) return "rgba(56, 189, 248, 0.78)";
    if (norm < 0.70) return "rgba(245, 158, 11, 0.82)";
    return "rgba(244, 63, 94, 0.85)";
  }

  if (val < 0) return "rgba(244, 63, 94, 0.82)";
  if (norm < 0.35) return "rgba(56, 189, 248, 0.78)";
  if (norm < 0.70) return "rgba(14, 165, 233, 0.85)";
  return "rgba(16, 185, 129, 0.88)";
}

export async function initOrUpdateGlobe(containerId, currencies, metric, onSelectCurrency) {
  const container = document.getElementById(containerId);
  if (!container || typeof Globe === "undefined") return;

  // Charger le GeoJSON mondial léger (1 seule fois)
  if (!worldGeoJson) {
    try {
      const res = await fetch("https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/ne_110m_admin_0_countries.geojson");
      const raw = await res.json();
      worldGeoJson = raw.features.filter(f => f.properties.ISO_A3 !== "ATA"); // Sans l'Antarctique pour l'esthétique
    } catch (e) {
      console.error("Erreur chargement GeoJSON:", e);
      return;
    }
  }

  // Index ISO3 -> Objet devise
  const isoToCur = {};
  Object.values(currencies).forEach(c => {
    isoToCur[c.iso3] = c;
    if (c.currency === "EUR") {
      EUROZONE_ISO3.forEach(iso => { isoToCur[iso] = c; });
    }
  });

  const getMetricVal = (c) => {
    if (!c) return null;
    if (metric === "realRate") return c.realRateStd;
    if (metric === "inflationGap") {
      return c.headlineCpi != null && c.target != null ? +(c.headlineCpi - c.target).toFixed(2) : null;
    }
    return c[metric];
  };

  const vals = Object.values(currencies).map(getMetricVal).filter(v => v != null);
  const minVal = vals.length ? Math.min(...vals) : -1;
  const maxVal = vals.length ? Math.max(...vals) : 6;

  // Initialisation du Globe WebGL
  if (!globeInstance) {
    globeInstance = Globe()(container)
      .backgroundColor("rgba(0,0,0,0)")
      .globeImageUrl("https://unpkg.com/three-globe/example/img/earth-dark.jpg")
      .bumpImageUrl("https://unpkg.com/three-globe/example/img/earth-topology.png")
      .showAtmosphere(true)
      .atmosphereColor("#38bdf8")
      .atmosphereAltitude(0.18)
      .polygonSideColor(() => "rgba(15, 23, 42, 0.6)")
      .polygonStrokeColor(() => "rgba(148, 163, 184, 0.25)")
      .polygonsTransitionDuration(350);

    // Contrôles fluides (Rotation auto + zoom)
    const controls = globeInstance.controls();
    controls.autoRotate = true;
    controls.autoRotateSpeed = 0.45;
    controls.enableDamping = true;
    controls.dampingFactor = 0.08;
    controls.minDistance = 135;
    controls.maxDistance = 420;

    // Arrêter la rotation auto dès que l'utilisateur touche le globe
    controls.addEventListener("start", () => {
      if (isSpinning) {
        controls.autoRotate = false;
      }
    });

    // Vue initiale centrée sur l'Atlantique / Europe
    globeInstance.pointOfView({ lat: 32, lng: 10, altitude: 2.05 }, 0);

    // Responsive resize
    window.addEventListener("resize", () => {
      if (globeInstance && container.clientWidth > 0) {
        globeInstance.width(container.clientWidth);
        globeInstance.height(container.clientHeight);
      }
    });
  }

  // Mise à jour des polygones pays
  globeInstance
    .width(container.clientWidth)
    .height(container.clientHeight)
    .polygonsData(worldGeoJson)
    .polygonAltitude(feat => {
      const iso = feat.properties.ADM0_A3 || feat.properties.ISO_A3;
      return isoToCur[iso] ? 0.025 : 0.006;
    })
    .polygonCapColor(feat => {
      const iso = feat.properties.ADM0_A3 || feat.properties.ISO_A3;
      const c = isoToCur[iso];
      return getColorForValue(getMetricVal(c), minVal, maxVal, metric);
    })
    .polygonLabel(feat => {
      const iso = feat.properties.ADM0_A3 || feat.properties.ISO_A3;
      const c = isoToCur[iso];
      if (!c) {
        return `<div style="background:#0b111e;border:1px solid #334155;padding:6px 10px;border-radius:8px;font-family:Inter,sans-serif;font-size:11px;color:#94a3b8;">
          ${feat.properties.NAME} (Hors périmètre)
        </div>`;
      }
      const val = getMetricVal(c);
      const valStr = val != null ? `${val > 0 && metric === "realRate" ? "+" : ""}${val.toFixed(2)}%` : "n.d.";
      return `
        <div style="background:rgba(11,17,30,0.95);border:1px solid #38bdf8;padding:10px 12px;border-radius:10px;font-family:'JetBrains Mono',monospace;font-size:11px;color:#f8fafc;box-shadow:0 10px 25px rgba(0,0,0,0.7);">
          <div style="font-weight:700;font-size:13px;margin-bottom:4px;">${c.flag} ${c.name} (${c.currency})</div>
          <div style="color:#94a3b8;font-family:Inter,sans-serif;margin-bottom:6px;">${c.bank}</div>
          <div>Taux Réel : <strong style="color:#38bdf8;">${c.realRateStd != null ? (c.realRateStd > 0 ? "+" : "") + c.realRateStd.toFixed(2) + "%" : "n.d."}</strong></div>
          <div>Nominal : <strong>${c.nominalRate}%</strong> • CPI : <strong>${c.headlineCpi}%</strong></div>
          <div style="margin-top:4px;color:#34d399;">Dernier mouv. : ${c.lastChange} (${valStr})</div>
          <div style="margin-top:5px;font-size:10px;color:#38bdf8;">👆 Cliquer pour ouvrir la fiche</div>
        </div>
      `;
    })
    .onPolygonClick(feat => {
      const iso = feat.properties.ADM0_A3 || feat.properties.ISO_A3;
      const c = isoToCur[iso];
      if (c && onSelectCurrency) onSelectCurrency(c.currency);
    });

  // Balises HTML lumineuses sur chaque devise (permet de cliquer facilement sur CHF, KRW, CZK, etc.)
  const markersData = Object.values(currencies)
    .filter(c => COUNTRY_COORDS[c.currency])
    .map(c => ({
      ...c,
      lat: COUNTRY_COORDS[c.currency].lat,
      lng: COUNTRY_COORDS[c.currency].lng,
      displayVal: getMetricVal(c)
    }));

  globeInstance
    .htmlElementsData(markersData)
    .htmlElement(d => {
      const el = document.createElement("div");
      const valText = d.displayVal != null ? `${d.displayVal > 0 && metric === "realRate" ? "+" : ""}${d.displayVal.toFixed(1)}%` : "";
      el.innerHTML = `
        <div style="
          transform: translate(-50%, -50%);
          background: rgba(9, 14, 26, 0.88);
          border: 1px solid rgba(56, 189, 248, 0.7);
          color: #ffffff;
          padding: 2px 6px;
          border-radius: 6px;
          font-family: 'JetBrains Mono', monospace;
          font-size: 10px;
          font-weight: 700;
          white-space: nowrap;
          cursor: pointer;
          box-shadow: 0 0 10px rgba(56, 189, 248, 0.35);
          pointer-events: auto;
        ">
          ${d.flag} ${d.currency} <span style="color:#38bdf8;">${valText}</span>
        </div>
      `;
      el.onclick = () => onSelectCurrency && onSelectCurrency(d.currency);
      return el;
    });
}

export function focusGlobeRegion(region) {
  if (!globeInstance) return;
  const views = {
    world:    { lat: 25,  lng: 12,  altitude: 2.15 },
    europe:   { lat: 50,  lng: 12,  altitude: 1.05 },
    americas: { lat: 18,  lng: -82, altitude: 1.45 },
    asia:     { lat: 12,  lng: 125, altitude: 1.55 }
  };
  const target = views[region] || views.world;
  globeInstance.pointOfView(target, 900);
}

export function focusGlobeCurrency(cur) {
  if (!globeInstance || !COUNTRY_COORDS[cur]) return;
  const { camLat, camLng } = COUNTRY_COORDS[cur];
  globeInstance.pointOfView({ lat: camLat, lng: camLng, altitude: 1.15 }, 800);
}

export function toggleGlobeSpin() {
  if (!globeInstance) return false;
  isSpinning = !isSpinning;
  globeInstance.controls().autoRotate = isSpinning;
  return isSpinning;
}
