import React from "react";
import { Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";

export interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: "primary" | "secondary" | "destructive" | "outline" | "ghost";
  size?: "sm" | "md" | "lg";
  isLoading?: boolean;
  leftIcon?: React.ReactNode;
  rightIcon?: React.ReactNode;
}

export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  (
    {
      className,
      variant = "primary",
      size = "md",
      isLoading = false,
      leftIcon,
      rightIcon,
      disabled,
      children,
      ...props
    },
    ref
  ) => {
    const baseStyles =
      "inline-flex items-center justify-center font-medium rounded-lg transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#244C3B] focus-visible:ring-offset-2 disabled:opacity-50 disabled:pointer-events-none select-none";

    const variantStyles = {
      primary:
        "bg-[#244C3B] hover:bg-[#183A2C] active:bg-[#132E23] text-white shadow-none",
      secondary:
        "bg-white hover:bg-[#F8F9F6] active:bg-[#EEF1ED] text-[#1B2520] border border-[#E0E6DF] shadow-none",
      destructive:
        "bg-[#FEE2E2] hover:bg-[#FECACA] active:bg-[#FCA5A5] text-[#B91C1C] border border-[#FECACA] shadow-none",
      outline:
        "bg-transparent hover:bg-[#F8F9F6] text-[#647169] hover:text-[#1B2520] border border-[#E0E6DF]",
      ghost:
        "bg-transparent hover:bg-black/[0.04] text-[#647169] hover:text-[#1B2520]",
    };

    const sizeStyles = {
      sm: "h-9 px-3 text-xs gap-1.5",
      md: "h-10 px-4 text-sm gap-2",
      lg: "h-11 px-6 text-base gap-2.5",
    };

    return (
      <button
        ref={ref}
        disabled={disabled || isLoading}
        className={cn(baseStyles, variantStyles[variant], sizeStyles[size], className)}
        {...props}
      >
        {isLoading ? (
          <Loader2 className="w-4 h-4 animate-spin text-current" />
        ) : (
          leftIcon
        )}
        <span>{children}</span>
        {!isLoading && rightIcon}
      </button>
    );
  }
);

Button.displayName = "Button";
