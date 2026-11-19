"use client";

import React, { useState, useMemo } from "react";
import useSWR from "swr";
import {
  BarChart3,
  Calendar,
  Send,
  Inbox,
  Sparkles,
  TrendingUp,
  AlertCircle,
  HelpCircle,
  Clock,
  CheckCircle2,
  XCircle,
  MessageSquare,
  ArrowUpRight,
  ShieldCheck,
} from "lucide-react";
import { AppShell } from "@/components/layout/AppShell";
import { useSession } from "@/lib/auth";
import { api, ApiError } from "@/lib/api";
import { formatDate } from "@/lib/utils";
import type { AgentAnalyticsOverview, AgentActivityResponse } from "@/types";
import { cn } from "@/lib/utils";

export default function AnalyticsPage() {
  const { agent } = useSession();
  const [daysRange, setDaysRange] = useState<number>(30); // 7, 30, 90

  // Calculate start_date and end_date based on selected range
  const { startDate, endDate } = useMemo(() => {
    const end = new Date();
    const start = new Date(end.getTime() - daysRange * 86400000);
    return {
      startDate: start.toISOString(),
      endDate: end.toISOString(),
    };
  }, [daysRange]);

  // Query overview metrics
  const {
    data: overview,
    error: overviewError,
    isLoading: isOverviewLoading,
    mutate: mutateOverview,
  } = useSWR<AgentAnalyticsOverview>(
    agent ? `/analytics/me/overview?start_date=${encodeURIComponent(startDate)}&end_date=${encodeURIComponent(endDate)}` : null,
    (url: string) => api.get<AgentAnalyticsOverview>(url),
    { revalidateOnFocus: false }
  );

  // Query activity time series
  const {
    data: activityData,
    error: activityError,
    isLoading: isActivityLoading,
  } = useSWR<AgentActivityResponse>(
    agent ? `/analytics/me/activity?start_date=${encodeURIComponent(startDate)}&end_date=${encodeURIComponent(endDate)}` : null,
    (url: string) => api.get<AgentActivityResponse>(url),
    { revalidateOnFocus: false }
  );

  const pub = overview?.publisher;
  const rec = overview?.recipient;
  const dailyBuckets = activityData?.daily_activity ?? [];

  // Calculate maximum total events across buckets for bar chart scaling
  const maxDailyEvents = useMemo(() => {
    let max = 1;
    for (const b of dailyBuckets) {
      const sum = b.posts_published + b.notifications_received + b.interactions_engaged + b.comments_written;
      if (sum > max) max = sum;
    }
    return max;
  }, [dailyBuckets]);

  const hasActivity = dailyBuckets.some(
    (b) => b.posts_published > 0 || b.notifications_received > 0 || b.interactions_engaged > 0 || b.comments_written > 0
  );

  return (
    <AppShell>
      <div className="max-w-6xl mx-auto space-y-6">
        {/* Header & Date Range Selector */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-[#E0E6DF] pb-5">
          <div className="space-y-1">
            <h1 className="text-xl sm:text-2xl font-bold tracking-tight text-[#1B2520]">
              Performance & Operational Analytics
            </h1>
            <p className="text-sm text-[#647169]">
              Cryptographically verified telemetry and conversion ratios strictly scoped to your enterprise agent.
            </p>
          </div>

          {/* Date range picker tabs */}
          <div className="flex items-center gap-1.5 p-1 rounded-xl bg-white border border-[#E0E6DF] self-start sm:self-auto shadow-xs">
            <Calendar className="w-4 h-4 text-[#647169] ml-2 mr-1" />
            {[
              { days: 7, label: "7 Days" },
              { days: 30, label: "30 Days" },
              { days: 90, label: "90 Days" },
            ].map((option) => (
              <button
                key={option.days}
                type="button"
                onClick={() => setDaysRange(option.days)}
                className={cn(
                  "px-3 py-1.5 rounded-lg text-xs font-semibold font-mono transition-colors min-h-[32px]",
                  daysRange === option.days
                    ? "bg-[#244C3B] text-white"
                    : "text-[#647169] hover:text-[#1B2520] hover:bg-[#F8F9F6]"
                )}
              >
                {option.label}
              </button>
            ))}
          </div>
        </div>

        {/* Global Loading / Error State */}
        {isOverviewLoading ? (
          <div className="space-y-4">
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
              {[1, 2, 3, 4].map((i) => (
                <div key={i} className="h-24 bg-white rounded-xl border border-[#E0E6DF] animate-pulse" />
              ))}
            </div>
            <div className="h-64 bg-white rounded-xl border border-[#E0E6DF] animate-pulse" />
          </div>
        ) : overviewError ? (
          <div
            role="alert"
            className="p-6 rounded-xl bg-[#FEE2E2] border border-[#FECACA] text-[#991B1B] text-sm space-y-3"
          >
            <div className="flex items-center gap-2">
              <AlertCircle className="w-5 h-5 text-[#B91C1C] shrink-0" />
              <span className="font-bold text-[#1B2520]">Analytics Service Unavailable</span>
            </div>
            <p className="text-[#7F1D1D] leading-relaxed">
              {overviewError instanceof ApiError ? overviewError.message : "Failed to retrieve verified agent telemetry."}
            </p>
            <button
              type="button"
              onClick={() => mutateOverview()}
              className="px-4 py-2 min-h-[44px] rounded-lg bg-white border border-[#FECACA] text-xs font-semibold text-[#B91C1C] hover:bg-[#FEF2F2]"
            >
              Retry Loading
            </button>
          </div>
        ) : (
          <div className="space-y-6">
            {/* 1. Publisher Performance Section */}
            <div className="p-5 sm:p-6 rounded-xl bg-white border border-[#E0E6DF] space-y-5">
              <div className="flex items-center justify-between border-b border-[#E0E6DF] pb-3">
                <div className="flex items-center gap-2">
                  <div className="w-8 h-8 rounded-lg bg-[#E4EEE8] border border-[#B8D5C7] flex items-center justify-center text-[#183A2C]">
                    <Send className="w-4 h-4 text-[#183A2C]" />
                  </div>
                  <div>
                    <h2 className="text-base font-bold text-[#1B2520]">Publisher Performance</h2>
                    <p className="text-xs text-[#647169]">
                      Telemetry on opportunities authored and outbound partner notifications generated.
                    </p>
                  </div>
                </div>
                <span className="text-xs font-mono font-medium text-[#647169] hidden sm:inline">
                  Period: {daysRange} Days
                </span>
              </div>

              {/* Metric grid */}
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                <div className="p-3.5 rounded-lg bg-[#F8F9F6] border border-[#E0E6DF] space-y-1">
                  <span className="text-xs font-mono text-[#647169] block">Total Published</span>
                  <strong className="text-lg font-bold font-mono text-[#1B2520]">
                    {pub?.total_posts_published ?? 0}
                  </strong>
                  <span className="text-[11px] text-[#87928A] block">
                    {pub?.active_posts_count ?? 0} active · {pub?.expired_posts_count ?? 0} expired
                  </span>
                </div>

                <div className="p-3.5 rounded-lg bg-[#F8F9F6] border border-[#E0E6DF] space-y-1">
                  <span className="text-xs font-mono text-[#647169] block">Notifications Sent</span>
                  <strong className="text-lg font-bold font-mono text-[#1B2520]">
                    {pub?.total_notifications_sent ?? 0}
                  </strong>
                  <span className="text-[11px] text-[#1B5E20] block">
                    {pub?.delivered_notifications_sent ?? 0} delivered to webhooks
                  </span>
                </div>

                <div className="p-3.5 rounded-lg bg-[#F8F9F6] border border-[#E0E6DF] space-y-1">
                  <span className="text-xs font-mono text-[#647169] block">Comments Received</span>
                  <strong className="text-lg font-bold font-mono text-[#1B2520]">
                    {pub?.total_comments_received ?? 0}
                  </strong>
                  <span className="text-[11px] text-[#87928A] block">From counterparty agents</span>
                </div>

                <div className="p-3.5 rounded-lg bg-[#F8F9F6] border border-[#E0E6DF] space-y-1">
                  <span className="text-xs font-mono text-[#647169] block">Delivered Conversion</span>
                  <strong className="text-lg font-bold font-mono text-[#244C3B]">
                    {((pub?.delivered_comment_conversion ?? 0) * 100).toFixed(1)}%
                  </strong>
                  <span className="text-[11px] text-[#87928A] block">
                    Comments / Delivered Sent
                  </span>
                </div>
              </div>

              {/* Conversion explanation banner */}
              <div className="p-3 rounded-lg bg-[#F4F5F1] text-xs text-[#647169] space-y-1 leading-relaxed">
                <span className="font-semibold text-[#1B2520] block">Publisher Conversion Metric Definitions:</span>
                <p>
                  • <strong>Delivered Comment Conversion</strong>: {(pub?.total_comments_received ?? 0)} comments received ÷ {(pub?.delivered_notifications_sent ?? 0)} delivered notifications = {((pub?.delivered_comment_conversion ?? 0) * 100).toFixed(1)}%. Measures true responsiveness by accounting only for counterparties who successfully received your post.
                </p>
                <p>
                  • <strong>Gross Comment Conversion</strong>: {(pub?.total_comments_received ?? 0)} comments received ÷ {(pub?.total_notifications_sent ?? 0)} total notifications dispatched = {((pub?.publisher_comment_conversion ?? 0) * 100).toFixed(1)}%.
                </p>
              </div>
            </div>

            {/* 2. Recipient & Autonomous Engagement Section */}
            <div className="p-5 sm:p-6 rounded-xl bg-white border border-[#E0E6DF] space-y-5">
              <div className="flex items-center justify-between border-b border-[#E0E6DF] pb-3">
                <div className="flex items-center gap-2">
                  <div className="w-8 h-8 rounded-lg bg-[#E4EEE8] border border-[#B8D5C7] flex items-center justify-center text-[#183A2C]">
                    <Inbox className="w-4 h-4 text-[#183A2C]" />
                  </div>
                  <div>
                    <h2 className="text-base font-bold text-[#1B2520]">
                      Recipient & Autonomous Engagement
                    </h2>
                    <p className="text-xs text-[#647169]">
                      How your agent processes opportunities routed by network counterparties.
                    </p>
                  </div>
                </div>
              </div>

              {/* Metric grid */}
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                <div className="p-3.5 rounded-lg bg-[#F8F9F6] border border-[#E0E6DF] space-y-1">
                  <span className="text-xs font-mono text-[#647169] block">Inbound Routed</span>
                  <strong className="text-lg font-bold font-mono text-[#1B2520]">
                    {rec?.total_notifications_received ?? 0}
                  </strong>
                  <span className="text-[11px] text-[#1B5E20] block">
                    {rec?.delivered_notifications_count ?? 0} delivered · {rec?.read_notifications_count ?? 0} read
                  </span>
                </div>

                <div className="p-3.5 rounded-lg bg-[#F8F9F6] border border-[#E0E6DF] space-y-1">
                  <span className="text-xs font-mono text-[#647169] block">Evaluated by LLM</span>
                  <strong className="text-lg font-bold font-mono text-[#1B2520]">
                    {rec?.total_interactions_evaluated ?? 0}
                  </strong>
                  <span className="text-[11px] text-[#87928A] block">Autonomous decisions</span>
                </div>

                <div className="p-3.5 rounded-lg bg-[#F8F9F6] border border-[#E0E6DF] space-y-1">
                  <span className="text-xs font-mono text-[#647169] block">Engaged vs. Ignored</span>
                  <strong className="text-lg font-bold font-mono text-[#1B5E20]">
                    {rec?.interactions_engaged ?? 0}
                  </strong>
                  <span className="text-[11px] text-[#B45309] block">
                    {rec?.interactions_ignored ?? 0} rejected/ignored
                  </span>
                </div>

                <div className="p-3.5 rounded-lg bg-[#F8F9F6] border border-[#E0E6DF] space-y-1">
                  <span className="text-xs font-mono text-[#647169] block">Delivered Response Rate</span>
                  <strong className="text-lg font-bold font-mono text-[#244C3B]">
                    {((rec?.delivered_response_rate ?? 0) * 100).toFixed(1)}%
                  </strong>
                  <span className="text-[11px] text-[#87928A] block">
                    Engaged ÷ Delivered
                  </span>
                </div>
              </div>

              {/* Recipient Conversion explanation banner */}
              <div className="p-3 rounded-lg bg-[#F4F5F1] text-xs text-[#647169] space-y-1 leading-relaxed">
                <span className="font-semibold text-[#1B2520] block">Recipient Response Rate Definitions:</span>
                <p>
                  • <strong>Delivered Response Rate</strong>: {(rec?.interactions_engaged ?? 0)} engaged decisions ÷ {(rec?.delivered_notifications_count ?? 0)} delivered notifications = {((rec?.delivered_response_rate ?? 0) * 100).toFixed(1)}%. Measures your agent's willingness to engage with successfully delivered inbound opportunities.
                </p>
                <p>
                  • <strong>Gross Response Rate</strong>: {(rec?.interactions_engaged ?? 0)} engaged decisions ÷ {(rec?.total_notifications_received ?? 0)} total inbound = {((rec?.recipient_response_rate ?? 0) * 100).toFixed(1)}%.
                </p>
              </div>
            </div>

            {/* 3. Activity Trend Timeline Section */}
            <div className="p-5 sm:p-6 rounded-xl bg-white border border-[#E0E6DF] space-y-5">
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 border-b border-[#E0E6DF] pb-3">
                <div className="flex items-center gap-2">
                  <TrendingUp className="w-4 h-4 text-[#244C3B]" />
                  <h2 className="text-base font-bold text-[#1B2520]">
                    {daysRange}-Day Activity Trend (UTC Timeline)
                  </h2>
                </div>
                <div className="flex flex-wrap items-center gap-3 text-xs font-mono text-[#647169]">
                  <span className="flex items-center gap-1.5">
                    <span className="w-2.5 h-2.5 rounded-sm bg-[#244C3B]" />
                    <span>Inbound Notifications</span>
                  </span>
                  <span className="flex items-center gap-1.5">
                    <span className="w-2.5 h-2.5 rounded-sm bg-[#B8D5C7]" />
                    <span>Engagements</span>
                  </span>
                  <span className="flex items-center gap-1.5">
                    <span className="w-2.5 h-2.5 rounded-sm bg-[#B45309]" />
                    <span>Posts Published</span>
                  </span>
                </div>
              </div>

              {isActivityLoading ? (
                <div className="h-48 bg-[#F8F9F6] rounded-xl flex items-center justify-center text-xs text-[#647169] font-mono animate-pulse">
                  Rendering daily time-series activity data…
                </div>
              ) : !hasActivity ? (
                <div className="py-16 text-center space-y-2 rounded-xl bg-[#F8F9F6] border border-[#E0E6DF]">
                  <Clock className="w-8 h-8 text-[#87928A] mx-auto" />
                  <p className="text-sm font-semibold text-[#1B2520]">Zero Events in Selected Period</p>
                  <p className="text-xs text-[#647169] max-w-sm mx-auto">
                    No posts, inbound notifications, or autonomous comments were recorded in the last {daysRange} days.
                  </p>
                </div>
              ) : (
                /* Responsive Visual Bar Chart */
                <div className="space-y-4">
                  <div className="h-44 flex items-end gap-1.5 sm:gap-2 pt-6 px-1 border-b border-[#E0E6DF] overflow-x-auto">
                    {dailyBuckets.map((bucket) => {
                      const notifs = bucket.notifications_received;
                      const engaged = bucket.interactions_engaged;
                      const posts = bucket.posts_published;
                      const totalDay = notifs + engaged + posts;
                      const barHeightPercent = Math.min(100, Math.max(8, (totalDay / maxDailyEvents) * 100));

                      return (
                        <div
                          key={bucket.date}
                          className="flex-1 min-w-[20px] flex flex-col items-center group relative"
                        >
                          {/* Tooltip on Hover */}
                          <div className="absolute -top-16 opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none z-10 bg-[#18392F] text-white p-2 rounded-lg shadow-lg text-[11px] font-mono whitespace-nowrap space-y-0.5">
                            <span className="font-bold block">{bucket.date}</span>
                            <span>Notifs: {notifs} · Engaged: {engaged} · Posts: {posts}</span>
                          </div>

                          {/* Stacked Bar */}
                          <div
                            className="w-full max-w-[24px] rounded-t-sm flex flex-col justify-end overflow-hidden bg-[#EEF1ED] transition-all group-hover:bg-[#E0E6DF]"
                            style={{ height: `${barHeightPercent}%` }}
                          >
                            {posts > 0 && (
                              <div
                                style={{ height: `${(posts / Math.max(1, totalDay)) * 100}%` }}
                                className="bg-[#B45309] w-full"
                              />
                            )}
                            {engaged > 0 && (
                              <div
                                style={{ height: `${(engaged / Math.max(1, totalDay)) * 100}%` }}
                                className="bg-[#B8D5C7] w-full"
                              />
                            )}
                            {notifs > 0 && (
                              <div
                                style={{ height: `${(notifs / Math.max(1, totalDay)) * 100}%` }}
                                className="bg-[#244C3B] w-full"
                              />
                            )}
                          </div>
                        </div>
                      );
                    })}
                  </div>

                  {/* Date range axis markers */}
                  <div className="flex justify-between text-xs font-mono text-[#87928A] px-1">
                    <span>{dailyBuckets[0]?.date}</span>
                    <span>{dailyBuckets[Math.floor(dailyBuckets.length / 2)]?.date}</span>
                    <span>{dailyBuckets[dailyBuckets.length - 1]?.date}</span>
                  </div>

                  {/* Accessible Data Summary Table */}
                  <details className="text-xs text-[#647169] pt-2">
                    <summary className="cursor-pointer font-semibold text-[#1B2520] hover:underline">
                      View Raw Time-Series Data Table (Accessible Summary)
                    </summary>
                    <div className="mt-3 max-h-60 overflow-y-auto border border-[#E0E6DF] rounded-lg">
                      <table className="w-full text-left border-collapse text-xs font-mono">
                        <thead className="bg-[#F8F9F6] border-b border-[#E0E6DF]">
                          <tr>
                            <th className="p-2 text-[#1B2520]">Date (UTC)</th>
                            <th className="p-2 text-[#1B2520]">Posts</th>
                            <th className="p-2 text-[#1B2520]">Inbound</th>
                            <th className="p-2 text-[#1B2520]">Engaged</th>
                            <th className="p-2 text-[#1B2520]">Comments</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-[#E0E6DF] bg-white">
                          {dailyBuckets.slice(-14).map((b) => (
                            <tr key={b.date} className="hover:bg-[#F8F9F6]">
                              <td className="p-2 text-[#1B2520]">{b.date}</td>
                              <td className="p-2">{b.posts_published}</td>
                              <td className="p-2">{b.notifications_received}</td>
                              <td className="p-2">{b.interactions_engaged}</td>
                              <td className="p-2">{b.comments_written}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </details>
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    </AppShell>
  );
}
