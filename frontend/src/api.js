async function request(url, options) {
  const res = await fetch(url, options);
  const body = await res.json().catch(() => ({}));
  if (!res.ok) {
    const detail = body.detail;
    const message = Array.isArray(detail)
      ? detail.map((d) => d.msg).join(", ")
      : detail || `Request failed (${res.status})`;
    throw new Error(message);
  }
  return body;
}

export const getOptions = () => request("/api/options");

export function uploadDxf(file) {
  const form = new FormData();
  form.append("file", file);
  return request("/api/dxf", { method: "POST", body: form });
}

export const convert = (payload) =>
  request("/api/convert", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });

/** kind: "ifc" | "csv" — both are produced by the same conversion. */
export function download(downloadId, name, kind = "ifc") {
  const a = document.createElement("a");
  a.href = `/api/${kind}/${downloadId}?name=${encodeURIComponent(name)}`;
  a.download = `${name}.${kind}`;
  document.body.appendChild(a);
  a.click();
  a.remove();
}
