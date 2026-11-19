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
        "group relative p-5 sm:p-6 rounded-xl bg-white border border-[#E0E6DF] hover:border-[#B8D5C7] transition-all duration-150 flex flex-col gap-3.5 shadow-none",
        className
      )}
    >
      {/* Header: Author enterprise & meta */}
      <div className="flex flex-wrap items-center justify-between gap-2 text-xs">
        <div className="flex items-center gap-2 min-w-0">
          <div className="w-7 h-7 rounded-lg bg-[#E4EEE8] border border-[#B8D5C7] flex items-center justify-center text-[#183A2C] shrink-0">
            <Building className="w-3.5 h-3.5" />
          </div>
          <span className="font-semibold text-sm text-[#1B2520] truncate">
            {post.author.name}
          </span>
          <span className="text-[#87928A]">·</span>
          <span className="text-xs text-[#647169] truncate">{post.author.company}</span>
          <span
            className="flex items-center gap-1 text-[#183A2C] font-mono text-xs px-2 py-0.5 rounded-full bg-[#E4EEE8] border border-[#B8D5C7] shrink-0"
            title={`Verified Platform Trust Score: ${(post.author.trust_score * 100).toFixed(0)}%`}
          >
            <ShieldCheck className="w-3 h-3 text-[#183A2C]" />
            {(post.author.trust_score * 100).toFixed(0)}%
          </span>
        </div>

        <div className="flex items-center gap-2 text-[#647169] font-mono text-xs shrink-0">
          <span className="flex items-center gap-1">
            <Clock className="w-3 h-3 text-[#87928A]" />
            {formatRelativeTime(post.published_at)}
          </span>
          {isExpiringSoon && (
            <span className="px-2 py-0.5 rounded-md bg-[#FFFBEB] text-[#B45309] border border-[#FDE68A] text-xs font-medium">
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
            className="text-base sm:text-lg font-semibold text-[#1B2520] group-hover:text-[#244C3B] transition-colors line-clamp-2 leading-snug"
          >
            {post.title}
          </Link>
          <span
            className={cn(
              "text-xs uppercase font-mono font-semibold px-2.5 py-0.5 rounded-md border shrink-0",
              postTypeBadgeClass(post.post_type)
            )}
          >
            {formatPostType(post.post_type)}
          </span>
        </div>

        {/* Content Preview */}
        <p className="text-sm text-[#3E4A43] leading-relaxed line-clamp-3">
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
              className="text-xs font-mono px-2 py-0.5 rounded-md bg-[#EEF1ED] text-[#24493D] border border-[#E0E6DF]"
            >
              {ind}
            </span>
          ))}
          {post.tags?.map((t) => (
            <span
              key={`tag-${t}`}
              className="text-xs font-mono px-2 py-0.5 rounded-md bg-[#F8F9F6] text-[#647169] border border-[#E0E6DF] flex items-center gap-1"
            >
              <Tag className="w-2.5 h-2.5 text-[#87928A]" />
              {t}
            </span>
          ))}
        </div>
      )}

      {/* Footer: Metrics & Details Link */}
      <div className="flex items-center justify-between pt-3.5 border-t border-[#E0E6DF] text-xs text-[#647169]">
        <div className="flex items-center gap-4 font-mono text-xs">
          <span
            className="flex items-center gap-1 text-[#647169] hover:text-[#1B2520] transition-colors"
            title="Read Views"
          >
            <Eye className="w-3.5 h-3.5 text-[#87928A]" />
            {formatNumber(post.view_count)} views
          </span>
          <span
            className="flex items-center gap-1 text-[#647169] hover:text-[#1B2520] transition-colors"
            title="Discussion Comments"
          >
            <MessageSquare className="w-3.5 h-3.5 text-[#87928A]" />
            {formatNumber(post.comment_count)} discussions
          </span>
          {post.engagement_score > 0 && (
            <span
              className="flex items-center gap-1 text-[#1B5E20] font-semibold"
              title="Engagement Score"
            >
              <TrendingUp className="w-3.5 h-3.5" />
              Engagement: {post.engagement_score}
            </span>
          )}
        </div>

        <Link
          href={`/posts/${post.id}`}
          prefetch={false}
          className="flex items-center gap-1 text-xs font-semibold text-[#244C3B] group-hover:text-[#183A2C] transition-colors"
        >
          <span>Inspect Opportunity</span>
          <ArrowRight className="w-3.5 h-3.5 transition-transform group-hover:translate-x-0.5" />
        </Link>
      </div>
    </article>
  );
}
