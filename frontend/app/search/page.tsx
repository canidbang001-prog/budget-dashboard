'use client';

import { useState, useEffect, useCallback, Suspense } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import Link from 'next/link';
import type { SearchResultData } from '@/types';
import { fetchSearch } from '@/lib/api';
import { getNodeLabel } from '@/types';

// ─── 포맷 ──────────────────────────────────────────────────

function formatCompact(amount: number): string {
  if (amount >= 100000) {
    const eok = Math.floor(amount / 100000);
    const man = Math.floor((amount % 100000) / 10);
    if (man > 0) return `${eok}억${man}만원`;
    return `${eok}억원`;
  }
  return `${Math.floor(amount / 10)}만원`;
}

// ─── 본문 컴포넌트 ────────────────────────────────────────

function SearchContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const q = searchParams.get('q') || '';

  const [query, setQuery] = useState(q);
  const [results, setResults] = useState<SearchResultData[]>([]);
  const [loading, setLoading] = useState(false);
  const [searched, setSearched] = useState(false);

  const doSearch = useCallback(
    (searchQuery: string) => {
      if (!searchQuery.trim()) return;
      setLoading(true);
      setSearched(true);
      router.replace(`/search?q=${encodeURIComponent(searchQuery.trim())}`);
      fetchSearch(searchQuery.trim())
        .then(setResults)
        .catch(() => {})
        .finally(() => setLoading(false));
    },
    [router],
  );

  useEffect(() => {
    if (q) {
      setQuery(q);
      doSearch(q);
    }
  }, [q, doSearch]);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    doSearch(query);
  };

  return (
    <main className="flex-1 max-w-screen-2xl w-full mx-auto px-4 sm:px-6 py-6">
      {/* Breadcrumb */}
      <nav className="flex items-center gap-2 text-sm mb-4 text-slate-500">
        <Link href="/" className="hover:text-blue-600 transition-colors">대시보드</Link>
        <span>/</span>
        <span className="font-medium text-slate-700">검색</span>
      </nav>

      {/* Search */}
      <div className="bg-white rounded-lg shadow-sm border border-slate-100 p-6 mb-6">
        <form onSubmit={handleSubmit} className="flex gap-3">
          <div className="relative flex-1">
            <svg
              className="absolute left-3.5 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-400"
              fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}
            >
              <path strokeLinecap="round" strokeLinejoin="round" d="M21 21l-4.35-4.35M11 19a8 8 0 100-16 8 8 0 000 16z" />
            </svg>
            <input
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="부서명, 사업명, 키워드로 검색..."
              className="w-full h-11 pl-11 pr-4 text-sm rounded-lg border border-slate-200
                         placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-blue-500/30
                         focus:border-blue-400 transition-colors"
            />
          </div>
          <button
            type="submit"
            className="px-5 h-11 text-sm font-medium text-white bg-blue-600 hover:bg-blue-700
                       rounded-lg transition-colors disabled:opacity-50"
            disabled={loading || !query.trim()}
          >
            {loading ? '검색 중...' : '검색'}
          </button>
        </form>
      </div>

      {/* Results */}
      <div className="bg-white rounded-lg shadow-sm border border-slate-100 overflow-hidden">
        <div className="px-4 py-3 border-b border-slate-100 bg-slate-50/50">
          <h2 className="text-sm font-semibold text-slate-700">
            {searched
              ? `검색 결과 ${loading ? '(불러오는 중...)' : `(${results.length}건)`}`
              : '검색어를 입력해주세요'}
          </h2>
        </div>

        <div className="overflow-x-auto">
          {loading ? (
            <div className="p-6 space-y-3">
              {[1, 2, 3, 4, 5].map((i) => (
                <div key={i} className="animate-pulse h-8 bg-slate-200 rounded" />
              ))}
            </div>
          ) : results.length === 0 && searched ? (
            <div className="p-8 text-center text-sm text-slate-400">
              검색 결과가 없습니다
            </div>
          ) : results.length > 0 ? (
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-slate-100 bg-slate-50/30">
                  <th className="text-left px-4 py-2.5 text-xs font-medium text-slate-500">부서</th>
                  <th className="text-left px-4 py-2.5 text-xs font-medium text-slate-500">사업명</th>
                  <th className="text-right px-4 py-2.5 text-xs font-medium text-slate-500">예산액</th>
                  <th className="text-center px-4 py-2.5 text-xs font-medium text-slate-500">페이지</th>
                </tr>
              </thead>
              <tbody>
                {results.map((row, i) => (
                  <tr key={row.id || i} className="border-b border-slate-50 hover:bg-slate-50/50 transition-colors">
                    <td className="px-4 py-2.5">
                      <Link href={`/dept/${encodeURIComponent(row.dept)}`} className="text-blue-600 hover:underline text-xs">
                        {row.dept}
                      </Link>
                    </td>
                    <td className="px-4 py-2.5 text-slate-700 max-w-md truncate">
                      {getNodeLabel(row)}
                    </td>
                    <td className="px-4 py-2.5 text-right font-mono text-xs text-slate-600">
                      {formatCompact(row.budget_amount)}
                    </td>
                    <td className="px-4 py-2.5 text-center text-xs text-slate-400">{row.page}p</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : null}
        </div>
      </div>
    </main>
  );
}

// ─── Suspense Wrapper ──────────────────────────────────────

export default function SearchPage() {
  return (
    <Suspense fallback={
      <main className="flex-1 max-w-screen-2xl w-full mx-auto px-4 sm:px-6 py-6">
        <div className="animate-pulse space-y-4">
          <div className="h-8 bg-slate-200 rounded w-32" />
          <div className="h-16 bg-slate-200 rounded" />
          <div className="h-64 bg-slate-200 rounded" />
        </div>
      </main>
    }>
      <SearchContent />
    </Suspense>
  );
}
