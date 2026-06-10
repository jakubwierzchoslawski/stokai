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
import { api } from '@/lib/api/client';

const COMPANY_DETAIL_STALE_MS = 60_000;

async function fetchCompanyDetail(
  companyId: string,
  profileId?: string,
): Promise<CompanyDetailResponse> {
  const params = new URLSearchParams();
  if (profileId) {
    params.set('profile_id', profileId);
  }
  const qs = params.toString();
  return api<CompanyDetailResponse>(
    '/companies/' + companyId + '/detail' + (qs ? '?' + qs : ''),
  );
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
