#!/bin/bash

# md2pdf.sh: Converts Markdown with LaTeX to PDF using pandoc and xelatex.

set -e

TOC_FLAG=""
INPUT_FILE=""

while [[ $# -gt 0 ]]; do
  case $1 in
    --toc)
      TOC_FLAG="--toc"
      shift
      ;;
    *)
      INPUT_FILE="$1"
      shift
      ;;
  esac
done

if [[ -z "$INPUT_FILE" ]]; then
    echo "Usage: $0 [--toc] <input_file.md>"
    exit 1
fi

if [ ! -f "$INPUT_FILE" ]; then
    echo "Error: File '$INPUT_FILE' not found."
    exit 1
fi

OUTPUT_FILE="${INPUT_FILE%.md}.pdf"
TEMP_FILE=$(mktemp /tmp/md2pdf.XXXXXX.md)

echo "Processing '$INPUT_FILE'..."

# Copy the input file to the temp file
cp "$INPUT_FILE" "$TEMP_FILE"

echo "Converting to PDF via pandoc (using xelatex) with $TOC_FLAG..."

if pandoc "$TEMP_FILE" $TOC_FLAG --pdf-engine=xelatex -o "$OUTPUT_FILE"; then
    echo "Success! Created '$OUTPUT_FILE'."
else
    # Fallback to default engine if xelatx fails
    echo "xelatex failed or not found. Retrying with default engine..."
    if pandoc "$TEMP_FILE" $TOC_FLAG -o "$OUTPUT_FILE"; then
        echo "Success! Created '$OUTPUT_FILE' (using default engine)."
    else
        echo "Error: Conversion failed."
        rm -f "$TEMP_FILE"
        exit 1
    fi
fi

rm -f "$TEMP_FILE"
