'use client';

import { useState, useEffect, useCallback, useMemo } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import type { TreeNodeData } from '@/types';
import { fetchTree } from '@/lib/api';
import TreeNode from '@/components/TreeNode';
import TreeControls from '@/components/TreeControls';

/** 평면 노드 리스트 → 부모-자식 트리 구조로 변환 */
function buildTree(flatNodes: TreeNodeData[]): TreeNodeData[] {
  const map = new Map<number, TreeNodeData>();
  const roots: TreeNodeData[] = [];
  
  for (const n of flatNodes) {
    map.set(n.id, { ...n, children: [], has_children: false });
  }
  
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

export default function DepartmentPageClient({ name }: { name: string }) {
  const router = useRouter();
  const deptName = decodeURIComponent(name);

  const [flatNodes, setFlatNodes] = useState<TreeNodeData[]>([]);
  const [loading, setLoading] = useState(true);
  const [expandKey, setExpandKey] = useState(0);
  const [bulkExpand, setBulkExpand] = useState<boolean>(false);

  const rootNodes = useMemo(() => buildTree(flatNodes), [flatNodes]);

  useEffect(() => {
    setLoading(true);
    fetchTree(deptName)
      .then((data) => {
        setFlatNodes(data);
      })
      .finally(() => setLoading(false));
  }, [deptName]);

  const handleExpandAll = useCallback(() => {
    setBulkExpand(true);
    setExpandKey((k) => k + 1);
  }, []);

  const handleCollapseAll = useCallback(() => {
    setBulkExpand(false);
    setExpandKey((k) => k + 1);
  }, []);

  return (
    <main className="flex-1 max-w-screen-2xl w-full mx-auto px-4 sm:px-6 py-6">
      {/* Breadcrumb */}
      <nav className="flex items-center gap-2 text-sm mb-4 text-slate-500">
        <Link href="/" className="hover:text-blue-600 transition-colors">대시보드</Link>
        <span>/</span>
        <span className="font-medium text-slate-700">{deptName}</span>
      </nav>

      {/* Tree */}
      <div className="bg-white rounded-lg shadow-sm border border-slate-100 overflow-hidden flex flex-col" style={{ minHeight: 'calc(100vh - 180px)' }}>
        <div className="px-4 py-3 border-b border-slate-100">
          <h1 className="text-base font-bold text-slate-800 flex items-center gap-2">
            <span className="text-blue-500">📁</span>
            {deptName}
          </h1>
        </div>

        {!loading && flatNodes.length > 0 && (
          <TreeControls
            onExpandAll={handleExpandAll}
            onCollapseAll={handleCollapseAll}
            nodeCount={flatNodes.length}
          />
        )}

        <div className="overflow-y-auto flex-1">
          {loading ? (
            <div className="p-6 space-y-3">
              {[1, 2, 3, 4, 5, 6].map((i) => (
                <div key={i} className="animate-pulse flex items-center gap-3">
                  <div className="w-4 h-4 bg-slate-200 rounded" />
                  <div className="flex-1 h-4 bg-slate-200 rounded" style={{ width: `${50 + i * 8}%` }} />
                  <div className="w-16 h-4 bg-slate-100 rounded" />
                </div>
              ))}
            </div>
          ) : flatNodes.length === 0 ? (
            <div className="p-8 text-center text-sm text-slate-400">
              데이터가 없습니다
            </div>
          ) : (
            <div key={expandKey}>
              {rootNodes.map((node) => (
                <TreeNode key={node.id} node={node} depth={0} autoExpand={bulkExpand} />
              ))}
            </div>
          )}
        </div>
      </div>
    </main>
  );
}
