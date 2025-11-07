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

const isRenderableMessage = (entry: unknown) => {
  const msg = entry as Record<string, unknown>;
  return (
    typeof msg?.role === 'string' &&
    typeof msg?.content === 'string' &&
    msg.content.trim().length > 0
  );
};

const toBubbles = (payload: unknown): ChatBubble[] => {
  const data = payload as Record<string, unknown>;
  if (!Array.isArray(data?.messages)) return [];

  return data.messages
    .filter(isRenderableMessage)
    .map((message: unknown, index: number) => {
      const msg = message as Record<string, unknown>;
      return {
        id: `history-${index}`,
        role: msg.role as string,
        text: formatEscapeCharacters(msg.content as string),
        timestamp: typeof msg.timestamp === 'string' ? msg.timestamp : null,
      };
    });
};

export default function Page() {
  const { settings, saveSettings } = useSettings();
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
    } catch (err: unknown) {
      if (err instanceof Error && err.name === 'AbortError') return;
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
      const existingTimezone = typeof window !== 'undefined'
        ? localStorage.getItem('user_timezone')
        : null;
      if (existingTimezone) return;
      
      try {
        const browserTimezone = Intl.DateTimeFormat().resolvedOptions().timeZone;
        
        // Send to server
        const response = await fetch('/api/timezone', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ timezone: browserTimezone }),
        });
        
        if (response.ok) {
          // Update localStorage only, don't persist the whole profile
          // (profile might not be loaded yet from backend)
          try {
            localStorage.setItem('user_timezone', browserTimezone);
          } catch {
            console.debug('Failed to save timezone to localStorage');
          }
        }
      } catch (error) {
        // Fail silently - timezone detection is not critical
        console.debug('Timezone detection failed:', error);
      }
    };

    void detectAndStoreTimezone();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []); // Run once on mount


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
        timestamp: new Date().toISOString(),
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
      } catch (err: unknown) {
        console.error('Failed to send message', err);
        const errorMessage = err instanceof Error ? err.message : 'Failed to send message';
        setError(errorMessage);
        // Remove the optimistic message on error
        setMessages(prev => prev.filter(msg => msg.id !== userMessage.id));
        setIsWaitingForResponse(false);
        throw err instanceof Error ? err : new Error('Failed to send message');
      } finally {
        // Poll until we get the assistant's response
        let pollAttempts = 0;
        const maxPollAttempts = 30; // Max 30 attempts (30 seconds)
        
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
    <main className="chat-bg flex h-full flex-col p-1 sm:p-2 md:p-6">
      <div className="chat-wrap flex h-full flex-col">
        <ChatHeader onOpenSettings={openSettings} />

        <div className="card flex flex-1 flex-col overflow-hidden">
          <ChatMessages
            messages={messages}
            isWaitingForResponse={isWaitingForResponse}
            scrollContainerRef={scrollContainerRef}
            onScroll={handleScroll}
          />

          <div className="border-t border-gray-200 px-1 pt-1 pb-[calc(env(safe-area-inset-bottom)+0.25rem)] sm:px-2 sm:pt-2 sm:pb-[calc(env(safe-area-inset-bottom)+0.5rem)] md:px-3 md:pt-3 md:pb-[calc(env(safe-area-inset-bottom)+0.75rem)]">
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

        <SettingsModal open={open} onClose={closeSettings} settings={settings} onSave={saveSettings} />
      </div>
    </main>
  );
}
