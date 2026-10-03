import React from 'react';

export interface UserTimestampProps {
  timestamp: string | Date;
  timeZone?: string;
  format?: 'full' | 'short' | 'date-only' | 'time-only';
  showZoneAbbr?: boolean;
  className?: string;
}

/**
 * User Localized Timestamp Component
 * Enforces BBP Section 31: "timestamps in the user's time zone with the zone displayed".
 */
export const UserTimestamp: React.FC<UserTimestampProps> = ({
  timestamp,
  timeZone,
  format = 'full',
  showZoneAbbr = true,
  className = '',
}) => {
  const dateObj = typeof timestamp === 'string' ? new Date(timestamp) : timestamp;

  // Detect browser local timezone if not explicitly provided
  const targetZone =
    timeZone ||
    (() => {
      try {
        return Intl.DateTimeFormat().resolvedOptions().timeZone;
      } catch {
        return 'UTC';
      }
    })();

  const formatOptions: Intl.DateTimeFormatOptions = {
    timeZone: targetZone,
    ...(format === 'full' && {
      year: 'numeric',
      month: 'short',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
      hour12: false,
    }),
    ...(format === 'short' && {
      year: 'numeric',
      month: 'short',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      hour12: false,
    }),
    ...(format === 'date-only' && {
      year: 'numeric',
      month: 'short',
      day: '2-digit',
    }),
    ...(format === 'time-only' && {
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
      hour12: false,
    }),
    ...(showZoneAbbr && { timeZoneName: 'short' }),
  };

  let formatted = '';
  try {
    formatted = new Intl.DateTimeFormat(undefined, formatOptions).format(dateObj);
  } catch {
    formatted = dateObj.toUTCString();
  }

  const isoUtc = dateObj.toISOString();

  return (
    <time
      dateTime={isoUtc}
      title={`UTC ISO: ${isoUtc} | Display Zone: ${targetZone}`}
      className={`cloudlens-timestamp ${className}`}
      style={{
        fontVariantNumeric: 'tabular-nums',
        fontFamily: 'monospace',
        fontSize: '0.8125rem',
        color: 'var(--text-primary)',
        whiteSpace: 'nowrap',
      }}
    >
      {formatted}
    </time>
  );
};
