/** Shows new NEXUS notifications on the desktop while the app is open: as Windows notifications
 * in the desktop app, or browser notifications when Web Push isn't already doing it. */

import { desktopNotify, isDesktopApp } from "./desktop";
import { pushState } from "./push";
import type { AppNotification } from "./types";

/** Unread notifications that weren't there last time. The first call only records what exists. */
export function freshNotifications(seen: Set<string> | null, items: AppNotification[]): { fresh: AppNotification[]; seen: Set<string> } {
  const ids = new Set(items.map((n) => n.id));
  if (seen === null) return { fresh: [], seen: ids };
  return { fresh: items.filter((n) => !n.read && !seen.has(n.id)), seen: new Set([...seen, ...ids]) };
}

export async function showLive(items: AppNotification[]) {
  if (!items.length) return;
  if (isDesktopApp()) {
    for (const n of items.slice(0, 3)) await desktopNotify(n.title, n.body);
    return;
  }
  if (typeof Notification === "undefined" || Notification.permission !== "granted") return;
  if ((await pushState()) === "on") return; // the service worker already shows pushes
  if (document.visibilityState === "visible" && document.hasFocus()) return; // the bell is enough
  for (const n of items.slice(0, 3)) {
    const note = new Notification(n.title, { body: n.body, tag: n.id, icon: "/icon.svg" });
    note.onclick = () => {
      window.focus();
      if (n.link) window.location.assign(n.link);
    };
  }
}
