# T7 visual QA capture matrix

Working surface: the T7 execution-profile transition UI plus the responsive containment fix in `web/components/benchmark-model-picker.tsx`.

## Final captures

All captures are valid RGB PNG files. The 375 px, 768 px, and 1280 px rows use a 900 px browser height and full-page capture. The 200% rows use a 640 x 450 CSS-pixel viewport at device scale factor 2, producing 1280 px-wide output while exercising the 200% reflow operating point.

| Surface/state | 375 px | 768 px | 1280 px | 200% |
|---|---|---|---|---|
| Home, static 8k-only | `home-base-375.png` | `home-base-768.png` | `home-base-1280.png` | n/a |
| Home, mixed 8k/32k | `home-mixed-375.png` | `home-mixed-768.png` | `home-mixed-1280.png` | `home-mixed-zoom200.png` |
| Leaderboard, static 8k-only | `leaderboard-base-375.png` | `leaderboard-base-768.png` | `leaderboard-base-1280.png` | n/a |
| Leaderboard, mixed 8k/32k | `leaderboard-mixed-375.png` | `leaderboard-mixed-768.png` | `leaderboard-mixed-1280.png` | `leaderboard-mixed-zoom200.png` |
| Compare, static 8k-only | `compare-base-375.png` | `compare-base-768.png` | `compare-base-1280.png` | n/a |
| Compare, current-vs-legacy | `compare-mixed-375.png` | `compare-mixed-768.png` | `compare-mixed-1280.png` | `compare-mixed-zoom200.png` |
| Model family, legacy snapshot | `model-legacy-375.png` | `model-legacy-768.png` | `model-legacy-1280.png` | `model-legacy-zoom200.png` |
| Compare, keyboard focus | `compare-mixed-focus-375.png` | n/a | n/a | n/a |

## Recorded observables

- No page-level horizontal overflow in any final capture. Dense score tables retain their intentional local horizontal scroller.
- The exact transition notice is absent in all base captures and present in every mixed home/leaderboard capture.
- Mixed leaderboard captures contain both text-bearing `Current` and `Legacy` badges, with readable summaries `32k reasoning · 16k final · 64k context` and `8k static reasoning`.
- The current-vs-legacy compare captures explicitly select `ticket_cccccccccccccccccccccccccccccccc` and `ticket_dddddddddddddddddddddddddddddddd` and render `Index and axis deltas withheld: execution-profile semantic identities differ or are incomplete.`
- The 375 px keyboard capture focuses `#right-config`; the focus ring is visible without clipping.
- DOM accessibility audit on the mixed leaderboard found no unlabeled interactive controls and no duplicate IDs. The exact notice uses a live status region; profile state remains readable without color because the badge and summary are text.
- Heading order on the affected leaderboard surface starts at one `h1` with no skipped level in the injected transition content.

## Objective image-diff evidence

The bundled `visual-qa.mjs image-diff` tool was run for base-vs-mixed home, leaderboard, and compare captures at all three widths. Dimension differences are expected because the live fixture adds two rows and the transition notice. Alpha integrity passed in all nine comparisons. Similarity scores were:

- 375 px: home 49, leaderboard 25, compare 65.
- 768 px: home 47, leaderboard 22, compare 61.
- 1280 px: home 44, leaderboard 16, compare 68.
- The focused-vs-unfocused 375 px compare pair matched dimensions and scored 93/100; the remaining difference is the selected focus presentation.

## Manual walkthroughs

- Methodology-conscious reader: sees the exact non-compute-matched warning before the mixed leaderboard and receives no cross-profile score delta in Compare.
- Keyboard reader: can focus both compare selectors and encounters a visible focus ring; every interactive control has an accessible name.
- Low-vision reader: all four 200% reflow captures remain within the page viewport, and notice/badge copy wraps naturally.
- Mobile reader: the model-picker row that previously expanded a 293 px grid column to 411 px is contained after adding `min-w-0`; the final 375 px home captures report 375 px client and scroll widths.

## Limitations

The installed in-app Browser runtime reported no available browser instance. Captures used the repository's installed Playwright client with system Chrome 150.0.7871.188 against the production static export. No browser or package installer was run because that would write outside the repository.
