/**
 * The bundle decode worker (lib/bundleDecode.ts): one request; the decoded
 * bundle's parts, then the reply. Each message is structured-cloned to the
 * main thread.
 */
import { answerDecodeRequest, type DecodeRequest } from "./bundleDecode";

const scope = self as unknown as {
  onmessage: ((event: MessageEvent<DecodeRequest>) => void) | null;
  postMessage: (message: unknown) => void;
};

scope.onmessage = (event) => {
  void answerDecodeRequest(event.data, (part) => scope.postMessage(part)).then((reply) => scope.postMessage(reply));
};
