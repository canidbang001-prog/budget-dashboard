'use client';

import { useState, useCallback, useEffect } from 'react';
import type { TreeNodeData } from '@/types';
import { getNodeLabel } from '@/types';
import { fetchChildren } from '@/lib/api';

// ─── 포맷 ──────────────────────────────────────────────────

function formatCompact(amount: number): string {
  if (amount >= 100000) {
    const eok = Math.floor(amount / 100000);
    const man = Math.floor((amount % 100000) / 10);
    if (man > 0) return `${eok.toLocaleString()}억${man.toLocaleString()}만원`;
    return `${eok.toLocaleString()}억원`;
  }
  return `${Math.floor(amount / 10).toLocaleString()}만원`;
}

// ─── Depth별 스타일 ────────────────────────────────────────

const DEPTH_STYLES: Record<number, string> = {
  0: 'font-bold text-blue-900 text-sm',
  1: 'font-semibold text-blue-800 text-sm',
  2: 'font-semibold text-indigo-700 text-[13px]',
  3: 'text-slate-600 text-[13px]',
  4: 'text-slate-500 text-xs',
  5: 'text-slate-500 text-xs',
  6: 'text-slate-400 text-[11px]',
  7: 'text-slate-400 text-[11px]',
};

const PADDING_PER_DEPTH = 20; // px

// ─── 재원 태그 ─────────────────────────────────────────────

const FINANCE_TAGS = [
  { key: 'finance_national' as const, label: '국', bg: 'bg-blue-50', text: 'text-blue-600' },
  { key: 'finance_province' as const, label: '도', bg: 'bg-emerald-50', text: 'text-emerald-600' },
  { key: 'finance_county' as const, label: '군', bg: 'bg-orange-50', text: 'text-orange-600' },
  { key: 'finance_special' as const, label: '특', bg: 'bg-red-50', text: 'text-red-600' },
  { key: 'finance_balance' as const, label: '균', bg: 'bg-purple-50', text: 'text-purple-600' },
  { key: 'finance_other' as const, label: '기', bg: 'bg-slate-100', text: 'text-slate-500' },
];

// ─── 컴포넌트 ──────────────────────────────────────────────

interface Props {
  node: TreeNodeData;
  depth?: number;
  autoExpand?: boolean;
  onSelect?: (node: TreeNodeData) => void;
}

export default function TreeNode({ node, depth = 0, autoExpand = false, onSelect }: Props) {
  const [expanded, setExpanded] = useState(autoExpand);
  const [children, setChildren] = useState<TreeNodeData[]>(node.children || []);
  const [loading, setLoading] = useState(false);

  // autoExpand prop 변경 감지 → 전체 펼치기/접기
  useEffect(() => {
    if (autoExpand && node.has_children) {
      setExpanded(true);
      if (children.length === 0 && node.children.length > 0) {
        setChildren(node.children);
      } else if (children.length === 0) {
        setLoading(true);
        fetchChildren(node.id)
          .then(setChildren)
          .catch(() => {})
          .finally(() => setLoading(false));
      }
    } else if (!autoExpand) {
      setExpanded(false);
    }
  }, [autoExpand]); // eslint-disable-line react-hooks/exhaustive-deps

  const toggle = useCallback(async () => {
    onSelect?.(node);
    if (!node.has_children) return;
    if (expanded) {
      setExpanded(false);
      return;
    }
    // children이 이미 있으면 바로 펼침, 없으면 lazy load
    if (children.length === 0 && node.children.length > 0) {
      setChildren(node.children);
    } else if (children.length === 0) {
      setLoading(true);
      try {
        const data = await fetchChildren(node.id);
        setChildren(data);
      } catch (err) {
        console.error('[TreeNode] fetchChildren 실패:', err);
      } finally {
        setLoading(false);
      }
    }
    setExpanded(true);
  }, [node.has_children, node.id, node.children, expanded, children.length]);

  const depthStyle = DEPTH_STYLES[Math.min(depth, 5)] || DEPTH_STYLES[5];
  const leftPad = depth * PADDING_PER_DEPTH;
  const hasFinance = node.finance_national > 0 || node.finance_province > 0 || node.finance_county > 0 || node.finance_special > 0 || node.finance_balance > 0 || node.finance_other > 0;

  return (
    <div>
      {/* Row */}
      <div
        className={`flex items-center gap-2 py-2 px-3 border-b border-slate-50 hover:bg-slate-50/50 transition-colors cursor-pointer`}
        style={{ paddingLeft: `${16 + leftPad}px` }}
        onClick={toggle}
      >
        {/* Expand toggle */}
        {node.has_children ? (
          <span className="inline-flex items-center justify-center w-5 h-5 shrink-0">
            {loading ? (
              <span className="inline-block w-3 h-3 border-2 border-slate-300 border-t-blue-500 rounded-full animate-spin" />
            ) : (
              <svg
                className={`w-3.5 h-3.5 text-slate-400 transition-transform ${expanded ? 'rotate-90' : ''}`}
                fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}
              >
                <path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" />
              </svg>
            )}
          </span>
        ) : (
          <span className="w-5 shrink-0" />
        )}

        {/* Node name */}
        <span className={`flex-1 truncate ${depthStyle}`}>
          {getNodeLabel(node)}
          {node.is_total === 1 && (
            <span className="ml-1.5 text-[10px] text-slate-400 font-normal">(합계)</span>
          )}
          {node.carryover_continued > 0 && (
            <span className="ml-1.5 text-[10px] font-medium px-1.5 py-0.5 rounded text-purple-600 bg-purple-50">계속비</span>
          )}
          {node.carryover_explicit > 0 && (
            <span className="ml-1.5 text-[10px] font-medium px-1.5 py-0.5 rounded text-amber-600 bg-amber-50">명시이월</span>
          )}
          {node.carryover_accident > 0 && (
            <span className="ml-1.5 text-[10px] font-medium px-1.5 py-0.5 rounded text-red-600 bg-red-50">사고이월</span>
          )}
          {/* fallback: carryover_* 없고 status만 있는 구데이터 */}
          {node.carryover_continued === 0 && node.carryover_explicit === 0 && node.carryover_accident === 0 && (node.status === '명시이월' || node.status === '사고이월' || node.status === '계속비') && (
            <span className={`ml-1.5 text-[10px] font-medium px-1.5 py-0.5 rounded ${
              node.status === '명시이월' ? 'text-amber-600 bg-amber-50' :
              node.status === '사고이월' ? 'text-red-600 bg-red-50' :
              'text-purple-600 bg-purple-50'
            }`}>
              {node.status}
            </span>
          )}
        </span>

        {/* Budget amount — carryover 제외 (트리 펼침 시 일관성) */}
        <span
          className="text-xs font-mono text-slate-600 shrink-0 cursor-pointer hover:text-blue-600 hover:bg-blue-50 px-1.5 py-0.5 rounded transition-colors"
          onClick={(e) => { e.stopPropagation(); onSelect?.(node); }}
          title={node.carryover > 0 ? `당해 ${formatCompact(node.budget_amount)} + 이월 ${formatCompact(node.carryover)}` : '클릭: 재원 구분 보기'}
        >
          {formatCompact(node.budget_amount)}
        </span>

        {/* Finance tags */}
        {hasFinance && (
          <span className="flex gap-0.5 shrink-0">
            {FINANCE_TAGS.filter((t) => node[t.key] > 0).map((tag) => (
              <span key={tag.key} className={`inline-flex items-center px-1 py-0.5 rounded text-[10px] font-medium ${tag.bg} ${tag.text}`}>
                {tag.label}
              </span>
            ))}
          </span>
        )}

        {/* Child count badge */}
        {node.has_children && !expanded && node.children.length > 0 && (
          <span className="text-[10px] text-slate-400 bg-slate-100 px-1.5 py-0.5 rounded shrink-0">
            {node.children.length}
          </span>
        )}
      </div>

      {/* Children */}
      {expanded && children.length > 0 && (
        <div className="border-l-2 border-blue-100 ml-5">
          {children.map((child) => (
            <TreeNode key={child.id} node={child} depth={depth + 1} autoExpand={autoExpand} onSelect={onSelect} />
          ))}
        </div>
      )}

      {/* Loading placeholder */}
      {loading && <div className="py-1 px-3 text-xs text-slate-400 animate-pulse" style={{ paddingLeft: `${16 + leftPad + 20}px` }}>불러오는 중...</div>}
    </div>
  );
}
