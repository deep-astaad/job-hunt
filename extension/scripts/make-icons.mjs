#!/usr/bin/env node
/**
 * Generate the AppFill PNG icons (16/48/128) from code — no native deps.
 *
 * Mirrors public/icons/logo.svg: a blue rounded tile, a white form card with
 * field rows, and a green "done" check badge (the autofill metaphor). Shapes are
 * drawn at high supersampling and box-downsampled for anti-aliasing, then encoded
 * as RGBA PNGs (so the rounded corners are transparent).
 *
 * Run: `npm run icons`
 */
import zlib from "node:zlib";
import { writeFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const outDir = join(dirname(fileURLToPath(import.meta.url)), "..", "public", "icons");

// --- colors ---
const BG_TOP = [59, 130, 246]; // #3b82f6
const BG_BOT = [30, 64, 175]; // #1e40af
const WHITE = [255, 255, 255];
const BLUE = [37, 99, 235]; // #2563eb
const GRAY = [203, 213, 225]; // #cbd5e1
const GREEN = [34, 197, 94]; // #22c55e

/** Draw the logo into an SS-resolution RGBA buffer (single opaque color per px). */
function drawLogo(S, ss) {
  const big = S * ss;
  const buf = new Uint8Array(big * big * 4); // transparent by default
  const u = (f) => f * big; // fraction (0..1) -> px

  const set = (x, y, c, a = 255) => {
    if (x < 0 || y < 0 || x >= big || y >= big) return;
    const i = (y * big + x) * 4;
    buf[i] = c[0];
    buf[i + 1] = c[1];
    buf[i + 2] = c[2];
    buf[i + 3] = a;
  };

  const inRound = (px, py, x, y, w, h, r) => {
    if (px < x || py < y || px >= x + w || py >= y + h) return false;
    const cx = Math.min(Math.max(px, x + r), x + w - r);
    const cy = Math.min(Math.max(py, y + r), y + h - r);
    const dx = px - cx;
    const dy = py - cy;
    return dx * dx + dy * dy <= r * r;
  };

  const roundRect = (fx, fy, fw, fh, fr, color, colorBottom) => {
    const x = u(fx), y = u(fy), w = u(fw), h = u(fh), r = u(fr);
    for (let py = Math.floor(y); py < y + h; py++) {
      for (let px = Math.floor(x); px < x + w; px++) {
        if (!inRound(px, py, x, y, w, h, r)) continue;
        if (colorBottom) {
          const t = (py - y) / h;
          set(px, py, [
            Math.round(color[0] + (colorBottom[0] - color[0]) * t),
            Math.round(color[1] + (colorBottom[1] - color[1]) * t),
            Math.round(color[2] + (colorBottom[2] - color[2]) * t),
          ]);
        } else set(px, py, color);
      }
    }
  };

  const disc = (fcx, fcy, fr, color) => {
    const cx = u(fcx), cy = u(fcy), r = u(fr);
    for (let py = Math.floor(cy - r); py <= cy + r; py++)
      for (let px = Math.floor(cx - r); px <= cx + r; px++) {
        const dx = px - cx, dy = py - cy;
        if (dx * dx + dy * dy <= r * r) set(px, py, color);
      }
  };

  const capsule = (fx1, fy1, fx2, fy2, fth, color) => {
    const x1 = u(fx1), y1 = u(fy1), x2 = u(fx2), y2 = u(fy2), th = u(fth) / 2;
    const minX = Math.floor(Math.min(x1, x2) - th), maxX = Math.ceil(Math.max(x1, x2) + th);
    const minY = Math.floor(Math.min(y1, y2) - th), maxY = Math.ceil(Math.max(y1, y2) + th);
    const vx = x2 - x1, vy = y2 - y1;
    const len2 = vx * vx + vy * vy || 1;
    for (let py = minY; py <= maxY; py++)
      for (let px = minX; px <= maxX; px++) {
        let t = ((px - x1) * vx + (py - y1) * vy) / len2;
        t = Math.max(0, Math.min(1, t));
        const dx = px - (x1 + t * vx), dy = py - (y1 + t * vy);
        if (dx * dx + dy * dy <= th * th) set(px, py, color);
      }
  };

  // tile background (vertical gradient) with rounded corners
  roundRect(0, 0, 1, 1, 0.219, BG_TOP, BG_BOT);
  // form card
  roundRect(0.203, 0.156, 0.484, 0.688, 0.094, WHITE);
  // field rows
  roundRect(0.281, 0.281, 0.234, 0.055, 0.027, BLUE);
  roundRect(0.281, 0.422, 0.328, 0.047, 0.023, GRAY);
  roundRect(0.281, 0.547, 0.328, 0.047, 0.023, GRAY);
  roundRect(0.281, 0.672, 0.203, 0.047, 0.023, GRAY);
  // "done" badge: white ring + green disc + white check
  disc(0.719, 0.719, 0.211, WHITE);
  disc(0.719, 0.719, 0.172, GREEN);
  capsule(0.648, 0.719, 0.695, 0.773, 0.047, WHITE);
  capsule(0.695, 0.773, 0.789, 0.664, 0.047, WHITE);

  return { buf, big };
}

/** Box-downsample SS buffer to SxS RGBA (averaging, premultiplied by alpha). */
function downsample(buf, big, S, ss) {
  const out = new Uint8Array(S * S * 4);
  for (let y = 0; y < S; y++)
    for (let x = 0; x < S; x++) {
      let r = 0, g = 0, b = 0, a = 0;
      for (let sy = 0; sy < ss; sy++)
        for (let sx = 0; sx < ss; sx++) {
          const i = ((y * ss + sy) * big + (x * ss + sx)) * 4;
          const al = buf[i + 3];
          r += buf[i] * al;
          g += buf[i + 1] * al;
          b += buf[i + 2] * al;
          a += al;
        }
      const n = ss * ss;
      const o = (y * S + x) * 4;
      out[o] = a ? Math.round(r / a) : 0;
      out[o + 1] = a ? Math.round(g / a) : 0;
      out[o + 2] = a ? Math.round(b / a) : 0;
      out[o + 3] = Math.round(a / n);
    }
  return out;
}

// --- minimal RGBA PNG encoder ---
function crc32(buf) {
  let c = ~0;
  for (const b of buf) {
    c ^= b;
    for (let k = 0; k < 8; k++) c = (c >>> 1) ^ (0xedb88320 & -(c & 1));
  }
  return ~c >>> 0;
}
function chunk(type, data) {
  const t = Buffer.from(type);
  const len = Buffer.alloc(4);
  len.writeUInt32BE(data.length);
  const cd = Buffer.concat([t, data]);
  const crc = Buffer.alloc(4);
  crc.writeUInt32BE(crc32(cd));
  return Buffer.concat([len, cd, crc]);
}
function encodePng(rgba, S) {
  const sig = Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]);
  const ihdr = Buffer.alloc(13);
  ihdr.writeUInt32BE(S, 0);
  ihdr.writeUInt32BE(S, 4);
  ihdr[8] = 8; // bit depth
  ihdr[9] = 6; // color type RGBA
  const stride = S * 4;
  const raw = Buffer.alloc((stride + 1) * S);
  for (let y = 0; y < S; y++) {
    raw[y * (stride + 1)] = 0; // filter: none
    Buffer.from(rgba.buffer, y * stride, stride).copy(raw, y * (stride + 1) + 1);
  }
  const idat = zlib.deflateSync(raw, { level: 9 });
  return Buffer.concat([
    sig,
    chunk("IHDR", ihdr),
    chunk("IDAT", idat),
    chunk("IEND", Buffer.alloc(0)),
  ]);
}

for (const S of [16, 48, 128]) {
  const ss = S <= 16 ? 16 : S <= 48 ? 12 : 10;
  const { buf, big } = drawLogo(S, ss);
  const rgba = downsample(buf, big, S, ss);
  writeFileSync(join(outDir, `icon-${S}.png`), encodePng(rgba, S));
}
console.log("✓ Wrote icon-16/48/128.png");
