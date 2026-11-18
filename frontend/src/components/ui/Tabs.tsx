"use client";

import React from "react";
import { cn } from "@/lib/utils";

export interface TabItem {
  id: string;
  label: string;
  icon?: React.ReactNode;
  count?: number;
  disabled?: boolean;
}

export interface TabsProps {
  tabs: TabItem[];
  activeTab: string;
  onChange: (tabId: string) => void;
  className?: string;
}

export function Tabs({ tabs, activeTab, onChange, className }: TabsProps) {
  return (
    <div
      role="tablist"
      aria-orientation="horizontal"
      className={cn(
        "flex items-center gap-1 p-1 rounded-lg bg-[#EEF1ED] border border-[#E0E6DF]",
        className
      )}
    >
      {tabs.map((tab) => {
        const isActive = activeTab === tab.id;
        return (
          <button
            key={tab.id}
            role="tab"
            aria-selected={isActive}
            aria-controls={`tabpanel-${tab.id}`}
            id={`tab-${tab.id}`}
            disabled={tab.disabled}
            onClick={() => onChange(tab.id)}
            className={cn(
              "flex items-center justify-center gap-2 px-3.5 py-1.5 rounded-md text-xs font-medium transition-all select-none",
              "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#244C3B]",
              "disabled:opacity-40 disabled:pointer-events-none",
              isActive
                ? "bg-white text-[#1B2520] shadow-sm font-semibold border border-[#E0E6DF]"
                : "text-[#647169] hover:text-[#1B2520] hover:bg-white/50 border border-transparent"
            )}
          >
            {tab.icon && <span className="w-3.5 h-3.5">{tab.icon}</span>}
            <span>{tab.label}</span>
            {tab.count !== undefined && (
              <span
                className={cn(
                  "px-1.5 py-0.5 rounded-full text-[11px] font-semibold",
                  isActive
                    ? "bg-[#E4EEE8] text-[#183A2C]"
                    : "bg-[#E0E6DF]/60 text-[#647169]"
                )}
              >
                {tab.count}
              </span>
            )}
          </button>
        );
      })}
    </div>
  );
}
