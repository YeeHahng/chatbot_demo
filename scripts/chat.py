#!/usr/bin/env python3
"""
Interactive chatbox for testing the SkyView property bot pipeline.

Usage:
    python scripts/chat.py
    python scripts/chat.py --building tower_a --unit 3-05
    python scripts/chat.py --phone +60123456789 --building tower_b --unit 5-01

No server needed — runs the full pipeline directly.
Type 'quit' or Ctrl+C to exit.
Type '/reset' to clear session.
Type '/session' to view current session state.
Type '/model' to see current model.
"""
import sys
import asyncio
import argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.config import settings
from app.models import ConversationState
from app.search import init_search
from app.session import get_session, update_session, add_to_history
from app.responder import generate_response

# ANSI colors
CYAN   = "\033[96m"
GREEN  = "\033[92m"
YELLOW = "\033[93m"
GREY   = "\033[90m"
RED    = "\033[91m"
BOLD   = "\033[1m"
RESET  = "\033[0m"


def print_banner(phone: str) -> None:
    print(f"\n{BOLD}{'=' * 60}{RESET}")
    print(f"{BOLD}  SkyView Property Bot — Interactive Chat{RESET}")
    print(f"{GREY}  Model  : {settings.model}{RESET}")
    print(f"{GREY}  Phone  : {phone}{RESET}")
    print(f"{GREY}  Commands: /reset  /session  /model  quit{RESET}")
    print(f"{BOLD}{'=' * 60}{RESET}\n")


def print_stats(intent: str, language: str, latency_ms: int, input_tokens: int, output_tokens: int) -> None:
    total = input_tokens + output_tokens
    print(
        f"{GREY}  ▸ intent={intent}  lang={language}  "
        f"{latency_ms}ms  "
        f"in={input_tokens} out={output_tokens} total={total} tokens{RESET}"
    )


def print_session(session: ConversationState) -> None:
    print(f"{YELLOW}  Session:{RESET}")
    print(f"{YELLOW}    state    : {session.state}{RESET}")
    print(f"{YELLOW}    building : {session.building or '—'}{RESET}")
    print(f"{YELLOW}    unit     : {session.unit or '—'}{RESET}")
    print(f"{YELLOW}    language : {session.language}{RESET}")
    print(f"{YELLOW}    history  : {len(session.history)} messages{RESET}")


async def chat_loop(phone: str, building: str | None, unit: str | None) -> None:
    # Pre-seed session if building/unit provided
    if building or unit:
        state = "BOOKED" if (building and unit) else "PRE_BOOKING"
        update_session(phone, building=building, unit=unit, state=state)
        print(f"{YELLOW}  Session pre-seeded: building={building or '—'} unit={unit or '—'} state={state}{RESET}\n")

    print_banner(phone)

    while True:
        try:
            user_input = input(f"{CYAN}You:{RESET} ").strip()
        except (EOFError, KeyboardInterrupt):
            print(f"\n{GREY}Goodbye!{RESET}")
            break

        if not user_input:
            continue

        if user_input.lower() in ("quit", "exit", "q"):
            print(f"{GREY}Goodbye!{RESET}")
            break

        if user_input == "/reset":
            # Reset session for this phone
            from app.session import _sessions
            if phone in _sessions:
                del _sessions[phone]
            if building or unit:
                state = "BOOKED" if (building and unit) else "PRE_BOOKING"
                update_session(phone, building=building, unit=unit, state=state)
            print(f"{YELLOW}  Session reset.{RESET}\n")
            continue

        if user_input == "/session":
            print_session(get_session(phone))
            print()
            continue

        if user_input == "/model":
            print(f"{YELLOW}  Model: {settings.model}{RESET}\n")
            continue

        # Run the pipeline
        session = get_session(phone)
        try:
            llm_response, input_tokens, output_tokens, latency_ms = await generate_response(
                phone=phone,
                message=user_input,
                session=session,
            )
        except Exception as e:
            print(f"{RED}  Error: {e}{RESET}\n")
            continue

        # Update session
        update_session(
            phone,
            building=llm_response.building_extracted,
            unit=llm_response.unit_extracted,
            language=llm_response.language,
            state="BOOKED" if (session.building or llm_response.building_extracted) and (session.unit or llm_response.unit_extracted) else session.state,
        )
        add_to_history(phone, "user", user_input)
        add_to_history(phone, "assistant", llm_response.response)

        # Print response
        print(f"\n{GREEN}{BOLD}Bot:{RESET} {llm_response.response}")
        print()
        print_stats(
            intent=llm_response.intent,
            language=llm_response.language,
            latency_ms=latency_ms,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )
        print()


def main() -> None:
    parser = argparse.ArgumentParser(description="Interactive SkyView property bot chat")
    parser.add_argument("--phone",    default="+60100000999", help="Phone number for session (default: +60100000999)")
    parser.add_argument("--building", default=None,           help="Pre-set building (e.g. tower_a)")
    parser.add_argument("--unit",     default=None,           help="Pre-set unit (e.g. 3-05)")
    args = parser.parse_args()

    print(f"{GREY}Loading embedding model (first run may take ~30s)...{RESET}")
    init_search()

    asyncio.run(chat_loop(phone=args.phone, building=args.building, unit=args.unit))


if __name__ == "__main__":
    main()
