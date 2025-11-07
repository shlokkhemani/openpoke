"use client";
import { useCallback, useEffect, useMemo, useState } from 'react';

export type Settings = {
  timezone: string;
  userName: string;
  birthDate: string;
  location: string;
};

export function useSettings() {
  const [settings, setSettings] = useState<Settings>({
    timezone: '',
    userName: '',
    birthDate: '',
    location: ''
  });

  useEffect(() => {
    // Fetch from backend FIRST (source of truth)
    fetch('/api/profile/load')
      .then(res => res.json())
      .then(data => {
        const timezone = localStorage.getItem('user_timezone') || '';

        if (data.ok && data.profile) {
          const profile = data.profile;
          // Backend is the source of truth
          const updatedSettings = {
            timezone,
            userName: profile.userName || '',
            birthDate: profile.birthDate || '',
            location: profile.location || ''
          };
          setSettings(updatedSettings);

          // Sync to localStorage for offline access
          try {
            if (profile.userName) localStorage.setItem('user_name', profile.userName);
            if (profile.birthDate) localStorage.setItem('user_birth_date', profile.birthDate);
            if (profile.location) localStorage.setItem('user_location', profile.location);
          } catch {}
        } else {
          // Fallback to localStorage only if backend fails
          try {
            const userName = localStorage.getItem('user_name') || '';
            const birthDate = localStorage.getItem('user_birth_date') || '';
            const location = localStorage.getItem('user_location') || '';
            setSettings({ timezone, userName, birthDate, location });
          } catch {}
        }
      })
      .catch(() => {
        // If backend is unreachable, use localStorage as fallback
        try {
          const timezone = localStorage.getItem('user_timezone') || '';
          const userName = localStorage.getItem('user_name') || '';
          const birthDate = localStorage.getItem('user_birth_date') || '';
          const location = localStorage.getItem('user_location') || '';
          setSettings({ timezone, userName, birthDate, location });
        } catch {}
      });
  }, []);

  const persistAndSave = useCallback(async (s: Settings) => {
    // Update React state
    setSettings(s);

    try {
      // Update localStorage
      localStorage.setItem('user_timezone', s.timezone);
      localStorage.setItem('user_name', s.userName);
      localStorage.setItem('user_birth_date', s.birthDate);
      localStorage.setItem('user_location', s.location);

      // Save profile to backend
      await fetch('/api/profile/save', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          userName: s.userName,
          birthDate: s.birthDate,
          location: s.location,
        }),
      });
    } catch (error) {
      console.error('Failed to save profile:', error);
    }
  }, []);

  return { settings, updateSettings: setSettings, saveSettings: persistAndSave } as const;
}

function coerceEmailFrom(value: unknown): string | null {
  if (typeof value === 'string' && value.includes('@')) {
    return value;
  }
  if (value && typeof value === 'object') {
    const obj = value as Record<string, unknown>;
    const candidate =
      obj.emailAddress ??
      obj.email ??
      obj.value ??
      obj.address;
    if (typeof candidate === 'string' && candidate.includes('@')) {
      return candidate;
    }
  }
  return null;
}

function deriveEmailFromPayload(payload: unknown): string {
  if (!payload || typeof payload !== 'object') return '';
  const data = payload as Record<string, unknown>;
  const profileSlice = data?.profile;
  const candidateObjects: Record<string, unknown>[] = [];

  if (profileSlice && typeof profileSlice === 'object') {
    const profile = profileSlice as Record<string, unknown>;
    candidateObjects.push(profile);
    if (profile.response_data && typeof profile.response_data === 'object') {
      candidateObjects.push(profile.response_data as Record<string, unknown>);
    }
    if (Array.isArray(profile.items)) {
      for (const entry of profile.items) {
        if (entry && typeof entry === 'object') {
          const item = entry as Record<string, unknown>;
          if (typeof item.data === 'object' && item.data !== null) {
            candidateObjects.push(item.data as Record<string, unknown>);
          }
          if (typeof item.response_data === 'object' && item.response_data !== null) {
            candidateObjects.push(item.response_data as Record<string, unknown>);
          }
          if (typeof item.profile === 'object' && item.profile !== null) {
            candidateObjects.push(item.profile as Record<string, unknown>);
          }
        }
      }
    }
  }

  const directCandidates = [data?.email];

  for (const obj of candidateObjects) {
    if (!obj || typeof obj !== 'object') continue;
    const record = obj as Record<string, unknown>;
    const profile = record?.profile as Record<string, unknown> | undefined;
    const user = record?.user as Record<string, unknown> | undefined;
    const objData = record?.data as Record<string, unknown> | undefined;
    directCandidates.push(
      record?.email,
      record?.email_address,
      record?.emailAddress,
      profile?.email,
      profile?.emailAddress,
      profile?.email_address,
      user?.email,
      user?.emailAddress,
      user?.email_address,
      objData?.email,
      objData?.emailAddress,
      objData?.email_address,
    );
    const emailAddresses = record.emailAddresses;
    if (Array.isArray(emailAddresses)) {
      for (const entry of emailAddresses) {
        const entryObj = entry as Record<string, unknown> | undefined;
        const email = coerceEmailFrom(entry) ?? coerceEmailFrom(entryObj?.value);
        if (email) return email;
      }
    }
  }

  for (const candidate of directCandidates) {
    const email = coerceEmailFrom(candidate);
    if (email) return email;
  }

  return '';
}

export default function SettingsModal({
  open,
  onClose,
  settings,
  onSave,
}: {
  open: boolean;
  onClose: () => void;
  settings: Settings;
  onSave: (s: Settings) => void;
}) {
  const [timezone, setTimezone] = useState(settings.timezone);
  const [userName, setUserName] = useState(settings.userName);
  const [birthDate, setBirthDate] = useState(settings.birthDate);
  const [location, setLocation] = useState(settings.location);
  
  // Gmail states
  const [connectingGmail, setConnectingGmail] = useState(false);
  const [isRefreshingGmail, setIsRefreshingGmail] = useState(false);
  const [isDisconnecting, setIsDisconnecting] = useState(false);
  const [gmailStatusMessage, setGmailStatusMessage] = useState('');
  const [gmailConnected, setGmailConnected] = useState(false);
  const [gmailEmail, setGmailEmail] = useState('');
  const [gmailConnId, setGmailConnId] = useState('');
  const [gmailProfile, setGmailProfile] = useState<Record<string, unknown> | null>(null);

  // Calendar states
  const [connectingCalendar, setConnectingCalendar] = useState(false);
  const [isRefreshingCalendar, setIsRefreshingCalendar] = useState(false);
  const [isDisconnectingCalendar, setIsDisconnectingCalendar] = useState(false);
  const [calendarStatusMessage, setCalendarStatusMessage] = useState('');
  const [calendarConnected, setCalendarConnected] = useState(false);
  const [calendarEmail, setCalendarEmail] = useState('');
  const [calendarConnId, setCalendarConnId] = useState('');

  const readStoredUserId = useCallback(() => {
    if (typeof window === 'undefined') return '';
    try {
      return localStorage.getItem('alyn_user_id') || '';
    } catch {
      return '';
    }
  }, []);

  const ensureUserId = useCallback(() => {
    if (typeof window === 'undefined') {
      return `web-${Math.random().toString(36).slice(2)}`;
    }
    try {
      const existing = localStorage.getItem('alyn_user_id');
      if (existing) return existing;
      const cryptoObj = (globalThis as { crypto?: Crypto }).crypto;
      const randomPart =
        cryptoObj && typeof cryptoObj.randomUUID === 'function'
          ? cryptoObj.randomUUID().replace(/-/g, '')
          : Math.random().toString(36).slice(2);
      const generated = `web-${randomPart}`;
      localStorage.setItem('alyn_user_id', generated);
      return generated;
    } catch {
      return `web-${Math.random().toString(36).slice(2)}`;
    }
  }, []);

  const readStoredConnectionRequestId = useCallback(() => {
    if (gmailConnId) return gmailConnId;
    if (typeof window === 'undefined') return '';
    try {
      return localStorage.getItem('gmail_connection_request_id') || '';
    } catch {
      return '';
    }
  }, [gmailConnId]);

  useEffect(() => {
    try {
      // Gmail
      const savedConnected = localStorage.getItem('gmail_connected') === 'true';
      const savedConnId = localStorage.getItem('gmail_connection_request_id') || '';
      const savedEmail = localStorage.getItem('gmail_email') || '';
      setGmailConnected(savedConnected);
      setGmailConnId(savedConnId);
      setGmailEmail(savedEmail);
      if (savedConnected && savedEmail) {
        setGmailStatusMessage(`Connected as ${savedEmail}`);
      }

      // Calendar
      const savedCalendarConnected = localStorage.getItem('calendar_connected') === 'true';
      const savedCalendarEmail = localStorage.getItem('calendar_email') || '';
      setCalendarConnected(savedCalendarConnected);
      setCalendarEmail(savedCalendarEmail);
      if (savedCalendarConnected && savedCalendarEmail) {
        setCalendarStatusMessage(`Connected as ${savedCalendarEmail}`);
      }
    } catch {}
  }, []);

  const gmailProfileDetails = useMemo(() => {
    if (!gmailProfile) return [] as { label: string; value: string }[];
    const details: { label: string; value: string }[] = [];
    const messagesTotal = gmailProfile?.messagesTotal;
    if (typeof messagesTotal === 'number') {
      details.push({ label: 'Messages', value: messagesTotal.toLocaleString() });
    }
    const threadsTotal = gmailProfile?.threadsTotal;
    if (typeof threadsTotal === 'number') {
      details.push({ label: 'Threads', value: threadsTotal.toLocaleString() });
    }
    const historyId = gmailProfile?.historyId ?? gmailProfile?.historyID;
    if (historyId !== undefined && historyId !== null && historyId !== '') {
      details.push({ label: 'History ID', value: String(historyId) });
    }
    return details;
  }, [gmailProfile]);

  const handleConnectGmail = useCallback(async () => {
    try {
      setConnectingGmail(true);
      setGmailStatusMessage('');
      const userId = ensureUserId();
      const resp = await fetch('/api/gmail/connect', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ userId }),
      });
      const data = await resp.json().catch(() => ({}));
      if (!resp.ok || !data?.ok) {
        const msg = data?.error || `Failed (${resp.status})`;
        setGmailStatusMessage(msg);
        return;
      }
      const url = data?.redirect_url;
      const connId = data?.connection_request_id || '';
      if (connId) {
        setGmailConnId(connId);
        try {
          localStorage.setItem('gmail_connection_request_id', connId);
        } catch {}
      }
      setGmailConnected(false);
      setGmailEmail('');
      setGmailProfile(null);
      if (url) {
        // Check if we're on mobile/PWA
        const isMobile = /iPhone|iPad|iPod|Android/i.test(navigator.userAgent);
        const isPWA = window.matchMedia('(display-mode: standalone)').matches;

        if (isMobile || isPWA) {
          // On mobile/PWA, open in same window to avoid popup blockers
          window.location.href = url;
        } else {
          // On desktop, open in new tab
          window.open(url, '_blank', 'noopener');
          setGmailStatusMessage('Gmail authorization opened in a new tab. Complete it, then press "Refresh status".');
        }
      } else {
        setGmailStatusMessage('Connection initiated. Refresh status once authorization completes.');
      }
    } catch (e: unknown) {
      const message = e instanceof Error ? e.message : 'Failed to connect Gmail';
      setGmailStatusMessage(message);
    } finally {
      setConnectingGmail(false);
    }
  }, [ensureUserId]);

  const refreshGmailStatus = useCallback(async () => {
    const userId = readStoredUserId();
    const connectionRequestId = readStoredConnectionRequestId();
    if (!userId && !connectionRequestId) {
      setGmailConnected(false);
      setGmailProfile(null);
      setGmailEmail('');
      setGmailStatusMessage('Connect Gmail to get started.');
      return;
    }

    try {
      setIsRefreshingGmail(true);
      setGmailStatusMessage('Refreshing Gmail status…');
      const resp = await fetch('/api/gmail/status', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ userId, connectionRequestId }),
      });
      const data = await resp.json().catch(() => ({}));

      if (!resp.ok || !data?.ok) {
        const message = data?.error || `Failed (${resp.status})`;
        setGmailConnected(false);
        setGmailProfile(null);
        setGmailEmail('');
        setGmailStatusMessage(message);
        return;
      }

      if (!gmailConnId && connectionRequestId) {
        setGmailConnId(connectionRequestId);
      }

      const profileData = data?.profile && typeof data.profile === 'object' ? (data.profile as Record<string, unknown>) : null;
      setGmailProfile(profileData);

      const derivedEmail = deriveEmailFromPayload({ email: data?.email, profile: profileData });
      const email = derivedEmail || (typeof data?.email === 'string' ? data.email : '');
      const connected = Boolean(data?.connected);

      setGmailConnected(connected);
      setGmailEmail(email);

      if (connected) {
        const source = typeof data?.profile_source === 'string' ? data.profile_source : '';
        const sourceNote = source === 'fetched' ? 'Verified moments ago.' : source === 'cache' ? 'Loaded from cache.' : '';
        const message = email ? `Connected as ${email}` : 'Gmail connected.';
        setGmailStatusMessage(sourceNote ? `${message} ${sourceNote}` : message);
        try {
          localStorage.setItem('gmail_connected', 'true');
          if (email) localStorage.setItem('gmail_email', email);
          if (typeof data?.user_id === 'string' && data.user_id) {
            localStorage.setItem('alyn_user_id', data.user_id);
          }
        } catch {}
      } else {
        const statusText = typeof data?.status === 'string' && data.status && data.status !== 'UNKNOWN'
          ? `Status: ${data.status}`
          : 'Not connected yet.';
        setGmailStatusMessage(statusText);
        try {
          localStorage.removeItem('gmail_connected');
          localStorage.removeItem('gmail_email');
        } catch {}
      }
    } catch (e: unknown) {
      setGmailConnected(false);
      setGmailProfile(null);
      setGmailEmail('');
      const message = e instanceof Error ? e.message : 'Failed to check Gmail status';
      setGmailStatusMessage(message);
    } finally {
      setIsRefreshingGmail(false);
    }
  }, [gmailConnId, readStoredConnectionRequestId, readStoredUserId]);

  const handleDisconnectGmail = useCallback(async () => {
    if (typeof window !== 'undefined') {
      const proceed = window.confirm('Disconnect Gmail from Alyn?');
      if (!proceed) return;
    }

    try {
      setIsDisconnecting(true);
      setGmailStatusMessage('Disconnecting Gmail…');
      const userId = readStoredUserId();
      const connectionRequestId = readStoredConnectionRequestId();
      const resp = await fetch('/api/gmail/disconnect', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ userId, connectionRequestId }),
      });
      const data = await resp.json().catch(() => ({}));

      if (!resp.ok || !data?.ok) {
        const message = data?.error || `Failed (${resp.status})`;
        setGmailStatusMessage(message);
        return;
      }

      setGmailConnected(false);
      setGmailEmail('');
      setGmailProfile(null);
      setGmailConnId('');
      setGmailStatusMessage('Gmail disconnected.');
      try {
        localStorage.removeItem('gmail_connected');
        localStorage.removeItem('gmail_email');
        localStorage.removeItem('gmail_connection_request_id');
        localStorage.removeItem('alyn_user_id');
      } catch {}
    } catch (e: unknown) {
      const message = e instanceof Error ? e.message : 'Failed to disconnect Gmail';
      setGmailStatusMessage(message);
    } finally {
      setIsDisconnecting(false);
    }
  }, [readStoredConnectionRequestId, readStoredUserId]);

  // Calendar functions
  const handleConnectCalendar = useCallback(async () => {
    try {
      setConnectingCalendar(true);
      setCalendarStatusMessage('');
      const userId = ensureUserId();
      const resp = await fetch('/api/calendar/connect', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ userId }),
      });
      const data = await resp.json().catch(() => ({}));
      if (!resp.ok || !data?.ok) {
        const msg = data?.error || `Failed (${resp.status})`;
        setCalendarStatusMessage(msg);
        return;
      }
      const url = data?.redirect_url;
      const connId = data?.connection_request_id || '';
      if (connId) {
        setCalendarConnId(connId);
        try {
          localStorage.setItem('calendar_connection_request_id', connId);
        } catch {}
      }
      setCalendarConnected(false);
      setCalendarEmail('');
      if (url) {
        const isMobile = /iPhone|iPad|iPod|Android/i.test(navigator.userAgent);
        const isPWA = window.matchMedia('(display-mode: standalone)').matches;
        if (isMobile || isPWA) {
          window.location.href = url;
        } else {
          window.open(url, '_blank', 'noopener');
          setCalendarStatusMessage('Calendar authorization opened in a new tab. Complete it, then press "Refresh status".');
        }
      } else {
        setCalendarStatusMessage('Connection initiated. Refresh status once authorization completes.');
      }
    } catch (e: unknown) {
      const message = e instanceof Error ? e.message : 'Failed to connect Calendar';
      setCalendarStatusMessage(message);
    } finally {
      setConnectingCalendar(false);
    }
  }, [ensureUserId]);

  const refreshCalendarStatus = useCallback(async () => {
    const userId = readStoredUserId();
    const connectionRequestId = calendarConnId || (typeof window !== 'undefined' ? localStorage.getItem('calendar_connection_request_id') || '' : '');
    if (!userId && !connectionRequestId) {
      setCalendarConnected(false);
      setCalendarEmail('');
      setCalendarStatusMessage('Connect Calendar to get started.');
      return;
    }

    try {
      setIsRefreshingCalendar(true);
      setCalendarStatusMessage('Refreshing Calendar status…');
      const resp = await fetch('/api/calendar/status', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ userId, connectionRequestId }),
      });
      const data = await resp.json().catch(() => ({}));

      if (!resp.ok || !data?.ok) {
        const message = data?.error || `Failed (${resp.status})`;
        setCalendarConnected(false);
        setCalendarEmail('');
        setCalendarStatusMessage(message);
        return;
      }

      const email = typeof data?.email === 'string' ? data.email : '';
      const connected = Boolean(data?.connected || data?.status === 'active');

      setCalendarConnected(connected);
      setCalendarEmail(email);

      if (connected) {
        const message = email ? `Connected as ${email}` : 'Calendar connected.';
        setCalendarStatusMessage(message);
        try {
          localStorage.setItem('calendar_connected', 'true');
          if (email) localStorage.setItem('calendar_email', email);
        } catch {}
      } else {
        setCalendarStatusMessage('Not connected yet.');
        try {
          localStorage.removeItem('calendar_connected');
          localStorage.removeItem('calendar_email');
        } catch {}
      }
    } catch (e: unknown) {
      setCalendarConnected(false);
      setCalendarEmail('');
      const message = e instanceof Error ? e.message : 'Failed to check Calendar status';
      setCalendarStatusMessage(message);
    } finally {
      setIsRefreshingCalendar(false);
    }
  }, [calendarConnId, readStoredUserId]);

  const handleDisconnectCalendar = useCallback(async () => {
    if (typeof window !== 'undefined') {
      const proceed = window.confirm('Disconnect Calendar from Alyn?');
      if (!proceed) return;
    }

    try {
      setIsDisconnectingCalendar(true);
      setCalendarStatusMessage('Disconnecting Calendar…');
      const userId = readStoredUserId();
      const connectionRequestId = calendarConnId || (typeof window !== 'undefined' ? localStorage.getItem('calendar_connection_request_id') || '' : '');
      const resp = await fetch('/api/calendar/disconnect', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ userId, connectionRequestId }),
      });
      const data = await resp.json().catch(() => ({}));

      if (!resp.ok || !data?.ok) {
        const message = data?.error || `Failed (${resp.status})`;
        setCalendarStatusMessage(message);
        return;
      }

      setCalendarConnected(false);
      setCalendarEmail('');
      setCalendarConnId('');
      setCalendarStatusMessage('Calendar disconnected.');
      try {
        localStorage.removeItem('calendar_connected');
        localStorage.removeItem('calendar_email');
        localStorage.removeItem('calendar_connection_request_id');
      } catch {}
    } catch (e: unknown) {
      const message = e instanceof Error ? e.message : 'Failed to disconnect Calendar';
      setCalendarStatusMessage(message);
    } finally {
      setIsDisconnectingCalendar(false);
    }
  }, [calendarConnId, readStoredUserId]);

  useEffect(() => {
    setTimezone(settings.timezone);
    setUserName(settings.userName);
    setBirthDate(settings.birthDate);
    setLocation(settings.location);
  }, [settings]);

  useEffect(() => {
    if (!open) return;
    void refreshGmailStatus();
    void refreshCalendarStatus();
  }, [open, refreshGmailStatus, refreshCalendarStatus]);

  if (!open) return null;

  const connectButtonLabel = connectingGmail ? 'Opening…' : gmailConnected ? 'Reconnect' : 'Connect Gmail';
  const refreshButtonLabel = isRefreshingGmail ? 'Refreshing…' : 'Refresh status';
  const disconnectButtonLabel = isDisconnecting ? 'Disconnecting…' : 'Disconnect';

  const connectCalendarButtonLabel = connectingCalendar ? 'Opening…' : calendarConnected ? 'Reconnect' : 'Connect Calendar';
  const refreshCalendarButtonLabel = isRefreshingCalendar ? 'Refreshing…' : 'Refresh status';
  const disconnectCalendarButtonLabel = isDisconnectingCalendar ? 'Disconnecting…' : 'Disconnect';

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 p-3 sm:p-4">
      <div className="card w-full max-w-lg max-h-[95vh] overflow-y-auto p-4 sm:p-6">
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-lg sm:text-xl font-semibold">Settings</h2>
          <button onClick={onClose} className="rounded-md p-2 hover:bg-gray-100 touch-manipulation" aria-label="Close settings">
            ✕
          </button>
        </div>
        <div className="space-y-5">
          <div>
            <div className="mb-3 text-sm font-medium text-gray-700">Profile Information</div>
            <div className="space-y-4 rounded-xl border border-gray-200 bg-white/70 p-4">
              <div>
                <label className="mb-2 block text-sm font-medium text-gray-700">Your Name</label>
                <input
                  className="input text-base min-h-[44px]"
                  type="text"
                  value={userName}
                  onChange={(e) => setUserName(e.target.value)}
                  placeholder="e.g. Joseph"
                />
              </div>
              <div>
                <label className="mb-2 block text-sm font-medium text-gray-700">Date of Birth</label>
                <input
                  className="input text-base min-h-[44px]"
                  type="date"
                  value={birthDate}
                  onChange={(e) => setBirthDate(e.target.value)}
                />
              </div>
              <div>
                <label className="mb-2 block text-sm font-medium text-gray-700">Location</label>
                <input
                  className="input text-base min-h-[44px]"
                  type="text"
                  value={location}
                  onChange={(e) => setLocation(e.target.value)}
                  placeholder="e.g. San Francisco, CA"
                />
              </div>
              <p className="text-xs text-gray-500">
                This information helps Alyn provide more personalized assistance.
              </p>
            </div>
          </div>
          <div>
            <label className="mb-2 block text-sm font-medium text-gray-700">Timezone</label>
            <input
              className="input text-base min-h-[44px]"
              type="text"
              value={timezone}
              onChange={(e) => setTimezone(e.target.value)}
              placeholder="e.g. America/New_York, Europe/London"
              readOnly={!timezone}
            />
            <p className="mt-2 text-xs text-gray-500">
              {timezone ? 'Auto-detected from browser. Edit to override.' : 'Will be auto-detected on next page load.'}
            </p>
          </div>
          <div className="pt-2">
            <div className="mb-1 text-sm font-medium text-gray-700">Integrations</div>
            <div className="rounded-xl border border-gray-200 bg-white/70 p-4 shadow-sm">
              <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                <div>
                  <div className="text-sm font-semibold text-gray-900">Gmail (via Composio)</div>
                  <p className="mt-1 text-sm text-gray-600">
                    Connect Gmail to unlock email search, drafting, and automations inside Alyn.
                  </p>
                </div>
                <span
                  className={`inline-flex items-center rounded-full px-3 py-1 text-xs font-medium ring-1 ring-inset ${
                    gmailConnected
                      ? 'bg-emerald-50 text-emerald-700 ring-emerald-200'
                      : 'bg-amber-50 text-amber-700 ring-amber-200'
                  }`}
                >
                  {gmailConnected ? 'Connected' : 'Not connected'}
                </span>
              </div>

              {gmailConnected ? (
                <div className="mt-4 space-y-3 rounded-lg border border-gray-100 bg-gray-50 p-3">
                  <div>
                    <div className="text-[11px] uppercase tracking-wide text-gray-500">Connected account</div>
                    <div className="mt-1 text-sm font-medium text-gray-900">{gmailEmail || 'Email unavailable'}</div>
                  </div>
                  {gmailProfileDetails.length > 0 && (
                    <dl className="grid grid-cols-1 gap-2 text-xs text-gray-600 sm:grid-cols-3">
                      {gmailProfileDetails.map((item) => (
                        <div key={item.label} className="rounded-md border border-gray-200 bg-white/80 p-2">
                          <dt className="text-[10px] font-semibold uppercase tracking-wide text-gray-500">{item.label}</dt>
                          <dd className="mt-1 text-sm font-medium text-gray-900">{item.value}</dd>
                        </div>
                      ))}
                    </dl>
                  )}
                  {gmailStatusMessage && (
                    <p className="text-xs text-gray-500" aria-live="polite">{gmailStatusMessage}</p>
                  )}
                </div>
              ) : (
                <div className="mt-4 rounded-lg border border-dashed border-gray-200 p-3 text-sm text-gray-500" aria-live="polite">
                  {gmailStatusMessage || 'Complete the connection to view your Gmail account details here.'}
                </div>
              )}

              <div className="mt-4 flex flex-col sm:flex-row sm:flex-wrap gap-2">
                <button
                  type="button"
                  className="btn min-h-[44px] touch-manipulation"
                  onClick={handleConnectGmail}
                  disabled={connectingGmail || isRefreshingGmail || isDisconnecting}
                  aria-busy={connectingGmail}
                >
                  {connectButtonLabel}
                </button>
                <button
                  type="button"
                  className="rounded-md border border-gray-200 px-4 py-2.5 min-h-[44px] text-sm font-medium text-gray-700 hover:bg-gray-100 disabled:cursor-not-allowed disabled:opacity-60 touch-manipulation"
                  onClick={refreshGmailStatus}
                  disabled={isRefreshingGmail || connectingGmail}
                  aria-busy={isRefreshingGmail}
                >
                  {refreshButtonLabel}
                </button>
                {gmailConnected && (
                  <button
                    type="button"
                    className="rounded-md border border-transparent bg-red-50 px-4 py-2.5 min-h-[44px] text-sm font-medium text-red-600 hover:bg-red-100 disabled:cursor-not-allowed disabled:opacity-60 touch-manipulation"
                    onClick={handleDisconnectGmail}
                    disabled={isDisconnecting || connectingGmail}
                    aria-busy={isDisconnecting}
                  >
                    {disconnectButtonLabel}
                  </button>
                )}
              </div>
            </div>
          </div>

          {/* Google Calendar Integration */}
          <div className="pt-2">
            <div className="rounded-xl border border-gray-200 bg-white/70 p-4 shadow-sm">
              <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                <div>
                  <div className="text-sm font-semibold text-gray-900">Google Calendar (via Composio)</div>
                  <p className="mt-1 text-sm text-gray-600">
                    Connect Calendar to manage events, check availability, and schedule meetings.
                  </p>
                </div>
                <span
                  className={`inline-flex items-center rounded-full px-3 py-1 text-xs font-medium ring-1 ring-inset ${
                    calendarConnected
                      ? 'bg-emerald-50 text-emerald-700 ring-emerald-200'
                      : 'bg-amber-50 text-amber-700 ring-amber-200'
                  }`}
                >
                  {calendarConnected ? 'Connected' : 'Not connected'}
                </span>
              </div>

              {calendarConnected ? (
                <div className="mt-4 space-y-3 rounded-lg border border-gray-100 bg-gray-50 p-3">
                  <div>
                    <div className="text-[11px] uppercase tracking-wide text-gray-500">Connected account</div>
                    <div className="mt-1 text-sm font-medium text-gray-900">{calendarEmail || 'Email unavailable'}</div>
                  </div>
                  {calendarStatusMessage && (
                    <p className="text-xs text-gray-500" aria-live="polite">{calendarStatusMessage}</p>
                  )}
                </div>
              ) : (
                <div className="mt-4 rounded-lg border border-dashed border-gray-200 p-3 text-sm text-gray-500" aria-live="polite">
                  {calendarStatusMessage || 'Complete the connection to view your Calendar account details here.'}
                </div>
              )}

              <div className="mt-4 flex flex-col sm:flex-row sm:flex-wrap gap-2">
                <button
                  type="button"
                  className="btn min-h-[44px] touch-manipulation"
                  onClick={handleConnectCalendar}
                  disabled={connectingCalendar || isRefreshingCalendar || isDisconnectingCalendar}
                  aria-busy={connectingCalendar}
                >
                  {connectCalendarButtonLabel}
                </button>
                <button
                  type="button"
                  className="rounded-md border border-gray-200 px-4 py-2.5 min-h-[44px] text-sm font-medium text-gray-700 hover:bg-gray-100 disabled:cursor-not-allowed disabled:opacity-60 touch-manipulation"
                  onClick={refreshCalendarStatus}
                  disabled={isRefreshingCalendar || connectingCalendar}
                  aria-busy={isRefreshingCalendar}
                >
                  {refreshCalendarButtonLabel}
                </button>
                {calendarConnected && (
                  <button
                    type="button"
                    className="rounded-md border border-transparent bg-red-50 px-4 py-2.5 min-h-[44px] text-sm font-medium text-red-600 hover:bg-red-100 disabled:cursor-not-allowed disabled:opacity-60 touch-manipulation"
                    onClick={handleDisconnectCalendar}
                    disabled={isDisconnectingCalendar || connectingCalendar}
                    aria-busy={isDisconnectingCalendar}
                  >
                    {disconnectCalendarButtonLabel}
                  </button>
                )}
              </div>
            </div>
          </div>
        </div>

        <div className="mt-6 flex flex-col-reverse sm:flex-row justify-end gap-2">
          <button
            onClick={onClose}
            className="rounded-md px-4 py-2.5 min-h-[44px] text-sm font-medium text-gray-700 hover:bg-gray-100 touch-manipulation border border-gray-200"
          >
            Cancel
          </button>
          <button
            className="btn min-h-[44px] touch-manipulation"
            onClick={() => {
              onSave({ timezone, userName, birthDate, location });
              onClose();
            }}
          >
            Save
          </button>
        </div>
      </div>
    </div>
  );
}
