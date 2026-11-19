"use client";

import React, { useState, useEffect } from "react";
import useSWR from "swr";
import {
  Settings,
  ShieldCheck,
  Building,
  FileText,
  Tag,
  Cpu,
  Layers,
  Webhook,
  Plus,
  RotateCcw,
  Trash2,
  Check,
  Copy,
  AlertTriangle,
  CheckCircle2,
  Loader2,
  X,
  ExternalLink,
  Lock,
  Globe,
  Radio,
  Clock,
  Key,
} from "lucide-react";
import { AppShell } from "@/components/layout/AppShell";
import { useSession } from "@/lib/auth";
import { api, ApiError } from "@/lib/api";
import { formatDate } from "@/lib/utils";
import type {
  AgentProfile,
  AgentProfileUpdateRequest,
  WebhookSubscription,
  WebhookSubscriptionCreatedResponse,
  WebhookSecretRotatedResponse,
  CreateWebhookRequest,
} from "@/types";
import { cn } from "@/lib/utils";

export default function SettingsPage() {
  const { agent, mutate: refreshSession } = useSession();

  // Active Tab
  const [activeTab, setActiveTab] = useState<"profile" | "webhooks">("profile");

  // Profile Form State
  const [company, setCompany] = useState("");
  const [description, setDescription] = useState("");
  const [industries, setIndustries] = useState<string[]>([]);
  const [newIndustry, setNewIndustry] = useState("");
  const [capabilities, setCapabilities] = useState<string[]>([]);
  const [newCapability, setNewCapability] = useState("");
  const [tags, setTags] = useState<string[]>([]);
  const [newTag, setNewTag] = useState("");

  const [isSavingProfile, setIsSavingProfile] = useState(false);
  const [profileSuccess, setProfileSuccess] = useState<string | null>(null);
  const [profileError, setProfileError] = useState<string | null>(null);

  // Sync profile when session loads
  useEffect(() => {
    if (agent) {
      setCompany(agent.company || "");
      setDescription(agent.description || "");
      setIndustries(agent.industries || []);
      setCapabilities(agent.capabilities || []);
      setTags(agent.tags || []);
    }
  }, [agent]);

  // Webhooks SWR
  const {
    data: webhooks,
    error: webhooksError,
    isLoading: isLoadingWebhooks,
    mutate: mutateWebhooks,
  } = useSWR<WebhookSubscription[]>(
    agent ? "/webhooks" : null,
    (url: string) => api.get<WebhookSubscription[]>(url),
    { revalidateOnFocus: false }
  );

  // Webhook Modals & Action States
  const [isRegisterModalOpen, setIsRegisterModalOpen] = useState(false);
  const [newEndpointUrl, setNewEndpointUrl] = useState("");
  const [selectedEventTypes, setSelectedEventTypes] = useState<string[]>(["new_notification"]);
  const [newIsActive, setNewIsActive] = useState(true);
  const [registerError, setRegisterError] = useState<string | null>(null);
  const [isRegistering, setIsRegistering] = useState(false);

  // One-time Secret Modal State
  const [revealedSecret, setRevealedSecret] = useState<string | null>(null);
  const [secretModalTitle, setSecretModalTitle] = useState("");
  const [secretCopied, setSecretCopied] = useState(false);

  // Confirmation Modals
  const [rotateTarget, setRotateTarget] = useState<WebhookSubscription | null>(null);
  const [isRotating, setIsRotating] = useState(false);

  const [deleteTarget, setDeleteTarget] = useState<WebhookSubscription | null>(null);
  const [isDeleting, setIsDeleting] = useState(false);

  // Handle Add/Remove Array Items for Profile
  const handleAddIndustry = (e: React.KeyboardEvent | React.MouseEvent) => {
    if ("key" in e && e.key !== "Enter") return;
    e.preventDefault();
    const val = newIndustry.trim().toLowerCase();
    if (val && !industries.includes(val) && industries.length < 10) {
      setIndustries([...industries, val]);
      setNewIndustry("");
    }
  };

  const handleRemoveIndustry = (item: string) => {
    if (industries.length > 1) {
      setIndustries(industries.filter((i) => i !== item));
    }
  };

  const handleAddCapability = (e: React.KeyboardEvent | React.MouseEvent) => {
    if ("key" in e && e.key !== "Enter") return;
    e.preventDefault();
    const val = newCapability.trim().toLowerCase();
    if (val && !capabilities.includes(val) && capabilities.length < 20) {
      setCapabilities([...capabilities, val]);
      setNewCapability("");
    }
  };

  const handleRemoveCapability = (item: string) => {
    setCapabilities(capabilities.filter((c) => c !== item));
  };

  const handleAddTag = (e: React.KeyboardEvent | React.MouseEvent) => {
    if ("key" in e && e.key !== "Enter") return;
    e.preventDefault();
    const val = newTag.trim().toLowerCase();
    if (val && !tags.includes(val) && tags.length < 20) {
      setTags([...tags, val]);
      setNewTag("");
    }
  };

  const handleRemoveTag = (item: string) => {
    setTags(tags.filter((t) => t !== item));
  };

  // Save Profile Handler
  const handleSaveProfile = async (e: React.FormEvent) => {
    e.preventDefault();
    setProfileError(null);
    setProfileSuccess(null);
    setIsSavingProfile(true);

    if (company.trim().length < 2) {
      setProfileError("Company name must be at least 2 characters.");
      setIsSavingProfile(false);
      return;
    }
    if (description.trim().length < 10) {
      setProfileError("Description manifesto must be at least 10 characters.");
      setIsSavingProfile(false);
      return;
    }
    if (industries.length === 0) {
      setProfileError("At least one industry category is required.");
      setIsSavingProfile(false);
      return;
    }

    try {
      const payload: AgentProfileUpdateRequest = {
        company: company.trim(),
        description: description.trim(),
        industries,
        capabilities,
        tags,
      };

      await api.patch<AgentProfile>("/agents/me", payload);
      await refreshSession();
      setProfileSuccess("Agent profile and taxonomy updated successfully.");
      setTimeout(() => setProfileSuccess(null), 5000);
    } catch (err) {
      if (err instanceof ApiError) {
        setProfileError(err.message || "Failed to update profile.");
      } else {
        setProfileError("An unexpected error occurred while saving profile.");
      }
    } finally {
      setIsSavingProfile(false);
    }
  };

  // Register Webhook Handler
  const handleRegisterWebhook = async (e: React.FormEvent) => {
    e.preventDefault();
    setRegisterError(null);

    const url = newEndpointUrl.trim();
    if (!url.startsWith("https://")) {
      setRegisterError("Webhook endpoint URL must start with https://");
      return;
    }
    if (selectedEventTypes.length === 0) {
      setRegisterError("Select at least one event type.");
      return;
    }

    setIsRegistering(true);
    try {
      const payload: CreateWebhookRequest = {
        endpoint_url: url,
        event_types: selectedEventTypes,
        is_active: newIsActive,
      };

      const res = await api.post<WebhookSubscriptionCreatedResponse>("/webhooks", payload);
      await mutateWebhooks();
      setIsRegisterModalOpen(false);
      setNewEndpointUrl("");

      // Reveal secret once
      setSecretModalTitle("Webhook Endpoint Registered");
      setRevealedSecret(res.secret);
      setSecretCopied(false);
    } catch (err) {
      if (err instanceof ApiError) {
        setRegisterError(err.message || "Failed to register webhook.");
      } else {
        setRegisterError("Failed to register webhook endpoint.");
      }
    } finally {
      setIsRegistering(false);
    }
  };

  // Toggle Webhook Active State
  const handleToggleWebhook = async (sub: WebhookSubscription) => {
    try {
      const updated = await api.patch<WebhookSubscription>(`/webhooks/${sub.id}`, {
        is_active: !sub.is_active,
      });
      mutateWebhooks(
        (prev) => prev?.map((w) => (w.id === sub.id ? updated : w)),
        false
      );
    } catch (err) {
      console.error("Failed to toggle webhook", err);
    }
  };

  // Rotate Secret Handler
  const handleConfirmRotate = async () => {
    if (!rotateTarget) return;
    setIsRotating(true);
    try {
      const res = await api.post<WebhookSecretRotatedResponse>(
        `/webhooks/${rotateTarget.id}/rotate-secret`
      );
      setRotateTarget(null);
      setSecretModalTitle("HMAC Secret Rotated");
      setRevealedSecret(res.secret);
      setSecretCopied(false);
      await mutateWebhooks();
    } catch (err) {
      console.error("Failed to rotate secret", err);
    } finally {
      setIsRotating(false);
    }
  };

  // Delete Webhook Handler
  const handleConfirmDelete = async () => {
    if (!deleteTarget) return;
    setIsDeleting(true);
    try {
      await api.del(`/webhooks/${deleteTarget.id}`);
      setDeleteTarget(null);
      mutateWebhooks(
        (prev) => prev?.filter((w) => w.id !== deleteTarget.id),
        false
      );
    } catch (err) {
      console.error("Failed to delete webhook", err);
    } finally {
      setIsDeleting(false);
    }
  };

  const copyToClipboard = (text: string) => {
    navigator.clipboard.writeText(text);
    setSecretCopied(true);
    setTimeout(() => setSecretCopied(false), 3000);
  };

  return (
    <AppShell>
      <div className="max-w-6xl mx-auto space-y-8 pb-16">
        {/* Header */}
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 pb-6 border-b border-[#E0E6DF]">
          <div>
            <div className="flex items-center gap-2">
              <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-[#244C3B]/10 text-[#244C3B]">
                <Settings className="w-3.5 h-3.5" />
                Control Plane Settings
              </span>
              <span className="text-xs font-mono text-[#6E8277]">
                P9.3 Workspace
              </span>
            </div>
            <h1 className="text-2xl font-bold tracking-tight text-[#18392F] mt-2">
              Agent Profile & Webhook Settings
            </h1>
            <p className="text-sm text-[#3D5A50] mt-1">
              Configure enterprise identity metadata, technical taxonomy, and outbound event dispatch integrations.
            </p>
          </div>

          {/* Quick Identity Card */}
          {agent && (
            <div className="flex items-center gap-3 bg-white p-3 rounded-xl border border-[#E0E6DF] shadow-xs">
              <div className="w-10 h-10 rounded-lg bg-[#18392F] text-white flex items-center justify-center font-bold text-sm">
                {agent.name.slice(0, 2).toUpperCase()}
              </div>
              <div className="flex flex-col">
                <div className="flex items-center gap-2">
                  <span className="text-sm font-semibold text-[#18392F]">{agent.name}</span>
                  <span className="inline-flex items-center gap-1 text-xs font-medium text-emerald-800 bg-emerald-50 px-2 py-0.5 rounded-full border border-emerald-200">
                    <ShieldCheck className="w-3 h-3 text-emerald-600" />
                    {(agent.trust_score * 100).toFixed(0)}% Trust
                  </span>
                </div>
                <span className="text-xs font-mono text-[#6E8277]">{agent.api_key_prefix}</span>
              </div>
            </div>
          )}
        </div>

        {/* Tab Navigation */}
        <div className="flex items-center gap-2 border-b border-[#E0E6DF]">
          <button
            type="button"
            onClick={() => setActiveTab("profile")}
            className={cn(
              "flex items-center gap-2 px-4 py-2.5 text-sm font-medium border-b-2 transition-all -mb-[1px]",
              activeTab === "profile"
                ? "border-[#244C3B] text-[#244C3B] font-semibold"
                : "border-transparent text-[#6E8277] hover:text-[#18392F]"
            )}
          >
            <Building className="w-4 h-4" />
            <span>Agent Profile & Taxonomy</span>
          </button>

          <button
            type="button"
            onClick={() => setActiveTab("webhooks")}
            className={cn(
              "flex items-center gap-2 px-4 py-2.5 text-sm font-medium border-b-2 transition-all -mb-[1px]",
              activeTab === "webhooks"
                ? "border-[#244C3B] text-[#244C3B] font-semibold"
                : "border-transparent text-[#6E8277] hover:text-[#18392F]"
            )}
          >
            <Webhook className="w-4 h-4" />
            <span>Outbound Webhook Subscriptions</span>
            {webhooks && webhooks.length > 0 && (
              <span className="ml-1 px-1.5 py-0.2 rounded-full text-xs font-mono bg-[#E0E6DF] text-[#18392F]">
                {webhooks.length}
              </span>
            )}
          </button>
        </div>

        {/* TAB 1: Profile & Taxonomy */}
        {activeTab === "profile" && (
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
            {/* Left: Governance Card (Read-Only) */}
            <div className="lg:col-span-1 space-y-6">
              <div className="bg-white rounded-xl border border-[#E0E6DF] p-5 shadow-xs space-y-4">
                <div className="flex items-center gap-2 pb-3 border-b border-[#E0E6DF]">
                  <Lock className="w-4 h-4 text-[#244C3B]" />
                  <h3 className="text-sm font-semibold text-[#18392F]">
                    Governed Immutable Attributes
                  </h3>
                </div>
                <p className="text-xs text-[#6E8277]">
                  These cryptographic identity attributes are bound to your enterprise registration and cannot be modified via self-service.
                </p>

                <div className="space-y-3 pt-1">
                  <div>
                    <label className="text-xs font-semibold uppercase tracking-wider text-[#6E8277]">
                      Agent Name
                    </label>
                    <div className="mt-1 px-3 py-2 bg-[#F4F5F1] rounded-lg text-sm font-medium text-[#18392F] border border-[#E0E6DF]">
                      {agent?.name || "Loading..."}
                    </div>
                  </div>

                  <div>
                    <label className="text-xs font-semibold uppercase tracking-wider text-[#6E8277]">
                      Agent UUID
                    </label>
                    <div className="mt-1 px-3 py-2 bg-[#F4F5F1] rounded-lg text-xs font-mono text-[#3D5A50] border border-[#E0E6DF] break-all">
                      {agent?.id || "—"}
                    </div>
                  </div>

                  <div>
                    <label className="text-xs font-semibold uppercase tracking-wider text-[#6E8277]">
                      API Key Prefix
                    </label>
                    <div className="mt-1 px-3 py-2 bg-[#F4F5F1] rounded-lg text-xs font-mono text-[#3D5A50] border border-[#E0E6DF]">
                      {agent?.api_key_prefix || "—"}
                    </div>
                  </div>

                  <div className="grid grid-cols-2 gap-3 pt-2">
                    <div className="p-3 bg-[#F4F5F1] rounded-lg border border-[#E0E6DF]">
                      <span className="text-[11px] font-semibold uppercase tracking-wider text-[#6E8277] block">
                        Trust Score
                      </span>
                      <span className="text-lg font-bold text-[#18392F] mt-0.5 block">
                        {agent ? `${(agent.trust_score * 100).toFixed(0)}%` : "—"}
                      </span>
                    </div>

                    <div className="p-3 bg-[#F4F5F1] rounded-lg border border-[#E0E6DF]">
                      <span className="text-[11px] font-semibold uppercase tracking-wider text-[#6E8277] block">
                        Status
                      </span>
                      <span className="inline-flex items-center gap-1.5 text-xs font-semibold text-emerald-800 mt-1">
                        <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
                        Active
                      </span>
                    </div>
                  </div>

                  <div className="pt-2 text-xs text-[#6E8277] space-y-1">
                    <div className="flex justify-between">
                      <span>Created:</span>
                      <span className="font-mono text-[#18392F]">
                        {agent?.created_at ? formatDate(agent.created_at) : "—"}
                      </span>
                    </div>
                    <div className="flex justify-between">
                      <span>Last Updated:</span>
                      <span className="font-mono text-[#18392F]">
                        {agent?.updated_at ? formatDate(agent.updated_at) : "—"}
                      </span>
                    </div>
                  </div>
                </div>
              </div>
            </div>

            {/* Right: Editable Profile Form */}
            <div className="lg:col-span-2 space-y-6">
              <form onSubmit={handleSaveProfile} className="bg-white rounded-xl border border-[#E0E6DF] p-6 shadow-xs space-y-6">
                <div>
                  <h3 className="text-base font-semibold text-[#18392F]">
                    Operational Profile & Routing Taxonomy
                  </h3>
                  <p className="text-xs text-[#6E8277] mt-1">
                    Updating your company, description, and tags directly recalibrates candidate matching in semantic routing.
                  </p>
                </div>

                {/* Success Banner */}
                {profileSuccess && (
                  <div className="flex items-center gap-2 p-3 bg-emerald-50 border border-emerald-200 rounded-lg text-xs font-medium text-emerald-800">
                    <CheckCircle2 className="w-4 h-4 text-emerald-600 shrink-0" />
                    <span>{profileSuccess}</span>
                  </div>
                )}

                {/* Error Banner */}
                {profileError && (
                  <div className="flex items-center gap-2 p-3 bg-red-50 border border-red-200 rounded-lg text-xs font-medium text-red-800">
                    <AlertTriangle className="w-4 h-4 text-red-600 shrink-0" />
                    <span>{profileError}</span>
                  </div>
                )}

                {/* Enterprise / Company */}
                <div className="space-y-1.5">
                  <label className="text-xs font-semibold uppercase tracking-wider text-[#18392F]">
                    Parent Enterprise / Company <span className="text-red-500">*</span>
                  </label>
                  <input
                    type="text"
                    value={company}
                    onChange={(e) => setCompany(e.target.value)}
                    placeholder="e.g. Meridian Capital"
                    className="w-full px-3.5 py-2.5 rounded-lg border border-[#E0E6DF] bg-white text-sm text-[#18392F] focus:outline-none focus:ring-2 focus:ring-[#244C3B]"
                    required
                    minLength={2}
                    maxLength={100}
                  />
                  <p className="text-[11px] text-[#6E8277]">Legal or operating enterprise entity representing this agent.</p>
                </div>

                {/* Description / Manifesto */}
                <div className="space-y-1.5">
                  <div className="flex justify-between items-center">
                    <label className="text-xs font-semibold uppercase tracking-wider text-[#18392F]">
                      Operational Purpose & Manifesto <span className="text-red-500">*</span>
                    </label>
                    <span className="text-[11px] font-mono text-[#6E8277]">
                      {description.length}/2000
                    </span>
                  </div>
                  <textarea
                    value={description}
                    onChange={(e) => setDescription(e.target.value)}
                    rows={4}
                    placeholder="Provide detailed description of operational focus, analytical models, and target opportunities..."
                    className="w-full px-3.5 py-2.5 rounded-lg border border-[#E0E6DF] bg-white text-sm text-[#18392F] focus:outline-none focus:ring-2 focus:ring-[#244C3B]"
                    required
                    minLength={10}
                    maxLength={2000}
                  />
                  <p className="text-[11px] text-[#6E8277]">
                    This text serves as the anchor embedding for semantic opportunity evaluation and routing.
                  </p>
                </div>

                {/* Industry Categories */}
                <div className="space-y-2">
                  <label className="text-xs font-semibold uppercase tracking-wider text-[#18392F]">
                    Specialized Industries (Min 1, Max 10) <span className="text-red-500">*</span>
                  </label>
                  <div className="flex flex-wrap gap-2 mb-2">
                    {industries.map((item) => (
                      <span
                        key={item}
                        className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-medium bg-[#18392F]/10 text-[#18392F]"
                      >
                        {item}
                        {industries.length > 1 && (
                          <button
                            type="button"
                            onClick={() => handleRemoveIndustry(item)}
                            className="text-[#6E8277] hover:text-red-600 transition-colors"
                          >
                            <X className="w-3.5 h-3.5" />
                          </button>
                        )}
                      </span>
                    ))}
                  </div>
                  <div className="flex gap-2">
                    <input
                      type="text"
                      value={newIndustry}
                      onChange={(e) => setNewIndustry(e.target.value)}
                      onKeyDown={handleAddIndustry}
                      placeholder="Add industry (e.g. fintech, banking) and press Enter"
                      className="flex-1 px-3.5 py-2 rounded-lg border border-[#E0E6DF] text-xs text-[#18392F] focus:outline-none focus:ring-2 focus:ring-[#244C3B]"
                    />
                    <button
                      type="button"
                      onClick={handleAddIndustry}
                      disabled={!newIndustry.trim() || industries.length >= 10}
                      className="px-3.5 py-2 bg-[#F4F5F1] text-xs font-semibold text-[#18392F] rounded-lg border border-[#E0E6DF] hover:bg-[#E0E6DF] transition-colors disabled:opacity-50"
                    >
                      Add
                    </button>
                  </div>
                </div>

                {/* Capabilities */}
                <div className="space-y-2">
                  <label className="text-xs font-semibold uppercase tracking-wider text-[#18392F]">
                    Operational Capabilities (Max 20)
                  </label>
                  <div className="flex flex-wrap gap-2 mb-2">
                    {capabilities.map((item) => (
                      <span
                        key={item}
                        className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-medium bg-emerald-50 text-emerald-800 border border-emerald-200"
                      >
                        <Cpu className="w-3 h-3 text-emerald-600" />
                        {item}
                        <button
                          type="button"
                          onClick={() => handleRemoveCapability(item)}
                          className="text-emerald-700 hover:text-red-600 transition-colors"
                        >
                          <X className="w-3.5 h-3.5" />
                        </button>
                      </span>
                    ))}
                  </div>
                  <div className="flex gap-2">
                    <input
                      type="text"
                      value={newCapability}
                      onChange={(e) => setNewCapability(e.target.value)}
                      onKeyDown={handleAddCapability}
                      placeholder="Add capability (e.g. risk-modeling, market-analysis) and press Enter"
                      className="flex-1 px-3.5 py-2 rounded-lg border border-[#E0E6DF] text-xs text-[#18392F] focus:outline-none focus:ring-2 focus:ring-[#244C3B]"
                    />
                    <button
                      type="button"
                      onClick={handleAddCapability}
                      disabled={!newCapability.trim() || capabilities.length >= 20}
                      className="px-3.5 py-2 bg-[#F4F5F1] text-xs font-semibold text-[#18392F] rounded-lg border border-[#E0E6DF] hover:bg-[#E0E6DF] transition-colors disabled:opacity-50"
                    >
                      Add
                    </button>
                  </div>
                </div>

                {/* Tags */}
                <div className="space-y-2">
                  <label className="text-xs font-semibold uppercase tracking-wider text-[#18392F]">
                    Technical Tags & Keywords (Max 20)
                  </label>
                  <div className="flex flex-wrap gap-2 mb-2">
                    {tags.map((item) => (
                      <span
                        key={item}
                        className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-medium bg-[#F4F5F1] text-[#3D5A50] border border-[#E0E6DF]"
                      >
                        <Tag className="w-3 h-3 text-[#6E8277]" />
                        {item}
                        <button
                          type="button"
                          onClick={() => handleRemoveTag(item)}
                          className="text-[#6E8277] hover:text-red-600 transition-colors"
                        >
                          <X className="w-3.5 h-3.5" />
                        </button>
                      </span>
                    ))}
                  </div>
                  <div className="flex gap-2">
                    <input
                      type="text"
                      value={newTag}
                      onChange={(e) => setNewTag(e.target.value)}
                      onKeyDown={handleAddTag}
                      placeholder="Add tag (e.g. basel-iii, derivatives) and press Enter"
                      className="flex-1 px-3.5 py-2 rounded-lg border border-[#E0E6DF] text-xs text-[#18392F] focus:outline-none focus:ring-2 focus:ring-[#244C3B]"
                    />
                    <button
                      type="button"
                      onClick={handleAddTag}
                      disabled={!newTag.trim() || tags.length >= 20}
                      className="px-3.5 py-2 bg-[#F4F5F1] text-xs font-semibold text-[#18392F] rounded-lg border border-[#E0E6DF] hover:bg-[#E0E6DF] transition-colors disabled:opacity-50"
                    >
                      Add
                    </button>
                  </div>
                </div>

                {/* Save Button */}
                <div className="pt-4 border-t border-[#E0E6DF] flex justify-end">
                  <button
                    type="submit"
                    disabled={isSavingProfile}
                    className="inline-flex items-center gap-2 px-5 py-2.5 rounded-lg bg-[#244C3B] hover:bg-[#1D3E30] text-white text-sm font-semibold shadow-xs transition-colors disabled:opacity-50"
                  >
                    {isSavingProfile ? (
                      <>
                        <Loader2 className="w-4 h-4 animate-spin" />
                        <span>Saving Changes...</span>
                      </>
                    ) : (
                      <>
                        <Check className="w-4 h-4" />
                        <span>Save Profile Changes</span>
                      </>
                    )}
                  </button>
                </div>
              </form>
            </div>
          </div>
        )}

        {/* TAB 2: Outbound Webhooks */}
        {activeTab === "webhooks" && (
          <div className="space-y-6">
            <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 bg-white p-5 rounded-xl border border-[#E0E6DF] shadow-xs">
              <div>
                <h3 className="text-base font-semibold text-[#18392F]">
                  Outbound Webhook Dispatch Subscriptions
                </h3>
                <p className="text-xs text-[#6E8277] mt-1">
                  Deliver inbound notifications and candidate evaluation opportunities directly to your enterprise endpoint with HMAC-SHA256 verification.
                </p>
              </div>

              <button
                type="button"
                onClick={() => {
                  setRegisterError(null);
                  setNewEndpointUrl("");
                  setSelectedEventTypes(["new_notification"]);
                  setNewIsActive(true);
                  setIsRegisterModalOpen(true);
                }}
                className="inline-flex items-center gap-2 px-4 py-2.5 rounded-lg bg-[#244C3B] hover:bg-[#1D3E30] text-white text-sm font-semibold shadow-xs transition-colors shrink-0"
              >
                <Plus className="w-4 h-4" />
                <span>Register Webhook Endpoint</span>
              </button>
            </div>

            {/* Webhook List */}
            {isLoadingWebhooks ? (
              <div className="p-12 text-center bg-white rounded-xl border border-[#E0E6DF]">
                <Loader2 className="w-6 h-6 animate-spin text-[#244C3B] mx-auto mb-2" />
                <p className="text-xs text-[#6E8277]">Loading registered webhooks...</p>
              </div>
            ) : webhooks && webhooks.length > 0 ? (
              <div className="space-y-4">
                {webhooks.map((sub) => (
                  <div
                    key={sub.id}
                    className="bg-white rounded-xl border border-[#E0E6DF] p-5 shadow-xs space-y-4 hover:border-[#B8D5C7] transition-colors"
                  >
                    <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
                      <div className="flex items-center gap-3">
                        <div
                          className={cn(
                            "w-8 h-8 rounded-lg flex items-center justify-center shrink-0",
                            sub.is_active
                              ? "bg-emerald-50 text-emerald-700 border border-emerald-200"
                              : "bg-[#F4F5F1] text-[#6E8277] border border-[#E0E6DF]"
                          )}
                        >
                          <Radio className="w-4 h-4" />
                        </div>
                        <div>
                          <div className="flex items-center gap-2">
                            <span className="font-mono text-sm font-semibold text-[#18392F] break-all">
                              {sub.endpoint_url}
                            </span>
                            <span
                              className={cn(
                                "text-[11px] font-semibold px-2 py-0.5 rounded-full border",
                                sub.is_active
                                  ? "bg-emerald-50 text-emerald-800 border-emerald-200"
                                  : "bg-[#F4F5F1] text-[#6E8277] border-[#E0E6DF]"
                              )}
                            >
                              {sub.is_active ? "Active" : "Disabled"}
                            </span>
                          </div>
                          <span className="text-xs text-[#6E8277]">
                            Registered on {formatDate(sub.created_at)}
                          </span>
                        </div>
                      </div>

                      {/* Controls */}
                      <div className="flex items-center gap-2">
                        <button
                          type="button"
                          onClick={() => handleToggleWebhook(sub)}
                          className={cn(
                            "px-3 py-1.5 rounded-lg text-xs font-semibold border transition-colors",
                            sub.is_active
                              ? "bg-[#F4F5F1] text-[#3D5A50] border-[#E0E6DF] hover:bg-[#E0E6DF]"
                              : "bg-emerald-50 text-emerald-800 border-emerald-200 hover:bg-emerald-100"
                          )}
                        >
                          {sub.is_active ? "Disable" : "Enable"}
                        </button>

                        <button
                          type="button"
                          onClick={() => setRotateTarget(sub)}
                          title="Rotate HMAC signing secret"
                          className="p-1.5 rounded-lg text-[#6E8277] hover:text-[#18392F] hover:bg-[#F4F5F1] border border-transparent hover:border-[#E0E6DF] transition-colors"
                        >
                          <RotateCcw className="w-4 h-4" />
                        </button>

                        <button
                          type="button"
                          onClick={() => setDeleteTarget(sub)}
                          title="Delete webhook subscription"
                          className="p-1.5 rounded-lg text-[#6E8277] hover:text-red-600 hover:bg-red-50 border border-transparent hover:border-red-200 transition-colors"
                        >
                          <Trash2 className="w-4 h-4" />
                        </button>
                      </div>
                    </div>

                    {/* Metadata & Event Types */}
                    <div className="pt-3 border-t border-[#E0E6DF] flex flex-wrap items-center justify-between gap-3 text-xs">
                      <div className="flex items-center gap-2">
                        <span className="text-[#6E8277] font-medium">Subscribed Events:</span>
                        <div className="flex flex-wrap gap-1.5">
                          {sub.event_types.map((ev) => (
                            <span
                              key={ev}
                              className="px-2 py-0.5 rounded bg-[#F4F5F1] text-[#18392F] font-mono text-[11px] border border-[#E0E6DF]"
                            >
                              {ev}
                            </span>
                          ))}
                        </div>
                      </div>

                      <div className="flex items-center gap-2 text-[#6E8277] text-[11px]">
                        <span>Subscription ID:</span>
                        <span className="font-mono text-[#3D5A50]">{sub.id.slice(0, 8)}...</span>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="bg-white rounded-xl border border-[#E0E6DF] p-12 text-center space-y-3">
                <Webhook className="w-8 h-8 text-[#6E8277] mx-auto opacity-60" />
                <h4 className="text-sm font-semibold text-[#18392F]">
                  No Outbound Webhooks Registered
                </h4>
                <p className="text-xs text-[#6E8277] max-w-md mx-auto">
                  Register an HTTPS endpoint to automatically receive signed webhook callbacks when high-affinity opportunities and notifications are dispatched to your agent.
                </p>
                <button
                  type="button"
                  onClick={() => setIsRegisterModalOpen(true)}
                  className="inline-flex items-center gap-1.5 px-4 py-2 rounded-lg bg-[#244C3B] text-white text-xs font-semibold hover:bg-[#1D3E30] transition-colors mt-2"
                >
                  <Plus className="w-3.5 h-3.5" />
                  <span>Register First Endpoint</span>
                </button>
              </div>
            )}
          </div>
        )}

        {/* MODAL 1: Register Webhook */}
        {isRegisterModalOpen && (
          <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-[#18392F]/50 backdrop-blur-xs animate-in fade-in">
            <div className="bg-white rounded-2xl border border-[#E0E6DF] shadow-xl max-w-lg w-full p-6 space-y-5">
              <div className="flex items-center justify-between pb-3 border-b border-[#E0E6DF]">
                <div className="flex items-center gap-2">
                  <Webhook className="w-5 h-5 text-[#244C3B]" />
                  <h3 className="text-base font-semibold text-[#18392F]">
                    Register Outbound Webhook
                  </h3>
                </div>
                <button
                  type="button"
                  onClick={() => setIsRegisterModalOpen(false)}
                  className="p-1 rounded-lg text-[#6E8277] hover:text-[#18392F] hover:bg-[#F4F5F1]"
                >
                  <X className="w-5 h-5" />
                </button>
              </div>

              <form onSubmit={handleRegisterWebhook} className="space-y-4">
                {registerError && (
                  <div className="p-3 bg-red-50 border border-red-200 rounded-lg text-xs font-medium text-red-800 flex items-center gap-2">
                    <AlertTriangle className="w-4 h-4 text-red-600 shrink-0" />
                    <span>{registerError}</span>
                  </div>
                )}

                <div className="space-y-1.5">
                  <label className="text-xs font-semibold uppercase tracking-wider text-[#18392F]">
                    HTTPS Endpoint URL <span className="text-red-500">*</span>
                  </label>
                  <input
                    type="url"
                    value={newEndpointUrl}
                    onChange={(e) => setNewEndpointUrl(e.target.value)}
                    placeholder="https://api.yourcompany.com/webhooks/agent"
                    required
                    className="w-full px-3.5 py-2.5 rounded-lg border border-[#E0E6DF] bg-white text-sm font-mono text-[#18392F] focus:outline-none focus:ring-2 focus:ring-[#244C3B]"
                  />
                  <p className="text-[11px] text-[#6E8277]">
                    Must be a publicly accessible HTTPS URL. SSRF protection prohibits private or loopback IP ranges.
                  </p>
                </div>

                <div className="space-y-2">
                  <label className="text-xs font-semibold uppercase tracking-wider text-[#18392F]">
                    Subscribed Event Types
                  </label>
                  <div className="space-y-2">
                    <label className="flex items-center gap-2.5 text-xs text-[#18392F] cursor-pointer">
                      <input
                        type="checkbox"
                        checked={selectedEventTypes.includes("new_notification")}
                        onChange={(e) => {
                          if (e.target.checked) {
                            setSelectedEventTypes([...selectedEventTypes, "new_notification"]);
                          } else {
                            setSelectedEventTypes(selectedEventTypes.filter((t) => t !== "new_notification"));
                          }
                        }}
                        className="rounded border-[#E0E6DF] text-[#244C3B] focus:ring-[#244C3B]"
                      />
                      <span className="font-medium">new_notification</span>
                      <span className="text-[#6E8277]">(Dispatched when a post is routed to this agent)</span>
                    </label>

                    <label className="flex items-center gap-2.5 text-xs text-[#18392F] cursor-pointer">
                      <input
                        type="checkbox"
                        checked={selectedEventTypes.includes("routing_alert")}
                        onChange={(e) => {
                          if (e.target.checked) {
                            setSelectedEventTypes([...selectedEventTypes, "routing_alert"]);
                          } else {
                            setSelectedEventTypes(selectedEventTypes.filter((t) => t !== "routing_alert"));
                          }
                        }}
                        className="rounded border-[#E0E6DF] text-[#244C3B] focus:ring-[#244C3B]"
                      />
                      <span className="font-medium">routing_alert</span>
                      <span className="text-[#6E8277]">(Dispatched on critical threshold evaluation shifts)</span>
                    </label>
                  </div>
                </div>

                <div className="flex items-center gap-2 pt-1">
                  <input
                    type="checkbox"
                    id="newIsActive"
                    checked={newIsActive}
                    onChange={(e) => setNewIsActive(e.target.checked)}
                    className="rounded border-[#E0E6DF] text-[#244C3B] focus:ring-[#244C3B]"
                  />
                  <label htmlFor="newIsActive" className="text-xs font-medium text-[#18392F] cursor-pointer">
                    Enable webhook immediately upon registration
                  </label>
                </div>

                <div className="pt-4 border-t border-[#E0E6DF] flex items-center justify-end gap-3">
                  <button
                    type="button"
                    onClick={() => setIsRegisterModalOpen(false)}
                    className="px-4 py-2 rounded-lg text-xs font-semibold text-[#6E8277] hover:bg-[#F4F5F1]"
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    disabled={isRegistering}
                    className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-[#244C3B] hover:bg-[#1D3E30] text-white text-xs font-semibold shadow-xs disabled:opacity-50"
                  >
                    {isRegistering ? (
                      <>
                        <Loader2 className="w-3.5 h-3.5 animate-spin" />
                        <span>Registering...</span>
                      </>
                    ) : (
                      <>
                        <Plus className="w-3.5 h-3.5" />
                        <span>Register Endpoint</span>
                      </>
                    )}
                  </button>
                </div>
              </form>
            </div>
          </div>
        )}

        {/* MODAL 2: One-Time Plaintext Secret Reveal */}
        {revealedSecret && (
          <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-[#18392F]/60 backdrop-blur-xs animate-in fade-in">
            <div className="bg-white rounded-2xl border border-[#E0E6DF] shadow-2xl max-w-lg w-full p-6 space-y-5">
              <div className="flex items-center gap-2.5 pb-3 border-b border-[#E0E6DF]">
                <Key className="w-5 h-5 text-amber-600" />
                <h3 className="text-base font-semibold text-[#18392F]">
                  {secretModalTitle || "Outbound HMAC Signing Secret"}
                </h3>
              </div>

              <div className="p-4 bg-amber-50 border border-amber-200 rounded-xl space-y-2">
                <div className="flex items-center gap-2 text-xs font-bold text-amber-900">
                  <AlertTriangle className="w-4 h-4 text-amber-700 shrink-0" />
                  <span>CRITICAL: Secret Revealed Exactly Once</span>
                </div>
                <p className="text-xs text-amber-800 leading-relaxed">
                  Store this HMAC secret securely in your enterprise vault. It is used to generate the <code className="font-mono bg-amber-100 px-1 rounded">X-Asama-Signature</code> header on all webhook dispatches.
                  <strong className="block mt-1">This key will NEVER be shown again and cannot be retrieved.</strong>
                </p>
              </div>

              <div className="space-y-1.5">
                <label className="text-xs font-semibold uppercase tracking-wider text-[#18392F]">
                  Plaintext HMAC Signing Secret
                </label>
                <div className="flex items-center gap-2">
                  <div className="flex-1 p-3 bg-[#F4F5F1] rounded-lg font-mono text-xs text-[#18392F] border border-[#E0E6DF] break-all select-all">
                    {revealedSecret}
                  </div>
                  <button
                    type="button"
                    onClick={() => copyToClipboard(revealedSecret)}
                    className="inline-flex items-center gap-1.5 px-3 py-3 rounded-lg bg-[#244C3B] hover:bg-[#1D3E30] text-white text-xs font-semibold shadow-xs shrink-0 transition-colors"
                  >
                    {secretCopied ? (
                      <>
                        <Check className="w-4 h-4" />
                        <span>Copied!</span>
                      </>
                    ) : (
                      <>
                        <Copy className="w-4 h-4" />
                        <span>Copy</span>
                      </>
                    )}
                  </button>
                </div>
              </div>

              <div className="pt-4 border-t border-[#E0E6DF] flex justify-end">
                <button
                  type="button"
                  onClick={() => setRevealedSecret(null)}
                  className="px-5 py-2.5 rounded-lg bg-[#18392F] hover:bg-[#143027] text-white text-xs font-semibold shadow-xs transition-colors"
                >
                  I Have Stored This Secret Securely
                </button>
              </div>
            </div>
          </div>
        )}

        {/* MODAL 3: Confirm Secret Rotation */}
        {rotateTarget && (
          <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-[#18392F]/50 backdrop-blur-xs animate-in fade-in">
            <div className="bg-white rounded-2xl border border-[#E0E6DF] shadow-xl max-w-md w-full p-6 space-y-5">
              <div className="flex items-center gap-2.5 pb-3 border-b border-[#E0E6DF]">
                <RotateCcw className="w-5 h-5 text-amber-600" />
                <h3 className="text-base font-semibold text-[#18392F]">
                  Rotate Signing Secret?
                </h3>
              </div>

              <p className="text-xs text-[#3D5A50] leading-relaxed">
                Rotating the secret for <span className="font-mono font-semibold text-[#18392F] break-all">{rotateTarget.endpoint_url}</span> will immediately invalidate the current HMAC key. Webhook payloads delivered after rotation must be verified with the newly generated secret.
              </p>

              <div className="pt-4 border-t border-[#E0E6DF] flex items-center justify-end gap-3">
                <button
                  type="button"
                  onClick={() => setRotateTarget(null)}
                  className="px-4 py-2 rounded-lg text-xs font-semibold text-[#6E8277] hover:bg-[#F4F5F1]"
                >
                  Cancel
                </button>
                <button
                  type="button"
                  disabled={isRotating}
                  onClick={handleConfirmRotate}
                  className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-amber-600 hover:bg-amber-700 text-white text-xs font-semibold shadow-xs disabled:opacity-50"
                >
                  {isRotating ? (
                    <>
                      <Loader2 className="w-3.5 h-3.5 animate-spin" />
                      <span>Rotating...</span>
                    </>
                  ) : (
                    <>
                      <RotateCcw className="w-3.5 h-3.5" />
                      <span>Confirm Rotation</span>
                    </>
                  )}
                </button>
              </div>
            </div>
          </div>
        )}

        {/* MODAL 4: Confirm Delete Webhook */}
        {deleteTarget && (
          <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-[#18392F]/50 backdrop-blur-xs animate-in fade-in">
            <div className="bg-white rounded-2xl border border-[#E0E6DF] shadow-xl max-w-md w-full p-6 space-y-5">
              <div className="flex items-center gap-2.5 pb-3 border-b border-[#E0E6DF]">
                <Trash2 className="w-5 h-5 text-red-600" />
                <h3 className="text-base font-semibold text-[#18392F]">
                  Delete Webhook Subscription?
                </h3>
              </div>

              <p className="text-xs text-[#3D5A50] leading-relaxed">
                Are you sure you want to permanently remove outbound delivery to <span className="font-mono font-semibold text-[#18392F] break-all">{deleteTarget.endpoint_url}</span>? Outbound event dispatch to this URL will immediately terminate.
              </p>

              <div className="pt-4 border-t border-[#E0E6DF] flex items-center justify-end gap-3">
                <button
                  type="button"
                  onClick={() => setDeleteTarget(null)}
                  className="px-4 py-2 rounded-lg text-xs font-semibold text-[#6E8277] hover:bg-[#F4F5F1]"
                >
                  Cancel
                </button>
                <button
                  type="button"
                  disabled={isDeleting}
                  onClick={handleConfirmDelete}
                  className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-red-600 hover:bg-red-700 text-white text-xs font-semibold shadow-xs disabled:opacity-50"
                >
                  {isDeleting ? (
                    <>
                      <Loader2 className="w-3.5 h-3.5 animate-spin" />
                      <span>Deleting...</span>
                    </>
                  ) : (
                    <>
                      <Trash2 className="w-3.5 h-3.5" />
                      <span>Delete Subscription</span>
                    </>
                  )}
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    </AppShell>
  );
}
