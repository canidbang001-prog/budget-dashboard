'use client';

import type { TreeNodeData } from '@/types';

// ─── 재원 항목 정의 ────────────────────────────────────────

interface FinanceEntry {
  key: keyof Pick<TreeNodeData, 'finance_national' | 'finance_province' | 'finance_county' | 'finance_special' | 'finance_balance' | 'finance_other'>;
  label: string;
  barColor: string;
  textColor: string;
  bgColor: string;
}

const FINANCE_ENTRIES: FinanceEntry[] = [
  { key: 'finance_national', label: '국비', barColor: 'bg-blue-500', textColor: 'text-blue-700', bgColor: 'bg-blue-50' },
  { key: 'finance_province', label: '도비', barColor: 'bg-emerald-500', textColor: 'text-emerald-700', bgColor: 'bg-emerald-50' },
  { key: 'finance_county', label: '군비', barColor: 'bg-orange-500', textColor: 'text-orange-700', bgColor: 'bg-orange-50' },
  { key: 'finance_special', label: '특별교부세', barColor: 'bg-red-500', textColor: 'text-red-700', bgColor: 'bg-red-50' },
  { key: 'finance_balance', label: '균특회계', barColor: 'bg-purple-500', textColor: 'text-purple-700', bgColor: 'bg-purple-50' },
  { key: 'finance_other', label: '기타', barColor: 'bg-slate-400', textColor: 'text-slate-600', bgColor: 'bg-slate-50' },
];

// ─── 포맷 (천원 단위) ──────────────────────────────────────

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
  node: TreeNodeData | null;
  onClose: () => void;
}

export default function FinanceBreakdown({ node, onClose }: Props) {
  if (!node) return null;

  const entries = FINANCE_ENTRIES
    .map((e) => ({ ...e, amount: node[e.key] }))
    .filter((e) => e.amount > 0);

  if (entries.length === 0) return null;

  const total = entries.reduce((sum, e) => sum + e.amount, 0);

  return (
    /* 배경 딤 오버레이 */
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm"
      onClick={onClose}
    >
      {/* 모달 */}
      <div
        className="bg-white rounded-xl shadow-2xl w-full max-w-sm mx-4 overflow-hidden"
        onClick={(e) => e.stopPropagation()}
      >
        {/* 헤더 */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-slate-100">
          <div>
            <h3 className="text-sm font-bold text-slate-800">재원 구분</h3>
            <p className="text-xs text-slate-400 mt-0.5 truncate max-w-[220px]">
              {node.dept}
            </p>
          </div>
          <button
            onClick={onClose}
            className="w-7 h-7 flex items-center justify-center rounded-full hover:bg-slate-100 text-slate-400 hover:text-slate-600 transition-colors"
          >
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        {/* 본문 */}
        <div className="px-5 py-4">
          {/* Horizontal stacked bar */}
          <div className="flex h-3 rounded-full overflow-hidden mb-4 bg-slate-100">
            {entries.map((e) => {
              const pct = total > 0 ? (e.amount / total) * 100 : 0;
              return pct > 1 ? (
                <div
                  key={e.key}
                  className={`${e.barColor} transition-all`}
                  style={{ width: `${pct}%` }}
                  title={`${e.label}: ${formatBudget(e.amount)}`}
                />
              ) : null;
            })}
          </div>

          {/* Legend list */}
          <div className="space-y-2">
            {entries.map((e) => {
              const pct = total > 0 ? ((e.amount / total) * 100).toFixed(1) : '0';
              return (
                <div key={e.key} className="flex items-center gap-2.5 text-sm">
                  <span className={`w-3 h-3 rounded-sm shrink-0 ${e.barColor}`} />
                  <span className={`font-medium w-20 shrink-0 ${e.textColor}`}>{e.label}</span>
                  <span className="font-mono text-slate-600 flex-1 text-right">
                    {formatBudget(e.amount)}
                  </span>
                  <span className="text-slate-400 w-14 text-right tabular-nums text-xs">
                    {pct}%
                  </span>
                </div>
              );
            })}
          </div>

          {/* Total verification */}
          <div className="mt-3 pt-3 border-t border-slate-100 flex items-center justify-between text-xs text-slate-400">
            <span>총합</span>
            <span className="font-mono font-medium text-slate-500">{formatBudget(total)}</span>
          </div>
        </div>
      </div>
    </div>
  );
}
