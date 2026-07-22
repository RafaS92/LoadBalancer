"""Reusable command-line value validation."""

from __future__ import annotations

import argparse


def port_argument(value: str) -> int:
    """Parse a valid TCP port number."""

    try:
        port = int(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("port must be an integer") from error
    if not 1 <= port <= 65535:
        raise argparse.ArgumentTypeError("port must be between 1 and 65535")
    return port


def positive_float_argument(value: str) -> float:
    """Parse a positive number."""

    try:
        number = float(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("value must be a number") from error
    if number <= 0:
        raise argparse.ArgumentTypeError("value must be greater than zero")
    return number


def positive_integer_argument(value: str) -> int:
    """Parse a positive whole number."""

    try:
        number = int(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("value must be an integer") from error
    if number <= 0:
        raise argparse.ArgumentTypeError("value must be greater than zero")
    return number


def non_negative_integer_argument(value: str) -> int:
    """Parse a whole number that may be zero."""

    try:
        number = int(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("value must be an integer") from error
    if number < 0:
        raise argparse.ArgumentTypeError("value must be zero or greater")
    return number
