/** Base64 <-> binary helpers. Used to ferry the resume file across the
 * chrome.runtime message boundary (which JSON-serializes, so no ArrayBuffer). */

export function arrayBufferToBase64(buf: ArrayBuffer): string {
  const bytes = new Uint8Array(buf);
  let binary = "";
  const chunk = 0x8000;
  for (let i = 0; i < bytes.length; i += chunk) {
    binary += String.fromCharCode(...bytes.subarray(i, i + chunk));
  }
  return btoa(binary);
}

export function base64ToArrayBuffer(b64: string): ArrayBuffer {
  const binary = atob(b64);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
  return bytes.buffer;
}

export function base64ToFile(b64: string, name: string, type: string): File {
  return new File([base64ToArrayBuffer(b64)], name, { type });
}
