import React from "react";
import { cn } from "@/lib/utils";

export interface SkeletonProps extends React.HTMLAttributes<HTMLDivElement> {
  variant?: "rectangular" | "circular" | "rounded";
}

export function Skeleton({
  className,
  variant = "rounded",
  ...props
}: SkeletonProps) {
  const variantStyles = {
    rectangular: "rounded-none",
    rounded: "rounded-md",
    circular: "rounded-full",
  };

  return (
    <div
      aria-hidden="true"
      className={cn(
        "bg-[#E0E6DF]/60 animate-pulse",
        variantStyles[variant],
        className
      )}
      {...props}
    />
  );
}
