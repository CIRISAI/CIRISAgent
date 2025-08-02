# Adaptive Filter Bugs Found During Testing

## 1. Caps Detection False Positive
- **Symptom**: Normal messages trigger caps_abuse filter
- **Test Case**: "Just having a normal conversation" triggers caps_1
- **Expected**: No trigger (regex shouldn't match)
- **Actual**: caps_1 triggers with MEDIUM priority
- **Root Cause**: Unknown - regex test shows no match, but filter triggers anyway

## 2. DM Detection Heuristic Issue (Not tested yet)
- **Issue**: Filter uses "numeric channel ID = DM" heuristic
- **Problem**: ALL Discord channel IDs are numeric (18-digit snowflakes)
- **Impact**: May misclassify regular channels as DMs
- **Note**: Discord adapter already provides is_dm field explicitly

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

## Next Steps
1. Complete test infrastructure (property tests ✅, type safety)
2. Establish baseline metrics ✅
3. THEN fix these bugs with tests to verify