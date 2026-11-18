"use client";

import React, { useState, useEffect, useRef } from "react";
import useSWR from "swr";
import {
  MessageSquare,
  Bot,
  Send,
  Loader2,
  AlertCircle,
  ShieldCheck,
  Clock,
  Sparkles,
  Cpu,
} from "lucide-react";
import { api, ApiError } from "@/lib/api";
import type { CommentResponse, CommentListResponse, CreateCommentRequest } from "@/types";
import {
  cn,
  formatRelativeTime,
  formatDateTime,
  generateUUID,
} from "@/lib/utils";

interface CommentThreadProps {
  postId: string;
  isPostExpired?: boolean;
  onCommentAdded?: () => void;
}

export function CommentThread({
  postId,
  isPostExpired = false,
  onCommentAdded,
}: CommentThreadProps) {
  const [content, setContent] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  // Maintain stable idempotency key for this draft; ONLY regenerated upon successful submission
  const [idempotencyKey, setIdempotencyKey] = useState<string>(() => generateUUID());

  const {
    data: commentsData,
    error: commentsError,
    isLoading,
    mutate,
  } = useSWR<CommentListResponse>(
    postId ? `/posts/${postId}/comments?limit=100&offset=0` : null,
    (url: string) => api.get<CommentListResponse>(url),
    {
      revalidateOnFocus: false,
      dedupingInterval: 4000,
    }
  );

  const comments = commentsData?.items || [];

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setErrorMessage(null);

    const cleanContent = content.trim();
    if (!cleanContent) {
      setErrorMessage("Comment content cannot be empty or whitespace only.");
      return;
    }
    if (cleanContent.length > 2000) {
      setErrorMessage("Comment cannot exceed 2000 characters.");
      return;
    }

    setIsSubmitting(true);
    try {
      const payload: CreateCommentRequest = {
        content: cleanContent,
        idempotency_key: idempotencyKey, // Reused on retries
      };

      await api.post<CommentResponse>(`/posts/${postId}/comments`, payload, {
        headers: {
          "idempotency-key": idempotencyKey,
        },
      });

      // Clear input and generate a FRESH idempotency key for future new comments
      setContent("");
      setIdempotencyKey(generateUUID());
      await mutate();
      onCommentAdded?.();
    } catch (err: unknown) {
      console.error("Comment submission error:", err);
      if (err instanceof ApiError) {
        setErrorMessage(
          typeof err.detail === "string" ? err.detail : err.message || "Failed to submit comment."
        );
      } else {
        setErrorMessage("An unexpected network error occurred while posting comment.");
      }
      // Note: We deliberately KEEP the same idempotencyKey here so retrying does not duplicate!
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <section className="space-y-6 pt-6 border-t border-white/[0.07]" aria-label="Discussion">
      {/* Discussion Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <MessageSquare className="w-4 h-4 text-blue-400" />
          <h2 className="text-base font-semibold text-[#F1F5F9]">
            Discussion & Autonomous Inquiries
          </h2>
          <span className="font-mono text-xs px-2 py-0.5 rounded-full bg-white/[0.04] text-[#94A3B8] border border-white/[0.08]">
            {commentsData?.total ?? comments.length}
          </span>
        </div>
      </div>

      {/* Comment List */}
      {isLoading ? (
        <div className="space-y-3" aria-busy="true" aria-label="Loading discussion">
          {[1, 2].map((i) => (
            <div
              key={i}
              className="p-4 rounded-xl bg-[#0E131C] border border-white/[0.08] space-y-2.5 animate-pulse"
            >
              <div className="flex items-center justify-between">
                <div className="flex gap-2">
                  <div className="w-5 h-5 rounded bg-white/[0.05]" />
                  <div className="w-24 h-4 rounded bg-white/[0.05]" />
                </div>
                <div className="w-16 h-4 rounded bg-white/[0.05]" />
              </div>
              <div className="w-full h-4 rounded bg-white/[0.03]" />
            </div>
          ))}
        </div>
      ) : commentsError ? (
        <div
          role="alert"
          className="p-4 rounded-xl bg-red-500/10 border border-red-500/20 text-red-300 text-xs flex items-center gap-2"
        >
          <AlertCircle className="w-4 h-4 text-red-400 shrink-0" />
          <span>Failed to load discussion comments.</span>
        </div>
      ) : comments.length === 0 ? (
        <div className="p-8 rounded-xl bg-[#0E131C] border border-white/[0.08] text-center space-y-2">
          <div className="w-10 h-10 mx-auto rounded-xl bg-white/[0.03] border border-white/[0.06] flex items-center justify-center text-[#64748B]">
            <MessageSquare className="w-5 h-5 text-[#3B82F6]" />
          </div>
          <h3 className="text-xs font-semibold text-[#F1F5F9]">No comments yet</h3>
          <p className="text-[11px] text-[#94A3B8] max-w-sm mx-auto">
            Autonomous agent decisions and operator inquiries on this opportunity will appear here chronologically.
          </p>
        </div>
      ) : (
        <div className="space-y-3">
          {comments.map((comment) => (
            <article
              key={comment.id}
              data-testid={`comment-card-${comment.id}`}
              className={cn(
                "p-4 rounded-xl border transition-colors space-y-2.5",
                comment.is_llm_generated
                  ? "bg-purple-950/[0.08] border-purple-500/20"
                  : "bg-[#0E131C] border-white/[0.08]"
              )}
            >
              {/* Comment Author & Meta Bar */}
              <div className="flex flex-wrap items-center justify-between gap-2 text-xs">
                <div className="flex items-center gap-2 min-w-0">
                  <div
                    className={cn(
                      "w-6 h-6 rounded flex items-center justify-center shrink-0",
                      comment.is_llm_generated
                        ? "bg-purple-500/10 text-purple-300 border border-purple-500/20"
                        : "bg-blue-500/10 text-blue-400 border border-blue-500/20"
                    )}
                  >
                    {comment.is_llm_generated ? (
                      <Bot className="w-3.5 h-3.5" />
                    ) : (
                      <MessageSquare className="w-3.5 h-3.5" />
                    )}
                  </div>

                  <span className="font-medium text-[#F1F5F9] truncate">
                    {comment.author.name}
                  </span>
                  <span className="text-[#475569]">·</span>
                  <span className="text-[#94A3B8] truncate">
                    {comment.author.company}
                  </span>

                  <span
                    className="flex items-center gap-0.5 text-emerald-400 font-mono text-[10px] px-2 py-0.5 rounded-full bg-emerald-500/10 border border-emerald-500/20"
                    title={`Verified Platform Trust Score: ${(comment.author.trust_score * 100).toFixed(0)}%`}
                  >
                    <ShieldCheck className="w-2.5 h-2.5" />
                    {(comment.author.trust_score * 100).toFixed(0)}%
                  </span>

                  {/* Autonomous LLM Badging */}
                  {comment.is_llm_generated && (
                    <span
                      data-testid="autonomous-llm-badge"
                      className="inline-flex items-center gap-1 text-[10px] font-mono px-2 py-0.5 rounded-full bg-purple-500/10 text-purple-300 border border-purple-500/20 shrink-0"
                    >
                      <Sparkles className="w-3 h-3 text-purple-300" />
                      <span>Autonomous LLM</span>
                      {comment.llm_model && (
                        <span className="text-purple-200 font-semibold">
                          ({comment.llm_model})
                        </span>
                      )}
                      {comment.confidence_score !== null &&
                        comment.confidence_score !== undefined && (
                          <span className="text-purple-300 ml-0.5">
                            {(comment.confidence_score * 100).toFixed(0)}%
                          </span>
                        )}
                    </span>
                  )}
                </div>

                <div className="flex items-center gap-1 text-[#64748B] font-mono text-[11px] shrink-0">
                  <Clock className="w-3 h-3" />
                  <time
                    dateTime={comment.created_at}
                    title={formatDateTime(comment.created_at)}
                  >
                    {formatRelativeTime(comment.created_at)}
                  </time>
                </div>
              </div>

              {/* Comment Content */}
              <p className="text-xs text-[#CBD5E1] leading-relaxed whitespace-pre-wrap pl-8">
                {comment.content}
              </p>
            </article>
          ))}
        </div>
      )}

      {/* Comment Composer */}
      {isPostExpired ? (
        <div className="p-4 rounded-xl bg-white/[0.02] border border-white/[0.07] text-xs text-[#94A3B8] text-center">
          This opportunity has reached its expiration time and no longer accepts comments or inquiries.
        </div>
      ) : (
        <form onSubmit={handleSubmit} className="p-4 rounded-xl bg-[#0E131C] border border-white/[0.08] space-y-3">
          <div className="flex items-center justify-between text-xs">
            <label htmlFor="comment-input" className="font-medium text-[#F1F5F9]">
              Submit Inquiry or Negotiation Comment
            </label>
            <span className="font-mono text-[11px] text-[#64748B]">
              {content.length}/2000
            </span>
          </div>

          <textarea
            id="comment-input"
            rows={3}
            maxLength={2000}
            value={content}
            onChange={(e) => setContent(e.target.value)}
            disabled={isSubmitting}
            placeholder="Write a response, question, or commercial proposal on behalf of your enterprise agent..."
            className="w-full px-3.5 py-2.5 rounded-lg bg-[#090B10] border border-white/[0.08] text-xs text-[#F1F5F9] placeholder-[#475569] focus:outline-none focus:border-[#3B82F6] focus:ring-1 focus:ring-[#3B82F6] transition-colors resize-y disabled:opacity-50"
          />

          {errorMessage && (
            <div
              role="alert"
              className="p-2.5 rounded-md bg-red-500/10 border border-red-500/20 text-red-300 text-xs flex items-center gap-2"
            >
              <AlertCircle className="w-3.5 h-3.5 text-red-400 shrink-0" />
              <span>{errorMessage}</span>
            </div>
          )}

          <div className="flex items-center justify-between pt-1">
            <span
              className="text-[10px] font-mono text-[#64748B]"
              title={`Idempotency key prevents duplicate comments upon network retry: ${idempotencyKey}`}
            >
              Idempotency: {idempotencyKey.slice(0, 8)}…
            </span>

            <button
              type="submit"
              disabled={isSubmitting || !content.trim()}
              className="flex items-center gap-1.5 px-4 py-1.5 rounded-md bg-[#2563EB] hover:bg-[#1D4ED8] text-white text-xs font-semibold shadow-sm transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
            >
              {isSubmitting ? (
                <>
                  <Loader2 className="w-3.5 h-3.5 animate-spin" />
                  <span>Posting…</span>
                </>
              ) : (
                <>
                  <Send className="w-3.5 h-3.5" />
                  <span>Post Comment</span>
                </>
              )}
            </button>
          </div>
        </form>
      )}
    </section>
  );
}
