# General conventions

Applies to every repo, independent of language or framework.

## Git and pull requests

- **Branches**
  - **Naming**: Name work branches `<type>/<slug>`, where `<type>` is a Conventional Commits type — `feat`, `fix`, `chore`, `refactor`, `ci`, `docs`, `style`, `test`, `perf`, or `build` — and `<slug>` is a short kebab-case description of the change. Never use a `claude/` prefix or a random session suffix.
  - **Renaming an assigned branch**: The naming rule above overrides the branch name a session is assigned by default — if you were given one, rename it before the first push.
- **PR review threads**: Always reply on the thread with what changed (or why it wasn't changed), then mark the thread resolved. Do this for every thread you act on, not just the ones that needed discussion.

## Tooling

- **Formatting**: Run the repo's format script after making edits and before every commit. Each language's conventions say what it is.

## Testing

- **Testing internals**: Never widen a module's API for a test. Where something is only public so a test file can reach it, keep it internal and drive it through the public thing that uses it — the test then pins behaviour someone can actually depend on, and survives the internal being renamed or absorbed. A repo's test-support module is the exception: being imported by tests is its whole job.
- **Checking a new test can fail**: A test that passes against broken source pins nothing. Before keeping a new case, break the behaviour it names and confirm that case — and ideally only that case — goes red.

## Comments

- **Where a comment goes**: A doc comment (i.e., above a function) is for _callers_ — what the thing is/does, what it gives back, what it costs them, etc. Any note about _how_ it does that, or explaining a cast, a workaround, or a library's behaviour, etc., goes in a line comment _within_ the function _at_ the code it describes, since it doesn't need to be known to the caller. This goes for any function, internal to a file or exported.
- **Doc comment shape**: A doc comment that runs to more than one line opens with its summary alone — what the thing is, usually one sentence — then a blank line before any specifics: conditions, defaults, the reason it's built the way it is. A comment that is only a summary, however many lines it wraps to, needs no gap.

## Writing

- **Oxford comma**: A list of three or more takes a comma before its final `and` or `or` — in prose, comments, documentation, and commit messages alike.
