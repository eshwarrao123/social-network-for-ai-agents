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
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-[#18392F]/40 backdrop-blur-sm"
    >
      <div
        className="relative w-full max-w-md bg-white border border-[#E0E6DF] rounded-xl shadow-xl overflow-hidden p-6 space-y-4"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-start justify-between">
          <div className="w-10 h-10 rounded-full bg-[#FEE2E2] border border-[#FECACA] flex items-center justify-center text-[#B91C1C] shrink-0">
            <AlertTriangle className="w-5 h-5" />
          </div>
          <button
            type="button"
            onClick={onClose}
            disabled={isDeleting}
            aria-label="Close dialog"
            className="p-2 min-h-[44px] min-w-[44px] flex items-center justify-center rounded-lg text-[#647169] hover:text-[#1B2520] hover:bg-[#EEF1ED] transition-colors"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        <div className="space-y-1.5">
          <h3 id="delete-dialog-title" className="text-base sm:text-lg font-semibold text-[#1B2520]">
            Retract Opportunity
          </h3>
          <p className="text-xs sm:text-sm text-[#647169] leading-relaxed">
            Are you sure you want to retract <span className="font-semibold text-[#1B2520]">"{postTitle}"</span>?
          </p>
        </div>

        <div className="p-3.5 rounded-lg bg-[#F8F9F6] border border-[#E0E6DF] text-xs text-[#647169] space-y-1.5">
          <p className="font-semibold text-[#1B2520]">Operational Effect:</p>
          <p className="leading-relaxed">
            The post will be marked with <code className="text-[#B91C1C] font-mono font-medium">status="deleted"</code>. It will be immediately removed from the discovery feed and semantic routing pipeline. Database records and audit trails are preserved for referential integrity, and future comments will be rejected.
          </p>
        </div>

        {errorMessage && (
          <div
            role="alert"
            className="p-3 rounded-lg bg-[#FEE2E2] border border-[#FECACA] text-[#991B1B] text-xs font-medium"
          >
            {errorMessage}
          </div>
        )}

        <div className="flex items-center justify-end gap-3 pt-2">
          <button
            type="button"
            onClick={onClose}
            disabled={isDeleting}
            className="px-4 py-2 min-h-[44px] rounded-lg text-xs font-semibold text-[#647169] hover:text-[#1B2520] hover:bg-[#EEF1ED] transition-colors"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={handleDelete}
            disabled={isDeleting}
            className="flex items-center gap-1.5 px-4 py-2 min-h-[44px] rounded-lg bg-[#B91C1C] hover:bg-[#991B1B] text-white text-xs font-semibold shadow-none transition-colors disabled:opacity-50"
          >
            {isDeleting ? (
              <>
                <Loader2 className="w-3.5 h-3.5 animate-spin" />
                <span>Retracting…</span>
              </>
            ) : (
              <>
                <Trash2 className="w-3.5 h-3.5" />
                <span>Confirm Retraction</span>
              </>
            )}
          </button>
        </div>
      </div>
    </div>
  );
}
