export type ErrorSeverity = "info" | "warning" | "error" | "critical";

export type StructuredError = {
  code: string;
  title: string;
  message: string;
  severity: ErrorSeverity;
  source: string;
  possible_causes: string[];
  recovery_actions: string[];
  technical_detail: string | null;
  timestamp: string;
  request_id: string | null;
};

export class ApiError extends Error {
  structured: StructuredError | null;
  status: number;
  path: string;

  constructor(
    message: string,
    options: { status: number; path: string; structured?: StructuredError | null },
  ) {
    super(message);
    this.name = "ApiError";
    this.status = options.status;
    this.path = options.path;
    this.structured = options.structured ?? null;
  }
}
