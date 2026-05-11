export function previewJson(value: unknown, maxLength = 100) {
  if (value == null) {
    return "";
  }

  try {
    return JSON.stringify(value).slice(0, maxLength);
  } catch {
    return String(value).slice(0, maxLength);
  }
}
