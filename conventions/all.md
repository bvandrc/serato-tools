# General conventions

Applies to every repo, independent of language or framework.

## Git and pull requests

- **Branches**
  - **Naming**: Name work branches `<type>/<slug>`, where `<type>` is a Conventional Commits type — `feat`, `fix`, `chore`, `refactor`, `ci`, `docs`, `style`, `test`, `perf`, or `build` — and `<slug>` is a short kebab-case description of the change. Never use a `claude/` prefix or a random session suffix.
  - **Renaming an assigned branch**: This overrides a session's assigned branch name: rename it before the first push.
- **Commit messages and PR titles**: [Conventional Commits](https://www.conventionalcommits.org), using the branch types above.
  - **Summary**: lowercase and imperative, saying what changes for whoever uses the code, not how (`fix: keep saved filters when another device syncs`).
  - **Scope**: optional; leave it off rather than invent one.
  - **Breaking changes**: `!` only in a repo that versions a public API.
  - **Squash merges**: the PR title is the commit message, with ` (#<number>)` appended.
  - **Squashing several PRs together**: only on command. One summary covering them all, with every PR number at the end, oldest first (`chore: update dependencies (#534, #538, #539)`).
- **PR review threads**: On every thread you act on, reply with what changed (or why not), then resolve it.
- **Labels**: Every PR, and every issue that asks for a change, carries at least one _type_ label; more than one is fine where a change really is more than one kind.
  - **Type labels**: named for the Conventional Commits type, except `feat` is `feature` and `perf` is `performance`. A PR's labels include its title's type.
    - **`bug` and `fix`**: `bug` is for issues, `fix` for PRs. A PR is never `bug`.
  - **Issues**: titled like the PR expected to close them (`feat: …`), except bugs, which are `bug: …`. `question` stays on while the issue waits on an answer before work can start.
  - **Action labels**: a label a workflow reads (`run ci`, `preview`, `refresh-data`) is named for what adding it does, with a GitHub description saying so. Each repo's `CLAUDE.md` lists its own in a table: label, what adding it does, and the workflow that reads it.
  - **Other labels** (`a11y`, `question`, `help wanted`, `duplicate`, `wontfix`): go beside the type label, never in place of it, except on an issue that only asks something, which carries `question` alone. Only `a11y` has a title form, as a scope (`fix(a11y): …`). Close `duplicate` and `wontfix` issues with GitHub's matching reason too.
  - **GitHub's defaults**: bring them in line with the table below, renaming rather than recreating so existing issues and PRs carry across.

| GitHub default | Becomes |
| --- | --- |
| `enhancement` | `feature` |
| `documentation` | `docs` |
| `accessibility` | `a11y` |
| `bug` | kept, for issues only; PRs labeled `bug` become `fix` |
| `invalid`, `good first issue` | deleted |
| `question`, `help wanted`, `duplicate`, `wontfix` | kept |

An existing `perf` label is renamed `performance`.

## Tooling

- **Formatting**: Run the repo's format script after making edits and before every commit. Each language's conventions say what it is.

## Testing

- **Testing internals**: Never widen a module's API for a test. Keep the internal internal and test it through the public code that uses it. A repo's test-support module is the exception.
- **Checking a new test can fail**: Before keeping a new case, break the behavior it names and confirm that case, ideally alone, goes red.
- **Trivial cases**: Don't write a case whose whole subject is one plain line of source (a prop spread, a simple ternary, a specific error type): it restates the line rather than pinning behavior.

## Comments

- **Where a comment goes**: A doc comment is for callers: what the thing does, returns, and costs them. How it works, and notes on a cast, a workaround, or a library's behavior, go in a line comment inside the function, at the code they describe. This holds for every function, exported or not.
- **Doc comment shape**: A multi-line doc comment opens with its summary alone, usually one sentence, then a blank line before the specifics (conditions, defaults, why it's built that way). A summary-only comment needs no gap, however many lines it wraps to.

## Writing

- **Oxford comma**: Always, in prose, comments, docs, and commit messages.
