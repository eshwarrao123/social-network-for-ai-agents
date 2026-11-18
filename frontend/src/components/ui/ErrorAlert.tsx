import React from "react";
import { AlertTriangle, RotateCw } from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "./Button";

export interface ErrorAlertProps {
  message: string;
  title?: string;
  onRetry?: () => void;
  className?: string;
}

export function ErrorAlert({
  message,
  title = "Service Alert",
  onRetry,
  className,
}: ErrorAlertProps) {
  return (
    <div
      role="alert"
      className={cn(
        "flex items-start justify-between gap-4 p-4 rounded-xl bg-[#FEE2E2] border border-[#FECACA] text-[#B91C1C]",
        className
      )}
    >
      <div className="flex items-start gap-3">
        <AlertTriangle className="w-5 h-5 text-[#B91C1C] shrink-0 mt-0.5" />
        <div className="space-y-1">
          <h5 className="text-sm font-semibold text-[#B91C1C] leading-none">
            {title}
          </h5>
          <p className="text-sm text-[#7F1D1D] leading-relaxed">{message}</p>
        </div>
      </div>
      {onRetry && (
        <Button
          variant="secondary"
          size="sm"
          onClick={onRetry}
          leftIcon={<RotateCw className="w-3.5 h-3.5" />}
          className="shrink-0 text-xs border-[#FECACA] text-[#B91C1C] hover:bg-[#FCA5A5]/30"
        >
          Retry
        </Button>
      )}
    </div>
  );
}
