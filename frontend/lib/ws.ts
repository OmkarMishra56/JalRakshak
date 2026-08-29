"use client";
import { useEffect, useRef } from "react";

const WS_URL = process.env.NEXT_PUBLIC_WS_URL || "ws://localhost:8000/ws/zones";

export interface ZoneUpdateEvent {
  type: "zone_update";
  zone_id: string;
  code: string;
  name: string;
  score: number;
  status: "safe" | "moderate" | "severe";
  status_changed: boolean;
  updated_at: string;
}

export function useZoneUpdates(onUpdate: (event: ZoneUpdateEvent) => void) {
  const retryDelay = useRef(1000);

  useEffect(() => {
    let ws: WebSocket;
    let closedByUs = false;
    let heartbeat: ReturnType<typeof setInterval>;

    function connect() {
      ws = new WebSocket(WS_URL);

      ws.onopen = () => {
        retryDelay.current = 1000;
        heartbeat = setInterval(() => {
          if (ws.readyState === WebSocket.OPEN) ws.send("ping");
        }, 25000);
      };

      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          if (data.type === "zone_update") onUpdate(data as ZoneUpdateEvent);
        } catch {
          
        }
      };

      ws.onclose = () => {
        clearInterval(heartbeat);
        if (!closedByUs) {
          setTimeout(connect, retryDelay.current);
          retryDelay.current = Math.min(retryDelay.current * 2, 15000);
        }
      };

      ws.onerror = () => ws.close();
    }

    connect();
    return () => {
      closedByUs = true;
      clearInterval(heartbeat);
      ws?.close();
    };
    
  }, []);
}
