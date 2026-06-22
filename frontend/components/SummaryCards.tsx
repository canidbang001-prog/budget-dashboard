'use client';

import type { SummaryData } from '@/types';

// ─── 포맷 유틸 ─────────────────────────────────────────────

function formatBudget(amount: number): string {
  if (amount >= 100000) {
    const eok = Math.floor(amount / 100000);
    const man = Math.floor((amount % 100000) / 10);
    if (man > 0) return `${eok.toLocaleString()}억 ${man.toLocaleString()}만원`;
    return `${eok.toLocaleString()}억원`;
  }
  return `${Math.floor(amount / 10).toLocaleString()}만원`;
}

// ─── 컴포넌트 ──────────────────────────────────────────────

interface Props {
  data: SummaryData | null;
  loading: boolean;
}

export default function SummaryCards({ data, loading }: Props) {
  if (loading || !data) {
    return (
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 mb-6">
        {[1, 2, 3].map((i) => (
          <div key={i} className="bg-white rounded-lg shadow-sm p-5 animate-pulse">
            <div className="h-3 bg-slate-200 rounded w-20 mb-3" />
            <div className="h-7 bg-slate-200 rounded w-32" />
          </div>
        ))}
      </div>
    );
  }

  return (
    <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 mb-6">
      {/* ── 총 예산 카드 (3단) ── */}
      <div className="bg-white rounded-lg shadow-sm p-5 border border-slate-100 hover:shadow-md transition-shadow">
        <div className="flex items-center gap-2 mb-3">
          <span className="text-xl">💰</span>
          <span className="text-xs font-medium text-slate-500 uppercase tracking-wide">총 예산</span>
        </div>
        <div className="space-y-1">
          <div className="flex justify-between text-xs text-slate-500">
            <span>당해예산</span>
            <span className="font-mono text-slate-600">{formatBudget(data.total_budget)}</span>
          </div>
          <div className="flex justify-between text-xs text-amber-600">
            <span>이월예산</span>
            <span className="font-mono">{formatBudget(data.total_carryover)}</span>
          </div>
          <div className="border-t border-slate-100 pt-1 mt-1 flex justify-between text-sm font-bold text-blue-600">
            <span>총계</span>
            <span>{formatBudget(data.total_combined)}</span>
          </div>
        </div>
      </div>

      {/* ── 부서 수 ── */}
      <div className="bg-white rounded-lg shadow-sm p-5 border border-slate-100 hover:shadow-md transition-shadow">
        <div className="flex items-center gap-2 mb-2">
          <span className="text-xl">🏢</span>
          <span className="text-xs font-medium text-slate-500 uppercase tracking-wide">부서 수</span>
        </div>
        <div className="text-lg sm:text-xl font-bold text-emerald-600">
          {data.department_count.toLocaleString()}개
        </div>
      </div>

      {/* ── 전체 노드 수 ── */}
      <div className="bg-white rounded-lg shadow-sm p-5 border border-slate-100 hover:shadow-md transition-shadow">
        <div className="flex items-center gap-2 mb-2">
          <span className="text-xl">📋</span>
          <span className="text-xs font-medium text-slate-500 uppercase tracking-wide">전체 노드 수</span>
        </div>
        <div className="text-lg sm:text-xl font-bold text-violet-600">
          {data.total_nodes.toLocaleString()}건
        </div>
      </div>
    </div>
  );
}
