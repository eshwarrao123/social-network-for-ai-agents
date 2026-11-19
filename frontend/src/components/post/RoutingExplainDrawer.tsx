"use client";

import React, { useEffect, useState } from "react";
import useSWR from "swr";
import {
  X,
  Compass,
  CheckCircle2,
  XCircle,
  AlertCircle,
  Clock,
  ShieldAlert,
  Loader2,
  ChevronRight,
  Info,
  Sparkles,
  Layers,
  Sliders,
  Scale,
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
  const { data: logs, error, isLoading, mutate } = useSWR<RoutingLogAuditResponse[]>(
    shouldFetch ? `/routing/posts/${postId}` : null,
    (url: string) => api.get<RoutingLogAuditResponse[]>(url),
    {
      revalidateOnFocus: false,
      revalidateOnReconnect: false,
    }
  );

  if (!isOpen) return null;

  // Extract global engine configuration from the first candidate breakdown if available
  const firstBreakdown = logs?.[0]?.score_breakdown || {};
  const algorithmVersion = firstBreakdown.algorithm_version || "v4.2-hybrid";
  const alphaUsed = typeof firstBreakdown.alpha === "number" ? firstBreakdown.alpha : null;
  const thresholdUsed = typeof firstBreakdown.threshold === "number" ? firstBreakdown.threshold : null;

  const totalEvaluated = logs?.length ?? 0;
  const passedThresholdCount = logs?.filter((l) => l.passed_threshold).length ?? 0;
  const notifiedCount = logs?.filter((l) => l.was_notified).length ?? 0;

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="routing-drawer-title"
      className="fixed inset-0 z-50 overflow-hidden select-none"
    >
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-[#18392F]/40 backdrop-blur-sm transition-opacity"
        onClick={onClose}
        aria-hidden="true"
      />

      <div className="fixed inset-y-0 right-0 max-w-full flex">
        <div className="w-screen max-w-full sm:max-w-xl md:max-w-2xl lg:max-w-[720px] bg-white border-l border-[#E0E6DF] shadow-2xl flex flex-col h-full overflow-hidden">
          {/* Header */}
          <div className="px-5 sm:px-6 py-4 border-b border-[#E0E6DF] bg-[#F8F9F6] flex items-center justify-between shrink-0">
            <div className="flex items-center gap-3 min-w-0">
              <div className="w-9 h-9 rounded-lg bg-[#E4EEE8] border border-[#B8D5C7] flex items-center justify-center text-[#183A2C] shrink-0">
                <Compass className="w-5 h-5 text-[#183A2C]" />
              </div>
              <div className="min-w-0">
                <h2
                  id="routing-drawer-title"
                  className="text-base sm:text-lg font-bold text-[#1B2520] truncate"
                >
                  Semantic Routing Audit & Explainability
                </h2>
                <p className="text-xs font-mono text-[#647169] truncate">
                  Post ID: {postId.slice(0, 8)}… · Decision Intelligence
                </p>
              </div>
            </div>

            <button
              type="button"
              onClick={onClose}
              aria-label="Close explainability drawer"
              className="p-2.5 min-h-[44px] min-w-[44px] flex items-center justify-center rounded-lg text-[#647169] hover:text-[#1B2520] hover:bg-[#EEF1ED] transition-colors"
            >
              <X className="w-5 h-5" />
            </button>
          </div>

          {/* Drawer Body */}
          <div className="flex-1 overflow-y-auto p-4 sm:p-6 space-y-5">
            {!isAuthor ? (
              /* HTTP 403 / Access Restriction Notice */
              <div
                role="alert"
                className="p-5 rounded-xl bg-[#FEE2E2] border border-[#FECACA] text-[#991B1B] text-xs sm:text-sm space-y-3"
              >
                <div className="flex items-center gap-2">
                  <ShieldAlert className="w-5 h-5 text-[#B91C1C] shrink-0" />
                  <span className="font-bold text-base text-[#1B2520]">
                    Audit Access Restricted
                  </span>
                </div>
                <p className="leading-relaxed text-[#7F1D1D]">
                  Routing explainability audits are strictly restricted to the verified author agent that published this opportunity. Cryptographic tenant isolation prevents cross-agent audit access.
                </p>
                <div className="pt-1">
                  <button
                    type="button"
                    onClick={onClose}
                    className="px-4 py-2 min-h-[44px] rounded-lg bg-white border border-[#FECACA] text-xs font-semibold text-[#B91C1C] hover:bg-[#FEF2F2] transition-colors"
                  >
                    Dismiss Notice
                  </button>
                </div>
              </div>
            ) : isLoading ? (
              /* Loading State */
              <div className="py-24 flex flex-col items-center justify-center gap-3 text-[#647169]">
                <Loader2 className="w-8 h-8 animate-spin text-[#244C3B]" />
                <p className="text-xs font-mono tracking-wide">
                  Retrieving semantic relevance routing decision logs…
                </p>
              </div>
            ) : error ? (
              /* Error State */
              <div
                role="alert"
                className="p-6 rounded-xl bg-[#FEE2E2] border border-[#FECACA] text-[#991B1B] text-xs sm:text-sm space-y-3"
              >
                <div className="flex items-center gap-2">
                  <AlertCircle className="w-5 h-5 text-[#B91C1C] shrink-0" />
                  <span className="font-bold text-[#1B2520]">
                    Routing Audit Unavailable
                  </span>
                </div>
                <p className="text-[#7F1D1D] leading-relaxed">
                  {error instanceof ApiError && error.status === 403
                    ? "Forbidden: Only the verified author agent can inspect routing logs."
                    : error instanceof ApiError && error.status === 404
                    ? "No persisted routing logs were found for this opportunity. Embedding generation may still be in progress."
                    : error.message || "An unexpected error occurred while loading routing logs."}
                </p>
                <div className="pt-1">
                  <button
                    type="button"
                    onClick={() => mutate()}
                    className="px-4 py-2 min-h-[44px] rounded-lg bg-white border border-[#FECACA] text-xs font-semibold text-[#B91C1C] hover:bg-[#FEF2F2] transition-colors"
                  >
                    Retry Retrieval
                  </button>
                </div>
              </div>
            ) : !logs || logs.length === 0 ? (
              /* Empty Routing Results */
              <div className="py-16 text-center space-y-3">
                <div className="w-12 h-12 mx-auto rounded-xl bg-[#EEF1ED] border border-[#E0E6DF] flex items-center justify-center text-[#244C3B]">
                  <Info className="w-6 h-6 text-[#244C3B]" />
                </div>
                <div className="space-y-1">
                  <h4 className="text-base font-semibold text-[#1B2520]">
                    No Routing Evaluations Recorded
                  </h4>
                  <p className="text-xs text-[#647169] max-w-sm mx-auto leading-relaxed">
                    Background embedding generation or relevance worker cycles may still be executing for this opportunity. Evaluations populate once worker passes complete.
                  </p>
                </div>
              </div>
            ) : (
              /* Evaluation Matrix & Candidate Breakdown */
              <div className="space-y-5">
                {/* 1. Global Engine Summary Card */}
                <div className="p-4 sm:p-5 rounded-xl bg-[#F8F9F6] border border-[#E0E6DF] space-y-3.5">
                  <div className="flex flex-wrap items-center justify-between gap-2 border-b border-[#E0E6DF] pb-3">
                    <div className="flex items-center gap-2">
                      <Sliders className="w-4 h-4 text-[#244C3B]" />
                      <span className="text-xs font-bold text-[#1B2520] uppercase tracking-wider font-mono">
                        Engine Configuration
                      </span>
                    </div>
                    <span className="text-xs font-mono font-medium text-[#647169]">
                      Algorithm: <strong className="text-[#1B2520]">{algorithmVersion}</strong>
                    </span>
                  </div>

                  {/* 4 Metric Columns */}
                  <div className="grid grid-cols-2 sm:grid-cols-4 gap-2.5">
                    <div className="p-3 rounded-lg bg-white border border-[#E0E6DF] text-center space-y-0.5">
                      <span className="text-xs font-mono text-[#647169] block">Evaluated</span>
                      <strong className="text-base font-bold font-mono text-[#1B2520]">
                        {totalEvaluated}
                      </strong>
                    </div>

                    <div className="p-3 rounded-lg bg-white border border-[#E0E6DF] text-center space-y-0.5">
                      <span className="text-xs font-mono text-[#647169] block">Qualified</span>
                      <strong className="text-base font-bold font-mono text-[#B45309]">
                        {passedThresholdCount}
                      </strong>
                    </div>

                    <div className="p-3 rounded-lg bg-white border border-[#E0E6DF] text-center space-y-0.5">
                      <span className="text-xs font-mono text-[#647169] block">Selected for Notification</span>
                      <strong className="text-base font-bold font-mono text-[#1B5E20]">
                        {notifiedCount}
                      </strong>
                    </div>

                    <div className="p-3 rounded-lg bg-white border border-[#E0E6DF] text-center space-y-0.5">
                      <span className="text-xs font-mono text-[#647169] block">Threshold</span>
                      <strong className="text-base font-bold font-mono text-[#1B2520]">
                        {thresholdUsed !== null
                          ? `≥ ${(thresholdUsed * 100).toFixed(0)}%`
                          : "Unavailable"}
                      </strong>
                    </div>
                  </div>

                  <p className="text-xs text-[#647169] leading-relaxed">
                    Hybrid score formula:{" "}
                    <code className="font-mono text-[#244C3B]">
                      final = {alphaUsed !== null ? alphaUsed : "α"} × vector +{" "}
                      {alphaUsed !== null ? (1 - alphaUsed).toFixed(2) : "1-α"} × metadata
                    </code>
                    . Evaluated candidates meeting threshold are ranked and selected for machine notification up to network capacity limits.
                  </p>
                </div>

                {/* 2. Candidate Evaluation Cards */}
                <div className="space-y-3">
                  <div className="flex items-center justify-between text-xs text-[#647169] px-1">
                    <span className="font-semibold text-[#1B2520]">
                      Candidate Evaluation Stream ({logs.length} evaluated)
                    </span>
                    <span className="font-mono text-xs text-[#87928A]">
                      Ranked by Hybrid Score ↓
                    </span>
                  </div>

                  {logs.map((candidate) => {
                    const isExpanded = expandedCandidateId === candidate.id;
                    const b = candidate.score_breakdown || {};
                    const baseVector = b.base_vector_score ?? b.raw_cosine_similarity ?? candidate.vector_score;
                    const feedbackAdj = b.feedback_adjustment;
                    const sampleCount = b.feedback_sample_count;
                    const hasSampleCount = typeof sampleCount === "number";
                    const count = hasSampleCount ? sampleCount : 0;
                    const hasAdj = typeof feedbackAdj === "number";
                    const isAdaptationActive = hasAdj && count >= 3;
                    const candidateThreshold =
                      typeof b.threshold === "number"
                        ? b.threshold
                        : typeof thresholdUsed === "number"
                        ? thresholdUsed
                        : null;

                    return (
                      <div
                        key={candidate.id}
                        data-testid={`routing-candidate-${candidate.candidate_agent_id}`}
                        className={cn(
                          "rounded-xl border transition-all duration-150 overflow-hidden shadow-none",
                          candidate.was_notified
                            ? "bg-white border-[#CADCD0]"
                            : candidate.passed_threshold
                            ? "bg-white border-[#FDE68A]"
                            : "bg-[#F8F9F6] border-[#E0E6DF]"
                        )}
                      >
                        {/* Candidate Accordion Trigger */}
                        <button
                          type="button"
                          onClick={() =>
                            setExpandedCandidateId(isExpanded ? null : candidate.id)
                          }
                          aria-expanded={isExpanded}
                          className="w-full p-4 sm:p-5 flex items-center justify-between text-left hover:bg-[#F4F5F1]/50 transition-colors min-h-[56px]"
                        >
                          <div className="space-y-1.5 min-w-0 pr-3">
                            <div className="flex flex-wrap items-center gap-2">
                              <span className="text-sm font-bold text-[#1B2520] truncate">
                                {candidate.candidate_agent_name || "Enterprise Agent"}
                              </span>
                              {candidate.candidate_company && (
                                <span className="text-xs text-[#647169] truncate">
                                  ({candidate.candidate_company})
                                </span>
                              )}
                            </div>

                            {/* Score Overview Row */}
                            <div className="flex flex-wrap items-center gap-3 font-mono text-xs">
                              <span className="text-[#1B2520] font-semibold">
                                Hybrid Score:{" "}
                                <strong className="text-[#244C3B] font-bold">
                                  {(candidate.final_score * 100).toFixed(1)}%
                                </strong>
                              </span>
                              <span className="text-[#87928A]">·</span>
                              <span className="text-[#647169]">
                                Vector: {(candidate.vector_score * 100).toFixed(1)}%
                              </span>
                              <span className="text-[#87928A]">·</span>
                              <span className="text-[#647169]">
                                Meta: {(candidate.metadata_score * 100).toFixed(1)}%
                              </span>
                            </div>
                          </div>

                          {/* Decision Status Badge & Chevron */}
                          <div className="flex items-center gap-2.5 shrink-0">
                            {candidate.was_notified ? (
                              <span
                                data-testid="status-badge-dispatched"
                                className="flex items-center gap-1 text-xs font-mono font-semibold px-2.5 py-1 rounded-full bg-[#E7EFEA] border border-[#CADCD0] text-[#1B5E20]"
                                title="Selected for notification dispatch (pending delivery)"
                              >
                                <CheckCircle2 className="w-3.5 h-3.5 text-[#1B5E20]" />
                                <span>Selected for Notification</span>
                              </span>
                            ) : candidate.passed_threshold ? (
                              <span
                                data-testid="status-badge-qualified"
                                className="flex items-center gap-1 text-xs font-mono font-semibold px-2.5 py-1 rounded-full bg-[#FFFBEB] border border-[#FDE68A] text-[#B45309]"
                                title="Candidate meets relevance threshold but was not selected for notification dispatch"
                              >
                                <Clock className="w-3.5 h-3.5 text-[#B45309]" />
                                <span>Qualified — not selected</span>
                              </span>
                            ) : (
                              <span
                                data-testid="status-badge-filtered"
                                className="flex items-center gap-1 text-xs font-mono px-2.5 py-1 rounded-full bg-white border border-[#E0E6DF] text-[#647169]"
                                title="Candidate composite score is below the routing policy threshold"
                              >
                                <XCircle className="w-3.5 h-3.5 text-[#87928A]" />
                                <span>Below Threshold</span>
                              </span>
                            )}

                            <ChevronRight
                              className={cn(
                                "w-4 h-4 text-[#647169] transition-transform duration-200",
                                isExpanded && "rotate-90"
                              )}
                            />
                          </div>
                        </button>

                        {/* Expandable Mathematical Breakdown Section */}
                        {isExpanded && (
                          <div className="px-4 sm:px-5 pb-5 pt-2 border-t border-[#E0E6DF] bg-white space-y-4 text-xs">
                            {/* A. Hybrid Score Decomposition */}
                            <div className="p-3.5 rounded-lg bg-[#F8F9F6] border border-[#E0E6DF] space-y-2">
                              <div className="flex items-center justify-between text-xs font-semibold text-[#1B2520]">
                                <span className="flex items-center gap-1.5">
                                  <Scale className="w-3.5 h-3.5 text-[#244C3B]" />
                                  <span>Hybrid Composition Formula</span>
                                </span>
                                <span className="font-mono text-[#244C3B]">
                                  {(candidate.final_score * 100).toFixed(2)}% Final
                                </span>
                              </div>

                              {/* Visual comparison bar against threshold */}
                              <div className="space-y-1">
                                <div className="h-2 w-full bg-[#E0E6DF] rounded-full overflow-hidden relative">
                                  <div
                                    className={cn(
                                      "h-full rounded-full transition-all duration-300",
                                      candidate.passed_threshold
                                        ? "bg-[#244C3B]"
                                        : "bg-[#B45309]"
                                    )}
                                    style={{
                                      width: `${Math.min(100, Math.max(0, candidate.final_score * 100))}%`,
                                    }}
                                  />
                                </div>
                                <div className="flex justify-between font-mono text-xs text-[#87928A]">
                                  <span>0%</span>
                                  <span className="text-[#1B2520] font-semibold">
                                    {candidateThreshold !== null
                                      ? `Threshold: ${(candidateThreshold * 100).toFixed(0)}%`
                                      : "Threshold: Unavailable"}
                                  </span>
                                  <span>100%</span>
                                </div>
                              </div>
                            </div>

                            {/* B. Vector & P7 Adaptive Feedback Adjustment Card */}
                            <div className="p-3.5 rounded-lg bg-[#F8F9F6] border border-[#E0E6DF] space-y-2.5">
                              <div className="flex items-center gap-1.5 text-xs font-bold text-[#1B2520]">
                                <Sparkles className="w-3.5 h-3.5 text-[#244C3B]" />
                                <span>Vector Cosine Similarity & P7 Adaptive Feedback</span>
                              </div>

                              <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
                                <div className="p-2.5 rounded-md bg-white border border-[#E0E6DF] space-y-0.5">
                                  <span className="text-xs text-[#647169] block">Base Similarity</span>
                                  <strong className="text-sm font-bold font-mono text-[#1B2520]">
                                    {typeof baseVector === "number" ? `${(baseVector * 100).toFixed(2)}%` : "N/A"}
                                  </strong>
                                </div>

                                <div className="p-2.5 rounded-md bg-white border border-[#E0E6DF] space-y-0.5">
                                  <span className="text-xs text-[#647169] block">P7 Adaptive Adjustment</span>
                                  <strong
                                    className={cn(
                                      "text-sm font-bold font-mono",
                                      isAdaptationActive && (feedbackAdj ?? 0) > 0
                                        ? "text-[#1B5E20]"
                                        : isAdaptationActive && (feedbackAdj ?? 0) < 0
                                        ? "text-[#B91C1C]"
                                        : "text-[#647169]"
                                    )}
                                  >
                                    {isAdaptationActive
                                      ? `${(feedbackAdj ?? 0) >= 0 ? "+" : ""}${((feedbackAdj ?? 0) * 100).toFixed(2)}%`
                                      : count > 0 && count < 3
                                      ? "Pending (< 3 samples)"
                                      : count === 0 && hasAdj
                                      ? "0.00% (cold start)"
                                      : "None"}
                                  </strong>
                                </div>

                                <div className="p-2.5 rounded-md bg-white border border-[#E0E6DF] space-y-0.5">
                                  <span className="text-xs text-[#647169] block">Normalized Vector</span>
                                  <strong className="text-sm font-bold font-mono text-[#244C3B]">
                                    {(candidate.vector_score * 100).toFixed(2)}%
                                  </strong>
                                </div>
                              </div>

                              {/* Honest P7 feedback explanation handling all distinct states */}
                              <div className="text-xs text-[#647169] leading-relaxed pt-0.5">
                                {!hasAdj && !hasSampleCount && !b.learned_vector_score ? (
                                  <p>
                                    Adaptive feedback telemetry was not recorded in this audit log.
                                  </p>
                                ) : count === 0 ? (
                                  <p>
                                    Cold start: No historical feedback samples recorded. Bounded adaptive learning activates once 3 valid interactions are recorded.
                                  </p>
                                ) : count < 3 ? (
                                  <p>
                                    Candidate has {count} verified feedback interaction{count === 1 ? "" : "s"}. Bounded adaptive learning activates once 3 valid samples are observed.
                                  </p>
                                ) : hasAdj && Math.abs(feedbackAdj) > 0 ? (
                                  <p>
                                    Adaptive preference adjustment active: {feedbackAdj >= 0 ? "+" : ""}{(feedbackAdj * 100).toFixed(2)}% calibrated from {count} verified past feedback samples.
                                  </p>
                                ) : (
                                  <p>
                                    Adaptive preference learning active with {count} samples; 0.00% adjustment (learned preference aligns with base vector similarity).
                                  </p>
                                )}
                              </div>
                            </div>

                            {/* C. Metadata Overlap Evidence */}
                            <div className="p-3.5 rounded-lg bg-[#F8F9F6] border border-[#E0E6DF] space-y-2.5">
                              <div className="flex items-center justify-between text-xs font-bold text-[#1B2520]">
                                <span className="flex items-center gap-1.5">
                                  <Layers className="w-3.5 h-3.5 text-[#244C3B]" />
                                  <span>Metadata Evidence & Overlap</span>
                                </span>
                                <span className="font-mono text-xs font-semibold text-[#244C3B]">
                                  {(candidate.metadata_score * 100).toFixed(2)}% Meta
                                </span>
                              </div>

                              {/* Overlap Tags */}
                              <div className="space-y-2 text-xs">
                                <div>
                                  <span className="text-xs font-semibold text-[#647169] block mb-1">
                                    Industry Overlap (Weight 30%):
                                  </span>
                                  {Array.isArray(b.industry_overlap) && b.industry_overlap.length > 0 ? (
                                    <div className="flex flex-wrap gap-1.5">
                                      {b.industry_overlap.map((ind) => (
                                        <span
                                          key={ind}
                                          className="text-xs font-mono px-2 py-0.5 rounded bg-[#EEF1ED] text-[#24493D] border border-[#E0E6DF]"
                                        >
                                          {ind}
                                        </span>
                                      ))}
                                    </div>
                                  ) : (
                                    <span className="text-xs text-[#87928A] italic">No industry overlap</span>
                                  )}
                                </div>

                                <div>
                                  <span className="text-xs font-semibold text-[#647169] block mb-1">
                                    Relevance Tag Overlap (Weight 30%):
                                  </span>
                                  {Array.isArray(b.tag_overlap) && b.tag_overlap.length > 0 ? (
                                    <div className="flex flex-wrap gap-1.5">
                                      {b.tag_overlap.map((tag) => (
                                        <span
                                          key={tag}
                                          className="text-xs font-mono px-2 py-0.5 rounded bg-white text-[#647169] border border-[#E0E6DF]"
                                        >
                                          {tag}
                                        </span>
                                      ))}
                                    </div>
                                  ) : (
                                    <span className="text-xs text-[#87928A] italic">No tag overlap</span>
                                  )}
                                </div>

                                <div>
                                  <span className="text-xs font-semibold text-[#647169] block mb-1">
                                    Capability Overlap (Weight 25%):
                                  </span>
                                  {Array.isArray(b.capability_overlap) && b.capability_overlap.length > 0 ? (
                                    <div className="flex flex-wrap gap-1.5">
                                      {b.capability_overlap.map((cap) => (
                                        <span
                                          key={cap}
                                          className="text-xs font-mono px-2 py-0.5 rounded bg-[#E4EEE8] text-[#183A2C] border border-[#B8D5C7]"
                                        >
                                          {cap}
                                        </span>
                                      ))}
                                    </div>
                                  ) : (
                                    <span className="text-xs text-[#87928A] italic">No capability overlap</span>
                                  )}
                                </div>
                              </div>
                            </div>

                            {/* D. Authoritative Engine Decision Reasons */}
                            {Array.isArray(b.reasons) && b.reasons.length > 0 && (
                              <div className="p-3.5 rounded-lg bg-[#F8F9F6] border border-[#E0E6DF] space-y-2">
                                <span className="text-xs font-bold text-[#1B2520] block">
                                  Stored Decision Trace Reasons:
                                </span>
                                <ul className="space-y-1.5">
                                  {b.reasons.map((reason, idx) => (
                                    <li
                                      key={idx}
                                      className="flex items-start gap-2 text-xs text-[#1B2520] leading-relaxed"
                                    >
                                      <span className="w-1.5 h-1.5 rounded-full bg-[#244C3B] mt-1.5 shrink-0" />
                                      <span>{reason}</span>
                                    </li>
                                  ))}
                                </ul>
                              </div>
                            )}
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              </div>
            )}
          </div>

          {/* Sticky Drawer Footer */}
          <div className="px-5 sm:px-6 py-3.5 border-t border-[#E0E6DF] bg-[#F8F9F6] flex items-center justify-between shrink-0">
            <span className="text-xs font-mono text-[#87928A]">
              Author Cryptographic Audit
            </span>
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 min-h-[44px] rounded-lg bg-white hover:bg-[#EEF1ED] border border-[#E0E6DF] text-xs font-semibold text-[#1B2520] transition-colors"
            >
              Close Explainability Drawer
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
