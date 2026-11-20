'use client';

import { useCallback, useEffect, useState } from 'react';
import SettingsModal, { useSettings } from '@/components/SettingsModal';
import { ChatHeader } from '@/components/chat/ChatHeader';
import { ChatInput } from '@/components/chat/ChatInput';
import { ChatMessages } from '@/components/chat/ChatMessages';
import { ErrorBanner } from '@/components/chat/ErrorBanner';
import { useAutoScroll } from '@/components/chat/useAutoScroll';
import type { ChatBubble } from '@/components/chat/types';

const POLL_INTERVAL_MS = 1500;

const formatEscapeCharacters = (text: string): string => {
  return text
    .replace(/\\n/g, '\n')
    .replace(/\\t/g, '\t')
    .replace(/\\r/g, '\r')
    .replace(/\\\\/g, '\\');
};

const isRenderableMessage = (entry: any) =>
  typeof entry?.role === 'string' &&
  typeof entry?.content === 'string' &&
  entry.content.trim().length > 0;

const toBubbles = (payload: any): ChatBubble[] => {
  if (!Array.isArray(payload?.messages)) return [];

  return payload.messages
    .filter(isRenderableMessage)
    .map((message: any, index: number) => ({
      id: `history-${index}`,
      role: message.role,
      text: formatEscapeCharacters(message.content),
    }));
};

export default function Page() {
  const { settings, setSettings } = useSettings();
  const [open, setOpen] = useState(false);
  const [input, setInput] = useState('');
  const [messages, setMessages] = useState<ChatBubble[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [isWaitingForResponse, setIsWaitingForResponse] = useState(false);
  const { scrollContainerRef, handleScroll } = useAutoScroll({
    items: messages,
    isWaiting: isWaitingForResponse,
  });
  const openSettings = useCallback(() => setOpen(true), [setOpen]);
  const closeSettings = useCallback(() => setOpen(false), [setOpen]);

  const loadHistory = useCallback(async () => {
    try {
      const res = await fetch('/api/chat/history', { cache: 'no-store' });
      if (!res.ok) return;
      const data = await res.json();
      setMessages(toBubbles(data));
    } catch (err: any) {
      if (err?.name === 'AbortError') return;
      console.error('Failed to load chat history', err);
    }
  }, []);

  useEffect(() => {
    void loadHistory();
  }, [loadHistory]);

  // Detect and store browser timezone on first load
  useEffect(() => {
    const detectAndStoreTimezone = async () => {
      // Only run if timezone not already stored
      if (settings.timezone) return;
      
      try {
        const browserTimezone = Intl.DateTimeFormat().resolvedOptions().timeZone;
        
        // Send to server
        const response = await fetch('/api/timezone', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ timezone: browserTimezone }),
        });
        
        if (response.ok) {
          // Update local settings
          setSettings({ ...settings, timezone: browserTimezone });
        }
      } catch (error) {
        // Fail silently - timezone detection is not critical
        console.debug('Timezone detection failed:', error);
      }
    };

    void detectAndStoreTimezone();
  }, [settings, setSettings]);


  useEffect(() => {
    const intervalId = window.setInterval(() => {
      void loadHistory();
    }, POLL_INTERVAL_MS);

    return () => window.clearInterval(intervalId);
  }, [loadHistory]);

  const canSubmit = input.trim().length > 0;
  const inputPlaceholder = 'Type a message…';

  const sendMessage = useCallback(
    async (text: string) => {
      const trimmed = text.trim();
      if (!trimmed) return;

      setError(null);
      setIsWaitingForResponse(true);

      // Optimistically add the user message immediately
      const userMessage: ChatBubble = {
        id: `user-${Date.now()}`,
        role: 'user',
        text: formatEscapeCharacters(trimmed),
      };
      setMessages(prev => {
        const newMessages = [...prev, userMessage];
        return newMessages;
      });

      try {
        const res = await fetch('/api/chat', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            messages: [{ role: 'user', content: trimmed }],
          }),
        });

        if (!(res.ok || res.status === 202)) {
          const detail = await res.text();
          throw new Error(detail || `Request failed (${res.status})`);
        }
      } catch (err: any) {
        console.error('Failed to send message', err);
        setError(err?.message || 'Failed to send message');
        // Remove the optimistic message on error
        setMessages(prev => prev.filter(msg => msg.id !== userMessage.id));
        setIsWaitingForResponse(false);
        throw err instanceof Error ? err : new Error('Failed to send message');
      } finally {
        // Poll until we get the assistant's response
        let pollAttempts = 0;
        const maxPollAttempts = 120; // Max 120 attempts (2 minutes)
        
        const pollForAssistantResponse = async () => {
          pollAttempts++;
          
          try {
            const res = await fetch('/api/chat/history', { cache: 'no-store' });
            if (res.ok) {
              const data = await res.json();
              const currentMessages = toBubbles(data);
              
              // Check if the last message is from assistant and contains our user message
              const lastMessage = currentMessages[currentMessages.length - 1];
              const hasUserMessage = currentMessages.some(msg => msg.text === trimmed && msg.role === 'user');
              const hasAssistantResponse = lastMessage?.role === 'assistant' && hasUserMessage;
              
              if (hasAssistantResponse) {
                // We got the assistant response, update messages and stop loading
                setMessages(currentMessages);
                setIsWaitingForResponse(false);
                return;
              }
            }
          } catch (err) {
            console.error('Error polling for response:', err);
          }
          
          // Continue polling if we haven't exceeded max attempts
          if (pollAttempts < maxPollAttempts) {
            setTimeout(pollForAssistantResponse, 1000); // Poll every second
          } else {
            // Timeout - stop loading and update messages anyway
            setIsWaitingForResponse(false);
            await loadHistory();
          }
        };
        
        // Start polling after a brief delay
        setTimeout(pollForAssistantResponse, 1000);
      }
    },
    [loadHistory],
  );

  const handleClearHistory = useCallback(async () => {
    try {
      const res = await fetch('/api/chat/history', { method: 'DELETE' });
      if (!res.ok) {
        console.error('Failed to clear chat history', res.statusText);
        return;
      }
      setMessages([]);
    } catch (err) {
      console.error('Failed to clear chat history', err);
    }
  }, [setMessages]);

  const triggerClearHistory = useCallback(() => {
    void handleClearHistory();
  }, [handleClearHistory]);

  const handleSubmit = useCallback(async () => {
    if (!canSubmit) return;
    const value = input;
    setInput('');
    try {
      await sendMessage(value);
    } catch {
      setInput(value);
    }
  }, [canSubmit, input, sendMessage, setInput]);

  const handleInputChange = useCallback((value: string) => {
    setInput(value);
  }, [setInput]);

  const clearError = useCallback(() => setError(null), [setError]);

  return (
    <main className="chat-bg min-h-screen p-4 sm:p-6">
      <div className="chat-wrap flex flex-col">
        <ChatHeader onOpenSettings={openSettings} onClearHistory={triggerClearHistory} />

        <div className="card flex-1 overflow-hidden">
          <ChatMessages
            messages={messages}
            isWaitingForResponse={isWaitingForResponse}
            scrollContainerRef={scrollContainerRef}
            onScroll={handleScroll}
          />

          <div className="border-t border-gray-200 p-3">
            {error && <ErrorBanner message={error} onDismiss={clearError} />}

            <ChatInput
              value={input}
              canSubmit={canSubmit}
              placeholder={inputPlaceholder}
              onChange={handleInputChange}
              onSubmit={handleSubmit}
            />
          </div>
        </div>

        <SettingsModal open={open} onClose={closeSettings} settings={settings} onSave={setSettings} />
      </div>
    </main>
  );
}
