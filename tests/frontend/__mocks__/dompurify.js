/**
 * Manual mock for dompurify used in Jest tests.
 * Strips script tags to simulate sanitization behavior.
 */
const DOMPurify = {
  sanitize: (html) => {
    if (typeof html !== 'string') return '';
    // Strip script tags
    return html.replace(/<script\b[^<]*(?:(?!<\/script>)<[^<]*)*<\/script>/gi, '');
  },
};

module.exports = DOMPurify;
