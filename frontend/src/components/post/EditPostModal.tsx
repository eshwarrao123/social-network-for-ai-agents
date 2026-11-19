"use client";

import React, { useState, useEffect } from "react";
import { X, Loader2, Save, AlertCircle, Plus, Tag as TagIcon } from "lucide-react";
import { api, ApiError } from "@/lib/api";
import type { PostResponse, PostType, PostUpdateRequest } from "@/types";
import { cn } from "@/lib/utils";

interface EditPostModalProps {
  post: PostResponse;
  isOpen: boolean;
  onClose: () => void;
  onUpdated: (updatedPost: PostResponse) => void;
}

const POST_TYPES: { label: string; value: PostType; desc: string }[] = [
  { label: "Announcement", value: "announcement", desc: "Corporate bulletin" },
  { label: "Market Update", value: "market_update", desc: "Market or pricing shift" },
  { label: "Collaboration", value: "collaboration", desc: "Joint venture or partnership" },
  { label: "Promotion", value: "promotion", desc: "Commercial offering" },
];

export function EditPostModal({
  post,
  isOpen,
  onClose,
  onUpdated,
}: EditPostModalProps) {
  const [title, setTitle] = useState(post.title);
  const [content, setContent] = useState(post.content);
  const [postType, setPostType] = useState<PostType>(post.post_type);
  const [targetIndustries, setTargetIndustries] = useState<string[]>(post.target_industries || []);
  const [industryInput, setIndustryInput] = useState("");
  const [tags, setTags] = useState<string[]>(post.tags || []);
  const [tagInput, setTagInput] = useState("");
  const [expiresAt, setExpiresAt] = useState(
    post.expires_at ? new Date(post.expires_at).toISOString().slice(0, 16) : ""
  );

  const [isSubmitting, setIsSubmitting] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  useEffect(() => {
    if (isOpen) {
      setTitle(post.title);
      setContent(post.content);
      setPostType(post.post_type);
      setTargetIndustries(post.target_industries || []);
      setIndustryInput("");
      setTags(post.tags || []);
      setTagInput("");
      setExpiresAt(
        post.expires_at ? new Date(post.expires_at).toISOString().slice(0, 16) : ""
      );
      setErrorMessage(null);
      setIsSubmitting(false);
    }
  }, [isOpen, post]);

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape" && isOpen && !isSubmitting) {
        onClose();
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [isOpen, isSubmitting, onClose]);

  if (!isOpen) return null;

  const handleAddIndustry = () => {
    const clean = industryInput.trim().toLowerCase();
    if (clean && !targetIndustries.includes(clean) && targetIndustries.length < 50) {
      setTargetIndustries([...targetIndustries, clean]);
      setIndustryInput("");
    }
  };

  const handleRemoveIndustry = (item: string) => {
    setTargetIndustries(targetIndustries.filter((i) => i !== item));
  };

  const handleAddTag = () => {
    const clean = tagInput.trim().toLowerCase();
    if (clean && !tags.includes(clean) && tags.length < 50) {
      setTags([...tags, clean]);
      setTagInput("");
    }
  };

  const handleRemoveTag = (item: string) => {
    setTags(tags.filter((t) => t !== item));
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setErrorMessage(null);

    const cleanTitle = title.trim();
    const cleanContent = content.trim();

    if (!cleanTitle) {
      setErrorMessage("Title cannot be empty.");
      return;
    }
    if (cleanTitle.length > 500) {
      setErrorMessage("Title cannot exceed 500 characters.");
      return;
    }
    if (!cleanContent) {
      setErrorMessage("Content cannot be empty.");
      return;
    }
    if (cleanContent.length > 50000) {
      setErrorMessage("Content cannot exceed 50,000 characters.");
      return;
    }

    let parsedExpiresAt: string | null = null;
    if (expiresAt) {
      const expDate = new Date(expiresAt);
      if (isNaN(expDate.getTime())) {
        setErrorMessage("Invalid expiration timestamp format.");
        return;
      }
      if (expDate.getTime() <= Date.now()) {
        setErrorMessage("Expiration timestamp must be in the future.");
        return;
      }
      parsedExpiresAt = expDate.toISOString();
    }

    const payload: PostUpdateRequest = {
      title: cleanTitle,
      content: cleanContent,
      post_type: postType,
      target_industries: targetIndustries,
      tags: tags,
      expires_at: parsedExpiresAt,
    };

    setIsSubmitting(true);
    try {
      const updated = await api.patch<PostResponse>(`/posts/${post.id}`, payload);
      onUpdated(updated);
      onClose();
    } catch (err: unknown) {
      console.error("Update error:", err);
      if (err instanceof ApiError) {
        setErrorMessage(
          typeof err.detail === "string" ? err.detail : err.message || "Failed to update opportunity."
        );
      } else {
        setErrorMessage("An unexpected network error occurred while updating.");
      }
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="edit-dialog-title"
      className="fixed inset-0 z-50 flex items-center justify-center p-3 sm:p-4 bg-[#18392F]/40 backdrop-blur-sm overflow-hidden"
    >
      <div
        className="relative w-full max-w-2xl bg-white border border-[#E0E6DF] rounded-xl shadow-xl overflow-hidden flex flex-col max-h-[90vh]"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-[#E0E6DF] bg-[#F8F9F6] shrink-0">
          <div className="space-y-0.5">
            <h2
              id="edit-dialog-title"
              className="text-base sm:text-lg font-semibold text-[#1B2520]"
            >
              Edit Opportunity
            </h2>
            <p className="text-xs text-[#647169]">
              Modify opportunity details, target industries, or taxonomy tags.
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            disabled={isSubmitting}
            aria-label="Close dialog"
            className="p-2 min-h-[44px] min-w-[44px] flex items-center justify-center rounded-lg text-[#647169] hover:text-[#1B2520] hover:bg-[#EEF1ED] transition-colors disabled:opacity-50"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Scrollable Form Body */}
        <form onSubmit={handleSubmit} className="flex flex-col flex-1 min-h-0 overflow-hidden">
          <div className="flex-1 overflow-y-auto px-6 py-5 space-y-4">
            {errorMessage && (
              <div
                role="alert"
                className="p-3.5 rounded-lg bg-[#FEE2E2] border border-[#FECACA] text-[#991B1B] text-xs flex items-start gap-2.5"
              >
                <AlertCircle className="w-4 h-4 shrink-0 text-[#B91C1C] mt-0.5" />
                <div className="flex-1 font-medium">{errorMessage}</div>
              </div>
            )}

            {/* Post Type Selector */}
            <div className="space-y-1.5">
              <label className="block text-xs font-semibold text-[#1B2520]">
                Opportunity Category
              </label>
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
                {POST_TYPES.map((type) => (
                  <button
                    key={type.value}
                    type="button"
                    onClick={() => setPostType(type.value)}
                    className={cn(
                      "flex flex-col items-start p-2.5 rounded-lg border text-left transition-all min-h-[56px]",
                      postType === type.value
                        ? "bg-[#E4EEE8] border-[#244C3B] text-[#183A2C] shadow-xs"
                        : "bg-[#F8F9F6] border-[#E0E6DF] text-[#647169] hover:border-[#CADCD0] hover:bg-white"
                    )}
                  >
                    <span className="text-xs font-semibold text-[#1B2520]">{type.label}</span>
                    <span className="text-xs text-[#647169] line-clamp-1 mt-0.5">
                      {type.desc}
                    </span>
                  </button>
                ))}
              </div>
            </div>

            {/* Title Input */}
            <div className="space-y-1.5">
              <div className="flex items-center justify-between text-xs">
                <label htmlFor="edit-title" className="font-semibold text-[#1B2520]">
                  Headline Title <span className="text-[#B91C1C]">*</span>
                </label>
                <span className="font-mono text-xs text-[#87928A]">
                  {title.length}/500
                </span>
              </div>
              <input
                id="edit-title"
                type="text"
                required
                maxLength={500}
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                className="w-full px-3.5 py-2.5 min-h-[44px] rounded-lg bg-white border border-[#E0E6DF] text-sm text-[#1B2520] placeholder-[#87928A] focus:outline-none focus:border-[#244C3B] focus:ring-1 focus:ring-[#244C3B] transition-colors"
              />
            </div>

            {/* Content Body Input */}
            <div className="space-y-1.5">
              <div className="flex items-center justify-between text-xs">
                <label htmlFor="edit-content" className="font-semibold text-[#1B2520]">
                  Opportunity Content Body <span className="text-[#B91C1C]">*</span>
                </label>
                <span className="font-mono text-xs text-[#87928A]">
                  {content.length}/50,000
                </span>
              </div>
              <textarea
                id="edit-content"
                required
                rows={4}
                maxLength={50000}
                value={content}
                onChange={(e) => setContent(e.target.value)}
                className="w-full px-3.5 py-2.5 rounded-lg bg-white border border-[#E0E6DF] text-sm text-[#1B2520] placeholder-[#87928A] focus:outline-none focus:border-[#244C3B] focus:ring-1 focus:ring-[#244C3B] transition-colors resize-y min-h-[120px]"
              />
            </div>

            {/* Target Industries */}
            <div className="space-y-1.5">
              <label className="block text-xs font-semibold text-[#1B2520]">
                Target Industries (Used for Relevance Routing)
              </label>
              <div className="flex gap-2">
                <input
                  type="text"
                  value={industryInput}
                  onChange={(e) => setIndustryInput(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") {
                      e.preventDefault();
                      handleAddIndustry();
                    }
                  }}
                  placeholder="e.g. fintech, logistics, energy"
                  className="flex-1 px-3.5 py-2 min-h-[44px] rounded-lg bg-white border border-[#E0E6DF] text-sm text-[#1B2520] placeholder-[#87928A] focus:outline-none focus:border-[#244C3B]"
                />
                <button
                  type="button"
                  onClick={handleAddIndustry}
                  className="px-4 py-2 min-h-[44px] rounded-lg bg-[#F8F9F6] hover:bg-[#EEF1ED] border border-[#E0E6DF] text-xs text-[#1B2520] flex items-center gap-1 font-semibold transition-colors"
                >
                  <Plus className="w-3.5 h-3.5" />
                  <span>Add</span>
                </button>
              </div>
              {targetIndustries.length > 0 && (
                <div className="flex flex-wrap gap-1.5 pt-1">
                  {targetIndustries.map((ind) => (
                    <span
                      key={ind}
                      className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-[#EEF1ED] text-[#24493D] border border-[#E0E6DF] text-xs font-mono"
                    >
                      <span>{ind}</span>
                      <button
                        type="button"
                        onClick={() => handleRemoveIndustry(ind)}
                        aria-label={`Remove industry ${ind}`}
                        className="min-w-[20px] min-h-[20px] flex items-center justify-center rounded hover:bg-[#E0E6DF] text-[#647169] hover:text-[#B91C1C]"
                      >
                        <X className="w-3 h-3" />
                      </button>
                    </span>
                  ))}
                </div>
              )}
            </div>

            {/* Relevance Tags */}
            <div className="space-y-1.5">
              <label className="block text-xs font-semibold text-[#1B2520]">
                Relevance Tags
              </label>
              <div className="flex gap-2">
                <input
                  type="text"
                  value={tagInput}
                  onChange={(e) => setTagInput(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") {
                      e.preventDefault();
                      handleAddTag();
                    }
                  }}
                  placeholder="e.g. liquidity, cross-border, compliance"
                  className="flex-1 px-3.5 py-2 min-h-[44px] rounded-lg bg-white border border-[#E0E6DF] text-sm text-[#1B2520] placeholder-[#87928A] focus:outline-none focus:border-[#244C3B]"
                />
                <button
                  type="button"
                  onClick={handleAddTag}
                  className="px-4 py-2 min-h-[44px] rounded-lg bg-[#F8F9F6] hover:bg-[#EEF1ED] border border-[#E0E6DF] text-xs text-[#1B2520] flex items-center gap-1 font-semibold transition-colors"
                >
                  <Plus className="w-3.5 h-3.5" />
                  <span>Add</span>
                </button>
              </div>
              {tags.length > 0 && (
                <div className="flex flex-wrap gap-1.5 pt-1">
                  {tags.map((t) => (
                    <span
                      key={t}
                      className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-[#F8F9F6] text-[#647169] border border-[#E0E6DF] text-xs font-mono"
                    >
                      <TagIcon className="w-3 h-3 text-[#87928A]" />
                      <span>{t}</span>
                      <button
                        type="button"
                        onClick={() => handleRemoveTag(t)}
                        aria-label={`Remove tag ${t}`}
                        className="min-w-[20px] min-h-[20px] flex items-center justify-center rounded hover:bg-[#E0E6DF] text-[#647169] hover:text-[#B91C1C]"
                      >
                        <X className="w-3 h-3" />
                      </button>
                    </span>
                  ))}
                </div>
              )}
            </div>

            {/* Expiration (Optional) */}
            <div className="space-y-1.5">
              <label htmlFor="edit-expires-at" className="block text-xs font-semibold text-[#1B2520]">
                Expiration Date & Time (Optional UTC)
              </label>
              <input
                id="edit-expires-at"
                type="datetime-local"
                value={expiresAt}
                onChange={(e) => setExpiresAt(e.target.value)}
                className="px-3.5 py-2 min-h-[44px] rounded-lg bg-white border border-[#E0E6DF] text-xs text-[#1B2520] focus:outline-none focus:border-[#244C3B]"
              />
              <p className="text-xs text-[#647169]">
                Expired opportunities are automatically omitted from discovery feeds and reject new autonomous comments.
              </p>
            </div>
          </div>

          {/* Sticky Footer Actions */}
          <div className="flex items-center justify-end gap-3 px-6 py-3.5 border-t border-[#E0E6DF] bg-[#F8F9F6] shrink-0">
            <button
              type="button"
              onClick={onClose}
              disabled={isSubmitting}
              className="px-4 py-2 min-h-[44px] rounded-lg text-xs font-medium text-[#647169] hover:text-[#1B2520] hover:bg-[#EEF1ED] transition-colors disabled:opacity-50"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={isSubmitting}
              className="flex items-center gap-2 px-5 py-2 min-h-[44px] rounded-lg bg-[#244C3B] hover:bg-[#183A2C] text-white text-xs font-semibold shadow-none transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {isSubmitting ? (
                <>
                  <Loader2 className="w-3.5 h-3.5 animate-spin" />
                  <span>Saving…</span>
                </>
              ) : (
                <>
                  <Save className="w-3.5 h-3.5" />
                  <span>Save Changes</span>
                </>
              )}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
