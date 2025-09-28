# codex-ratelimit

A lightweight utility to check the token usage and rate limits of your local CODEX installation (CLI or IDE extensions) without interrupting your workflow.

## Background

While the CODEX CLI's `/status` command provides token usage and rate limit information, it has some limitations:

1. **Requires Active Session**: You must send at least one message in a session before using `/status` to get rate limit info
2. **Workflow Interruption**: The `/status` command breaks the natural flow of conversation from the user's perspective (although the command and output don't pollute the context)
3. **Requires Extra Clicks in VS Code Extension**: The VS Code extension does show the rate limit, but you need to click the mouse twice, so a live TUI might still be useful to some users.

This utility provides a non-intrusive way to check your current token usage and rate limits by directly parsing the session files, without needing to start a new conversation or interrupt your workflow.

This utility is inspired by [ccusage](https://github.com/ryoppippi/ccusage); at present ccusage only supports CODEX usage data and does not yet include rate limit information.

## Overview

This tool searches through CODEX session files (stored in `~/.codex/sessions/`) to find the most recent token usage statistics and rate limit information. It provides a clear summary of:

- **Token Usage**: Total and last session input, cached, output, reasoning tokens
- **Rate Limits**: 5-hour and weekly limits with usage percentages and reset times
- **Time Validation**: Automatically marks outdated reset times

## Quick Start

```bash
# Run with default session directory
python ratelimit_checker.py

# Use custom directory
python ratelimit_checker.py --input-folder /path/to/sessions

# Launch live TUI monitoring interface
python ratelimit_checker.py --live

# Live mode with custom refresh interval
python ratelimit_checker.py --live --interval 5

# Live mode with custom warning threshold for color coding
python ratelimit_checker.py --live --warning-threshold 80
```

## Sample Output

### CLI Mode

```
Using default input folder: /Users/username/.codex/sessions
Searching for latest token_count event...
Found latest token_count event in: /Users/username/.codex/sessions/2025/09/27/rollout-2025-09-27T15-27-13-01998a11-9bd4-7880-a0a8-5bf579f59db3.jsonl
total: input 5200, cached 2048, output 14, reasoning 0, subtotal 5214
last:  input 5200, cached 2048, output 14, reasoning 0, subtotal 5214
5h limit: used 0.0%, reset: 2025-09-27 12:26:21
weekly limit: used 22.0%, reset: 2025-10-01 09:04:07
```

### Live TUI Mode

```
  ┌────────────────────────────────────────────────────────────────────────┐
  │                  CODEX RATELIMIT - LIVE USAGE MONITOR                  │
  ├────────────────────────────────────────────────────────────────────────┤
  │ 5H SESSION   [----------------------------------------------]    N/A   │
  │    Reset: 09-28 04:51:36 [OUTDATED]                                    │
  ├────────────────────────────────────────────────────────────────────────┤
  │ 5H USAGE     [----------------------------------------------]    N/A   │
  ├────────────────────────────────────────────────────────────────────────┤
  │ WEEKLY TIME  [█████████████████████░░░░░░░░░░░░░░░░░░░░░░░░░]  47.6%   │
  │    Reset: 10-01 17:04:14                                               │
  ├────────────────────────────────────────────────────────────────────────┤
  │ WEEKLY USAGE [███████████████░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░]  34.0%   │
  ├────────────────────────────────────────────────────────────────────────┤
  │ Last update: 2025-09-28 12:22:07                                       │
  │ Refresh interval: 60s | Press 'q' to quit                              │
  └────────────────────────────────────────────────────────────────────────┘

```

## Features

### Key Capabilities
- **Smart Discovery**: Searches backwards up to 7 days to find the most recent token usage data
- **Complete Analysis**: Shows total/last token usage and both rate limit statuses
- **Time Awareness**: Calculates and validates reset times, marking outdated ones
- **Robust Processing**: Handles missing files, empty directories, and corrupted JSON gracefully
- **Live TUI Monitor**: Real-time monitoring interface with progress bars for usage and time limits

## Command Line Options

```bash
python ratelimit_checker.py [OPTIONS]

Options:
  -h, --help                    Show help message
  -i, --input-folder PATH       Custom input folder path (default: ~/.codex/sessions)
  --live                        Launch TUI live monitoring interface
  --interval SECONDS            Refresh interval in seconds for live mode (default: 10)
  --warning-threshold PERCENT   Usage percentage threshold for warning color (default: 70)
```

## Live TUI Interface

The `--live` option launches a real-time monitoring interface similar to `ccusage blocks --live`, featuring:

- **4 Progress Bars**:
  - **5H TIME**: Time elapsed in 5-hour window
  - **5H USAGE**: Usage percentage in 5-hour limit (colored: green < threshold, red ≥ threshold)
  - **WEEKLY TIME**: Time elapsed in weekly window
  - **WEEKLY USAGE**: Usage percentage in weekly limit (colored: green < threshold, red ≥ threshold)
- **Color Coding**: Usage bars are green when below warning threshold (default 70%), red when above
- **Reset Times**: Shows when limits reset (marks outdated limits)
- **Auto-refresh**: Updates data at specified interval (default: 10 seconds)
- **Outdated Data**: Shows "N/A" with dash-filled bars for expired rate limit data


## File Structure

The utility expects CODEX session files in this structure:
```
~/.codex/sessions/
├── 2025/
│   ├── 09/
│   │   ├── 27/
│   │   │   ├── rollout-2025-09-27T15-27-13-*.jsonl
│   │   │   └── rollout-2025-09-27T15-33-50-*.jsonl
│   │   └── 26/
│   │       └── rollout-2025-09-26T18-49-09-*.jsonl
│   └── 08/
│       └── ...
```

## How It Works

1. Searches backwards from today through the `YYYY/MM/DD/` directory structure
2. Examines all `rollout-*.jsonl` files to find `token_count` events
3. Selects the most recent event based on timestamp
4. Extracts and formats token usage and rate limit data


## Requirements

- Python 3.6+
- Standard library only (no external dependencies)

## Session File Format

The utility parses JSONL files where each line contains a JSON record. It specifically looks for records like:

```json
{
  "timestamp": "2025-09-27T07:27:21.415Z",
  "type": "event_msg",
  "payload": {
    "type": "token_count",
    "info": {
      "total_token_usage": {
        "input_tokens": 5200,
        "cached_input_tokens": 2048,
        "output_tokens": 14,
        "reasoning_output_tokens": 0,
        "total_tokens": 5214
      },
      "last_token_usage": {
        "input_tokens": 5200,
        "cached_input_tokens": 2048,
        "output_tokens": 14,
        "reasoning_output_tokens": 0,
        "total_tokens": 5214
      }
    },
    "rate_limits": {
      "primary": {
        "used_percent": 0.0,
        "window_minutes": 299,
        "resets_in_seconds": 17940
      },
      "secondary": {
        "used_percent": 22.0,
        "window_minutes": 10079,
        "resets_in_seconds": 351406
      }
    }
  }
}
```

## Troubleshooting

### No token_count events found
- Verify the session directory path is correct
- Check if session files exist in the expected date structure
- Ensure files are not older than 7 days (extend search range if needed)

### Incorrect timestamps
- The utility uses the session file's timestamp, not current time
- Reset times are calculated as: session_timestamp + reset_in_seconds
- Times are displayed in local timezone

### Permission errors
- Ensure read access to the session directory
- Check file permissions on the session files

## License

This tool is designed for personal use with CODEX session data. Ensure compliance with Anthropic's terms of service when analyzing session data.
