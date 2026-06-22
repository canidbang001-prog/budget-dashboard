'use client';

import { useState, useEffect, useCallback, useMemo } from 'react';
import type { TreeNodeData } from '@/types';
import { fetchTree } from '@/lib/api';
import TreeNode from './TreeNode';
import TreeControls from './TreeControls';
import BudgetDetailPanel from './BudgetDetailPanel';

interface Props {
  dept: string | null;
}

/** 평면 노드 리스트 → 부모-자식 트리 구조로 변환 */
function buildTree(flatNodes: TreeNodeData[]): TreeNodeData[] {
  const map = new Map<number, TreeNodeData>();
  const roots: TreeNodeData[] = [];
  
  // 1차: 모든 노드를 map에 등록 (has_children는 mapTreeNode 기본값 true 유지 → lazy load로 판단)
  for (const n of flatNodes) {
    map.set(n.id, { ...n, children: [] });
  }
  
  // 2차: parent_id 따라 자식 연결
  for (const n of map.values()) {
    if (n.parent_id !== null && map.has(n.parent_id)) {
      const parent = map.get(n.parent_id)!;
      parent.children.push(n);
      parent.has_children = true;
    } else if (n.depth === 0) {
      roots.push(n);
    }
  }
  
  return roots;
}

export default function TreePanel({ dept }: Props) {
  const [flatNodes, setFlatNodes] = useState<TreeNodeData[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // 전체 펼침/접힘 제어용 key + autoExpand (re-mount 트리거)
  const [expandKey, setExpandKey] = useState(0);
  const [bulkExpand, setBulkExpand] = useState<boolean>(false);
  const [selectedNode, setSelectedNode] = useState<TreeNodeData | null>(null);

  // 평면 → 트리 변환 (메모이제이션)
  const rootNodes = useMemo(() => buildTree(flatNodes), [flatNodes]);

  useEffect(() => {
    if (!dept) {
      setFlatNodes([]);
      return;
    }
    setLoading(true);
    setError(null);
    fetchTree(dept)
      .then((data) => {
        setFlatNodes(data);
      })
      .catch((err) => {
        console.error('[TreePanel] fetchTree 실패:', err);
        setError(`트리 로드 실패: ${err instanceof Error ? err.message : String(err)}`);
      })
      .finally(() => setLoading(false));
  }, [dept]);

  const handleExpandAll = useCallback(() => {
    setBulkExpand(true);
    setExpandKey((k) => k + 1);
  }, []);

  const handleCollapseAll = useCallback(() => {
    setBulkExpand(false);
    setExpandKey((k) => k + 1);
  }, []);

  if (!dept) {
    return (
      <div className="flex-1 flex items-center justify-center bg-white rounded-lg shadow-sm border border-slate-100 p-8">
        <div className="text-center">
          <span className="text-4xl">👈</span>
          <p className="mt-3 text-sm text-slate-400">왼쪽 부서 목록에서 선택해주세요</p>
        </div>
      </div>
    );
  }

  const hasSelection = selectedNode !== null;

  return (
    <div className="flex-1 flex min-h-0 gap-0">
      {/* ── 좌측: 트리 영역 (70% when detail open, 100% when closed) ── */}
      <div className={`bg-white rounded-lg shadow-sm border border-slate-100 overflow-hidden flex flex-col transition-all duration-300 ${hasSelection ? 'lg:flex-1 lg:basis-auto' : 'w-full'}`}>
        {/* Header */}
        <div className="px-4 py-3 border-b border-slate-100">
          <h2 className="text-sm font-semibold text-slate-800 flex items-center gap-2">
            <span className="text-blue-500">📁</span>
            {dept}
          </h2>
        </div>

        {/* Controls */}
        {!loading && flatNodes.length > 0 && (
          <TreeControls
            onExpandAll={handleExpandAll}
            onCollapseAll={handleCollapseAll}
            nodeCount={flatNodes.length}
          />
        )}

        {/* Content */}
        <div className="overflow-y-auto flex-1">
          {loading ? (
            <div className="p-6 space-y-3">
              {[1, 2, 3, 4].map((i) => (
                <div key={i} className="animate-pulse flex items-center gap-3">
                  <div className="w-4 h-4 bg-slate-200 rounded" />
                  <div className="flex-1 h-4 bg-slate-200 rounded" style={{ width: `${60 + i * 10}%` }} />
                  <div className="w-16 h-4 bg-slate-100 rounded" />
                </div>
              ))}
            </div>
          ) : error ? (
            <div className="p-6 text-center text-sm text-red-400">{error}</div>
          ) : flatNodes.length === 0 ? (
            <div className="p-6 text-center text-sm text-slate-400">
              표시할 항목이 없습니다
            </div>
          ) : (
            <div key={expandKey}>
              {rootNodes.map((node) => (
                <TreeNode key={node.id} node={node} depth={0} autoExpand={bulkExpand} onSelect={setSelectedNode} />
              ))}
            </div>
          )}
        </div>
      </div>

      {/* ── 우측: 상세 패널 (30%) ── */}
      {selectedNode && (
        <BudgetDetailPanel node={selectedNode} onClose={() => setSelectedNode(null)} />
      )}
    </div>
  );
}
