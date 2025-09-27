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
import curses
import time
import signal
import sys
import unicodedata
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Dict, Any, Tuple



LABEL_AREA_WIDTH = 12
BAR_WIDTH = 46


def pad_label_to_width(label: str, target_width: int = LABEL_AREA_WIDTH) -> str:
    """Trim and pad the label so its rendered width matches target_width."""
    current_width = 0
    truncated_chars = []

    for char in label:
        char_width = get_display_width(char)

        # Always include zero-width characters (e.g., combining marks)
        if char_width == 0:
            truncated_chars.append(char)
            continue

        if current_width + char_width > target_width:
            break

        truncated_chars.append(char)
        current_width += char_width

    padded_label = "".join(truncated_chars)

    if current_width < target_width:
        padded_label += " " * (target_width - current_width)

    return padded_label


def get_display_width(text: str) -> int:
    """Calculate the actual display width of text including Unicode characters."""
    width = 0
    for char in text:
        # Handle common block characters
        if char in '█░':
            # These block characters typically display as 1 column
            width += 1
        elif unicodedata.category(char).startswith('M'):
            # Combining marks (don't add width)
            width += 0
        else:
            # Regular characters
            width += 1
    return width

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


def get_rate_limit_data(base_path: Optional[Path] = None) -> Optional[Dict[str, Any]]:
    """Get rate limit data and return structured information for display."""
    result = find_latest_token_count_record(base_path)
    if not result:
        return None

    latest_file, record = result
    payload = record['payload']
    info = payload['info']
    rate_limits = payload.get('rate_limits', {})
    record_timestamp = datetime.fromisoformat(record['timestamp'].replace('Z', '+00:00'))
    current_time_local = datetime.now().astimezone()

    data = {
        'file_path': latest_file,
        'record_timestamp': record_timestamp,
        'current_time': current_time_local,
        'total_usage': info['total_token_usage'],
        'last_usage': info['last_token_usage']
    }

    # Process primary (5h) rate limits
    primary = rate_limits.get('primary', {})
    if primary:
        primary_reset_time, primary_outdated = calculate_reset_time(record_timestamp, primary.get('resets_in_seconds', 0))
        window_seconds = primary.get('window_minutes', 299) * 60
        resets_in_seconds = primary.get('resets_in_seconds', 0)

        if primary_outdated:
            # If outdated, assume 100% time elapsed
            time_percent = 100.0
        else:
            # elapsed_seconds = total_window - remaining_seconds
            elapsed_seconds = window_seconds - resets_in_seconds
            time_percent = (elapsed_seconds / window_seconds) * 100 if window_seconds > 0 else 0

        data['primary'] = {
            'used_percent': primary.get('used_percent', 0),
            'time_percent': max(0, min(100, time_percent)),
            'reset_time': primary_reset_time,
            'outdated': primary_outdated,
            'window_minutes': primary.get('window_minutes', 299)
        }

    # Process secondary (weekly) rate limits
    secondary = rate_limits.get('secondary', {})
    if secondary:
        secondary_reset_time, secondary_outdated = calculate_reset_time(record_timestamp, secondary.get('resets_in_seconds', 0))
        window_seconds = secondary.get('window_minutes', 10079) * 60
        resets_in_seconds = secondary.get('resets_in_seconds', 0)

        if secondary_outdated:
            # If outdated, assume 100% time elapsed
            time_percent = 100.0
        else:
            # elapsed_seconds = total_window - remaining_seconds
            elapsed_seconds = window_seconds - resets_in_seconds
            time_percent = (elapsed_seconds / window_seconds) * 100 if window_seconds > 0 else 0

        data['secondary'] = {
            'used_percent': secondary.get('used_percent', 0),
            'time_percent': max(0, min(100, time_percent)),
            'reset_time': secondary_reset_time,
            'outdated': secondary_outdated,
            'window_minutes': secondary.get('window_minutes', 10079)
        }

    return data


def draw_progress_bar(stdscr, y: int, x: int, bar_width: int, percent: float, label: str, details: str = "", total_width: int = 70) -> None:
    """Draw a progress bar at the specified position."""
    filled_width = int((percent / 100.0) * bar_width)
    bar = "█" * filled_width + "░" * (bar_width - filled_width)

    try:
        left_edge = x
        right_edge = x + total_width - 1
        content_start = left_edge + 1
        content_width = total_width - 2

        # Prepare formatted pieces
        label_text = pad_label_to_width(label)
        percent_text = f"{percent:5.1f}%"
        label_x = content_start + 1  # leave one-space margin after border
        bar_x = label_x + LABEL_AREA_WIDTH + 1  # space between label area and bar
        percent_x = right_edge - len(percent_text) - 3  # leave three spaces before border

        # Draw borders
        stdscr.addch(y, left_edge, "│")
        stdscr.addch(y, right_edge, "│")

        # Clear the interior content area
        stdscr.addstr(y, content_start, " " * content_width)

        # Draw label
        stdscr.addstr(y, label_x, label_text)

        # Draw bar at fixed column
        stdscr.addstr(y, bar_x, "[")
        stdscr.addstr(y, bar_x + 1, bar)
        stdscr.addstr(y, bar_x + 1 + bar_width, "]")

        # Ensure at least one space between bar and percentage
        percent_x = max(percent_x, bar_x + 1 + bar_width + 2)

        # Draw percentage value
        stdscr.addstr(y, percent_x, percent_text)
    except curses.error:
        pass  # Skip if can't draw

    # Draw details line if provided
    if details:
        detail_template = f"    {details}"
        detail_length = len(detail_template)

        if detail_length <= content_width:
            detail_padding = content_width - detail_length
            detail_line = f"│{detail_template}{' ' * detail_padding}│"
        else:
            truncated_detail = detail_template[:content_width]
            detail_line = f"│{truncated_detail}│"

        try:
            stdscr.addstr(y + 1, x, detail_line)
        except curses.error:
            pass  # Skip if can't draw



def run_tui(base_path: Optional[Path], refresh_interval: int) -> None:
    """Run the TUI interface."""
    def tui_main(stdscr):
        # Configure curses
        curses.curs_set(0)  # Hide cursor
        stdscr.nodelay(True)  # Non-blocking input
        stdscr.timeout(100)  # 100ms timeout for getch()

        # Get terminal dimensions
        max_y, max_x = stdscr.getmaxyx()

        last_refresh = 0

        while True:
            current_time = time.time()

            # Check for 'q' key to quit
            key = stdscr.getch()
            if key == ord('q') or key == ord('Q'):
                break

            # Refresh data based on interval
            if current_time - last_refresh >= refresh_interval:
                stdscr.clear()

                # Get current data
                data = get_rate_limit_data(base_path)

                if not data:
                    stdscr.addstr(2, 2, "No token_count events found in session files.")
                    stdscr.addstr(3, 2, "Press 'q' to quit.")
                else:
                    # Header
                    header = "CODEX RATELIMIT - LIVE USAGE MONITOR"
                    total_width = 74  # Extended by 2 characters
                    content_width = total_width - 2
                    header_padding = (content_width - len(header)) // 2

                    # Check if we have enough space to draw
                    if max_y < 20 or max_x < 76:
                        stdscr.addstr(1, 2, "Terminal too small! Need at least 76x20")
                        stdscr.refresh()
                        continue

                    try:
                        stdscr.addstr(1, 2, "┌" + "─" * content_width + "┐")
                        stdscr.addstr(2, 2, f"│{' ' * header_padding}{header}{' ' * (content_width - header_padding - len(header))}│")
                        stdscr.addstr(3, 2, "├" + "─" * content_width + "┤")
                    except curses.error:
                        stdscr.addstr(1, 2, "Display error - terminal too small")
                        stdscr.refresh()
                        continue

                    y_pos = 4

                    # 5-hour session bars
                    if 'primary' in data:
                        primary = data['primary']

                        # Session time bar
                        reset_time_str = primary['reset_time'].astimezone().strftime('%H:%M:%S')
                        outdated_str = " [OUTDATED]" if primary['outdated'] else ""
                        time_details = f"Reset: {reset_time_str}{outdated_str}"
                        draw_progress_bar(stdscr, y_pos, 2, BAR_WIDTH, primary['time_percent'], "5H SESSION", time_details, total_width)
                        y_pos += 2

                        # Session usage bar
                        usage_details = f"Used: {primary['used_percent']:.1f}%"
                        draw_progress_bar(stdscr, y_pos, 2, BAR_WIDTH, primary['used_percent'], "5H USAGE", usage_details, total_width)
                        y_pos += 2

                    # Weekly bars
                    if 'secondary' in data:
                        secondary = data['secondary']

                        # Weekly time bar
                        reset_time_str = secondary['reset_time'].astimezone().strftime('%m-%d %H:%M:%S')
                        outdated_str = " [OUTDATED]" if secondary['outdated'] else ""
                        time_details = f"Reset: {reset_time_str}{outdated_str}"
                        draw_progress_bar(stdscr, y_pos, 2, BAR_WIDTH, secondary['time_percent'], "WEEK TIME", time_details, total_width)
                        y_pos += 2

                        # Weekly usage bar
                        usage_details = f"Used: {secondary['used_percent']:.1f}%"
                        draw_progress_bar(stdscr, y_pos, 2, BAR_WIDTH, secondary['used_percent'], "WEEK USAGE", usage_details, total_width)
                        y_pos += 2

                    # Footer info
                    try:
                        stdscr.addstr(y_pos, 2, "├" + "─" * content_width + "┤")

                        # Last update line
                        # content_width already defined above
                        last_update_content = f" Last update: {data['current_time'].strftime('%Y-%m-%d %H:%M:%S')}"
                        if len(last_update_content) > content_width:
                            last_update_content = last_update_content[:content_width]
                        last_update_padding = content_width - len(last_update_content)
                        last_update_line = f"│{last_update_content}{' ' * last_update_padding}│"
                        stdscr.addstr(y_pos + 1, 2, last_update_line)

                        # Refresh interval line
                        refresh_content = f" Refresh interval: {refresh_interval}s | Press 'q' to quit"
                        if len(refresh_content) > content_width:
                            refresh_content = refresh_content[:content_width]
                        refresh_padding = content_width - len(refresh_content)
                        refresh_line = f"│{refresh_content}{' ' * refresh_padding}│"
                        stdscr.addstr(y_pos + 2, 2, refresh_line)

                        stdscr.addstr(y_pos + 3, 2, "└" + "─" * content_width + "┘")
                    except curses.error:
                        pass

                stdscr.refresh()
                last_refresh = current_time

            time.sleep(0.1)

    # Handle Ctrl+C gracefully
    def signal_handler(sig, frame):
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)

    try:
        curses.wrapper(tui_main)
    except KeyboardInterrupt:
        pass


def main():
    """Main function to parse and display token usage information."""
    parser = argparse.ArgumentParser(description='Parse Claude Code session token usage and rate limits')
    parser.add_argument('--input-folder', '-i', type=str,
                       help='Custom input folder path (default: ~/.codex/sessions)')
    parser.add_argument('--live', action='store_true',
                       help='Launch TUI live monitoring interface')
    parser.add_argument('--interval', type=int, default=10,
                       help='Refresh interval in seconds for live mode (default: 10)')

    args = parser.parse_args()

    # Set up base path
    if args.input_folder:
        base_path = Path(args.input_folder).expanduser()
        if not args.live:
            print(f"Using custom input folder: {base_path}")
    else:
        base_path = get_session_base_path()
        if not args.live:
            print(f"Using default input folder: {base_path}")

    # Launch TUI if --live flag is used
    if args.live:
        run_tui(base_path, args.interval)
        return

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
