import { describe, it, expect, vi, afterEach } from 'vitest';
import * as client from '@/lib/api/client';

describe('qaApi', () => {
  afterEach(() => vi.restoreAllMocks());

  describe('createQASession', () => {
    it('calls api() for POST /qa/sessions', async () => {
      const mockResponse = { session_id: 'sess-1' };
      const spy = vi.spyOn(client, 'api').mockResolvedValue(mockResponse);
      const { createQASession } = await import('./qaApi');
      const result = await createQASession();
      expect(spy).toHaveBeenCalledWith('/qa/sessions', expect.objectContaining({ method: 'POST' }));
      expect(result).toEqual(mockResponse);
    });
  });

  describe('submitQuestionFetch', () => {
    it('includes Authorization header from getAccessToken()', async () => {
      vi.spyOn(client, 'getAccessToken').mockReturnValue('tok-abc');
      const mockFetch = vi.fn().mockResolvedValue({
        ok: true,
        body: { getReader: () => ({ read: vi.fn().mockResolvedValue({ done: true }) }) },
      });
      vi.stubGlobal('fetch', mockFetch);

      const { submitQuestionFetch } = await import('./qaApi');
      await submitQuestionFetch('sess-1', 'What is risk?');

      const [, init] = mockFetch.mock.calls[0] as [string, RequestInit];
      const headers = new Headers(init.headers as HeadersInit);
      expect(headers.get('authorization')).toBe('Bearer tok-abc');
    });

    it('does not include credentials: include (POST+SSE uses bearer only)', async () => {
      vi.spyOn(client, 'getAccessToken').mockReturnValue('tok-abc');
      const mockFetch = vi.fn().mockResolvedValue({
        ok: true,
        body: { getReader: () => ({ read: vi.fn().mockResolvedValue({ done: true }) }) },
      });
      vi.stubGlobal('fetch', mockFetch);

      const { submitQuestionFetch } = await import('./qaApi');
      await submitQuestionFetch('sess-1', 'test');

      const [, init] = mockFetch.mock.calls[0] as [string, RequestInit];
      expect((init as Record<string, unknown>).credentials).toBeUndefined();
    });
  });
});
