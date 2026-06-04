/**
 * pages/admin/system/IngestionJobsTab — Ingestion jobs management tab.
 *
 * Displays: table with name, schedule, last_run, next_run, status badge, error_count.
 * Actions: Manual Trigger per row (disabled when running).
 *
 * PLAN-F-030 TASK-009
 */
import React from 'react';
import { useIngestionJobs, useTriggerJob, type IngestionJob } from '../../../hooks/useSystemOps';

// ── Status badge ───────────────────────────────────────────────────────────────

function StatusBadge({ status }: { status: IngestionJob['status'] }) {
  const colorMap: Record<IngestionJob['status'], string> = {
    idle: 'bg-gray-100 text-gray-800',
    running: 'bg-blue-100 text-blue-800',
    failed: 'bg-red-100 text-red-800',
  };
  return (
    <span
      className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${colorMap[status]}`}
      data-testid={`status-badge-${status}`}
    >
      {status}
    </span>
  );
}

// ── Main component ─────────────────────────────────────────────────────────────

export function IngestionJobsTab() {
  const { data: jobs, isLoading, error } = useIngestionJobs();
  const triggerMutation = useTriggerJob();

  if (isLoading) {
    return <div data-testid="jobs-loading">Loading ingestion jobs...</div>;
  }

  if (error) {
    return (
      <div data-testid="jobs-error" className="text-red-600">
        Failed to load jobs: {error.message}
      </div>
    );
  }

  return (
    <div data-testid="ingestion-jobs-tab">
      <h2 className="text-lg font-semibold mb-4">Ingestion Jobs</h2>
      <div className="overflow-x-auto">
        <table className="min-w-full divide-y divide-gray-200" data-testid="jobs-table">
          <thead className="bg-gray-50">
            <tr>
              <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                Name
              </th>
              <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                Schedule
              </th>
              <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                Last Run
              </th>
              <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                Next Run
              </th>
              <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                Status
              </th>
              <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                Errors
              </th>
              <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                Action
              </th>
            </tr>
          </thead>
          <tbody className="bg-white divide-y divide-gray-200">
            {(jobs ?? []).map((job) => (
              <tr key={job.job_id} data-testid={`job-row-${job.job_id}`}>
                <td className="px-4 py-3 text-sm text-gray-900">{job.name}</td>
                <td className="px-4 py-3 text-sm text-gray-500 font-mono">{job.schedule}</td>
                <td className="px-4 py-3 text-sm text-gray-500">
                  {job.last_run ? new Date(job.last_run).toLocaleString() : '—'}
                </td>
                <td className="px-4 py-3 text-sm text-gray-500">
                  {job.next_run ? new Date(job.next_run).toLocaleString() : '—'}
                </td>
                <td className="px-4 py-3">
                  <StatusBadge status={job.status} />
                  {job.status === 'failed' && job.error_count > 0 && (
                    <span
                      data-testid={`error-count-${job.job_id}`}
                      className="ml-1 text-xs text-red-600"
                    >
                      ({job.error_count})
                    </span>
                  )}
                </td>
                <td className="px-4 py-3 text-sm text-gray-900" data-testid={`error-count-cell-${job.job_id}`}>
                  {job.error_count}
                </td>
                <td className="px-4 py-3">
                  <button
                    data-testid={`trigger-btn-${job.job_id}`}
                    disabled={job.status === 'running' || triggerMutation.isPending}
                    onClick={() => triggerMutation.mutate({ job_id: job.job_id })}
                    className={`px-3 py-1 text-sm rounded ${
                      job.status === 'running'
                        ? 'bg-gray-200 text-gray-400 cursor-not-allowed'
                        : 'bg-blue-600 text-white hover:bg-blue-700'
                    }`}
                  >
                    {triggerMutation.isPending ? 'Triggering...' : 'Trigger'}
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export default IngestionJobsTab;
