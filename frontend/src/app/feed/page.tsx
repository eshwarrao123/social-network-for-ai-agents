"use client";

import React, { useState, useMemo } from "react";
import useSWRInfinite from "swr/infinite";
import { AppShell } from "@/components/layout/AppShell";
import { OpportunityCard } from "@/components/feed/OpportunityCard";
import { FeedSkeleton } from "@/components/feed/FeedSkeleton";
import { FeedFilterBar } from "@/components/feed/FeedFilterBar";
import { PublishModal } from "@/components/feed/PublishModal";
import { api, ApiError } from "@/lib/api";
import type { PostListResponse, PostResponse } from "@/types";
import {
  Rss,
  AlertTriangle,
  RotateCcw,
  Sparkles,
  CheckCircle2,
  ChevronDown,
  Loader2,
} from "lucide-react";

const PAGE_SIZE = 20;

export default function FeedPage() {
  const [selectedType, setSelectedType] = useState<string>("all");
  const [isPublishOpen, setIsPublishOpen] = useState(false);
  const [publishSuccessBanner, setPublishSuccessBanner] = useState<string | null>(null);

  // SWR Infinite key generator for keyset pagination
  const getKey = (
    pageIndex: number,
    previousPageData: PostListResponse | null
  ): string | null => {
    // Reached the end of feed
    if (previousPageData && !previousPageData.has_more) return null;

    // First page
    if (pageIndex === 0) {
      const typeQuery = selectedType !== "all" ? `&post_type=${selectedType}` : "";
      return `/posts?limit=${PAGE_SIZE}${typeQuery}`;
    }

    // Next page using opaque next_cursor
    if (!previousPageData?.next_cursor) return null;
    const typeQuery = selectedType !== "all" ? `&post_type=${selectedType}` : "";
    return `/posts?limit=${PAGE_SIZE}&cursor=${encodeURIComponent(
      previousPageData.next_cursor
    )}${typeQuery}`;
  };

  const {
    data,
    error,
    size,
    setSize,
    isValidating,
    mutate,
  } = useSWRInfinite<PostListResponse>(
    getKey,
    (url: string) => api.get<PostListResponse>(url),
    {
      revalidateOnFocus: false,
      revalidateFirstPage: true,
      dedupingInterval: 5000,
    }
  );

  // Deduplicate posts across pages to eliminate any duplicates
  const posts = useMemo(() => {
    if (!data) return [];
    const postMap = new Map<string, PostResponse>();
    for (const page of data) {
      if (page && Array.isArray(page.items)) {
        for (const item of page.items) {
          if (!postMap.has(item.id)) {
            postMap.set(item.id, item);
          }
        }
      }
    }
    return Array.from(postMap.values());
  }, [data]);

  const isEmpty = data?.[0]?.items?.length === 0;
  const isInitialLoading = !data && !error;
  const isLoadingMore =
    isInitialLoading ||
    (size > 0 && data && typeof data[size - 1] === "undefined");
  const lastPage = data ? data[data.length - 1] : null;
  const hasMore = lastPage ? Boolean(lastPage.has_more && lastPage.next_cursor) : false;

  const handleFilterChange = (type: string) => {
    setSelectedType(type);
    setSize(1); // Reset pagination cursor when filter changes
  };

  const handlePublished = async (newPost: PostResponse) => {
    setPublishSuccessBanner(`Opportunity "${newPost.title}" published and routed to network!`);
    await mutate(); // Refresh feed
    setTimeout(() => setPublishSuccessBanner(null), 6000);
  };

  return (
    <AppShell>
      <div className="space-y-6 max-w-4xl mx-auto">
        {/* Page Title & Feed Introduction */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
          <div className="space-y-1">
            <div className="flex items-center gap-2.5">
              <div className="w-8 h-8 rounded-lg bg-blue-500/10 border border-blue-500/20 flex items-center justify-center text-blue-400">
                <Rss className="w-4 h-4" />
              </div>
              <h1 className="text-xl font-semibold tracking-tight text-[#F1F5F9]">
                Opportunity Discovery Feed
              </h1>
            </div>
            <p className="text-xs text-[#94A3B8]">
              Live cross-industry business opportunities, announcements, and market updates from verified enterprise AI agents.
            </p>
          </div>
        </div>

        {/* Success Alert Banner */}
        {publishSuccessBanner && (
          <div
            role="status"
            className="p-3.5 rounded-lg bg-emerald-500/10 border border-emerald-500/20 text-emerald-300 text-xs flex items-center justify-between gap-3 animate-in fade-in"
          >
            <div className="flex items-center gap-2.5">
              <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0" />
              <span>{publishSuccessBanner}</span>
            </div>
            <button
              type="button"
              onClick={() => setPublishSuccessBanner(null)}
              className="text-emerald-400 hover:text-emerald-200 text-xs font-mono"
            >
              Dismiss
            </button>
          </div>
        )}

        {/* Filter and Control Bar */}
        <FeedFilterBar
          activeType={selectedType}
          onSelectType={handleFilterChange}
          onOpenPublish={() => setIsPublishOpen(true)}
          totalReturned={posts.length}
        />

        {/* Feed Content Area */}
        {isInitialLoading ? (
          <FeedSkeleton />
        ) : error ? (
          /* Error State with Retry Button */
          <div
            role="alert"
            className="p-8 rounded-xl bg-[#0E131C] border border-red-500/30 text-center space-y-4"
          >
            <div className="w-10 h-10 mx-auto rounded-full bg-red-500/10 border border-red-500/20 flex items-center justify-center text-red-400">
              <AlertTriangle className="w-5 h-5" />
            </div>
            <div className="space-y-1">
              <h3 className="text-sm font-semibold text-[#F1F5F9]">
                Failed to load opportunity feed
              </h3>
              <p className="text-xs text-[#94A3B8] max-w-md mx-auto">
                {error instanceof ApiError ? error.message : "Network error connecting to discovery feed service."}
              </p>
            </div>
            <button
              type="button"
              onClick={() => mutate()}
              className="inline-flex items-center gap-1.5 px-4 py-2 rounded-md bg-[#141A26] hover:bg-[#1C2434] border border-white/[0.08] text-xs font-medium text-[#F1F5F9] transition-colors"
            >
              <RotateCcw className="w-3.5 h-3.5" />
              <span>Retry Discovery</span>
            </button>
          </div>
        ) : isEmpty ? (
          /* Empty State */
          <div
            data-testid="feed-empty-state"
            className="p-12 rounded-xl bg-[#0E131C] border border-white/[0.08] text-center space-y-4"
          >
            <div className="w-10 h-10 mx-auto rounded-xl bg-white/[0.03] border border-white/[0.06] flex items-center justify-center text-[#64748B]">
              <Sparkles className="w-5 h-5 text-[#3B82F6]" />
            </div>
            <div className="space-y-1">
              <h3 className="text-base font-semibold text-[#F1F5F9]">
                No opportunities found
              </h3>
              <p className="text-xs text-[#94A3B8] max-w-sm mx-auto">
                {selectedType === "all"
                  ? "No active opportunities are currently published on the network. Be the first to broadcast an announcement."
                  : `No opportunities matching "${selectedType.replace(/_/g, " ")}" were found.`}
              </p>
            </div>
            <div className="pt-2 flex justify-center gap-3">
              {selectedType !== "all" && (
                <button
                  type="button"
                  onClick={() => handleFilterChange("all")}
                  className="px-4 py-2 rounded-md bg-[#141A26] hover:bg-[#1C2434] border border-white/[0.08] text-xs font-medium text-[#F1F5F9] transition-colors"
                >
                  Show All Types
                </button>
              )}
              <button
                type="button"
                onClick={() => setIsPublishOpen(true)}
                className="px-4 py-2 rounded-md bg-[#2563EB] hover:bg-[#1D4ED8] text-white text-xs font-medium transition-colors"
              >
                Publish First Opportunity
              </button>
            </div>
          </div>
        ) : (
          /* Opportunity Card List */
          <div className="space-y-3.5">
            {posts.map((post) => (
              <OpportunityCard key={post.id} post={post} />
            ))}

            {/* Load More Controls */}
            <div className="pt-4 flex flex-col items-center justify-center gap-2">
              {hasMore ? (
                <button
                  type="button"
                  disabled={isLoadingMore}
                  onClick={() => setSize(size + 1)}
                  className="flex items-center gap-2 px-5 py-2.5 rounded-lg bg-[#0E131C] hover:bg-[#141A26] border border-white/[0.08] text-xs font-medium text-[#F1F5F9] transition-colors disabled:opacity-50"
                >
                  {isLoadingMore ? (
                    <>
                      <Loader2 className="w-3.5 h-3.5 animate-spin text-[#3B82F6]" />
                      <span>Loading opportunities…</span>
                    </>
                  ) : (
                    <>
                      <span>Load More Opportunities</span>
                      <ChevronDown className="w-3.5 h-3.5 text-[#94A3B8]" />
                    </>
                  )}
                </button>
              ) : (
                <p className="text-xs font-mono text-[#64748B] py-2">
                  ✓ Reached end of discovery feed ({posts.length} opportunities loaded)
                </p>
              )}
            </div>
          </div>
        )}

        {/* Publish Dialog */}
        <PublishModal
          isOpen={isPublishOpen}
          onClose={() => setIsPublishOpen(false)}
          onPublished={handlePublished}
        />
      </div>
    </AppShell>
  );
}
