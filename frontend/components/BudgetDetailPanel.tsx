'use client';

import { useEffect, useRef, useState, useCallback } from 'react';
import type { TreeNodeData } from '@/types';
import { getNodeLabel } from '@/types';

// ─── 재원 항목 정의 ────────────────────────────────────────

interface FinanceEntry {
  key: keyof Pick<
    TreeNodeData,
    | 'finance_national' | 'finance_province' | 'finance_county' | 'finance_special' | 'finance_balance' | 'finance_other'
    | 'carryover_national' | 'carryover_province' | 'carryover_county' | 'carryover_special' | 'carryover_balance' | 'carryover_other'
  >;
  label: string;
  barColor: string;
  textColor: string;
}

const FINANCE_ENTRIES: FinanceEntry[] = [
  { key: 'finance_national', label: '국비', barColor: 'bg-blue-500', textColor: 'text-blue-700' },
  { key: 'finance_province', label: '도비', barColor: 'bg-emerald-500', textColor: 'text-emerald-700' },
  { key: 'finance_county', label: '군비', barColor: 'bg-orange-500', textColor: 'text-orange-700' },
  { key: 'finance_special', label: '특별교부세', barColor: 'bg-red-500', textColor: 'text-red-700' },
  { key: 'finance_balance', label: '균특회계', barColor: 'bg-purple-500', textColor: 'text-purple-700' },
  { key: 'finance_other', label: '기타', barColor: 'bg-slate-400', textColor: 'text-slate-600' },
];

const CARRYOVER_FINANCE_ENTRIES: FinanceEntry[] = [
  { key: 'carryover_national', label: '국비', barColor: 'bg-blue-400', textColor: 'text-blue-600' },
  { key: 'carryover_province', label: '도비', barColor: 'bg-emerald-400', textColor: 'text-emerald-600' },
  { key: 'carryover_county', label: '군비', barColor: 'bg-orange-400', textColor: 'text-orange-600' },
  { key: 'carryover_special', label: '특별교부세', barColor: 'bg-red-400', textColor: 'text-red-600' },
  { key: 'carryover_balance', label: '균특회계', barColor: 'bg-purple-400', textColor: 'text-purple-600' },
  { key: 'carryover_other', label: '기타', barColor: 'bg-slate-300', textColor: 'text-slate-500' },
];

// ─── 포맷 ──────────────────────────────────────────────────

function formatBudget(amount: number): string {
  if (amount === 0) return '0원';
  if (amount >= 100_000) {
    const eok = Math.floor(amount / 100_000);
    const man = Math.floor((amount % 100_000) / 10);
    if (man > 0) return `${eok.toLocaleString()}억 ${man.toLocaleString()}만원`;
    return `${eok.toLocaleString()}억원`;
  }
  return `${Math.floor(amount / 10).toLocaleString()}만원`;
}

// ─── 상태 뱃지 (API status 필드 우선, fallback) ────────────

function getStatusBadge(node: TreeNodeData): { label: string; color: string } {
  if (node.status === '추가') return { label: '추가', color: 'bg-emerald-50 text-emerald-700' };
  if (node.status === '변동') return { label: '변동', color: 'bg-amber-50 text-amber-700' };
  if (node.status === '합계' || node.is_total === 1) return { label: '합계', color: 'bg-slate-100 text-slate-600' };
  if (node.status === '동일') return { label: '동일', color: 'bg-slate-100 text-slate-500' };
  return { label: '동일', color: 'bg-slate-100 text-slate-500' };
}

// ─── 모바일 드래그 임계값 ───────────────────────────────────

const DRAG_CLOSE_THRESHOLD = 120; // px

// ─── 컴포넌트 ──────────────────────────────────────────────

interface Props {
  node: TreeNodeData;
  onClose: () => void;
}

export default function BudgetDetailPanel({ node, onClose }: Props) {
  // ── Escape 키 닫기 ──
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [onClose]);

  // ── 파생 데이터 ──
  const statusBadge = getStatusBadge(node);
  const projectName = getNodeLabel(node);
  const hierarchyPath = [node.dept, node.policy, node.unit, node.detail]
    .filter(Boolean)
    .join(' > ');

  const financeItems = FINANCE_ENTRIES
    .map((e) => ({ ...e, amount: node[e.key] }))
    .filter((e) => e.amount > 0);
  const financeTotal = financeItems.reduce((sum, e) => sum + e.amount, 0);

  const carryoverFinanceItems = CARRYOVER_FINANCE_ENTRIES
    .map((e) => ({ ...e, amount: node[e.key] }))
    .filter((e) => e.amount > 0);
  const carryoverFinanceTotal = carryoverFinanceItems.reduce((sum, e) => sum + e.amount, 0);

  // ── 모바일 드래그 투 클로즈 ──
  const sheetRef = useRef<HTMLDivElement>(null);
  const [dragOffset, setDragOffset] = useState(0);
  const [isDragging, setIsDragging] = useState(false);
  const dragStartY = useRef(0);
  const dragStartOffset = useRef(0);

  const handleTouchStart = useCallback((e: React.TouchEvent) => {
    setIsDragging(true);
    dragStartY.current = e.touches[0].clientY;
    dragStartOffset.current = dragOffset;
  }, [dragOffset]);

  const handleTouchMove = useCallback((e: React.TouchEvent) => {
    if (!isDragging) return;
    const deltaY = e.touches[0].clientY - dragStartY.current;
    const newOffset = Math.max(0, dragStartOffset.current + deltaY);
    setDragOffset(newOffset);
  }, [isDragging]);

  const handleTouchEnd = useCallback(() => {
    setIsDragging(false);
    if (dragOffset > DRAG_CLOSE_THRESHOLD) {
      onClose();
      setDragOffset(0);
    } else {
      setDragOffset(0);
    }
  }, [dragOffset, onClose]);

  // ── 공통 패널 컨텐츠 ──
  const panelContent = (
    <div className="flex flex-col h-full">
      {/* 헤더 */}
      <div className="shrink-0 flex items-center justify-between px-5 py-3.5 border-b border-slate-100 bg-white">
        <h3 className="text-sm font-bold text-slate-800 flex items-center gap-2">
          <span className="text-blue-500">📄</span>
          상세 정보
        </h3>
        <button
          onClick={onClose}
          className="w-7 h-7 flex items-center justify-center rounded-full hover:bg-slate-100 text-slate-400 hover:text-slate-600 transition-colors"
          aria-label="닫기"
        >
          <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
          </svg>
        </button>
      </div>

      {/* 본문 */}
      <div className="flex-1 overflow-y-auto p-5 space-y-5 detail-scroll">
        {/* ── 사업명 ── */}
        <section>
          <label className="text-[11px] font-medium text-slate-400 uppercase tracking-wide">사업명</label>
          <p className="mt-1 text-sm font-semibold text-slate-800 leading-relaxed">{projectName}</p>
          <p className="mt-0.5 text-xs text-slate-400">{hierarchyPath}</p>
        </section>

        {/* ── 상태 뱃지 + 페이지 ── */}
        <div className="flex items-center gap-2">
          <span className={`inline-flex items-center px-2.5 py-0.5 rounded text-xs font-semibold ${statusBadge.color}`}>
            {statusBadge.label}
          </span>
          {node.page > 0 && (
            <span className="text-[11px] text-slate-400">p.{node.page}</span>
          )}
        </div>

        {/* ── 총예산 (강조 카드, carryover > 0 시 총계 + breakdown) ── */}
        <div className="rounded-xl bg-gradient-to-br from-blue-500 to-blue-600 p-5 text-white shadow-md">
          <p className="text-xs font-medium text-blue-100 uppercase tracking-wide">총예산</p>
          <p className="mt-1.5 text-2xl font-bold tracking-tight">
            {node.calc_name === '◎이월액'
              ? (node.carryover > 0 ? formatBudget(node.carryover) : '-')
              : node.carryover > 0
                ? formatBudget(node.budget_amount + node.carryover)
                : (node.budget_amount > 0 ? formatBudget(node.budget_amount) : '-')
            }
          </p>
          {node.carryover > 0 && node.calc_name !== '◎이월액' && (
            <p className="mt-1 text-[10px] text-blue-100">
              당해 {formatBudget(node.budget_amount)} + 이월 {formatBudget(node.carryover)}
            </p>
          )}
          {node.is_total === 1 && (
            <span className="inline-block mt-1.5 text-[10px] bg-white/20 px-2 py-0.5 rounded-full">합계 항목</span>
          )}
        </div>

        {/* ── 본예산 / 이월예산 (좌우 카드) ── */}
        <div className="grid grid-cols-2 gap-3">
          <div className="rounded-xl bg-slate-50 border border-slate-100 p-4">
            <p className="text-[11px] font-medium text-slate-400 uppercase tracking-wide">당해예산</p>
            <p className="mt-1 text-base font-bold text-slate-800">
              {node.budget_amount > 0 ? formatBudget(node.budget_amount) : '-'}
            </p>
            <p className="mt-0.5 text-[10px] text-slate-400">당해</p>
          </div>
          <div className="rounded-xl bg-amber-50/60 border border-amber-100 p-4">
            <p className="text-[11px] font-medium text-amber-500 uppercase tracking-wide">이월예산</p>
            <p className="mt-1 text-base font-bold text-amber-800">
              {node.carryover > 0 ? formatBudget(node.carryover) : '-'}
            </p>
            <p className="mt-0.5 text-[10px] text-amber-400">차기 이월</p>
          </div>
        </div>

        {/* ── 이월예산 타입 breakdown ── */}
        {node.carryover > 0 && (node.carryover_continued > 0 || node.carryover_explicit > 0 || node.carryover_accident > 0) && (
          <section>
            <label className="text-[11px] font-medium text-slate-400 uppercase tracking-wide block mb-2">
              이월 구분
            </label>
            <div className="space-y-1.5">
              {node.carryover_continued > 0 && (
                <div className="flex justify-between items-center text-xs">
                  <span className="text-purple-600">🔄 계속비</span>
                  <span className="font-mono text-purple-700">{formatBudget(node.carryover_continued)}</span>
                </div>
              )}
              {node.carryover_explicit > 0 && (
                <div className="flex justify-between items-center text-xs">
                  <span className="text-amber-600">📋 명시이월</span>
                  <span className="font-mono text-amber-700">{formatBudget(node.carryover_explicit)}</span>
                </div>
              )}
              {node.carryover_accident > 0 && (
                <div className="flex justify-between items-center text-xs">
                  <span className="text-red-600">⚠️ 사고이월</span>
                  <span className="font-mono text-red-700">{formatBudget(node.carryover_accident)}</span>
                </div>
              )}
            </div>
          </section>
        )}

        {/* ── 적요 ── */}
        {node.summary_text && (
          <section>
            <label className="text-[11px] font-medium text-slate-400 uppercase tracking-wide">적요</label>
            <p className="mt-1.5 text-sm text-slate-700 leading-relaxed bg-slate-50 rounded-lg p-3 border border-slate-100">
              {node.summary_text}
            </p>
          </section>
        )}

        {/* ── 재원 구분 ── */}
        {financeItems.length > 0 && (
          <section>
            <label className="text-[11px] font-medium text-slate-400 uppercase tracking-wide block mb-3">
              재원 구분
            </label>

            {/* Stacked bar */}
            <div className="flex h-3 rounded-full overflow-hidden mb-3 bg-slate-100">
              {financeItems.map((e) => {
                const pct = financeTotal > 0 ? (e.amount / financeTotal) * 100 : 0;
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

            {/* Legend */}
            <div className="space-y-1.5">
              {financeItems.map((e) => {
                const pct = financeTotal > 0 ? ((e.amount / financeTotal) * 100).toFixed(1) : '0';
                return (
                  <div key={e.key} className="flex items-center gap-2 text-xs">
                    <span className={`w-2.5 h-2.5 rounded-sm shrink-0 ${e.barColor}`} />
                    <span className={`font-medium w-16 shrink-0 ${e.textColor}`}>{e.label}</span>
                    <span className="font-mono text-slate-600 flex-1 text-right">{formatBudget(e.amount)}</span>
                    <span className="text-slate-400 w-12 text-right tabular-nums">{pct}%</span>
                  </div>
                );
              })}
            </div>

            {/* 총합 */}
            <div className="mt-3 pt-3 border-t border-slate-100 flex items-center justify-between text-xs text-slate-400">
              <span>재원 총합</span>
              <span className="font-mono font-medium text-slate-500">{formatBudget(financeTotal)}</span>
            </div>
          </section>
        )}

        {/* ── 이월액 재원 구분 ── */}
        {node.carryover > 0 && carryoverFinanceItems.length > 0 && (
          <section>
            <label className="text-[11px] font-medium text-amber-600 uppercase tracking-wide block mb-3">
              🔄 이월액 재원 구분
            </label>

            {/* Stacked bar */}
            <div className="flex h-3 rounded-full overflow-hidden mb-3 bg-amber-50">
              {carryoverFinanceItems.map((e) => {
                const pct = carryoverFinanceTotal > 0 ? (e.amount / carryoverFinanceTotal) * 100 : 0;
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

            {/* Legend */}
            <div className="space-y-1.5">
              {carryoverFinanceItems.map((e) => {
                const pct = carryoverFinanceTotal > 0 ? ((e.amount / carryoverFinanceTotal) * 100).toFixed(1) : '0';
                return (
                  <div key={e.key} className="flex items-center gap-2 text-xs">
                    <span className={`w-2.5 h-2.5 rounded-sm shrink-0 ${e.barColor}`} />
                    <span className={`font-medium w-16 shrink-0 ${e.textColor}`}>{e.label}</span>
                    <span className="font-mono text-slate-600 flex-1 text-right">{formatBudget(e.amount)}</span>
                    <span className="text-slate-400 w-12 text-right tabular-nums">{pct}%</span>
                  </div>
                );
              })}
            </div>

            {/* 총합 */}
            <div className="mt-3 pt-3 border-t border-amber-100 flex items-center justify-between text-xs text-slate-400">
              <span>이월액 총합</span>
              <span className="font-mono font-medium text-slate-500">{formatBudget(carryoverFinanceTotal)}</span>
            </div>
          </section>
        )}

        {/* ── 품목코드 ── */}
        {node.item_code && (
          <section>
            <label className="text-[11px] font-medium text-slate-400 uppercase tracking-wide">품목코드</label>
            <p className="mt-0.5 text-xs font-mono text-slate-600">{node.item_code}</p>
          </section>
        )}
      </div>
    </div>
  );

  return (
    <>
      {/* ── Desktop: 우측 고정 패널 ── */}
      <div className="hidden lg:flex lg:flex-col lg:w-[32%] lg:min-w-[340px] bg-white rounded-lg shadow-sm border border-slate-100 overflow-hidden">
        {panelContent}
      </div>

      {/* ── Mobile: 하단 시트 (드래그 닫기 지원) ── */}
      <div className="lg:hidden fixed inset-0 z-50 flex flex-col justify-end">
        <div
          className="absolute inset-0 bg-black/40 backdrop-blur-sm animate-fade-in"
          onClick={onClose}
        />
        <div
          ref={sheetRef}
          className="relative bg-white rounded-t-xl shadow-2xl max-h-[85vh] flex flex-col animate-slide-up transition-transform duration-200"
          style={{ transform: dragOffset > 0 ? `translateY(${dragOffset}px)` : undefined }}
        >
          <div
            className="flex justify-center pt-2 pb-1 cursor-grab active:cursor-grabbing touch-none"
            onTouchStart={handleTouchStart}
            onTouchMove={handleTouchMove}
            onTouchEnd={handleTouchEnd}
          >
            <div className="w-10 h-1.5 bg-slate-300 rounded-full" />
          </div>
          {panelContent}
        </div>
      </div>
    </>
  );
}
