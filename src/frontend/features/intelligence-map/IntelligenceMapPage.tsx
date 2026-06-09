import * as React from "react";
import { useNavigate } from "react-router-dom";

import { StubModeBadge } from "@/ui/StubModeBadge";

import { IntelligenceMap } from "./IntelligenceMap";
import type { EventPulse } from "./types/map.types";

export function IntelligenceMapPage() {
  const navigate = useNavigate();

  const handleExpand = React.useCallback(
    (event: EventPulse) => {
      navigate(`/events/${event.event_id}/deep-dive`);
    },
    [navigate],
  );

  return (
    <div className="relative">
      <div className="absolute left-4 top-4 z-50">
        <StubModeBadge watch={["market_data", "news"]} />
      </div>
      <IntelligenceMap onExpandEvent={handleExpand} />
    </div>
  );
}

export default IntelligenceMapPage;
