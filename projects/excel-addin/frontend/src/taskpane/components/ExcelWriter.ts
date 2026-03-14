/**
 * ExcelWriter — writes data to Excel worksheets as formatted tables.
 *
 * Supports two destination modes:
 *   - "replace": delete existing sheet with same name (default)
 *   - "new": always create a new sheet, appending suffix if name exists
 */

/* global Excel */

export interface WriteOptions {
  /** "replace" = overwrite existing sheet. "new" = always create new. */
  destination?: "replace" | "new";
  /** Column labels to format as Swedish currency amounts (#,##0.00). */
  amountColumns?: string[];
  /** Column labels to format as percentages (0.0). */
  percentColumns?: string[];
}

/**
 * Convert a 0-based column index to an Excel column letter (A, B, ..., Z, AA, AB, ...).
 */
function colLetter(index: number): string {
  let s = "";
  let n = index + 1;
  while (n > 0) {
    n--;
    s = String.fromCharCode(65 + (n % 26)) + s;
    n = Math.floor(n / 26);
  }
  return s;
}

/**
 * Write tabular data to a named Excel worksheet.
 *
 * Returns the actual sheet name used (may differ from input when
 * destination is "new" and name already exists).
 */
export async function writeToSheet(
  sheetName: string,
  headers: string[],
  rows: (string | number | boolean | null)[][],
  options: WriteOptions = {},
): Promise<string> {
  const { destination = "replace", amountColumns, percentColumns } = options;

  let actualSheetName = sheetName;

  await Excel.run(async (context) => {
    const sheets = context.workbook.worksheets;
    sheets.load("items/name");
    await context.sync();

    const existingNames = new Set(
      sheets.items.map((s) => s.name.toLowerCase()),
    );

    if (destination === "replace") {
      // Delete existing sheet with same name.
      const existing = sheets.items.find(
        (s) => s.name.toLowerCase() === sheetName.toLowerCase(),
      );
      if (existing) {
        existing.delete();
        await context.sync();
      }
      actualSheetName = sheetName;
    } else {
      // "new" mode — find a unique name.
      if (existingNames.has(sheetName.toLowerCase())) {
        let suffix = 2;
        while (existingNames.has(`${sheetName} (${suffix})`.toLowerCase())) {
          suffix++;
        }
        actualSheetName = `${sheetName} (${suffix})`;
      }
    }

    // Truncate to Excel's 31-character sheet name limit.
    if (actualSheetName.length > 31) {
      actualSheetName = actualSheetName.substring(0, 31);
    }

    // Create new sheet.
    const sheet = sheets.add(actualSheetName);
    sheet.activate();

    if (rows.length === 0) {
      // Write just a message if no data.
      sheet.getRange("A1").values = [["Inga rader hittades."]];
      await context.sync();
      return;
    }

    // Build data array: headers + rows.
    const allData: (string | number | boolean | null)[][] = [headers, ...rows];
    const lastCol = colLetter(headers.length - 1);
    const rangeAddress = `A1:${lastCol}${allData.length}`;
    const range = sheet.getRange(rangeAddress);
    range.values = allData;

    // Create table with auto-filter.
    const tableRange = sheet.getRange(rangeAddress);
    const table = sheet.tables.add(tableRange, true /* hasHeaders */);
    table.name = actualSheetName.replace(/[^a-zA-Z0-9]/g, "_");
    table.style = "TableStyleMedium2";

    // Format header row.
    const headerRange = sheet.getRange(`A1:${lastCol}1`);
    headerRange.format.font.bold = true;

    // Format amount columns with Swedish number format.
    if (amountColumns && amountColumns.length > 0) {
      for (const colName of amountColumns) {
        const colIndex = headers.indexOf(colName);
        if (colIndex >= 0) {
          const letter = colLetter(colIndex);
          const amountRange = sheet.getRange(
            `${letter}2:${letter}${allData.length}`,
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
          const letter = colLetter(colIndex);
          const pctRange = sheet.getRange(
            `${letter}2:${letter}${allData.length}`,
          );
          pctRange.numberFormat = [["0.0"]];
        }
      }
    }

    // Auto-fit all columns.
    range.format.autofitColumns();

    await context.sync();
  });

  return actualSheetName;
}

/**
 * Check if Excel/Office.js is available in the current environment.
 */
export function isExcelAvailable(): boolean {
  return typeof Excel !== "undefined" && typeof Excel.run === "function";
}
