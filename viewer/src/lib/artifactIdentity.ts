export interface ArtifactIdentity {
  name: string;
  byteLength: number;
  sha256: string | null;
}

// Hash original bytes, including BOM/whitespace; never a reserialized bundle.
export async function identifyArtifact(name: string, bytes: ArrayBuffer): Promise<ArtifactIdentity> {
  let sha256: string | null = null;
  try {
    // A view hashes the same bytes and supports cross-realm File ArrayBuffers
    // when Node 20 Web Crypto runs against jsdom.
    const digest = await globalThis.crypto.subtle.digest("SHA-256", new Uint8Array(bytes));
    sha256 = Array.from(new Uint8Array(digest), (byte) => byte.toString(16).padStart(2, "0")).join("");
  } catch {
    // File viewing also works on origins where Web Crypto is unavailable.
  }
  return { name, byteLength: bytes.byteLength, sha256 };
}
