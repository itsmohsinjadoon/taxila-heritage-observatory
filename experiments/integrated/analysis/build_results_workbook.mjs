import fs from "node:fs/promises";
import path from "node:path";
import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const [baseDir, outputDir] = process.argv.slice(2);
if (!baseDir || !outputDir) {
  throw new Error("Usage: node build_results_workbook.mjs <analysis-dir> <output-dir>");
}

const tableDir = path.join(baseDir, "derived", "tables");
await fs.mkdir(outputDir, { recursive: true });
await fs.mkdir(path.join(outputDir, "workbook_previews"), { recursive: true });

function parseCsv(text) {
  const rows = [];
  let row = [];
  let value = "";
  let quoted = false;
  for (let i = 0; i < text.length; i += 1) {
    const ch = text[i];
    if (quoted) {
      if (ch === '"' && text[i + 1] === '"') {
        value += '"';
        i += 1;
      } else if (ch === '"') {
        quoted = false;
      } else {
        value += ch;
      }
    } else if (ch === '"') {
      quoted = true;
    } else if (ch === ",") {
      row.push(value);
      value = "";
    } else if (ch === "\n") {
      row.push(value.replace(/\r$/, ""));
      rows.push(row);
      row = [];
      value = "";
    } else {
      value += ch;
    }
  }
  if (value.length || row.length) {
    row.push(value.replace(/\r$/, ""));
    rows.push(row);
  }
  return rows.filter((r) => r.some((v) => v !== ""));
}

function coerce(value) {
  if (value === "") return null;
  if (/^-?\d+(\.\d+)?([eE][+-]?\d+)?$/.test(value)) return Number(value);
  return value;
}

async function readCsv(fileName) {
  const rows = parseCsv(await fs.readFile(path.join(tableDir, fileName), "utf8"));
  return rows.map((row, index) => (index === 0 ? row : row.map(coerce)));
}

const wb = Workbook.create();
const theme = {
  navy: "#17324D",
  teal: "#0F766E",
  blue: "#2F6B8A",
  gold: "#D9A441",
  pale: "#EDF4F7",
  light: "#F5F7F9",
  ink: "#1F2937",
  muted: "#5B6573",
  red: "#B43C3C",
  white: "#FFFFFF",
  border: "#D3DAE2",
};

function colName(number) {
  let n = number;
  let out = "";
  while (n > 0) {
    const rem = (n - 1) % 26;
    out = String.fromCharCode(65 + rem) + out;
    n = Math.floor((n - 1) / 26);
  }
  return out;
}

function styleTitle(sheet, title, subtitle, lastColumn = "H") {
  sheet.mergeCells(`A1:${lastColumn}1`);
  sheet.getRange("A1").values = [[title]];
  sheet.getRange("A1").format = {
    fill: theme.navy,
    font: { bold: true, color: theme.white, size: 18 },
    rowHeight: 31,
    verticalAlignment: "center",
  };
  sheet.mergeCells(`A2:${lastColumn}2`);
  sheet.getRange("A2").values = [[subtitle]];
  sheet.getRange("A2").format = {
    fill: theme.pale,
    font: { italic: true, color: theme.muted, size: 10 },
    wrapText: true,
    rowHeight: 30,
    verticalAlignment: "center",
  };
}

function styleTable(sheet, headerRow, lastRow, lastCol, percentCols = [], decimalCols = []) {
  const last = colName(lastCol);
  const header = sheet.getRange(`A${headerRow}:${last}${headerRow}`);
  header.format = {
    fill: theme.teal,
    font: { bold: true, color: theme.white, size: 9 },
    wrapText: true,
    verticalAlignment: "center",
    horizontalAlignment: "center",
    rowHeight: 33,
    borders: { preset: "all", style: "thin", color: theme.border },
  };
  const body = sheet.getRange(`A${headerRow + 1}:${last}${lastRow}`);
  body.format = {
    font: { color: theme.ink, size: 9 },
    borders: { preset: "all", style: "thin", color: theme.border },
    verticalAlignment: "center",
  };
  body.format.autofitRows();
  for (const col of percentCols) {
    sheet.getRange(`${col}${headerRow + 1}:${col}${lastRow}`).format.numberFormat = "0.00%";
  }
  for (const col of decimalCols) {
    sheet.getRange(`${col}${headerRow + 1}:${col}${lastRow}`).format.numberFormat = "0.000";
  }
  sheet.freezePanes.freezeRows(headerRow);
}

function writeDataSheet(name, title, subtitle, rows, options = {}) {
  const sheet = wb.worksheets.add(name);
  const width = rows[0].length;
  styleTitle(sheet, title, subtitle, colName(Math.max(width, 8)));
  sheet.getRange(`A4:${colName(width)}${rows.length + 3}`).values = rows;
  styleTable(
    sheet,
    4,
    rows.length + 3,
    width,
    options.percentCols || [],
    options.decimalCols || [],
  );
  sheet.getRange(`A4:${colName(width)}${Math.min(rows.length + 3, 60)}`).format.autofitColumns();
  for (let c = 1; c <= width; c += 1) {
    const column = colName(c);
    const maxWidth = c === 2 ? 38 : 18;
    sheet.getRange(`${column}:${column}`).format.columnWidth = maxWidth;
  }
  if (options.tableName) {
    sheet.tables.add(`A4:${colName(width)}${rows.length + 3}`, true, options.tableName);
  }
  return sheet;
}

// 1) Dashboard.
const summary = wb.worksheets.add("Summary");
styleTitle(
  summary,
  "Taxila PreserveX | Integrated Experiments",
  "Audited numerical companion to the standalone Experiments, Results and Discussion manuscript section",
  "N",
);
summary.getRange("A4:B4").values = [["Headline result", "Formula-linked value"]];
summary.getRange("A5:A13").values = [
  ["Endpoint common support"],
  ["Cells meeting ≥2 adverse spectral criteria"],
  ["Cells meeting all 3 adverse spectral criteria"],
  ["Highest 2024 climate-extreme score"],
  ["Top 500 m local-priority component"],
  ["Top component local-priority score"],
  ["Best proxy-model macro-F1"],
  ["Best proxy-model 95% block-bootstrap interval"],
  ["Validation gates passed"],
];
summary.getRange("B5:B13").formulas = [
  ["='Endpoint Screen'!B6/100"],
  ["='Endpoint Screen'!B12/100"],
  ["='Endpoint Screen'!B13/100"],
  ["=MAX('Climate Epochs'!AA5:AA9)"],
  ["='2024 Ranking'!A5"],
  ["='2024 Ranking'!G5"],
  ["=MAX('Model Comparison'!E5:E9)"],
  ['="["&TEXT(\'Model Comparison\'!N5,"0.000")&", "&TEXT(\'Model Comparison\'!O5,"0.000")&"]"'],
  ["='Validation'!B6&\"/\"&'Validation'!B7"],
];
summary.getRange("B5:B7").format.numberFormat = "0.00%";
summary.getRange("B8").format.numberFormat = "0.000";
summary.getRange("B10:B11").format.numberFormat = "0.000";
summary.getRange("A4:B13").format.borders = { preset: "all", style: "thin", color: theme.border };
summary.getRange("A4:B4").format = {
  fill: theme.teal,
  font: { bold: true, color: theme.white },
};
summary.getRange("A5:A13").format.font = { bold: true, color: theme.ink };
summary.getRange("A:A").format.columnWidth = 44;
summary.getRange("B:B").format.columnWidth = 26;
summary.getRange("A15:N17").merge();
summary.getRange("A15").values = [[
  "Interpretation boundary: the integrated score is a relative field-inspection priority combining landscape pressure, terrain susceptibility and site-wide climate forcing. It is not a monument-damage probability or a validated complete-risk score. Model metrics are agreement with a WorldCover-consensus proxy under spatial blocking, not independent human accuracy.",
]];
summary.getRange("A15").format = {
  fill: "#FFF7E3",
  font: { color: "#6B4F00", bold: true, size: 10 },
  wrapText: true,
  verticalAlignment: "center",
  borders: { preset: "outside", style: "thin", color: theme.gold },
};
summary.freezePanes.freezeRows(3);

// 2) Experiment matrix.
const experimentRows = [
  ["Experiment", "Question", "Evidence", "Primary output", "Inference boundary"],
  ["E1 Reproduction", "Does the revised pipeline reproduce the accepted endpoint screen?", "Five Landsat epochs; fixed 30 m grid", "Support and convergence statistics", "Descriptive spectral pressure only"],
  ["E2 Matched climate", "How did wet, dry and heat forcing vary across satellite windows?", "NASA POWER daily, 1991–2025; three-year windows", "Eight anomaly indicators and climate score", "Site-wide temporal forcing; no 30 m rainfall mapping"],
  ["E3 Terrain/hydrology", "Where does topography amplify runoff, wetness and erosion susceptibility?", "1 arc-second bare-earth terrain tile", "Slope, TWI proxy, high-flow distance", "Susceptibility screen; not hydraulic inundation"],
  ["E4 Model comparison", "Does model complexity materially improve proxy land-cover discrimination?", "20,749 consensus samples; 100 spatial blocks", "Blocked outer-test scores and 2,000 block bootstraps", "Proxy agreement; not independent accuracy"],
  ["E5 Integrated priority", "Which components combine dynamic landscape pressure and terrain susceptibility?", "Component summaries at 250/500/1,000 m", "Relative integrated and local-priority scores", "Prioritisation, not damage probability"],
  ["E6 Robustness", "Are component positions stable to scale, weights and factor removal?", "50,000 weight draws; scale and ablation tests", "Rank intervals, top-5 probability, Spearman ρ", "Unstable ranks must not be treated as definitive"],
];
writeDataSheet(
  "Experiment Matrix",
  "Executed experiment matrix",
  "Six prespecified experiment families and their permitted inference",
  experimentRows,
  { tableName: "ExperimentMatrixTable" },
);

// 3) Endpoint exact reproduction.
const endpoint = JSON.parse(await fs.readFile(path.join(tableDir, "endpoint_screening_summary.json"), "utf8"));
const endpointRows = [
  ["Metric", "Value"],
  ["Endpoint supported cells", endpoint.endpoint_supported_cells],
  ["Endpoint supported percent", endpoint.endpoint_supported_percent],
  ["NDVI adverse threshold (q20)", endpoint.thresholds.delta_ndvi_q20],
  ["MNDWI adverse threshold (q20)", endpoint.thresholds.delta_mndwi_q20],
  ["NDBI adverse threshold (q80)", endpoint.thresholds.delta_ndbi_q80],
  ["Cells with 0 criteria", endpoint.convergence_cell_counts["0"]],
  ["Cells with 1 criterion", endpoint.convergence_cell_counts["1"]],
  ["Share with ≥2 criteria (%)", endpoint.share_c_ge_2_percent],
  ["Share with all 3 criteria (%)", endpoint.share_c_eq_3_percent],
  ["Median ΔNDVI", endpoint.grid_median_delta.NDVI],
  ["Median ΔMNDWI", endpoint.grid_median_delta.MNDWI],
  ["Median ΔNDBI", endpoint.grid_median_delta.NDBI],
];
writeDataSheet(
  "Endpoint Screen",
  "Endpoint spectral-screen reproduction",
  "Exact reproduction of the accepted 2004–2024 common-support analysis",
  endpointRows,
  { decimalCols: ["B"], tableName: "EndpointScreenTable" },
);

// 4) Climate.
const climateRows = await readCsv("matched_epoch_climate_metrics.csv");
const climate = writeDataSheet(
  "Climate Epochs",
  "Matched three-year climate windows",
  "NASA POWER daily weather summarised for the same five satellite epochs; 1991–2020 baseline",
  climateRows,
  { decimalCols: ["D", "E", "G", "AB"], tableName: "ClimateEpochsTable" },
);
climate.getRange("D5:AI9").format.numberFormat = "0.00";
const climateChart = climate.charts.add("line", climate.getRange("B4:B9"));
climateChart.series.add("Climate-extreme score").formula = "'Climate Epochs'!$AB$5:$AB$9";
climateChart.series.items[0].categoryFormula = "'Climate Epochs'!$B$5:$B$9";
climateChart.title = "Climate-extreme score by matched epoch";
climateChart.hasLegend = false;
climateChart.yAxis = { min: 0, max: 1, numberFormatCode: "0.00" };
climateChart.setPosition("AK4", "AS20");

// 5) Integrated component results.
const componentRows = await readCsv("component_epoch_integrated_scores.csv");
const componentHeader = componentRows[0];
const radiusIndex = componentHeader.indexOf("radius_m");
const epochIndex = componentHeader.indexOf("epoch_id");
const targetRows = [
  componentHeader,
  ...componentRows
    .slice(1)
    .filter((row) => row[radiusIndex] === 500 && row[epochIndex] === "E2024")
    .sort((a, b) => b[componentHeader.indexOf("local_priority_score")] - a[componentHeader.indexOf("local_priority_score")]),
];
const selectedHeaders = [
  "component_name",
  "component_id",
  "landscape_pressure_score",
  "terrain_susceptibility_score",
  "climate_extreme_score",
  "integrated_exposure_score",
  "local_priority_score",
];
const selectedIndices = selectedHeaders.map((h) => componentHeader.indexOf(h));
const rankingRows = [
  selectedHeaders,
  ...targetRows.slice(1).map((row) => selectedIndices.map((i) => row[i])),
];
const ranking = writeDataSheet(
  "2024 Ranking",
  "2024 integrated component screen at 500 m",
  "Sorted by local-priority score (landscape pressure + terrain susceptibility); climate is site-wide within the epoch",
  rankingRows,
  { decimalCols: ["C", "D", "E", "F", "G"], tableName: "Ranking2024Table" },
);
const rankingChart = ranking.charts.add("bar", ranking.getRange("A4:A16"));
rankingChart.series.add("Local priority").formula = "'2024 Ranking'!$G$5:$G$16";
rankingChart.series.items[0].categoryFormula = "'2024 Ranking'!$A$5:$A$16";
rankingChart.title = "Twelve highest 500 m local-priority scores";
rankingChart.hasLegend = false;
rankingChart.xAxis = { numberFormatCode: "0.00", min: 0, max: 1 };
rankingChart.setPosition("I4", "Q24");

writeDataSheet(
  "Component Epochs",
  "Component-by-epoch integrated scores",
  "Complete 17-component × 5-epoch × 3-scale analytical table",
  componentRows,
  { decimalCols: ["G", "J", "M", "P", "AA", "AB", "AC", "AF", "AG", "AJ", "AK", "AL"], tableName: "ComponentEpochsTable" },
);

// 6) Uncertainty.
const uncertaintyRows = await readCsv("monte_carlo_domain_weight_rank_uncertainty.csv");
const uncertainty = writeDataSheet(
  "Rank Uncertainty",
  "Monte Carlo domain-weight uncertainty",
  "Fifty thousand Dirichlet weight draws; rank 1 is highest priority",
  uncertaintyRows,
  { percentCols: ["H", "I"], decimalCols: ["C"], tableName: "RankUncertaintyTable" },
);
const uncertaintyChart = uncertainty.charts.add("bar", uncertainty.getRange("B4:B14"));
uncertaintyChart.series.add("Probability top 5").formula = "'Rank Uncertainty'!$H$5:$H$14";
uncertaintyChart.series.items[0].categoryFormula = "'Rank Uncertainty'!$B$5:$B$14";
uncertaintyChart.title = "Probability of ranking in the top five";
uncertaintyChart.hasLegend = false;
uncertaintyChart.xAxis = { numberFormatCode: "0%", min: 0, max: 1 };
uncertaintyChart.setPosition("L4", "T23");

// 7) Model comparison.
const modelRows = await readCsv("spatially_blocked_model_comparison.csv");
const models = writeDataSheet(
  "Model Comparison",
  "Spatially blocked proxy-model comparison",
  "Outer test: 4,195 samples in 21 held-out blocks; 2,000 whole-block bootstrap resamples",
  modelRows,
  { decimalCols: ["B", "C", "D", "E", "F", "N", "O", "P", "Q", "R"], tableName: "ModelComparisonTable" },
);
const modelChart = models.charts.add("bar", models.getRange("A4:A9"));
modelChart.series.add("Macro-F1").formula = "'Model Comparison'!$E$5:$E$9";
modelChart.series.items[0].categoryFormula = "'Model Comparison'!$A$5:$A$9";
modelChart.title = "Held-out proxy macro-F1";
modelChart.hasLegend = false;
modelChart.xAxis = { numberFormatCode: "0.00", min: 0.75, max: 0.92 };
modelChart.setPosition("U4", "AC20");

// 8) Scale and ablation.
const ablationRows = await readCsv("leave_one_domain_factor_out_ablation.csv");
const ablation = writeDataSheet(
  "Ablation",
  "Leave-one-domain/factor-out stability",
  "Spearman agreement with the full 500 m local-priority ranking",
  ablationRows,
  { decimalCols: ["B"], tableName: "AblationTable" },
);
const ablationChart = ablation.charts.add("bar", ablation.getRange(`A4:A${ablationRows.length + 3}`));
ablationChart.series.add("Spearman rho").formula = `'Ablation'!$B$5:$B$${ablationRows.length + 3}`;
ablationChart.series.items[0].categoryFormula = `'Ablation'!$A$5:$A$${ablationRows.length + 3}`;
ablationChart.title = "Ranking stability after evidence removal";
ablationChart.hasLegend = false;
ablationChart.xAxis = { numberFormatCode: "0.00", min: 0, max: 1 };
ablationChart.setPosition("F4", "N20");

writeDataSheet(
  "Scale Sensitivity",
  "Integrated rank agreement across spatial supports",
  "Pairwise Spearman correlations for 250, 500 and 1,000 m component rankings",
  await readCsv("integrated_score_scale_rank_correlations.csv"),
  { decimalCols: ["C"], tableName: "ScaleSensitivityTable" },
);

// 9) Terrain and exploratory associations.
writeDataSheet(
  "Terrain",
  "Component terrain and hydrological susceptibility",
  "Static elevation, slope, roughness, topographic wetness and drainage-proximity summaries",
  await readCsv("component_multiscale_terrain_hydrology.csv"),
  { decimalCols: ["E", "H", "I", "J", "K", "L", "M", "N"], tableName: "TerrainTable" },
);
writeDataSheet(
  "Climate-Spectral",
  "Exploratory climate–spectral associations",
  "Only five unique epochs: report effect direction and leave-one-epoch-out sign stability, not confirmatory p-values",
  await readCsv("climate_spectral_exploratory_associations.csv"),
  { decimalCols: ["C", "E", "F", "G"], tableName: "ClimateSpectralTable" },
);

// 10) Validation and sources.
const validation = JSON.parse(await fs.readFile(path.join(baseDir, "validation", "integrated_experiment_validation.json"), "utf8"));
const validationRows = [
  ["Metric", "Value"],
  ["Status", validation.status],
  ["Checks passed", validation.checks_passed],
  ["Checks total", validation.checks_total],
  ["NASA POWER SHA-256", validation.source_hashes.nasa_power_json],
  ["Terrain tile SHA-256", validation.source_hashes.terrain_hgt_gz],
  ["Raw-manifest SHA-256", validation.source_hashes.raw_manifest],
];
const validationSheet = writeDataSheet(
  "Validation",
  "Validation gates and source provenance",
  "Machine-readable checksums and executable structural checks",
  validationRows,
  { tableName: "ValidationTable" },
);
validationSheet.getRange("A13:B16").values = [
  ["Source", "URL"],
  ["NASA POWER Daily API", "https://power.larc.nasa.gov/docs/services/api/temporal/daily/"],
  ["NASA POWER resolution guidance", "https://power.larc.nasa.gov/docs/tutorials/service-data-request/api/"],
  ["AWS Terrain Tiles", "https://registry.opendata.aws/terrain-tiles/"],
];
validationSheet.getRange("A13:B13").format = {
  fill: theme.teal,
  font: { bold: true, color: theme.white },
};
validationSheet.getRange("A13:B16").format.borders = { preset: "all", style: "thin", color: theme.border };
validationSheet.getRange("B:B").format.columnWidth = 74;

// Global workbook QA styling.
for (const sheet of wb.worksheets.items) {
  const used = sheet.getUsedRange();
  if (used) used.format.font.name = "Aptos";
}

const inspectResult = await wb.inspect({
  kind: "workbook,sheet,formula,drawing",
  maxChars: 9000,
  options: { maxResults: 150 },
});
await fs.writeFile(path.join(outputDir, "workbook_inspection.txt"), inspectResult.ndjson || String(inspectResult));

const errorScan = await wb.inspect({
  kind: "match",
  searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A",
  options: { useRegex: true, maxResults: 200 },
  maxChars: 7000,
});
await fs.writeFile(path.join(outputDir, "workbook_formula_error_scan.txt"), errorScan.ndjson || String(errorScan));

for (const sheet of wb.worksheets.items) {
  const preview = await wb.render({
    sheetName: sheet.name,
    autoCrop: "all",
    scale: 1,
    format: "png",
  });
  const safe = sheet.name.toLowerCase().replace(/[^a-z0-9]+/g, "_");
  await fs.writeFile(
    path.join(outputDir, "workbook_previews", `${safe}.png`),
    new Uint8Array(await preview.arrayBuffer()),
  );
}

const output = await SpreadsheetFile.exportXlsx(wb);
await output.save(path.join(outputDir, "Taxila_PreserveX_Integrated_Experiments_Results.xlsx"));
console.log(JSON.stringify({
  workbook: path.join(outputDir, "Taxila_PreserveX_Integrated_Experiments_Results.xlsx"),
  sheets: wb.worksheets.items.map((sheet) => sheet.name),
}));
