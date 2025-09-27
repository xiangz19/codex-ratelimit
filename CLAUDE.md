# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a lightweight Python utility that checks Claude Code token usage and rate limits by parsing session files directly from `~/.codex/sessions/`. The tool provides a non-intrusive way to monitor usage without starting new conversations or interrupting workflow.

## Core Architecture

- **Main script**: `ratelimit_checker.py` - Standalone Python 3.6+ script with no external dependencies
- **Session file parsing**: Searches backwards through `~/.codex/sessions/YYYY/MM/DD/rollout-*.jsonl` files
- **Token analysis**: Extracts `token_count` events from JSONL session files to display usage and rate limits
- **Test framework**: Comprehensive test scenarios in `test_scenarios/` directory

## Development Commands

### Running the main utility
```bash
# Default usage (searches ~/.codex/sessions)
python ratelimit_checker.py

# Custom session directory
python ratelimit_checker.py --input-folder /path/to/sessions
python ratelimit_checker.py -i /path/to/sessions
```

### Testing
```bash
# Run all test scenarios
cd test_scenarios/
python run_tests.py

# Test individual scenarios
python ratelimit_checker.py -i test_scenarios/scenario1_normal/
```

### Test data generation
```bash
# Modify timestamps in test files
python test_scenarios/modify_timestamps.py

# Create malformed JSON test data
python test_scenarios/create_malformed.py
```

## Key Implementation Details

### Session File Format
The utility parses JSONL files looking for records with:
- `type: "event_msg"`
- `payload.type: "token_count"`
- Timestamp-based selection for most recent data

### Search Strategy
- Searches backwards from current date up to 30 days
- Processes all `rollout-*.jsonl` files in date-structured directories
- Selects most recent `token_count` event based on ISO timestamp

### Rate Limit Display
- **Primary**: 5-hour window (299 minutes)
- **Secondary**: Weekly window (10079 minutes)
- Calculates actual reset times and marks outdated ones with `[OUTDATED]`

## Testing Architecture

Five comprehensive test scenarios:
1. **scenario1_normal/**: Recent files (Sept 26-27)
2. **scenario2_no_files_today/**: Yesterday's files only
3. **scenario3_old_files_only/**: 3-day old files
4. **scenario4_empty_folder/**: Empty directory handling
5. **scenario5_malformed_json/**: Corrupted JSON resilience

## Error Handling

The utility gracefully handles:
- Missing session directories
- Empty date folders
- Malformed JSON lines (skips and continues)
- File permission errors
- Outdated reset timestamps