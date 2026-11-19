import { clsx, type ClassValue } from "clsx";

export function cn(...inputs: ClassValue[]): string {
  return clsx(inputs);
}

export function formatDateTime(dateStr?: string | null): string {
  if (!dateStr) return "—";
  try {
    const date = new Date(dateStr);
    return new Intl.DateTimeFormat("en-US", {
      month: "short",
      day: "numeric",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
      timeZoneName: "short",
    }).format(date);
  } catch {
    return dateStr;
  }
}

export function formatDate(dateStr?: string | null): string {
  if (!dateStr) return "—";
  try {
    const date = new Date(dateStr);
    return new Intl.DateTimeFormat("en-US", {
      month: "short",
      day: "numeric",
      year: "numeric",
    }).format(date);
  } catch {
    return dateStr;
  }
}

export function formatRelativeTime(dateStr?: string | null): string {
  if (!dateStr) return "—";
  try {
    const date = new Date(dateStr);
    const now = new Date();
    const diff = now.getTime() - date.getTime();

    const seconds = Math.floor(diff / 1000);
    if (seconds < 45) return "just now";

    const minutes = Math.floor(seconds / 60);
    if (minutes < 60) return `${minutes}m ago`;

    const hours = Math.floor(minutes / 60);
    if (hours < 24) return `${hours}h ago`;

    const days = Math.floor(hours / 24);
    if (days < 30) return `${days}d ago`;

    return formatDate(dateStr);
  } catch {
    return dateStr;
  }
}

export function truncate(str: string, maxLength: number): string {
  if (!str) return "";
  if (str.length <= maxLength) return str;
  return str.slice(0, maxLength).trimEnd() + "…";
}

export function formatNumber(num: number): string {
  if (num >= 1_000_000) {
    return `${(num / 1_000_000).toFixed(1)}M`;
  }
  if (num >= 1_000) {
    return `${(num / 1_000).toFixed(1)}k`;
  }
  return num.toString();
}

export function scoreColor(score: number): string {
  if (score >= 0.7) return "text-emerald-400";
  if (score >= 0.4) return "text-amber-400";
  return "text-red-400";
}

export function scoreBadgeClass(score: number): string {
  if (score >= 0.7) {
    return "bg-emerald-500/10 text-emerald-300 border-emerald-500/20";
  }
  if (score >= 0.4) {
    return "bg-amber-500/10 text-amber-300 border-amber-500/20";
  }
  return "bg-red-500/10 text-red-300 border-red-500/20";
}

export function generateUUID(): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }
  return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0;
    const v = c === "x" ? r : (r & 0x3) | 0x8;
    return v.toString(16);
  });
}

export function formatPostType(type: string): string {
  switch (type) {
    case "announcement":
      return "Announcement";
    case "promotion":
      return "Promotion";
    case "market_update":
      return "Market Update";
    case "collaboration":
      return "Collaboration";
    default:
      return type.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
  }
}

export function postTypeBadgeClass(type: string): string {
  switch (type) {
    case "announcement":
      return "bg-[#E4EEE8] text-[#183A2C] border-[#B8D5C7]";
    case "promotion":
      return "bg-[#F8F9F6] text-[#647169] border-[#E0E6DF]";
    case "market_update":
      return "bg-[#EEF1ED] text-[#24493D] border-[#E0E6DF]";
    case "collaboration":
      return "bg-[#E7EFEA] text-[#2D4A3E] border-[#CADCD0]";
    default:
      return "bg-[#F8F9F6] text-[#647169] border-[#E0E6DF]";
  }
}
