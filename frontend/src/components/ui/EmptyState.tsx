import React from "react";
import { cn } from "@/lib/utils";

export interface EmptyStateProps {
  icon?: React.ReactNode;
  title: string;
  description: string;
  badge?: string;
  action?: React.ReactNode;
  className?: string;
}

export function EmptyState({
  icon,
  title,
  description,
  badge,
  action,
  className,
}: EmptyStateProps) {
  return (
    <div
      className={cn(
        "flex flex-col items-center justify-center text-center p-8 rounded-xl bg-white border border-[#E0E6DF] space-y-3",
        className
      )}
    >
      {badge && (
        <span className="px-2.5 py-0.5 rounded-full text-xs font-mono font-medium bg-[#F8F9F6] text-[#647169] border border-[#E0E6DF]">
          {badge}
        </span>
      )}
      {icon && (
        <div className="w-10 h-10 rounded-lg bg-[#F8F9F6] border border-[#E0E6DF] flex items-center justify-center text-[#244C3B]">
          {icon}
        </div>
      )}
      <div className="space-y-1 max-w-sm">
        <h4 className="text-sm font-semibold text-[#1B2520]">{title}</h4>
        <p className="text-sm text-[#647169] leading-relaxed">{description}</p>
      </div>
      {action && <div className="pt-2">{action}</div>}
    </div>
  );
}
