import clsx from 'clsx';
import { RefObject } from 'react';

import type { ChatBubble } from './types';

const TIMESTAMP_FORMATTER = new Intl.DateTimeFormat(undefined, {
  month: 'short',
  day: 'numeric',
  hour: '2-digit',
  minute: '2-digit',
});

function parseTimestamp(raw?: string | null): Date | null {
  if (!raw) return null;
  const candidate = raw.trim();
  if (!candidate) return null;

  const normalized = candidate.replace(' ', 'T');
  const parsed = new Date(normalized);
  if (!Number.isNaN(parsed.getTime())) {
    return parsed;
  }

  const match = candidate.match(
    /^(\d{4})-(\d{2})-(\d{2})[ T](\d{2}):(\d{2})(?::(\d{2}))?$/,
  );
  if (!match) return null;

  const [, year, month, day, hour, minute, second = '0'] = match;
  return new Date(
    Number(year),
    Number(month) - 1,
    Number(day),
    Number(hour),
    Number(minute),
    Number(second),
  );
}

function formatTimestamp(raw?: string | null): string | null {
  const parsed = parseTimestamp(raw);
  return parsed ? TIMESTAMP_FORMATTER.format(parsed) : null;
}

interface ChatMessagesProps {
  messages: ReadonlyArray<ChatBubble>;
  isWaitingForResponse: boolean;
  scrollContainerRef: RefObject<HTMLDivElement | null>;
  onScroll: () => void;
}

export function ChatMessages({ messages, isWaitingForResponse, scrollContainerRef, onScroll }: ChatMessagesProps) {
  return (
    <div ref={scrollContainerRef} onScroll={onScroll} className="flex flex-1 flex-col gap-3 overflow-x-hidden overflow-y-auto p-2 sm:gap-2 sm:p-3 sm:px-4">
      {messages.length === 0 && <EmptyState />}

      {messages.map((message, index) => {
        const isUser = message.role === 'user';
        const isDraft = message.role === 'draft';
        const next = messages[index + 1];
        const tail = !next || next.role !== message.role;
        const formattedTimestamp = !isDraft ? formatTimestamp(message.timestamp) : null;

        return (
          <div key={message.id} className={clsx('flex', isUser ? 'justify-end' : 'justify-start')}>
            <div className={clsx('flex min-w-0 flex-col', isUser ? 'items-end' : 'items-start')}>
              <div
                className={clsx(
                  isUser ? 'bubble-out' : 'bubble-in',
                  tail ? (isUser ? 'bubble-tail-out' : 'bubble-tail-in') : '',
                  isDraft && 'whitespace-pre-wrap',
                )}
              >
                <span className={isDraft ? 'block break-words whitespace-pre-wrap' : 'break-words whitespace-pre-wrap'}>{message.text}</span>
              </div>
              {formattedTimestamp && (
                <span className={clsx('mt-1 text-xs text-gray-400', isUser ? 'text-right' : 'text-left', 'px-1 sm:px-0')}>
                  {formattedTimestamp}
                </span>
              )}
            </div>
          </div>
        );
      })}

      {isWaitingForResponse && <TypingIndicator />}
    </div>
  );
}

function TypingIndicator() {
  return (
    <div className="flex justify-start">
      <div className="bubble-in bubble-tail-in">
        <div className="flex items-center space-x-1">
          <div className="flex space-x-1">
            <div className="h-2 w-2 animate-bounce rounded-full bg-gray-400 [animation-delay:-0.3s]"></div>
            <div className="h-2 w-2 animate-bounce rounded-full bg-gray-400 [animation-delay:-0.15s]"></div>
            <div className="h-2 w-2 animate-bounce rounded-full bg-gray-400"></div>
          </div>
        </div>
      </div>
    </div>
  );
}

function EmptyState() {
  return (
    <div className="mx-auto my-12 max-w-sm text-center text-gray-500">
      <h2 className="mb-2 text-xl font-semibold text-gray-700">Start a conversation</h2>
      <p className="text-sm">
        Your messages will appear here. Send something to get started.
      </p>
    </div>
  );
}
