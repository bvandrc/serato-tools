# PyPI publishing conventions

For repos that publish a package to PyPI.

- **Releasing**: Bump `version` in `pyproject.toml` and add its `CHANGELOG.md` section, merge, then publish a GitHub release tagged `v<version>` (`gh release create v1.2.0 --title v1.2.0 --notes ""`). That runs `.github/workflows/release.yml`, built from the [shared PyPI release actions](https://github.com/bvandrc/bvandrc-conventions#pypi-release-actions), whose README has the full file:
  - **Build job**: `pypi-build` builds and checks the distributions, uploads them as an artifact, and fails if the tag isn't `v` + their version.
  - **Publish job**: `release-notes-from-changelog` replaces the release notes with the version's `CHANGELOG.md` section, `pypa/gh-action-pypi-publish` uploads the distributions, and the job attaches them to the release.
  - **Never publish from a machine**: a local `twine upload` skips the tag check and leaves no GitHub release behind the version.
  - **A merge isn't a release**: merging to `main` publishes nothing.
- **Trusted publishing, no token**: PyPI trusts the release workflow's OIDC token, set up as a trusted publisher in the project's PyPI settings. The publish job runs in a `pypi` environment whose `url` is the project's PyPI page. No `PYPI_TOKEN` secret; never add one.
  - **Permissions**: The publish job asks for `contents: write` (to edit the release notes and attach the distributions) and `id-token: write`, each with a comment saying why.
- **Versions are final**: PyPI never accepts a version twice, even after deletion, so a bad upload means a new version.
- **`pyproject.toml`**
  - **`[build-system]`**: setuptools, with a floor that supports the fields used (`setuptools>=77.0` for `license-files`).
  - **`license`**: An SPDX expression (`"MIT"`), not a table, with `LICENSE` committed at the root.
  - **`readme`**: `README.md`, which becomes the PyPI page, so it's written for someone installing: install, usage, and the CLI's arguments.
  - **`[project.urls]`**: `Repository`, `Issues`, and `Changelog` (the `CHANGELOG.md` on GitHub). `Homepage`, when set, points at the repo or docs, not the PyPI page.
  - **`[project.scripts]`**: Each console script points at a `main()` in its module (`serato_crate = "serato_tools.crate:main"`).
- **No runtime version checks or network calls on import or startup**: a package never checks PyPI for newer releases of itself or its dependencies. Users get newer dependencies when the package raises its floor in a release.
- **Versioning**: semver against the public API: what it exports, its console scripts and their arguments, and anything else a user can observe, such as the files it writes. `_`-prefixed names are free to change.
- **`CHANGELOG.md` is the history**: the release notes are copied from it, never written separately.
  - **What goes in**: User-visible changes, added in the PR that makes them, saying what changed for a user, not how. Entries don't name PRs.
  - **Headings**: `## [x.y.z] - YYYY-MM-DD`, newest first. A repo that collects several PRs per release keeps unreleased changes under `## [Unreleased]`, which the release renames.
  - **Version links**: Each heading gets a link definition at the bottom of the file, newest first, comparing the previous version's tag with its own (`[1.2.0]: https://github.com/<owner>/<repo>/compare/v1.1.0...v1.2.0`), which 404s until the release creates the tag. The first version links its release (`.../releases/tag/v1.0.0`), and `[Unreleased]` compares the latest tag with `HEAD`.
  - **Sentences**: Every sentence of an entry ends with a period, the last one included.
  - **Order**: Most significant first, whatever the kind. A large new feature can lead ahead of a breaking change few users will hit (an error's new type, a rarely used attribute made internal); removing something widely used outranks either.
  - **Breaking changes**: Each is marked `**[BREAKING]**`, with an `**Upgrading:**` sub-bullet saying how to move past it.
  - **Rewording past entries**: Release notes don't follow later edits. Rerun the repo's Sync Release Notes workflow, built from the shared [`sync-release-notes`](https://github.com/bvandrc/bvandrc-conventions#pypi-release-actions) action, which rewrites every release's notes from the changelog.
