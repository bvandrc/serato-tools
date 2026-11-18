# PyPI publishing conventions

For repos that publish a package to PyPI.

- **Releasing**: Bump `version` in `pyproject.toml` and add its `CHANGELOG.md` section, merge, then publish a GitHub release tagged `v<version>` (`gh release create v1.2.0 --title v1.2.0 --notes ""`). Publishing it runs `.github/workflows/release.yml`, built from the [shared PyPI release actions](https://github.com/bvandrc/bvandrc-conventions#pypi-release-actions) in bvandrc-conventions, whose README has the full file:
  - **Build job**: `pypi-build` builds and checks the distributions, uploads them as an artifact, and fails if the tag isn't `v` + their version.
  - **Publish job**: `release-notes-from-changelog` sets the release notes to the version's `CHANGELOG.md` section, replacing any written on the release, then `pypa/gh-action-pypi-publish` checks the distributions' metadata and uploads them, and the job attaches them to the release.
  - **Never publish from a machine**: a local `twine upload` skips the tag check and leaves the PyPI version with no GitHub release to point back at.
  - **A merge isn't a release**: merging to `main` publishes nothing. The release is the deliberate step.
- **Trusted publishing, no token**: PyPI trusts the release workflow's OIDC token (`id-token: write`), configured as a trusted publisher on the project's PyPI settings page. The publish job runs in a `pypi` environment, whose `url` is the project's PyPI page. There is no `PYPI_TOKEN` secret to store or rotate, and none should be added.
  - **Permissions**: The publish job asks for `contents: write` (to edit the release's notes and attach the distributions) and `id-token: write`, each with a comment saying why.
- **Versions are final**: PyPI never accepts the same version twice, even after a release is deleted, so a bad upload means a new version.
- **`pyproject.toml`**
  - **`[build-system]`**: setuptools, with a floor that supports the fields used (`setuptools>=77.0` for `license-files`).
  - **`license`**: An SPDX expression (`"MIT"`), not a table, with the `LICENSE` file committed at the root.
  - **`readme`**: `README.md`, which becomes the PyPI page, so it's written for someone installing the package: install, usage, and its CLI's arguments.
  - **`[project.urls]`**: `Repository`, `Issues`, and `Changelog` (the `CHANGELOG.md` on GitHub), so PyPI links back to each. `Homepage`, when set, points at the package's own repo or docs, not its PyPI page.
  - **`[project.scripts]`**: Each console script points at a `main()` in its module (`serato_crate = "serato_tools.crate:main"`).
- **No runtime version checks or network calls on import or startup**: a package never checks PyPI for a newer release of itself or its dependencies, or warns about one. Users get a newer dependency when the package raises its floor and publishes a release.
- **Versioning**: semver against the package's public API: what it exports, its console scripts and their arguments, and anything else a user can observe, such as the files it writes. Python's `_`-prefixed names are internal and free to change.
- **`CHANGELOG.md` is the history**: the GitHub release notes are copied from it, not written separately, so there's one copy to keep right.
  - **What goes in**: User-visible changes, added in the PR that makes them. Entries describe what changed for a user, not how; they don't name PRs, since one often spans several. The compare link lists them, and `git blame` leads from an entry to its PR.
  - **Headings**: A version's heading is `## [x.y.z] - YYYY-MM-DD`, newest first. Changes merged but not yet released, in a repo that collects several PRs into one release, go under `## [Unreleased]` until the release renames that heading to the version.
  - **Version links**: Each heading gets a link definition at the bottom of the file, newest at the top of the list, comparing the previous version's tag with its own (`[1.2.0]: https://github.com/<owner>/<repo>/compare/v1.1.0...v1.2.0`). The link 404s until the release creates the tag. The first version links its release (`.../releases/tag/v1.0.0`), and `[Unreleased]` compares the latest tag with `HEAD`.
  - **Sentences**: End every sentence of an entry with a period, the last one included, so an entry of two sentences doesn't end one with a period and not the other.
  - **Breaking changes**: Each comes first in its version (or its section of one), marked `**[BREAKING]**`, with an `**Upgrading:**` sub-bullet saying how to move past it.
  - **Rewording past entries**: A release's notes don't follow later edits to its section. Rerun the repo's Sync Release Notes workflow, built from the shared [`sync-release-notes`](https://github.com/bvandrc/bvandrc-conventions#pypi-release-actions) action, which rewrites every release's notes from the changelog.
