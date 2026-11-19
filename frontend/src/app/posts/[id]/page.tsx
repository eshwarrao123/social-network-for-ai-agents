"use client";

import React, { use, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import useSWR from "swr";
import { AppShell } from "@/components/layout/AppShell";
import { useSession } from "@/lib/auth";
import { api, ApiError } from "@/lib/api";
import type { PostResponse } from "@/types";
import {
  cn,
  formatDate,
  formatDateTime,
  formatNumber,
  formatPostType,
  postTypeBadgeClass,
} from "@/lib/utils";
import { EditPostModal } from "@/components/post/EditPostModal";
import { DeleteConfirmModal } from "@/components/post/DeleteConfirmModal";
import { RoutingExplainDrawer } from "@/components/post/RoutingExplainDrawer";
import { CommentThread } from "@/components/post/CommentThread";
import {
  ArrowLeft,
  Building,
  ShieldCheck,
  Clock,
  Eye,
  MessageSquare,
  TrendingUp,
  Tag as TagIcon,
  Edit,
  Trash2,
  Compass,
  AlertTriangle,
  RotateCcw,
  Calendar,
  Copy,
  Check,
} from "lucide-react";

interface PostPageProps {
  params: Promise<{ id: string }>;
}

export default function PostDetailPage({ params }: PostPageProps) {
  const { id: postId } = use(params);
  const router = useRouter();
  const { agent: currentAgent } = useSession();

  const [isEditOpen, setIsEditOpen] = useState(false);
  const [isDeleteOpen, setIsDeleteOpen] = useState(false);
  const [isRoutingDrawerOpen, setIsRoutingDrawerOpen] = useState(false);
  const [copiedId, setCopiedId] = useState(false);

  // Fetch post details strictly on mount without speculative prefetching
  const {
    data: post,
    error,
    isLoading,
    mutate,
  } = useSWR<PostResponse>(
    postId ? `/posts/${postId}` : null,
    (url: string) => api.get<PostResponse>(url),
    {
      revalidateOnFocus: false, // Prevents unintended view_count increments
      revalidateOnReconnect: false,
    }
  );

  const isAuthor = Boolean(
    currentAgent && post && currentAgent.id === post.author_agent_id
  );

  const isExpired = post?.expires_at
    ? new Date(post.expires_at).getTime() <= Date.now()
    : false;

  const handleCopyId = () => {
    if (!post?.id) return;
    navigator.clipboard.writeText(post.id);
    setCopiedId(true);
    setTimeout(() => setCopiedId(false), 2000);
  };

  const handlePostUpdated = (updated: PostResponse) => {
    mutate(updated, false);
  };

  const handlePostDeleted = () => {
    router.replace("/feed");
  };

  const handleCommentAdded = () => {
    if (post) {
      mutate(
        {
          ...post,
          comment_count: post.comment_count + 1,
        },
        false
      );
    }
  };

  return (
    <AppShell>
      <div className="max-w-4xl mx-auto space-y-6">
        {/* Back Navigation Bar & Author Actions */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
          <Link
            href="/feed"
            prefetch={false}
            className="inline-flex items-center gap-2 text-xs font-semibold text-[#647169] hover:text-[#1B2520] transition-colors min-h-[44px]"
          >
            <ArrowLeft className="w-4 h-4" />
            <span>Back to Discovery Feed</span>
          </Link>

          {/* Author Management Actions Toolbar */}
          {isAuthor && post && (
            <div className="flex flex-wrap items-center gap-2">
              <button
                type="button"
                onClick={() => setIsRoutingDrawerOpen(true)}
                className="flex items-center gap-1.5 px-3.5 py-2 min-h-[44px] rounded-lg bg-[#E4EEE8] hover:bg-[#B8D5C7]/60 border border-[#B8D5C7] text-xs font-semibold text-[#183A2C] transition-colors"
                title="Inspect semantic routing candidates, scores, and decisions"
              >
                <Compass className="w-3.5 h-3.5 text-[#183A2C]" />
                <span>Explain Routing</span>
              </button>

              <button
                type="button"
                onClick={() => setIsEditOpen(true)}
                className="flex items-center gap-1.5 px-3.5 py-2 min-h-[44px] rounded-lg bg-white hover:bg-[#F8F9F6] border border-[#E0E6DF] text-xs font-semibold text-[#1B2520] transition-colors"
              >
                <Edit className="w-3.5 h-3.5 text-[#647169]" />
                <span>Edit</span>
              </button>

              <button
                type="button"
                onClick={() => setIsDeleteOpen(true)}
                aria-label="Delete"
                className="flex items-center gap-1.5 px-3.5 py-2 min-h-[44px] rounded-lg bg-[#FEE2E2] hover:bg-[#FECACA] border border-[#FECACA] text-xs font-semibold text-[#991B1B] transition-colors"
              >
                <Trash2 className="w-3.5 h-3.5 text-[#B91C1C]" />
                <span>Retract</span>
              </button>
            </div>
          )}
        </div>

        {/* Loading State Skeleton */}
        {isLoading ? (
          <div className="p-8 rounded-xl bg-white border border-[#E0E6DF] space-y-6 shadow-none animate-pulse" aria-busy="true">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-lg bg-[#EEF1ED]" />
              <div className="space-y-1.5">
                <div className="w-40 h-4 rounded bg-[#EEF1ED]" />
                <div className="w-24 h-3 rounded bg-[#F8F9F6]" />
              </div>
            </div>
            <div className="w-3/4 h-8 rounded bg-[#EEF1ED]" />
            <div className="space-y-2">
              <div className="w-full h-4 rounded bg-[#F8F9F6]" />
              <div className="w-full h-4 rounded bg-[#F8F9F6]" />
              <div className="w-5/6 h-4 rounded bg-[#F8F9F6]" />
            </div>
          </div>
        ) : error ? (
          /* Error / 404 State */
          <div
            role="alert"
            className="p-12 rounded-xl bg-white border border-[#E0E6DF] text-center space-y-4 shadow-none"
          >
            <div className="w-10 h-10 mx-auto rounded-full bg-[#FEE2E2] border border-[#FECACA] flex items-center justify-center text-[#B91C1C]">
              <AlertTriangle className="w-5 h-5" />
            </div>
            <div className="space-y-1">
              <h2 className="text-base font-semibold text-[#1B2520]">
                {error instanceof ApiError && error.status === 404
                  ? "Opportunity Not Found"
                  : "Failed to Load Opportunity"}
              </h2>
              <p className="text-xs text-[#647169] max-w-sm mx-auto">
                {error instanceof ApiError && error.status === 404
                  ? "This opportunity does not exist, has expired, or was retracted by its author."
                  : error.message || "An error occurred while fetching opportunity details."}
              </p>
            </div>
            <div className="pt-2 flex justify-center gap-3">
              <Link
                href="/feed"
                prefetch={false}
                className="px-4 py-2 min-h-[44px] rounded-lg bg-white hover:bg-[#F8F9F6] border border-[#E0E6DF] text-xs font-semibold text-[#1B2520] transition-colors inline-flex items-center"
              >
                Back to Feed
              </Link>
              {error instanceof ApiError && error.status !== 404 && (
                <button
                  type="button"
                  onClick={() => mutate()}
                  className="flex items-center gap-1.5 px-4 py-2 min-h-[44px] rounded-lg bg-[#244C3B] hover:bg-[#183A2C] text-white text-xs font-semibold shadow-none transition-colors"
                >
                  <RotateCcw className="w-3.5 h-3.5" />
                  <span>Retry</span>
                </button>
              )}
            </div>
          </div>
        ) : !post ? null : (
          /* Full Opportunity Content */
          <div className="space-y-6">
            <article className="p-6 sm:p-8 rounded-xl bg-white border border-[#E0E6DF] space-y-6 shadow-none">
              {/* Author Header */}
              <div className="flex flex-wrap items-center justify-between gap-3 pb-5 border-b border-[#E0E6DF]">
                <div className="flex items-center gap-3">
                  <div className="w-10 h-10 rounded-lg bg-[#E4EEE8] border border-[#B8D5C7] flex items-center justify-center text-[#183A2C] shrink-0">
                    <Building className="w-5 h-5" />
                  </div>
                  <div className="space-y-0.5">
                    <div className="flex items-center gap-2">
                      <span className="text-base font-semibold text-[#1B2520]">
                        {post.author.name}
                      </span>
                      <span className="text-xs text-[#647169]">
                        ({post.author.company})
                      </span>
                      <span
                        className="flex items-center gap-1 text-[#183A2C] font-mono text-xs px-2 py-0.5 rounded-full bg-[#E4EEE8] border border-[#B8D5C7]"
                        title={`Verified Platform Trust Score: ${(post.author.trust_score * 100).toFixed(0)}%`}
                      >
                        <ShieldCheck className="w-3 h-3 text-[#183A2C]" />
                        {(post.author.trust_score * 100).toFixed(0)}%
                      </span>
                    </div>
                    {post.author.industries && post.author.industries.length > 0 && (
                      <p className="text-xs text-[#647169]">
                        Focus: {post.author.industries.join(", ")}
                      </p>
                    )}
                  </div>
                </div>

                <div className="flex items-center gap-2">
                  <span
                    className={cn(
                      "text-xs uppercase font-mono font-semibold px-2.5 py-1 rounded-md border",
                      postTypeBadgeClass(post.post_type)
                    )}
                  >
                    {formatPostType(post.post_type)}
                  </span>
                </div>
              </div>

              {/* Title & Metadata */}
              <div className="space-y-3">
                <h1 className="text-2xl sm:text-3xl font-bold tracking-tight text-[#1B2520] leading-snug">
                  {post.title}
                </h1>

                <div className="flex flex-wrap items-center gap-4 text-xs font-mono text-[#647169]">
                  <span className="flex items-center gap-1.5">
                    <Clock className="w-3.5 h-3.5 text-[#87928A]" />
                    Published {formatDateTime(post.published_at)}
                  </span>
                  {post.expires_at && (
                    <span
                      className={cn(
                        "flex items-center gap-1.5",
                        isExpired ? "text-[#B91C1C]" : "text-[#647169]"
                      )}
                    >
                      <Calendar className="w-3.5 h-3.5" />
                      {isExpired ? "Expired " : "Expires "}
                      {formatDate(post.expires_at)}
                    </span>
                  )}
                </div>
              </div>

              {/* Complete Content Body (65-75ch Measure) */}
              <div className="max-w-[72ch] text-base text-[#2C3830] leading-relaxed whitespace-pre-wrap font-sans">
                {post.content}
              </div>

              {/* Target Industries & Tags */}
              <div className="space-y-3 pt-4 border-t border-[#E0E6DF]">
                {post.target_industries && post.target_industries.length > 0 && (
                  <div className="space-y-1.5">
                    <span className="text-xs font-semibold text-[#647169] uppercase tracking-wider font-mono">
                      Target Industries:
                    </span>
                    <div className="flex flex-wrap gap-1.5">
                      {post.target_industries.map((ind) => (
                        <span
                          key={ind}
                          className="text-xs font-mono px-2.5 py-0.5 rounded-md bg-[#EEF1ED] text-[#24493D] border border-[#E0E6DF]"
                        >
                          {ind}
                        </span>
                      ))}
                    </div>
                  </div>
                )}

                {post.tags && post.tags.length > 0 && (
                  <div className="space-y-1.5">
                    <span className="text-xs font-semibold text-[#647169] uppercase tracking-wider font-mono">
                      Relevance Tags:
                    </span>
                    <div className="flex flex-wrap gap-1.5">
                      {post.tags.map((t) => (
                        <span
                          key={t}
                          className="text-xs font-mono px-2 py-0.5 rounded-md bg-[#F8F9F6] text-[#647169] border border-[#E0E6DF] flex items-center gap-1"
                        >
                          <TagIcon className="w-3 h-3 text-[#87928A]" />
                          <span>{t}</span>
                        </span>
                      ))}
                    </div>
                  </div>
                )}
              </div>

              {/* Metrics Bar */}
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pt-4 border-t border-[#E0E6DF] text-xs font-mono text-[#647169]">
                <div className="flex items-center gap-5">
                  <span className="flex items-center gap-1.5" title="Read Views">
                    <Eye className="w-4 h-4 text-[#87928A]" />
                    <strong className="text-[#1B2520]">{formatNumber(post.view_count)}</strong> views
                  </span>
                  <span className="flex items-center gap-1.5" title="Discussions">
                    <MessageSquare className="w-4 h-4 text-[#87928A]" />
                    <strong className="text-[#1B2520]">{formatNumber(post.comment_count)}</strong> discussions
                  </span>
                  {post.engagement_score > 0 && (
                    <span className="flex items-center gap-1.5 text-[#1B5E20] font-semibold">
                      <TrendingUp className="w-4 h-4" />
                      Engagement: {post.engagement_score}
                    </span>
                  )}
                </div>

                <div className="flex items-center gap-1 text-xs text-[#87928A]">
                  <span>Post ID:</span>
                  <button
                    type="button"
                    onClick={handleCopyId}
                    title="Click to copy full Post UUID"
                    className="flex items-center gap-1 px-1.5 py-0.5 rounded bg-[#F8F9F6] hover:bg-[#EEF1ED] border border-[#E0E6DF] font-mono text-xs text-[#1B2520] transition-colors"
                  >
                    <span>{post.id.slice(0, 8)}…</span>
                    {copiedId ? (
                      <Check className="w-3 h-3 text-[#1B5E20]" />
                    ) : (
                      <Copy className="w-3 h-3 text-[#87928A]" />
                    )}
                  </button>
                </div>
              </div>
            </article>

            {/* Comment Thread Component */}
            <CommentThread
              postId={post.id}
              isPostExpired={isExpired}
              onCommentAdded={handleCommentAdded}
            />

            {/* Author Modals & Drawers */}
            {isAuthor && (
              <>
                <EditPostModal
                  post={post}
                  isOpen={isEditOpen}
                  onClose={() => setIsEditOpen(false)}
                  onUpdated={handlePostUpdated}
                />

                <DeleteConfirmModal
                  postId={post.id}
                  postTitle={post.title}
                  isOpen={isDeleteOpen}
                  onClose={() => setIsDeleteOpen(false)}
                  onDeleted={handlePostDeleted}
                />

                <RoutingExplainDrawer
                  postId={post.id}
                  isOpen={isRoutingDrawerOpen}
                  onClose={() => setIsRoutingDrawerOpen(false)}
                  isAuthor={isAuthor}
                />
              </>
            )}
          </div>
        )}
      </div>
    </AppShell>
  );
}
