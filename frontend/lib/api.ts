import type { SummaryData, TreeNodeData, SearchResultData } from '@/types';

// ─── API 설정 ──────────────────────────────────────────────

// DEV: NEXT_PUBLIC_API_BASE=http://localhost:3002 (.env.local)
// PROD: 빈 문자열 → window.location.origin (3003 통합본 same-origin)
const API_BASE = process.env.NEXT_PUBLIC_API_BASE || '';

async function fetchAPI<T>(path: string, params?: Record<string, string>): Promise<T> {
  const base = API_BASE || (typeof window !== 'undefined' ? window.location.origin : 'http://localhost:3003');
  const url = new URL(path, base);
  if (params) {
    Object.entries(params)
      .filter(([, v]) => v)
      .forEach(([k, v]) => url.searchParams.set(k, v));
  }
  // 10초 타임아웃
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 10_000);

  const handleSessionExpired = () => {
    alert('세션이 만료되었습니다. 다시 로그인해주세요.');
    window.location.href = '/login';
  };

  try {
    const res = await fetch(url.toString(), { signal: controller.signal });
    if (!res.ok) throw new Error(`API ${res.status}: ${res.statusText}`);

    // 세션 만료 감지: 302 → /login 리다이렉트 시 Content-Type이 JSON이 아닌 HTML 반환됨
    const contentType = res.headers.get('Content-Type') || '';
    if (!contentType.includes('application/json')) {
      handleSessionExpired();
      throw new Error('Session expired');
    }

    try {
      const data = await res.json();
      return data as T;
    } catch {
      // JSON 파싱 실패도 세션 만료로 간주 (HTML 응답 등)
      handleSessionExpired();
      throw new Error('Session expired');
    }
  } finally {
    clearTimeout(timer);
  }
}

// ─── Raw API 응답 타입 ─────────────────────────────────────

interface RawDeptNode {
  dept: string;
  total_budget: number;
  carryover?: number;
  carryover_national?: number;
  carryover_province?: number;
  carryover_county?: number;
  carryover_special?: number;
  carryover_balance?: number;
  carryover_other?: number;
  finance_national: number;
  finance_province: number;
  finance_county: number;
  finance_special: number;
  finance_balance: number;
  finance_other: number;
  policy_count: number;
  unit_count: number;
}

interface RawSummary {
  total_budget: number;          // 당해예산 (천원)
  total_carryover?: number;      // 이월예산 (천원)
  total_combined?: number;       // 총계 (천원)
  department_count: number;
  total_nodes: number;
  departments: RawDeptNode[];
}

interface RawTreeNode {
  id: number;
  parent_id: number | null;
  depth: number;
  dept: string;
  policy?: string;
  unit?: string;
  detail?: string;
  item_code?: string;
  item_name?: string;
  label?: string;
  calc_name?: string;
  budget_amount: number;         // 천원 (총예산)
  budget_original?: number;      // 본예산
  budget_modified?: number;      // 변경예산
  carryover?: number;            // 이월예산
  carryover_continued?: number;  // 계속비
  carryover_explicit?: number;   // 명시이월
  carryover_accident?: number;   // 사고이월
  carryover_national?: number;
  carryover_province?: number;
  carryover_county?: number;
  carryover_special?: number;
  carryover_balance?: number;
  carryover_other?: number;
  summary_text?: string;         // 적요
  status?: string;               // "추가"|"변동"|"동일"|"합계"
  finance_national: number;
  finance_province: number;
  finance_county: number;
  finance_special: number;
  finance_balance: number;
  finance_other: number;
  is_total: number;
  page?: number;
  children_count?: number;
  has_children?: boolean;
  children: RawTreeNode[];
}

interface RawTreeResponse {
  items: RawTreeNode[];
  total?: number;
}

interface RawSearchItem {
  id: number;
  depth: number;
  dept: string;
  policy?: string;
  unit?: string;
  detail?: string;
  item_name?: string;
  calc_name?: string;
  budget_amount: number;         // 천원
  carryover_national?: number;
  carryover_province?: number;
  carryover_county?: number;
  carryover_special?: number;
  carryover_balance?: number;
  carryover_other?: number;
  page?: number;
}

interface RawSearchResponse {
  items: RawSearchItem[];
}

// ─── 변환 유틸 (천원 단위 그대로 사용) ───────────────────

function mapTreeNode(raw: RawTreeNode): TreeNodeData {
  return {
    id: raw.id,
    parent_id: raw.parent_id ?? null,
    depth: raw.depth ?? 0,
    dept: raw.dept || '',
    policy: raw.policy || '',
    unit: raw.unit || '',
    detail: raw.detail || '',
    item_code: raw.item_code || '',
    item_name: raw.item_name || '',
    label: raw.label || '',
    calc_name: raw.calc_name || '',
    budget_amount: raw.budget_amount ?? 0,
    budget_original: raw.budget_original ?? 0,
    budget_modified: raw.budget_modified ?? 0,
    carryover: raw.carryover ?? 0,
    carryover_continued: raw.carryover_continued ?? 0,
    carryover_explicit: raw.carryover_explicit ?? 0,
    carryover_accident: raw.carryover_accident ?? 0,
    carryover_national: raw.carryover_national ?? 0,
    carryover_province: raw.carryover_province ?? 0,
    carryover_county: raw.carryover_county ?? 0,
    carryover_special: raw.carryover_special ?? 0,
    carryover_balance: raw.carryover_balance ?? 0,
    carryover_other: raw.carryover_other ?? 0,
    summary_text: raw.summary_text || '',
    status: raw.status || (raw.is_total === 1 ? '합계' : '동일'),
    finance_national: raw.finance_national ?? 0,
    finance_province: raw.finance_province ?? 0,
    finance_county: raw.finance_county ?? 0,
    finance_special: raw.finance_special ?? 0,
    finance_balance: raw.finance_balance ?? 0,
    finance_other: raw.finance_other ?? 0,
    is_total: raw.is_total ?? 0,
    page: raw.page ?? 0,
    has_children: (raw.children_count ? raw.children_count > 0 : (raw.children && raw.children.length > 0)),
    children: (raw.children || []).map(mapTreeNode),
  };
}

function mapSearchItem(raw: RawSearchItem): SearchResultData {
  return {
    id: raw.id,
    depth: raw.depth ?? 0,
    dept: raw.dept || '',
    policy: raw.policy || '',
    unit: raw.unit || '',
    detail: raw.detail || '',
    item_name: raw.item_name || '',
    calc_name: raw.calc_name || '',
    budget_amount: raw.budget_amount ?? 0,
    carryover_national: raw.carryover_national ?? 0,
    carryover_province: raw.carryover_province ?? 0,
    carryover_county: raw.carryover_county ?? 0,
    carryover_special: raw.carryover_special ?? 0,
    carryover_balance: raw.carryover_balance ?? 0,
    carryover_other: raw.carryover_other ?? 0,
    page: raw.page ?? 0,
  };
}

// ─── API 함수 ──────────────────────────────────────────────

export async function fetchSummary(): Promise<SummaryData> {
  const raw = await fetchAPI<RawSummary>('/api/summary');
  const departments = (raw.departments || []).map((d) => ({
    dept: d.dept,
    budget_amount: d.total_budget ?? 0,
    carryover: d.carryover ?? 0,
    carryover_national: d.carryover_national ?? 0,
    carryover_province: d.carryover_province ?? 0,
    carryover_county: d.carryover_county ?? 0,
    carryover_special: d.carryover_special ?? 0,
    carryover_balance: d.carryover_balance ?? 0,
    carryover_other: d.carryover_other ?? 0,
    finance_national: d.finance_national ?? 0,
    finance_province: d.finance_province ?? 0,
    finance_county: d.finance_county ?? 0,
    finance_special: d.finance_special ?? 0,
    finance_balance: d.finance_balance ?? 0,
    finance_other: d.finance_other ?? 0,
    policy_count: d.policy_count ?? 0,
    unit_count: d.unit_count ?? 0,
  }));
  return {
    total_budget: raw.total_budget ?? 0,
    total_carryover: raw.total_carryover ?? 0,
    total_combined: raw.total_combined ?? 0,
    department_count: raw.department_count ?? 0,
    total_nodes: raw.total_nodes ?? 0,
    departments,
  };
}

export async function fetchTree(dept: string): Promise<TreeNodeData[]> {
  const raw = await fetchAPI<RawTreeResponse>('/api/tree', { dept });
  return (raw.items || []).map(mapTreeNode);
}

export async function fetchChildren(parentId: number): Promise<TreeNodeData[]> {
  const raw = await fetchAPI<RawTreeResponse>(`/api/tree/children/${parentId}`);
  return (raw.items || []).map(mapTreeNode);
}

export async function fetchSearch(query: string): Promise<SearchResultData[]> {
  const raw = await fetchAPI<RawSearchResponse>('/api/search', { q: query });
  return (raw.items || []).map(mapSearchItem);
}
