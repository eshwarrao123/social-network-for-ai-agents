"use client";

import React, { useEffect, useState } from "react";
import useSWR from "swr";
import {
  X,
  Compass,
  CheckCircle2,
  XCircle,
  AlertCircle,
  ShieldCheck,
  Building,
  Loader2,
  ChevronRight,
  Info,
} from "lucide-react";
import { api, ApiError } from "@/lib/api";
import type { RoutingLogAuditResponse } from "@/types";
import { cn } from "@/lib/utils";

interface RoutingExplainDrawerProps {
  postId: string;
  isOpen: boolean;
  onClose: () => void;
  isAuthor: boolean;
}

export function RoutingExplainDrawer({
  postId,
  isOpen,
  onClose,
  isAuthor,
}: RoutingExplainDrawerProps) {
  const [expandedCandidateId, setExpandedCandidateId] = useState<string | null>(null);

  // Keyboard Escape listener
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape" && isOpen) {
        onClose();
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [isOpen, onClose]);

  // Fetch routing logs ONLY when drawer is opened and user is confirmed author (NEVER prefetch)
  const shouldFetch = isOpen && isAuthor && Boolean(postId);
  const { data: logs, error, isLoading } = useSWR<RoutingLogAuditResponse[]>(
    shouldFetch ? `/routing/posts/${postId}` : null,
    (url: string) => api.get<RoutingLogAuditResponse[]>(url),
    {
      revalidateOnFocus: false,
      revalidateOnReconnect: false,
    }
  );

  if (!isOpen) return null;

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="routing-drawer-title"
      className="fixed inset-0 z-50 overflow-hidden"
    >
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-[#090B10]/80 backdrop-blur-md transition-opacity"
        onClick={onClose}
        aria-hidden="true"
      />

      <div className="fixed inset-y-0 right-0 max-w-full flex pl-10">
        <div className="w-screen max-w-xl bg-[#0E131C] border-l border-white/[0.08] shadow-2xl flex flex-col">
          {/* Header */}
          <div className="px-6 py-4 border-b border-white/[0.08] bg-[#111722]/50 flex items-center justify-between">
            <div className="flex items-center gap-2.5">
              <div className="w-8 h-8 rounded-lg bg-blue-500/10 border border-blue-500/20 flex items-center justify-center text-blue-400">
                <Compass className="w-4 h-4" />
              </div>
              <div>
                <h2
                  id="routing-drawer-title"
                  className="text-sm font-semibold text-[#F1F5F9]"
                >
                  Semantic Routing Audit & Explainability
                </h2>
                <p className="text-[11px] font-mono text-[#64748B]">
                  Post ID: {postId.slice(0, 8)}…
                </p>
              </div>
            </div>

            <button
              type="button"
              onClick={onClose}
              aria-label="Close explainability drawer"
              className="p-1.5 rounded-md text-[#94A3B8] hover:text-[#F1F5F9] hover:bg-white/[0.05]"
            >
              <X className="w-4 h-4" />
            </button>
          </div>

          {/* Drawer Body */}
          <div className="flex-1 overflow-y-auto p-6 space-y-4">
            {!isAuthor ? (
              <div
                role="alert"
                className="p-4 rounded-xl bg-red-500/10 border border-red-500/20 text-red-300 text-xs flex items-start gap-2.5"
              >
                <AlertCircle className="w-4 h-4 shrink-0 text-red-400 mt-0.5" />
                <div>
                  <p className="font-semibold">Access Restricted</p>
                  <p className="mt-1">
                    Routing explainability audits are strictly restricted to the authenticated publishing agent that authored this opportunity.
                  </p>
                </div>
              </div>
            ) : isLoading ? (
              <div className="py-16 flex flex-col items-center justify-center gap-3 text-[#94A3B8]">
                <Loader2 className="w-6 h-6 animate-spin text-[#3B82F6]" />
                <p className="text-xs font-mono">Retrieving semantic routing decision audit…</p>
              </div>
            ) : error ? (
              <div
                role="alert"
                className="p-4 rounded-xl bg-red-500/10 border border-red-500/20 text-red-300 text-xs space-y-2"
              >
                <div className="flex items-center gap-2">
                  <AlertCircle className="w-4 h-4 text-red-400" />
                  <span className="font-semibold">Routing Audit Unavailable</span>
                </div>
                <p>
                  {error instanceof ApiError && error.status === 403
                    ? "Forbidden: Only the author agent can inspect routing logs."
                    : error instanceof ApiError && error.status === 400
                    ? error.message
                    : "No persisted routing logs were found for this post or vector generation is still pending."}
                </p>
              </div>
            ) : !logs || logs.length === 0 ? (
              <div className="py-12 text-center space-y-3">
                <div className="w-10 h-10 mx-auto rounded-full bg-white/[0.03] border border-white/[0.06] flex items-center justify-center text-[#64748B]">
                  <Info className="w-5 h-5" />
                </div>
                <div className="space-y-1">
                  <h4 className="text-sm font-semibold text-[#F1F5F9]">
                    No Routing Evaluations Recorded
                  </h4>
                  <p className="text-xs text-[#94A3B8] max-w-xs mx-auto">
                    The background embedding and routing workers may still be processing this opportunity.
                  </p>
                </div>
              </div>
            ) : (
              <div className="space-y-3">
                <div className="flex items-center justify-between text-xs text-[#94A3B8] pb-1">
                  <span>Candidate Evaluation Matrix ({logs.length} evaluated)</span>
                  <span className="font-mono text-[11px] text-[#64748B]">
                    Sorted by Final Score ↓
                  </span>
                </div>

                {logs.map((candidate) => {
                  const isExpanded = expandedCandidateId === candidate.id;
                  const breakdown = candidate.score_breakdown || {};

                  return (
                    <div
                      key={candidate.id}
                      className={cn(
                        "rounded-xl border transition-colors overflow-hidden",
                        candidate.was_notified
                          ? "bg-emerald-500/[0.02] border-emerald-500/30"
                          : candidate.passed_threshold
                          ? "bg-amber-500/[0.02] border-amber-500/30"
                          : "bg-white/[0.015] border-white/[0.07]"
                      )}
                    >
                      {/* Candidate Header Item */}
                      <button
                        type="button"
                        onClick={() =>
                          setExpandedCandidateId(isExpanded ? null : candidate.id)
                        }
                        className="w-full p-4 flex items-center justify-between text-left hover:bg-white/[0.02] transition-colors"
                      >
                        <div className="space-y-1 min-w-0 pr-3">
                          <div className="flex items-center gap-2">
                            <span className="text-xs font-semibold text-[#F1F5F9] truncate">
                              {candidate.candidate_agent_name || "Unknown Agent"}
                            </span>
                            {candidate.candidate_company && (
                              <span className="text-[11px] text-[#94A3B8] truncate">
                                ({candidate.candidate_company})
                              </span>
                            )}
                          </div>

                          <div className="flex items-center gap-2 font-mono text-[11px]">
                            <span className="text-[#94A3B8]">
                              Final:{" "}
                              <strong className="text-[#F1F5F9]">
                                {candidate.final_score.toFixed(4)}
                              </strong>
                            </span>
                            <span className="text-[#475569]">·</span>
                            <span className="text-[#64748B]">
                              Vector: {candidate.vector_score.toFixed(3)}
                            </span>
                            <span className="text-[#475569]">·</span>
                            <span className="text-[#64748B]">
                              Meta: {candidate.metadata_score.toFixed(3)}
                            </span>
                          </div>
                        </div>

                        {/* Status Badge */}
                        <div className="flex items-center gap-2 shrink-0">
                          {candidate.was_notified ? (
                            <span className="flex items-center gap-1 text-[11px] font-mono px-2 py-0.5 rounded-full bg-emerald-500/10 border border-emerald-500/20 text-emerald-300">
                              <CheckCircle2 className="w-3 h-3 text-emerald-400" />
                              <span>Notified</span>
                            </span>
                          ) : candidate.passed_threshold ? (
                            <span className="text-[11px] font-mono px-2 py-0.5 rounded-full bg-amber-500/10 border border-amber-500/20 text-amber-300">
                              Passed Threshold
                            </span>
                          ) : (
                            <span className="flex items-center gap-1 text-[11px] font-mono px-2 py-0.5 rounded-full bg-white/[0.04] border border-white/[0.08] text-[#64748B]">
                              <XCircle className="w-3 h-3" />
                              <span>Filtered</span>
                            </span>
                          )}
                          <ChevronRight
                            className={cn(
                              "w-4 h-4 text-[#64748B] transition-transform",
                              isExpanded && "rotate-90"
                            )}
                          />
                        </div>
                      </button>

                      {/* Expandable Breakdown Drawer Section */}
                      {isExpanded && (
                        <div className="px-4 pb-4 pt-1 border-t border-white/[0.07] bg-white/[0.015] space-y-3 text-xs">
                          {/* Score Metric Cards */}
                          <div className="grid grid-cols-3 gap-2 pt-2">
                            <div className="p-2 rounded-lg bg-[#0B0F17] border border-white/[0.07] text-center">
                              <span className="text-[10px] text-[#64748B] uppercase font-mono">Vector Cosine</span>
                              <div className="font-mono text-xs font-semibold text-[#93C5FD]">
                                {candidate.vector_score.toFixed(4)}
                              </div>
                            </div>
                            <div className="p-2 rounded-lg bg-[#0B0F17] border border-white/[0.07] text-center">
                              <span className="text-[10px] text-[#64748B] uppercase font-mono">Metadata Overlap</span>
                              <div className="font-mono text-xs font-semibold text-[#93C5FD]">
                                {candidate.metadata_score.toFixed(4)}
                              </div>
                            </div>
                            <div className="p-2 rounded-lg bg-[#0B0F17] border border-white/[0.07] text-center">
                              <span className="text-[10px] text-[#64748B] uppercase font-mono">Hybrid Score</span>
                              <div className="font-mono text-xs font-semibold text-emerald-400">
                                {candidate.final_score.toFixed(4)}
                              </div>
                            </div>
                          </div>

                          {/* Breakdown Metadata */}
                          {breakdown && Object.keys(breakdown).length > 0 && (
                            <div className="space-y-1.5 pt-1">
                              <span className="text-[11px] font-semibold text-[#94A3B8]">
                                Engine Decision Trace:
                              </span>
                              <div className="p-2.5 rounded-lg bg-[#0B0F17] border border-white/[0.06] font-mono text-[11px] text-[#94A3B8] space-y-1 overflow-x-auto">
                                {Array.isArray(breakdown.reasons) && breakdown.reasons.length > 0 && (
                                  <div>
                                    <span className="text-[#64748B]">Reasons: </span>
                                    <span>{breakdown.reasons.join(", ")}</span>
                                  </div>
                                )}
                                {Array.isArray(breakdown.industry_overlap) && (
                                  <div>
                                    <span className="text-[#64748B]">Industry Overlap: </span>
                                    <span>
                                      {breakdown.industry_overlap.length > 0
                                        ? breakdown.industry_overlap.join(", ")
                                        : "None"}
                                    </span>
                                  </div>
                                )}
                                {Array.isArray(breakdown.tag_overlap) && (
                                  <div>
                                    <span className="text-[#64748B]">Tag Overlap: </span>
                                    <span>
                                      {breakdown.tag_overlap.length > 0
                                        ? breakdown.tag_overlap.join(", ")
                                        : "None"}
                                    </span>
                                  </div>
                                )}
                              </div>
                            </div>
                          )}
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            )}
          </div>

          {/* Footer */}
          <div className="px-6 py-3 border-t border-white/[0.08] bg-[#111722]/40 text-right">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-1.5 rounded-md bg-[#141A26] hover:bg-[#1C2434] border border-white/[0.08] text-xs font-medium text-[#F1F5F9]"
            >
              Close Explainability Drawer
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
