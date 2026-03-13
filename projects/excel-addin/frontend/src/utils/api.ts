/**
 * API client for the FastAPI backend.
 *
 * All endpoints return { headers: string[], rows: any[][], count: number }
 * for invoice data, or similar structures for reports.
 */

const API_BASE = "http://localhost:8000/api";

async function fetchJson<T>(path: string, params?: Record<string, string>): Promise<T> {
  const url = new URL(`${API_BASE}${path}`);
  if (params) {
    Object.entries(params).forEach(([k, v]) => {
      if (v) url.searchParams.set(k, v);
    });
  }

  const response = await fetch(url.toString());
  if (!response.ok) {
    const text = await response.text();
    throw new Error(`API error ${response.status}: ${text}`);
  }
  return response.json();
}

// ----------------------------------------------------------------
// Types
// ----------------------------------------------------------------

export interface FinancialYear {
  id: number;
  from_date: string;
  to_date: string;
  label: string;
}

export interface TableData {
  headers: string[];
  rows: (string | number | boolean | null)[][];
  count: number;
}

export interface ReportData {
  headers: string[];
  rows: (string | number | null)[][];
  period: string;
  total?: number;
  totals?: Record<string, number>;
}

// ----------------------------------------------------------------
// API functions
// ----------------------------------------------------------------

export async function getFinancialYears(): Promise<FinancialYear[]> {
  return fetchJson<FinancialYear[]>("/financial-years");
}

export async function getLRK(params: {
  from_date?: string;
  to_date?: string;
  statuses?: string;
}): Promise<TableData> {
  return fetchJson<TableData>("/lrk", params as Record<string, string>);
}

export async function getKRK(params: {
  from_date?: string;
  to_date?: string;
  statuses?: string;
}): Promise<TableData> {
  return fetchJson<TableData>("/krk", params as Record<string, string>);
}

export async function getRR(params: {
  financial_year_id: string;
  from_period: string;
  to_period: string;
}): Promise<ReportData> {
  return fetchJson<ReportData>("/rr", params);
}

export async function getBR(params: {
  financial_year_id: string;
  period: string;
}): Promise<ReportData> {
  return fetchJson<ReportData>("/br", params);
}

// ----------------------------------------------------------------
// Huvudbok
// ----------------------------------------------------------------

export async function getHuvudbok(params: {
  financial_year_id: string;
  from_account: string;
  to_account: string;
  from_period: string;
  to_period: string;
  cost_center?: string;
}): Promise<TableData> {
  return fetchJson<TableData>("/huvudbok", params as Record<string, string>);
}

// ----------------------------------------------------------------
// Comparative reports (vs prior year)
// ----------------------------------------------------------------

export async function getRRComparative(params: {
  financial_year_id: string;
  from_period: string;
  to_period: string;
}): Promise<ReportData> {
  return fetchJson<ReportData>("/rr-comparative", params);
}

export async function getBRComparative(params: {
  financial_year_id: string;
  period: string;
}): Promise<ReportData> {
  return fetchJson<ReportData>("/br-comparative", params);
}
