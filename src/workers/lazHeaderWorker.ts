export interface LazHeaderParseResult {
  hasProjectionVlr: boolean;
  vlrCount: number;
  error?: string;
}

function parseLasHeader(buffer: ArrayBuffer): LazHeaderParseResult {
  const view = new DataView(buffer);
  const signature = String.fromCharCode(
    view.getUint8(0),
    view.getUint8(1),
    view.getUint8(2),
    view.getUint8(3)
  );
  if (signature !== "LASF") {
    return { hasProjectionVlr: false, vlrCount: 0, error: "Invalid LAS signature" };
  }

  const headerSize = view.getUint16(94, true);
  const vlrCount = view.getUint32(100, true);

  let cursor = headerSize;
  let hasProjectionVlr = false;

  for (let i = 0; i < vlrCount; i += 1) {
    if (cursor + 54 > view.byteLength) {
      break;
    }
    let userId = "";
    for (let j = 0; j < 16; j += 1) {
      const c = view.getUint8(cursor + 2 + j);
      if (c !== 0) userId += String.fromCharCode(c);
    }
    const normalized = userId.trim();
    if (
      normalized.includes("LASF_Projection") ||
      normalized.includes("liblas") ||
      normalized.includes("LASF")
    ) {
      hasProjectionVlr = true;
      break;
    }
    const recordLength = view.getUint16(cursor + 20, true);
    cursor += 54 + recordLength;
  }

  return { hasProjectionVlr, vlrCount };
}

self.onmessage = async (event: MessageEvent<{ file: File }>) => {
  try {
    const file = event.data.file;
    // Read only initial bytes containing LAS header and most VLR descriptors.
    const slice = file.slice(0, Math.min(file.size, 2 * 1024 * 1024));
    const buffer = await slice.arrayBuffer();
    const result = parseLasHeader(buffer);
    ((self as unknown as { postMessage: (msg: LazHeaderParseResult) => void })).postMessage(result);
  } catch (error) {
    const message = error instanceof Error ? error.message : "Unknown parse error";
    ((self as unknown as { postMessage: (msg: LazHeaderParseResult) => void })).postMessage({
      hasProjectionVlr: false,
      vlrCount: 0,
      error: message,
    } satisfies LazHeaderParseResult);
  }
};
