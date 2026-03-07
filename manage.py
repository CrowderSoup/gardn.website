#!/usr/bin/env python
import os
import sys


def main() -> None:
    command = sys.argv[1] if len(sys.argv) > 1 else ""
    has_explicit_settings = any(arg.startswith("--settings") for arg in sys.argv[1:])

    if "DJANGO_SETTINGS_MODULE" not in os.environ and not has_explicit_settings:
        if command == "test":
            os.environ["DJANGO_SETTINGS_MODULE"] = "gardn.test_settings"
        else:
            os.environ["DJANGO_SETTINGS_MODULE"] = "gardn.settings"

    from django.core.management import execute_from_command_line

    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
