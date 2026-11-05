# Vantage: the dialog

Job story: *When I stop at the pharmacy counter with my cane in one hand, I want to know what is in front of me and what the box says, so I can decide without asking a stranger.*

Format rules from the UX session: answer first, one breath, numbers as words, every line ends with an instruction or a question, and no failure ends in silence.

## Happy path (6 turns)

| # | Wearer | Vantage |
|---|---|---|
| 1 | *taps Look* | ♪ working · "Counter ahead, two steps. Person behind it, on your left. Clear to walk." ♪ done |
| 2 | *taps Ask* "What's on the shelf to my right?" | ♪ listening … ♪ working · "Cold and flu boxes, three rows. Blue one at eye level is Panadol." ♪ done |
| 3 | *taps Read* (holding a box) | ♪ working · "Panadol Cold and Flu. Twenty-four tablets. Adults, two tablets every six hours. More below." ♪ done |
| 4 | "Again" | "Panadol Cold and Flu. Twenty-four tablets. Adults, two tablets every six hours. More below." |
| 5 | *taps Ask* "Is there a date on it?" | ♪ working · "I'm not sure. The bottom edge is cut off; tilt the box up a little and ask again." |
| 6 | *taps Read* | ♪ working · "Expiry: zero eight, twenty twenty-seven." ♪ done |

## Repair path A: didn't hear

| # | Wearer | Vantage |
|---|---|---|
| 1 | *taps Ask*, says nothing (bus passes) | ♪ listening … ♪ error · "Say look, read, or a question. Or use the buttons." |
| 2 | *taps Ask*, mumbles | ♪ error · "Sorry. Use the Look or Read button on the phone." |
| 3 | *taps Look* | ♪ working · "Bus stop ahead, three metres. Bench on your right. Clear path." ♪ done |

Never "I didn't hear you". One apology at most. After the second miss the hand-off is to the silent path, which always works.

## Repair path B: no connection

| # | Wearer | Vantage |
|---|---|---|
| 1 | *taps Look* (in the metro, no signal) | ♪ working · (1.5 s) "Looking." · ♪ error · "No connection right now. Try again in a moment." |
| 2 | *taps Look* (still none) | ♪ error · "Sorry. No connection right now. Try again in a moment." |
| 3 | *taps Look* (third miss) | ♪ error · "Let's use the phone buttons for now." *(screen keeps showing the line; Vantage stops talking until a turn succeeds)* |
| 4 | *taps Look* (signal back) | ♪ working · "Escalator down, four metres ahead. Handrail on your right." ♪ done |

## Commands (verb first, three words or fewer)

- **look** / **what's ahead** → Look
- **read** → Read
- anything else → Ask with that question
- **again** → repeat · **stop** → stop speaking · **help** → "Say look, read, or ask a question. Again repeats. Stop stops."
