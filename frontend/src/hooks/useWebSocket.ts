'use client';

import { useEffect, useRef, useCallback, useState } from 'react';
import { getWebSocketUrl } from '@/lib/api';

export interface WSEvent {
  type: string;
  agent?: string;
  content?: string;
  metadata?: Record<string, unknown>;
  timestamp?: string;
}

export function useWebSocket(onEvent?: (event: WSEvent) => void) {
  const wsRef = useRef<WebSocket | null>(null);
  const [connected, setConnected] = useState(false);
  const reconnectTimer = useRef<NodeJS.Timeout | null>(null);
  const attemptRef = useRef(0);

  const connect = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) return;

    try {
      const ws = new WebSocket(getWebSocketUrl());

      ws.onopen = () => {
        setConnected(true);
        attemptRef.current = 0; // reset backoff on success
        console.log('[WS] Connected');
      };

      ws.onmessage = (event) => {
        try {
          const data: WSEvent = JSON.parse(event.data);
          onEvent?.(data);
        } catch (e) {
          console.warn('[WS] Parse error:', e);
        }
      };

      ws.onclose = () => {
        setConnected(false);
        // Exponential backoff: 3s, 6s, 12s, cap at 30s
        const delay = Math.min(3000 * Math.pow(2, attemptRef.current), 30000);
        attemptRef.current += 1;
        reconnectTimer.current = setTimeout(connect, delay);
      };

      ws.onerror = () => {
        // Silently close — onclose will handle reconnection
        ws.close();
      };

      wsRef.current = ws;
    } catch {
      const delay = Math.min(3000 * Math.pow(2, attemptRef.current), 30000);
      attemptRef.current += 1;
      reconnectTimer.current = setTimeout(connect, delay);
    }
  }, [onEvent]);

  useEffect(() => {
    connect();
    return () => {
      if (reconnectTimer.current) clearTimeout(reconnectTimer.current);
      wsRef.current?.close();
    };
  }, [connect]);

  // Ping to keep alive
  useEffect(() => {
    const interval = setInterval(() => {
      if (wsRef.current?.readyState === WebSocket.OPEN) {
        wsRef.current.send('ping');
      }
    }, 30000);
    return () => clearInterval(interval);
  }, []);

  return { connected };
}
