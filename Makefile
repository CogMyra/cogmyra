.PHONY: ids-% ids-all verify-all

ids-%:
	@lo=$(word 1,$(subst -, ,$*)); hi=$(word 2,$(subst -, ,$*)); \
	python3 scripts/extract_ids.py docs/knowledge/checks/cmg_ids_$*_categories.txt $$lo $$hi && \
	sed -n '1,25p' docs/knowledge/checks/cmg_ids_$*_categories.txt

# Build common ranges and combine into one file.
# NOTE: the [0-9]* glob excludes "all" so we don't read our own output.
ids-all: ids-1-15 ids-16-30 ids-31-45
	@cat docs/knowledge/checks/cmg_ids_[0-9]*_categories.txt > docs/knowledge/checks/cmg_ids_all_categories.txt
	@echo "Built docs/knowledge/checks/cmg_ids_all_categories.txt"

verify-all:
	@echo "Count:" && wc -l docs/knowledge/checks/cmg_ids_all_categories.txt
	@echo "Unique IDs:" && cut -d, -f1 docs/knowledge/checks/cmg_ids_all_categories.txt | sort -n | uniq -c
