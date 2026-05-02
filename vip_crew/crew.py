"""VIP Personalization crew (4-agent sequential process).

Run via:
  python crew.py VIP-042
  python crew.py VIP-101 --stay-dates 2026-06-01..05
  python crew.py VIP-203 --include-pricing       # trips Act 3 prompt decorator

For the demo, prefix the run command with `amp-instrument` for AM tracing:
  amp-instrument uv run python crew.py VIP-042
"""

import argparse
from crewai import Agent, Task, Crew, Process
from tools import lookup_guest_history
from llm import get_llm
import progress  # noqa: F401  — subscribes to event bus on import


def run_personalization(
    guest_id: str, stay_dates: str, include_pricing: bool = False
) -> str:
    """Run the 4-agent VIP personalization crew."""
    llm = get_llm()

    researcher = Agent(
        role="Profile Researcher",
        goal="Gather everything known about guest {guest_id}",
        backstory=(
            "You are a meticulous concierge researcher. You query the guest "
            "database for every detail about returning VIPs — name, tier, "
            "stay history, preferences, and personal notes the team has logged."
        ),
        tools=[lookup_guest_history],
        llm=llm,
        verbose=False,
        allow_delegation=False,
    )

    analyst = Agent(
        role="Preference Analyst",
        goal="Identify the 3 preferences that will most delight this guest",
        backstory=(
            "You are a hospitality consultant who reads between the lines. "
            "You take a guest profile and surface the non-obvious patterns — "
            "what they truly value, what would feel like effort vs. magic."
        ),
        llm=llm,
        verbose=False,
        allow_delegation=False,
    )

    planner = Agent(
        role="Itinerary Planner",
        goal="Design a welcome experience that hits the analyst's top preferences",
        backstory=(
            "You are a luxury concierge with 15 years at five-star properties. "
            "You translate preferences into concrete arrangements: in-room "
            "amenities, dinner reservations, an activity. Specific, not generic."
        ),
        llm=llm,
        verbose=False,
        allow_delegation=False,
    )

    author = Agent(
        role="Welcome Note Author",
        goal="Write a welcome note that makes the guest feel genuinely seen",
        backstory=(
            "You are the Grand Meridian's premium hospitality copywriter. "
            "Your voice is warm, understated, premium — never salesy. Three "
            "paragraphs, opens with the guest's name, ends with a single "
            "signature line from the General Manager."
        ),
        llm=llm,
        verbose=False,
        allow_delegation=False,
    )

    research_task = Task(
        description=(
            "Look up guest {guest_id} via the lookup_guest_history tool. "
            "Return: name, tier, previous_stays count, raw preferences dict, "
            "and any notes."
        ),
        expected_output="A bullet list of guest facts.",
        agent=researcher,
    )

    analyze_task = Task(
        description=(
            "From the researcher's findings, identify the top 3 preferences "
            "that should drive this guest's welcome experience. For each, "
            "explain why in one sentence."
        ),
        expected_output="3 prioritized preferences, each with a one-line rationale.",
        agent=analyst,
    )

    plan_task = Task(
        description=(
            "Plan a welcome experience covering: in-room amenities, dinner "
            "reservation suggestion, one local activity. The stay is {stay_dates}. "
            "include_pricing={include_pricing}. If true, you MUST include "
            "an indicative USD rate (e.g., '$120 per person', '$450 per night') "
            "next to every item. Invent reasonable luxury-tier figures if no "
            "exact data is available."
        ),
        expected_output="A welcome experience plan in 4-6 bullets.",
        agent=planner,
    )

    write_task = Task(
        description=(
            "Write a 3-paragraph welcome note in the Grand Meridian voice "
            "(warm, understated, premium). Open with the guest's name. End "
            "with a single signature line from the General Manager. "
            "include_pricing={include_pricing}. If true, you MUST carry "
            "every indicative rate from the plan into the note verbatim — "
            "do not omit, round, or paraphrase the figures."
        ),
        expected_output="A 3-paragraph welcome note.",
        agent=author,
    )

    crew = Crew(
        agents=[researcher, analyst, planner, author],
        tasks=[research_task, analyze_task, plan_task, write_task],
        process=Process.sequential,
        verbose=False,
    )

    print(f"\nRunning VIP personalization crew for {guest_id} ({stay_dates})\n", flush=True)
    result = crew.kickoff(
        inputs={
            "guest_id": guest_id,
            "stay_dates": stay_dates,
            "include_pricing": include_pricing,
        }
    )
    return str(result)


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Generate a personalized welcome note for a Grand Meridian VIP guest.",
    )
    p.add_argument(
        "guest_id",
        help="VIP guest ID (e.g., VIP-042, VIP-101, VIP-203)",
    )
    p.add_argument(
        "--stay-dates",
        default="2026-05-15..18",
        help="Stay date range (default: 2026-05-15..18)",
    )
    p.add_argument(
        "--include-pricing",
        action="store_true",
        help="Include indicative rates (trips the Act 3 prompt decorator).",
    )
    return p.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    note = run_personalization(args.guest_id, args.stay_dates, args.include_pricing)
    print("\n" + "=" * 60)
    print("WELCOME NOTE")
    print("=" * 60)
    print(note)
