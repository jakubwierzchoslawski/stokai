/**
 * AiAuditConsolePage — top-level Admin AI Audit Console.
 *
 * Four-tab layout:
 *   1. Decision Log
 *   2. Prompt History
 *   3. Calibration
 *   4. Workflow History
 *
 * Tab switching is controlled by React state; no URL routing between tabs.
 *
 * PLAN-F-029 TASK-007
 */
import React, { useState } from 'react';
import { DecisionLogPanel } from './DecisionLogPanel';
import { PromptVersionPanel } from './PromptVersionPanel';
import { CalibrationDashboard } from './CalibrationDashboard';
import { WorkflowHistoryPanel } from './WorkflowHistoryPanel';

type Tab = 'decisions' | 'prompts' | 'calibration' | 'workflows';

const TABS: { id: Tab; label: string }[] = [
  { id: 'decisions', label: 'Decision Log' },
  { id: 'prompts', label: 'Prompt History' },
  { id: 'calibration', label: 'Calibration' },
  { id: 'workflows', label: 'Workflow History' },
];

export function AiAuditConsolePage() {
  const [activeTab, setActiveTab] = useState<Tab>('decisions');

  return (
    <div className="min-h-screen bg-gray-50" data-testid="ai-audit-console">
      <div className="max-w-screen-2xl mx-auto px-6 py-6">
        <h1 className="text-2xl font-bold text-gray-900 mb-6">AI Audit Console</h1>

        {/* Tab navigation */}
        <div className="border-b border-gray-200 mb-6">
          <nav className="flex -mb-px gap-6">
            {TABS.map((tab) => (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                className={`pb-3 text-sm font-medium border-b-2 transition-colors ${
                  activeTab === tab.id
                    ? 'border-blue-600 text-blue-600'
                    : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
                }`}
                data-testid={`tab-${tab.id}`}
                aria-selected={activeTab === tab.id}
                role="tab"
              >
                {tab.label}
              </button>
            ))}
          </nav>
        </div>

        {/* Tab panels */}
        {activeTab === 'decisions' && <DecisionLogPanel />}
        {activeTab === 'prompts' && <PromptVersionPanel />}
        {activeTab === 'calibration' && <CalibrationDashboard />}
        {activeTab === 'workflows' && <WorkflowHistoryPanel />}
      </div>
    </div>
  );
}

export default AiAuditConsolePage;
