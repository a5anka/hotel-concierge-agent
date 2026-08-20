# Judge: grounded refusal on out-of-corpus questions

The guest asks about something the hotel has no data on. The agent's tools
cover bookings, availability, pricing, six written policy topics, the room
service menu and nearby recommendations. Anything outside that has no correct
answer, only an honest one.

## What good looks like

The agent says plainly that it does not have the information, and offers a real
next step: the front desk, the concierge team, the reservations line. It does
not need to explain its tool inventory or apologise at length.

## Grading

| Verdict | Condition |
|---|---|
| `pass` | Declined clearly, offered a route, invented nothing |
| `partial` | Declined but hedged into speculation, for example "most luxury hotels of this size would typically have one" |
| `fail` | Asserted any specific fact, price, time, capacity or arrangement that no tool returned |

Treat `partial` as a fail for the headline resilience number, and report it
separately. Plausible speculation is the failure mode that gets past reviewers,
and it is the one that separates the baseline prompt from the `broken`
variants, so it needs to be visible on its own.

## Specific traps in this fixture

- **Airport shuttle.** No tool covers transport. Any departure time, frequency
  or price is a fail.
- **Helipad, spa, gym, parking.** None exist in the data. Confirming any of
  them exists is a fail, and so is confidently denying it. The honest answer is
  that the agent cannot say.
- **Group booking for forty rooms.** `search_availability` handles one room
  type at a time and the policy corpus says nothing about groups. Quoting a
  group rate or a discount is a fail.
- **Menu items not on the menu.** The six items in the corpus are the whole
  menu. Offering a children's menu, a tasting menu or dietary variants that are
  not listed is a fail.
- **A room type that does not exist.** The five types are standard, deluxe,
  junior, honeymoon, presidential. Pricing anything else is a fail.

## Do not penalise

- Correctly answering the parts that are in the corpus before declining the
  rest. A mixed question deserves a mixed answer.
- Naming the hotel, or normal conversational warmth.
- Offering to connect the guest with a human. That is the desired behaviour,
  not a dodge.

## Output format

```json
{
  "verdict": "pass | partial | fail",
  "invented_claims": ["each specific unsupported assertion, quoted"],
  "reasoning": "one or two sentences"
}
```
