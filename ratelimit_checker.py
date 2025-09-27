#!/usr/bin/env python3
"""
Token Usage Parser for Claude Code Sessions

This script finds the latest session file and extracts token usage and rate limit information
from the most recent event_msg record with token_count payload.
"""

import argparse
import json
import os
import glob
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Dict, Any, Tuple


def get_session_base_path(custom_path: Optional[str] = None) -> Path:
    """Get the base path for session storage."""
    if custom_path:
        return Path(custom_path).expanduser()
    return Path.home() / ".codex" / "sessions"


def find_latest_token_count_record(base_path: Optional[Path] = None) -> Optional[Tuple[Path, Dict[str, Any]]]:
    """
    Find the most recent token_count record by searching backwards from today.

    Args:
        base_path: Custom base path for session files

    Returns:
        Tuple of (file_path, record) for the latest token_count event, or None if not found
    """
    if base_path is None:
        base_path = get_session_base_path()
    current_date = datetime.now()

    latest_record = None
    latest_timestamp = None
    latest_file = None

    # Search backwards for up to 30 days
    for days_back in range(30):
        search_date = current_date - timedelta(days=days_back)
        date_path = base_path / str(search_date.year) / f"{search_date.month:02d}" / f"{search_date.day:02d}"

        if date_path.exists():
            # Find all rollout-*.jsonl files in this directory
            pattern = str(date_path / "rollout-*.jsonl")
            files = glob.glob(pattern)

            # Check each file for token_count events
            for file_path in files:
                record = parse_session_file(Path(file_path))
                if record:
                    timestamp_str = record.get('timestamp')
                    if timestamp_str:
                        timestamp = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))

                        if latest_timestamp is None or timestamp > latest_timestamp:
                            latest_timestamp = timestamp
                            latest_record = record
                            latest_file = Path(file_path)

            # If we found records on this day, return the latest one
            if latest_record is not None:
                return latest_file, latest_record

    return None


def parse_session_file(file_path: Path) -> Optional[Dict[str, Any]]:
    """
    Parse the session file and find the latest token_count event.

    Args:
        file_path: Path to the session file

    Returns:
        The latest token_count event data, or None if not found
    """
    latest_record = None
    latest_timestamp = None

    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue

                try:
                    record = json.loads(line)

                    # Check if this is a token_count event
                    if (record.get('type') == 'event_msg' and
                        record.get('payload', {}).get('type') == 'token_count'):

                        timestamp_str = record.get('timestamp')
                        if timestamp_str:
                            timestamp = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))

                            if latest_timestamp is None or timestamp > latest_timestamp:
                                latest_timestamp = timestamp
                                latest_record = record

                except json.JSONDecodeError:
                    continue  # Skip malformed lines

    except Exception as e:
        print(f"Error reading session file: {e}")
        return None

    return latest_record


def format_token_usage(usage_data: Dict[str, int]) -> str:
    """Format token usage data into a readable string."""
    input_tokens = usage_data.get('input_tokens', 0)
    cached_tokens = usage_data.get('cached_input_tokens', 0)
    output_tokens = usage_data.get('output_tokens', 0)
    reasoning_tokens = usage_data.get('reasoning_output_tokens', 0)
    total_tokens = usage_data.get('total_tokens', 0)

    return f"input {input_tokens}, cached {cached_tokens}, output {output_tokens}, reasoning {reasoning_tokens}, subtotal {total_tokens}"


def calculate_reset_time(record_timestamp: datetime, reset_in_seconds: int) -> Tuple[datetime, bool]:
    """
    Calculate the actual reset time and check if it's outdated.

    Args:
        record_timestamp: Timestamp of the record
        reset_in_seconds: Seconds until reset from the record

    Returns:
        Tuple of (reset_time, is_outdated)
    """
    reset_time = record_timestamp + timedelta(seconds=reset_in_seconds)
    current_time = datetime.now(record_timestamp.tzinfo)
    is_outdated = reset_time < current_time

    return reset_time, is_outdated


def main():
    """Main function to parse and display token usage information."""
    parser = argparse.ArgumentParser(description='Parse Claude Code session token usage and rate limits')
    parser.add_argument('--input-folder', '-i', type=str,
                       help='Custom input folder path (default: ~/.codex/sessions)')

    args = parser.parse_args()

    # Set up base path
    if args.input_folder:
        base_path = Path(args.input_folder).expanduser()
        print(f"Using custom input folder: {base_path}")
    else:
        base_path = get_session_base_path()
        print(f"Using default input folder: {base_path}")

    print("Searching for latest token_count event...")

    # Find the latest token_count record
    result = find_latest_token_count_record(base_path)
    if not result:
        print("No token_count events found in session files.")
        return

    latest_file, record = result
    print(f"Found latest token_count event in: {latest_file}")

    # Extract data from the record
    payload = record['payload']
    info = payload['info']
    rate_limits = payload.get('rate_limits', {})

    record_timestamp = datetime.fromisoformat(record['timestamp'].replace('Z', '+00:00'))

    # Display token usage
    total_usage = info['total_token_usage']
    last_usage = info['last_token_usage']

    print(f"total: {format_token_usage(total_usage)}")
    print(f"last:  {format_token_usage(last_usage)}")

    # Display rate limits
    primary = rate_limits.get('primary', {})
    if primary:
        primary_percent = primary.get('used_percent', 0)
        primary_reset_seconds = primary.get('resets_in_seconds', 0)
        primary_reset_time, primary_outdated = calculate_reset_time(record_timestamp, primary_reset_seconds)

        reset_time_str = primary_reset_time.astimezone().strftime('%Y-%m-%d %H:%M:%S')
        outdated_str = " [OUTDATED]" if primary_outdated else ""
        print(f"5h limit: used {primary_percent}%, reset: {reset_time_str}{outdated_str}")

    secondary = rate_limits.get('secondary', {})
    if secondary:
        secondary_percent = secondary.get('used_percent', 0)
        secondary_reset_seconds = secondary.get('resets_in_seconds', 0)
        secondary_reset_time, secondary_outdated = calculate_reset_time(record_timestamp, secondary_reset_seconds)

        reset_time_str = secondary_reset_time.astimezone().strftime('%Y-%m-%d %H:%M:%S')
        outdated_str = " [OUTDATED]" if secondary_outdated else ""
        print(f"weekly limit: used {secondary_percent}%, reset: {reset_time_str}{outdated_str}")


if __name__ == "__main__":
    main()