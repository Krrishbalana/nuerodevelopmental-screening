export class Cancelled extends Error {}

/** Resolves after ms; rejects with Cancelled if the token is cancelled first. */
export function wait(ms: number, token: CancelToken): Promise<void> {
  return new Promise((resolve, reject) => {
    if (token.cancelled) return reject(new Cancelled());
    const id = window.setTimeout(() => {
      token.off(onCancel);
      resolve();
    }, ms);
    const onCancel = () => {
      clearTimeout(id);
      reject(new Cancelled());
    };
    token.on(onCancel);
  });
}

export class CancelToken {
  cancelled = false;
  private listeners = new Set<() => void>();

  on(fn: () => void) {
    this.listeners.add(fn);
  }

  off(fn: () => void) {
    this.listeners.delete(fn);
  }

  cancel() {
    this.cancelled = true;
    this.listeners.forEach((fn) => fn());
    this.listeners.clear();
  }
}

/** Runs an async sequence; cancelling stops it silently, other errors go to onError. */
export function runSequence(seq: (token: CancelToken) => Promise<void>, onError: (e: unknown) => void): () => void {
  const token = new CancelToken();
  seq(token).catch((e) => {
    if (!(e instanceof Cancelled)) onError(e);
  });
  return () => token.cancel();
}
