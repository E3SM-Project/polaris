# Hunting for bugs: instructions for agents

These instructions are for an agent that a developer has asked to hunt for
bugs in Omega and Polaris, and for any agent that finds a bug while doing
something else.  Read the Polaris `AGENTS.md` at the root of this checkout as
well; it still applies.

Below, `bug_hunt.py` means `./utils/bug_hunt/bug_hunt.py`, run from a shell
with a Polaris load script sourced.

## If you found a bug while doing something else

1. **If it blocks your task, fix it as part of the task**, in a commit or
   branch of its own, and only as far as the task needs.  A bug blocks the
   task when the task cannot reach its goal without a fix.  Turning off or
   working around the feature that fails does not make it a non-blocker if
   the goal needs that feature.  Whatever the fix turns up is judged the same
   way, so one blocker does not start a chain of fixes.  Record it:
   `bug_hunt.py park ... --fixing <branch or PR>`.
2. **Otherwise, park it and go back to your task.**  Do not reproduce it,
   search for issues or fix it:

   ```
   bug_hunt.py park --claim "<the bug, in one line>" \
       --name "<a few plain words: what goes wrong, and where>" \
       --where <file>:<line> --owner omega --confidence inferred \
       --evidence <a file with what you saw> --context "<your task>"
   ```

3. **Say so in one line of your report**, such as
   `Parked "<name>": <claim>`.

If you cannot tell whether a bug blocks your task, ask the developer.  The
same applies to review findings that a pull request did not introduce.
Without a ledger, `park` prints the finding instead; put it in your report.

## Rules for a hunt

- **Ask before anything outward-facing.**  Filing or editing an issue
  (`file --post`), commenting on one, submitting a job (any `sbatch` or
  `qsub`) and pushing a branch each need the developer's permission, given
  in your own session.  Without it, run the command without `--post` and
  show the developer what it would do.  Answering `file` or `batch` in the
  digest is that permission for the finding answered.  Writing to the
  ledger needs no permission.
- **A hunt never fixes.**  A finding the developer wants fixed gets a
  `handoff` prompt for a new session.
- **Stop investigating once a finding can be ranked.**  Anything more is a
  `dig` the developer chooses in the digest, with its cost stated.
- **Refer to a finding by its name** whenever you write for a person,
  never by its ID alone.  A name is a few plain words saying what goes
  wrong and where, as a developer would say it aloud, such as "Frontier
  nightly can't find python" or "coupled answers change with the processor
  layout".  A name may use terms Omega developers know, the names of
  components, schemes, machines and suites listed by `bug_hunt.py
  name-terms`, as in "EAMxx coupled debug tests crash at startup on
  Chrysalis".  CIME test types and compsets (`PEM`, `WCYCLXX1850NS`),
  option names, error codes (`FPE`) and row names (`craycray-mphipcc`) go
  in the claim and the evidence, not the name; `update --name` warns about
  words like these.  When the developer renames a finding with a term not
  on the list, add it: `bug_hunt.py name-terms --add <term>`.  `harvest`
  and `park` give a rough name; rewrite it at triage with `update
  --name`.  Once a digest has shown a name, change it only if
  the developer asks.  Commands take a name or an ID.
- **Write references in full**, as `E3SM-Project/Omega#673`, never
  `Omega#673` or `#673`: hunts work across several repositories, and
  GitHub links only the full form.  `file` expands short ones in what it
  posts, outside code blocks.
- **Say how sure you are.**  `measured` means seen in a test's output or
  reproduced; `inferred` means read from code or indirect evidence, with what
  would disprove it; anything else is `speculative`.  No superlatives.  A
  claim says no more than its confidence: if a failure is measured but its
  cause is inferred, leave the cause out of the claim, or rate the finding
  `inferred`.
- **Build only on a login node, through Polaris** (`polaris suite --build`);
  never run a model there.
- **End your turn with the digest.**  A hunt's log is long, and the
  developer should be able to decide without scrolling back through it.
  The digest goes last in your message, in full, followed only by your
  questions.  Never ask for answers to decisions by number alone, or point
  to an earlier message or to the digest's file: until every decision is
  answered, each turn ends with the open ones again.  If the developer
  leaves the rest for later, stop asking.  They stay open in the ledger,
  and the next digest raises them again.
- **Show the developer things in your reply.**  Any issue you need
  permission to post goes in your message, in full.  Read every issue
  before posting it, and give the link once it is posted.

## A hunt, step by step

The developer says which of these to do.  A hunt with no instructions
harvests and triages.

Begin every hunt with `bug_hunt.py start`, which begins the hunt's record
and prints its name, such as `2026-11-12-2`: the date and its number that
day.  Later commands write to the hunt this clone started last, so two
hunts on one day keep two records.  If two agents hunt in one clone, each
passes its own hunt's name with `--hunt <name>` on every command.  A hunt
keeps its name past midnight.  If another clone pushed a hunt with the same
name first, yours takes the next number when it pushes, and `status` shows
it.

1. **Status:** `bug_hunt.py status` says what the ledger holds and what was
   last harvested and reviewed.
2. **Harvest:** `bug_hunt.py harvest` reads CDash since the last harvest.
   `bug_hunt.py harvest --no-cdash --local --roots <dirs>` reads Polaris and
   CIME runs on disk.  If the developer says a row stopped reporting for a
   reason that is not a bug, such as an allocation out of compute hours,
   put it on hold: `bug_hunt.py hold <machine>/<compiler> ... --reason
   "<why>"`.  A harvest does not report a row on hold as stopped, and takes
   it off hold once it reports again; `hold --release` does so sooner.
3. **Match:** every finding with a new key is matched before it is
   triaged, whatever its source: a harvest, a review or `park`.
   `bug_hunt.py match <id>` prints the open issues and pull requests (and
   issues closed in the last 90 days) that may track it, from searches for
   its test or file and the identifiers in its claim.  Many open issues were
   filed outside any hunt, so the ledger alone does not show what is known.
   A candidate found by the test name or file, or by a term that finds
   few results, needs a ruling.  Those found only by broad terms, such as
   a tool's name that every pull request tested with it mentions, are
   listed in one line and need none, even when two broad terms find the
   same one.

   The search is where you start, not where you stop: a redundant issue
   costs developers' time and their trust in the hunter far more than
   searching costs you.  Use your judgment to look further: skim the
   candidates that need no ruling, search with your own words for the
   symptom, and read the open issues about the same code.  Anything you
   find that may cover the bug gets a ruling like any other candidate.

   Read every candidate that needs a ruling, and decide and record one of:
   - it is tracked: `bug_hunt.py update <id> --link <owner>/<repo>#<n>
     --status tracked`.  This includes a finding that is one instance of an
     open general issue, such as one of many loops that ignore the minimum
     layer index: it is not filed on its own, and commenting on the general
     issue is a decision for the developer;
   - a candidate is a different bug: `bug_hunt.py update <id>
     --not-duplicate "<owner>/<repo>#<n>: <why it is different>"`, so the
     digest and `file` know it was ruled out;
   - it has the same cause as another finding, such as several tests that
     began failing after the same merge: `bug_hunt.py update <kept id>
     --merge <id>` folds `<id>` into `<kept id>`, the finding that stays,
     usually the older one that a digest has already shown;
   - some rows fail for another reason: `bug_hunt.py update <id> --split
     <row>,<row>`.  This also undoes a "came back" that those rows set
     off;
   - it is new: leave it.
   Whenever a hunt finds it filed a duplicate, or a list of candidates
   needing a ruling is mostly noise, add the case to the matching corpus,
   `tests/bug_hunt/corpus` (its `README.md` says how), so the matcher is
   tested against it from then on.

   `match` marks the pull requests merged before the first failure, which
   may have caused it, and those merged before it passed again, which may
   have fixed it.

   `bug_hunt.py match --refresh` checks the links of tracked findings, so
   one that still fails after its issue closed or its fix merged is raised
   again.  It also lists tracked findings whose links have all closed and
   that have not failed since; the digest shows them as closed upstream.
   Read each link: if each was closed by a fix, `bug_hunt.py update <name>
   --status fixed`.  A link closed as a duplicate is replaced by the issue
   it duplicates: `--unlink <old> --link <the original>`.
4. **Review** (only if asked): a review reads code, looking for bugs no
   test has caught.  All of Omega and Polaris is in scope, old code as much
   as recent merges, since the oldest code gets the least scrutiny.
   `bug_hunt.py review` lists, by directory and with sizes, the files in
   Omega's `components/omega/src` and Polaris' `polaris` package that no
   review has read or that changed after their review; give it paths to
   narrow the list.  Read the part the developer names, or else pick a
   related group of unreviewed files sized for one review, with code that
   E3SM v4 runs before code outside it.  `bug_hunt.py review --merges`
   lists the merges since the last review of merges instead.

   Look only for code that gives wrong answers or fails: missing halo
   exchanges, races on GPUs, out-of-bounds or uninitialized values, wrong
   vertical bounds, inconsistent units or constants.  Start from the bugs
   already known, the ledger's findings and the open issues in both
   repositories, and hand both to any agent that reviews.  Before recording
   a candidate, search the open issues for the files, functions and
   variables it touches.  Record at most ten candidates, each with the
   quoted code and a concrete way it fails: `bug_hunt.py park --source
   review ...`, then match each as in step 3.  Then record what was read:
   `bug_hunt.py review --record "<what you reviewed>" <files or
   directories>`, with `--omega <sha>` and `--polaris <sha>` for the
   commits read if either branch has moved since it was listed.  A file
   counts as reviewed until it changes.
5. **Campaigns** (only if asked): set up the campaign as `campaigns.yaml`
   describes, passing `-P` to every `polaris suite` and `polaris setup`,
   state its cost, and ask before submitting.  When the jobs are done,
   harvest their work directories with `--local`.  Before blaming Omega for
   a task that failed under `polaris parallel`, rerun the task serially
   (`polaris serial` in its directory, in a job); if it then passes, the
   finding is Polaris'.
6. **Triage:** first explain each failure that has ended (a harvest lists
   them, with the merges before it passed).  Read those merges and the
   `match` candidates.  If one of them fixed it, link it and set it
   `fixed`; if the merge that introduced the failure is clear, record it
   with `--caused-by <owner>/<repo>#<n>`, not as a link, since links are
   what track or fix a finding.
   Only a failure that nothing explains is ranked as one that has ended,
   one level lower.

   Then give each open finding a name, an owner, severity and confidence by
   the rubric below, and a claim, what was expected, how to reproduce it,
   and a proposed answer:

   ```
   bug_hunt.py update <id> --name "<a few plain words>" \
       --owner omega --severity S1 \
       --confidence measured --claim "..." \
       --expected "..." --reproduce "..." --propose file
   ```

   `update` sets the priority from the rubric.  A different priority
   (`--priority`) needs a `--note` saying why, which the digest shows.  An
   Omega bug that matters only for a feature or option outside E3SM v4
   names the entry it depends on, with `--outside-v4 <entry>`.
   `bug_hunt.py outside-v4` lists the entries; add one with `--description`
   and `--source` only when the developer or a code owner says so, or when
   the v4 roadmap does.

   A finding that belongs in a clean-up batch gets `--theme <area>`: the
   area of code one pull request would touch and one developer would own,
   such as a task family (ice shelves), a utility (Omega PR testing), a
   part of Omega (KPP), or one mechanical fix across files (compiler
   warnings).  A layer or category, such as tasks and steps, tests and CI
   or error handling, is not a theme.  Before batching, ask whether one
   person would fix the lines in one sitting and one pull request.  A
   small finding with no partner, in the ledger or in an open batch, is
   filed on its own with `priority: low`: small does not mean batchable.
   The digest shows a P3 or P4 finding only with its partners, the other
   findings with its owner and theme, as one decision that opens with the
   theme and then describes each finding.  A finding worth digging into gets
   `--dig "<what and its cost>"`.  Open the `--evidence` with a paragraph of a few
   sentences, under 100 words, saying why you believe the claim, which
   change introduced it if known, and what it affects; put the excerpts
   after a blank line.  The digest shows only that first paragraph.
7. **Digest:** `bug_hunt.py digest --omega <sha> --polaris <sha>`, and end
   your turn with it.
8. **Answers:** the developer answers each decision with one word.
   - `file`: `bug_hunt.py file <id> --title "<under 90 characters>"`
     searches again and prints the candidates above the issue.  Read both;
     code names in the evidence summary need backticks.  Then post it with
     `bug_hunt.py file <id> --title "..." --post --agent "<your name>"`,
     adding `--co-drafted` if the developer directed what the issue says.
     `--post` refuses while any candidate that needs a ruling is neither
     linked nor ruled out with `--not-duplicate`; that is a floor, not the
     whole check.  Before posting, look again as in step 3, beyond what
     `file` lists.  If anything turns out to be the same bug, link it, do
     not file, and tell the developer.
   - `batch`: answers a batch decision for every finding in it, except any
     the developer names to file on its own or leave out:
     `bug_hunt.py file <id> <id> ... --batch <theme>`, checked and posted
     as for `file`.  One run adds them all, since each body edit replaces
     the whole body.  A
     batch closes once every line is checked off or struck out as not a
     bug.  The pull request that fixes a line names it, and its author or
     reviewer checks the box; the hunter never does.  `match --refresh`
     lists a finding whose line is done as closed upstream, to confirm and
     set `fixed`, and a batch whose lines are all done as ready to close.
     Close it only when the developer says so (`gh issue close <n> --repo
     <owner>/<repo>`).  A closed batch is never reopened: a later finding in
     the same area starts a new batch, which links the last one.
   - `log`: `bug_hunt.py update <id> --status logged --answer log`.
   - `dismiss`: `bug_hunt.py update <id> --status dismissed --answer
     dismiss --note "<why>"`.
   - `dig`: `bug_hunt.py update <id> --answer dig`, investigate as stated,
     then update the finding and ask again.  If the dig has to wait, for a
     machine or a person, `bug_hunt.py update <id> --status digging --note
     "<what it waits for>"`: the digest then counts it in one line instead
     of asking again, and each hunt does it once it can.  The answer covers
     the cost stated in the digest, but a compute job still needs the
     developer's permission before it is submitted.  A dig that needs another
     machine is a handoff: a prompt for an agent there, saying how to get
     this branch and the ledger, what to look at, and what to record.  Put
     the checks that need no special access first, so that a directory the
     agent cannot read does not stop the rest.
   - If the developer is handling it outside the hunt: `bug_hunt.py update
     <id> --status fixing --fixing "<who or where>" --note "<why>"`.  Hunts
     leave it alone, and a harvest raises it again only if a new row fails.
     Set `--status fixed` once it is resolved, or `--status new` to bring it
     back.
9. **Fixing** is separate work: `bug_hunt.py handoff <id>` prints the prompt
   for a new session.

## Ranking

| Severity | Meaning |
|---|---|
| S1 | wrong or lost results: answers that depend on decomposition, threads or restarts; runs that do not repeat; broken conservation; output silently overwritten |
| S2 | a failure in regular testing: a CTest, an `omega_pr` or `omega_nightly` task, a coupled test or the build, on a row tested nightly or for pull requests |
| S3 | other failures: debug builds, tasks and rows not tested regularly, errors that hide their cause, slowdowns, warnings that point to a fault |
| S4 | cosmetic: other warnings, names, documentation, log messages, dead code |

| Priority | Findings | Goes to |
|---|---|---|
| P1 | S1 measured; S2 measured on more than one row | an issue of its own, `priority: high` |
| P2 | S1 inferred; S2 measured on one row; S3 measured on more than one row | an issue of its own, `priority: medium` |
| P3 | other S3; S2 inferred | a clean-up batch, or an issue of its own |
| P4 | S4 | a clean-up batch, below the P3 lines, or an issue of its own |

A speculative finding stays in the ledger, whatever its severity, until a
test or a closer reading confirms it.  A bug that came back after its issue
was closed moves up one level.  An Omega bug that matters only for a
feature or option outside E3SM v4 moves down one level, but no lower than
P3.  The features in v4.0 are those in the Ocean section of the E3SM v4
roadmap; an option is in v4 only if v4 turns it on, which Omega's defaults
do not show.  When v4's setting is not written down, propose one, say so in
the digest, and let the code owner decide; a code owner who relabels the
issue has decided.  `park`, `harvest` and `update` set the priority from
these tables, the rows a finding fails on and the list outside v4, so it
changes as rows are added.

## Owners

| Owner | Covers | Issues go to |
|---|---|---|
| `omega` | Omega's code and build | E3SM-Project/Omega |
| `polaris` | tasks, steps, framework and utilities | E3SM-Project/polaris |
| `e3sm` | other components, CIME, the coupler | E3SM-Project/Omega, labeled `Coupled` |
| `environment` | modules, compilers, file systems, queues, deployment | the developer decides (`--repo`) |
| `unknown` | | none until it is known |

Evidence decides the owner.  A failing Polaris step that does not run the
model points to Polaris.  A coupled failure that a standalone Omega test also
shows points to Omega; one that none shows is `unknown` until narrowed down.
A failure on one row while the same commits pass on others suggests the
environment without showing it.
