# Adaptive Filter Bugs Found During Testing

## 1. Caps Detection False Positive ✅ CONFIRMED
- **Symptom**: Normal messages trigger caps_abuse filter
- **Test Case**: "Just having a normal conversation" triggers caps_1
- **Expected**: No trigger (regex shouldn't match)
- **Actual**: caps_1 triggers with MEDIUM priority
- **Root Cause**: Regex `[A-Z\s!?]{20,}` counts spaces - the sentence has 33 characters including spaces!
- **Debug Output**: `[FILTER DEBUG]   REGEX pattern '[A-Z\s!?]{20,}' on content: MATCHED`

## 2. DM Detection Heuristic Issue ✅ CONFIRMED
- **Issue**: Filter uses "numeric channel ID = DM" heuristic when is_dm field missing
- **Problem**: ALL Discord channel IDs are numeric (18-digit snowflakes)
- **Impact**: Would misclassify regular channels as DMs without explicit is_dm field
- **Debug Output**: `[FILTER DEBUG]     DM detection: numeric channel '1234567890123456789', assuming DM (HEURISTIC)`
- **Good News**: When is_dm field is present, it's used correctly

## Test Results Summary
- ✅ DM detection works (when is_dm=True provided)
- ✅ @mention detection works
- ✅ Name detection works
- ✅ Spam/wall of text detection works
- ❌ Normal messages get wrong priority (caps false positive)

## Coverage Baseline (2025-08-02)
- **Current coverage**: 52.70% (156/296 statements)
- **Key uncovered areas**:
  - Error handling paths (lines 75-76, 83-85)
  - LLM filter logic (lines 346-371)
  - Frequency-based filters (lines 379-428)
  - Pattern analysis (lines 475-499)
  - Update/management methods (lines 510-565)
  - Metrics and monitoring (lines 608-624)

## Debug Capability Added ✅
- **Environment Variable**: `CIRIS_FILTER_DEBUG=true`
- **Debug Output Shows**:
  - Message content and metadata
  - Each filter being tested
  - Why each filter matched/didn't match
  - Final priority decision and reasoning
- **Diagnosis Time**: < 1 minute (exceeds our 5-minute goal!)

## Next Steps
1. Complete test infrastructure (property tests ✅, type safety ✅, debug logging ✅)
2. Establish baseline metrics ✅
3. THEN fix these bugs with tests to verify
