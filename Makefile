# Makefile -- build curriculum chapter PDFs via md2pdf.sh
#
# Every chapter is built with --toc (table of contents). Only chapters that
# embed mermaid diagrams are also built with --mermaid; currently that is just
# week1/chapter1.md.
#
#   make                      build every canonical chapter
#                               (--toc; +--mermaid for chapters that use it)
#   make T=week1/chapter1.md  build ONLY that one chapter (flags auto-detected)
#   make ch1                  shorthand: build week1/chapter1.md
#   make clean                remove generated chapter *.pdf under curriculum/week*/
#   make lint                 shellcheck md2pdf.sh
#
# The file sets are overridable, e.g.:
#   make CHAPTERS="curriculum/week3/chapter18.md curriculum/week3/chapter19.md"
#   make MERMAID_CHAPTERS="curriculum/week1/chapter1.md curriculum/week3/chapter19.md"

CURRICULUM  ?= curriculum
MD2PDF       := bash $(CURDIR)/md2pdf.sh

# Canonical numbered chapters only -- skips day*.md notes and *_vN drafts.
CHAPTERS ?= $(shell ls $(CURRICULUM)/week*/chapter[0-9]*.md 2>/dev/null | grep -vE '(_v[0-9]+)\.')

# Chapters that render mermaid diagrams -> add --mermaid.
MERMAID_CHAPTERS      ?= $(CURRICULUM)/week1/chapter1.md

ifeq ($(strip $(T)),)
.DEFAULT_GOAL := all      # bare `make` builds everything
else
.DEFAULT_GOAL := one      # `make T=...` builds that single chapter
endif

# Build a list of .md files. Each gets --toc, plus --mermaid when its basename
# is listed in MERMAID_CHAPTERS (by basename). md2pdf.sh resolves paths relative to its CWD,
# so we cd into each chapter's directory and pass the basename. A single broken
# chapter is reported but does not abort the rest of the run.
# Usage: $(call RUN,md-list)
define RUN
	@__fail=0; __total=0; \
	for m in $(1); do \
		__f=$$(basename "$$m"); __d=$$(dirname "$$m"); __total=$$((__total + 1)); \
		if printf '%s\n' "$(MERMAID_CHAPTERS)" | while read -r p; do basename "$$p"; done | grep -qxF "$$__f"; then __mf="--mermaid"; else __mf=""; fi; \
		printf 'BUILD %-40s [--toc%s]\n' "$$__f" "$$__mf"; \
		if ! ( cd "$$__d" && $(MD2PDF) --toc $$__mf "$$__f" ); then echo "    !! failed: $$__f" >&2; __fail=$$((__fail + 1)); fi; \
	done; \
	__ok=$$((__total - __fail)); \
	echo "----- built $$__ok/$$__total, $$__fail failed -----"; \
	[ $$__fail -eq 0 ]
endef

.PHONY: all one ch1 lint clean

## build every canonical chapter
all:
	$(call RUN,$(CHAPTERS))

## build one chapter with auto-detected flags: make one T=week1/chapter1.md
one:
	@if [ -z "$(T)" ]; then echo "usage: make one T=week1/chapter1.md" >&2; exit 1; fi
	$(call RUN,$(T))

## shorthand for the single mermaid chapter
ch1:
	@$(MAKE) --no-print-directory one T=$(CURRICULUM)/week1/chapter1.md

## shellcheck the converter
lint:
	shellcheck md2pdf.sh

## remove generated chapter PDFs
clean:
	@rm -f $(CURRICULUM)/week*/chapter[0-9]*.pdf
