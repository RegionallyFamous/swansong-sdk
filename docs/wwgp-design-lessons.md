# WWGP 2001–2003 game-design lessons

This review covers the official Qute catalogs for all three WonderWitch Grand
Prix contests, the linked entry documentation that remains available, the
final results, and contemporary ceremony reporting. The catalogs contain 147
valid entries in 2001, 74 in 2002, and 57 in 2003. The broad game-like set is
92 entries in 2001, 54 actual games in the 2002 GAME division, and 35 games
plus four game-like freestyle/challenge entries in 2003.

The evidence boundary matters. Catalog rows and available manuals were reviewed
for every plausible game. Some downloads were withheld by the original contest
organizers, a few bundles contain no useful manual, and this review did not
claim a SwanSong playthrough of every historical binary. Mechanics that cannot
be recovered responsibly remain unknown rather than guessed.

Primary sources:

- WWGP 2001 [complete catalog](http://wwgp.qute.co.jp/2001/allworks.htm)
  ([archived](https://web.archive.org/web/20010419111750/http://wwgp.qute.co.jp:80/2001/allworks.htm))
  and [final results](http://wwgp.qute.co.jp/2001/finalresult.htm)
  ([archived](https://web.archive.org/web/20010819104714/http://wwgp.qute.co.jp:80/2001/finalresult.htm))
- WWGP 2002 [complete catalog](http://wwgp.qute.co.jp/2002/allworks.htm)
  ([archived](https://web.archive.org/web/20020726094323/http://wwgp.qute.co.jp:80/2002/allworks.htm))
  and [final results](http://wwgp.qute.co.jp/2002/finalresult.htm)
  ([archived](https://web.archive.org/web/20020727031329/http://wwgp.qute.co.jp:80/2002/finalresult.htm))
- WWGP 2003 [complete catalog](http://wwgp.qute.co.jp/2003/entries/index.html)
  ([archived](https://web.archive.org/web/20030801141123/http://wwgp.qute.co.jp/2003/entries/index.html))
  and [final results](http://wwgp.qute.co.jp/2003/finalresult.html)
  ([archived](https://web.archive.org/web/20030801141819/http://wwgp.qute.co.jp/2003/finalresult.html))
- [2001 ceremony report](https://game.watch.impress.co.jp/docs/20010305/ww.htm)
  and [2002 ceremony report](https://game.watch.impress.co.jp/docs/20020623/wwgp.htm)

## What the strongest games do

### Start with one memorable verb

The clearest winners can be explained in one sentence. *Judgement Silversword*
switches between complementary shot/field modes. *Nametry* turns name entry
into a timed spatial game. *DicingKnight* makes dice uncertainty part of
combat, healing, exploration, and persistence. *RAVE HUNTER* lets the player
choose when a prepared line clears. *WAVE R* makes every jump send a useful but
dangerous ripple through the ground. *Es=Loss* changes attack and defense with
one stance switch.

The lesson is not to stop at one mechanic. It is to make the other systems
express the same mechanic instead of competing with it.

### Put mastery around a short run

The catalogs repeatedly use time attack, survival, chains, multipliers, grades,
named rankings, unlocks, stage select, assists, and alternate modes. These
systems produce replay value without requiring another large content set.
Strong examples also make the cost of risk legible: delaying a clear raises a
bonus, a dangerous route saves time, a charge increases power but reduces
mobility, or an aggressive defense field raises a multiplier.

The SDK response is `swan/timing.h`, `swan/score.h`, and `swan/records.h`.
They are caller-owned and deterministic so a game can trace, replay, test, and
persist the same run without hidden time or allocation.

### Design for the actual handheld

Distinctive entries use portrait play, independent X/Y-pad characters,
differential tank steering, alternating-hand swimming, shared-console hidden
information, stereo positioning, one-button control, or even physical console
rotation. Generic ports tend to inherit awkward controls; hardware-native games
turn the unusual button layout into the premise.

SwanSong already supplies semantic actions, raw X/Y keys, tap/hold/chord
gestures, static orientation-aware manifest bindings, and runtime display
orientation. Runtime display rotation does not remap semantic actions. A game
that asks the player to rotate the physical console during play must therefore
own and test its raw-key rotation policy explicitly.

### Treat the front end as part of the game

The most complete entries surround play with a readable title, instructions,
options, difficulty or assist choices, pause, result/grade, ranking, retry, and
safe suspend/continue behavior. Many weaker entries have an interesting core
but explicitly lack sound, endings, records, tuning, documentation, or a stable
save path.

Use the existing scene runtime, transactional saves, deterministic outcomes,
and fresh-boot play contracts to test the entire route, not only the playfield:

1. title ready;
2. instructions/options and difficulty;
3. play and pause;
4. success or failure result;
5. record insertion and persistence;
6. retry and return to title;
7. session reset from every relevant state.

### Spend bytes on density, not breadth

*MagicalHarvest* fit 128 maps and an action RPG into 64 KiB. Puzzle books,
stage tables, procedural dungeons, branching text, parameterized actors, and
palette/tile reuse recur across the catalogs. In the 2002 ceremony report,
memory shortage was the complaint repeated by the award recipients.

SwanSong's asset budgets, dirty tile grids, fixed pools, seeded RNG, and data
authoring already support this approach. Prefer compact ROM-owned tables and
small caller-owned runtime state. Do not duplicate content as code or allocate
for a worst case that the game never presents.

### Make motion readable before making it difficult

Many promising games use inertia, charging, braking, bounce, homing, knockback,
or a moving floor. Their manuals also reveal a recurring failure mode: the
physics are interesting but the facing, collision, control state, or failure
cause is unclear.

`swan/motion.h` supplies deterministic signed 32-bit motion with eight
fractional bits, clamps, braking, and bounce. A game still needs anticipation
frames, readable state changes, useful sound, generous early stages, and
explicit collision feedback. Physics is the rule; telegraphing is the
interface.

## A practical quality bar

Before expanding a game, verify that a fresh player can answer these questions
from the screen and controls:

- What is my one main verb?
- What state changes when I use it?
- Why did I succeed or fail?
- What risk can I choose for a better result?
- What changes on the next run besides raw difficulty?
- Can I pause, retry quickly, and recover safely after power loss?
- Does the title/result flow look as intentional as the playfield?
- Does the game remain readable on its declared mono/Color hardware and both
  tested orientations?

If those answers are strong, add stages, enemies, modes, or story. The contest
history consistently rewards a small coherent game with finished feedback over
a larger unfinished one.
