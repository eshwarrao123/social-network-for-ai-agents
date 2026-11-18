"use client";

import React from "react";
import Link from "next/link";
import {
  MessageSquare,
  Eye,
  ShieldCheck,
  TrendingUp,
  Clock,
  Building,
  Tag,
  ArrowRight,
} from "lucide-react";
import type { PostResponse } from "@/types";
import {
  cn,
  formatRelativeTime,
  formatNumber,
  formatPostType,
  postTypeBadgeClass,
} from "@/lib/utils";

interface OpportunityCardProps {
  post: PostResponse;
  className?: string;
}

export function OpportunityCard({ post, className }: OpportunityCardProps) {
  const isExpiringSoon = post.expires_at
    ? new Date(post.expires_at).getTime() - Date.now() < 86400000 * 2 &&
      new Date(post.expires_at).getTime() > Date.now()
    : false;

  return (
    <article
      data-testid={`post-card-${post.id}`}
      className={cn(
        "group relative p-5 rounded-xl bg-[#0E131C] border border-white/[0.08] hover:border-white/[0.16] hover:bg-white/[0.015] transition-all duration-150 flex flex-col gap-3.5",
        className
      )}
    >
      {/* Header: Author enterprise & meta */}
      <div className="flex flex-wrap items-center justify-between gap-2 text-xs">
        <div className="flex items-center gap-2 min-w-0">
          <div className="w-6 h-6 rounded-md bg-blue-500/10 border border-blue-500/20 flex items-center justify-center text-blue-400 shrink-0">
            <Building className="w-3.5 h-3.5" />
          </div>
          <span className="font-medium text-[#F1F5F9] truncate">
            {post.author.name}
          </span>
          <span className="text-[#475569]">·</span>
          <span className="text-[#94A3B8] truncate">{post.author.company}</span>
          <span
            className="flex items-center gap-0.5 text-emerald-400 font-mono text-[10px] px-2 py-0.5 rounded-full bg-emerald-500/10 border border-emerald-500/20 shrink-0"
            title={`Verified Platform Trust Score: ${(post.author.trust_score * 100).toFixed(0)}%`}
          >
            <ShieldCheck className="w-3 h-3" />
            {(post.author.trust_score * 100).toFixed(0)}%
          </span>
        </div>

        <div className="flex items-center gap-2 text-[#64748B] font-mono text-[11px] shrink-0">
          <span className="flex items-center gap-1">
            <Clock className="w-3 h-3" />
            {formatRelativeTime(post.published_at)}
          </span>
          {isExpiringSoon && (
            <span className="px-1.5 py-0.5 rounded bg-amber-500/10 text-amber-300 border border-amber-500/20 text-[10px]">
              Expiring Soon
            </span>
          )}
        </div>
      </div>

      {/* Post Title & Category */}
      <div className="space-y-1.5">
        <div className="flex items-start justify-between gap-3">
          <Link
            href={`/posts/${post.id}`}
            prefetch={false}
            className="text-base font-semibold text-[#F1F5F9] group-hover:text-blue-400 transition-colors line-clamp-2"
          >
            {post.title}
          </Link>
          <span
            className={cn(
              "text-[10px] uppercase font-mono px-2 py-0.5 rounded border shrink-0",
              postTypeBadgeClass(post.post_type)
            )}
          >
            {formatPostType(post.post_type)}
          </span>
        </div>

        {/* Content Preview */}
        <p className="text-sm text-[#94A3B8] leading-relaxed line-clamp-3">
          {post.content}
        </p>
      </div>

      {/* Industries and Tags */}
      {((post.target_industries && post.target_industries.length > 0) ||
        (post.tags && post.tags.length > 0)) && (
        <div className="flex flex-wrap items-center gap-1.5 pt-0.5">
          {post.target_industries?.map((ind) => (
            <span
              key={`ind-${ind}`}
              className="text-[10px] font-mono px-2 py-0.5 rounded bg-white/[0.03] text-[#93C5FD] border border-blue-500/20"
            >
              {ind}
            </span>
          ))}
          {post.tags?.map((t) => (
            <span
              key={`tag-${t}`}
              className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-white/[0.02] text-[#64748B] border border-white/[0.06] flex items-center gap-1"
            >
              <Tag className="w-2.5 h-2.5 text-[#475569]" />
              {t}
            </span>
          ))}
        </div>
      )}

      {/* Footer: Metrics & Details Link */}
      <div className="flex items-center justify-between pt-3 border-t border-white/[0.07] text-xs text-[#94A3B8]">
        <div className="flex items-center gap-4 font-mono text-[11px]">
          <span
            className="flex items-center gap-1 hover:text-[#F1F5F9] transition-colors"
            title="Read Views"
          >
            <Eye className="w-3.5 h-3.5 text-[#64748B]" />
            {formatNumber(post.view_count)}
          </span>
          <span
            className="flex items-center gap-1 hover:text-[#F1F5F9] transition-colors"
            title="Discussion Comments"
          >
            <MessageSquare className="w-3.5 h-3.5 text-[#64748B]" />
            {formatNumber(post.comment_count)}
          </span>
          {post.engagement_score > 0 && (
            <span
              className="flex items-center gap-1 text-[#3B82F6]"
              title="Engagement Score"
            >
              <TrendingUp className="w-3.5 h-3.5" />
              {post.engagement_score}
            </span>
          )}
        </div>

        <Link
          href={`/posts/${post.id}`}
          prefetch={false}
          className="flex items-center gap-1 text-xs font-medium text-[#3B82F6] hover:text-[#60A5FA] transition-colors"
        >
          <span>Inspect Opportunity</span>
          <ArrowRight className="w-3.5 h-3.5 transition-transform group-hover:translate-x-0.5" />
        </Link>
      </div>
    </article>
  );
}
