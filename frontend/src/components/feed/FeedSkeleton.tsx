import React from "react";

export function FeedSkeleton() {
  return (
    <div className="space-y-3.5" aria-busy="true" aria-label="Loading opportunities">
      {[1, 2, 3].map((i) => (
        <div
          key={i}
          className="p-5 rounded-xl bg-[#0E131C] border border-white/[0.08] space-y-4 animate-pulse"
        >
          {/* Header */}
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <div className="w-6 h-6 rounded bg-white/[0.05]" />
              <div className="h-4 w-28 rounded bg-white/[0.05]" />
              <div className="h-4 w-20 rounded bg-white/[0.03]" />
            </div>
            <div className="h-4 w-16 rounded bg-white/[0.04]" />
          </div>

          {/* Title & Preview */}
          <div className="space-y-2">
            <div className="h-5 w-3/4 rounded bg-white/[0.05]" />
            <div className="h-4 w-full rounded bg-white/[0.03]" />
            <div className="h-4 w-5/6 rounded bg-white/[0.03]" />
          </div>

          {/* Tags */}
          <div className="flex gap-2">
            <div className="h-4 w-16 rounded bg-white/[0.04]" />
            <div className="h-4 w-16 rounded bg-white/[0.04]" />
            <div className="h-4 w-12 rounded bg-white/[0.04]" />
          </div>

          {/* Footer */}
          <div className="pt-3 border-t border-white/[0.07] flex justify-between">
            <div className="flex gap-4">
              <div className="h-4 w-10 rounded bg-white/[0.04]" />
              <div className="h-4 w-10 rounded bg-white/[0.04]" />
            </div>
            <div className="h-4 w-24 rounded bg-white/[0.04]" />
          </div>
        </div>
      ))}
    </div>
  );
}
