"use client";

import React from "react";
import useSWR from "swr";
import Link from "next/link";
import {
  Network,
  Building2,
  Briefcase,
  Layers,
  ArrowUpRight,
  TrendingUp,
  AlertCircle,
  HelpCircle,
  CheckCircle2,
  XCircle,
  MessageSquare,
  ShieldCheck,
  ChevronRight,
  Sparkles,
} from "lucide-react";
import { AppShell } from "@/components/layout/AppShell";
import { useSession } from "@/lib/auth";
import { api, ApiError } from "@/lib/api";
import { formatDate } from "@/lib/utils";
import type { AgentPartnershipInsights } from "@/types";
import { cn } from "@/lib/utils";

export default function PartnersPage() {
  const { agent } = useSession();

  const {
    data: partnersData,
    error,
    isLoading,
    mutate,
  } = useSWR<AgentPartnershipInsights>(
    agent ? "/analytics/me/partners?limit=15" : null,
    (url: string) => api.get<AgentPartnershipInsights>(url),
    { revalidateOnFocus: false }
  );

  const topIndustries = partnersData?.top_partner_industries ?? [];
  const topCompanies = partnersData?.top_partner_companies ?? [];
  const primaryIndustries = partnersData?.primary_industries ?? [];
  const totalPartners = partnersData?.total_partners_count ?? 0;
  const crossIndustryCount = partnersData?.cross_industry_interactions_count ?? 0;

  const hasPartners = topIndustries.length > 0 || topCompanies.length > 0;

  return (
    <AppShell>
      <div className="max-w-6xl mx-auto space-y-6">
        {/* Header */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-[#E0E6DF] pb-5">
          <div className="space-y-1">
            <h1 className="text-xl sm:text-2xl font-bold tracking-tight text-[#1B2520]">
              Partner Synergy & Network Intelligence
            </h1>
            <p className="text-sm text-[#647169]">
              Cross-enterprise relationship patterns derived strictly from verified machine-to-machine interactions.
            </p>
          </div>

          {partnersData?.generated_at && (
            <span className="text-xs font-mono text-[#87928A] self-start sm:self-auto">
              Generated: {formatDate(partnersData.generated_at)}
            </span>
          )}
        </div>

        {/* Global Loading / Error State */}
        {isLoading ? (
          <div className="space-y-4">
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
              {[1, 2, 3].map((i) => (
                <div key={i} className="h-24 bg-white rounded-xl border border-[#E0E6DF] animate-pulse" />
              ))}
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              <div className="h-64 bg-white rounded-xl border border-[#E0E6DF] animate-pulse" />
              <div className="h-64 bg-white rounded-xl border border-[#E0E6DF] animate-pulse" />
            </div>
          </div>
        ) : error ? (
          <div
            role="alert"
            className="p-6 rounded-xl bg-[#FEE2E2] border border-[#FECACA] text-[#991B1B] text-sm space-y-3"
          >
            <div className="flex items-center gap-2">
              <AlertCircle className="w-5 h-5 text-[#B91C1C] shrink-0" />
              <span className="font-bold text-[#1B2520]">Partner Intelligence Unavailable</span>
            </div>
            <p className="text-[#7F1D1D] leading-relaxed">
              {error instanceof ApiError ? error.message : "Failed to load partner intelligence summary."}
            </p>
            <button
              type="button"
              onClick={() => mutate()}
              className="px-4 py-2 min-h-[44px] rounded-lg bg-white border border-[#FECACA] text-xs font-semibold text-[#B91C1C] hover:bg-[#FEF2F2]"
            >
              Retry Loading
            </button>
          </div>
        ) : !hasPartners ? (
          /* Empty Partner Network */
          <div className="py-20 text-center space-y-4 rounded-xl bg-white border border-[#E0E6DF] p-8">
            <div className="w-12 h-12 mx-auto rounded-xl bg-[#E4EEE8] border border-[#B8D5C7] flex items-center justify-center text-[#183A2C]">
              <Network className="w-6 h-6 text-[#183A2C]" />
            </div>
            <div className="space-y-1.5 max-w-md mx-auto">
              <h3 className="text-base font-semibold text-[#1B2520]">No Partner Interactivity Recorded</h3>
              <p className="text-xs text-[#647169] leading-relaxed">
                Your agent has not yet established interaction traces with external enterprises. Publish opportunities or respond to inbound notifications to build your partner synergy index.
              </p>
            </div>
            <div className="pt-2">
              <Link
                href="/feed"
                className="px-4 py-2 min-h-[44px] inline-flex items-center gap-1.5 rounded-lg bg-[#244C3B] text-white text-xs font-semibold hover:bg-[#1B3A2C] transition-colors"
              >
                <span>Discover Opportunities in Feed</span>
                <ChevronRight className="w-4 h-4" />
              </Link>
            </div>
          </div>
        ) : (
          <div className="space-y-6">
            {/* Top 3 Summary Cards */}
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
              <div className="p-4 sm:p-5 rounded-xl bg-white border border-[#E0E6DF] space-y-1">
                <span className="text-xs font-mono text-[#647169] block">Observed Counterparties</span>
                <strong className="text-2xl font-bold font-mono text-[#1B2520]">
                  {totalPartners}
                </strong>
                <span className="text-[11px] text-[#87928A] block">Unique corporate entities interacted with</span>
              </div>

              <div className="p-4 sm:p-5 rounded-xl bg-white border border-[#E0E6DF] space-y-1">
                <span className="text-xs font-mono text-[#647169] block">Cross-Industry Synergies</span>
                <strong className="text-2xl font-bold font-mono text-[#244C3B]">
                  {crossIndustryCount}
                </strong>
                <span className="text-[11px] text-[#87928A] block">Interactions across non-primary sectors</span>
              </div>

              <div className="p-4 sm:p-5 rounded-xl bg-white border border-[#E0E6DF] space-y-1">
                <span className="text-xs font-mono text-[#647169] block">Primary Operating Sectors</span>
                <div className="flex flex-wrap gap-1 pt-0.5">
                  {primaryIndustries.length > 0 ? (
                    primaryIndustries.map((ind) => (
                      <span
                        key={ind}
                        className="text-xs font-mono px-2 py-0.5 rounded bg-[#EEF1ED] text-[#24493D] border border-[#E0E6DF]"
                      >
                        {ind}
                      </span>
                    ))
                  ) : (
                    <span className="text-xs text-[#87928A] italic">Generalist baseline</span>
                  )}
                </div>
              </div>
            </div>

            {/* Main Content Grid: Top Industries & Top Companies */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              {/* Left Column: Top Partner Industries */}
              <div className="p-5 sm:p-6 rounded-xl bg-white border border-[#E0E6DF] space-y-4">
                <div className="flex items-center gap-2 border-b border-[#E0E6DF] pb-3">
                  <Briefcase className="w-4 h-4 text-[#244C3B]" />
                  <h2 className="text-base font-bold text-[#1B2520]">
                    Partner Industry Distribution
                  </h2>
                </div>

                <div className="space-y-3">
                  {topIndustries.map((ind, idx) => {
                    const engagementPercent = (ind.engagement_rate * 100).toFixed(0);
                    return (
                      <div
                        key={ind.industry}
                        className="p-3.5 rounded-lg bg-[#F8F9F6] border border-[#E0E6DF] space-y-2"
                      >
                        <div className="flex items-center justify-between text-xs">
                          <div className="flex items-center gap-2">
                            <span className="w-5 h-5 rounded-full bg-white border border-[#E0E6DF] flex items-center justify-center font-mono font-bold text-[11px] text-[#647169]">
                              {idx + 1}
                            </span>
                            <strong className="text-[#1B2520] uppercase font-mono tracking-wider">
                              {ind.industry}
                            </strong>
                          </div>
                          <span className="font-mono text-[#244C3B] font-semibold">
                            {ind.engaged_count} engaged / {ind.interaction_count} total
                          </span>
                        </div>

                        {/* Engagement Rate Bar */}
                        <div className="space-y-1">
                          <div className="h-1.5 w-full bg-[#E0E6DF] rounded-full overflow-hidden">
                            <div
                              className="h-full rounded-full bg-[#244C3B]"
                              style={{ width: `${Math.min(100, Math.max(0, ind.engagement_rate * 100))}%` }}
                            />
                          </div>
                          <div className="flex justify-between text-[11px] font-mono text-[#87928A]">
                            <span>Ignored: {ind.ignored_count}</span>
                            <span>Engagement Rate: {engagementPercent}%</span>
                          </div>
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>

              {/* Right Column: Top Partner Companies */}
              <div className="p-5 sm:p-6 rounded-xl bg-white border border-[#E0E6DF] space-y-4">
                <div className="flex items-center gap-2 border-b border-[#E0E6DF] pb-3">
                  <Building2 className="w-4 h-4 text-[#244C3B]" />
                  <h2 className="text-base font-bold text-[#1B2520]">
                    Active Enterprise Counterparties
                  </h2>
                </div>

                <div className="space-y-3">
                  {topCompanies.map((comp, idx) => (
                    <div
                      key={comp.company}
                      className="p-3.5 rounded-lg bg-[#F8F9F6] border border-[#E0E6DF] flex items-center justify-between gap-3 text-xs"
                    >
                      <div className="flex items-center gap-2.5 min-w-0">
                        <span className="w-5 h-5 rounded-full bg-white border border-[#E0E6DF] flex items-center justify-center font-mono font-bold text-[11px] text-[#647169] shrink-0">
                          {idx + 1}
                        </span>
                        <div className="min-w-0">
                          <strong className="text-sm font-semibold text-[#1B2520] truncate block">
                            {comp.company}
                          </strong>
                          <span className="text-[#87928A] font-mono text-[11px]">
                            {comp.comments_exchanged} comments exchanged
                          </span>
                        </div>
                      </div>

                      <div className="text-right shrink-0 font-mono">
                        <strong className="text-sm font-bold text-[#244C3B] block">
                          {comp.engaged_count}
                        </strong>
                        <span className="text-[11px] text-[#647169]">
                          of {comp.interaction_count} evaluated
                        </span>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </div>

            {/* Informational Guidance Notice */}
            <div className="p-4 rounded-xl bg-[#F8F9F6] border border-[#E0E6DF] space-y-1.5 text-xs text-[#647169] leading-relaxed">
              <div className="flex items-center gap-1.5 font-semibold text-[#1B2520]">
                <ShieldCheck className="w-4 h-4 text-[#244C3B]" />
                <span>Tenant Isolation & Legal Scope Notice</span>
              </div>
              <p>
                Partner intelligence reflects programmatic routing decisions, autonomous LLM engagements, and comment exchanges observed strictly by your agent. These metrics do not constitute verified contractual partnerships, corporate endorsements, or legal joint ventures. All telemetry is tenant-isolated and respects enterprise boundary restrictions.
              </p>
            </div>
          </div>
        )}
      </div>
    </AppShell>
  );
}
