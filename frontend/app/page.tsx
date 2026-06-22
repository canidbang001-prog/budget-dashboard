'use client';

import { useState, useEffect, useCallback } from 'react';
import SummaryCards from '@/components/SummaryCards';
import DeptListPanel from '@/components/DeptListPanel';
import TreePanel from '@/components/TreePanel';
import { fetchSummary } from '@/lib/api';
import type { SummaryData } from '@/types';

export default function DashboardPage() {
  const [summary, setSummary] = useState<SummaryData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [activeDept, setActiveDept] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    console.log('[Dashboard] fetchSummary 시작...');
    fetchSummary()
      .then((data) => {
        if (cancelled) return;
        console.log('[Dashboard] fetchSummary 성공:', data.department_count, '부서,', data.total_budget, '원');
        setSummary(data);
      })
      .catch((err) => {
        if (cancelled) return;
        console.error('[Dashboard] fetchSummary 실패:', err);
        setError(err instanceof Error ? err.message : String(err));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => { cancelled = true; };
  }, []);

  const handleSelectDept = useCallback((dept: string) => {
    setActiveDept((prev) => (prev === dept ? null : dept));
  }, []);

  return (
    <main className="flex-1 max-w-screen-2xl w-full mx-auto px-4 sm:px-6 py-6">
      {/* 에러 표시 */}
      {error && (
        <div className="mb-4 p-4 bg-red-50 border border-red-200 rounded-lg text-sm text-red-700">
          ⚠️ API 연동 오류: {error}
          <button onClick={() => window.location.reload()} className="ml-3 underline hover:text-red-900">새로고침</button>
        </div>
      )}
      {/* 요약 카드 */}
      <SummaryCards data={summary} loading={loading} />

      {/* 2컬럼 레이아웃 (FHD 1920x1080 최적화) */}
      <div className="flex flex-col lg:flex-row gap-4 lg:gap-6 min-h-0" style={{ height: 'calc(100vh - 140px)' }}>
        {/* 좌측 사이드바 - 부서 목록 */}
        <div className="w-full lg:w-[280px] shrink-0">
          <DeptListPanel
            departments={summary?.departments || []}
            loading={loading}
            activeDept={activeDept}
            onSelectDept={handleSelectDept}
          />
        </div>

        {/* 우측 본문 - 트리 뷰 */}
        <div className="flex-1 flex min-h-0">
          <TreePanel dept={activeDept} />
        </div>
      </div>
    </main>
  );
}
