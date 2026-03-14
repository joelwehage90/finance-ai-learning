import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Button,
  Checkbox,
  Field,
  Input,
  MessageBar,
  MessageBarBody,
  Select,
  Spinner,
  Text,
  makeStyles,
  tokens,
} from "@fluentui/react-components";
import { ArrowDownloadRegular } from "@fluentui/react-icons";
import {
  getFinancialYears,
  getLRK,
  getKRK,
  getRR,
  getBR,
  getRRComparative,
  getBRComparative,
  getRRFlat,
  getBRFlat,
  getHuvudbok,
  type FinancialYear,
  type TableData,
  type ReportData,
} from "../../utils/api";
import { writeToSheet, isExcelAvailable, type WriteOptions } from "./ExcelWriter";
import {
  DATA_TYPE_CONFIGS,
  STATUS_OPTIONS,
  type DataType,
  type DataTypeConfig,
} from "./dataTypeConfig";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Today as YYYY-MM-DD. */
function todayStr(): string {
  return new Date().toISOString().slice(0, 10);
}

/** First day of current month as YYYY-MM-DD. */
function firstOfMonthStr(): string {
  const d = new Date();
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  return `${y}-${m}-01`;
}

/** Current period as YYYY-MM. */
function currentPeriod(): string {
  return todayStr().slice(0, 7);
}

/** Generate period options for a financial year. */
function periodsForYear(fy: FinancialYear | null): string[] {
  if (!fy) return [];
  const from = new Date(fy.from_date);
  const to = new Date(fy.to_date);
  const periods: string[] = [];
  const cur = new Date(from.getFullYear(), from.getMonth(), 1);
  while (cur <= to) {
    const y = cur.getFullYear();
    const m = String(cur.getMonth() + 1).padStart(2, "0");
    periods.push(`${y}-${m}`);
    cur.setMonth(cur.getMonth() + 1);
  }
  return periods;
}

/** Compute a smart default "to period" for a financial year. */
function smartToPeriod(fy: FinancialYear): string {
  const fyYear = fy.from_date.substring(0, 4);
  const now = new Date();
  const nowYear = String(now.getFullYear());
  if (fyYear === nowYear) {
    // Current year: use current month.
    return currentPeriod();
  }
  // Prior year: use last month of the financial year.
  const to = new Date(fy.to_date);
  const m = String(to.getMonth() + 1).padStart(2, "0");
  return `${to.getFullYear()}-${m}`;
}

// ---------------------------------------------------------------------------
// Styles
// ---------------------------------------------------------------------------

const useStyles = makeStyles({
  section: {
    marginBottom: "12px",
  },
  row: {
    display: "flex",
    gap: "8px",
    marginBottom: "8px",
  },
  checkboxGroup: {
    display: "flex",
    flexDirection: "column",
    gap: "2px",
    marginTop: "4px",
    marginBottom: "4px",
  },
  divider: {
    borderTop: `1px solid ${tokens.colorNeutralStroke1}`,
    marginTop: "12px",
    marginBottom: "12px",
  },
  fixedColsList: {
    fontSize: "12px",
    color: tokens.colorNeutralForeground3,
    marginBottom: "8px",
  },
  presetRow: {
    display: "flex",
    gap: "4px",
    flexWrap: "wrap" as const,
    marginBottom: "8px",
  },
  columnCounter: {
    fontSize: "11px",
    color: tokens.colorNeutralForeground3,
    marginTop: "2px",
  },
  stickyFooter: {
    position: "sticky" as const,
    bottom: 0,
    backgroundColor: tokens.colorNeutralBackground1,
    paddingTop: "8px",
    paddingBottom: "8px",
    borderTop: `1px solid ${tokens.colorNeutralStroke1}`,
    marginTop: "8px",
  },
  sheetPreview: {
    fontSize: "12px",
    color: tokens.colorNeutralForeground3,
    marginBottom: "8px",
  },
  centerBox: {
    display: "flex",
    flexDirection: "column" as const,
    alignItems: "center",
    justifyContent: "center",
    minHeight: "200px",
    gap: "16px",
    textAlign: "center" as const,
  },
  hint: {
    fontSize: "11px",
    color: tokens.colorNeutralForeground3,
    marginTop: "2px",
  },
});

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

const ExportPanel: React.FC = () => {
  const styles = useStyles();

  // --- Initial loading state (improvement 1) ---
  const [initialLoading, setInitialLoading] = useState(true);
  const [apiError, setApiError] = useState<string | null>(null);

  // --- Core state ---
  const [dataType, setDataType] = useState<DataType>("rr");
  const [selectedColumns, setSelectedColumns] = useState<Set<string>>(new Set());
  const [outputFormat, setOutputFormat] = useState<"datatabell" | "rapport">("datatabell");
  const [destination, setDestination] = useState<"replace" | "new">("new"); // Improvement 9: default "new"
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<{ text: string; intent: "success" | "warning" | "error" } | null>(null);

  // --- Report filters (RR/BR/Huvudbok) ---
  const [years, setYears] = useState<FinancialYear[]>([]);
  const [selectedYear, setSelectedYear] = useState<FinancialYear | null>(null);
  const [fromPeriod, setFromPeriod] = useState("");
  const [toPeriod, setToPeriod] = useState("");

  // --- Huvudbok extra ---
  const [fromAccount, setFromAccount] = useState("1000");
  const [toAccount, setToAccount] = useState("9999");

  // --- Invoice filters (LRK/KRK) ---
  const [fromDate, setFromDate] = useState(firstOfMonthStr); // Improvement 10
  const [toDate, setToDate] = useState(todayStr); // Improvement 10
  const [selectedStatuses, setSelectedStatuses] = useState<Set<string>>(new Set());

  // --- Auto-dismiss timer for success messages (improvement 8) ---
  const dismissTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const config: DataTypeConfig = DATA_TYPE_CONFIGS[dataType];
  const periods = useMemo(() => periodsForYear(selectedYear), [selectedYear]);
  const optionalColumns = useMemo(() => config.columns.filter((c) => !c.isFixed), [config]);
  const fixedColumns = useMemo(() => config.columns.filter((c) => c.isFixed), [config]);

  // --- Load financial years on mount (improvement 1) ---
  const loadYears = useCallback(async () => {
    setInitialLoading(true);
    setApiError(null);
    try {
      const data = await getFinancialYears();
      setYears(data);
      if (data.length > 0) {
        const fy = data[0];
        setSelectedYear(fy);
        const year = fy.from_date.substring(0, 4);
        setFromPeriod(`${year}-01`);
        setToPeriod(smartToPeriod(fy));
      }
    } catch (err) {
      setApiError(err instanceof Error ? err.message : "Okänt fel");
    } finally {
      setInitialLoading(false);
    }
  }, []);

  useEffect(() => {
    loadYears();
  }, [loadYears]);

  // Reset optional columns when data type changes.
  useEffect(() => {
    setSelectedColumns(new Set());
    setResult(null);
  }, [dataType]);

  // Clear dismiss timer on unmount.
  useEffect(() => {
    return () => {
      if (dismissTimer.current) clearTimeout(dismissTimer.current);
    };
  }, []);

  // --- Handlers ---

  const handleYearChange = (yearId: string) => {
    const fy = years.find((y) => y.id === Number(yearId));
    if (fy) {
      setSelectedYear(fy);
      const year = fy.from_date.substring(0, 4);
      setFromPeriod(`${year}-01`);
      setToPeriod(smartToPeriod(fy));
    }
  };

  const toggleColumn = useCallback((colId: string) => {
    setSelectedColumns((prev) => {
      const next = new Set(prev);
      if (next.has(colId)) {
        next.delete(colId);
      } else {
        next.add(colId);
      }
      return next;
    });
  }, []);

  const toggleStatus = useCallback((status: string) => {
    setSelectedStatuses((prev) => {
      const next = new Set(prev);
      if (next.has(status)) {
        next.delete(status);
      } else {
        next.add(status);
      }
      return next;
    });
  }, []);

  const applyPreset = (columnIds: string[]) => {
    // Filter by what is actually available (respecting dim-disabled state).
    const allowed = columnIds.filter((id) => !disabledCols.has(id));
    setSelectedColumns(new Set(allowed));
  };

  const selectAllOptional = () => {
    const ids = optionalColumns
      .filter((c) => !disabledCols.has(c.id))
      .map((c) => c.id);
    setSelectedColumns(new Set(ids));
  };

  const clearAllOptional = () => {
    setSelectedColumns(new Set());
  };

  // --- Improvement 3: actively deselect dims when switching to rapport ---
  const handleFormatChange = (fmt: "datatabell" | "rapport") => {
    setOutputFormat(fmt);
    if (fmt === "rapport" && (dataType === "rr" || dataType === "br")) {
      setSelectedColumns((prev) => {
        const next = new Set(prev);
        next.delete("cost_center");
        next.delete("project");
        return next;
      });
    }
  };

  // --- Dimension disabled check (memoized as a Set) ---
  const disabledCols = useMemo((): Set<string> => {
    if (outputFormat === "rapport" && (dataType === "rr" || dataType === "br")) {
      return new Set(["cost_center", "project"]);
    }
    return new Set();
  }, [outputFormat, dataType]);

  // --- Build dimension string from selected columns ---
  const getDimensionString = (): string | undefined => {
    const dims: number[] = [];
    if (selectedColumns.has("cost_center")) dims.push(1);
    if (selectedColumns.has("project")) dims.push(6);
    return dims.length > 0 ? dims.join(",") : undefined;
  };

  // --- Validation (improvement 2) ---
  const validationError = useMemo((): string | null => {
    if (config.filterType === "report" || config.filterType === "huvudbok") {
      // Period range check (only when both periods are used).
      if (dataType !== "br" && fromPeriod && toPeriod && fromPeriod > toPeriod) {
        return "Från-period kan inte vara efter till-period";
      }
      if (!selectedYear) {
        return "Välj ett räkenskapsår";
      }
    }
    if (config.filterType === "huvudbok") {
      if (Number(fromAccount) > Number(toAccount)) {
        return "Från-konto kan inte vara större än till-konto";
      }
    }
    if (config.filterType === "invoice") {
      if (fromDate && toDate && fromDate > toDate) {
        return "Från-datum kan inte vara efter till-datum";
      }
    }
    return null;
  }, [config.filterType, dataType, fromPeriod, toPeriod, fromAccount, toAccount, fromDate, toDate, selectedYear]);

  // --- Computed sheet name (improvement 8 + 9) ---
  const computedSheetName = useMemo((): string => {
    const filterParams: Record<string, string> = {
      fromPeriod,
      toPeriod,
      fromAccount,
      toAccount,
    };
    return config.defaultSheetName(filterParams);
  }, [config, fromPeriod, toPeriod, fromAccount, toAccount]);

  // --- Set result with auto-dismiss for success (improvement 8) ---
  const showResult = useCallback((text: string, intent: "success" | "warning" | "error") => {
    if (dismissTimer.current) clearTimeout(dismissTimer.current);
    setResult({ text, intent });
    if (intent === "success") {
      dismissTimer.current = setTimeout(() => setResult(null), 8000);
    }
  }, []);

  // --- Export handler ---
  const handleExport = async () => {
    if (validationError) return;

    setLoading(true);
    setResult(null);

    try {
      let headers: string[] = [];
      let rows: (string | number | boolean | null)[][] = [];
      let rowCount = 0;

      const yearId = selectedYear ? String(selectedYear.id) : "";
      const hasPriorYear = selectedColumns.has("prior_year");
      const dimString = getDimensionString();

      if (dataType === "rr" || dataType === "br") {
        if (outputFormat === "datatabell") {
          let data: TableData;
          if (dataType === "rr") {
            data = await getRRFlat({
              financial_year_id: yearId,
              from_period: fromPeriod,
              to_period: toPeriod,
              dimensions: dimString,
              include_prior_year: hasPriorYear ? "true" : undefined,
            });
          } else {
            data = await getBRFlat({
              financial_year_id: yearId,
              period: toPeriod,
              dimensions: dimString,
              include_prior_year: hasPriorYear ? "true" : undefined,
            });
          }
          headers = data.headers;
          rows = data.rows;
          rowCount = data.count;
        } else {
          let data: ReportData;
          if (dataType === "rr") {
            data = hasPriorYear
              ? await getRRComparative({
                  financial_year_id: yearId,
                  from_period: fromPeriod,
                  to_period: toPeriod,
                })
              : await getRR({
                  financial_year_id: yearId,
                  from_period: fromPeriod,
                  to_period: toPeriod,
                });
          } else {
            data = hasPriorYear
              ? await getBRComparative({
                  financial_year_id: yearId,
                  period: toPeriod,
                })
              : await getBR({
                  financial_year_id: yearId,
                  period: toPeriod,
                });
          }
          headers = data.headers;
          rows = data.rows;
          rowCount = data.rows.length;
        }
      } else if (dataType === "lrk" || dataType === "krk") {
        const allCols = config.columns
          .filter((c) => c.isFixed || selectedColumns.has(c.id))
          .map((c) => c.label);

        const statusStr =
          selectedStatuses.size > 0
            ? Array.from(selectedStatuses).join(",")
            : undefined;

        const fetchFn = dataType === "lrk" ? getLRK : getKRK;
        const data = await fetchFn({
          from_date: fromDate || undefined,
          to_date: toDate || undefined,
          statuses: statusStr,
          columns: allCols.join(","),
        });
        headers = data.headers;
        rows = data.rows;
        rowCount = data.count;
      } else if (dataType === "huvudbok") {
        const data = await getHuvudbok({
          financial_year_id: yearId,
          from_account: fromAccount,
          to_account: toAccount,
          from_period: fromPeriod,
          to_period: toPeriod,
          include_dimensions: dimString,
        });

        if (outputFormat === "datatabell") {
          headers = data.headers;
          const textIdx = data.headers.indexOf("Text");
          rows = data.rows.filter((r) => {
            if (r[0] === null) return false;
            const text = textIdx >= 0 ? r[textIdx] : null;
            if (text === "Ingående balans" || text === "Utgående balans") return false;
            return true;
          });
          rowCount = rows.length;
        } else {
          headers = data.headers;
          rows = data.rows;
          rowCount = data.count;
        }
      }

      // Handle zero rows as warning.
      if (rowCount === 0) {
        showResult("Inga rader hittades för vald period och filter", "warning");
        return;
      }

      const amountCols = config.amountColumns.filter((c) => headers.includes(c));
      const pctCols = config.percentColumns.filter((c) => headers.includes(c));

      const writeOpts: WriteOptions = {
        destination,
        amountColumns: amountCols,
        percentColumns: pctCols.length > 0 ? pctCols : undefined,
      };

      if (isExcelAvailable()) {
        const actualName = await writeToSheet(computedSheetName, headers, rows, writeOpts);
        showResult(`${rowCount} rader skrivna till "${actualName}"`, "success");
      } else {
        showResult(`${rowCount} rader hämtade (Excel ej tillgängligt)`, "success");
        console.table(rows.slice(0, 30));
      }
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Okänt fel";
      // Translate common API errors to Swedish.
      if (msg.includes("Failed to fetch") || msg.includes("NetworkError")) {
        showResult("Kunde inte nå servern — kontrollera anslutningen", "error");
      } else if (msg.includes("API error")) {
        showResult(`Serverfel: ${msg.replace("API error ", "")}`, "error");
      } else {
        showResult(`Fel: ${msg}`, "error");
      }
    } finally {
      setLoading(false);
    }
  };

  // --- Improvement 1: Loading state on initial mount ---
  if (initialLoading) {
    return (
      <div className={styles.centerBox}>
        <Spinner size="medium" label="Laddar räkenskapsår..." />
      </div>
    );
  }

  if (apiError) {
    return (
      <div className={styles.centerBox}>
        <Text size={300} weight="semibold">
          Kunde inte ansluta
        </Text>
        <Text size={200}>{apiError}</Text>
        <Button appearance="primary" onClick={loadYears}>
          Försök igen
        </Button>
      </div>
    );
  }

  // --- Count selected optional columns ---
  const selectedOptCount = optionalColumns.filter(
    (c) => selectedColumns.has(c.id),
  ).length;

  return (
    <div>
      <Text size={400} weight="semibold" block style={{ marginBottom: 12 }}>
        Exportera data
      </Text>

      {/* --- Data type selector --- */}
      <div className={styles.section}>
        <Field label="Datatyp" size="small">
          <Select
            size="small"
            value={dataType}
            onChange={(_, d) => setDataType(d.value as DataType)}
          >
            <option value="rr">Resultaträkning</option>
            <option value="br">Balansräkning</option>
            <option value="lrk">Leverantörsreskontra</option>
            <option value="krk">Kundreskontra</option>
            <option value="huvudbok">Huvudbok</option>
          </Select>
        </Field>
      </div>

      {/* --- Report filters (RR / BR) --- */}
      {config.filterType === "report" && (
        <>
          <div className={styles.section}>
            <Field label="Räkenskapsår" size="small">
              <Select
                size="small"
                value={selectedYear ? String(selectedYear.id) : ""}
                onChange={(_, d) => handleYearChange(d.value)}
              >
                {years.map((fy) => (
                  <option key={fy.id} value={fy.id}>
                    {fy.label}
                  </option>
                ))}
              </Select>
            </Field>
          </div>
          <div className={styles.section}>
            <div className={styles.row}>
              <Field label="Från period" size="small" style={{ flex: 1 }}>
                <Select
                  size="small"
                  value={fromPeriod}
                  onChange={(_, d) => setFromPeriod(d.value)}
                >
                  {periods.map((p) => (
                    <option key={p} value={p}>
                      {p}
                    </option>
                  ))}
                </Select>
              </Field>
              {dataType === "rr" && (
                <Field label="Till period" size="small" style={{ flex: 1 }}>
                  <Select
                    size="small"
                    value={toPeriod}
                    onChange={(_, d) => setToPeriod(d.value)}
                  >
                    {periods.map((p) => (
                      <option key={p} value={p}>
                        {p}
                      </option>
                    ))}
                  </Select>
                </Field>
              )}
            </div>
          </div>
        </>
      )}

      {/* --- Invoice filters (LRK / KRK) --- */}
      {config.filterType === "invoice" && (
        <>
          <div className={styles.section}>
            <div className={styles.row}>
              <Field label="Från datum" size="small" style={{ flex: 1 }}>
                <Input
                  size="small"
                  type="date"
                  value={fromDate}
                  onChange={(_, d) => setFromDate(d.value)}
                />
              </Field>
              <Field label="Till datum" size="small" style={{ flex: 1 }}>
                <Input
                  size="small"
                  type="date"
                  value={toDate}
                  onChange={(_, d) => setToDate(d.value)}
                />
              </Field>
            </div>
            <div className={styles.hint}>
              Lämna tomt för alla fakturor
            </div>
          </div>
          <div className={styles.section}>
            <Text size={200} weight="medium">
              Status:
            </Text>
            <div className={styles.checkboxGroup}>
              {STATUS_OPTIONS.map((opt) => (
                <Checkbox
                  key={opt.value}
                  label={opt.label}
                  size="medium"
                  checked={selectedStatuses.has(opt.value)}
                  onChange={() => toggleStatus(opt.value)}
                />
              ))}
            </div>
          </div>
        </>
      )}

      {/* --- Huvudbok filters --- */}
      {config.filterType === "huvudbok" && (
        <>
          <div className={styles.section}>
            <Field label="Räkenskapsår" size="small">
              <Select
                size="small"
                value={selectedYear ? String(selectedYear.id) : ""}
                onChange={(_, d) => handleYearChange(d.value)}
              >
                {years.map((fy) => (
                  <option key={fy.id} value={fy.id}>
                    {fy.label}
                  </option>
                ))}
              </Select>
            </Field>
          </div>
          <div className={styles.section}>
            <div className={styles.row}>
              <Field label="Från konto" size="small" style={{ flex: 1 }}>
                <Input
                  size="small"
                  type="number"
                  value={fromAccount}
                  onChange={(_, d) => setFromAccount(d.value)}
                />
              </Field>
              <Field label="Till konto" size="small" style={{ flex: 1 }}>
                <Input
                  size="small"
                  type="number"
                  value={toAccount}
                  onChange={(_, d) => setToAccount(d.value)}
                />
              </Field>
            </div>
          </div>
          <div className={styles.section}>
            <div className={styles.row}>
              <Field label="Från period" size="small" style={{ flex: 1 }}>
                <Select
                  size="small"
                  value={fromPeriod}
                  onChange={(_, d) => setFromPeriod(d.value)}
                >
                  {periods.map((p) => (
                    <option key={p} value={p}>
                      {p}
                    </option>
                  ))}
                </Select>
              </Field>
              <Field label="Till period" size="small" style={{ flex: 1 }}>
                <Select
                  size="small"
                  value={toPeriod}
                  onChange={(_, d) => setToPeriod(d.value)}
                >
                  {periods.map((p) => (
                    <option key={p} value={p}>
                      {p}
                    </option>
                  ))}
                </Select>
              </Field>
            </div>
          </div>
        </>
      )}

      <div className={styles.divider} />

      {/* --- Improvement 3: Format + Destination BEFORE columns --- */}
      <div className={styles.section}>
        <div className={styles.row}>
          <Field label="Exportformat" size="small" style={{ flex: 1 }}>
            <Select
              size="small"
              value={outputFormat}
              onChange={(_, d) =>
                handleFormatChange(d.value as "datatabell" | "rapport")
              }
            >
              <option value="datatabell">Platt data</option>
              <option value="rapport">Rapport med delsummor</option>
            </Select>
          </Field>
          <Field label="Destination" size="small" style={{ flex: 1 }}>
            <Select
              size="small"
              value={destination}
              onChange={(_, d) =>
                setDestination(d.value as "replace" | "new")
              }
            >
              <option value="new">Ny flik</option>
              <option value="replace">Ersätt befintlig</option>
            </Select>
          </Field>
        </div>
        {/* Improvement 9: warning when replace is selected */}
        {destination === "replace" && (
          <div className={styles.hint} style={{ color: tokens.colorPaletteYellowForeground2 }}>
            Befintlig flik med samma namn skrivs över
          </div>
        )}
      </div>

      <div className={styles.divider} />

      {/* --- Improvement 4: Structured column selection --- */}
      <div className={styles.section}>
        <Text size={200} weight="medium" block>
          Kolumner
        </Text>

        {/* Fixed columns as non-interactive text */}
        <div className={styles.fixedColsList}>
          Inkluderas alltid: {fixedColumns.map((c) => c.label).join(", ")}
        </div>

        {/* Preset buttons */}
        {config.presets.length > 0 && (
          <div className={styles.presetRow}>
            {config.presets.map((preset) => (
              <Button
                key={preset.id}
                size="small"
                appearance="subtle"
                onClick={() => applyPreset(preset.columnIds)}
                style={{
                  minWidth: 0,
                  padding: "2px 8px",
                  fontSize: "11px",
                }}
              >
                {preset.label}
              </Button>
            ))}
          </div>
        )}

        {/* Optional columns as checkboxes */}
        {optionalColumns.length > 0 && (
          <>
            <div className={styles.checkboxGroup}>
              {optionalColumns.map((col) => {
                const disabled = disabledCols.has(col.id);
                return (
                  <Checkbox
                    key={col.id}
                    label={col.label}
                    size="medium"
                    checked={selectedColumns.has(col.id)}
                    disabled={disabled}
                    onChange={() => {
                      if (!disabled) toggleColumn(col.id);
                    }}
                  />
                );
              })}
            </div>

            {/* Select all / Clear + counter */}
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <div style={{ display: "flex", gap: "8px" }}>
                <Button
                  size="small"
                  appearance="transparent"
                  onClick={selectAllOptional}
                  style={{ minWidth: 0, padding: "0 4px", fontSize: "11px" }}
                >
                  Välj alla
                </Button>
                <Button
                  size="small"
                  appearance="transparent"
                  onClick={clearAllOptional}
                  style={{ minWidth: 0, padding: "0 4px", fontSize: "11px" }}
                >
                  Rensa
                </Button>
              </div>
              <div className={styles.columnCounter}>
                {selectedOptCount} av {optionalColumns.length} valbara
              </div>
            </div>
          </>
        )}

        {/* Dim disabled note for rapport mode */}
        {outputFormat === "rapport" &&
          (dataType === "rr" || dataType === "br") && (
            <div className={styles.hint}>
              Dimensioner kräver platt data-format.
            </div>
          )}
      </div>

      {/* --- Sticky export section (improvement 8) --- */}
      <div className={styles.stickyFooter}>
        {/* Validation warning (improvement 2) */}
        {validationError && (
          <MessageBar intent="warning" style={{ marginBottom: 8 }}>
            <MessageBarBody>{validationError}</MessageBarBody>
          </MessageBar>
        )}

        {/* Sheet name preview (improvement 8 + 9) */}
        <div className={styles.sheetPreview}>
          Exporteras till: <strong>{computedSheetName}</strong>
        </div>

        {/* Export button (improvement 8) */}
        <Button
          appearance="primary"
          icon={loading ? undefined : <ArrowDownloadRegular />}
          onClick={handleExport}
          disabled={loading || !!validationError}
          size="medium"
          style={{ width: "100%" }}
        >
          {loading ? (
            <>
              <Spinner size="tiny" style={{ marginRight: 6 }} />
              Hämtar data...
            </>
          ) : (
            "Exportera till Excel"
          )}
        </Button>

        {/* Result message (improvement 8) */}
        {result && (
          <MessageBar
            intent={result.intent}
            style={{ marginTop: 8 }}
          >
            <MessageBarBody>{result.text}</MessageBarBody>
          </MessageBar>
        )}
      </div>
    </div>
  );
};

export default ExportPanel;
