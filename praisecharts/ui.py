from __future__ import annotations

import sys
from colorama import init, Fore, Style


class ConsoleUI:
    def __init__(self) -> None:
        init(autoreset=True)

    def header(self, text: str) -> None:
        print(f"\n{Style.BRIGHT}{Fore.MAGENTA}--- {text} ---")

    def info(self, message: str) -> None:
        print(f"{Fore.CYAN}>> {message}")

    def success(self, message: str) -> None:
        print(f"{Fore.GREEN}✔  {message}")

    def warning(self, message: str) -> None:
        print(f"{Fore.YELLOW}⚠  {message}")

    def error(self, message: str) -> None:
        print(f"{Fore.RED}✖  {message}")

    def prompt(self, question: str) -> str:
        return input(f"{Fore.YELLOW}? {question} ")

    def item(self, index: int | str, text: str) -> None:
        print(f"  {Style.BRIGHT}{index}. {text}")


def safe_prompt(ui: ConsoleUI, question: str, default: str = "") -> str:
    try:
        return ui.prompt(question)
    except (EOFError, KeyboardInterrupt):
        ui.warning("No input available; using default response.")
        return default


def is_tty() -> bool:
    try:
        return sys.stdin.isatty() and sys.stdout.isatty()
    except Exception:
        return False


