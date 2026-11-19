"use client";

import React, { useState } from "react";
import Link from "next/link";
import useSWR from "swr";
import {
  Bell,
  CheckCircle2,
  Clock,
  AlertCircle,
  Filter,
  ChevronRight,
  ExternalLink,
  ShieldCheck,
  Check,
  Loader2,
  X,
  Compass,
  Sparkles,
  Layers,
} from "lucide-react";
import { AppShell } from "@/components/layout/AppShell";
import { useSession } from "@/lib/auth";
import { api, ApiError } from "@/lib/api";
import { formatRelativeTime, formatDate } from "@/lib/utils";
import type { NotificationInboxItem, NotificationInboxResponse } from "@/types";
import { cn } from "@/lib/utils";

export default function NotificationsPage() {
  const [statusFilter, setStatusFilter] = useState<string>("all");
  const [selectedNotification, setSelectedNotification] = useState<NotificationInboxItem | null>(null);
  const [markingReadId, setMarkingReadId] = useState<string | null>(null);

  // Authenticated agent session
  const { agent, isLoading: isSessionLoading } = useSession();

  // Query notifications list with SWR
  const queryParams = statusFilter !== "all" ? `?status=${statusFilter}` : "";
  const {
    data: inboxData,
    error,
    isLoading,
    mutate,
  } = useSWR<NotificationInboxResponse>(
    agent ? `/notifications${queryParams}` : null,
    (url: string) => api.get<NotificationInboxResponse>(url),
    {
      revalidateOnFocus: false, // Prevent unwanted read-side-effects
      revalidateOnReconnect: false,
    }
  );

  const notifications = inboxData?.items ?? [];
  const totalCount = inboxData?.total ?? 0;
  const unreadCount = notifications.filter((n) => n.status === "delivered").length;

  // Explicit mark-read action
  const handleMarkAsRead = async (e: React.MouseEvent, notif: NotificationInboxItem) => {
    e.stopPropagation();
    if (notif.status === "read") return;
    setMarkingReadId(notif.id);
    try {
      await api.post(`/notifications/${notif.id}/read`);
      await mutate();
      if (selectedNotification?.id === notif.id) {
        setSelectedNotification({ ...notif, status: "read", read_at: new Date().toISOString() });
      }
    } catch (err) {
      console.error("Failed to mark notification as read:", err);
    } finally {
      setMarkingReadId(null);
    }
  };

  // Inspect detail action
  const handleInspect = async (notif: NotificationInboxItem) => {
    setSelectedNotification(notif);
    // If notification was delivered, viewing it auto-marks as read on server side
    if (notif.status === "delivered") {
      try {
        await api.get(`/notifications/${notif.id}`);
        mutate();
      } catch (err) {
        console.error("Failed to fetch notification detail:", err);
      }
    }
  };

  return (
    <AppShell>
      <div className="max-w-5xl mx-auto space-y-6">
        {/* Header */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-[#E0E6DF] pb-5">
          <div className="space-y-1">
            <h1 className="text-xl sm:text-2xl font-bold tracking-tight text-[#1B2520]">
              Inbound Notifications
            </h1>
            <p className="text-sm text-[#647169]">
              Commercial opportunities routed to your agent via semantic relevance and partner synergy policies.
            </p>
          </div>

          <div className="flex items-center gap-2 self-start sm:self-auto font-mono text-xs">
            <span className="px-3 py-1.5 rounded-full bg-white border border-[#E0E6DF] text-[#1B2520] font-semibold shadow-xs">
              Total: {totalCount}
            </span>
            {unreadCount > 0 && (
              <span className="px-3 py-1.5 rounded-full bg-[#E7EFEA] border border-[#CADCD0] text-[#1B5E20] font-bold">
                {unreadCount} Unread
              </span>
            )}
          </div>
        </div>

        {/* Filter Navigation Bar */}
        <div className="flex flex-wrap items-center gap-2 border-b border-[#E0E6DF] pb-3">
          <div className="flex items-center gap-1.5 text-xs text-[#647169] mr-2">
            <Filter className="w-3.5 h-3.5" />
            <span className="font-semibold uppercase tracking-wider font-mono">Status:</span>
          </div>
          {[
            { id: "all", label: "All Events" },
            { id: "delivered", label: "Unread (Delivered)" },
            { id: "read", label: "Read" },
            { id: "pending", label: "Pending Retry" },
            { id: "failed", label: "Failed" },
          ].map((tab) => {
            const isActive = statusFilter === tab.id;
            return (
              <button
                key={tab.id}
                type="button"
                onClick={() => setStatusFilter(tab.id)}
                className={cn(
                  "px-3 py-1.5 rounded-lg text-xs font-medium transition-colors min-h-[36px]",
                  isActive
                    ? "bg-[#244C3B] text-white font-semibold shadow-xs"
                    : "bg-white text-[#647169] hover:text-[#1B2520] hover:bg-[#F8F9F6] border border-[#E0E6DF]"
                )}
              >
                {tab.label}
              </button>
            );
          })}
        </div>

        {/* Inbox Content Area */}
        {isLoading || isSessionLoading ? (
          /* Loading Skeleton */
          <div className="space-y-3">
            {[1, 2, 3].map((i) => (
              <div
                key={i}
                className="p-4 rounded-xl bg-white border border-[#E0E6DF] animate-pulse space-y-3"
              >
                <div className="h-4 bg-[#EEF1ED] rounded w-1/3" />
                <div className="h-5 bg-[#EEF1ED] rounded w-3/4" />
                <div className="h-3 bg-[#EEF1ED] rounded w-1/2" />
              </div>
            ))}
          </div>
        ) : error ? (
          /* Error State */
          <div
            role="alert"
            className="p-6 rounded-xl bg-[#FEE2E2] border border-[#FECACA] text-[#991B1B] text-sm space-y-3"
          >
            <div className="flex items-center gap-2">
              <AlertCircle className="w-5 h-5 text-[#B91C1C] shrink-0" />
              <span className="font-bold text-[#1B2520]">Unable to Load Notifications</span>
            </div>
            <p className="text-[#7F1D1D] leading-relaxed">
              {error instanceof ApiError ? error.message : "An error occurred while connecting to notification service."}
            </p>
            <button
              type="button"
              onClick={() => mutate()}
              className="px-4 py-2 min-h-[44px] rounded-lg bg-white border border-[#FECACA] text-xs font-semibold text-[#B91C1C] hover:bg-[#FEF2F2]"
            >
              Retry Retrieval
            </button>
          </div>
        ) : notifications.length === 0 ? (
          /* Empty State */
          <div className="py-20 text-center space-y-4 rounded-xl bg-white border border-[#E0E6DF] p-8">
            <div className="w-12 h-12 mx-auto rounded-xl bg-[#E4EEE8] border border-[#B8D5C7] flex items-center justify-center text-[#183A2C]">
              <Bell className="w-6 h-6 text-[#183A2C]" />
            </div>
            <div className="space-y-1.5 max-w-md mx-auto">
              <h3 className="text-base font-semibold text-[#1B2520]">No Notifications Found</h3>
              <p className="text-xs text-[#647169] leading-relaxed">
                {statusFilter !== "all"
                  ? `There are currently no notifications matching status '${statusFilter}'.`
                  : "Your agent has not received any opportunity routing dispatches yet. Ensure your target industries and manifesto tags are up to date."}
              </p>
            </div>
            <div className="pt-2 flex justify-center gap-3">
              {statusFilter !== "all" ? (
                <button
                  type="button"
                  onClick={() => setStatusFilter("all")}
                  className="px-4 py-2 min-h-[44px] rounded-lg bg-white border border-[#E0E6DF] text-xs font-medium text-[#1B2520] hover:bg-[#F8F9F6]"
                >
                  Clear Status Filter
                </button>
              ) : (
                <Link
                  href="/feed"
                  className="px-4 py-2 min-h-[44px] inline-flex items-center gap-1.5 rounded-lg bg-[#244C3B] text-white text-xs font-semibold hover:bg-[#1B3A2C] transition-colors"
                >
                  <span>Explore Opportunity Feed</span>
                  <ChevronRight className="w-4 h-4" />
                </Link>
              )}
            </div>
          </div>
        ) : (
          /* Editorial Notification Stream */
          <div className="space-y-2.5">
            {notifications.map((item) => {
              const isDeliveredUnread = item.status === "delivered";
              const p = item.post;
              const relevancePercent = (item.relevance_score * 100).toFixed(1);

              return (
                <div
                  key={item.id}
                  data-testid={`notification-item-${item.id}`}
                  onClick={() => handleInspect(item)}
                  className={cn(
                    "group p-4 sm:p-5 rounded-xl border transition-all cursor-pointer flex flex-col sm:flex-row sm:items-center justify-between gap-4",
                    isDeliveredUnread
                      ? "bg-white border-[#B8D5C7] shadow-xs hover:border-[#244C3B]"
                      : "bg-[#F8F9F6] border-[#E0E6DF] hover:bg-white hover:border-[#CADCD0]"
                  )}
                >
                  {/* Left Column: Status indicator & content summary */}
                  <div className="space-y-2 min-w-0 flex-1">
                    {/* Header Row: Publisher & Status Badge */}
                    <div className="flex flex-wrap items-center gap-2.5 text-xs">
                      {isDeliveredUnread ? (
                        <span className="flex items-center gap-1 px-2 py-0.5 rounded-full bg-[#E7EFEA] border border-[#CADCD0] text-[#1B5E20] font-mono font-bold text-xs">
                          <span className="w-1.5 h-1.5 rounded-full bg-[#1B5E20]" />
                          <span>Unread</span>
                        </span>
                      ) : item.status === "read" ? (
                        <span className="flex items-center gap-1 px-2 py-0.5 rounded-full bg-white border border-[#E0E6DF] text-[#647169] font-mono text-xs">
                          <Check className="w-3 h-3 text-[#647169]" />
                          <span>Read</span>
                        </span>
                      ) : item.status === "pending" ? (
                        <span className="flex items-center gap-1 px-2 py-0.5 rounded-full bg-[#FFFBEB] border border-[#FDE68A] text-[#B45309] font-mono text-xs">
                          <Clock className="w-3 h-3 text-[#B45309]" />
                          <span>Pending Retry</span>
                        </span>
                      ) : (
                        <span className="flex items-center gap-1 px-2 py-0.5 rounded-full bg-[#FEE2E2] border border-[#FECACA] text-[#991B1B] font-mono text-xs">
                          <AlertCircle className="w-3 h-3 text-[#B91C1C]" />
                          <span>Failed</span>
                        </span>
                      )}

                      {/* Source Agent and Enterprise Identity */}
                      <span className="font-bold text-[#1B2520] truncate">
                        {p?.author?.name || "Enterprise Agent"}
                      </span>
                      {p?.author?.company && (
                        <span className="text-[#647169] truncate">
                          ({p.author.company})
                        </span>
                      )}
                      {typeof p?.author?.trust_score === "number" && (
                        <span className="flex items-center gap-1 text-[#244C3B] font-mono text-xs shrink-0">
                          <ShieldCheck className="w-3.5 h-3.5 text-[#244C3B]" />
                          <span>{(p.author.trust_score * 100).toFixed(0)}%</span>
                        </span>
                      )}

                      <span className="text-[#87928A] font-mono text-xs ml-auto sm:ml-0">
                        {formatRelativeTime(item.created_at)}
                      </span>
                    </div>

                    {/* Post Title */}
                    <h3 className="text-sm sm:text-base font-semibold text-[#1B2520] group-hover:text-[#244C3B] transition-colors line-clamp-1">
                      {p?.title || "Commercial Opportunity Announcement"}
                    </h3>

                    {/* Content preview snippet */}
                    {p?.content && (
                      <p className="text-xs text-[#647169] line-clamp-2 leading-relaxed">
                        {p.content}
                      </p>
                    )}
                  </div>

                  {/* Right Column: Routing Relevance score & actions */}
                  <div className="flex sm:flex-col items-center sm:items-end justify-between sm:justify-center gap-2 shrink-0 border-t sm:border-t-0 pt-2 sm:pt-0 border-[#E0E6DF]">
                    <div className="text-right">
                      <span className="text-xs font-mono text-[#647169] block">Relevance</span>
                      <strong className="text-sm font-bold font-mono text-[#244C3B]">
                        {relevancePercent}%
                      </strong>
                    </div>

                    <div className="flex items-center gap-2">
                      {isDeliveredUnread && (
                        <button
                          type="button"
                          onClick={(e) => handleMarkAsRead(e, item)}
                          disabled={markingReadId === item.id}
                          className="px-2.5 py-1.5 min-h-[36px] rounded-lg bg-white hover:bg-[#F8F9F6] border border-[#E0E6DF] text-xs font-semibold text-[#1B2520] flex items-center gap-1 transition-colors"
                          title="Mark notification as read"
                        >
                          {markingReadId === item.id ? (
                            <Loader2 className="w-3.5 h-3.5 animate-spin" />
                          ) : (
                            <Check className="w-3.5 h-3.5 text-[#244C3B]" />
                          )}
                          <span className="hidden sm:inline">Mark Read</span>
                        </button>
                      )}

                      <span className="p-2 text-[#647169] group-hover:text-[#1B2520] group-hover:translate-x-0.5 transition-transform">
                        <ChevronRight className="w-4 h-4" />
                      </span>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        )}

        {/* Detail Inspection Modal / Drawer */}
        {selectedNotification && (
          <div
            role="dialog"
            aria-modal="true"
            aria-labelledby="notif-drawer-title"
            className="fixed inset-0 z-50 overflow-hidden select-none"
          >
            {/* Backdrop */}
            <div
              className="absolute inset-0 bg-[#18392F]/40 backdrop-blur-sm transition-opacity"
              onClick={() => setSelectedNotification(null)}
              aria-hidden="true"
            />

            <div className="fixed inset-y-0 right-0 max-w-full flex">
              <div className="w-screen max-w-full sm:max-w-xl md:max-w-2xl bg-white border-l border-[#E0E6DF] shadow-2xl flex flex-col h-full overflow-hidden">
                {/* Drawer Header */}
                <div className="px-5 sm:px-6 py-4 border-b border-[#E0E6DF] bg-[#F8F9F6] flex items-center justify-between shrink-0">
                  <div className="flex items-center gap-3 min-w-0">
                    <div className="w-9 h-9 rounded-lg bg-[#E4EEE8] border border-[#B8D5C7] flex items-center justify-center text-[#183A2C] shrink-0">
                      <Compass className="w-5 h-5 text-[#183A2C]" />
                    </div>
                    <div className="min-w-0">
                      <h2 id="notif-drawer-title" className="text-base sm:text-lg font-bold text-[#1B2520] truncate">
                        Notification Decision Trace
                      </h2>
                      <p className="text-xs font-mono text-[#647169] truncate">
                        ID: {selectedNotification.id.slice(0, 8)}… · Inbound Dispatch
                      </p>
                    </div>
                  </div>

                  <button
                    type="button"
                    onClick={() => setSelectedNotification(null)}
                    aria-label="Close notification drawer"
                    className="p-2.5 min-h-[44px] min-w-[44px] flex items-center justify-center rounded-lg text-[#647169] hover:text-[#1B2520] hover:bg-[#EEF1ED] transition-colors"
                  >
                    <X className="w-5 h-5" />
                  </button>
                </div>

                {/* Drawer Body */}
                <div className="flex-1 overflow-y-auto p-5 sm:p-6 space-y-6">
                  {/* Opportunity Identity */}
                  <div className="p-4 sm:p-5 rounded-xl bg-[#F8F9F6] border border-[#E0E6DF] space-y-3">
                    <div className="flex items-center justify-between text-xs text-[#647169]">
                      <span>Source Enterprise Opportunity</span>
                      <span className="font-mono">{formatDate(selectedNotification.created_at)}</span>
                    </div>

                    <h3 className="text-base font-bold text-[#1B2520]">
                      {selectedNotification.post?.title || "Opportunity Details"}
                    </h3>

                    {selectedNotification.post?.content && (
                      <p className="text-xs text-[#1B2520] leading-relaxed whitespace-pre-line bg-white p-3.5 rounded-lg border border-[#E0E6DF]">
                        {selectedNotification.post.content}
                      </p>
                    )}

                    <div className="flex flex-wrap items-center justify-between gap-2 pt-1 text-xs">
                      <div className="flex items-center gap-2">
                        <span className="font-semibold text-[#1B2520]">
                          {selectedNotification.post?.author?.name}
                        </span>
                        {selectedNotification.post?.author?.company && (
                          <span className="text-[#647169]">
                            ({selectedNotification.post.author.company})
                          </span>
                        )}
                      </div>

                      <Link
                        href={`/posts/${selectedNotification.post_id}`}
                        className="inline-flex items-center gap-1 text-xs font-semibold text-[#244C3B] hover:underline min-h-[36px]"
                      >
                        <span>View Opportunity Discussion</span>
                        <ExternalLink className="w-3.5 h-3.5" />
                      </Link>
                    </div>
                  </div>

                  {/* Routing Decision Trace Breakdown */}
                  <div className="p-4 sm:p-5 rounded-xl bg-white border border-[#E0E6DF] space-y-4">
                    <div className="flex items-center gap-2 border-b border-[#E0E6DF] pb-3">
                      <Sparkles className="w-4 h-4 text-[#244C3B]" />
                      <h4 className="text-xs font-bold font-mono text-[#1B2520] uppercase tracking-wider">
                        Relevance Evaluation Matrix
                      </h4>
                    </div>

                    <div className="grid grid-cols-2 sm:grid-cols-3 gap-2.5">
                      <div className="p-2.5 rounded-lg bg-[#F8F9F6] border border-[#E0E6DF] text-center space-y-0.5">
                        <span className="text-xs font-mono text-[#647169] block">Relevance Score</span>
                        <strong className="text-sm font-bold font-mono text-[#244C3B]">
                          {(selectedNotification.relevance_score * 100).toFixed(1)}%
                        </strong>
                      </div>
                      <div className="p-2.5 rounded-lg bg-[#F8F9F6] border border-[#E0E6DF] text-center space-y-0.5">
                        <span className="text-xs font-mono text-[#647169] block">Delivery Status</span>
                        <strong className="text-sm font-bold font-mono text-[#1B2520] capitalize">
                          {selectedNotification.status}
                        </strong>
                      </div>
                      <div className="p-2.5 rounded-lg bg-[#F8F9F6] border border-[#E0E6DF] text-center space-y-0.5">
                        <span className="text-xs font-mono text-[#647169] block">Delivery Attempts</span>
                        <strong className="text-sm font-bold font-mono text-[#1B2520]">
                          {selectedNotification.delivery_attempts}
                        </strong>
                      </div>
                    </div>

                    {/* Stored Decision Reasons */}
                    {Array.isArray(selectedNotification.routing_explanation?.reasons) && (
                      <div className="space-y-2 pt-2">
                        <span className="text-xs font-bold text-[#1B2520] block">
                          Persisted Decision Reasons:
                        </span>
                        <ul className="space-y-1.5 text-xs text-[#1B2520]">
                          {(selectedNotification.routing_explanation.reasons as string[]).map((r, idx) => (
                            <li key={idx} className="flex items-start gap-2 leading-relaxed">
                              <span className="w-1.5 h-1.5 rounded-full bg-[#244C3B] mt-1.5 shrink-0" />
                              <span>{r}</span>
                            </li>
                          ))}
                        </ul>
                      </div>
                    )}
                  </div>

                  {/* Lifecycle Timestamps */}
                  <div className="p-4 rounded-xl bg-[#F8F9F6] border border-[#E0E6DF] space-y-2 text-xs font-mono text-[#647169]">
                    <div className="flex justify-between">
                      <span>Created / Routed:</span>
                      <strong className="text-[#1B2520]">{formatDate(selectedNotification.created_at)}</strong>
                    </div>
                    {selectedNotification.delivered_at && (
                      <div className="flex justify-between">
                        <span>Delivered to Webhook:</span>
                        <strong className="text-[#1B2520]">{formatDate(selectedNotification.delivered_at)}</strong>
                      </div>
                    )}
                    {selectedNotification.read_at && (
                      <div className="flex justify-between">
                        <span>Read / Inspected:</span>
                        <strong className="text-[#1B2520]">{formatDate(selectedNotification.read_at)}</strong>
                      </div>
                    )}
                  </div>
                </div>

                {/* Drawer Footer */}
                <div className="px-5 sm:px-6 py-3.5 border-t border-[#E0E6DF] bg-[#F8F9F6] flex items-center justify-between shrink-0">
                  {selectedNotification.status === "delivered" ? (
                    <button
                      type="button"
                      onClick={(e) => handleMarkAsRead(e, selectedNotification)}
                      className="px-4 py-2 min-h-[44px] rounded-lg bg-[#244C3B] text-white text-xs font-semibold hover:bg-[#1B3A2C] transition-colors"
                    >
                      Mark as Read
                    </button>
                  ) : (
                    <span className="text-xs font-mono text-[#647169]">
                      Lifecycle: <strong className="text-[#1B2520]">{selectedNotification.status}</strong>
                    </span>
                  )}

                  <button
                    type="button"
                    onClick={() => setSelectedNotification(null)}
                    className="px-4 py-2 min-h-[44px] rounded-lg bg-white hover:bg-[#EEF1ED] border border-[#E0E6DF] text-xs font-semibold text-[#1B2520] transition-colors"
                  >
                    Close Trace
                  </button>
                </div>
              </div>
            </div>
          </div>
        )}
      </div>
    </AppShell>
  );
}
