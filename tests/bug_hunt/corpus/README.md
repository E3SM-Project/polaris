# The bug hunter's corpus

Real cases from hunts, with the responses they were matched or harvested
against, saved here because live GitHub searches and CDash results change
under the tests. `test_bug_hunt_corpus.py` replays them offline. A search or
CDash response a case needs but does not have fails the case, and means the
case needs refreshing, never that the search found nothing.

Add a case whenever a hunt files a duplicate, or `match` asks for rulings
that are mostly noise (see `utils/bug_hunt/AGENTS.md`).

## `match/<case>/`

| File | Role |
|---|---|
| `finding.yaml` | the finding, as the hunter matched it (input) |
| `searches.yaml` | GitHub's response to each search the matcher runs for it, trimmed to the fields it reads, and the day they were saved (input) |
| `expected.yaml` | what must come of it (expected output) |

`expected.yaml` says:

- `date`: the day the closed issues are counted back from, the day the
  searches were saved;
- `must_rule`: the issues and pull requests that must need a ruling, such as
  the duplicates a hunt filed;
- `related`: those that need a ruling and are worth one, though not
  duplicates, so they are not noise;
- `timing`: what `match` must say of a pull request merged when the
  failure began or ended;
- `max_noise`: the most candidates that need a ruling and are neither, set
  at the level the case had when it was added, so that noise cannot grow
  unnoticed and can be lowered as matching improves.

| Case | Why it is here |
|---|---|
| `cron_results_lost_when_driver_dies` | A claim that names the `omega_nightly` suite, which found 9 issues across both repositories on 2026-11-12, one short of `FEW_RESULTS`, so 5 unrelated issues needed a ruling before E3SM-Project/polaris#968 was posted. The saved searches leave out #968 itself, whose posting made the suite name broad. |
| `gpu_race_already_reported` | Filed twice on 2026-10-30 (E3SM-Project/Omega#664) though Omega#631 had reported it; found only by `ProvPseudoThickness`, an identifier in the claim. |
| `one_instance_of_a_general_issue` | Filed on 2026-10-30 (Omega#665) though it is one instance of Omega#434, about loops that ignore the minimum layer index; found only by `MinLayerCell`, the family of `MinLayerEdgeBot` in the claim. Searches sorted by recency lost #434 to recent pull requests until they were sorted by best match and issues were counted apart from pull requests. |
| `pr_testing_cleanup_marker` | A claim that names a tool, `omega_pr_test.py`, which every Omega pull request tested with it mentions, and E3SM: 30 candidates needed a ruling on 2026-11-11, all unrelated. |
| `pr_testing_hand_submitted_jobs` | The same tool name, with no other broad term. |
| `sphere_operator_fix_and_cause` | `HORZOPERATORS_SPHERE_TEST` failed around 2026-11-07: Omega#639 introduced it and #643 fixed it, which `match` must mark as merged before the first failure and before it passed. The CTest name is also in every Omega Testing comment and in pasted CTest logs. |

The noise left is of two kinds: old issues with pasted CTest logs, which
list every CTest and source file (Omega#217, #565, #368, #618), and issues
whose reproduction steps run `omega_pr_test.py` (Omega#686, #658, #666,
#678).

## `harvest/<case>/`

| File | Role |
|---|---|
| `cdash/omega/*.json` | CDash's responses, as the hunter caches them, trimmed to the builds the case reads (input) |
| `expected.yaml` | the nights harvested, the kinds of build, and what each occurrence must record (expected output) |

| Case | Why it is here |
|---|---|
| `new_tests_have_no_last_pass` | The EAMxx coupled tests first ran on Chrysalis on 2026-11-08 and failed from that night. CDash lists only failures, so the night before once counted as their last pass, and an issue said "last passed 2026-11-07" for tests that did not exist then. They must have no last pass and record 11-08 as the first night they ran. |

## Running against live searches

`live.py` runs the cases against live GitHub searches and CDash, by hand and
never in CI, to show when GitHub's search has changed under the matcher:

```
python tests/bug_hunt/corpus/live.py
python tests/bug_hunt/corpus/live.py --save <case>
```

`--save` replaces a case's saved responses with live ones. Check the
comparison first, and review the expectations against the new responses.
