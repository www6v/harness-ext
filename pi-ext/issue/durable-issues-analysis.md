# Durable-Related Issues Without Linked PRs

Analysis of issues in [earendil-works/pi](https://github.com/earendil-works/pi) tagged with "durable" or related to durable functionality that have no associated pull requests. Sorted from easiest to most difficult based on scope, complexity, and architectural impact.

**Total:** 23 issues  
**Last Updated:** 2026-10-23

---

## Difficulty Legend

- 🟢 **Easy**: Trivial changes, clear scope, well-defined solution
- 🟡 **Medium**: Well-scoped but requires moderate code changes and design decisions
- 🔴 **Hard**: Complex changes, large scope, or architectural impact

---

## 🟢 Easy (Trivial to Simple)

### 1. #11254 - Import toCodemodeIdentifier from pi-codemode/declarations
**URL:** https://github.com/earendil-works/pi/issues/11254  
**Labels:** durable  
**Complexity:** One-line import change

Change the import source of `toCodemodeIdentifier` from `@earendil-works/pi-codemode/portable` to `@earendil-works/pi-codemode/declarations` in `packages/durable/src/codemode/codemode.ts`. The `/portable` module re-exports `InlineCodemodeSandbox`, causing the WASM runtime to load unnecessarily. Author offers to send the PR.

**Why it's easy:** Single import statement change, no behavior change, author has already identified the exact line and solution.

---

### 2. #11180 - Environments CI fails: @earendil-works/pi-telemetry has no source export condition
**URL:** https://github.com/earendil-works/pi/issues/11180  
**Labels:** prio:p0  
**Complexity:** Package.json configuration fix

CI fails because `packages/telemetry/package.json` declares `"source"` export only on `./render`, not on `.` or `./testing`. The vitest config resolves with `conditions: ["source"]`, causing resolution to fall through to unbuilt `./dist/index.js`.

**Why it's easy:** Add `"source"` export conditions to package.json for the missing entry points. Clear error message, straightforward fix.

---

### 3. #11055 - Let beforeRequest reject a request
**URL:** https://github.com/earendil-works/pi/issues/11055  
**Labels:** (none)  
**Complexity:** Hook extension with existing pattern

`GenerationHooks.beforeRequest` can rewrite messages but cannot stop a request. A throw goes to `onReport` and the request still sends. Need to allow `beforeRequest` to return `{ reject: string }` (or throw `RequestRejected`) to settle the run with a terminal error without retrying.

**Why it's easy:** Pattern already exists in `beforeTool` which returns `{ block }`. Add similar return type to `beforeRequest`, check for rejection before sending request, settle run with error message.

---

### 4. #10804 - Support Anthropic thinking.display "updates"
**URL:** https://github.com/earendil-works/pi/issues/10804  
**Labels:** durable  
**Complexity:** Type widening + beta header

Add `"updates"` to `AnthropicThinkingDisplay` type, append `thinking-display-updates-2026-08-18` beta when used, and add `thinkingDisplay` option to `ConversationStreamOptions` in pi-durable.

**Why it's easy:** Type definition change, beta header logic, and pass-through option. No parsing changes needed since blocks are standard thinking blocks.

---

## 🟡 Medium (Well-Scoped, Moderate Changes)

### 5. #11149 - Admit a submission inside a host's own commit
**URL:** https://github.com/earendil-works/pi/issues/11149  
**Labels:** durable  
**Complexity:** Expose internal function with adapted signature

Let a host call `admitSubmission()` inside its own `harness.commit` after its own checks. Today only `Conversation.submit()` and compaction call it. Either expose a public method that takes `Tx` and `SubmissionDraft` and fills in internal parameters, or add `whenIdle: "reject"` on input drafts.

**Why it's medium:** Need to design the public API surface, adapt internal function signature, handle transaction context. Clear use case but requires thoughtful API design.

---

### 6. #10535 - Commit retry delays as task state
**URL:** https://github.com/earendil-works/pi/issues/10535  
**Labels:** durable  
**Complexity:** Add notBefore field to waiting tasks

When generation waits out a model retry backoff, commit it as `waiting` with a `notBefore` timestamp instead of sleeping in the process. The storage already arms wakes from task records, but sleeping retry looks live so the wake waits through the delay.

**Why it's medium:** Add `notBefore` field to task state, update `resume()` to honor it, change retry logic to commit instead of sleep. Clear design but touches task state machine.

---

### 7. #10845 - Identify the task behind each model request
**URL:** https://github.com/earendil-works/pi/issues/10845  
**Labels:** durable  
**Complexity:** Add metadata to request options

Tell the `Models` provider which task each generation/compaction request belongs to via `metadata: { taskId, purpose: "generation" | "compaction" }`. For compaction, also record the placed inputs of the run that created the task.

**Why it's medium:** Add metadata fields to request options, thread task identity through generation and compaction code paths. Author has linked specific code locations.

---

### 8. #10846 - Accept an injected daemon process so the client runs in Workers
**URL:** https://github.com/earendil-works/pi/issues/10846  
**Labels:** durable  
**Complexity:** Refactor Connection to take startProcess callback

Let `Connection` take a `startProcess({ token, signal })` callback as an alternative to `command`. Returns started daemon with stdin/stdout/stderr as Web Streams, exitCode promise, and kill(). Export from entry that doesn't import `node:child_process`.

**Why it's medium:** Refactor Connection to support injected process, adapt existing framing to work with injected streams, separate Node-specific imports. Clear design but touches core connection logic.

---

### 9. #11043 - afterTool for calls that never ran, and a turn limit
**URL:** https://github.com/earendil-works/pi/issues/11043  
**Labels:** durable  
**Complexity:** Two small additions with tests

Two independent features: (1) `afterTool` also runs for calls that never executed (unknown tool, invalid args, blocked by `beforeTool`), (2) `HarnessSettings.maxTurns` ends a run after N model turns.

**Why it's medium:** Each feature is well-defined with tests. Author has a working diff and offers to split into separate PRs. Moderate scope but clear requirements.

---

### 10. #11141 - Make extension start a task on each turn without a tool call
**URL:** https://github.com/earendil-works/pi/issues/11141  
**Labels:** durable  
**Complexity:** Lifecycle management for extension-created tasks

Let an extension start its own task on every turn with the same lifecycle as manual compaction: conversation-owned, cancelled by `abort()`, included in idle waits. Today extension code can only create tasks from a tool's `execute` or from another task.

**Why it's medium:** Need to design how extensions can create tasks from hooks, manage lifecycle (abort, restart, resume), integrate with conversation busy state. Clear use case but non-trivial lifecycle coordination.

---

### 11. #11070 - Allow hosts to provide a Code Mode output writer
**URL:** https://github.com/earendil-works/pi/issues/11070  
**Labels:** (none)  
**Complexity:** Add callback option to CodemodeToolOptions

Add an optional output-writer callback to `CodemodeToolOptions`, keeping the current filesystem writer as default. The callback receives name, data, ToolExecutionApi, and Context, returning a location or error.

**Why it's medium:** Add callback option, thread it through Code Mode output writing, adapt existing filesystem writer to use it. Clear interface but requires understanding of output flow.

---

### 12. #10063 - Anthropic OAuth requests return Invalid effort level for Claude Opus 5/5.5 and Fable 5
**URL:** https://github.com/earendil-works/pi/issues/10063  
**Labels:** last-read  
**Complexity:** Model gating and effort level mapping

OAuth requests for Opus 5, Opus 5.5, and Fable 5 return HTTP 400 "Invalid effort level" at default, low, and high thinking. The request shaping is in `anthropic-messages.ts`, model gating in `generate-models.ts`.

**Why it's medium:** Need to understand effort level mapping for different models, fix the gating logic. Clear reproduction steps and affected models listed.

---

### 13. #9508 - pi-ai sends unsupported OpenAI-specific request fields/roles/auth to compatible providers
**URL:** https://github.com/earendil-works/pi/issues/9508  
**Labels:** bug  
**Complexity:** Conditional field omission based on provider capabilities

pi-ai sends OpenAI-specific fields (store, tools, tool_choice), message roles, or auth headers that some compatible providers reject. Need to omit unsupported fields by default, make role selection conditional on provider capabilities, allow unauthenticated requests when no API key is configured.

**Why it's medium:** Touches request building logic, need to design provider capability flags, conditional logic for multiple fields. Clear problem but broad scope.

---

### 14. #9792 - SessionManager.create() does not write session file to disk until first assistant message
**URL:** https://github.com/earendil-works/pi/issues/9792  
**Labels:** (none)  
**Complexity:** Add eager persistence option

`SessionManager.create()` returns a session with `isPersisted() === true` but no file exists on disk until the first assistant message. `_persist()` defers writing while no assistant message exists. Need to support eager persistence or expose a flush method.

**Why it's medium:** Add option to write version-3 header immediately on creation, or expose public flush method. Clear impact on external orchestrators but requires understanding of persistence flow.

---

## 🔴 Hard (Complex, Large Scope, or Architectural)

### 15. #11006 - GitHub Copilot models enabled by enterprise admin stay hidden after restart
**URL:** https://github.com/earendil-works/pi/issues/11006  
**Labels:** (none)  
**Complexity:** OAuth cache refresh logic

Models newly enabled by a GitHub Copilot Enterprise admin remain absent from Pi's model picker after restart. The OAuth credential's `availableModelIds` is cached, and restarting doesn't refresh it. Need to synchronize the account-specific model list at startup and when credentials change.

**Why it's hard:** Touches OAuth credential management, model list caching, startup flow. Need to understand GitHub Copilot API integration and design refresh logic without breaking existing flows.

---

### 16. #10857 - On a Durable Object, a sleeping task wakes only on the next request
**URL:** https://github.com/earendil-works/pi/issues/10857  
**Labels:** bug, durable  
**Complexity:** Alarm system integration for Durable Objects

`runtime.sleep()` doesn't wake at its deadline after object restart because it's an in-memory `setTimeout`. Durable Objects only run code for requests or alarms, and Pi never sets an alarm. Need to set alarms for deadlines from the durable harness.

**Why it's hard:** Requires integrating with Cloudflare Durable Object alarm API, tracking sleep deadlines in persistent state, arming alarms on commit. Author mentions they have a working Durable Object base class.

---

### 17. #10583 - Calibrate compaction retention to reported context usage
**URL:** https://github.com/earendil-works/pi/issues/10583  
**Labels:** durable  
**Complexity:** Token estimation rework for CJK text

Compaction is skipped when reported context usage exceeds threshold but character estimates are below `keepRecentTokens`. CJK text uses substantially more tokens per character than the fixed divisor (4 or 3.5) assumes. Need to reuse `estimateContext()` to calibrate entry estimates before range selection.

**Why it's hard:** Touches compaction logic, token estimation, context range selection. Author mentions implementation with six regression tests but requires understanding of compaction internals.

---

### 18. #7053 - Parallel tool batches lose already-completed tool results when one sibling stalls
**URL:** https://github.com/earendil-works/pi/issues/7053  
**Labels:** inprogress  
**Complexity:** Persistence architecture change for parallel tool execution

Follow-up to #3503. `toolResult` messages are created only after the whole batch settles (`Promise.all`). If one tool stalls, completed siblings' results are never persisted. On abort, all toolCalls become orphans with "No result provided".

**Why it's hard:** Requires changing parallel execution to persist results incrementally rather than atomically. Touches agent loop, message persistence, error recovery. Already in progress but complex.

---

### 19. #10162 - Too many input images stop the agent task
**URL:** https://github.com/earendil-works/pi/issues/10162  
**Labels:** bug  
**Complexity:** Image limit tracking and auto-compaction

Models have limits on input images (e.g., 30 images) similar to context windows. When exceeded, the task fails with 400 error. Need to track image count and either auto-trigger compaction or add `max_num_input_images` to model catalog.

**Why it's hard:** Requires tracking image count across messages, integrating with compaction system, adding model capability flags. Touches request validation, compaction triggers, model configuration.

---

### 20. #8301 - Can't interleave compaction requests with prompts in prompt queue
**URL:** https://github.com/earendil-works/pi/issues/8301  
**Labels:** bug  
**Complexity:** Queue system rework

Queuing commands like "Do task 1" → `/compact` → "Do task 2" → `/compact` fails because the first `/compact` cancels the session and starts compaction immediately. Need to support interleaving compaction with prompts in the queue.

**Why it's hard:** Requires reworking the prompt queue system to handle compaction commands without cancelling the session. Touches session management, queue processing, compaction triggers.

---

### 21. #10852 - Pi Durable support for client-side tool execution and tool approval
**URL:** https://github.com/earendil-works/pi/issues/10852  
**Labels:** durable  
**Complexity:** Persistence and lifecycle design for human-in-the-loop tools

Support tools that require human approval or client-side information before execution. The run stops before the tool executes, the pending call is persisted, and the run resumes when approval/result is provided (potentially hours or days later).

**Why it's hard:** Requires designing persistence for pending tool calls, lifecycle management for long-running approvals, client-server communication for approval flow, resume logic. Major feature with significant design space.

---

### 22. #10624 - Idempotent exec, replay-safe bash, local daemon, TCP forwarding, iroh transport
**URL:** https://github.com/earendil-works/pi/issues/10624  
**Labels:** durable  
**Complexity:** Massive multi-feature epic

Umbrella issue covering: (1) idempotent keyed process spawning in pi-env, (2) replay-safe bash, (3) route local tools through pi-env daemon, (4) TCP/HTTP forwarding, (5) evaluate iroh as optional transport. Each sub-feature is substantial.

**Why it's hard:** Multiple large features in one issue. Idempotent exec alone requires detached process management, job persistence, attach semantics. TCP forwarding needs port management. iroh transport evaluation is research. Clearly an epic.

---

### 23. #5932 - Exposing ctx.navigateTree() to agents
**URL:** https://github.com/earendil-works/pi/issues/5932  
**Labels:** to-discuss, new-harness  
**Complexity:** API surface change with design discussion needed

`navigateTree()` exists on `ExtensionCommandContext` but not on normal event/tool `ExtensionContext`. Exposing it would allow agents to use /tree functionality programmatically for task slicing and navigation.

**Why it's hard:** Tagged "to-discuss" and "new-harness", suggesting design decisions needed. Requires understanding of tree navigation semantics, how to expose them safely to agents, potential security/permission implications.

---

## Summary Statistics

| Difficulty | Count | Percentage |
|------------|-------|------------|
| 🟢 Easy | 4 | 17% |
| 🟡 Medium | 10 | 43% |
| 🔴 Hard | 9 | 39% |

## Recommendations

**Quick wins to start with:**
- #11254 (one-line import change)
- #11180 (CI fix, p0 priority)
- #11055 (beforeRequest rejection - clear pattern exists)

**High-impact medium efforts:**
- #11055 (beforeRequest rejection - clear pattern exists)
- #10535 (commit retry delays - improves serverless efficiency)
- #10845 (task identification - enables proper billing)

**Strategic hard issues:**
- #10857 (alarm system - critical for Durable Object reliability)
- #10852 (client-side tool execution - major feature for human-in-the-loop)
- #10624 (idempotent exec epic - foundational for robust remote execution)
