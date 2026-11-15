import { getDecimals } from "./quant.js";

export function renderPairHistoryChart(containerId, dates, spotArr, spreadArr, baseCur, quoteCur, spreadLabel) {
  const dec = getDecimals(quoteCur);

  const traceSpread = {
    x: dates,
    y: spreadArr,
    name: `${spreadLabel} (${baseCur} - ${quoteCur})`,
    type: "scatter",
    mode: "lines",
    fill: "tozeroy",
    fillcolor: "rgba(56, 189, 248, 0.12)",
    line: { color: "#38bdf8", width: 1.8 },
    yaxis: "y2",
    hovertemplate: `%{y:.2f}%<extra>${spreadLabel}</extra>`
  };

  const traceSpot = {
    x: dates,
    y: spotArr,
    name: `Cours ${baseCur}/${quoteCur}`,
    type: "scatter",
    mode: "lines",
    connectgaps: true,
    line: { color: "#f8fafc", width: 2.5 },
    yaxis: "y",
    hovertemplate: `%{y:.${dec}f}<extra>${baseCur}/${quoteCur}</extra>`
  };

  const layout = {
    paper_bgcolor: "transparent",
    plot_bgcolor: "transparent",
    margin: { t: 30, r: 55, b: 35, l: 55 },
    font: { family: "JetBrains Mono, monospace", color: "#94a3b8", size: 11 },
    xaxis: {
      showgrid: true,
      gridcolor: "rgba(30, 41, 59, 0.5)",
      zeroline: false
    },
    yaxis: {
      title: { text: `${baseCur}/${quoteCur}`, font: { color: "#f8fafc", size: 11 } },
      showgrid: true,
      gridcolor: "rgba(30, 41, 59, 0.5)",
      tickformat: `.${Math.min(dec, 4)}f`
    },
    yaxis2: {
      title: { text: "Spread (%)", font: { color: "#38bdf8", size: 11 } },
      overlaying: "y",
      side: "right",
      showgrid: false,
      zeroline: true,
      zerolinecolor: "rgba(148, 163, 184, 0.3)",
      ticksuffix: "%"
    },
    legend: {
      orientation: "h",
      y: 1.12,
      x: 0,
      font: { size: 11, color: "#cbd5e1" }
    },
    hovermode: "x unified",
    hoverlabel: {
      bgcolor: "#0f172a",
      bordercolor: "#334155",
      font: { family: "JetBrains Mono, monospace", size: 12, color: "#f8fafc" }
    }
  };

  Plotly.newPlot(containerId, [traceSpread, traceSpot], layout, {
    responsive: true,
    displayModeBar: false
  });
}

export function renderDrawerChart(containerId, dates, rateArr, cpiArr, coreArr) {
  const sliceIdx = Math.max(0, dates.length - 24);
  const x = dates.slice(sliceIdx);

  const traces = [
    {
      x,
      y: rateArr.slice(sliceIdx),
      name: "Taux Directeur",
      type: "scatter",
      mode: "lines",
      line: { color: "#38bdf8", width: 2.5, shape: "hv" }
    },
    {
      x,
      y: cpiArr.slice(sliceIdx),
      name: "Headline CPI",
      type: "scatter",
      mode: "lines",
      line: { color: "#fb7185", width: 2, dash: "dot" }
    }
  ];

  if (coreArr && coreArr.slice(sliceIdx).some(v => v != null)) {
    traces.push({
      x,
      y: coreArr.slice(sliceIdx),
      name: "Core CPI",
      type: "scatter",
      mode: "lines",
      line: { color: "#fbbf24", width: 1.8 }
    });
  }

  Plotly.newPlot(containerId, traces, {
    paper_bgcolor: "transparent",
    plot_bgcolor: "transparent",
    margin: { t: 25, r: 15, b: 30, l: 38 },
    font: { family: "JetBrains Mono, monospace", color: "#94a3b8", size: 10 },
    xaxis: { showgrid: false },
    yaxis: { gridcolor: "rgba(30, 41, 59, 0.5)", ticksuffix: "%" },
    legend: { orientation: "h", y: 1.18, x: 0, font: { size: 10 } },
    hovermode: "x unified"
  }, { responsive: true, displayModeBar: false });
}
