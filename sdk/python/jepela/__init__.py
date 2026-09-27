"""Jepela: the decision API with memory. Typed questions in, calibrated typed answers out."""
from .client import AsyncJepelaClient, JepelaClient, base_url_for, region_of, signup
from .errors import (AuthenticationError, BadRequestError, ConflictError, ConnectionFailed, EngineError, JepelaError, NotFoundError,
                     PaymentRequiredError, PermissionDeniedError, RateLimitError, ServerError)
from .pydantic_support import Levels, Options, questions_from_model, to_model
from .types import (Answer, Choice, ChoiceAnswer, JepelaWarning, MemoryInfo, MemoryResult, Models, Noul, NoulAnswer, Question, Response,
                    Score, ScoreAnswer, Usage)

__version__ = "0.2.0"
__all__ = ["JepelaClient", "AsyncJepelaClient", "signup", "base_url_for", "region_of", "Choice", "Score", "Noul", "Question", "Response", "Answer", "ChoiceAnswer",
           "ScoreAnswer", "NoulAnswer", "Usage", "MemoryResult", "MemoryInfo", "Models", "JepelaWarning", "Levels", "Options",
           "questions_from_model", "to_model", "JepelaError", "AuthenticationError", "PaymentRequiredError", "RateLimitError",
           "BadRequestError", "NotFoundError", "PermissionDeniedError", "ConflictError", "EngineError", "ServerError", "ConnectionFailed"]
