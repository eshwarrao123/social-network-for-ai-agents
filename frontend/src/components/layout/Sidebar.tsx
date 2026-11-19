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
  Layers,
  ShieldCheck,
} from "lucide-react";
import { cn } from "@/lib/utils";
import type { AgentProfile } from "@/types";

interface NavItem {
  label: string;
  href: string;
  icon: React.ReactNode;
  enabled: boolean;
  phaseBadge?: string;
}

const NAV_ITEMS: NavItem[] = [
  {
    label: "Dashboard",
    href: "/dashboard",
    icon: <LayoutDashboard className="w-4 h-4" />,
    enabled: true,
  },
  {
    label: "Opportunity Feed",
    href: "/feed",
    icon: <Rss className="w-4 h-4" />,
    enabled: true,
  },
  {
    label: "Inbound Inbox",
    href: "/notifications",
    icon: <Bell className="w-4 h-4" />,
    enabled: false,
    phaseBadge: "P9.3",
  },
  {
    label: "Partner Synergy",
    href: "/partners",
    icon: <Network className="w-4 h-4" />,
    enabled: false,
    phaseBadge: "P9.3",
  },
  {
    label: "Analytics",
    href: "/analytics",
    icon: <BarChart3 className="w-4 h-4" />,
    enabled: false,
    phaseBadge: "P9.3",
  },
  {
    label: "Preferences",
    href: "/preferences",
    icon: <Sliders className="w-4 h-4" />,
    enabled: false,
    phaseBadge: "P9.3",
  },
  {
    label: "Settings & Webhooks",
    href: "/settings",
    icon: <Settings className="w-4 h-4" />,
    enabled: false,
    phaseBadge: "P9.3",
  },
];

interface SidebarProps {
  agent: AgentProfile | null;
  className?: string;
}

export function Sidebar({ agent, className }: SidebarProps) {
  const pathname = usePathname();

  return (
    <aside
      className={cn(
        "hidden md:flex flex-col w-60 h-screen bg-[#18392F] border-r border-[#24493D] select-none shrink-0 text-[#F4F5F1]",
        className
      )}
    >
      {/* Brand Header */}
      <div className="flex items-center gap-3 px-5 py-4 border-b border-[#24493D]">
        <div className="w-8 h-8 rounded-lg bg-white/[0.08] border border-white/[0.12] flex items-center justify-center text-[#B8D5C7] shrink-0">
          <Layers className="w-4 h-4" />
        </div>
        <div className="flex flex-col">
          <span className="text-sm font-semibold tracking-tight text-[#F4F5F1]">
            Agent Network
          </span>
          <span className="text-xs uppercase tracking-wider text-[#A3B5AC] font-mono">
            Control Plane
          </span>
        </div>
      </div>

      {/* Navigation Section */}
      <div className="flex-1 overflow-y-auto px-3 py-4 space-y-1">
        <div className="px-3 pb-2 text-xs font-semibold uppercase tracking-wider text-[#A3B5AC]">
          Workspace
        </div>

        {NAV_ITEMS.map((item) => {
          const isActive = pathname === item.href;

          if (!item.enabled) {
            return (
              <div
                key={item.href}
                className="flex items-center justify-between px-3 py-2 rounded-lg text-xs font-medium text-[#A3B5AC]/60 cursor-not-allowed group relative"
                title={`${item.label} (Scheduled for ${item.phaseBadge})`}
              >
                <div className="flex items-center gap-2.5">
                  <span className="text-[#A3B5AC]/60">{item.icon}</span>
                  <span>{item.label}</span>
                </div>
                {item.phaseBadge && (
                  <span className="text-xs font-mono px-1.5 py-0.5 rounded bg-white/[0.04] text-[#A3B5AC]/80 border border-white/[0.08]">
                    {item.phaseBadge}
                  </span>
                )}
              </div>
            );
          }

          return (
            <Link
              key={item.href}
              href={item.href}
              className={cn(
                "flex items-center justify-between px-3 py-2 rounded-lg text-xs font-medium transition-colors",
                isActive
                  ? "bg-white/[0.08] text-[#F4F5F1] font-semibold"
                  : "text-[#A3B5AC] hover:text-[#F4F5F1] hover:bg-white/[0.05]"
              )}
            >
              <div className="flex items-center gap-2.5">
                <span className={isActive ? "text-[#B8D5C7]" : "text-[#A3B5AC]"}>
                  {item.icon}
                </span>
                <span>{item.label}</span>
              </div>
              {isActive && (
                <span className="w-1.5 h-1.5 rounded-full bg-[#B8D5C7]" />
              )}
            </Link>
          );
        })}
      </div>

      {/* Agent Identity & Status Footer */}
      {agent && (
        <div className="p-3 border-t border-[#24493D] bg-[#143027]">
          <div className="p-2.5 rounded-lg bg-[#18392F] border border-[#24493D] space-y-1.5">
            <div className="flex items-center justify-between gap-2">
              <div className="flex items-center gap-1.5 min-w-0">
                <span className="w-1.5 h-1.5 rounded-full bg-[#B8D5C7] shrink-0" />
                <span className="text-xs font-semibold text-[#F4F5F1] truncate">
                  {agent.name}
                </span>
              </div>
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
        </div>
      )}
    </aside>
  );
}
