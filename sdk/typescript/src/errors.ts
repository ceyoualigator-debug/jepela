// One error class per answer the gateway can give, the same ones the Python SDK has.

export class JepelaError extends Error {
  status: number | undefined;
  kind: string | undefined;
  retryAfter: number | undefined;

  constructor(message: string, status?: number, kind?: string, retryAfter?: number) {
    super(message);
    this.name = new.target.name;
    this.status = status;
    this.kind = kind;
    this.retryAfter = retryAfter;
  }
}

export class AuthenticationError extends JepelaError {}      // 401
export class PaymentRequiredError extends JepelaError {}     // 402: no credit left
export class PermissionDeniedError extends JepelaError {}    // 403: e.g. sign-up is off, or an invite code is needed
export class NotFoundError extends JepelaError {}            // 404
export class ConflictError extends JepelaError {}            // 409: a limit such as the number of golden cases
export class BadRequestError extends JepelaError {}          // 413, 415, 422
export class RateLimitError extends JepelaError {}           // 429
export class ServerError extends JepelaError {}              // 500
export class EngineError extends JepelaError {}              // 502, 503: the engine or the product behind the gateway
export class ConnectionFailed extends JepelaError {}         // no HTTP answer at all

const BY_STATUS: Record<number, typeof JepelaError> = {
  401: AuthenticationError, 402: PaymentRequiredError, 403: PermissionDeniedError, 404: NotFoundError, 409: ConflictError,
  413: BadRequestError, 415: BadRequestError, 422: BadRequestError, 429: RateLimitError, 500: ServerError,
  502: EngineError, 503: EngineError,
};

export function errorFor(status: number, message: string, kind?: string, retryAfter?: number): JepelaError {
  const Cls = BY_STATUS[status] ?? JepelaError;
  return new Cls(message, status, kind, retryAfter);
}
