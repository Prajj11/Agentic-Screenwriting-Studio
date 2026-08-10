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

  const connect = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) return;

    try {
      const ws = new WebSocket(getWebSocketUrl());

      ws.onopen = () => {
        setConnected(true);
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
        console.log('[WS] Disconnected, reconnecting in 3s...');
        reconnectTimer.current = setTimeout(connect, 3000);
      };

      ws.onerror = (err) => {
        console.warn('[WS] Error:', err);
        ws.close();
      };

      wsRef.current = ws;
    } catch {
      reconnectTimer.current = setTimeout(connect, 3000);
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
