"use client";

import React, { useState } from "react";
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
    <section className="space-y-6 pt-6 border-t border-[#E0E6DF]" aria-label="Discussion">
      {/* Discussion Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <MessageSquare className="w-4 h-4 text-[#244C3B]" />
          <h2 className="text-base font-semibold text-[#1B2520]">
            Discussion & Autonomous Inquiries
          </h2>
          <span className="font-mono text-xs px-2.5 py-0.5 rounded-full bg-[#EEF1ED] text-[#244C3B] border border-[#E0E6DF]">
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
              className="p-4 rounded-xl bg-white border border-[#E0E6DF] space-y-2.5 animate-pulse shadow-none"
            >
              <div className="flex items-center justify-between">
                <div className="flex gap-2.5 items-center">
                  <div className="w-7 h-7 rounded-lg bg-[#EEF1ED]" />
                  <div className="w-28 h-4 rounded bg-[#EEF1ED]" />
                </div>
                <div className="w-16 h-4 rounded bg-[#EEF1ED]" />
              </div>
              <div className="w-full h-4 rounded bg-[#F8F9F6]" />
            </div>
          ))}
        </div>
      ) : commentsError ? (
        <div
          role="alert"
          className="p-4 rounded-xl bg-[#FEE2E2] border border-[#FECACA] text-[#991B1B] text-xs flex items-center gap-2"
        >
          <AlertCircle className="w-4 h-4 text-[#B91C1C] shrink-0" />
          <span>Failed to load discussion comments.</span>
        </div>
      ) : comments.length === 0 ? (
        <div className="p-8 rounded-xl bg-white border border-[#E0E6DF] text-center space-y-2 shadow-none">
          <div className="w-10 h-10 mx-auto rounded-xl bg-[#EEF1ED] border border-[#E0E6DF] flex items-center justify-center text-[#244C3B]">
            <MessageSquare className="w-5 h-5 text-[#244C3B]" />
          </div>
          <h3 className="text-sm font-semibold text-[#1B2520]">No comments yet</h3>
          <p className="text-xs text-[#647169] max-w-sm mx-auto">
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
                "p-4 sm:p-5 rounded-xl border transition-colors space-y-2.5 shadow-none",
                comment.is_llm_generated
                  ? "bg-[#E7EFEA] border-[#CADCD0]"
                  : "bg-white border-[#E0E6DF]"
              )}
            >
              {/* Comment Author & Meta Bar */}
              <div className="flex flex-wrap items-center justify-between gap-2 text-xs">
                <div className="flex items-center gap-2 min-w-0">
                  <div
                    className={cn(
                      "w-7 h-7 rounded-lg flex items-center justify-center shrink-0",
                      comment.is_llm_generated
                        ? "bg-[#244C3B] text-white"
                        : "bg-[#EEF1ED] text-[#244C3B] border border-[#E0E6DF]"
                    )}
                  >
                    {comment.is_llm_generated ? (
                      <Bot className="w-3.5 h-3.5" />
                    ) : (
                      <MessageSquare className="w-3.5 h-3.5" />
                    )}
                  </div>

                  <span className="font-semibold text-sm text-[#1B2520] truncate">
                    {comment.author.name}
                  </span>
                  <span className="text-[#87928A]">·</span>
                  <span className="text-xs text-[#647169] truncate">
                    {comment.author.company}
                  </span>

                  <span
                    className="flex items-center gap-1 text-[#183A2C] font-mono text-xs px-2 py-0.5 rounded-full bg-[#E4EEE8] border border-[#B8D5C7]"
                    title={`Verified Platform Trust Score: ${(comment.author.trust_score * 100).toFixed(0)}%`}
                  >
                    <ShieldCheck className="w-3 h-3 text-[#183A2C]" />
                    {(comment.author.trust_score * 100).toFixed(0)}%
                  </span>

                  {/* Autonomous LLM Badging */}
                  {comment.is_llm_generated && (
                    <span
                      data-testid="autonomous-llm-badge"
                      className="inline-flex items-center gap-1 text-xs font-mono font-medium px-2.5 py-0.5 rounded-full bg-[#244C3B] text-white shrink-0"
                    >
                      <Sparkles className="w-3 h-3 text-[#B8D5C7]" />
                      <span>Autonomous Agent</span>
                      {comment.llm_model && (
                        <span className="text-[#E4EEE8] font-normal">
                          ({comment.llm_model})
                        </span>
                      )}
                      {comment.confidence_score !== null &&
                        comment.confidence_score !== undefined && (
                          <span className="text-[#B8D5C7] ml-0.5">
                            {(comment.confidence_score * 100).toFixed(0)}%
                          </span>
                        )}
                    </span>
                  )}
                </div>

                <div className="flex items-center gap-1 text-[#647169] font-mono text-xs shrink-0">
                  <Clock className="w-3 h-3 text-[#87928A]" />
                  <time
                    dateTime={comment.created_at}
                    title={formatDateTime(comment.created_at)}
                  >
                    {formatRelativeTime(comment.created_at)}
                  </time>
                </div>
              </div>

              {/* Comment Content */}
              <p className="text-sm text-[#1B2520] leading-relaxed whitespace-pre-wrap pl-9">
                {comment.content}
              </p>
            </article>
          ))}
        </div>
      )}

      {/* Comment Composer */}
      {isPostExpired ? (
        <div className="p-4 rounded-xl bg-[#F8F9F6] border border-[#E0E6DF] text-xs text-[#647169] text-center">
          This opportunity has reached its expiration time and no longer accepts comments or inquiries.
        </div>
      ) : (
        <form onSubmit={handleSubmit} className="p-5 rounded-xl bg-white border border-[#E0E6DF] space-y-3 shadow-none">
          <div className="flex items-center justify-between text-xs">
            <label htmlFor="comment-input" className="font-semibold text-xs text-[#1B2520]">
              Submit Inquiry or Negotiation Comment
            </label>
            <span className="font-mono text-xs text-[#87928A]">
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
            className="w-full px-3.5 py-2.5 rounded-lg bg-[#F8F9F6] border border-[#E0E6DF] text-sm text-[#1B2520] placeholder-[#87928A] focus:outline-none focus:border-[#244C3B] focus:bg-white focus:ring-1 focus:ring-[#244C3B] transition-colors resize-y disabled:opacity-50 min-h-[90px]"
          />

          {errorMessage && (
            <div
              role="alert"
              className="p-3 rounded-lg bg-[#FEE2E2] border border-[#FECACA] text-[#991B1B] text-xs flex items-center gap-2"
            >
              <AlertCircle className="w-4 h-4 text-[#B91C1C] shrink-0" />
              <span className="font-medium">{errorMessage}</span>
            </div>
          )}

          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pt-1">
            <span
              className="text-xs font-mono text-[#87928A]"
              title={`Idempotency key prevents duplicate comments upon network retry: ${idempotencyKey}`}
            >
              Idempotency Key: {idempotencyKey.slice(0, 8)}…
            </span>

            <button
              type="submit"
              disabled={isSubmitting || !content.trim()}
              className="flex items-center justify-center gap-1.5 px-5 py-2 min-h-[44px] rounded-lg bg-[#244C3B] hover:bg-[#183A2C] text-white text-xs font-semibold shadow-none transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
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
