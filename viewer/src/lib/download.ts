/**
 * Save `text` as a file named `filename`: create an object URL, click a
 * temporary link, and revoke the URL a second later (after the browser has
 * started the download). Errors from the Blob/URL APIs propagate to the caller.
 */
export function downloadText(filename: string, text: string, mime: string): void {
  const url = URL.createObjectURL(new Blob([text], { type: mime }));
  const link = document.createElement("a");
  link.href = url; link.download = filename; link.click();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}
