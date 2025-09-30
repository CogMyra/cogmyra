ids-%:
@lo=$(word 1,$(subst -, ,$*)); hi=$(word 2,$(subst -, ,$*)); \
python3 scripts/extract_ids.py docs/knowledge/checks/cmg_ids_$*_categories.txt $$lo $$hi && \
sed -n '1,25p' docs/knowledge/checks/cmg_ids_$*_categories.txt
