/**
 * ExcelWriter — writes data to Excel worksheets as formatted tables.
 *
 * Creates or replaces a named sheet, writes headers + rows, and
 * applies formatting (auto-fit columns, number format for amounts).
 */

/* global Excel */

/**
 * Write tabular data to a named Excel worksheet.
 *
 * If a sheet with the given name exists, it is deleted first.
 * Data is written as an Excel Table with auto-filter.
 */
export async function writeToSheet(
  sheetName: string,
  headers: string[],
  rows: (string | number | boolean | null)[][],
  amountColumns?: string[],
  percentColumns?: string[]
): Promise<void> {
  await Excel.run(async (context) => {
    const sheets = context.workbook.worksheets;
    sheets.load("items/name");
    await context.sync();

    // Delete existing sheet with same name.
    const existing = sheets.items.find(
      (s) => s.name.toLowerCase() === sheetName.toLowerCase()
    );
    if (existing) {
      existing.delete();
      await context.sync();
    }

    // Create new sheet.
    const sheet = sheets.add(sheetName);
    sheet.activate();

    if (rows.length === 0) {
      // Write just a message if no data.
      sheet.getRange("A1").values = [["Inga rader hittades."]];
      await context.sync();
      return;
    }

    // Build data array: headers + rows.
    const allData: (string | number | boolean | null)[][] = [headers, ...rows];
    const lastCol = String.fromCharCode(64 + headers.length); // A=65
    const rangeAddress = `A1:${lastCol}${allData.length}`;
    const range = sheet.getRange(rangeAddress);
    range.values = allData;

    // Create table with auto-filter.
    const tableRange = sheet.getRange(rangeAddress);
    const table = sheet.tables.add(tableRange, true /* hasHeaders */);
    table.name = sheetName.replace(/[^a-zA-Z0-9]/g, "_");
    table.style = "TableStyleMedium2";

    // Format header row.
    const headerRange = sheet.getRange(`A1:${lastCol}1`);
    headerRange.format.font.bold = true;

    // Format amount columns with Swedish number format.
    if (amountColumns && amountColumns.length > 0) {
      for (const colName of amountColumns) {
        const colIndex = headers.indexOf(colName);
        if (colIndex >= 0) {
          const colLetter = String.fromCharCode(65 + colIndex);
          const amountRange = sheet.getRange(
            `${colLetter}2:${colLetter}${allData.length}`
          );
          amountRange.numberFormat = [["#,##0.00"]];
        }
      }
    }

    // Format percent columns with one decimal.
    if (percentColumns && percentColumns.length > 0) {
      for (const colName of percentColumns) {
        const colIndex = headers.indexOf(colName);
        if (colIndex >= 0) {
          const colLetter = String.fromCharCode(65 + colIndex);
          const pctRange = sheet.getRange(
            `${colLetter}2:${colLetter}${allData.length}`
          );
          pctRange.numberFormat = [["0.0"]];
        }
      }
    }

    // Auto-fit all columns.
    range.format.autofitColumns();

    await context.sync();
  });
}

/**
 * Check if Excel/Office.js is available in the current environment.
 */
export function isExcelAvailable(): boolean {
  return typeof Excel !== "undefined" && typeof Excel.run === "function";
}
