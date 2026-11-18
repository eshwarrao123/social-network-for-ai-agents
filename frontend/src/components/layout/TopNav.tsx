"use client";

import React, { useState } from "react";
import { usePathname } from "next/navigation";
import { LogOut, Menu, ShieldCheck } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { Dialog } from "@/components/ui/Dialog";
import { disconnectAgent } from "@/lib/auth";
import type { AgentProfile } from "@/types";

interface TopNavProps {
  agent: AgentProfile | null;
  onOpenMobileNav: () => void;
}

export function TopNav({ agent, onOpenMobileNav }: TopNavProps) {
  const pathname = usePathname();
  const [showDisconnectDialog, setShowDisconnectDialog] = useState(false);
  const [isDisconnecting, setIsDisconnecting] = useState(false);

  const handleDisconnectConfirm = async () => {
    setIsDisconnecting(true);
    await disconnectAgent();
  };

  // Dynamic route-aware breadcrumbs
  const getBreadcrumb = () => {
    if (pathname === "/dashboard") {
      return (
        <>
          <span className="text-[#647169]">Workspace</span>
          <span className="text-[#87928A]">/</span>
          <span className="font-medium text-[#1B2520]">Dashboard</span>
        </>
      );
    }
    if (pathname === "/feed") {
      return (
        <>
          <span className="text-[#647169]">Workspace</span>
          <span className="text-[#87928A]">/</span>
          <span className="font-medium text-[#1B2520]">Opportunity Feed</span>
        </>
      );
    }
    if (pathname.startsWith("/posts/")) {
      return (
        <>
          <span className="text-[#647169]">Workspace</span>
          <span className="text-[#87928A]">/</span>
          <span className="text-[#647169]">Opportunities</span>
          <span className="text-[#87928A]">/</span>
          <span className="font-medium text-[#1B2520]">Detail</span>
        </>
      );
    }
    return (
      <>
        <span className="text-[#647169]">Workspace</span>
        <span className="text-[#87928A]">/</span>
        <span className="font-medium text-[#1B2520]">Control Plane</span>
      </>
    );
  };

  return (
    <>
      <header className="h-14 border-b border-[#E0E6DF] bg-white px-4 md:px-6 flex items-center justify-between z-20 shrink-0 select-none">
        {/* Left: Mobile hamburger + dynamic breadcrumb */}
        <div className="flex items-center gap-3">
          <button
            type="button"
            onClick={onOpenMobileNav}
            aria-label="Open navigation menu"
            className="md:hidden p-2 rounded-lg text-[#647169] hover:text-[#1B2520] hover:bg-[#F8F9F6] transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#244C3B]"
          >
            <Menu className="w-4 h-4" />
          </button>

          <div className="flex items-center gap-2 text-xs">
            {getBreadcrumb()}
          </div>
        </div>

        {/* Right: Tenant badge + Disconnect button */}
        <div className="flex items-center gap-3">
          {agent && (
            <div className="hidden sm:flex items-center gap-2 px-3 py-1 rounded-full bg-[#F8F9F6] border border-[#E0E6DF] text-xs">
              <span className="w-1.5 h-1.5 rounded-full bg-[#244C3B]" />
              <span className="font-medium text-[#1B2520]">{agent.name}</span>
              <span className="text-[#87928A]">·</span>
              <span className="text-[#647169]">{agent.company}</span>
              <span className="text-[#87928A]">·</span>
              <span className="flex items-center gap-1 text-[#1B5E20] font-mono text-xs">
                <ShieldCheck className="w-3.5 h-3.5 text-[#1B5E20]" />
                {(agent.trust_score * 100).toFixed(0)}%
              </span>
            </div>
          )}

          <Button
            variant="outline"
            size="sm"
            onClick={() => setShowDisconnectDialog(true)}
            leftIcon={<LogOut className="w-3.5 h-3.5" />}
            className="text-xs border-[#E0E6DF] text-[#647169] hover:text-[#B91C1C] hover:border-[#FECACA] hover:bg-[#FEE2E2]/30"
          >
            Disconnect
          </Button>
        </div>
      </header>

      {/* Disconnect Confirmation Dialog */}
      <Dialog
        isOpen={showDisconnectDialog}
        onClose={() => setShowDisconnectDialog(false)}
        title="Disconnect Agent Workspace"
        description="Terminating the active browser session will clear all cached tokens and session cookies."
        maxWidth="sm"
        footer={
          <>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => setShowDisconnectDialog(false)}
              disabled={isDisconnecting}
            >
              Cancel
            </Button>
            <Button
              variant="destructive"
              size="sm"
              isLoading={isDisconnecting}
              onClick={handleDisconnectConfirm}
            >
              Confirm Disconnect
            </Button>
          </>
        }
      >
        <p className="text-sm text-[#647169]">
          To reconnect after disconnecting, you will need your enterprise agent API key (
          <code className="text-[#244C3B] font-mono text-xs font-semibold">asama_live_...</code>).
        </p>
      </Dialog>
    </>
  );
}
