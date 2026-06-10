import * as React from "react";

import { useDisclosure } from "@/features/progressive-disclosure/ProgressiveDisclosureProvider";
import { StubModeBadge } from "@/ui/StubModeBadge";
import { IntelligenceMap } from "./IntelligenceMap";

export function IntelligenceMapPage() {
  const { onExpandEvent } = useDisclosure();

  return (
    <div className="relative">
      <div className="absolute left-4 top-4 z-50">
        <StubModeBadge watch={["market_data", "news"]} />
      </div>
      <IntelligenceMap onExpandEvent={onExpandEvent} />
    </div>
  );
}

export default IntelligenceMapPage;
