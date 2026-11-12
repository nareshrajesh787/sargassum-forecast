# History rewrite: Claude co-author lines removed (2026-11-12)

At the owner's request, the `Co-Authored-By: Claude …` trailer lines were removed from commit messages with
`git filter-repo --message-callback`. **Nothing else changed.** Every rewritten commit was checked against the original
history (backup bundle kept outside git by the owner):

- file tree (all content): identical for all 40 commits
- author, committer, author date, commit date: identical
- message: identical except the removed line (22 commits had one)
- tags (`v0.1-test-frozen`, `sir-archive-*`): moved to the rewritten equivalent commits, same trees, same tag messages

## Frozen test evidence still holds

The test-season freeze is proven by **content**, not by commit hashes. The frozen model file's sha256
(`c355696f5a1b8e8534d4262b15f658911481a3d0fbe8a957e9bbf0f25f54518c`) is unchanged and is what `eval/run_test.py` checks.
`outputs/bundle_verify.json` shows the committed forecast bundle reproducing all frozen test predictions. A clean-clone `make results`
retrained the identical model (WORKLOG). The tag `v0.1-test-frozen` now points to the rewritten commit with the identical tree.

Old hashes quoted in committed files resolve here:

| Reference | Old commit | New commit |
| --- | --- | --- |
| Test unlock `git_head` (`outputs/results_test_meta.json`, `data/test_lock/UNLOCK.json`) | `2448db9c1139` | `ef054febde70` |
| Frozen validation stage / model freeze (WORKLOG) | `08ddcce5d411` | `63d683c36d54` |
| Test outputs + tag commit (WORKLOG) | `d8e708d236a9` | `ffe6fbdfadbb` |
| Failure gallery commit | `60f2a6788da8` | `f5c763a1b1fb` |
| Phase 7 release docs (WORKLOG) | `6e63c8601de3` | `241d69086a93` |
| make results fix (WORKLOG) | `2b38129e7bfd` | `e16a1ba87802` |

Full map, old → new, all commits (also in `docs/history-rewrite-commit-map.csv`).
