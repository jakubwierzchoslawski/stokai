/**
 * IngestionJobsTab — table of ingestion jobs with Manual Trigger button per row.
 *
 * - Status badge: idle=grey, running=blue spinner, failed=red
 * - "Manual Trigger" button disabled while job.status === "running"
 * - On trigger success: toast "Job dispatched"
 * - On trigger error: toast error message
 *
 * PLAN-F-030 TASK-009
 */
import React from "react";
import { useIngestionJobs, useTriggerJob } from "./hooks/useSystemOps";

type StatusBadgeProps = { status: "idle" | "running" | "failed" };

const StatusBadge: React.FC<StatusBadgeProps> = ({ status }) => {
  const styles: Record<string, React.CSSProperties> = {
    idle: { background: "#9ca3af", color: "#fff", padding: "2px 8px", borderRadius: 4 },
    running: { background: "#3b82f6", color: "#fff", padding: "2px 8px", borderRadius: 4 },
    failed: { background: "#ef4444", color: "#fff", padding: "2px 8px", borderRadius: 4 },
  };
  return (
    <span data-testid={`status-badge-${status}`} style={styles[status]}>
      {status === "running" ? "running..." : status}
    </span>
  );
};

export const IngestionJobsTab: React.FC = () => {
  const { data: jobs, isLoading, isError } = useIngestionJobs();
  const trigger = useTriggerJob();

  const handleTrigger = async (jobId: string) => {
    try {
      await trigger.mutateAsync(jobId);
      // Simple toast via alert — in a real app use a toast library
      alert("Job dispatched");
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : "Failed to trigger job");
    }
  };

  if (isLoading) return <div data-testid="jobs-loading">Loading...</div>;
  if (isError) return <div data-testid="jobs-error">Failed to load jobs</div>;

  return (
    <div data-testid="ingestion-jobs-tab">
      <h2>Ingestion Jobs</h2>
      <table style={{ width: "100%", borderCollapse: "collapse" }}>
        <thead>
          <tr>
            <th>Name</th>
            <th>Schedule</th>
            <th>Last Run</th>
            <th>Next Run</th>
            <th>Status</th>
            <th>Errors</th>
            <th>Action</th>
          </tr>
        </thead>
        <tbody>
          {(jobs ?? []).map((job) => (
            <tr key={job.job_id} data-testid={`job-row-${job.job_id}`}>
              <td>{job.name}</td>
              <td>
                <code>{job.schedule}</code>
              </td>
              <td>{job.last_run ? new Date(job.last_run).toLocaleString() : "—"}</td>
              <td>{job.next_run ? new Date(job.next_run).toLocaleString() : "—"}</td>
              <td>
                <StatusBadge status={job.status} />
              </td>
              <td data-testid={`error-count-${job.job_id}`}>{job.error_count}</td>
              <td>
                <button
                  data-testid={`trigger-btn-${job.job_id}`}
                  disabled={job.status === "running" || trigger.isPending}
                  onClick={() => handleTrigger(job.job_id)}
                >
                  {trigger.isPending ? "Dispatching..." : "Manual Trigger"}
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
};

export default IngestionJobsTab;
