'use client';

import type { DepartmentSummary } from '@/types';

// ─── 포맷 유틸 ─────────────────────────────────────────────

function formatCompact(amount: number): string {
  if (amount >= 100000) {
    const eok = Math.floor(amount / 100000);
    const man = Math.floor((amount % 100000) / 10);
    if (man > 0) return `${eok}억${man}만`;
    return `${eok}억`;
  }
  return `${Math.floor(amount / 10)}만`;
}

// ─── 재원 태그 ─────────────────────────────────────────────

const FINANCE_TAGS: { key: keyof Pick<DepartmentSummary, 'finance_national' | 'finance_province' | 'finance_county' | 'finance_special' | 'finance_balance' | 'finance_other'>; label: string; bg: string; text: string; bar: string }[] = [
  { key: 'finance_national', label: '국', bg: 'bg-blue-50', text: 'text-blue-600', bar: '#3b82f6' },
  { key: 'finance_province', label: '도', bg: 'bg-emerald-50', text: 'text-emerald-600', bar: '#10b981' },
  { key: 'finance_county', label: '군', bg: 'bg-orange-50', text: 'text-orange-600', bar: '#f97316' },
  { key: 'finance_special', label: '특', bg: 'bg-red-50', text: 'text-red-600', bar: '#ef4444' },
  { key: 'finance_balance', label: '균', bg: 'bg-purple-50', text: 'text-purple-600', bar: '#a855f7' },
  { key: 'finance_other', label: '기', bg: 'bg-slate-100', text: 'text-slate-500', bar: '#94a3b8' },
];

// ─── 컴포넌트 ──────────────────────────────────────────────

interface Props {
  dept: DepartmentSummary;
  isActive: boolean;
  onClick: () => void;
}

export default function DeptItem({ dept, isActive, onClick }: Props) {
  const financeTotal = dept.finance_national + dept.finance_province + dept.finance_county
    + dept.finance_special + dept.finance_balance + dept.finance_other;
  const tags = FINANCE_TAGS.filter((t) => dept[t.key] > 0);

  return (
    <button
      onClick={onClick}
      className={`w-full text-left px-4 py-3 border-b border-slate-100 transition-colors
        ${isActive ? 'bg-blue-50 border-l-2 border-l-blue-500' : 'bg-white hover:bg-slate-50 border-l-2 border-l-transparent'}`}
    >
      <div className="flex items-center justify-between mb-1">
        <span className={`text-sm font-medium truncate flex items-center gap-1 ${isActive ? 'text-blue-700' : 'text-slate-700'}`}>
          {dept.dept}
          {dept.carryover > 0 && (
            <span className="text-[10px] font-medium text-amber-600 bg-amber-50 px-1 py-0.5 rounded shrink-0">
              이월 {formatCompact(dept.carryover)}
            </span>
          )}
        </span>
        <div className="text-right shrink-0 ml-2">
          <div className="text-xs font-mono text-slate-500">{formatCompact(dept.budget_amount)}</div>
          {dept.carryover > 0 && (
            <div className="text-[10px] font-mono text-amber-600">{formatCompact(dept.carryover)}</div>
          )}
        </div>
      </div>

      {/* 재원 구성 stacked bar */}
      {financeTotal > 0 && (
        <div className="h-1.5 bg-slate-100 rounded-full overflow-hidden mb-1.5 flex">
          {FINANCE_TAGS.map((tag) => {
            const pct = (dept[tag.key] / financeTotal) * 100;
            if (pct <= 0) return null;
            return (
              <div
                key={tag.key}
                className="h-full transition-all duration-300"
                style={{ width: `${pct}%`, backgroundColor: tag.bar }}
              />
            );
          })}
        </div>
      )}

      {/* Finance tags */}
      {tags.length > 0 && (
        <div className="flex gap-1 flex-wrap">
          {tags.map((tag) => (
            <span key={tag.key} className={`inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-medium ${tag.bg} ${tag.text}`}>
              {tag.label}
            </span>
          ))}
        </div>
      )}
    </button>
  );
}
