'use client';

import { useState, useMemo } from 'react';
import type { DepartmentSummary } from '@/types';
import DeptItem from './DeptItem';

interface Props {
  departments: DepartmentSummary[];
  loading: boolean;
  activeDept: string | null;
  onSelectDept: (dept: string) => void;
}

export default function DeptListPanel({ departments, loading, activeDept, onSelectDept }: Props) {
  const [search, setSearch] = useState('');

  const filtered = useMemo(
    () =>
      search.trim()
        ? departments.filter((d) => d.dept.includes(search.trim()))
        : departments,
    [departments, search],
  );

  return (
    <aside className="bg-white rounded-lg shadow-sm border border-slate-100 overflow-hidden flex flex-col h-full">
      {/* Header */}
      <div className="px-4 py-3 border-b border-slate-100 bg-slate-50/50">
        <h2 className="text-sm font-semibold text-slate-700 mb-2">부서 목록</h2>
        <div className="relative">
          <svg
            className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-slate-400"
            fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}
          >
            <path strokeLinecap="round" strokeLinejoin="round" d="M21 21l-4.35-4.35M11 19a8 8 0 100-16 8 8 0 000 16z" />
          </svg>
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="부서명 필터..."
            className="w-full h-8 pl-8 pr-3 text-xs rounded-md border border-slate-200 bg-white
                       placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-blue-500/20 
                       focus:border-blue-400 transition-colors"
          />
        </div>
      </div>

      {/* List */}
      <div className="overflow-y-auto flex-1">
        {loading ? (
          <div className="p-4 space-y-3">
            {[1, 2, 3, 4, 5].map((i) => (
              <div key={i} className="animate-pulse">
                <div className="h-4 bg-slate-200 rounded w-3/4 mb-2" />
                <div className="h-2 bg-slate-100 rounded w-full" />
              </div>
            ))}
          </div>
        ) : filtered.length === 0 ? (
          <div className="p-6 text-center text-sm text-slate-400">부서가 없습니다</div>
        ) : (
          filtered.map((dept) => (
            <DeptItem
              key={dept.dept}
              dept={dept}
              isActive={activeDept === dept.dept}
              onClick={() => onSelectDept(dept.dept)}
            />
          ))
        )}
      </div>

      <div className="px-4 py-2 border-t border-slate-100 bg-slate-50/30 text-[10px] text-slate-400 text-right">
        {filtered.length}개 부서
      </div>
    </aside>
  );
}
