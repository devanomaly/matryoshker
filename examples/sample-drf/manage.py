#!/usr/bin/env python
"""Django management entrypoint for the sample library project.

This file exists so the fixture looks like a real Django project. The
project is never executed: it is a static fixture for the extractor.
"""
import os
import sys


def main():
    """Run administrative tasks."""
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "library.settings")
    from django.core.management import execute_from_command_line

    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
