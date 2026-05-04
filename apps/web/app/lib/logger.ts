type LogLevel = "debug" | "info" | "warn" | "error";

type LogFields = Record<string, unknown>;

const isProduction = process.env.NODE_ENV === "production";

const write = (level: LogLevel, event: string, fields: LogFields = {}) => {
  const payload = {
    ts: new Date().toISOString(),
    level,
    service: "web",
    event,
    ...fields
  };

  if (isProduction) {
    const line = JSON.stringify(payload);
    if (level === "error") {
      console.error(line);
      return;
    }
    if (level === "warn") {
      console.warn(line);
      return;
    }
    console.info(line);
    return;
  }

  const fieldText = Object.entries(fields)
    .map(([key, value]) => `${key}=${String(value)}`)
    .join(" ");
  const message = fieldText ? `${event} | ${fieldText}` : event;

  if (level === "error") {
    console.error(message);
    return;
  }
  if (level === "warn") {
    console.warn(message);
    return;
  }
  if (level === "debug") {
    console.debug(message);
    return;
  }
  console.info(message);
};

const logger = {
  debug: (event: string, fields?: LogFields) => write("debug", event, fields),
  info: (event: string, fields?: LogFields) => write("info", event, fields),
  warn: (event: string, fields?: LogFields) => write("warn", event, fields),
  error: (event: string, fields?: LogFields) => write("error", event, fields)
};

export { logger };
