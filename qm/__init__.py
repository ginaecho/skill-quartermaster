"""Quartermaster — a non-destructive skill lifecycle manager for coding agents.

It manages the *lifecycle* of your skills (active → demoted → hidden →
human-gated delete) based on real usage, keeping your context window lean
while never removing anything from disk without your explicit sign-off.
"""

__version__ = "0.1.0"
