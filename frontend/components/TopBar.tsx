'use client';

import { useState, useCallback } from 'react';
import { useRouter } from 'next/navigation';

export default function TopBar() {
  const router = useRouter();
  const [query, setQuery] = useState('');

  const handleSearch = useCallback(
    (e: React.FormEvent) => {
      e.preventDefault();
      const trimmed = query.trim();
      if (trimmed) {
        router.push(`/search?q=${encodeURIComponent(trimmed)}`);
      }
    },
    [query, router],
  );

  return (
    <header className="sticky top-0 z-50 bg-white border-b border-slate-200 shadow-sm">
      <div className="max-w-screen-2xl mx-auto flex items-center gap-4 h-14 px-4 sm:px-6">
        {/* Logo */}
        <a href="/" className="flex items-center gap-2 shrink-0">
          <span className="text-lg font-bold text-blue-700">📊</span>
          <span className="hidden sm:inline text-sm font-semibold text-slate-800">
            홍성군 합본예산서
          </span>
        </a>

        {/* Search Bar */}
        <form onSubmit={handleSearch} className="flex-1 max-w-md ml-auto">
          <div className="relative">
            <svg
              className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-400"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
              strokeWidth={2}
            >
              <path strokeLinecap="round" strokeLinejoin="round" d="M21 21l-4.35-4.35M11 19a8 8 0 100-16 8 8 0 000 16z" />
            </svg>
            <input
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="부서, 사업명, 키워드 검색..."
              className="w-full h-9 pl-10 pr-4 text-sm rounded-lg border border-slate-200 bg-slate-50
                         placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-blue-500/30 
                         focus:border-blue-400 focus:bg-white transition-colors"
            />
          </div>
        </form>
      </div>
    </header>
  );
}
