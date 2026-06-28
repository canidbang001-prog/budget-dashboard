// ─── 공통 타입 정의 (내부 사용) ──────────────────────────

/** 부서 요약 (summary API → 변환 후) */
export interface DepartmentSummary {
  dept: string;
  budget_amount: number;      // 당해예산 (천원)
  carryover: number;          // 이월예산 (천원)
  carryover_national: number;
  carryover_province: number;
  carryover_county: number;
  carryover_special: number;
  carryover_balance: number;
  carryover_other: number;
  finance_national: number;
  finance_province: number;
  finance_county: number;
  finance_special: number;
  finance_balance: number;
  finance_other: number;
  policy_count: number;
  unit_count: number;
}

/** 전체 요약 */
export interface SummaryData {
  total_budget: number;       // 당해예산 (천원)
  total_carryover: number;    // 이월예산 (천원)
  total_combined: number;     // 총계 = 당해 + 이월 (천원)
  department_count: number;
  total_nodes: number;        // 전체 노드 수
  departments: DepartmentSummary[];
}

/** 트리 노드 (tree API → 변환 후) */
export interface TreeNodeData {
  id: number;
  parent_id: number | null;
  depth: number;
  dept: string;
  policy: string;
  unit: string;
  detail: string;
  item_code: string;
  item_name: string;
  label: string;
  calc_name: string;
  budget_amount: number;      // 천원 단위 (총예산)
  budget_original: number;    // 본예산 (기준안)
  budget_modified: number;    // 변경예산
  carryover: number;          // 이월예산
  carryover_continued: number; // 계속비
  carryover_explicit: number;  // 명시이월
  carryover_accident: number;  // 사고이월
  carryover_national: number;
  carryover_province: number;
  carryover_county: number;
  carryover_special: number;
  carryover_balance: number;
  carryover_other: number;
  summary_text: string;       // 적요
  status: string;             // "추가"|"변동"|"동일"|"합계"
  finance_national: number;
  finance_province: number;
  finance_county: number;
  finance_special: number;
  finance_balance: number;
  finance_other: number;
  is_total: number;
  page: number;
  /** 자식 존재 여부 (children 배열 길이 > 0) */
  has_children: boolean;
  /** 실제 자식 노드 (lazy loading 후 채워짐) */
  children: TreeNodeData[];
}

/** 검색 결과 */
export interface SearchResultData {
  id: number;
  depth: number;
  dept: string;
  policy: string;
  unit: string;
  detail: string;
  item_name: string;
  calc_name: string;
  budget_amount: number;      // 천원 단위
  carryover_national: number;
  carryover_province: number;
  carryover_county: number;
  carryover_special: number;
  carryover_balance: number;
  carryover_other: number;
  page: number;
}

// ─── 유틸리티 ─────────────────────────────────────────────

export function getNodeLabel(node: TreeNodeData | SearchResultData): string {
  const n = node as TreeNodeData;
  // depth별 표시 필드 우선순위 (상위 → 하위):
  // d=0: dept | d=1: policy | d=2: unit | d=3: detail
  // d=4: label | d=5: item_name | d=6: calc_name(◎) | d=7: calc_name(○)
  if (n.depth === 0) return n.dept || '';
  if (n.depth === 1) return n.policy || '';
  if (n.depth === 2) return n.unit || '';
  if (n.depth === 3) return n.detail || n.unit || '';
  if (n.depth === 4) return n.label || n.detail || '';
  // d=5: item_name 우선, 없으면 label
  if (n.depth === 5) return n.item_name || n.label || '';
  // d=6/d=7: calc_name (◎/○ 마크는 API에서 _patch_tree_marks가 붙임)
  if (n.calc_name) return n.calc_name;
  if (n.item_name) return n.item_name;
  return n.detail || n.unit || '';
}

export function getNodePath(node: TreeNodeData | SearchResultData): string {
  const n = node as TreeNodeData;
  const parts = [n.policy, n.unit, n.detail, n.item_name, n.calc_name].filter(Boolean);
  return parts.join(' > ');
}
