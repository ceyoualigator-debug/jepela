// Jepela: the decision API with memory. Typed questions in, calibrated typed answers out.
export { JepelaClient, signup, DEFAULT_BASE_URL, regionOf, baseUrlFor } from "./client.ts";
export type { ClientOptions } from "./client.ts";
export {
  JepelaError, AuthenticationError, PaymentRequiredError, PermissionDeniedError, NotFoundError, ConflictError,
  BadRequestError, RateLimitError, ServerError, EngineError, ConnectionFailed, errorFor,
} from "./errors.ts";
export { choice, score, noul } from "./types.ts";
export type {
  ChoiceQuestion, ScoreQuestion, NoulQuestion, Question, Questions, ChoiceAnswer, ScoreAnswer, NoulAnswer, AnswerFor, Answers,
  Usage, JepelaWarning, MemoryResult, Response, MemoryOptions, DecideOptions, MemoryInfo, Calibration, FinetuneJob,
} from "./types.ts";
