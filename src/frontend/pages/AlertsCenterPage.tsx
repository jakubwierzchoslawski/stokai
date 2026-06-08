/**
 * AlertsCenterPage — top-level Alerts Center page with two-tab layout.
 *
 * Tabs: Alerts | Rules
 * Route: /alerts (auth-guarded via ProtectedRoute from app/routes.tsx)
 *
 * Mobile-first responsive constraints (PLAN-N-014 TASK-007):
 *  - Root container: overflow-x-hidden w-full (no horizontal scroll at 375px)
 *  - Tab buttons: min-h-[44px] px-4 (touch targets ≥44px)
 *  - All direct children: max-w-full
 *
 * PLAN-F-025 TASK-008
 * PLAN-N-014 TASK-007
 */
import React, { useState } from 'react';
import { AlertsListPanel } from '../features/alerts/AlertsListPanel';
import { AlertRulesPanel } from '../features/alerts/AlertRulesPanel';
import { AntiFatigueSettingsPanel } from '../features/alerts/AntiFatigueSettingsPanel';

type Tab = 'alerts' | 'rules';

export function AlertsCenterPage(): React.ReactElement {
  const [activeTab, setActiveTab] = useState<Tab>('alerts');

  return (
    // Root container: overflow-x-hidden w-full — no horizontal scroll at 375px (AC-001)
    <div
      className="alerts-center-page"
      style={{ overflowX: 'hidden', width: '100%' }}
      data-testid="alerts-center-page"
    >
      <header className="alerts-center-page__header" style={{ maxWidth: '100%' }}>
        <h1>Alerts Center</h1>
      </header>

      {/* Tab bar: tab buttons use min-h-[44px] for touch targets (AC-001) */}
      <nav
        className="alerts-center-page__tabs"
        role="tablist"
        aria-label="Alerts Center sections"
        style={{ maxWidth: '100%', display: 'flex' }}
      >
        <button
          role="tab"
          aria-selected={activeTab === 'alerts'}
          aria-controls="tab-panel-alerts"
          className={`alerts-center-page__tab ${activeTab === 'alerts' ? 'alerts-center-page__tab--active' : ''}`}
          onClick={() => setActiveTab('alerts')}
          data-testid="tab-alerts"
          style={{ minHeight: 44, padding: '0 16px' }}
        >
          Alerts
        </button>
        <button
          role="tab"
          aria-selected={activeTab === 'rules'}
          aria-controls="tab-panel-rules"
          className={`alerts-center-page__tab ${activeTab === 'rules' ? 'alerts-center-page__tab--active' : ''}`}
          onClick={() => setActiveTab('rules')}
          data-testid="tab-rules"
          style={{ minHeight: 44, padding: '0 16px' }}
        >
          Rules
        </button>
      </nav>

      <main style={{ maxWidth: '100%', overflowX: 'hidden' }}>
        {activeTab === 'alerts' && (
          <div
            id="tab-panel-alerts"
            role="tabpanel"
            aria-label="Alerts list"
            style={{ maxWidth: '100%' }}
          >
            <AlertsListPanel />
          </div>
        )}
        {activeTab === 'rules' && (
          <div
            id="tab-panel-rules"
            role="tabpanel"
            aria-label="Alert rules"
            style={{ maxWidth: '100%' }}
          >
            <AlertRulesPanel />
            <AntiFatigueSettingsPanel />
          </div>
        )}
      </main>
    </div>
  );
}

export default AlertsCenterPage;
