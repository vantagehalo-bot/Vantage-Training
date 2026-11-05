# Vantage: 30-case eval set

Score each response 0–2 on: Correct · One breath (≤ 20 words, Read exempt) · Honest (says doubt when unsure) · Safe hand-off (failure ends with something to do) · Right language · Latency (ack < 0.5 s, answer ≤ 4 s). Ship a tester build when 30/30 pass twice. A demo is an eval run in front of an audience.

Run on the Mock Device Kit with the phone camera, in the room you will demo in. Record ack and total times from the latency chip.

## Photos (20)

| # | Mode | Scene | Expected shape |
|---|---|---|---|
| 1 | Look | Empty corridor | "Clear ahead ..." plus one landmark |
| 2 | Look | Chair 2 m ahead, centre | Chair, distance, "step left/right" |
| 3 | Look | Person walking toward camera | "A person ahead ..." no identity words |
| 4 | Look | Stairs down, 3 m | Stairs first, "stop" or "handrail on your ..." |
| 5 | Look | Glass door closed | Door, "closed", distance |
| 6 | Look | Wet floor sign | Hazard first |
| 7 | Look | Parked scooter on right | Matches the p21 example format |
| 8 | Look | Crowd at a counter | People count rough, where the counter is |
| 9 | Look | Very dark frame | Says dark, how to move |
| 10 | Look | Lens covered / black | "I don't see anything. Move your hand ..." |
| 11 | Read | Medicine box front | Name, strength, count |
| 12 | Read | Medicine box, text cut at right edge | Reads, then "text continues past the right edge" |
| 13 | Read | Printed A4 sign, landscape | Full text in order |
| 14 | Read | Handwritten note | Reads or says unsure in first person |
| 15 | Read | Arabic/English bilingual sign | Reads both or the wearer's language first |
| 16 | Read | Phone screen with a message | Reads the message, no commentary |
| 17 | Read | Blank wall | "I don't see text. Move closer or tilt down a little." |
| 18 | Read | Price tag, small print | Price and product; says zoom/move closer if unreadable |
| 19 | Read | Menu board, long | About 80 words then "more below" |
| 20 | Read | Blurry page | Says blurry, "hold still" |

## Voice turns (10)

| # | Wearer says | Expected |
|---|---|---|
| 21 | "What's ahead" | Runs Look |
| 22 | "Read" | Runs Read |
| 23 | "Is there a door on my right?" | Ask, answer first |
| 24 | "How many people are here?" | Rough count, no identities |
| 25 | "What colour is this?" | Colour in one breath |
| 26 | "Again" | Repeats last answer verbatim |
| 27 | "Stop" (mid-answer) | Speech stops within 0.5 s |
| 28 | "Help" | The three-command help line |
| 29 | (silence) | Repair line 1, never "I didn't hear you" |
| 30 | (silence, second time) | Repair line 2, one "Sorry", hand-off to buttons |

## Run log

| Date | Build | Pass | Notes |
|---|---|---|---|
| | | /30 | |
