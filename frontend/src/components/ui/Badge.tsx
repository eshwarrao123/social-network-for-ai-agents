import React from "react";
import { cn } from "@/lib/utils";

export interface BadgeProps extends React.HTMLAttributes<HTMLSpanElement> {
  variant?: "default" | "primary" | "secondary" | "success" | "warning" | "error" | "llm" | "outline";
  size?: "sm" | "md";
}

export function Badge({
  className,
  variant = "default",
  size = "md",
  children,
  ...props
}: BadgeProps) {
  const baseStyles =
    "inline-flex items-center font-medium rounded-full border transition-colors select-none";

  const variantStyles = {
    default: "bg-[#F1F5F9] text-[#475569] border-[#E2E8F0]",
    primary: "bg-[#E4EEE8] text-[#183A2C] border-[#B8D5C7]",
    secondary: "bg-[#F8F9F6] text-[#647169] border-[#E0E6DF]",
    success: "bg-[#E8F5E9] text-[#1B5E20] border-[#C8E6C9]",
    warning: "bg-[#FEF3C7] text-[#B45309] border-[#FDE68A]",
    error: "bg-[#FEE2E2] text-[#B91C1C] border-[#FECACA]",
    llm: "bg-[#E7EFEA] text-[#2D4A3E] border-[#CADCD0]",
    outline: "bg-transparent text-[#647169] border-[#E0E6DF]",
  };

  const sizeStyles = {
    sm: "px-2 py-0.5 text-xs leading-tight tracking-normal",
    md: "px-2.5 py-1 text-xs leading-none",
  };

  return (
    <span
      className={cn(baseStyles, variantStyles[variant], sizeStyles[size], className)}
      {...props}
    >
      {children}
    </span>
  );
}
