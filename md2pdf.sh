#!/bin/bash

# md2pdf.sh: Converts Markdown with LaTeX to PDF using pandoc and xelatex.

set -e

TOC_FLAG=""
MERMAID_FLAG=""
GEOMETRY_FLAG=""
MARGIN_HEADER_FILE=""

while [[ $# -gt 0 ]]; do
  echo "Arg: $1"
  case $1 in
     --toc)
      TOC_FLAG="--toc"
      shift
      ;;
     --mermaid)
      MERMAID_FLAG="--filter mermaid-filter"
      shift
      ;;
     --margin)
      shift
      if [[ $# -eq 0 ]]; then
        echo "Error: --margin requires a value (e.g. 0.5in, 1cm, 0.3in)." >&2
        exit 1
      fi
      MARGIN_VAL="$1"
      shift
      MARGIN_HEADER_FILE=$(mktemp /tmp/md2pdf_geometry_$$_XXXXXX)
      echo "\usepackage[margin=${MARGIN_VAL}]{geometry}" > "$MARGIN_HEADER_FILE"
      GEOMETRY_FLAG="--include-in-header=$MARGIN_HEADER_FILE"
      ;;
     *)
      INPUT_FILE="$1"
      shift
      ;;
  esac
done

if [[ -z "$INPUT_FILE" ]]; then
    echo "Usage: $0 [--toc] [--mermaid] [--margin MARGIN] <input_file.md>"
    echo "    --margin MARGIN   Set page margins on all sides (e.g. 0.5in, 1cm, 0.3in)."
    exit 1
fi

if [ ! -f "$INPUT_FILE" ]; then
    echo "Error: File '$INPUT_FILE' not found."
    exit 1
fi

OUTPUT_FILE="${INPUT_FILE%.md}.pdf"
TEMP_FILE=$(mktemp /tmp/md2pdf.XXXXXX.md)

echo "Processing '$INPUT_FILE'..."

# Pre-process to convert [ ... ] math blocks to $$ ... $$
# We use a more robust regex to handle potential whitespace
sed -e 's/^[[:space:]]*\[[[:space:]]*$/$$\n/' \
     -e 's/^[[:space:]]*\][[:space:]]*$/\n$$/' \
     "$INPUT_FILE" > "$TEMP_FILE"

echo "Converting to PDF via pandoc (using xelatex) with $TOC_FLAG $MERMAID_FLAG $GEOMETRY_FLAG..."

if pandoc "$TEMP_FILE" $TOC_FLAG $MERMAID_FLAG $GEOMETRY_FLAG --pdf-engine=xelatex -o "$OUTPUT_FILE"; then
    echo "Success! Created '$OUTPUT_FILE'."
else
    # Fallback to default engine if xelatex fails
    echo "xelatex failed or not found. Retrying with default engine..."
    if pandoc "$TEMP_FILE" $TOC_FLAG $MERMAID_FLAG $GEOMETRY_FLAG -o "$OUTPUT_FILE"; then
        echo "Success! Created '$OUTPUT_FILE' (using default engine)."
    else
        echo "Error: Conversion failed."
        rm -f "$TEMP_FILE" "$MARGIN_HEADER_FILE"
        exit 1
    fi
fi

rm -f "$TEMP_FILE" "$MARGIN_HEADER_FILE"
