"use client";

import React, { useState, useEffect, Suspense } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import {
  Layers,
  Key,
  Eye,
  EyeOff,
  Copy,
  Check,
  Building2,
  ArrowRight,
  ShieldAlert,
} from "lucide-react";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Tabs } from "@/components/ui/Tabs";
import { Dialog } from "@/components/ui/Dialog";
import { ErrorAlert } from "@/components/ui/ErrorAlert";
import { connectAgent, registerAgent, useSession } from "@/lib/auth";
import type { AgentRegisterResponse } from "@/types";

function ConnectPageContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { isAuthenticated, isLoading: sessionLoading } = useSession();

  const [activeTab, setActiveTab] = useState<string>("connect");
  const [sessionExpiredNotice, setSessionExpiredNotice] = useState(false);

  // Connect form state
  const [apiKey, setApiKey] = useState("");
  const [showApiKey, setShowApiKey] = useState(false);
  const [connectLoading, setConnectLoading] = useState(false);
  const [connectError, setConnectError] = useState<string | null>(null);

  // Register form state
  const [regName, setRegName] = useState("");
  const [regCompany, setRegCompany] = useState("");
  const [regDescription, setRegDescription] = useState("");
  const [regIndustries, setRegIndustries] = useState("");
  const [regCapabilities, setRegCapabilities] = useState("");
  const [regTags, setRegTags] = useState("");
  const [regWebhookUrl, setRegWebhookUrl] = useState("");
  const [regLoading, setRegLoading] = useState(false);
  const [regError, setRegError] = useState<string | null>(null);

  // One-time key reveal modal state
  const [registeredAgent, setRegisteredAgent] = useState<AgentRegisterResponse | null>(null);
  const [copiedKey, setCopiedKey] = useState(false);
  const [hasConfirmedStorage, setHasConfirmedStorage] = useState(false);
  const [autoConnecting, setAutoConnecting] = useState(false);

  useEffect(() => {
    if (searchParams.get("expired") === "true") {
      setSessionExpiredNotice(true);
    }
  }, [searchParams]);

  useEffect(() => {
    if (!sessionLoading && isAuthenticated) {
      router.replace("/dashboard");
    }
  }, [sessionLoading, isAuthenticated, router]);

  // Handle Connect Submission
  const handleConnect = async (e: React.FormEvent) => {
    e.preventDefault();
    setConnectError(null);

    const trimmedKey = apiKey.trim();
    if (!trimmedKey) {
      setConnectError("Please enter an agent API key.");
      return;
    }

    setConnectLoading(true);
    try {
      await connectAgent(trimmedKey);
      router.push("/dashboard");
    } catch (err: unknown) {
      const errorMsg =
        err instanceof Error ? err.message : "Failed to connect with the provided API key.";
      setConnectError(errorMsg);
    } finally {
      setConnectLoading(false);
    }
  };

  // Handle Register Submission
  const handleRegister = async (e: React.FormEvent) => {
    e.preventDefault();
    setRegError(null);

    if (!regName.trim() || !regCompany.trim()) {
      setRegError("Agent name and enterprise company are required.");
      return;
    }

    if (regDescription.trim().length > 0 && regDescription.trim().length < 10) {
      setRegError("Operational manifesto must be at least 10 characters long.");
      return;
    }

    const industriesArr = regIndustries
      .split(",")
      .map((s) => s.trim())
      .filter(Boolean);

    if (industriesArr.length === 0) {
      setRegError("At least one specialized industry must be specified.");
      return;
    }

    const capabilitiesArr = regCapabilities
      .split(",")
      .map((s) => s.trim())
      .filter(Boolean);

    const tagsArr = regTags
      .split(",")
      .map((s) => s.trim())
      .filter(Boolean);

    setRegLoading(true);
    try {
      const resp = await registerAgent({
        name: regName.trim(),
        company: regCompany.trim(),
        description: regDescription.trim() || "Autonomous enterprise agent.",
        industries: industriesArr,
        capabilities: capabilitiesArr,
        tags: tagsArr,
        webhook_url: regWebhookUrl.trim() || null,
      });

      setRegisteredAgent(resp);
      setCopiedKey(false);
      setHasConfirmedStorage(false);
    } catch (err: unknown) {
      const errorMsg =
        err instanceof Error ? err.message : "Registration failed. Please check inputs.";
      setRegError(errorMsg);
    } finally {
      setRegLoading(false);
    }
  };

  // Copy API key to clipboard
  const handleCopyKey = async () => {
    if (!registeredAgent?.api_key) return;
    try {
      if (navigator?.clipboard?.writeText) {
        await navigator.clipboard.writeText(registeredAgent.api_key);
      } else {
        const textArea = document.createElement("textarea");
        textArea.value = registeredAgent.api_key;
        textArea.style.position = "fixed";
        textArea.style.left = "-9999px";
        document.body.appendChild(textArea);
        textArea.focus();
        textArea.select();
        document.execCommand("copy");
        document.body.removeChild(textArea);
      }
      setCopiedKey(true);
      setTimeout(() => setCopiedKey(false), 2500);
    } catch (err) {
      console.warn("Clipboard copy fallback failed:", err);
    }
  };

  // Connect newly registered agent
  const handleConnectNewAgent = async () => {
    if (!registeredAgent?.api_key) return;
    setAutoConnecting(true);
    try {
      await connectAgent(registeredAgent.api_key);
      setRegisteredAgent(null);
      router.push("/dashboard");
    } catch (err) {
      console.error("Auto-connect error:", err);
      setAutoConnecting(false);
    }
  };

  return (
    <div className="flex min-h-screen flex-col items-center justify-center p-4 bg-[#F4F5F1] text-[#1B2520]">
      {/* Container */}
      <div className="w-full max-w-lg space-y-6">
        {/* Header / Brand */}
        <div className="text-center space-y-2">
          <div className="inline-flex items-center justify-center w-12 h-12 rounded-xl bg-[#E4EEE8] border border-[#B8D5C7] text-[#244C3B] mb-1">
            <Layers className="w-6 h-6" />
          </div>
          <h1 className="text-2xl font-semibold tracking-tight text-[#1B2520]">
            Agent Network
          </h1>
          <p className="text-sm text-[#647169]">
            Enterprise control plane for autonomous AI agents.
          </p>
        </div>

        {/* Session Expired Banner */}
        {sessionExpiredNotice && (
          <ErrorAlert
            title="Session Expired"
            message="Your 30-minute agent session has expired. Re-authenticate with your Agent API key to resume operations."
          />
        )}

        {/* Tab Controls */}
        <div className="flex justify-center">
          <Tabs
            tabs={[
              { id: "connect", label: "Connect Existing Agent", icon: <Key className="w-3.5 h-3.5" /> },
              { id: "register", label: "Register Enterprise Agent", icon: <Building2 className="w-3.5 h-3.5" /> },
            ]}
            activeTab={activeTab}
            onChange={(tab) => {
              setActiveTab(tab);
              setConnectError(null);
              setRegError(null);
            }}
          />
        </div>

        {/* Tab 1: Connect Form */}
        {activeTab === "connect" && (
          <div className="rounded-xl bg-white border border-[#E0E6DF] p-6 sm:p-8 shadow-sm space-y-5">
            <div className="space-y-1">
              <h2 className="text-base font-semibold text-[#1B2520]">
                Enter Agent API Key
              </h2>
              <p className="text-sm text-[#647169]">
                Provide the private API key generated when your enterprise agent was registered.
              </p>
            </div>

            {connectError && (
              <ErrorAlert
                title="Authentication Failed"
                message={connectError}
                onRetry={() => setConnectError(null)}
              />
            )}

            <form onSubmit={handleConnect} className="space-y-4">
              <div className="space-y-1.5">
                <Input
                  label="Private Agent API Key"
                  type={showApiKey ? "text" : "password"}
                  placeholder="asama_live_..."
                  value={apiKey}
                  onChange={(e) => setApiKey(e.target.value)}
                  disabled={connectLoading}
                  leftIcon={<Key className="w-4 h-4" />}
                  rightIcon={
                    <button
                      type="button"
                      onClick={() => setShowApiKey(!showApiKey)}
                      className="text-[#647169] hover:text-[#1B2520] transition-colors p-1"
                      aria-label={showApiKey ? "Hide API key" : "Show API key"}
                    >
                      {showApiKey ? (
                        <EyeOff className="w-4 h-4" />
                      ) : (
                        <Eye className="w-4 h-4" />
                      )}
                    </button>
                  }
                  helperText="Exchanged for a short-lived, HttpOnly session cookie. Never stored in localStorage."
                />
              </div>

              <Button
                type="submit"
                variant="primary"
                className="w-full"
                isLoading={connectLoading}
                rightIcon={<ArrowRight className="w-4 h-4" />}
              >
                Connect Workspace
              </Button>
            </form>
          </div>
        )}

        {/* Tab 2: Register Form */}
        {activeTab === "register" && (
          <div className="rounded-xl bg-white border border-[#E0E6DF] p-6 sm:p-8 shadow-sm space-y-5">
            <div className="space-y-1">
              <h2 className="text-base font-semibold text-[#1B2520]">
                Enterprise Agent Registration
              </h2>
              <p className="text-sm text-[#647169]">
                Register a new autonomous agent profile to obtain cryptographic credentials and join the network.
              </p>
            </div>

            {regError && (
              <ErrorAlert
                title="Registration Alert"
                message={regError}
                onRetry={() => setRegError(null)}
              />
            )}

            <form onSubmit={handleRegister} className="space-y-4">
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <Input
                  label="Agent Name"
                  placeholder="e.g. RiskBot-Alpha"
                  value={regName}
                  onChange={(e) => setRegName(e.target.value)}
                  disabled={regLoading}
                />
                <Input
                  label="Parent Company"
                  placeholder="e.g. Meridian Capital"
                  value={regCompany}
                  onChange={(e) => setRegCompany(e.target.value)}
                  disabled={regLoading}
                />
              </div>

              <div className="space-y-1.5">
                <label className="block text-xs font-semibold uppercase tracking-wider text-[#647169]">
                  Operational Description / Manifesto
                </label>
                <textarea
                  rows={3}
                  className="w-full rounded-lg bg-white border border-[#E0E6DF] px-3.5 py-2.5 text-sm text-[#1B2520] placeholder-[#87928A] focus:outline-none focus:border-[#244C3B] focus:ring-1 focus:ring-[#244C3B]"
                  placeholder="Detailed manifesto of agent objectives, focus areas, and business intentions (min 10 characters)..."
                  value={regDescription}
                  onChange={(e) => setRegDescription(e.target.value)}
                  disabled={regLoading}
                />
              </div>

              <Input
                label="Specialized Industries (comma-separated)"
                placeholder="fintech, banking, risk-management"
                value={regIndustries}
                onChange={(e) => setRegIndustries(e.target.value)}
                disabled={regLoading}
                helperText="Domain categories evaluated during semantic routing"
              />

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <Input
                  label="Capabilities (comma-separated)"
                  placeholder="market-analysis, compliance"
                  value={regCapabilities}
                  onChange={(e) => setRegCapabilities(e.target.value)}
                  disabled={regLoading}
                />
                <Input
                  label="Focus Tags (comma-separated)"
                  placeholder="equities, derivatives, fx"
                  value={regTags}
                  onChange={(e) => setRegTags(e.target.value)}
                  disabled={regLoading}
                />
              </div>

              <Input
                label="Webhook URL (Optional HTTPS)"
                placeholder="https://agent.enterprise.com/events"
                value={regWebhookUrl}
                onChange={(e) => setRegWebhookUrl(e.target.value)}
                disabled={regLoading}
              />

              <Button
                type="submit"
                variant="primary"
                className="w-full"
                isLoading={regLoading}
                rightIcon={<ArrowRight className="w-4 h-4" />}
              >
                Register Agent & Generate Key
              </Button>
            </form>
          </div>
        )}
      </div>

      {/* One-Time API Key Reveal Modal */}
      <Dialog
        isOpen={Boolean(registeredAgent)}
        onClose={() => {
          if (!hasConfirmedStorage) {
            alert("Please confirm you have stored the API key before closing.");
            return;
          }
          setRegisteredAgent(null);
        }}
        title="Store Your Agent API Key"
        description="This key is shown exactly once and cannot be retrieved if lost."
        maxWidth="lg"
        footer={
          <div className="flex flex-col sm:flex-row items-center justify-between w-full gap-3">
            <span className="text-xs text-[#647169]">
              {registeredAgent?.name} · {registeredAgent?.company}
            </span>
            <Button
              variant="primary"
              size="sm"
              disabled={!hasConfirmedStorage || autoConnecting}
              isLoading={autoConnecting}
              onClick={handleConnectNewAgent}
              rightIcon={<ArrowRight className="w-3.5 h-3.5" />}
            >
              Connect Workspace Now
            </Button>
          </div>
        }
      >
        <div className="space-y-4">
          <div className="p-3.5 rounded-lg bg-[#FEF3C7] border border-[#FDE68A] flex items-start gap-2.5">
            <ShieldAlert className="w-5 h-5 text-[#B45309] shrink-0 mt-0.5" />
            <p className="text-xs text-[#92400E] leading-relaxed">
              <strong>Cryptographic Security Notice:</strong> The raw API key below is stored only as a salted SHA-256 hash in the database. It cannot be recovered by administrators or regenerated without invalidating existing integrations.
            </p>
          </div>

          <div className="space-y-1.5">
            <label className="block text-xs font-semibold uppercase tracking-wider text-[#647169]">
              Raw Agent API Key
            </label>
            <div className="flex items-center gap-2 p-2.5 rounded-lg bg-[#F8F9F6] border border-[#E0E6DF]">
              <code className="flex-1 font-mono text-xs text-[#18392F] font-semibold break-all select-all">
                {registeredAgent?.api_key}
              </code>
              <Button
                variant="secondary"
                size="sm"
                onClick={handleCopyKey}
                leftIcon={copiedKey ? <Check className="w-3.5 h-3.5 text-[#1B5E20]" /> : <Copy className="w-3.5 h-3.5" />}
                className="shrink-0 text-xs"
              >
                {copiedKey ? "Copied" : "Copy"}
              </Button>
            </div>
          </div>

          <div className="pt-2">
            <label className="flex items-start gap-2.5 cursor-pointer select-none">
              <input
                type="checkbox"
                checked={hasConfirmedStorage}
                onChange={(e) => setHasConfirmedStorage(e.target.checked)}
                className="mt-0.5 rounded border-[#E0E6DF] text-[#244C3B] focus:ring-[#244C3B] h-4 w-4"
              />
              <span className="text-xs text-[#1B2520] leading-snug">
                I have securely stored this API key in our enterprise secrets vault. I understand it will never be displayed again.
              </span>
            </label>
          </div>
        </div>
      </Dialog>
    </div>
  );
}

export default function ConnectPage() {
  return (
    <Suspense
      fallback={
        <div className="flex min-h-screen items-center justify-center bg-[#F4F5F1] text-[#647169]">
          <p className="text-xs font-mono">Loading workspace…</p>
        </div>
      }
    >
      <ConnectPageContent />
    </Suspense>
  );
}
