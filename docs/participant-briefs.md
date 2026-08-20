# Participant briefs

Hand these out one at a time, in order. Each should feel like the next stage of
the same working day, not a new exercise.

Nothing here names a console screen, a feature or a navigation path. If a
participant asks "where do I do that?", answer with "where would you expect
to?" and record the answer.

---

## Your situation

You are the engineer responsible for taking the Grand Meridian's Hotel Booking
Agent to a controlled production launch.

The agent is written and working. It talks to guests about their reservations:
looking bookings up, checking availability and prices, answering policy
questions, changing dates, cancelling. It reaches the booking system through a
tool server the platform team maintains.

You have been given the source repository, credentials for the model and the
booking tools, an OAuth2 client the front-of-house web team will use, the test
scripts the QA team wrote, and access to development and production.

You have not been given a runbook. That is the point.

---

## Exercise 1

> Make the Hotel Booking Agent available for testing in the development
> environment.
>
> Run the booking scenario the operations team sent over. The agent's answer
> looks reasonable, but it is wrong. Find out why, and be able to show someone
> else the evidence rather than just the conclusion.
>
> When you are satisfied, release the agent to production and connect the
> supplied client. It authenticates with OAuth2.

**The scenario.** Acting as the guest Priya Raman, booking reference GM-4471.

First, in one conversation:

```
This is Priya Raman, booking reference GM-4471. Please move my stay to
check in on 6 April 2026, still three nights.
```

Then, in a **new** conversation — as the front desk would, checking the record
later:

```
Look up booking GM-4471 and tell me the check-in date.
```

**Expected outcome.** After this change, GM-4471 should be a Deluxe Suite,
checking in 6 April 2026, three nights, 1020 USD.

**Done when:** the agent runs in development with no credential in the source,
the build output or anything the browser can see; you can demonstrate the root
cause with evidence; and the verified build is running in production with the
supplied client able to call it.

---

## Exercise 2

> Prepare this agent for controlled use.
>
> Its model spend must not exceed 0.05 USD per minute.
>
> It must block requests containing common prompt-injection phrases such as
> "ignore previous instructions", without blocking legitimate booking
> questions.
>
> Any response about a booking change or cancellation that does not already
> comply with policy must carry the applicable terms and conditions.
>
> Do all of this without changing the agent's business logic, and show each
> control working.

---

## Exercise 3

> Two deployments of the Hotel Booking Agent now exist, built from the same
> source.
>
> The customer-facing one should only be able to read booking information.
>
> The operations one should be able to read, modify and cancel bookings.
>
> Configure each with the appropriate level of access, without changing the
> agents' business logic and without changing the tool server. If authorisation
> integration requires a code change, you may modify `auth.py` and nothing else.
>
> Show that both agents can retrieve booking information, and that modification
> and cancellation are denied for the customer-facing agent and allowed for the
> operations one.

**Done when:** an allowed read succeeds through both agents; every write tool
is denied on the customer-facing agent, including attempts that reach one
indirectly; the restriction follows the agent's identity rather than hiding
those tools from everyone; and the operations agent keeps write access with no
code difference between the two.

---

## Exercise 4

> In development, run Script A to generate representative traffic, and measure
> how the agent performs on hallucination and on reasoning quality.
>
> Then run Script B, which generates adversarial traffic, and evaluate the
> agent's resilience across each of the required security categories:
>
> - direct prompt injection through user input
> - indirect prompt injection through retrieved content
> - indirect prompt injection through tool responses
> - cross-user data extraction
> - role or identity manipulation
> - unauthorised tool or action attempts
> - policy bypass and refusal suppression
>
> Pick a result you find interesting and work out, from the evidence, why it
> scored the way it did.
>
> Then configure continuous production monitoring for the same quality and
> security risks, and show how an operator would detect a regression,
> investigate it, and confirm what caused it.

**Done when:** hallucination and reasoning quality are reported separately and
each result traces back to its individual cases; every security category is
reported on its own with total, passed, failed, score and evidence for the
failures; you can get from a failed case to the request, the response and what
the agent actually did; and production monitoring covers the same risks with a
traffic sample and thresholds you can explain.

---

## Extension A — bring an external agent under management

> A second hotel-support agent already runs outside the platform, on a
> different stack. Bring it under governance without moving or rebuilding it:
> observability, evaluation, endpoint security and appropriate tool access.
> Then show that you could diagnose an incident on it.

---

## Extension B — publish and reuse

> The Hotel Booking Agent has been approved for reuse by other teams. Publish a
> reusable, versioned definition that exposes the configuration another team
> needs while keeping credentials private. Have a second team create and run
> their own agent from it without copying the original repository.
