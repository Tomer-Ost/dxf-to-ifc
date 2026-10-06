export const INK = "#1f2328";

/** Darken layer colours that would vanish on a white background (e.g. ACI 7 white, 2 yellow). */
export function readable(hex) {
  const n = parseInt(hex.slice(1), 16);
  const [r, g, b] = [(n >> 16) & 255, (n >> 8) & 255, n & 255];
  const lum = (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255;
  return lum > 0.72 ? INK : hex;
}
