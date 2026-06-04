/**
 * AlertsCenterPage — top-level Alerts Center page with two-tab layout.
 *
 * Tabs: Alerts | Rules
 * Route: /alerts (auth-guarded via ProtectedRoute from app/routes.tsx)
 *
 * PLAN-F-025 TASK-008
 */
import React, { useState } from 'react';
import { AlertsListPanel } from '../components/alerts/AlertsListPanel';
import { AlertRulesPanel } from '../components/alerts/AlertRulesPanel';
import { AntiFatigueSettingsPanel } from '../components/alerts/AntiFatigueSettingsPanel';

type Tab = 'alerts' | 'rules';

export function AlertsCenterPage(): React.ReactElement {
  const [activeTab, setActiveTab] = useState<Tab>('alerts');

  return (
    <div className="alerts-center-page">
      <header className="alerts-center-page__header">
        <h1>Alerts Center</h1>
      </header>

      <nav className="alerts-center-page__tabs" role="tablist" aria-label="Alerts Center sections">
        <button
          role="tab"
          aria-selected={activeTab === 'alerts'}
          aria-controls="tab-panel-alerts"
          className={`alerts-center-page__tab ${activeTab === 'alerts' ? 'alerts-center-page__tab--active' : ''}`}
          onClick={() => setActiveTab('alerts')}
          data-testid="tab-alerts"
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
        >
          Rules
        </button>
      </nav>

      <main>
        {activeTab === 'alerts' && (
          <div id="tab-panel-alerts" role="tabpanel" aria-label="Alerts list">
            <AlertsListPanel />
          </div>
        )}
        {activeTab === 'rules' && (
          <div id="tab-panel-rules" role="tabpanel" aria-label="Alert rules">
            <AlertRulesPanel />
            <AntiFatigueSettingsPanel />
          </div>
        )}
      </main>
    </div>
  );
}

export default AlertsCenterPage;
