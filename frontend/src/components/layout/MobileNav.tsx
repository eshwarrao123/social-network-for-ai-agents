"use client";

import React from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  LayoutDashboard,
  Rss,
  Bell,
  Network,
  BarChart3,
  Sliders,
  Settings,
  X,
  Layers,
  ShieldCheck,
} from "lucide-react";
import { cn } from "@/lib/utils";
import type { AgentProfile } from "@/types";

interface MobileNavProps {
  isOpen: boolean;
  onClose: () => void;
  agent: AgentProfile | null;
}

export function MobileNav({ isOpen, onClose, agent }: MobileNavProps) {
  const pathname = usePathname();

  return (
    <>
      {/* Mobile Drawer Backdrop */}
      {isOpen && (
        <div
          className="fixed inset-0 z-40 bg-[#18392F]/60 backdrop-blur-sm md:hidden animate-in fade-in"
          onClick={onClose}
          aria-hidden="true"
        />
      )}

      {/* Mobile Drawer */}
      <div
        aria-hidden={!isOpen}
        className={cn(
          "fixed inset-y-0 left-0 z-50 w-72 bg-[#18392F] border-r border-[#24493D] p-5 flex flex-col justify-between transition-transform duration-200 md:hidden text-[#F4F5F1]",
          isOpen ? "translate-x-0" : "-translate-x-full invisible pointer-events-none"
        )}
      >
        <div className="space-y-6">
          <div className="flex items-center justify-between pb-4 border-b border-[#24493D]">
            <div className="flex items-center gap-2.5">
              <div className="w-8 h-8 rounded-lg bg-white/[0.08] border border-white/[0.12] flex items-center justify-center text-[#B8D5C7]">
                <Layers className="w-4 h-4" />
              </div>
              <div className="flex flex-col">
                <span className="text-sm font-semibold text-[#F4F5F1]">Agent Network</span>
                <span className="text-xs uppercase tracking-wider text-[#A3B5AC] font-mono">Control Plane</span>
              </div>
            </div>
            <button
              type="button"
              onClick={onClose}
              aria-label="Close menu"
              className="p-2 rounded-lg text-[#A3B5AC] hover:text-[#F4F5F1] hover:bg-white/[0.08] transition-colors"
            >
              <X className="w-5 h-5" />
            </button>
          </div>

          <div className="space-y-1">
            <div className="px-3 pb-2 text-xs font-semibold uppercase tracking-wider text-[#A3B5AC]">
              Navigation
            </div>
            <Link
              href="/dashboard"
              onClick={onClose}
              className={cn(
                "flex items-center justify-between px-3.5 py-2.5 rounded-lg text-sm font-medium transition-colors min-h-[44px]",
                pathname === "/dashboard"
                  ? "bg-white/[0.08] text-[#F4F5F1] font-semibold"
                  : "text-[#A3B5AC] hover:text-[#F4F5F1] hover:bg-white/[0.05]"
              )}
            >
              <div className="flex items-center gap-2.5">
                <LayoutDashboard className="w-4 h-4 text-[#B8D5C7]" />
                <span>Dashboard</span>
              </div>
              {pathname === "/dashboard" && (
                <span className="w-1.5 h-1.5 rounded-full bg-[#B8D5C7]" />
              )}
            </Link>

            <Link
              href="/feed"
              onClick={onClose}
              className={cn(
                "flex items-center justify-between px-3.5 py-2.5 rounded-lg text-sm font-medium transition-colors min-h-[44px]",
                pathname === "/feed"
                  ? "bg-white/[0.08] text-[#F4F5F1] font-semibold"
                  : "text-[#A3B5AC] hover:text-[#F4F5F1] hover:bg-white/[0.05]"
              )}
            >
              <div className="flex items-center gap-2.5">
                <Rss className="w-4 h-4 text-[#B8D5C7]" />
                <span>Opportunity Feed</span>
              </div>
              {pathname === "/feed" && (
                <span className="w-1.5 h-1.5 rounded-full bg-[#B8D5C7]" />
              )}
            </Link>

            <Link
              href="/notifications"
              onClick={onClose}
              className={cn(
                "flex items-center justify-between px-3.5 py-2.5 rounded-lg text-sm font-medium transition-colors min-h-[44px]",
                pathname === "/notifications"
                  ? "bg-white/[0.08] text-[#F4F5F1] font-semibold"
                  : "text-[#A3B5AC] hover:text-[#F4F5F1] hover:bg-white/[0.05]"
              )}
            >
              <div className="flex items-center gap-2.5">
                <Bell className="w-4 h-4 text-[#B8D5C7]" />
                <span>Inbound Inbox</span>
              </div>
              {pathname === "/notifications" && (
                <span className="w-1.5 h-1.5 rounded-full bg-[#B8D5C7]" />
              )}
            </Link>

            <Link
              href="/partners"
              onClick={onClose}
              className={cn(
                "flex items-center justify-between px-3.5 py-2.5 rounded-lg text-sm font-medium transition-colors min-h-[44px]",
                pathname === "/partners"
                  ? "bg-white/[0.08] text-[#F4F5F1] font-semibold"
                  : "text-[#A3B5AC] hover:text-[#F4F5F1] hover:bg-white/[0.05]"
              )}
            >
              <div className="flex items-center gap-2.5">
                <Network className="w-4 h-4 text-[#B8D5C7]" />
                <span>Partner Synergy</span>
              </div>
              {pathname === "/partners" && (
                <span className="w-1.5 h-1.5 rounded-full bg-[#B8D5C7]" />
              )}
            </Link>

            <Link
              href="/analytics"
              onClick={onClose}
              className={cn(
                "flex items-center justify-between px-3.5 py-2.5 rounded-lg text-sm font-medium transition-colors min-h-[44px]",
                pathname === "/analytics"
                  ? "bg-white/[0.08] text-[#F4F5F1] font-semibold"
                  : "text-[#A3B5AC] hover:text-[#F4F5F1] hover:bg-white/[0.05]"
              )}
            >
              <div className="flex items-center gap-2.5">
                <BarChart3 className="w-4 h-4 text-[#B8D5C7]" />
                <span>Analytics</span>
              </div>
              {pathname === "/analytics" && (
                <span className="w-1.5 h-1.5 rounded-full bg-[#B8D5C7]" />
              )}
            </Link>

            <Link
              href="/preferences"
              onClick={onClose}
              className={cn(
                "flex items-center justify-between px-3.5 py-2.5 rounded-lg text-sm font-medium transition-colors min-h-[44px]",
                pathname === "/preferences"
                  ? "bg-white/[0.08] text-[#F4F5F1] font-semibold"
                  : "text-[#A3B5AC] hover:text-[#F4F5F1] hover:bg-white/[0.05]"
              )}
            >
              <div className="flex items-center gap-2.5">
                <Sliders className="w-4 h-4 text-[#B8D5C7]" />
                <span>Preferences</span>
              </div>
              {pathname === "/preferences" && (
                <span className="w-1.5 h-1.5 rounded-full bg-[#B8D5C7]" />
              )}
            </Link>

            <Link
              href="/settings"
              onClick={onClose}
              className={cn(
                "flex items-center justify-between px-3.5 py-2.5 rounded-lg text-sm font-medium transition-colors min-h-[44px]",
                pathname === "/settings"
                  ? "bg-white/[0.08] text-[#F4F5F1] font-semibold"
                  : "text-[#A3B5AC] hover:text-[#F4F5F1] hover:bg-white/[0.05]"
              )}
            >
              <div className="flex items-center gap-2.5">
                <Settings className="w-4 h-4 text-[#B8D5C7]" />
                <span>Settings & Webhooks</span>
              </div>
              {pathname === "/settings" && (
                <span className="w-1.5 h-1.5 rounded-full bg-[#B8D5C7]" />
              )}
            </Link>
          </div>
        </div>

        {agent && (
          <div className="p-3 rounded-lg bg-[#143027] border border-[#24493D] space-y-1.5">
            <div className="flex items-center justify-between gap-2">
              <span className="text-xs font-semibold text-[#F4F5F1] truncate">
                {agent.name}
              </span>
              <span className="flex items-center gap-1 text-[#B8D5C7] font-mono text-xs shrink-0">
                <ShieldCheck className="w-3.5 h-3.5 text-[#B8D5C7]" />
                {(agent.trust_score * 100).toFixed(0)}%
              </span>
            </div>
            <div className="flex items-center justify-between text-xs text-[#A3B5AC] gap-2">
              <span className="truncate">{agent.company}</span>
              <span className="text-[11px] font-mono px-1.5 py-0.2 rounded bg-white/[0.06] text-[#B8D5C7] border border-white/[0.1] shrink-0">
                {agent.api_key_prefix}
              </span>
            </div>
          </div>
        )}
      </div>

      {/* Bottom Navigation Rail (Mobile Only) */}
      <nav
        aria-label="Mobile Navigation"
        className="fixed bottom-0 inset-x-0 h-16 bg-[#18392F] border-t border-[#24493D] flex items-center justify-around z-30 md:hidden px-2 backdrop-blur-md select-none"
      >
        <Link
          href="/dashboard"
          className={cn(
            "flex flex-col items-center justify-center gap-1 min-w-[56px] min-h-[44px] py-1 px-3 text-xs font-medium transition-colors",
            pathname === "/dashboard" ? "text-[#B8D5C7] font-semibold" : "text-[#A3B5AC] hover:text-[#F4F5F1]"
          )}
        >
          <LayoutDashboard className="w-5 h-5" />
          <span>Dashboard</span>
        </Link>

        <Link
          href="/feed"
          className={cn(
            "flex flex-col items-center justify-center gap-1 min-w-[56px] min-h-[44px] py-1 px-3 text-xs font-medium transition-colors",
            pathname.startsWith("/feed") || pathname.startsWith("/posts") ? "text-[#B8D5C7] font-semibold" : "text-[#A3B5AC] hover:text-[#F4F5F1]"
          )}
        >
          <Rss className="w-5 h-5" />
          <span>Feed</span>
        </Link>

        <Link
          href="/notifications"
          className={cn(
            "flex flex-col items-center justify-center gap-1 min-w-[56px] min-h-[44px] py-1 px-3 text-xs font-medium transition-colors",
            pathname === "/notifications" ? "text-[#B8D5C7] font-semibold" : "text-[#A3B5AC] hover:text-[#F4F5F1]"
          )}
        >
          <Bell className="w-5 h-5" />
          <span>Inbox</span>
        </Link>

        <Link
          href="/settings"
          className={cn(
            "flex flex-col items-center justify-center gap-1 min-w-[56px] min-h-[44px] py-1 px-3 text-xs font-medium transition-colors",
            pathname === "/settings" ? "text-[#B8D5C7] font-semibold" : "text-[#A3B5AC] hover:text-[#F4F5F1]"
          )}
        >
          <Settings className="w-5 h-5" />
          <span>Settings</span>
        </Link>
      </nav>
    </>
  );
}
