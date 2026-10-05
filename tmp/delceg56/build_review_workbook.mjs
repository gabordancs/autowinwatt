import fs from "node:fs/promises";
import path from "node:path";
import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const root = "C:/Users/Dancs/Documents/GitHub/autowinwatt";
const inputPath = path.join(root, "data/delceg56/layer_audit_catalog_matched.json");
const outputDir = path.join(root, "outputs/delceg56_retegrend_review");
const outputPath = path.join(outputDir, "Delceg56_retegrend_katalogus_ellenorzes.xlsx");
const previewPath = path.join(outputDir, "Delceg56_retegrend_katalogus_ellenorzes_preview.png");

const audit = JSON.parse(await fs.readFile(inputPath, "utf8"));
const rows = audit.layers.map((layer) => {
  const match = /^(\S+)\s+(.*)$/.exec(layer.structure) ?? [null, layer.structure, ""];
  const candidate = layer.decision?.candidate ?? {};
  return [
    match[1],
    match[2],
    layer.sequence,
    layer.source_name,
    layer.thickness_cm,
    candidate.name ?? "",
    candidate.material_id ?? "",
    candidate.path ?? "",
    (layer.catalog_files ?? []).join(", "),
    candidate.lambda_wmk ?? null,
    candidate.density_kgm3 ?? null,
    layer.decision?.confidence ?? null,
    layer.decision?.status === "catalog" ? "KATALÓGUS-EGYEZÉS" : "ELLENŐRIZENDŐ",
    "",
    "",
  ];
});

await fs.mkdir(outputDir, { recursive: true });

const workbook = Workbook.create();
const sheet = workbook.worksheets.add("Rétegek");
sheet.showGridLines = false;
sheet.tabColor = "#1F4E78";

sheet.getRange("A2:O2").merge();
sheet.getRange("A2").values = [["Délceg utca 56 – rétegrendi katalógusellenőrzés"]];
sheet.getRange("A2:O2").format = {
  font: { name: "Arial", size: 15, bold: true, color: "#1F2937" },
  rowHeight: 25,
};
sheet.getRange("A3:O3").merge();
sheet.getRange("A3").values = [["A Döntés oszlopban jelöld: OK = a katalóguspár elfogadható; KIHAGYHATÓ = ezt a réteget ne vegyük fel. A Megjegyzés mező szabadon szerkeszthető."]];
sheet.getRange("A3:O3").format = {
  font: { name: "Arial", size: 10, italic: true, color: "#4B5563" },
  rowHeight: 22,
};

sheet.getRange("A5:F5").values = [["Összes réteg", rows.length, "Elfogadva", null, "Kihagyható", null]];
sheet.getRange("H5:K5").values = [["Hátralévő döntés", null, "Biztos katalógusegyezés", audit.summary?.catalog ?? 0]];
sheet.getRange("D5").formulas = [[`=COUNTIF(N8:N${7 + rows.length},"OK")`]];
sheet.getRange("F5").formulas = [[`=COUNTIF(N8:N${7 + rows.length},"KIHAGYHATÓ")`]];
sheet.getRange("I5").formulas = [[`=COUNTBLANK(N8:N${7 + rows.length})`]];
sheet.getRange("A5:K5").format = {
  font: { name: "Arial", size: 10, bold: true, color: "#1F2937" },
  fill: "#E8EEF7",
  verticalAlignment: "center",
  rowHeight: 22,
};
sheet.getRange("B5,D5,F5,I5,K5").format = {
  font: { name: "Arial", size: 11, bold: true, color: "#1F4E78" },
};

const headers = [[
  "Kód",
  "Rétegrend megnevezése",
  "Réteg sorszáma",
  "Terv szerinti anyag",
  "Vastagság [cm]",
  "Talált WinWatt katalógusanyag",
  "Katalógus ID",
  "Katalógus útvonal",
  "Katalógusfájl",
  "λ [W/mK]",
  "Sűrűség [kg/m³]",
  "Egyezés [%]",
  "Gépi állapot",
  "Döntés",
  "Megjegyzés",
]];
sheet.getRange("A7:O7").values = headers;
sheet.getRange(`A8:O${7 + rows.length}`).values = rows;

const table = sheet.tables.add(`A7:O${7 + rows.length}`, true, "LayerReviewTable");
table.style = "TableStyleMedium2";
table.showFilterButton = true;
table.showBandedRows = true;

const body = sheet.getRange(`A8:O${7 + rows.length}`);
body.format.font = { name: "Arial", size: 10, color: "#1F2937" };
body.format.verticalAlignment = "center";
sheet.getRange(`B8:B${7 + rows.length}`).format.wrapText = true;
sheet.getRange(`D8:D${7 + rows.length}`).format.wrapText = true;
sheet.getRange(`F8:I${7 + rows.length}`).format.wrapText = true;
sheet.getRange(`M8:O${7 + rows.length}`).format.wrapText = true;
sheet.getRange(`C8:C${7 + rows.length}`).format.horizontalAlignment = "center";
sheet.getRange(`E8:E${7 + rows.length}`).format.numberFormat = "0.0";
sheet.getRange(`J8:J${7 + rows.length}`).format.numberFormat = "0.000";
sheet.getRange(`K8:K${7 + rows.length}`).format.numberFormat = "0";
sheet.getRange(`L8:L${7 + rows.length}`).format.numberFormat = "0%";
sheet.getRange(`N8:N${7 + rows.length}`).dataValidation = {
  rule: { type: "list", values: ["OK", "KIHAGYHATÓ"] },
};
sheet.getRange(`N8:N${7 + rows.length}`).format.fill = "#FFF2CC";
sheet.getRange(`N8:N${7 + rows.length}`).format.font = { name: "Arial", size: 10, bold: true, color: "#7F6000" };

sheet.getRange(`N8:N${7 + rows.length}`).conditionalFormats.add("containsText", {
  text: "OK",
  format: { fill: "#E2F0D9", font: { bold: true, color: "#375623" } },
});
sheet.getRange(`N8:N${7 + rows.length}`).conditionalFormats.add("containsText", {
  text: "KIHAGYHATÓ",
  format: { fill: "#E7E6E6", font: { bold: true, color: "#595959" } },
});
sheet.getRange(`M8:M${7 + rows.length}`).conditionalFormats.add("containsText", {
  text: "KATALÓGUS-EGYEZÉS",
  format: { fill: "#E2F0D9", font: { color: "#375623" } },
});
sheet.getRange(`M8:M${7 + rows.length}`).conditionalFormats.add("containsText", {
  text: "ELLENŐRIZENDŐ",
  format: { fill: "#FCE4D6", font: { color: "#9C0006" } },
});

const widths = {
  A: 10, B: 25, C: 12, D: 31, E: 14, F: 32, G: 12, H: 36,
  I: 22, J: 12, K: 16, L: 13, M: 18, N: 18, O: 32,
};
for (const [col, width] of Object.entries(widths)) {
  sheet.getRange(`${col}:${col}`).format.columnWidth = width;
}
sheet.getRange(`A7:O${7 + rows.length}`).format.rowHeight = 32;
sheet.getRange("A7:O7").format.rowHeight = 42;
sheet.freezePanes.freezeRows(7);
sheet.freezePanes.freezeColumns(2);

workbook.recalculate();

const inspect = await workbook.inspect({
  kind: "region,table,formula",
  sheetId: "Rétegek",
  range: `A1:O${7 + rows.length}`,
  maxChars: 7000,
  tableMaxRows: 8,
  tableMaxCols: 15,
  options: { maxResults: 100 },
});
console.log(inspect.ndjson);

const errorScan = await workbook.inspect({
  kind: "match",
  searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A",
  options: { useRegex: true, maxResults: 100 },
  maxChars: 3000,
});
console.log("FORMULA_ERROR_SCAN");
console.log(errorScan.ndjson);

const preview = await workbook.render({
  sheetName: "Rétegek",
  range: `A1:O${Math.min(22, 7 + rows.length)}`,
  scale: 1,
  format: "png",
});
await fs.writeFile(previewPath, new Uint8Array(await preview.arrayBuffer()));

const xlsx = await SpreadsheetFile.exportXlsx(workbook);
await xlsx.save(outputPath);
console.log(`OUTPUT=${outputPath}`);
console.log(`PREVIEW=${previewPath}`);
