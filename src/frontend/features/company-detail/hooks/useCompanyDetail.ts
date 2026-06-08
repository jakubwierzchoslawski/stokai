/**
 * useCompanyDetail — TanStack Query hook for fetching company detail.
 *
 * GET /api/v1/companies/{companyId}/detail?profile_id={profileId}
 * staleTime: 60 seconds
 *
 * PLAN-F-023 TASK-005
 */
import { useQuery } from '@tanstack/react-query';
import type { CompanyDetailResponse } from '../types';

const COMPANY_DETAIL_STALE_MS = 60_000;

async function fetchCompanyDetail(
  companyId: string,
  profileId?: string,
): Promise<CompanyDetailResponse> {
  const params = new URLSearchParams();
  if (profileId) {
    params.set('profile_id', profileId);
  }

  const url = `/api/v1/companies/${companyId}/detail${params.toString() ? `?${params.toString()}` : ''}`;
  const resp = await fetch(url, { credentials: 'include' });

  if (!resp.ok) {
    throw new Error(`Failed to fetch company detail: ${resp.status}`);
  }

  return resp.json() as Promise<CompanyDetailResponse>;
}

export function companyDetailQueryKey(companyId: string, profileId?: string) {
  return ['companyDetail', companyId, profileId ?? null] as const;
}

export interface UseCompanyDetailOptions {
  companyId: string;
  profileId?: string;
}

export function useCompanyDetail({ companyId, profileId }: UseCompanyDetailOptions) {
  return useQuery({
    queryKey: companyDetailQueryKey(companyId, profileId),
    queryFn: () => fetchCompanyDetail(companyId, profileId),
    staleTime: COMPANY_DETAIL_STALE_MS,
    enabled: !!companyId,
  });
}
