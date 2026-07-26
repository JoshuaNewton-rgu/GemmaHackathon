/* eslint-disable no-console */
type LogFields = Record<string, unknown>;

function format(level: string, message: string, fields?: LogFields): string {
  const timestamp = new Date().toISOString();
  const extra = fields ? ` ${JSON.stringify(fields)}` : "";
  return `[${timestamp}] [${level}] ${message}${extra}`;
}

export const logger = {
  info(message: string, fields?: LogFields) {
    console.log(format("INFO", message, fields));
  },
  warn(message: string, fields?: LogFields) {
    console.warn(format("WARN", message, fields));
  },
  error(message: string, fields?: LogFields) {
    console.error(format("ERROR", message, fields));
  },
};
