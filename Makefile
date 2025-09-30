.PHONY: ids-% ids ids-all verify-all clean
IDS_DIR := docs/knowledge/checks
CSV := docs/knowledge/src/CMG_PromptCategoryFramework_v1.0_2025-08-05.csv

# Build a specific range: make ids-1-15  (RUN WITH `make`, DO NOT paste recipes in shell)
ids-%:
	@mkdir -p $(IDS_DIR)
	@lo=$(word 1,$(subst -, ,$*)); hi=$(word 2,$(subst -, ,$*)); \
	python3 scripts/extract_ids_from_csv.py $(CSV) $(IDS_DIR)/cmg_ids_$*_categories.txt $$lo $$hi; \
	sed -n '1,25p' $(IDS_DIR)/cmg_ids_$*_categories.txt; \
	# if empty (no rows found), delete so it won't pollute ids-all
	test -s $(IDS_DIR)/cmg_ids_$*_categories.txt || rm -f $(IDS_DIR)/cmg_ids_$*_categories.txt

# Wrapper: make ids RANGE=31-45
ids:
	@if [ -z "$(RANGE)" ]; then echo "usage: make ids RANGE=lo-hi (e.g., 1-15)"; exit 2; fi
	@$(MAKE) ids-$(RANGE)

# Combine any built ranges and DEDUP by first ID encountered
ids-all: ids-1-15 ids-16-30 ids-31-45 ids-46-60 ids-61-75
	@awk -F, '/^[0-9]+,/{ if (!seen[$$1]++) print }' \
	  $(IDS_DIR)/cmg_ids_*-[0-9]*_categories.txt \
	  > $(IDS_DIR)/cmg_ids_all_categories.txt
	@echo "Built $(IDS_DIR)/cmg_ids_all_categories.txt"

verify-all:
	@echo "Count:" && wc -l $(IDS_DIR)/cmg_ids_all_categories.txt
	@echo "Unique IDs:" && cut -d, -f1 $(IDS_DIR)/cmg_ids_all_categories.txt | sort -n | uniq -c

clean:
	@rm -f $(IDS_DIR)/cmg_ids_*-[0-9]*_categories.txt $(IDS_DIR)/cmg_ids_all_categories.txt
