# Repository instructions

- Write code, user-facing tool text, documentation, and commit messages in English.
- Support native OpenSSH on macOS, Linux, and Windows.
- Keep code free of comments.
- Keep the README brief. Explain what the tool does and how an agent should collect access fields and configure aliases.
- Keep server-specific values out of repository files.
- Commit each meaningful milestone using `feat: title`, `fix: title`, or `refactor: title`. Write the entire commit message in lowercase and the title in simple present tense.

# Agenter shared operating policy

This policy is portable across macOS and native Windows.

- Route only through the verified native model catalog and the shared policy.
- Luna may own a complete job, including bounded investigation, when its
  catalog-admitted capability is sufficient. Use Sol for work that needs more
  interpretation or complexity, and Astra only for material risk, frontier
  ambiguity, or an independent frontier review. Architecture or review wording
  alone is not an Astra trigger, and Luna is never forced when more capability
  is required.
- Jev decides model, effort, and lease. Agenter independently selects Fast for
  Luna only when the authenticated runtime catalog advertises it; otherwise use
  Standard. Sol and Astra always use Standard. Never report requested speed as
  served unless the response confirms it.
- Preserve an existing valid lease until the declared phase or user turn ends.
- On technical Jev failure, keep the previous valid native route, otherwise use
  Sol at medium effort; if neither is valid, return a limited explicit error.
- Alternate-provider fallback is disabled unless a future activation explicitly
  opts into it.
- For callback delegation, read and validate the actual parent runtime
  `CODEX_THREAD_ID` before spawning. Never use a title, child ID, or guessed
  ID. Generate a unique `job_id` and call `spawn_agent` with
  `fork_turns="none"` and a self-contained brief containing `job_id`,
  `delivery="callback"`, and `reply_thread_id` equal to the parent ID.
  `scripts/callback_protocol.py` prepares these arguments.
- The child must make one explicit Codex app `send_message_to_thread` call to
  `reply_thread_id` after verifying its work. A native child final answer or
  `delivery.attempts` claim is not callback delivery. If the tool is missing,
  return a blocked native result. Never retry an ambiguous send automatically.
- After dispatch, continue independent work or end the parent turn. Do not
  use `wait_agent`, `wait_threads`, polling, or manual `proceed` messages. On
  the callback-created turn, match `job_id`, terminal status, and evidence;
  then close the finished child, update work-unit state, and continue with
  dependency-valid requested work. A child callback does not imply overall
  closure.
- Optimize for completing the requested scope and stopping, not for continuing
  while related work exists. Track explicit exit criteria and closure state;
  keep a package PASS when its own criteria are met, with downstream work
  tracked separately.
- For ordered milestones or work units, preserve declared dependencies and
  classify each current unit PASS, BLOCKED, or IN PROGRESS. Never skip a
  required unit. A blocked unit stops dependent work; continue another unit
  only when the specification or dependency analysis establishes it is
  independent. Keep completed units PASS and track downstream work separately.
- A blocker requires concrete evidence: unavailable required environment,
  privileges, credential, external decision, upstream dependency, identity
  transition, or an incomplete dependency. Difficulty, failing tests,
  ambiguity, and needed investigation are not blockers. Do not weaken criteria.
  At the dependency boundary, report the unit, evidence, exact prerequisite,
  affected downstream units, and any explicitly independent work; request only
  the concrete user action required.
- Continue required in-scope work automatically; do not ask for generic
  "proceed". Do not start adjacent or future-milestone work, reopen completed
  units, repeat externally blocked gates, or continue auxiliary cleanup after
  acceptance. Elapsed time and a completed subtask are never stop conditions.
- Before closing a substantial request, obtain one bounded independent
  completeness review through the existing routing/capability system. Use a
  self-contained packet with scope, dependencies, criteria, unit states and
  evidence, blockers, unfinished and deferred work, and proposed conclusion;
  delegate with `fork_turns="none"`. The reviewer checks completeness only,
  does not implement or broadly retest, and returns exactly CLOSE, CONTINUE,
  or BLOCKED with concise reasons. Prefer Sol review for Luna execution and a
  stronger independent Sol review when useful; use Astra only for material
  frontier-level closure risk, never for ordinary closure by default.
- On CONTINUE, restore identified in-scope items to the actionable queue and
  continue. On CLOSE, report completion without adjacent work. On BLOCKED,
  stop at the dependency and report its concrete prerequisite and impact.
  Autonomous execution stops only after reviewed CLOSE, a hard dependency
  blocker with no independent required work remaining, or a concrete user
  action requirement. Do not skip dependent units.
- Children inherit the same scope boundary: one bounded job, its verification,
  one callback, then finish.
- Children use the active Jev routing path when it is available. They do not
  bypass Jev by hardcoding a model or provider; the role definition stays
  separate from the executor route.
- Never copy credentials, sessions, logs, databases, or machine-local state
  into shared configuration.
