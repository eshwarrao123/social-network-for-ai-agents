"use client";

import React from "react";
import { Plus, Filter } from "lucide-react";
import { cn } from "@/lib/utils";

interface FeedFilterBarProps {
  activeType: string;
  onSelectType: (type: string) => void;
  onOpenPublish: () => void;
  totalReturned?: number;
}

const FILTER_OPTIONS: { label: string; value: string }[] = [
  { label: "All Opportunities", value: "all" },
  { label: "Announcements", value: "announcement" },
  { label: "Market Updates", value: "market_update" },
  { label: "Collaborations", value: "collaboration" },
  { label: "Promotions", value: "promotion" },
];

export function FeedFilterBar({
  activeType,
  onSelectType,
  onOpenPublish,
  totalReturned,
}: FeedFilterBarProps) {
  return (
    <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-4 border-b border-[#E0E6DF]">
      {/* Category Filter Pills in Segmented Control */}
      <div className="flex items-center gap-2 overflow-x-auto pb-1 sm:pb-0 scrollbar-none">
        <span className="text-xs text-[#647169] flex items-center gap-1.5 shrink-0 font-medium select-none">
          <Filter className="w-3.5 h-3.5 text-[#647169]" />
          <span className="hidden sm:inline">Category:</span>
        </span>

        <div
          role="tablist"
          aria-label="Filter opportunities by category"
          className="flex items-center gap-1 p-1 rounded-xl bg-[#EEF1ED] border border-[#E0E6DF]"
        >
          {FILTER_OPTIONS.map((opt) => {
            const isSelected = activeType === opt.value;
            return (
              <button
                key={opt.value}
                type="button"
                role="tab"
                aria-selected={isSelected}
                onClick={() => onSelectType(opt.value)}
                className={cn(
                  "px-3 py-1.5 rounded-lg text-xs font-medium transition-all shrink-0 whitespace-nowrap select-none min-h-[36px]",
                  isSelected
                    ? "bg-white text-[#1B2520] shadow-xs font-semibold border border-[#E0E6DF]"
                    : "text-[#647169] hover:text-[#1B2520] hover:bg-white/50"
                )}
              >
                {opt.label}
              </button>
            );
          })}
        </div>
      </div>

      {/* Publish Action CTA */}
      <div className="flex items-center gap-3 shrink-0">
        {totalReturned !== undefined && (
          <span className="hidden md:inline text-xs font-mono text-[#647169]">
            {totalReturned} {totalReturned === 1 ? "opportunity" : "opportunities"}
          </span>
        )}
        <button
          type="button"
          onClick={onOpenPublish}
          className="flex items-center gap-1.5 px-4 py-2 min-h-[40px] rounded-lg bg-[#244C3B] hover:bg-[#183A2C] text-white text-xs font-semibold shadow-none transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#244C3B] focus-visible:ring-offset-2 select-none"
        >
          <Plus className="w-4 h-4" />
          <span>Broadcast Opportunity</span>
        </button>
      </div>
    </div>
  );
}
