export type SessionStreamEvent<T> = {
  id: string | null;
  event: string;
  data: T | null;
};

export async function readSessionStream<T>(
  stream: ReadableStream<Uint8Array>,
  onEvent: (event: SessionStreamEvent<T>) => Promise<void> | void
) {
  const reader = stream.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    buffer += decoder.decode(value ?? new Uint8Array(), { stream: !done });

    let boundary = buffer.indexOf("\n\n");
    while (boundary !== -1) {
      const rawEvent = buffer.slice(0, boundary);
      buffer = buffer.slice(boundary + 2);
      const parsed = parseSessionStreamEvent<T>(rawEvent);
      if (parsed) {
        await onEvent(parsed);
      }
      boundary = buffer.indexOf("\n\n");
    }

    if (done) {
      const parsed = parseSessionStreamEvent<T>(buffer);
      if (parsed) {
        await onEvent(parsed);
      }
      return;
    }
  }
}

function parseSessionStreamEvent<T>(rawEvent: string): SessionStreamEvent<T> | null {
  const trimmed = rawEvent.trim();
  if (!trimmed || trimmed.startsWith(":")) {
    return null;
  }

  let id: string | null = null;
  let event = "message";
  const dataLines: string[] = [];

  for (const line of rawEvent.split("\n")) {
    if (!line || line.startsWith(":")) {
      continue;
    }

    const separatorIndex = line.indexOf(":");
    if (separatorIndex === -1) {
      continue;
    }

    const field = line.slice(0, separatorIndex).trim();
    const value = line.slice(separatorIndex + 1).trimStart();
    if (field === "id") {
      id = value;
      continue;
    }
    if (field === "event") {
      event = value;
      continue;
    }
    if (field === "data") {
      dataLines.push(value);
    }
  }

  const rawData = dataLines.join("\n");
  if (!rawData) {
    return null;
  }

  return {
    id,
    event,
    data: JSON.parse(rawData) as T
  };
}
