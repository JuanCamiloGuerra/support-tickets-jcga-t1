import fs from "node:fs/promises";
import path from "node:path";
import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const projectRoot = path.resolve("../..");
const detailPath = path.join(projectRoot, "output", "pdf", "orden_produccion_blusas_cierre_2026.detalle.csv");
const outputDir = path.join(projectRoot, "output", "xlsx");
const outputPath = path.join(outputDir, "orden_produccion_blusas_cierre_2026.xlsx");
const previewPath = path.join(projectRoot, "tmp", "spreadsheets", "orden_produccion_blusas_cierre_2026_preview.png");

const sizeOrder = ["2", "4", "6", "8", "10", "12", "14", "16", "S", "M", "L", "XL"];

function parseCsv(text) {
  const lines = text.replace(/^\uFEFF/, "").trim().split(/\r?\n/);
  const headers = lines.shift().split(";");
  return lines.filter(Boolean).map((line) => {
    const values = line.split(";");
    return Object.fromEntries(headers.map((header, index) => [header, values[index] ?? ""]));
  });
}

function colLetter(index) {
  let n = index + 1;
  let result = "";
  while (n > 0) {
    const rem = (n - 1) % 26;
    result = String.fromCharCode(65 + rem) + result;
    n = Math.floor((n - 1) / 26);
  }
  return result;
}

const detailRows = parseCsv(await fs.readFile(detailPath, "utf8"));
const rowMap = new Map();

for (const row of detailRows) {
  const label = row.articulo_colegio;
  if (!rowMap.has(label)) {
    rowMap.set(label, Object.fromEntries(sizeOrder.map((size) => [size, 0])));
  }
  const size = String(row.talla).trim().toUpperCase();
  if (sizeOrder.includes(size)) {
    rowMap.get(label)[size] += Number(row.orden_produccion || 0);
  }
}

const sortedLabels = [...rowMap.keys()].sort((a, b) => a.localeCompare(b, "es"));
const headers = ["articulo y colegio", ...sizeOrder];
const tableRows = sortedLabels.map((label) => [
  label,
  ...sizeOrder.map((size) => rowMap.get(label)[size]),
]);
const totals = [
  "TOTAL POR TALLA",
  ...sizeOrder.map((size) => tableRows.reduce((sum, row) => sum + Number(row[headers.indexOf(size)] || 0), 0)),
];
const matrix = [headers, ...tableRows, totals];

await fs.mkdir(outputDir, { recursive: true });

const workbook = Workbook.create();
const sheet = workbook.worksheets.add("Orden blusas 2026");
sheet.showGridLines = false;

const generatedAt = new Date().toLocaleString("sv-SE", { timeZone: "America/Bogota" });
const totalUnits = totals.slice(1).reduce((sum, value) => sum + value, 0);
const totalSkus = detailRows.length;

sheet.getRange("A1:M1").merge();
sheet.getRange("A1").values = [["Orden de produccion blusas - cierre año 2026"]];
sheet.getRange("A1").format = {
  font: { bold: true, size: 16, color: "#1F2933" },
};

sheet.getRange("A2:M2").merge();
sheet.getRange("A2").values = [[
  `Generado: ${generatedAt} Bogota | Meses objetivo: agosto-diciembre 2026 | Unidades: ${totalUnits.toLocaleString("en-US")} | Filas: ${tableRows.length} | Referencias/tallas: ${totalSkus}`,
]];
sheet.getRange("A2").format = {
  font: { size: 9, color: "#4B5563" },
};

const startRow = 4;
const endRow = startRow + matrix.length - 1;
const endCol = headers.length - 1;
const rangeAddress = `A${startRow}:${colLetter(endCol)}${endRow}`;
sheet.getRange(rangeAddress).values = matrix;

const headerRange = sheet.getRange(`A${startRow}:${colLetter(endCol)}${startRow}`);
headerRange.format = {
  fill: "#243B53",
  font: { bold: true, color: "#FFFFFF" },
  horizontalAlignment: "center",
};

const bodyRange = sheet.getRange(`A${startRow + 1}:${colLetter(endCol)}${endRow - 1}`);
bodyRange.format = {
  borders: { preset: "all", style: "thin", color: "#D9E2EC" },
};

const totalRange = sheet.getRange(`A${endRow}:${colLetter(endCol)}${endRow}`);
totalRange.format = {
  fill: "#243B53",
  font: { bold: true, color: "#FFFFFF" },
  borders: { preset: "all", style: "thin", color: "#111827" },
};

sheet.getRange(`A${startRow + 1}:A${endRow}`).format = {
  horizontalAlignment: "left",
};
sheet.getRange(`B${startRow + 1}:${colLetter(endCol)}${endRow}`).format = {
  horizontalAlignment: "right",
  numberFormat: "#,##0",
};
sheet.getRange(rangeAddress).format = {
  borders: { preset: "all", style: "thin", color: "#D9E2EC" },
};

for (let r = 0; r < tableRows.length; r++) {
  for (let c = 1; c < headers.length; c++) {
    const value = tableRows[r][c];
    if (value > 15) {
      sheet.getCell(startRow + r, c).format = {
        fill: "#F8D7DA",
        font: { bold: true, color: "#8A1F2D" },
        horizontalAlignment: "right",
        numberFormat: "#,##0",
      };
    } else if (value > 10) {
      sheet.getCell(startRow + r, c).format = {
        fill: "#FFF3CD",
        font: { bold: true, color: "#664D03" },
        horizontalAlignment: "right",
        numberFormat: "#,##0",
      };
    }
  }
}

sheet.getRange("A:A").format.columnWidth = 44;
sheet.getRange("B:M").format.columnWidth = 10;
sheet.getRange("1:1").format.rowHeight = 24;
sheet.getRange(`${startRow}:${endRow}`).format.rowHeight = 18;

sheet.freezePanes.freezeRows(startRow);
sheet.freezePanes.freezeColumns(1);
const table = sheet.tables.add(rangeAddress, true, "OrdenBlusas2026");
table.style = "TableStyleMedium2";
table.showFilterButton = true;

const inspect = await workbook.inspect({
  kind: "region",
  sheetId: "Orden blusas 2026",
  range: "A1:M13",
  maxChars: 2500,
});
console.log(inspect.ndjson);

const errors = await workbook.inspect({
  kind: "match",
  searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A",
  options: { useRegex: true, maxResults: 50 },
  summary: "formula error scan",
});
console.log(errors.ndjson);

const preview = await workbook.render({
  sheetName: "Orden blusas 2026",
  range: "A1:M13",
  scale: 2,
  format: "png",
});
await fs.writeFile(previewPath, new Uint8Array(await preview.arrayBuffer()));

const xlsx = await SpreadsheetFile.exportXlsx(workbook);
await xlsx.save(outputPath);
console.log(JSON.stringify({ outputPath, previewPath, totalUnits, totalRows: tableRows.length, totalSkus }));
