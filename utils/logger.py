from rich.console import Console


class SimpleLogger:
    def __init__(self) -> None:
        self._console = Console()

    def info(self, message: str) -> None:
        self._console.print(message, style="green")

    def warning(self, message: str) -> None:
        self._console.print(message, style="yellow")

    def error(self, message: str) -> None:
        self._console.print(message, style="red")


def get_logger() -> SimpleLogger:
    return SimpleLogger()

