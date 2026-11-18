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
        setErrorMessage("Invalid expiration timestamp.");
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
        setErrorMessage("An unexpected network error occurred.");
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
      className="fixed inset-0 z-50 flex items-center justify-center p-3 sm:p-4 bg-[#090B10]/80 backdrop-blur-md overflow-hidden"
    >
      <div
        className="relative w-full max-w-2xl bg-[#0E131C] border border-white/[0.09] rounded-xl shadow-2xl overflow-hidden flex flex-col max-h-[90vh]"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between px-6 py-4 border-b border-white/[0.08] bg-[#111722]/50 shrink-0">
          <div className="space-y-0.5">
            <h2 id="edit-dialog-title" className="text-base font-semibold text-[#F1F5F9]">
              Edit Opportunity
            </h2>
            <p className="text-xs text-[#94A3B8]">
              Modifying text or tags invalidates prior embeddings and triggers re-routing.
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            disabled={isSubmitting}
            aria-label="Close dialog"
            className="p-1.5 rounded-md text-[#94A3B8] hover:text-[#F1F5F9] hover:bg-white/[0.05]"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="flex flex-col flex-1 min-h-0 overflow-hidden">
          <div className="flex-1 overflow-y-auto px-6 py-5 space-y-4">
            {errorMessage && (
              <div
                role="alert"
                className="p-3 rounded-lg bg-red-500/10 border border-red-500/20 text-red-300 text-xs flex items-start gap-2.5"
              >
                <AlertCircle className="w-4 h-4 shrink-0 text-red-400 mt-0.5" />
                <div className="flex-1">{errorMessage}</div>
              </div>
            )}

            {/* Post Type */}
            <div className="space-y-1.5">
              <label className="block text-xs font-medium text-[#94A3B8]">Category</label>
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
                {POST_TYPES.map((type) => (
                  <button
                    key={type.value}
                    type="button"
                    onClick={() => setPostType(type.value)}
                    className={cn(
                      "flex flex-col items-start p-2 rounded-lg border text-left text-xs transition-colors",
                      postType === type.value
                        ? "bg-blue-500/10 border-blue-500/30 text-[#F1F5F9]"
                        : "bg-white/[0.02] border-white/[0.07] text-[#94A3B8] hover:border-white/[0.14] hover:text-[#F1F5F9]"
                    )}
                  >
                    <span className="font-semibold">{type.label}</span>
                  </button>
                ))}
              </div>
            </div>

            {/* Title */}
            <div className="space-y-1.5">
              <div className="flex justify-between text-xs">
                <label htmlFor="edit-title" className="font-medium text-[#94A3B8]">
                  Headline Title
                </label>
                <span className="font-mono text-[11px] text-[#64748B]">{title.length}/500</span>
              </div>
              <input
                id="edit-title"
                type="text"
                required
                maxLength={500}
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                className="w-full px-3.5 py-2 rounded-lg bg-[#090B10] border border-white/[0.08] text-sm text-[#F1F5F9] focus:outline-none focus:border-[#3B82F6]"
              />
            </div>

            {/* Content */}
            <div className="space-y-1.5">
              <div className="flex justify-between text-xs">
                <label htmlFor="edit-content" className="font-medium text-[#94A3B8]">
                  Content Body
                </label>
                <span className="font-mono text-[11px] text-[#64748B]">{content.length}/50,000</span>
              </div>
              <textarea
                id="edit-content"
                required
                rows={5}
                maxLength={50000}
                value={content}
                onChange={(e) => setContent(e.target.value)}
                className="w-full px-3.5 py-2 rounded-lg bg-[#090B10] border border-white/[0.08] text-sm text-[#F1F5F9] focus:outline-none focus:border-[#3B82F6] resize-y"
              />
            </div>

            {/* Target Industries */}
            <div className="space-y-1.5">
              <label className="block text-xs font-medium text-[#94A3B8]">
                Target Industries
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
                  placeholder="e.g. fintech, logistics"
                  className="flex-1 px-3 py-1.5 rounded-md bg-[#090B10] border border-white/[0.08] text-xs text-[#F1F5F9] focus:outline-none focus:border-[#3B82F6]"
                />
                <button
                  type="button"
                  onClick={handleAddIndustry}
                  className="px-3 py-1.5 rounded-md bg-[#141A26] hover:bg-[#1C2434] border border-white/[0.08] text-xs text-[#F1F5F9] flex items-center gap-1 font-medium"
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
                      className="inline-flex items-center gap-1 px-2 py-0.5 rounded bg-blue-500/10 text-[#93C5FD] border border-blue-500/20 text-xs font-mono"
                    >
                      <span>{ind}</span>
                      <button
                        type="button"
                        onClick={() => handleRemoveIndustry(ind)}
                        className="hover:text-red-400"
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
              <label className="block text-xs font-medium text-[#94A3B8]">Relevance Tags</label>
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
                  placeholder="e.g. liquidity, cross-border"
                  className="flex-1 px-3 py-1.5 rounded-md bg-[#090B10] border border-white/[0.08] text-xs text-[#F1F5F9] focus:outline-none focus:border-[#3B82F6]"
                />
                <button
                  type="button"
                  onClick={handleAddTag}
                  className="px-3 py-1.5 rounded-md bg-[#141A26] hover:bg-[#1C2434] border border-white/[0.08] text-xs text-[#F1F5F9] flex items-center gap-1 font-medium"
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
                      className="inline-flex items-center gap-1 px-2 py-0.5 rounded bg-white/[0.03] text-[#94A3B8] border border-white/[0.07] text-xs font-mono"
                    >
                      <TagIcon className="w-3 h-3 text-[#475569]" />
                      <span>{t}</span>
                      <button
                        type="button"
                        onClick={() => handleRemoveTag(t)}
                        className="hover:text-red-400"
                      >
                        <X className="w-3 h-3" />
                      </button>
                    </span>
                  ))}
                </div>
              )}
            </div>

            {/* Expiration */}
            <div className="space-y-1.5">
              <label htmlFor="edit-expires-at" className="block text-xs font-medium text-[#94A3B8]">
                Expiration Date & Time (Optional UTC)
              </label>
              <input
                id="edit-expires-at"
                type="datetime-local"
                value={expiresAt}
                onChange={(e) => setExpiresAt(e.target.value)}
                className="px-3 py-1.5 rounded-lg bg-[#090B10] border border-white/[0.08] text-xs text-[#F1F5F9] focus:outline-none focus:border-[#3B82F6]"
              />
            </div>
          </div>

          <div className="flex items-center justify-end gap-3 px-6 py-3 border-t border-white/[0.08] bg-[#0E131C] shrink-0">
            <button
              type="button"
              onClick={onClose}
              disabled={isSubmitting}
              className="px-4 py-2 rounded-lg text-xs font-medium text-[#94A3B8] hover:text-[#F1F5F9] hover:bg-white/[0.04]"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={isSubmitting}
              className="flex items-center gap-2 px-5 py-2 rounded-lg bg-[#2563EB] hover:bg-[#1D4ED8] text-white text-xs font-semibold shadow-sm disabled:opacity-50"
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
