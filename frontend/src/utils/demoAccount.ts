/**
 * Utility for detecting demo and simulated user accounts.
 * Real SMTP delivery is disabled for demo accounts to prevent email bounces.
 */

export const DEMO_DOMAINS = [
  'pacific-shipping.com',
  'rotterdam-logistics.nl',
  'globalmaritime.org',
  'example.com',
  'test.com',
  'maritime.com',
];

export function isDemoAccount(email?: string | null): boolean {
  if (!email) return false;
  const clean = email.trim().toLowerCase();
  return (
    DEMO_DOMAINS.some((domain) => clean.endsWith(`@${domain}`)) ||
    clean.startsWith('demo@') ||
    clean.startsWith('test@') ||
    clean === 'mock-user'
  );
}
