/**
 * HilQueue — /admin/hil page.
 *
 * Renders the HIL queue table with expandable item detail and action buttons.
 * Route is guarded: only admin and operator roles may access this page.
 * Non-authorised users are redirected to /.
 *
 * PLAN-F-013 TASK-008
 */
import React, { useState } from "react";
import { Navigate } from "react-router-dom";
import { HilQueueTable } from "./HilQueueTable";
import { HilItemDetail } from "./HilItemDetail";
import { HilActionButtons } from "./HilActionButtons";
import { useHilQueue } from "./useHilQueue";
import { useCurrentUser } from "@/app/providers/AuthProvider";

/** HIL queue page (/admin/hil). */
export const HilQueue: React.FC = () => {
  const user = useCurrentUser();
  const { items, isLoading, executeAction } = useHilQueue();
  const [selectedItemId, setSelectedItemId] = useState<string | null>(null);

  // Route guard: only admin
  if (user.role !== "admin") {
    return <Navigate to="/" replace />;
  }

  const selectedItem = items?.find((item) => item.item_id === selectedItemId) ?? null;

  return (
    <div className="hil-queue-page" data-testid="hil-queue-page">
      <header className="hil-queue-header">
        <h1>HIL Review Queue</h1>
        <p className="hil-queue-subtitle">
          Workflows pending human review (confidence 0.40–0.69)
        </p>
      </header>

      {isLoading ? (
        <div className="hil-loading" aria-busy="true">
          Loading queue…
        </div>
      ) : (
        <div className="hil-queue-layout">
          <section className="hil-queue-list" aria-label="Pending items">
            <HilQueueTable
              items={items ?? []}
              selectedItemId={selectedItemId}
              onSelectItem={setSelectedItemId}
            />
          </section>

          {selectedItem && (
            <aside className="hil-queue-detail" aria-label="Item detail">
              <HilItemDetail item={selectedItem} />
              <HilActionButtons
                item={selectedItem}
                onAction={async (action, extras) => {
                  await executeAction({
                    itemId: selectedItem.item_id,
                    action,
                    ...extras,
                  });
                  setSelectedItemId(null);
                }}
              />
            </aside>
          )}
        </div>
      )}
    </div>
  );
};

export default HilQueue;
