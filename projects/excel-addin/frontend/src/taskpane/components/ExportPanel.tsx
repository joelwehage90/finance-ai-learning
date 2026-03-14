import React, { useEffect, useState } from "react";
import {
  Button,
  Checkbox,
  Field,
  Input,
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
    marginBottom: "8px",
  },
  fixedCol: {
    opacity: 0.6,
  },
  status: {
    marginTop: "12px",
    padding: "8px",
    borderRadius: "4px",
    backgroundColor: tokens.colorNeutralBackground3,
  },
  divider: {
    borderTop: `1px solid ${tokens.colorNeutralStroke1}`,
    marginTop: "12px",
    marginBottom: "12px",
  },
});

/** Generate period options (YYYY-01 through YYYY-12) for a year. */
function periodsForYear(fy: FinancialYear | null): string[] {
  if (!fy) return [];
  const year = fy.from_date.substring(0, 4);
  return Array.from({ length: 12 }, (_, i) => {
    const m = String(i + 1).padStart(2, "0");
    return `${year}-${m}`;
  });
}

const ExportPanel: React.FC = () => {
  const styles = useStyles();

  // --- Core state ---
  const [dataType, setDataType] = useState<DataType>("rr");
  const [selectedColumns, setSelectedColumns] = useState<Set<string>>(new Set());
  const [outputFormat, setOutputFormat] = useState<"datatabell" | "rapport">("datatabell");
  const [destination, setDestination] = useState<"replace" | "new">("replace");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  // --- Report filters (RR/BR/Huvudbok) ---
  const [years, setYears] = useState<FinancialYear[]>([]);
  const [selectedYear, setSelectedYear] = useState<FinancialYear | null>(null);
  const [fromPeriod, setFromPeriod] = useState("");
  const [toPeriod, setToPeriod] = useState("");

  // --- Huvudbok extra ---
  const [fromAccount, setFromAccount] = useState("1000");
  const [toAccount, setToAccount] = useState("9999");

  // --- Invoice filters (LRK/KRK) ---
  const [fromDate, setFromDate] = useState("");
  const [toDate, setToDate] = useState("");
  const [selectedStatuses, setSelectedStatuses] = useState<Set<string>>(new Set());

  const config: DataTypeConfig = DATA_TYPE_CONFIGS[dataType];
  const periods = periodsForYear(selectedYear);

  // Load financial years on mount.
  useEffect(() => {
    getFinancialYears()
      .then((data) => {
        setYears(data);
        if (data.length > 0) {
          setSelectedYear(data[0]);
          const year = data[0].from_date.substring(0, 4);
          setFromPeriod(`${year}-01`);
          setToPeriod(`${year}-03`);
        }
      })
      .catch((err) => setError(err.message));
  }, []);

  // Reset optional columns when data type changes.
  useEffect(() => {
    // Start with no optional columns selected.
    setSelectedColumns(new Set());
    setResult(null);
    setError(null);
  }, [dataType]);

  const handleYearChange = (yearId: string) => {
    const fy = years.find((y) => y.id === Number(yearId));
    if (fy) {
      setSelectedYear(fy);
      const year = fy.from_date.substring(0, 4);
      setFromPeriod(`${year}-01`);
      setToPeriod(`${year}-03`);
    }
  };

  const toggleColumn = (colId: string) => {
    setSelectedColumns((prev) => {
      const next = new Set(prev);
      if (next.has(colId)) {
        next.delete(colId);
      } else {
        next.add(colId);
      }
      return next;
    });
  };

  const toggleStatus = (status: string) => {
    setSelectedStatuses((prev) => {
      const next = new Set(prev);
      if (next.has(status)) {
        next.delete(status);
      } else {
        next.add(status);
      }
      return next;
    });
  };

  // --- Build dimension string from selected columns ---
  const getDimensionString = (): string | undefined => {
    const dims: number[] = [];
    if (selectedColumns.has("cost_center")) dims.push(1);
    if (selectedColumns.has("project")) dims.push(6);
    return dims.length > 0 ? dims.join(",") : undefined;
  };

  // --- Fetch and export handler ---
  const handleExport = async () => {
    if (!selectedYear && (config.filterType === "report" || config.filterType === "hovedbok")) {
      return;
    }

    setLoading(true);
    setError(null);
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
          // Flat endpoint — dimension columns + optional prior year.
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
          // Rapport format — structured with subtotals.
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
        // Build columns param from selected + fixed columns.
        const allCols = config.columns
          .filter((c) => c.isFixed || selectedColumns.has(c.id))
          .map((c) => c.label);

        const statusStr = selectedStatuses.size > 0
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
          // Strip IB/UB/separator rows for flat data mode.
          headers = data.headers;
          rows = data.rows.filter((r) => {
            if (r[0] === null) return false; // separator
            const text = r[5];
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

      // Build sheet name.
      const filterParams: Record<string, string> = {
        fromPeriod,
        toPeriod,
        fromAccount,
        toAccount,
      };
      const sheetName = config.defaultSheetName(filterParams);

      // Determine which amount/percent columns actually exist in headers.
      const amountCols = config.amountColumns.filter((c) => headers.includes(c));
      const pctCols = config.percentColumns.filter((c) => headers.includes(c));

      const writeOpts: WriteOptions = {
        destination,
        amountColumns: amountCols,
        percentColumns: pctCols.length > 0 ? pctCols : undefined,
      };

      if (isExcelAvailable()) {
        const actualName = await writeToSheet(sheetName, headers, rows, writeOpts);
        setResult(`${rowCount} rader skrivna till "${actualName}"`);
      } else {
        setResult(`${rowCount} rader hämtade (Excel ej tillgängligt)`);
        console.table(rows.slice(0, 30));
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Okänt fel");
    } finally {
      setLoading(false);
    }
  };

  // --- Determine if dimensions are available in current mode ---
  const isDimDisabled = (colId: string): boolean => {
    // Dimensions not supported in rapport mode for RR/BR.
    if (
      outputFormat === "rapport" &&
      (dataType === "rr" || dataType === "br") &&
      (colId === "cost_center" || colId === "project")
    ) {
      return true;
    }
    return false;
  };

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
                    <option key={p} value={p}>{p}</option>
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
                      <option key={p} value={p}>{p}</option>
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
          </div>
          <div className={styles.section}>
            <Text size={200} weight="medium">Status:</Text>
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
      {config.filterType === "hovedbok" && (
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
                    <option key={p} value={p}>{p}</option>
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
                    <option key={p} value={p}>{p}</option>
                  ))}
                </Select>
              </Field>
            </div>
          </div>
        </>
      )}

      <div className={styles.divider} />

      {/* --- Column checkboxes --- */}
      <div className={styles.section}>
        <Text size={200} weight="medium">Kolumner:</Text>
        <div className={styles.checkboxGroup}>
          {config.columns.map((col) => {
            const disabled = col.isFixed || isDimDisabled(col.id);
            return (
              <Checkbox
                key={col.id}
                label={col.isFixed ? `${col.label} (fast)` : col.label}
                size="medium"
                checked={col.isFixed || selectedColumns.has(col.id)}
                disabled={disabled}
                onChange={() => {
                  if (!col.isFixed && !isDimDisabled(col.id)) {
                    toggleColumn(col.id);
                  }
                }}
                className={col.isFixed ? styles.fixedCol : undefined}
              />
            );
          })}
        </div>
        {outputFormat === "rapport" &&
          (dataType === "rr" || dataType === "br") && (
            <Text size={100} style={{ color: tokens.colorNeutralForeground3 }}>
              Dimensioner kräver datatabellformat.
            </Text>
          )}
      </div>

      <div className={styles.divider} />

      {/* --- Output format --- */}
      <div className={styles.section}>
        <div className={styles.row}>
          <Field label="Format" size="small" style={{ flex: 1 }}>
            <Select
              size="small"
              value={outputFormat}
              onChange={(_, d) =>
                setOutputFormat(d.value as "datatabell" | "rapport")
              }
            >
              <option value="datatabell">Datatabell</option>
              <option value="rapport">Rapport (delsummor)</option>
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
              <option value="replace">Ersätt befintligt</option>
              <option value="new">Ny flik</option>
            </Select>
          </Field>
        </div>
      </div>

      {/* --- Export button --- */}
      <Button
        appearance="primary"
        icon={<ArrowDownloadRegular />}
        onClick={handleExport}
        disabled={loading}
        size="medium"
      >
        {loading ? <Spinner size="tiny" /> : "Exportera till Excel"}
      </Button>

      {/* --- Status messages --- */}
      {result && (
        <div className={styles.status}>
          <Text size={200}>{result}</Text>
        </div>
      )}
      {error && (
        <div
          className={styles.status}
          style={{ color: tokens.colorPaletteRedForeground1 }}
        >
          <Text size={200}>Fel: {error}</Text>
        </div>
      )}
    </div>
  );
};

export default ExportPanel;
