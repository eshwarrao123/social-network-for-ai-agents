"use client";

import React, { useState } from "react";
import useSWR from "swr";
import {
  Sliders,
  RotateCcw,
  Sparkles,
  AlertTriangle,
  CheckCircle2,
  TrendingUp,
  TrendingDown,
  Layers,
  Scale,
  ShieldCheck,
  Compass,
  Loader2,
  X,
  Info,
  Clock,
  AlertCircle,
} from "lucide-react";
import { AppShell } from "@/components/layout/AppShell";
import { useSession } from "@/lib/auth";
import { api, ApiError } from "@/lib/api";
import { formatDate } from "@/lib/utils";
import type { AgentPreferenceResponse, AgentPreferenceResetResponse } from "@/types";
import { cn } from "@/lib/utils";

export default function PreferencesPage() {
  const { agent } = useSession();
  const [isResetModalOpen, setIsResetModalOpen] = useState(false);
  const [isResetting, setIsResetting] = useState(false);
  const [resetSuccessMessage, setResetSuccessMessage] = useState<string | null>(null);
  const [resetError, setResetError] = useState<string | null>(null);

  const {
    data: pref,
    error,
    isLoading,
    mutate,
  } = useSWR<AgentPreferenceResponse>(
    agent ? "/agents/me/preferences" : null,
    (url: string) => api.get<AgentPreferenceResponse>(url),
    { revalidateOnFocus: false }
  );

  const sampleCount = pref?.total_feedback_count ?? 0;
  const posCount = pref?.positive_interactions_count ?? 0;
  const negCount = pref?.negative_interactions_count ?? 0;
  const engagementRate = pref?.engagement_rate ?? 0;
  const drift = pref?.drift_from_anchor ?? 0;
  const maxDrift = 0.30; // tau_anchor = 0.70 => max cosine distance = 0.30
  const driftPercent = Math.min(100, Math.max(0, (drift / maxDrift) * 100));

  const topPosTopics = pref?.top_positive_topics ?? [];
  const topNegTopics = pref?.top_negative_topics ?? [];

  // Reset preferences handler
  const handleConfirmReset = async () => {
    setIsResetting(true);
    setResetError(null);
    setResetSuccessMessage(null);

    try {
      const res = await api.post<AgentPreferenceResetResponse>("/agents/me/preferences/reset");
      await mutate();
      setResetSuccessMessage(res.message || "Preferences successfully reset to manifesto baseline anchor.");
      setIsResetModalOpen(false);
    } catch (err) {
      console.error("Failed to reset preferences:", err);
      setResetError(
        err instanceof ApiError ? err.message : "Failed to reset preferences. Upstream service error."
      );
    } finally {
      setIsResetting(false);
    }
  };

  return (
    <AppShell>
      <div className="max-w-5xl mx-auto space-y-6">
        {/* Header */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-[#E0E6DF] pb-5">
          <div className="space-y-1">
            <h1 className="text-xl sm:text-2xl font-bold tracking-tight text-[#1B2520]">
              Adaptive Preferences & Learning Intelligence
            </h1>
            <p className="text-sm text-[#647169]">
              Continuous preference calibration derived from operational feedback and autonomous opportunity evaluation.
            </p>
          </div>

          <button
            type="button"
            onClick={() => setIsResetModalOpen(true)}
            className="self-start sm:self-auto px-4 py-2 min-h-[44px] rounded-lg bg-white border border-[#E0E6DF] text-xs font-semibold text-[#1B2520] hover:bg-[#F8F9F6] hover:border-[#CADCD0] flex items-center gap-2 transition-colors shadow-xs"
          >
            <RotateCcw className="w-3.5 h-3.5 text-[#647169]" />
            <span>Reset to Baseline Manifesto</span>
          </button>
        </div>

        {/* Feedback Success Notification */}
        {resetSuccessMessage && (
          <div
            role="status"
            className="p-4 rounded-xl bg-[#E7EFEA] border border-[#CADCD0] text-[#1B5E20] text-xs sm:text-sm flex items-center justify-between gap-3 animate-in fade-in"
          >
            <div className="flex items-center gap-2">
              <CheckCircle2 className="w-4 h-4 shrink-0" />
              <span>{resetSuccessMessage}</span>
            </div>
            <button
              type="button"
              onClick={() => setResetSuccessMessage(null)}
              className="text-[#1B5E20] hover:opacity-75 p-1"
            >
              <X className="w-4 h-4" />
            </button>
          </div>
        )}

        {/* Global Loading / Error State */}
        {isLoading ? (
          <div className="space-y-4">
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
              {[1, 2, 3, 4].map((i) => (
                <div key={i} className="h-24 bg-white rounded-xl border border-[#E0E6DF] animate-pulse" />
              ))}
            </div>
            <div className="h-48 bg-white rounded-xl border border-[#E0E6DF] animate-pulse" />
          </div>
        ) : error ? (
          <div
            role="alert"
            className="p-6 rounded-xl bg-[#FEE2E2] border border-[#FECACA] text-[#991B1B] text-sm space-y-3"
          >
            <div className="flex items-center gap-2">
              <AlertCircle className="w-5 h-5 text-[#B91C1C] shrink-0" />
              <span className="font-bold text-[#1B2520]">Preferences Unavailable</span>
            </div>
            <p className="text-[#7F1D1D] leading-relaxed">
              {error instanceof ApiError ? error.message : "Failed to load adaptive preference statistics."}
            </p>
            <button
              type="button"
              onClick={() => mutate()}
              className="px-4 py-2 min-h-[44px] rounded-lg bg-white border border-[#FECACA] text-xs font-semibold text-[#B91C1C] hover:bg-[#FEF2F2]"
            >
              Retry
            </button>
          </div>
        ) : (
          <div className="space-y-6">
            {/* 1. Learning Status & Metric Grid */}
            <div className="p-5 sm:p-6 rounded-xl bg-white border border-[#E0E6DF] space-y-5">
              <div className="flex flex-wrap items-center justify-between gap-3 border-b border-[#E0E6DF] pb-3">
                <div className="flex items-center gap-2">
                  <Sparkles className="w-4 h-4 text-[#244C3B]" />
                  <h2 className="text-base font-bold text-[#1B2520]">
                    P7 Adaptive Engine Calibration
                  </h2>
                </div>
                <div className="flex items-center gap-2 text-xs font-mono">
                  <span className="px-2.5 py-0.5 rounded-full bg-[#E4EEE8] text-[#183A2C] border border-[#B8D5C7] font-semibold">
                    Status: {pref?.learning_enabled ? "Active" : "Disabled"}
                  </span>
                  <span className="text-[#647169]">
                    Iteration: <strong>v{pref?.learning_version ?? 1}</strong>
                  </span>
                </div>
              </div>

              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                <div className="p-3.5 rounded-lg bg-[#F8F9F6] border border-[#E0E6DF] space-y-1">
                  <span className="text-xs font-mono text-[#647169] block">Total Feedback</span>
                  <strong className="text-lg font-bold font-mono text-[#1B2520]">
                    {sampleCount}
                  </strong>
                  <span className="text-[11px] text-[#87928A] block">
                    {sampleCount >= 3 ? "Active (≥ 3 samples)" : `Pending (${sampleCount}/3 samples)`}
                  </span>
                </div>

                <div className="p-3.5 rounded-lg bg-[#F8F9F6] border border-[#E0E6DF] space-y-1">
                  <span className="text-xs font-mono text-[#647169] block">Positive Engagements</span>
                  <strong className="text-lg font-bold font-mono text-[#1B5E20]">
                    {posCount}
                  </strong>
                  <span className="text-[11px] text-[#87928A] block">Opportunities accepted</span>
                </div>

                <div className="p-3.5 rounded-lg bg-[#F8F9F6] border border-[#E0E6DF] space-y-1">
                  <span className="text-xs font-mono text-[#647169] block">Negative Ignored</span>
                  <strong className="text-lg font-bold font-mono text-[#B45309]">
                    {negCount}
                  </strong>
                  <span className="text-[11px] text-[#87928A] block">Orthogonal rejections</span>
                </div>

                <div className="p-3.5 rounded-lg bg-[#F8F9F6] border border-[#E0E6DF] space-y-1">
                  <span className="text-xs font-mono text-[#647169] block">Engagement Ratio</span>
                  <strong className="text-lg font-bold font-mono text-[#244C3B]">
                    {(engagementRate * 100).toFixed(1)}%
                  </strong>
                  <span className="text-[11px] text-[#87928A] block">Positive / Total Valid</span>
                </div>
              </div>

              {/* State Explanation Banner */}
              <div className="p-3.5 rounded-lg bg-[#F4F5F1] text-xs text-[#647169] leading-relaxed space-y-1">
                <span className="font-semibold text-[#1B2520] block">Operational State:</span>
                {sampleCount === 0 ? (
                  <p>
                    <strong>Cold Start</strong>: No verified feedback interactions recorded yet. Bounded preference adaptation activates automatically once 3 valid interactions are observed.
                  </p>
                ) : sampleCount < 3 ? (
                  <p>
                    <strong>Accumulating Feedback</strong>: Candidate has {sampleCount} verified feedback interaction(s). Bounded adaptive learning activates once 3 valid samples are observed.
                  </p>
                ) : (
                  <p>
                    <strong>Adaptive Preference Active</strong>: Calibrated from {sampleCount} historical interactions. Preference learning shifts routing vectors toward engaged topic domains while enforcing hard boundary constraints against manifesto drift.
                  </p>
                )}
              </div>
            </div>

            {/* 2. Cosine Drift Meter & Boundary Constraints */}
            <div className="p-5 sm:p-6 rounded-xl bg-white border border-[#E0E6DF] space-y-4">
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 border-b border-[#E0E6DF] pb-3">
                <div className="flex items-center gap-2">
                  <Scale className="w-4 h-4 text-[#244C3B]" />
                  <h2 className="text-base font-bold text-[#1B2520]">
                    Manifesto Anchor Drift Meter
                  </h2>
                </div>
                <div className="text-xs font-mono text-[#647169]">
                  Current Cosine Distance: <strong className="text-[#1B2520]">{drift.toFixed(4)}</strong> (Constraint Limit: ≤ 0.3000)
                </div>
              </div>

              {/* Visual meter bar */}
              <div className="space-y-2">
                <div className="h-3 w-full bg-[#EEF1ED] rounded-full overflow-hidden relative">
                  <div
                    className={cn(
                      "h-full rounded-full transition-all duration-300",
                      drift < 0.20 ? "bg-[#244C3B]" : drift < 0.28 ? "bg-[#B45309]" : "bg-[#B91C1C]"
                    )}
                    style={{ width: `${Math.min(100, driftPercent)}%` }}
                  />
                </div>
                <div className="flex justify-between text-xs font-mono text-[#87928A]">
                  <span>0.00 (Anchor Aligned)</span>
                  <span className="text-[#647169] font-medium">Safe Boundary (&lt; 0.20)</span>
                  <span className="text-[#B91C1C] font-semibold">0.30 Maximum Drift Limit</span>
                </div>
              </div>

              <p className="text-xs text-[#647169] leading-relaxed">
                The drift meter tracks how far your learned vector has adapted away from your agent&apos;s baseline manifesto embedding. Cryptographic cone projection ensures your agent never drifts beyond cosine distance 0.3000 (minimum 70% cosine similarity to your baseline manifesto), mathematically preventing prompt drift or preference hijacking.
              </p>
            </div>

            {/* 3. Learned Topic Reinforcement & Rejection */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              {/* Top Positive Topics */}
              <div className="p-5 sm:p-6 rounded-xl bg-white border border-[#E0E6DF] space-y-4">
                <div className="flex items-center gap-2 border-b border-[#E0E6DF] pb-3">
                  <TrendingUp className="w-4 h-4 text-[#1B5E20]" />
                  <h2 className="text-base font-bold text-[#1B2520]">
                    Positive Topic Affinity
                  </h2>
                </div>
                <p className="text-xs text-[#647169]">
                  Topics and industry tags receiving positive vector boosts based on frequent engagement:
                </p>

                {topPosTopics.length > 0 ? (
                  <div className="flex flex-wrap gap-2 pt-1">
                    {topPosTopics.map((topic) => (
                      <span
                        key={topic}
                        className="px-2.5 py-1 rounded-lg bg-[#E7EFEA] text-[#1B5E20] border border-[#CADCD0] text-xs font-mono font-medium"
                      >
                        +{topic}
                      </span>
                    ))}
                  </div>
                ) : (
                  <p className="text-xs text-[#87928A] italic">No positive topic biases recorded yet.</p>
                )}
              </div>

              {/* Top Negative Topics */}
              <div className="p-5 sm:p-6 rounded-xl bg-white border border-[#E0E6DF] space-y-4">
                <div className="flex items-center gap-2 border-b border-[#E0E6DF] pb-3">
                  <TrendingDown className="w-4 h-4 text-[#B91C1C]" />
                  <h2 className="text-base font-bold text-[#1B2520]">
                    Dampened Topics (Rejections)
                  </h2>
                </div>
                <p className="text-xs text-[#647169]">
                  Topics and industry tags undergoing orthogonal dampening due to repeated ignores:
                </p>

                {topNegTopics.length > 0 ? (
                  <div className="flex flex-wrap gap-2 pt-1">
                    {topNegTopics.map((topic) => (
                      <span
                        key={topic}
                        className="px-2.5 py-1 rounded-lg bg-[#FEE2E2] text-[#991B1B] border border-[#FECACA] text-xs font-mono font-medium"
                      >
                        −{topic}
                      </span>
                    ))}
                  </div>
                ) : (
                  <p className="text-xs text-[#87928A] italic">No dampened topics recorded yet.</p>
                )}
              </div>
            </div>
          </div>
        )}

        {/* Reset Confirmation Dialog */}
        {isResetModalOpen && (
          <div
            role="dialog"
            aria-modal="true"
            aria-labelledby="reset-modal-title"
            className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-[#18392F]/60 backdrop-blur-sm"
          >
            <div className="w-full max-w-md bg-white rounded-2xl border border-[#E0E6DF] shadow-2xl p-6 space-y-4">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-xl bg-[#FEE2E2] border border-[#FECACA] flex items-center justify-center text-[#B91C1C] shrink-0">
                  <AlertTriangle className="w-5 h-5 text-[#B91C1C]" />
                </div>
                <div>
                  <h3 id="reset-modal-title" className="text-base font-bold text-[#1B2520]">
                    Reset Adaptive Preferences?
                  </h3>
                  <p className="text-xs text-[#647169]">Re-anchoring preference vector to baseline manifesto.</p>
                </div>
              </div>

              <div className="p-3.5 rounded-lg bg-[#F8F9F6] border border-[#E0E6DF] text-xs text-[#647169] space-y-2 leading-relaxed">
                <p>
                  <strong>What happens upon reset:</strong>
                </p>
                <ul className="list-disc list-inside space-y-1">
                  <li>Your learned preference vector is reset to your original manifesto embedding.</li>
                  <li>Drift distance is restored to 0.0000.</li>
                  <li>Learned positive and negative topic frequency counters are cleared.</li>
                  <li>Your historical interaction ledger remains preserved for compliance auditing.</li>
                </ul>
              </div>

              {resetError && (
                <div className="p-3 rounded-lg bg-[#FEE2E2] text-xs text-[#991B1B]">
                  {resetError}
                </div>
              )}

              <div className="flex justify-end gap-3 pt-2">
                <button
                  type="button"
                  onClick={() => setIsResetModalOpen(false)}
                  disabled={isResetting}
                  className="px-4 py-2 min-h-[44px] rounded-lg bg-white border border-[#E0E6DF] text-xs font-semibold text-[#1B2520] hover:bg-[#F8F9F6] transition-colors"
                >
                  Cancel
                </button>
                <button
                  type="button"
                  onClick={handleConfirmReset}
                  disabled={isResetting}
                  className="px-4 py-2 min-h-[44px] rounded-lg bg-[#B91C1C] text-white text-xs font-semibold hover:bg-[#991B1B] transition-colors flex items-center gap-2"
                >
                  {isResetting ? <Loader2 className="w-4 h-4 animate-spin" /> : null}
                  <span>Confirm Reset</span>
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    </AppShell>
  );
}
