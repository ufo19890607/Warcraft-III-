#!/bin/bash
# map_diff.sh - Compare two .w3x map packages content-diff
# Usage: ./map_diff.sh <old.w3x> <new.w3x>
# Output: <new.w3x dir>/map_diff_<timestamp>.txt (pure text, no ANSI codes)

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
STORMTOOL="$SCRIPT_DIR/stormtool"

# Colors (terminal only)
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BOLD='\033[1m'
NC='\033[0m'

if [ $# -lt 2 ]; then
    echo "Usage: $0 <old.w3x> <new.w3x>"
    exit 1
fi

OLD="$1"
NEW="$2"

if [ ! -f "$OLD" ]; then echo "Error: File not found: $OLD"; exit 1; fi
if [ ! -f "$NEW" ]; then echo "Error: File not found: $NEW"; exit 1; fi

TIMESTAMP=$(date '+%Y%m%d_%H%M%S')
OUTDIR="$(dirname "$NEW")"
OUTFILE="$OUTDIR/map_diff_$TIMESTAMP.txt"
TMPDIR=$(mktemp -d)
trap "rm -rf $TMPDIR" EXIT

mkdir -p "$TMPDIR/old" "$TMPDIR/new"

# Capture all output, strip ANSI for file, keep for terminal
exec > >(tee >(sed 's/\x1b\[[0-9;]*m//g' > "$OUTFILE")) 2>&1

echo "========================================"
echo " WC3 Map Package Content Comparison"
echo " Generated: $(date '+%Y-%m-%d %H:%M:%S')"
echo "========================================"
echo "  OLD: $OLD"
echo "  NEW: $NEW"
echo ""

# ----------------------------------------
# 1. Basic package info
# ----------------------------------------
echo "----------------------------------------"
echo "[1] Basic Info"
echo "----------------------------------------"
OLD_SIZE=$(stat -c%s "$OLD")
NEW_SIZE=$(stat -c%s "$NEW")
OLD_MD5=$(md5sum "$OLD" | cut -d' ' -f1)
NEW_MD5=$(md5sum "$NEW" | cut -d' ' -f1)

echo "  OLD: ${OLD_SIZE} bytes  Modified: $(stat -c'%y' "$OLD")"
echo "  NEW: ${NEW_SIZE} bytes  Modified: $(stat -c'%y' "$NEW")"
if [ "$OLD_MD5" = "$NEW_MD5" ]; then
    echo -e "  Package MD5: ${GREEN}Identical ($OLD_MD5)${NC}"
else
    echo -e "  Package MD5: ${YELLOW}Different (old:$OLD_MD5 new:$NEW_MD5)${NC}"
    echo "    OLD: $OLD_MD5"
    echo "    NEW: $NEW_MD5"
fi
echo ""

# ----------------------------------------
# 2. List all files in both packages
# ----------------------------------------
echo "----------------------------------------"
echo "[2] File List Comparison"
echo "----------------------------------------"

OLD_LIST=$($STORMTOOL list "$OLD" 2>/dev/null | awk '{print $2}' | sort)
NEW_LIST=$($STORMTOOL list "$NEW" 2>/dev/null | awk '{print $2}' | sort)

ONLY_OLD=$(comm -23 <(echo "$OLD_LIST") <(echo "$NEW_LIST"))
ONLY_NEW=$(comm -13 <(echo "$OLD_LIST") <(echo "$NEW_LIST"))
COMMON=$(comm -12 <(echo "$OLD_LIST") <(echo "$NEW_LIST"))

if [ -z "$ONLY_OLD" ] && [ -z "$ONLY_NEW" ]; then
    echo -e "  ${GREEN}√ File list identical${NC}"
else
    [ -n "$ONLY_OLD" ] && echo -e "  ${RED}× Only in OLD:${NC}" && echo "$ONLY_OLD" | sed 's/^/    /'
    [ -n "$ONLY_NEW" ] && echo -e "  ${RED}× Only in NEW:${NC}" && echo "$ONLY_NEW" | sed 's/^/    /'
fi
echo ""

# ----------------------------------------
# 3. Compare common files (md5)
# ----------------------------------------
echo "----------------------------------------"
echo "[3] Content Comparison (md5)"
echo "----------------------------------------"

DIFF_SUMMARY=""

for f in $COMMON; do
    if [[ "$f" == "(listfile)" || "$f" == "(attributes)" || "$f" == "(signature)" ]]; then
        continue
    fi

    $STORMTOOL extract-one "$OLD" "$f" "$TMPDIR/old/$f" 2>/dev/null || true
    $STORMTOOL extract-one "$NEW" "$f" "$TMPDIR/new/$f" 2>/dev/null || true

    OLD_F="$TMPDIR/old/$f"
    NEW_F="$TMPDIR/new/$f"

    if [ ! -f "$OLD_F" ] || [ ! -f "$NEW_F" ]; then
        echo -e "  ${YELLOW}? $f  (extraction failed, skipped)${NC}"
        continue
    fi

    OLD_FSIZE=$(stat -c%s "$OLD_F")
    NEW_FSIZE=$(stat -c%s "$NEW_F")
    OLD_FMD5=$(md5sum "$OLD_F" | cut -d' ' -f1)
    NEW_FMD5=$(md5sum "$NEW_F" | cut -d' ' -f1)

    if [ "$OLD_FMD5" = "$NEW_FMD5" ]; then
        echo -e "  ${GREEN}√ $f  (${OLD_FSIZE} bytes)${NC}"
    else
        echo -e "  ${RED}× $f  OLD:${OLD_FSIZE}B -> NEW:${NEW_FSIZE}B${NC}"
        DIFF_SUMMARY="$DIFF_SUMMARY $f"
    fi
done

echo ""

# ----------------------------------------
# 4. Diff for text files only
# ----------------------------------------
if [ -n "$DIFF_SUMMARY" ]; then
    echo "----------------------------------------"
    echo "[4] Diff Details (text only)"
    echo "----------------------------------------"
    for f in $DIFF_SUMMARY; do
        if file "$TMPDIR/new/$f" 2>/dev/null | grep -qiE 'text|ascii|utf'; then
            echo ""
            echo -e "  ${BOLD}>>> $f <<<${NC}"
            echo "  (- OLD  + NEW)"
            diff -u "$TMPDIR/old/$f" "$TMPDIR/new/$f" | tail -n +3 | head -200 | sed 's/^/  /' || true
            DIFF_LINES=$(diff "$TMPDIR/old/$f" "$TMPDIR/new/$f" | grep -c '^[<>]' || true)
            echo "  ... $DIFF_LINES lines changed"
        else
            echo -e "  ${RED}× $f  (binary file, content differs, skip text diff)${NC}"
        fi
    done
fi

# ----------------------------------------
# 5. Summary
# ----------------------------------------
echo "----------------------------------------"
echo "[5] Summary"
echo "----------------------------------------"
TOTAL=$(echo "$COMMON" | wc -w)
DIFF_COUNT=$(echo "$DIFF_SUMMARY" | wc -w)
SAME_COUNT=$((TOTAL - DIFF_COUNT))
echo "  Total files compared: $TOTAL"
echo -e "  ${GREEN}√ Identical: $SAME_COUNT files${NC}"
if [ "$DIFF_COUNT" -gt 0 ]; then
    echo -e "  ${RED}× Different: $DIFF_COUNT files ($DIFF_SUMMARY )${NC}"
else
    echo -e "  ${GREEN}√ All content identical, packages equivalent${NC}"
fi
echo ""
echo "  Output: $OUTFILE"
echo "========================================"

# Wait for tee subprocess to finish writing
sleep 1
