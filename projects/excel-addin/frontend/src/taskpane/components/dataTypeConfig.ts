/**
 * Data type configuration — defines columns, presets, and settings
 * for each export type in the unified ExportPanel.
 */

export type DataType = "rr" | "br" | "lrk" | "krk" | "huvudbok";

export interface ColumnDef {
  /** Internal key used for API params and state tracking. */
  id: string;
  /** Swedish display name shown in UI and used as Excel header. */
  label: string;
  /** If true, always included and checkbox is disabled. */
  isFixed: boolean;
}

/** Quick-select preset for optional columns. */
export interface ColumnPreset {
  id: string;
  /** Swedish label shown on the preset button. */
  label: string;
  /** Which optional column IDs this preset selects (empty = none). */
  columnIds: string[];
}

export interface DataTypeConfig {
  id: DataType;
  /** Swedish label shown in the data type dropdown. */
  label: string;
  /** All possible columns (fixed + optional). */
  columns: ColumnDef[];
  /** Which filter section to render: "report", "invoice", or "huvudbok". */
  filterType: "report" | "invoice" | "huvudbok";
  /** Column labels that should be formatted as amounts in Excel. */
  amountColumns: string[];
  /** Column labels that should be formatted as percentages in Excel. */
  percentColumns: string[];
  /** Generate a default sheet name from current filter params. */
  defaultSheetName: (params: Record<string, string>) => string;
  /** Quick-select presets for optional columns. */
  presets: ColumnPreset[];
  /**
   * Whether the output format selector (flat vs report) is meaningful.
   * When false, the selector is hidden because both formats produce
   * identical output for this data type.
   */
  supportsOutputFormat: boolean;
}

export const DATA_TYPE_CONFIGS: Record<DataType, DataTypeConfig> = {
  rr: {
    id: "rr",
    label: "Resultaträkning",
    supportsOutputFormat: true,
    columns: [
      { id: "konto", label: "Konto", isFixed: true },
      { id: "kontonamn", label: "Kontonamn", isFixed: true },
      { id: "belopp", label: "Belopp", isFixed: true },
      { id: "cost_center", label: "Kostnadsställe", isFixed: false },
      { id: "project", label: "Projekt", isFixed: false },
      { id: "prior_year", label: "Föregående år", isFixed: false },
    ],
    filterType: "report",
    amountColumns: ["Belopp", "Föreg. år", "Förändring SEK"],
    percentColumns: ["Förändring %"],
    defaultSheetName: (p) => `RR ${p.fromPeriod || ""}–${p.toPeriod || ""}`,
    presets: [
      { id: "minimal", label: "Minimal", columnIds: [] },
      { id: "dimensions", label: "Med dimensioner", columnIds: ["cost_center", "project"] },
      { id: "comparison", label: "Jämförelse", columnIds: ["prior_year"] },
      {
        id: "all",
        label: "Alla",
        columnIds: ["cost_center", "project", "prior_year"],
      },
    ],
  },
  br: {
    id: "br",
    label: "Balansräkning",
    supportsOutputFormat: true,
    columns: [
      { id: "konto", label: "Konto", isFixed: true },
      { id: "kontonamn", label: "Kontonamn", isFixed: true },
      { id: "saldo", label: "Saldo", isFixed: true },
      { id: "cost_center", label: "Kostnadsställe", isFixed: false },
      { id: "project", label: "Projekt", isFixed: false },
      { id: "prior_year", label: "Föregående år", isFixed: false },
    ],
    filterType: "report",
    amountColumns: ["Saldo", "Föreg. år", "Förändring SEK"],
    percentColumns: ["Förändring %"],
    defaultSheetName: (p) => `BR ${p.toPeriod || ""}`,
    presets: [
      { id: "minimal", label: "Minimal", columnIds: [] },
      { id: "dimensions", label: "Med dimensioner", columnIds: ["cost_center", "project"] },
      { id: "comparison", label: "Jämförelse", columnIds: ["prior_year"] },
      {
        id: "all",
        label: "Alla",
        columnIds: ["cost_center", "project", "prior_year"],
      },
    ],
  },
  lrk: {
    id: "lrk",
    label: "Leverantörsreskontra",
    supportsOutputFormat: false,
    columns: [
      { id: "nr", label: "Nr", isFixed: true },
      { id: "leverantor", label: "Leverantör", isFixed: true },
      { id: "belopp", label: "Belopp", isFixed: true },
      { id: "leverantorsnr", label: "Leverantörsnr", isFixed: false },
      { id: "fakturanr", label: "Fakturanr", isFixed: false },
      { id: "fakturadatum", label: "Fakturadatum", isFixed: false },
      { id: "forfallodatum", label: "Förfallodatum", isFixed: false },
      { id: "status", label: "Status", isFixed: false },
      { id: "bokford", label: "Bokförd", isFixed: false },
      { id: "makulerad", label: "Makulerad", isFixed: false },
      { id: "cost_center", label: "Kostnadsställe", isFixed: false },
      { id: "project", label: "Projekt", isFixed: false },
      { id: "valuta", label: "Valuta", isFixed: false },
      { id: "saldo", label: "Saldo", isFixed: false },
      { id: "attesterad_av", label: "Attesterad av", isFixed: false },
      { id: "kommentar", label: "Kommentar", isFixed: false },
      { id: "var_referens", label: "Vår referens", isFixed: false },
      { id: "er_referens", label: "Er referens", isFixed: false },
    ],
    filterType: "invoice",
    amountColumns: ["Belopp", "Saldo"],
    percentColumns: [],
    defaultSheetName: () => "LRK",
    presets: [
      { id: "minimal", label: "Minimal", columnIds: [] },
      {
        id: "standard",
        label: "Standard",
        columnIds: ["forfallodatum", "status", "fakturanr"],
      },
      {
        id: "all",
        label: "Alla",
        columnIds: [
          "leverantorsnr", "fakturanr", "fakturadatum", "forfallodatum",
          "status", "bokford", "makulerad", "cost_center", "project",
          "valuta", "saldo", "attesterad_av", "kommentar",
          "var_referens", "er_referens",
        ],
      },
    ],
  },
  krk: {
    id: "krk",
    label: "Kundreskontra",
    supportsOutputFormat: false,
    columns: [
      { id: "dokumentnr", label: "Dokumentnr", isFixed: true },
      { id: "kund", label: "Kund", isFixed: true },
      { id: "belopp", label: "Belopp", isFixed: true },
      { id: "kundnr", label: "Kundnr", isFixed: false },
      { id: "fakturadatum", label: "Fakturadatum", isFixed: false },
      { id: "forfallodatum", label: "Förfallodatum", isFixed: false },
      { id: "status", label: "Status", isFixed: false },
      { id: "skickad", label: "Skickad", isFixed: false },
      { id: "bokford", label: "Bokförd", isFixed: false },
      { id: "makulerad", label: "Makulerad", isFixed: false },
      { id: "cost_center", label: "Kostnadsställe", isFixed: false },
      { id: "project", label: "Projekt", isFixed: false },
      { id: "valuta", label: "Valuta", isFixed: false },
      { id: "saldo", label: "Saldo", isFixed: false },
      { id: "kommentar", label: "Kommentar", isFixed: false },
      { id: "var_referens", label: "Vår referens", isFixed: false },
      { id: "er_referens", label: "Er referens", isFixed: false },
      { id: "er_ordernr", label: "Er ordernr", isFixed: false },
    ],
    filterType: "invoice",
    amountColumns: ["Belopp", "Saldo"],
    percentColumns: [],
    defaultSheetName: () => "KRK",
    presets: [
      { id: "minimal", label: "Minimal", columnIds: [] },
      {
        id: "standard",
        label: "Standard",
        columnIds: ["forfallodatum", "status", "fakturadatum"],
      },
      {
        id: "all",
        label: "Alla",
        columnIds: [
          "kundnr", "fakturadatum", "forfallodatum", "status",
          "skickad", "bokford", "makulerad", "cost_center", "project",
          "valuta", "saldo", "kommentar", "var_referens",
          "er_referens", "er_ordernr",
        ],
      },
    ],
  },
  huvudbok: {
    id: "huvudbok",
    label: "Huvudbok",
    supportsOutputFormat: true,
    columns: [
      { id: "konto", label: "Konto", isFixed: true },
      { id: "kontonamn", label: "Kontonamn", isFixed: true },
      { id: "datum", label: "Datum", isFixed: true },
      { id: "text", label: "Text", isFixed: true },
      { id: "debit", label: "Debit", isFixed: true },
      { id: "kredit", label: "Kredit", isFixed: true },
      { id: "saldo", label: "Saldo", isFixed: true },
      { id: "ver_serie", label: "Ver.serie", isFixed: false },
      { id: "ver_nr", label: "Ver.nr", isFixed: false },
      { id: "cost_center", label: "Kostnadsställe", isFixed: false },
      { id: "project", label: "Projekt", isFixed: false },
    ],
    filterType: "huvudbok",
    amountColumns: ["Debit", "Kredit", "Saldo"],
    percentColumns: [],
    defaultSheetName: (p) =>
      `Huvudbok ${p.fromAccount || "1000"}-${p.toAccount || "9999"}`,
    presets: [
      { id: "minimal", label: "Minimal", columnIds: [] },
      {
        id: "standard",
        label: "Standard",
        columnIds: ["ver_serie", "ver_nr"],
      },
      {
        id: "all",
        label: "Alla",
        columnIds: ["ver_serie", "ver_nr", "cost_center", "project"],
      },
    ],
  },
};

/** Status options for invoice filters. */
export const STATUS_OPTIONS = [
  { value: "booked", label: "Bokförd" },
  { value: "unbooked", label: "Ej bokförd" },
  { value: "unpaid", label: "Obetald" },
  { value: "fullypaid", label: "Betald" },
  { value: "cancelled", label: "Makulerad" },
  { value: "unpaidoverdue", label: "Förfallen" },
];
