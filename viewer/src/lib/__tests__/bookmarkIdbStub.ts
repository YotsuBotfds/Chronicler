/** Minimal asynchronous IndexedDB stand-in for component tests. */
export function bookmarkIdbStub() {
  let data: string | undefined;
  let failWrites = false;
  const factory = {
    open: () => {
      const request: { result?: unknown; onsuccess?: () => void } = {};
      const database = {
        close: () => {}, onversionchange: null,
        transaction: () => {
          const tx: { oncomplete?: () => void; onabort?: () => void; wrote?: boolean; objectStore?: () => unknown } = {};
          tx.objectStore = () => ({
            get: () => {
              const get: { result?: string; onsuccess?: () => void } = {};
              setTimeout(() => {
                get.result = data;
                get.onsuccess?.();
                setTimeout(() => failWrites && tx.wrote ? tx.onabort?.() : tx.oncomplete?.(), 0);
              }, 0);
              return get;
            },
            put: (value: string) => { tx.wrote = true; if (!failWrites) data = value; },
          });
          return tx;
        },
      };
      setTimeout(() => { request.result = database; request.onsuccess?.(); }, 0);
      return request;
    },
  } as unknown as IDBFactory;
  return { factory, failWrites: (value: boolean) => { failWrites = value; }, raw: () => data };
}
