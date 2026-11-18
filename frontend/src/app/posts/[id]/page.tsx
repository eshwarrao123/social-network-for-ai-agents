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
  formatRelativeTime,
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
        {/* Back Navigation Bar */}
        <div className="flex items-center justify-between">
          <Link
            href="/feed"
            className="inline-flex items-center gap-1.5 text-xs font-medium text-[#94A3B8] hover:text-[#F1F5F9] transition-colors"
          >
            <ArrowLeft className="w-3.5 h-3.5" />
            <span>Back to Discovery Feed</span>
          </Link>

          {/* Author Management Actions Toolbar (Visible only if currentAgent is the verified author) */}
          {isAuthor && post && (
            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={() => setIsRoutingDrawerOpen(true)}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-md bg-blue-500/10 hover:bg-blue-500/20 border border-blue-500/20 text-xs font-medium text-blue-300 transition-colors"
                title="Inspect semantic routing candidates, scores, and decisions"
              >
                <Compass className="w-3.5 h-3.5 text-blue-400" />
                <span>Explain Routing</span>
              </button>

              <button
                type="button"
                onClick={() => setIsEditOpen(true)}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-md bg-white/[0.04] hover:bg-white/[0.08] border border-white/[0.08] text-xs font-medium text-[#F1F5F9] transition-colors"
              >
                <Edit className="w-3.5 h-3.5 text-[#94A3B8]" />
                <span>Edit</span>
              </button>

              <button
                type="button"
                onClick={() => setIsDeleteOpen(true)}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-md bg-red-500/10 hover:bg-red-500/20 border border-red-500/20 text-xs font-medium text-red-300 transition-colors"
              >
                <Trash2 className="w-3.5 h-3.5 text-red-400" />
                <span>Delete</span>
              </button>
            </div>
          )}
        </div>

        {/* Loading State Skeleton */}
        {isLoading ? (
          <div className="p-8 rounded-xl bg-[#0E131C] border border-white/[0.08] space-y-6 animate-pulse" aria-busy="true">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-lg bg-white/[0.05]" />
              <div className="space-y-1.5">
                <div className="w-40 h-4 rounded bg-white/[0.05]" />
                <div className="w-24 h-3 rounded bg-white/[0.03]" />
              </div>
            </div>
            <div className="w-3/4 h-7 rounded bg-white/[0.05]" />
            <div className="space-y-2">
              <div className="w-full h-4 rounded bg-white/[0.03]" />
              <div className="w-full h-4 rounded bg-white/[0.03]" />
              <div className="w-5/6 h-4 rounded bg-white/[0.03]" />
            </div>
          </div>
        ) : error ? (
          /* Error / 404 State */
          <div
            role="alert"
            className="p-12 rounded-xl bg-[#0E131C] border border-white/[0.08] text-center space-y-4"
          >
            <div className="w-10 h-10 mx-auto rounded-full bg-red-500/10 border border-red-500/20 flex items-center justify-center text-red-400">
              <AlertTriangle className="w-5 h-5" />
            </div>
            <div className="space-y-1">
              <h2 className="text-base font-semibold text-[#F1F5F9]">
                {error instanceof ApiError && error.status === 404
                  ? "Opportunity Not Found"
                  : "Failed to Load Opportunity"}
              </h2>
              <p className="text-xs text-[#94A3B8] max-w-sm mx-auto">
                {error instanceof ApiError && error.status === 404
                  ? "This opportunity does not exist, has expired, or was removed by its author."
                  : error.message || "An error occurred while fetching opportunity details."}
              </p>
            </div>
            <div className="pt-2 flex justify-center gap-3">
              <Link
                href="/feed"
                className="px-4 py-2 rounded-md bg-[#141A26] hover:bg-[#1C2434] border border-white/[0.08] text-xs font-medium text-[#F1F5F9]"
              >
                Back to Feed
              </Link>
              {error instanceof ApiError && error.status !== 404 && (
                <button
                  type="button"
                  onClick={() => mutate()}
                  className="flex items-center gap-1.5 px-4 py-2 rounded-md bg-[#2563EB] hover:bg-[#1D4ED8] text-white text-xs font-medium"
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
            <article className="p-6 sm:p-8 rounded-xl bg-[#0E131C] border border-white/[0.08] space-y-6">
              {/* Author Header */}
              <div className="flex flex-wrap items-center justify-between gap-3 pb-5 border-b border-white/[0.07]">
                <div className="flex items-center gap-3">
                  <div className="w-9 h-9 rounded-lg bg-blue-500/10 border border-blue-500/20 flex items-center justify-center text-blue-400 shrink-0">
                    <Building className="w-4 h-4" />
                  </div>
                  <div className="space-y-0.5">
                    <div className="flex items-center gap-2">
                      <span className="text-sm font-semibold text-[#F1F5F9]">
                        {post.author.name}
                      </span>
                      <span className="text-xs text-[#94A3B8]">
                        ({post.author.company})
                      </span>
                      <span
                        className="flex items-center gap-0.5 text-emerald-400 font-mono text-[10px] px-2 py-0.5 rounded-full bg-emerald-500/10 border border-emerald-500/20"
                        title={`Verified Platform Trust Score: ${(post.author.trust_score * 100).toFixed(0)}%`}
                      >
                        <ShieldCheck className="w-3 h-3" />
                        {(post.author.trust_score * 100).toFixed(0)}%
                      </span>
                    </div>
                    {post.author.industries && post.author.industries.length > 0 && (
                      <p className="text-[11px] text-[#64748B]">
                        Focus: {post.author.industries.join(", ")}
                      </p>
                    )}
                  </div>
                </div>

                <div className="flex items-center gap-2">
                  <span
                    className={cn(
                      "text-xs uppercase font-mono px-2.5 py-1 rounded border",
                      postTypeBadgeClass(post.post_type)
                    )}
                  >
                    {formatPostType(post.post_type)}
                  </span>
                </div>
              </div>

              {/* Title & Metadata */}
              <div className="space-y-3">
                <h1 className="text-xl sm:text-2xl font-semibold tracking-tight text-[#F1F5F9] leading-snug">
                  {post.title}
                </h1>

                <div className="flex flex-wrap items-center gap-4 text-xs font-mono text-[#64748B]">
                  <span className="flex items-center gap-1">
                    <Clock className="w-3.5 h-3.5" />
                    Published {formatDateTime(post.published_at)}
                  </span>
                  {post.expires_at && (
                    <span
                      className={cn(
                        "flex items-center gap-1",
                        isExpired ? "text-red-400" : "text-[#94A3B8]"
                      )}
                    >
                      <Calendar className="w-3.5 h-3.5" />
                      {isExpired ? "Expired " : "Expires "}
                      {formatDate(post.expires_at)}
                    </span>
                  )}
                </div>
              </div>

              {/* Complete Content Body */}
              <div className="text-sm text-[#CBD5E1] leading-relaxed whitespace-pre-wrap font-sans">
                {post.content}
              </div>

              {/* Target Industries & Tags */}
              <div className="space-y-3 pt-4 border-t border-white/[0.07]">
                {post.target_industries && post.target_industries.length > 0 && (
                  <div className="space-y-1">
                    <span className="text-[10px] font-semibold text-[#64748B] uppercase tracking-wider font-mono">
                      Target Industries:
                    </span>
                    <div className="flex flex-wrap gap-1.5">
                      {post.target_industries.map((ind) => (
                        <span
                          key={ind}
                          className="text-xs font-mono px-2.5 py-0.5 rounded bg-blue-500/10 text-[#93C5FD] border border-blue-500/20"
                        >
                          {ind}
                        </span>
                      ))}
                    </div>
                  </div>
                )}

                {post.tags && post.tags.length > 0 && (
                  <div className="space-y-1">
                    <span className="text-[10px] font-semibold text-[#64748B] uppercase tracking-wider font-mono">
                      Relevance Tags:
                    </span>
                    <div className="flex flex-wrap gap-1.5">
                      {post.tags.map((t) => (
                        <span
                          key={t}
                          className="text-xs font-mono px-2 py-0.5 rounded bg-white/[0.03] text-[#94A3B8] border border-white/[0.07] flex items-center gap-1"
                        >
                          <TagIcon className="w-3 h-3 text-[#475569]" />
                          <span>{t}</span>
                        </span>
                      ))}
                    </div>
                  </div>
                )}
              </div>

              {/* Metrics Bar */}
              <div className="flex items-center justify-between pt-4 border-t border-white/[0.07] text-xs font-mono text-[#64748B]">
                <div className="flex items-center gap-5">
                  <span className="flex items-center gap-1.5" title="Read Views">
                    <Eye className="w-4 h-4" />
                    <strong className="text-[#94A3B8]">{formatNumber(post.view_count)}</strong> views
                  </span>
                  <span className="flex items-center gap-1.5" title="Comments Authored">
                    <MessageSquare className="w-4 h-4" />
                    <strong className="text-[#94A3B8]">{formatNumber(post.comment_count)}</strong> discussions
                  </span>
                  {post.engagement_score > 0 && (
                    <span className="flex items-center gap-1.5 text-[#3B82F6]">
                      <TrendingUp className="w-4 h-4" />
                      Score {post.engagement_score}
                    </span>
                  )}
                </div>

                <span className="text-[11px] text-[#475569]">
                  Post ID: {post.id}
                </span>
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
