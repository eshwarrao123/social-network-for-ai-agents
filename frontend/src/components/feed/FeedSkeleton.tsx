import React from "react";

export function FeedSkeleton() {
  return (
    <div className="space-y-3.5" aria-busy="true" aria-label="Loading opportunities">
      {[1, 2, 3].map((i) => (
        <div
          key={i}
          className="p-5 sm:p-6 rounded-xl bg-white border border-[#E0E6DF] space-y-4 shadow-none animate-pulse"
        >
          {/* Header */}
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2.5">
              <div className="w-7 h-7 rounded-lg bg-[#EEF1ED]" />
              <div className="h-4 w-32 rounded bg-[#EEF1ED]" />
              <div className="h-4 w-20 rounded bg-[#F8F9F6]" />
            </div>
            <div className="h-4 w-20 rounded bg-[#EEF1ED]" />
          </div>

          {/* Title & Preview */}
          <div className="space-y-2">
            <div className="h-5 w-3/4 rounded bg-[#EEF1ED]" />
            <div className="h-4 w-full rounded bg-[#F8F9F6]" />
            <div className="h-4 w-4/5 rounded bg-[#F8F9F6]" />
          </div>

          {/* Tags */}
          <div className="flex gap-2">
            <div className="h-5 w-20 rounded bg-[#EEF1ED]" />
            <div className="h-5 w-24 rounded bg-[#EEF1ED]" />
            <div className="h-5 w-16 rounded bg-[#F8F9F6]" />
          </div>

          {/* Footer */}
          <div className="pt-3.5 border-t border-[#E0E6DF] flex items-center justify-between">
            <div className="flex gap-4">
              <div className="h-4 w-16 rounded bg-[#EEF1ED]" />
              <div className="h-4 w-16 rounded bg-[#EEF1ED]" />
              <div className="h-4 w-24 rounded bg-[#EEF1ED]" />
            </div>
            <div className="h-4 w-28 rounded bg-[#EEF1ED]" />
          </div>
        </div>
      ))}
    </div>
  );
}
