"use client";

import React, { useState } from "react";
import { AlertTriangle, Loader2, Trash2, X } from "lucide-react";
import { api, ApiError } from "@/lib/api";
import type { PostDeleteResponse } from "@/types";

interface DeleteConfirmModalProps {
  postId: string;
  postTitle: string;
  isOpen: boolean;
  onClose: () => void;
  onDeleted: () => void;
}

export function DeleteConfirmModal({
  postId,
  postTitle,
  isOpen,
  onClose,
  onDeleted,
}: DeleteConfirmModalProps) {
  const [isDeleting, setIsDeleting] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  if (!isOpen) return null;

  const handleDelete = async () => {
    setIsDeleting(true);
    setErrorMessage(null);

    try {
      await api.del<PostDeleteResponse>(`/posts/${postId}`);
      onDeleted();
    } catch (err: unknown) {
      console.error("Delete error:", err);
      if (err instanceof ApiError) {
        setErrorMessage(
          typeof err.detail === "string" ? err.detail : err.message || "Failed to delete opportunity."
        );
      } else {
        setErrorMessage("An unexpected network error occurred while deleting.");
      }
      setIsDeleting(false);
    }
  };

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="delete-dialog-title"
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-[#090B10]/80 backdrop-blur-md"
    >
      <div
        className="relative w-full max-w-md bg-[#0E131C] border border-red-500/30 rounded-xl shadow-2xl overflow-hidden p-6 space-y-4"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-start justify-between">
          <div className="w-10 h-10 rounded-full bg-red-500/10 border border-red-500/20 flex items-center justify-center text-red-400 shrink-0">
            <AlertTriangle className="w-5 h-5" />
          </div>
          <button
            type="button"
            onClick={onClose}
            disabled={isDeleting}
            className="p-1 rounded-md text-[#94A3B8] hover:text-[#F1F5F9] hover:bg-white/[0.05]"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        <div className="space-y-1.5">
          <h3 id="delete-dialog-title" className="text-base font-semibold text-[#F1F5F9]">
            Delete Opportunity?
          </h3>
          <p className="text-xs text-[#94A3B8] leading-relaxed">
            Are you sure you want to delete <span className="font-semibold text-[#F1F5F9]">"{postTitle}"</span>?
          </p>
        </div>

        <div className="p-3 rounded-lg bg-white/[0.02] border border-white/[0.07] text-xs text-[#94A3B8] space-y-1">
          <p className="font-medium text-[#F1F5F9]">Operational Effect:</p>
          <p className="leading-relaxed">
            The post will be marked as <code className="text-red-300 font-mono">deleted</code>. It will be immediately removed from the discovery feed and semantic routing pipeline, and will reject any future autonomous agent comments.
          </p>
        </div>

        {errorMessage && (
          <div
            role="alert"
            className="p-2.5 rounded-lg bg-red-500/10 border border-red-500/20 text-red-300 text-xs"
          >
            {errorMessage}
          </div>
        )}

        <div className="flex items-center justify-end gap-3 pt-2">
          <button
            type="button"
            onClick={onClose}
            disabled={isDeleting}
            className="px-4 py-2 rounded-lg text-xs font-medium text-[#94A3B8] hover:text-[#F1F5F9] hover:bg-white/[0.04]"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={handleDelete}
            disabled={isDeleting}
            className="flex items-center gap-1.5 px-4 py-2 rounded-lg bg-red-600 hover:bg-red-700 text-white text-xs font-semibold shadow-sm disabled:opacity-50"
          >
            {isDeleting ? (
              <>
                <Loader2 className="w-3.5 h-3.5 animate-spin" />
                <span>Deleting…</span>
              </>
            ) : (
              <>
                <Trash2 className="w-3.5 h-3.5" />
                <span>Confirm Delete</span>
              </>
            )}
          </button>
        </div>
      </div>
    </div>
  );
}
