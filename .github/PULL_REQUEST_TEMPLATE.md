## What

This PR applies dependency upgrades to address open Dependabot security alerts detected in requirements.txt.

## Changes

- Updated pinned versions for packages implicated by Dependabot alerts, including but not limited to:
  - aiohttp 3.8.4 → 3.8.5
  - urllib3 1.26.16 → 1.26.17
  - Pillow 9.5.0 → 10.0.0
  - opencv-python 4.8.0.74 → 4.8.1.76
  - gevent 23.7.0 → 23.12.0
  - mistune 2.0.5 → 2.0.6
  - msgpack 1.0.5 → 1.0.6
  - nbconvert 7.4.0 → 7.5.0
  - fonttools 4.39.4 → 4.40.0
  - requests 2.31.0 → 2.32.0
  - soupsieve 2.4.1 → 2.5.0
  - tqdm 4.65.0 → 4.66.0
  - certifi bumped to 2024.4.0

This commit updates requirements.txt to the patched versions on branch dependabot/fix-all.

## Why

These upgrades address multiple security vulnerabilities flagged by Dependabot in the repository's dependency graph. Some fixes are transitive and are addressed by updating the direct dependency in requirements.txt.

## Testing & Risks

- The upgrades include major/minor releases for packages with native extensions (Pillow, opencv-python, gevent, tornado). Please run CI and validate runtime behavior, image handling, and any GUI interactions.
- If tests fail or runtime issues are found, we can revert specific upgrades or split them into smaller PRs for easier debugging.

## Notes

- If you need me to run additional follow-up PRs to further restrict versions or apply stricter pins, I can do that.

/cc @ckolluru