'use client';

interface Props {
  onExpandAll: () => void;
  onCollapseAll: () => void;
  nodeCount: number;
}

export default function TreeControls({ onExpandAll, onCollapseAll, nodeCount }: Props) {
  return (
    <div className="flex items-center justify-between px-4 py-2.5 bg-slate-50/80 border-b border-slate-100">
      <span className="text-xs text-slate-500">
        총 <span className="font-medium text-slate-700">{nodeCount.toLocaleString()}</span>개 항목
      </span>
      <div className="flex gap-1.5">
        <button
          onClick={onExpandAll}
          className="inline-flex items-center gap-1 px-2.5 py-1 text-[11px] font-medium text-blue-600 bg-blue-50 
                     hover:bg-blue-100 rounded-md transition-colors"
        >
          <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M12 6v12M6 12h12" />
          </svg>
          전체 펼치기
        </button>
        <button
          onClick={onCollapseAll}
          className="inline-flex items-center gap-1 px-2.5 py-1 text-[11px] font-medium text-slate-600 bg-white
                     hover:bg-slate-100 border border-slate-200 rounded-md transition-colors"
        >
          <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M12 18V6" />
          </svg>
          전체 접기
        </button>
      </div>
    </div>
  );
}
