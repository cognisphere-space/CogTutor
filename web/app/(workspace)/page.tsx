"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { capturePendingExternalContextMarker } from "@/lib/external-context";

/**
 * Root page now redirects to /home.
 * Handles backward compatibility for /?session=xxx URLs.
 */
export default function HomePage() {
  const router = useRouter();

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const sessionId = params.get("session");
    const capability = params.get("capability");
    const tools = params.getAll("tool");

    // complete_handoff() may have appended `external_context_pending` to
    // this URL. Capture it into sessionStorage and strip it from the
    // address bar here, before navigating away, rather than forwarding it
    // to /home — UnifiedChatProvider's own capture call there is a no-op
    // once this has already run, so forwarding would just leave a stale
    // marker sitting in the /home address bar. See web/lib/external-context.ts.
    capturePendingExternalContextMarker();

    let target = sessionId ? `/home/${sessionId}` : "/home";

    const query: string[] = [];
    if (capability) query.push(`capability=${encodeURIComponent(capability)}`);
    tools.forEach((t) => query.push(`tool=${encodeURIComponent(t)}`));
    if (query.length) target += `?${query.join("&")}`;

    router.replace(target);
  }, [router]);

  return null;
}
