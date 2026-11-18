"use client";

import React from "react";
import { Plus, Filter } from "lucide-react";
import type { PostType } from "@/types";
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
    <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-4 border-b border-white/[0.07]">
      {/* Category Filter Pills in Segmented Control */}
      <div className="flex items-center gap-2 overflow-x-auto pb-1 sm:pb-0 scrollbar-none">
        <span className="text-xs text-[#64748B] flex items-center gap-1 shrink-0 font-medium">
          <Filter className="w-3.5 h-3.5 text-[#64748B]" />
          <span className="hidden sm:inline">Type:</span>
        </span>

        <div
          role="tablist"
          aria-label="Filter opportunities by category"
          className="flex items-center gap-1 p-1 rounded-lg bg-[#0B0F17] border border-white/[0.08]"
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
                  "px-3 py-1 rounded-md text-xs font-medium transition-all shrink-0 whitespace-nowrap select-none",
                  isSelected
                    ? "bg-white/[0.08] text-[#F1F5F9] shadow-sm font-semibold border border-white/[0.1]"
                    : "text-[#94A3B8] hover:text-[#F1F5F9] hover:bg-white/[0.03]"
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
          <span className="hidden md:inline text-xs font-mono text-[#64748B]">
            {totalReturned} displayed
          </span>
        )}
        <button
          type="button"
          onClick={onOpenPublish}
          className="flex items-center gap-1.5 px-3.5 py-1.5 rounded-md bg-[#2563EB] hover:bg-[#1D4ED8] text-white text-xs font-medium shadow-sm transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#2563EB] focus-visible:ring-offset-2 focus-visible:ring-offset-[#090B10]"
        >
          <Plus className="w-4 h-4" />
          <span>Publish Opportunity</span>
        </button>
      </div>
    </div>
  );
}
