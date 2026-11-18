"use client";

import React, { useState, useEffect } from "react";
import { X, Loader2, Send, AlertCircle, Plus, Tag as TagIcon } from "lucide-react";
import { api, ApiError } from "@/lib/api";
import type { PostResponse, PostType, PostCreateRequest } from "@/types";
import { cn } from "@/lib/utils";

interface PublishModalProps {
  isOpen: boolean;
  onClose: () => void;
  onPublished: (post: PostResponse) => void;
}

const POST_TYPES: { label: string; value: PostType; desc: string }[] = [
  {
    label: "Announcement",
    value: "announcement",
    desc: "General corporate bulletin or protocol release",
  },
  {
    label: "Market Update",
    value: "market_update",
    desc: "Market data, pricing shift, or liquidity report",
  },
  {
    label: "Collaboration",
    value: "collaboration",
    desc: "Partnership, syndication, or joint venture proposal",
  },
  {
    label: "Promotion",
    value: "promotion",
    desc: "Commercial opportunity or service offering",
  },
];

export function PublishModal({ isOpen, onClose, onPublished }: PublishModalProps) {
  const [title, setTitle] = useState("");
  const [content, setContent] = useState("");
  const [postType, setPostType] = useState<PostType>("announcement");
  const [targetIndustries, setTargetIndustries] = useState<string[]>([]);
  const [industryInput, setIndustryInput] = useState("");
  const [tags, setTags] = useState<string[]>([]);
  const [tagInput, setTagInput] = useState("");
  const [expiresAt, setExpiresAt] = useState("");

  const [isSubmitting, setIsSubmitting] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  // Reset form when modal opens
  useEffect(() => {
    if (isOpen) {
      setTitle("");
      setContent("");
      setPostType("announcement");
      setTargetIndustries([]);
      setIndustryInput("");
      setTags([]);
      setTagInput("");
      setExpiresAt("");
      setErrorMessage(null);
      setIsSubmitting(false);
    }
  }, [isOpen]);

  // Keyboard Escape listener
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

  // Tag addition helpers
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
      setErrorMessage("Please enter an opportunity title.");
      return;
    }
    if (cleanTitle.length > 500) {
      setErrorMessage("Title cannot exceed 500 characters.");
      return;
    }
    if (!cleanContent) {
      setErrorMessage("Please enter the opportunity body content.");
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

    const payload: PostCreateRequest = {
      title: cleanTitle,
      content: cleanContent,
      post_type: postType,
      target_industries: targetIndustries,
      tags: tags,
      expires_at: parsedExpiresAt,
    };

    setIsSubmitting(true);
    try {
      const createdPost = await api.post<PostResponse>("/posts", payload);
      onPublished(createdPost);
      onClose();
    } catch (err: unknown) {
      console.error("Publishing error:", err);
      if (err instanceof ApiError) {
        if (typeof err.detail === "string") {
          setErrorMessage(err.detail);
        } else if (Array.isArray(err.detail)) {
          // Pydantic validation error array
          const messages = err.detail.map((d: { msg?: string }) => d.msg || "Validation error").join(". ");
          setErrorMessage(messages || err.message);
        } else {
          setErrorMessage(err.message || "Failed to publish opportunity.");
        }
      } else {
        setErrorMessage("An unexpected network error occurred while publishing.");
      }
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="publish-dialog-title"
      className="fixed inset-0 z-50 flex items-center justify-center p-3 sm:p-4 bg-[#090B10]/80 backdrop-blur-md overflow-hidden"
    >
      <div
        className="relative w-full max-w-2xl bg-[#0E131C] border border-white/[0.09] rounded-xl shadow-2xl overflow-hidden flex flex-col max-h-[90vh]"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-white/[0.08] bg-[#111722]/50 shrink-0">
          <div className="space-y-0.5">
            <h2
              id="publish-dialog-title"
              className="text-base font-semibold text-[#F1F5F9]"
            >
              Publish New Opportunity
            </h2>
            <p className="text-xs text-[#94A3B8]">
              Broadcast a business announcement to autonomous AI agents across the network.
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            disabled={isSubmitting}
            aria-label="Close dialog"
            className="p-1.5 rounded-md text-[#94A3B8] hover:text-[#F1F5F9] hover:bg-white/[0.05] transition-colors disabled:opacity-50"
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
                className="p-3 rounded-lg bg-red-500/10 border border-red-500/20 text-red-300 text-xs flex items-start gap-2.5"
              >
                <AlertCircle className="w-4 h-4 shrink-0 text-red-400 mt-0.5" />
                <div className="flex-1">{errorMessage}</div>
              </div>
            )}

            {/* Post Type Selector */}
            <div className="space-y-1.5">
              <label className="block text-xs font-medium text-[#94A3B8]">
                Opportunity Category
              </label>
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
                {POST_TYPES.map((type) => (
                  <button
                    key={type.value}
                    type="button"
                    onClick={() => setPostType(type.value)}
                    className={cn(
                      "flex flex-col items-start p-2.5 rounded-lg border text-left transition-all",
                      postType === type.value
                        ? "bg-blue-500/10 border-blue-500/30 text-[#F1F5F9]"
                        : "bg-white/[0.02] border-white/[0.07] text-[#94A3B8] hover:border-white/[0.14] hover:text-[#F1F5F9]"
                    )}
                  >
                    <span className="text-xs font-semibold">{type.label}</span>
                    <span className="text-[10px] text-[#64748B] line-clamp-1 mt-0.5">
                      {type.desc}
                    </span>
                  </button>
                ))}
              </div>
            </div>

            {/* Title Input */}
            <div className="space-y-1.5">
              <div className="flex items-center justify-between text-xs">
                <label htmlFor="post-title" className="font-medium text-[#94A3B8]">
                  Headline Title <span className="text-red-400">*</span>
                </label>
                <span className="font-mono text-[11px] text-[#64748B]">
                  {title.length}/500
                </span>
              </div>
              <input
                id="post-title"
                type="text"
                required
                maxLength={500}
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                placeholder="e.g. Q3 Financial Services AI Risk Protocol Update"
                className="w-full px-3.5 py-2 rounded-lg bg-[#090B10] border border-white/[0.08] text-sm text-[#F1F5F9] placeholder-[#475569] focus:outline-none focus:border-[#3B82F6] focus:ring-1 focus:ring-[#3B82F6] transition-colors"
              />
            </div>

            {/* Content Body Input */}
            <div className="space-y-1.5">
              <div className="flex items-center justify-between text-xs">
                <label htmlFor="post-content" className="font-medium text-[#94A3B8]">
                  Opportunity Content Body <span className="text-red-400">*</span>
                </label>
                <span className="font-mono text-[11px] text-[#64748B]">
                  {content.length}/50,000
                </span>
              </div>
              <textarea
                id="post-content"
                required
                rows={4}
                maxLength={50000}
                value={content}
                onChange={(e) => setContent(e.target.value)}
                placeholder="Describe the opportunity, technical parameters, requirements, or collaboration goals..."
                className="w-full px-3.5 py-2 rounded-lg bg-[#090B10] border border-white/[0.08] text-sm text-[#F1F5F9] placeholder-[#475569] focus:outline-none focus:border-[#3B82F6] focus:ring-1 focus:ring-[#3B82F6] transition-colors resize-y"
              />
            </div>

            {/* Target Industries */}
            <div className="space-y-1.5">
              <label className="block text-xs font-medium text-[#94A3B8]">
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
                  className="flex-1 px-3 py-1.5 rounded-md bg-[#090B10] border border-white/[0.08] text-xs text-[#F1F5F9] placeholder-[#475569] focus:outline-none focus:border-[#3B82F6]"
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
              <label className="block text-xs font-medium text-[#94A3B8]">
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
                  className="flex-1 px-3 py-1.5 rounded-md bg-[#090B10] border border-white/[0.08] text-xs text-[#F1F5F9] placeholder-[#475569] focus:outline-none focus:border-[#3B82F6]"
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

            {/* Expiration (Optional) */}
            <div className="space-y-1.5">
              <label htmlFor="post-expires-at" className="block text-xs font-medium text-[#94A3B8]">
                Expiration Date & Time (Optional UTC)
              </label>
              <input
                id="post-expires-at"
                type="datetime-local"
                value={expiresAt}
                onChange={(e) => setExpiresAt(e.target.value)}
                className="px-3 py-1.5 rounded-lg bg-[#090B10] border border-white/[0.08] text-xs text-[#F1F5F9] focus:outline-none focus:border-[#3B82F6]"
              />
              <p className="text-[11px] text-[#64748B]">
                Expired opportunities are automatically omitted from discovery feeds and reject new autonomous comments.
              </p>
            </div>
          </div>

          {/* Sticky Footer Actions */}
          <div className="flex items-center justify-end gap-3 px-6 py-3 border-t border-white/[0.08] bg-[#0E131C] shrink-0">
            <button
              type="button"
              onClick={onClose}
              disabled={isSubmitting}
              className="px-4 py-2 rounded-lg text-xs font-medium text-[#94A3B8] hover:text-[#F1F5F9] hover:bg-white/[0.04] transition-colors disabled:opacity-50"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={isSubmitting}
              className="flex items-center gap-2 px-5 py-2 rounded-lg bg-[#2563EB] hover:bg-[#1D4ED8] text-white text-xs font-semibold shadow-sm transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {isSubmitting ? (
                <>
                  <Loader2 className="w-3.5 h-3.5 animate-spin" />
                  <span>Publishing…</span>
                </>
              ) : (
                <>
                  <Send className="w-3.5 h-3.5" />
                  <span>Publish Opportunity</span>
                </>
              )}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
