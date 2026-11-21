/** Bridges to the Windows app (Tauri). In a normal browser these do nothing. */

type TauriGlobal = {
  event?: { listen: (name: string, cb: () => void) => Promise<() => void> };
  notification?: {
    isPermissionGranted: () => Promise<boolean>;
    requestPermission: () => Promise<string>;
    sendNotification: (opts: { title: string; body?: string }) => void;
  };
};

function tauri(): TauriGlobal | null {
  if (typeof window === "undefined") return null;
  return ((window as unknown as { __TAURI__?: TauriGlobal }).__TAURI__ ?? null);
}

export function isDesktopApp() {
  return tauri() !== null;
}

/** Calls fn when Ctrl+Shift+Space is pressed anywhere on the PC (desktop app only). */
export function onDesktopPushToTalk(fn: () => void): () => void {
  const listen = tauri()?.event?.listen;
  if (!listen) return () => {};
  let off: (() => void) | null = null;
  let cancelled = false;
  void listen("nexus://push-to-talk", fn).then((u) => {
    if (cancelled) u();
    else off = u;
  });
  return () => {
    cancelled = true;
    off?.();
  };
}

/** Shows a Windows notification from the desktop app. Returns false outside it. */
export async function desktopNotify(title: string, body?: string): Promise<boolean> {
  const n = tauri()?.notification;
  if (!n) return false;
  let ok = await n.isPermissionGranted();
  if (!ok) ok = (await n.requestPermission()) === "granted";
  if (ok) n.sendNotification({ title, body });
  return ok;
}
