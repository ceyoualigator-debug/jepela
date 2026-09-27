# jepela-sdk (TypeScript)

TypeScript client for Jepela, the decision API with memory. No dependencies: it uses the `fetch` built into
Node, Deno, Bun and browsers. The source is plain TypeScript that Node 22.18+ runs directly.

Install it from a checkout of this repository (npm links the folder, and Node runs the TypeScript there):

```bash
npm install /path/to/checkout/sdk/typescript      # then: import { JepelaClient } from "jepela-sdk"
```

Node does not strip types from files copied into `node_modules`, so a packed copy (`npm pack`, or `--install-links`) fails with `ERR_UNSUPPORTED_NODE_MODULES_TYPE_STRIPPING`; import from the linked folder, or from the source path as below.

```ts
import { JepelaClient, choice, noul, score } from "jepela-sdk";

const jepela = new JepelaClient();                       // JEPELA_API_KEY; the key's region picks the address
const r = await jepela.systemOne("We were charged twice for September again.", {
  route: choice("Which team should handle this?", { billing: "Charges and refunds", support: "Product problems", other: "None of these" }),
  refund: noul("Is the customer asking for money back?"),
  urgency: score("How urgent is this?", ["Can wait a week", "Should be handled today", "Blocking the customer now"]),
}, { subject: "acme", memory: { compare: true } });

r.answers.route.choice;          // typed "billing" | "support" | "other"
r.answers.refund.noul;           // probability of yes
r.memory?.without_memory;        // the same call without the memory
r.usage.input_tokens;            // what you pay for: the tokens the engine read
```

`new JepelaClient({ apiKey, baseUrl, timeoutMs, maxRetries, backoffMs })`: the key falls back to `JEPELA_API_KEY`,
the gateway to `JEPELA_BASE_URL` and then the API of the key's region (`baseUrlFor(key)`, `regionOf(key)`); by default 120 000 ms per call, 2 retries,
500 ms backoff.

Everything the API offers has a method: `remember`, `forget`, `delete`, `memory(subject, lines)`, `rulesAdd`, `pin`, `exclude`, `aliases`,
`rules`, `rulesDelete`, `feedback`, `quality`, `calibrationFit`, `calibration`, `goldenAdd`, `golden`,
`goldenRun`, `goldenDelete` (`[]` deletes nothing; no argument, every case), `decisionsDelete`, `batchCreate`,
`batchUpload` (JSON Lines), `batch`, `batches`, `batchResults`, `batchWait`, `finetune(base?)`, `finetunes`,
`finetuneJob(id)`, `finetuneWait(id, timeoutMs, pollMs)`, `finetuneDelete(model)`, `models`, `usage`,
`request(method, path, body)` for any route, and `signup(email, { inviteCode })`, which needs no key.

Options on `systemOne`: `model`, `subject`, `memory` (`use`, `top_k`, `min_share`, `compare`, `placebo`,
`names`, `question_words`, `focus`, `explain`), `robust` (`true` or `{ orders: 1-5 }`, choices of up to 20
options), `windows` (`true` or `{ combine: { question_id: "max" | "mean" | "min" } }`), `derive`, `values`,
`cache`, `method` (`"auto"` by default: choices of more than 20 options are matched by vectors, the rest asked
of the engine; `"engine"`; `"match"`). Each answer says its `method`; a matched one has `similarity`.
With a subject, `r.memory` also has `pinned`, `excluded`, `exclusions_skipped` and, with `explain: true`,
`explain` (`{ line, kind, effect }` per memory line).

```ts
await jepela.pin("acme", "ACME pays for premium support.");                 // sent first at every decision about acme
await jepela.exclude("player-9", ["gold_coins"], "Coin bug.", { question: "reward" });
await jepela.aliases("acct-1", ["Globex Corporation"]);                     // other names recall searches
await jepela.finetunes();                          // { jobs, min_cases, bases }
const job = await jepela.finetune("english");      // trains on your golden cases (at least 20)
const done = await jepela.finetuneWait(job.job);   // done.usable: it won on held-out cases and kept memory
```

Errors are typed per status: `AuthenticationError`, `PaymentRequiredError`, `PermissionDeniedError`,
`NotFoundError`, `ConflictError`, `BadRequestError`, `RateLimitError` (with `retryAfter`), `EngineError`,
`ServerError`, `ConnectionFailed`. The client retries 429, 502 and 503 with backoff and retries a
connection that failed before the request was sent; a request that was sent and then failed is sent
again only if it is a GET, so a decision is never billed twice.

Tests: `python tests/real_steps/test_jers_typescript_sdk.py` builds real gateways in front of the real
Jepela engine and runs `test/client.test.ts` with Node's test runner. The code is not type-checked in this
repository (`tsc` is not installed here); `tsconfig.json` has the settings for checking it with `tsc`.
