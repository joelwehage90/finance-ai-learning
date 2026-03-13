import React, { useEffect, useState } from "react";
import {
  Button,
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
  getHuvudbok,
  type FinancialYear,
  type TableData,
} from "../../utils/api";
import { writeToSheet, isExcelAvailable } from "./ExcelWriter";

const useStyles = makeStyles({
  section: {
    marginBottom: "16px",
  },
  row: {
    display: "flex",
    gap: "8px",
    marginBottom: "8px",
  },
  status: {
    marginTop: "12px",
    padding: "8px",
    borderRadius: "4px",
    backgroundColor: tokens.colorNeutralBackground3,
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

const HuvudbokPanel: React.FC = () => {
  const styles = useStyles();

  const [years, setYears] = useState<FinancialYear[]>([]);
  const [selectedYear, setSelectedYear] = useState<FinancialYear | null>(null);
  const [fromPeriod, setFromPeriod] = useState("");
  const [toPeriod, setToPeriod] = useState("");
  const [fromAccount, setFromAccount] = useState("1000");
  const [toAccount, setToAccount] = useState("9999");
  const [costCenter, setCostCenter] = useState("");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

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

  const periods = periodsForYear(selectedYear);

  const handleYearChange = (yearId: string) => {
    const fy = years.find((y) => y.id === Number(yearId));
    if (fy) {
      setSelectedYear(fy);
      const year = fy.from_date.substring(0, 4);
      setFromPeriod(`${year}-01`);
      setToPeriod(`${year}-03`);
    }
  };

  const handleFetch = async () => {
    if (!selectedYear) return;

    setLoading(true);
    setError(null);
    setResult(null);

    try {
      const data: TableData = await getHuvudbok({
        financial_year_id: String(selectedYear.id),
        from_account: fromAccount,
        to_account: toAccount,
        from_period: fromPeriod,
        to_period: toPeriod,
        cost_center: costCenter || undefined,
      });

      const sheetName = `Huvudbok ${fromAccount}-${toAccount} ${fromPeriod}`;
      const amountCols = ["Debit", "Kredit", "Saldo"];

      if (isExcelAvailable()) {
        await writeToSheet(sheetName, data.headers, data.rows, amountCols);
        setResult(
          `${data.count} rader skrivna till ark "${sheetName}"`
        );
      } else {
        setResult(
          `${data.count} rader hämtade (Excel ej tillgängligt)`
        );
        console.table(data.rows.slice(0, 30));
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Okänt fel");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div>
      <Text size={400} weight="semibold" block style={{ marginBottom: 12 }}>
        Huvudbok
      </Text>

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

      <div className={styles.section}>
        <Field label="Kostnadsställe (valfritt)" size="small">
          <Input
            size="small"
            placeholder="T.ex. SALJ"
            value={costCenter}
            onChange={(_, d) => setCostCenter(d.value)}
          />
        </Field>
      </div>

      <Button
        appearance="primary"
        icon={<ArrowDownloadRegular />}
        onClick={handleFetch}
        disabled={loading || !selectedYear}
        size="medium"
      >
        {loading ? <Spinner size="tiny" /> : "Hämta till Excel"}
      </Button>

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

export default HuvudbokPanel;
