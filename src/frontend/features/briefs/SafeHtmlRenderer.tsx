/**
 * SafeHtmlRenderer — DOMPurify-sanitized HTML renderer for brief content.
 *
 * Sanitizes content_html before injecting as dangerouslySetInnerHTML to prevent
 * stored-XSS. Never bypasses sanitization even for system-generated content.
 *
 * PLAN-F-026 TASK-006
 */
import React from 'react';
// eslint-disable-next-line @typescript-eslint/no-explicit-any
const DOMPurify: any = require('dompurify');

interface SafeHtmlRendererProps {
  html: string;
  className?: string;
}

export function SafeHtmlRenderer({ html, className }: SafeHtmlRendererProps): React.ReactElement {
  const sanitized = DOMPurify.sanitize(html, {
    USE_PROFILES: { html: true },
    FORBID_TAGS: ['script', 'iframe', 'object', 'embed', 'form'],
    FORBID_ATTR: ['onerror', 'onload', 'onclick', 'onmouseover'],
  });

  return (
    <div
      className={className}
      // eslint-disable-next-line react/no-danger
      dangerouslySetInnerHTML={{ __html: sanitized }}
      data-testid="safe-html-renderer"
    />
  );
}

export default SafeHtmlRenderer;
