"use client";

import React from "react";
import { SWRConfig } from "swr";

export function SWRProvider({ children }: { children: React.ReactNode }) {
  return (
    <SWRConfig
      value={{
        revalidateOnFocus: true,
        shouldRetryOnError: false,
        dedupingInterval: 10000,
        onError: (err) => {
          if (err?.status === 401 && typeof window !== "undefined") {
            window.dispatchEvent(new CustomEvent("agent-session-expired"));
          }
        },
      }}
    >
      {children}
    </SWRConfig>
  );
}
